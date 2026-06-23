import logging
import re
from typing import AsyncGenerator
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
from sqlalchemy.orm import Session
from app.config.settings import get_settings
from app.models.models import User
from app.rag.ollama_client import OllamaClient
from app.rag.prompt_engineering import PromptEngineer
from app.rag.vector_store import get_vector_store

logger = logging.getLogger(__name__)

NOT_FOUND = "I'm sorry, but I couldn't find the information you're looking for in the uploaded documents. Please try rephrasing your question or ask about a different topic."

MIN_CHUNK_SCORE = 0.05

MMR_LAMBDA = 0.90


class RAGService:

    def __init__(self) -> None:
        self.settings = get_settings()
        self.vector_store = get_vector_store()
        self.ollama = OllamaClient()

    async def answer(
        self,
        db: Session,
        user: User,
        question: str,
        conversation_history: list[dict] | None = None,
        model: str | None = None,
        top_k: int | None = None,
    ) -> dict:

        try:
            question = (question or "").strip()
            if not question:
                return {"answer": "Please enter a valid question.", "sources": [], "confidence": 0.0}

            self._current_question = question
            requested_top_k = top_k or self.settings.rag_top_k

            #Multi-Query Retrieval Strategy
            retrieval_queries = self._generate_retrieval_queries(
                question, conversation_history
            )

        
            all_search_results = []
            seen_chunk_fingerprints = set()
            for retrieval_query in retrieval_queries:
                search_results = self.vector_store.search(retrieval_query, requested_top_k * 2)
                for result in search_results:
                    fingerprint = self._chunk_fingerprint(result.get("text", ""))
                    if fingerprint not in seen_chunk_fingerprints:
                        seen_chunk_fingerprints.add(fingerprint)
                        all_search_results.append(result)

            if not all_search_results:
                return {"answer": NOT_FOUND, "sources": [], "confidence": 0.0}

            #Relevance-Aware Ranking
            ranked_results = self._rank_results(
                question, all_search_results,
                conversation_history=conversation_history,
            )

            #Relevance Check with keyword fallback
            if not self._is_retrieval_relevant(question, ranked_results, conversation_history):
                keyword_query = self._extract_keywords(question)
                search_results = self.vector_store.search(keyword_query, requested_top_k * 2)
                if len(retrieval_queries) > 1:
                    fallback_results = self.vector_store.search(question, requested_top_k * 2)
                    seen_fp = set()
                    merged = []
                    for r in search_results + fallback_results:
                        fp = self._chunk_fingerprint(r.get("text", ""))
                        if fp not in seen_fp:
                            seen_fp.add(fp)
                            merged.append(r)
                    search_results = merged

                ranked_results = self._rank_results(
                    question, search_results,
                    conversation_history=conversation_history,
                )
                if not self._is_retrieval_relevant(question, ranked_results, conversation_history):
                    return {"answer": NOT_FOUND, "sources": [], "confidence": 0.0}

            #Chunk Selection
            relevant_chunks = self._select_best_chunks_mmr(
                ranked_results, question
            )
            if not relevant_chunks:
                return {"answer": NOT_FOUND, "sources": [], "confidence": 0.0}

            #Build Context
            context_blocks, sources = self._build_context(relevant_chunks)
            if not context_blocks:
                return {"answer": NOT_FOUND, "sources": [], "confidence": 0.0}

            #Deduplicate and organize context
            context_blocks = self._synthesize_context_blocks(context_blocks)
            if len(context_blocks) > 1:
                context_blocks = self._group_context_by_similarity(context_blocks)

            retrieval_confidence = self._compute_retrieval_confidence(relevant_chunks)
            if retrieval_confidence < 0.40:
                return {
                    "answer": NOT_FOUND,
                    "sources": [],
                    "confidence": retrieval_confidence,
                }

            #Build Prompt
            prompt = PromptEngineer.build_prompt(question, context_blocks, conversation_history)

            #Generate Answer
            answer = await self._generate_answer(
                prompt, question, relevant_chunks, model
            )

            #Post-Process
            answer = self._post_process_answer(answer, question)

            answer_terms = self._terms(answer)

            chunk_terms = set()
            for chunk in relevant_chunks:
                chunk_terms.update(self._terms(chunk.get("text", "")))

            supported_ratio = (
                len(answer_terms.intersection(chunk_terms))
                / max(len(answer_terms), 1)
            )

            if supported_ratio < 0.10:
                return {
                    "answer": NOT_FOUND,
                    "sources": [],
                    "confidence": 0.0,
                }
            
            sources = self._filter_sources_by_answer_usage(answer, relevant_chunks, sources, question)
            if self._is_not_found_response(answer):
                sources = []

            calibrated_confidence = self._calibrate_confidence(
                retrieval_confidence, answer, relevant_chunks, question
            )

            return {
                "answer": answer,
                "sources": sources,
                "confidence": max(0.10, min(round(calibrated_confidence, 3), 0.99)),
            }

        except Exception as e:
            logger.exception(f"RAG pipeline failed: {str(e)}")
            return {"answer": "An error occurred while processing your request.", "sources": [], "confidence": 0.0}

    def _generate_retrieval_queries(
        self,
        question: str,
        conversation_history: list[dict] | None = None,
    ) -> list[str]:
        """
        Generate multiple retrieval query variants for better coverage.
        Returns queries ordered from most specific to most general.
        """
        queries = []
        base_query = re.sub(r'[?]+\s*$', '', question).strip()

        # 1. Original question
        queries.append(base_query)

        # 2. Expanded with context terms (for follow-ups)
        if conversation_history and self._needs_context_expansion(question):
            extra_terms = self._extract_context_terms(conversation_history, question)
            if extra_terms:
                queries.append(f"{base_query} {' '.join(sorted(extra_terms))}")

        # 3. Keyword-only query (extracted important terms)
        keyword_query = self._extract_keywords(question)
        if keyword_query and len(keyword_query) > 3 and keyword_query != question.lower():
            queries.append(keyword_query)

        # Deduplicate while preserving order
        seen = set()
        unique_queries = []
        for q in queries:
            q_norm = q.lower().strip()
            if q_norm not in seen:
                seen.add(q_norm)
                unique_queries.append(q)

        return unique_queries

    def _extract_keywords(self, question: str) -> str:
        """Extract meaningful keywords from a question for fallback search."""
        question_terms = self._terms(question)
        return " ".join(sorted(question_terms)) if question_terms else question

    def _rank_results(
        self,
        question: str,
        results: list[dict],
        conversation_history: list[dict] | None = None,
    ) -> list[dict]:
        """
        Rank results using:
        1. Semantic similarity score (from vector search with hybrid boost)
        2. Term overlap with question
        3. Context term overlap for follow-up questions
        4. Position penalty for very low-ranked results
        """
        if not results:
            return []

        question_terms = self._terms(question)

        # Context terms for follow-up questions
        is_follow_up = self._needs_context_expansion(question)
        context_terms = set()
        if is_follow_up and conversation_history:
            context_terms = self._extract_context_terms(conversation_history, question)

        ranked = []

        for row in results:
            text = row.get("text", "")
            text_lower = text.lower()
            text_terms = self._terms(text)

            # Semantic score from vector store
            semantic_score = float(row.get("confidence", 0.0))

            # Term overlap with question
            exact_matches = len(question_terms.intersection(text_terms))
            coverage = exact_matches / max(len(question_terms), 1) if question_terms else 0

            # Context overlap (for follow-ups)
            context_overlap_ratio = 0.0
            if context_terms:
                context_overlap = len(context_terms.intersection(text_terms))
                context_overlap_ratio = context_overlap / max(len(context_terms), 1)

            # Exact phrase match bonus
            phrase_boost = 0.0
            if len(question_terms) >= 2:
                question_words = re.findall(r'\b[a-zA-Z]{3,}\b', question.lower())
                for window_size in [3, 2]:
                    for i in range(len(question_words) - window_size + 1):
                        phrase = ' '.join(question_words[i:i+window_size])
                        if phrase in text_lower:
                            phrase_boost = max(phrase_boost, 0.12)
                            break
                    if phrase_boost > 0:
                        break

            final_score = (
                semantic_score * 0.35 +
                coverage * 0.30 +
                min(exact_matches / 4, 1.0) * 0.15 +
                context_overlap_ratio * 0.05 +
                phrase_boost
            )

            ranked.append({
                **row,
                "final_score": round(min(final_score, 1.0), 4),
            })

        return sorted(ranked, key=lambda item: item["final_score"], reverse=True)

    def _group_context_by_similarity(self, context_blocks: list[str]) -> list[str]:
        """
        Group context blocks by semantic similarity before prompt generation.
        Adjacent blocks that share high word overlap are grouped together with separators.
        """
        if not context_blocks or len(context_blocks) <= 1:
            return context_blocks

        groups = []
        current_group = [context_blocks[0]]
        current_terms = set(re.findall(r'\b[a-zA-Z]{4,}\b', context_blocks[0].lower()))

        for block in context_blocks[1:]:
            block_terms = set(re.findall(r'\b[a-zA-Z]{4,}\b', block.lower()))
            if not current_terms or not block_terms:
                overlap_ratio = 0.0
            else:
                overlap = len(current_terms.intersection(block_terms))
                overlap_ratio = overlap / max(len(current_terms), 1)

            if overlap_ratio > 0.15:
                current_group.append(block)
                current_terms.update(block_terms)
            else:
                groups.append(current_group)
                current_group = [block]
                current_terms = block_terms

        if current_group:
            groups.append(current_group)

        merged = []
        for group in groups:
            if len(group) == 1:
                merged.append(group[0])
            else:
                merged.append("\n--- Related Content ---\n" + "\n\n".join(group))

        return merged

    def _synthesize_context_blocks(self, context_blocks: list[str]) -> list[str]:
        """Deduplicate overlapping context blocks using significant word fingerprints."""
        if not context_blocks or len(context_blocks) <= 1:
            return context_blocks

        synthesized = []
        seen_fingerprints = set()

        for block in context_blocks:
            words = re.findall(r'\b[a-zA-Z]{4,}\b', block.lower())
            significant_words = set(words)
            if not significant_words:
                synthesized.append(block)
                continue

            is_duplicate = False
            for seen_fp in seen_fingerprints:
                overlap = len(significant_words.intersection(seen_fp))
                smaller = min(len(significant_words), len(seen_fp))
                if smaller > 0 and overlap / smaller > 0.95:
                    is_duplicate = True
                    break

            if not is_duplicate:
                seen_fingerprints.add(frozenset(significant_words))
                synthesized.append(block)

        return synthesized if synthesized else context_blocks

    async def _generate_answer(
        self,
        prompt: str,
        question: str,
        relevant_chunks: list[dict],
        model: str | None = None,
    ) -> str:
        """Generate answer with retry logic for quality."""
        answer = ""
        try:
            answer = (await self.ollama.generate(prompt=prompt, model=model)).strip()
        except Exception as e:
            logger.exception(f"LLM generation failed: {str(e)}")

        min_words = self._minimum_answer_words(question)
        word_count = len(answer.split())

        needs_retry = (
            not answer
            or word_count < min_words
            or self._looks_like_raw_chunk(answer)
            or self._is_all_bold_or_heading(answer)
            or self._has_consecutive_repeated_lines(answer)
        )

        if needs_retry and not self._is_not_found_response(answer):
            retry_prompt = (
                prompt + "\n\n"
                "IMPORTANT: Please rewrite your answer following these rules:\n"
                "Provide a complete answer using ALL relevant retrieved information. "
                "For definitions include important characteristics, types, features, steps, examples, or explanations whenever present in the retrieved context. "
                "Do not stop after a short definition if additional relevant information exists."
                + PromptEngineer.synthesis_reminder() + "\n"
                + PromptEngineer.direct_answer_reminder() + "\n"
                "Format your answer cleanly. Use proper markdown for lists, tables, and steps."
            )
            try:
                retry_answer = (await self.ollama.generate(prompt=retry_prompt, model=model)).strip()
                if retry_answer and len(retry_answer.split()) >= min_words:
                    if not self._looks_like_raw_chunk(retry_answer):
                        answer = retry_answer
            except Exception as e:
                logger.exception(f"Retry generation failed: {str(e)}")

        if not answer:
            answer = NOT_FOUND

        return answer

    def _is_all_bold_or_heading(self, answer: str) -> bool:
        if not answer:
            return False
        stripped = answer.strip()
        if stripped.startswith("**") and stripped.endswith("**"):
            inner = stripped[2:-2].strip()
            if len(inner) < len(stripped) * 0.8:
                return True
        return False

    def _has_consecutive_repeated_lines(self, answer: str) -> bool:
        if not answer:
            return False
        lines = answer.strip().split("\n")
        for i in range(len(lines) - 1):
            if lines[i].strip().lower() == lines[i + 1].strip().lower():
                return True
        return False

    def _post_process_answer(self, answer: str, question: str) -> str:
        """Clean and polish the generated answer."""
        if not answer:
            return answer

        # Strip any HTML/XML tags that may have been generated by the LLM
        answer = re.sub(r"<[^>]+>", "", answer)

        answer = PromptEngineer.clean_response(answer, question)

        answer = re.sub(
            r"```+\w*\s*\n\s*//.*?\n\s*```+",
            "",
            answer,
            flags=re.DOTALL
        )

        answer = self._clean_natural_answer(answer)
        answer = self._fix_sentence_capitalization(answer)
        answer = self._fix_ocr_artifacts(answer)
        answer = PromptEngineer.polish_answer(answer)

        # Fix common markdown issues
        answer = self._fix_markdown_formatting(answer)

        # Trim excessively long answers at sentence boundaries
        if len(answer) > 4000:
            sentences = re.split(r'(?<=[.!?])\s+', answer)

            truncated = []
            char_count = 0

            for sentence in sentences:
                char_count += len(sentence) + 1

                if char_count > 3800:
                    break

                truncated.append(sentence)

            answer = " ".join(truncated)

        # Remove repeated question if model echoes it
        question_clean = (question or "").strip().lower()
        answer_clean = (answer or "").strip().lower()

        if question_clean and answer_clean.startswith(question_clean):
            answer = answer[len(question):].strip()

        return answer.strip()

    def _fix_markdown_formatting(self, text: str) -> str:
        """Ensures consistent markdown structural formatting without destroying list blocks or trailing bold nodes."""
        if not text:
            return text

        # 1. Temporarily isolate code blocks to avoid mangling valid technical syntax layouts
        code_blocks = []
        def preserve_code(match):
            code_blocks.append(match.group(0))
            return f"__CODE_BLOCK_{len(code_blocks)-1}__"

        text = re.sub(r"```.*?```", preserve_code, text, flags=re.DOTALL)
        text = re.sub(r"`.*?`", preserve_code, text, flags=re.DOTALL)

        # Remove generic extraction tags out of line blocks
        text = re.sub(r"<[^>]+>", "", text)

        # 2. FIXED: Universal spacing padding around inline bold terms without splitting punctuation transitions
        text = re.sub(r'\s*\*\*([^\*]+)\*\*\s*', r' **\1** ', text)
        text = re.sub(r'\s+([.,;:!?])', r'\1', text)

        # 3. Clean up list item markers missing markdown white-space constraints
        text = re.sub(r'(?m)^(\s*[-*•+])([A-Za-z0-9_*])', r'\1 \2', text)

        # Fix numbered lists that lost their dots
        text = re.sub(r'(?m)^(\s*\d+)([A-Za-z_*])', r'\1. \2', text)

        # 4. DYNAMIC: Detect any colon-delimited list of items in a sentence and convert to bullet points.
        # Handles patterns like "There are three types: Type A, Type B, and Type C" without
        # hardcoding any specific topic names. Only triggers when 3+ items are present.
        text = re.sub(
            r'(?<=\w)(?<!\n)\s*:\s*([A-Za-z][A-Za-z0-9_ \-&/()]+)(?:,\s*|\s+and\s+|\s+or\s+)([A-Za-z][A-Za-z0-9_ \-&/()]+)(?:,\s*|\s+and\s+|\s+or\s+)([A-Za-z][A-Za-z0-9_ \-&/()]+)',
            lambda m: ':\n\n• ' + m.group(1).strip() + '\n• ' + m.group(2).strip() + '\n• ' + m.group(3).strip(),
            text
        )
        # Also catch cases where a colon already introduces a list on the next line, but items are inline
        text = re.sub(r'([.])\s*[*•+-]\s*', r'\1\n\n• ', text)

        # Ensure markdown table alignment markers are correct
        text = re.sub(
            r'(?m)^(\|[\s:]*-+[\s:]*\|)+$',
            lambda m: self._fix_table_separator(m.group(0)),
            text
        )

        text = re.sub(
            r'([A-Za-z]):\*\*',
            r'\1:\n\n**',
            text
        )

        # 5. FIXED: Ensure explicit block line returns (\n\n) precede lists so frontends parse layout changes correctly
        text = re.sub(r'\n*(?=\s*[-*•+]|\s*\d+\.)', '\n\n', text)

        # FIXED: Removed the destructive trailing multiline bold stripper regex entirely to prevent raw unclosed tag artifacts

        # 6. Restore code blocks unharmed
        for i, block in enumerate(code_blocks):
            text = text.replace(f"__CODE_BLOCK_{i}__", block)

        # Ensure multi-newline formatting collapses gracefully without flattening markdown boundaries
        text = re.sub(r'\n{3,}', '\n\n', text)

        return text.strip()

    def _fix_table_separator(self, separator_line: str) -> str:
        """
        Universally cleans markdown table alignment rows, preserving column balance 
        without creating double-pipe walls or dropping columns.
        """
        # 1. Clean up surrounding whitespace first, then isolate internal columns
        clean_line = separator_line.strip()
        
        # Safely drop only the single outermost wall boundaries if they exist
        if clean_line.startswith('|'):
            clean_line = clean_line[1:]
        if clean_line.endswith('|'):
            clean_line = clean_line[:-1]
            
        # 2. Split columns cleanly (keeping empty spaces intact to preserve column counts)
        parts = clean_line.split('|')
        fixed_parts = []
        
        for part in parts:
            part = part.strip()
            
            # If the cell already holds a valid alignment context (like :---, ---:, or :---:), pass it through
            if re.match(r'^:?-+:?$', part):
                fixed_parts.append(part)
            else:
                # FIXED: Instead of skipping or continuing (which deletes columns), fallback to left-alignment
                # This ensures the column count always exactly matches the data rows!
                fixed_parts.append(':---')
                
        # 3. Securely stitch the grid back together wrapped in exactly one outer pipe wall pair
        return '| ' + ' | '.join(fixed_parts) + ' |'

    def _clean_natural_answer(self, answer: str) -> str:
        """Remove grounding filler, meta-commentary, and unnatural phrasing."""
        if not answer:
            return answer

        text = answer.strip()

        filler_patterns = [
            r"(?i)^\s*based on (the )?(uploaded |provided )?documents?[^.]*\.?\s*\n?",
            r"(?i)^\s*according to (the )?(uploaded |provided )?(notes|pdfs|materials|documents|text|context)[^.]*\.?\s*\n?",
            r"(?i)^\s*another definition from[^.]*\.?\s*\n?",
            r"(?i)^\s*retrieved information shows[^.]*\.?\s*\n?",
            r"(?i)^\s*the document explains[^.]*\.?\s*\n?",
            r"(?i)^\s*the (uploaded |provided )?documents (state|indicate|mention|contain|provide)[^.]*\.?\s*\n?",
            r"(?i)^\s*from the (uploaded |provided )?context[^.]*\.?\s*\n?",
            r"(?i)^\s*in essence,?\s*",
            r"(?i)^\s*from a high-level perspective,?\s*",
            r"(?i)^\s*it can be concluded,?\s*",
            r"(?i)^\s*therefore we can conclude,?\s*",
            r"(?i)^\s*the above discussion,?\s*",
            r"(?i)^\s*as discussed above,?\s*",
            r"(?i)^\s*here is (the )?(direct )?(answer|response):?\s*",
            r"(?i)^\s*the (direct )?(answer|response) is:?\s*",
            r"(?i)^\s*here is (a )?(brief )?(definition|explanation|comparison):?\s*",
            r"(?i)^\s*here are (some of )?(the )?(key )?(types|features|advantages|disadvantages|categories)?:?\s*",
            r"(?i)^\s*here is a list of[^:]*:?\s*",
            r"(?i)^\s*the following (is|are)[^:]*:?\s*",
            r"(?i)^\s*sure,? here is[^:]*:?\s*",
        ]
        for pattern in filler_patterns:
            text = re.sub(pattern, "", text).strip()

        inline_patterns = [
            r"(?i)\baccording to the (uploaded |provided )?(notes|pdfs|materials|documents|text|context)\b,?\s*",
            r"(?i)\bfrom the uploaded (materials|documents|text|context)\b,?\s*",
            r"(?i)\bthe document explains\b,?\s*",
            r"(?i)\btherefore we can conclude\b,?\s*",
            r"(?i)\bbased on the (uploaded |provided )?documents?\b,?\s*",
            r"(?i)\bbased on the context\b,?\s*",
            r"(?i)\bthe requested information was found in the (uploaded |provided )?documents?\.?\s*",
            r"(?i)\bthe table follows markdown syntax\.?\s*",
            r"(?i)\bin essence\b,?\s*",
            r"(?i)\bfrom a high-level perspective\b,?\s*",
        ]
        for pattern in inline_patterns:
            text = re.sub(pattern, "", text).strip()

        text = re.sub(r"(?i)\n*##?\s*(Note|Summary|Additional Information|References|Sources|Conclusion|Key Takeaways|Final Thoughts|Disclaimer|Important)\s*[:\s]?\s*\n?.*$", "", text, flags=re.DOTALL)
        text = re.sub(r"(?i)\n*\*\*(Note|Summary|Additional Information|References|Sources|Conclusion|Key Takeaways|Final Thoughts|Disclaimer|Important)\s*[:\s]?\s*\*\*\s*\n?.*$", "", text, flags=re.DOTALL)

        return text.strip()

    def _fix_sentence_capitalization(self, text: str) -> str:
        if not text:
            return text
        sentences = re.split(r'(?<=[.!?])\s+', text)
        fixed = []
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence and sentence[0].islower():
                sentence = sentence[0].upper() + sentence[1:]
            fixed.append(sentence)
        return " ".join(fixed)

    def _fix_ocr_artifacts(self, text: str) -> str:
        if not text:
            return text

        ocr_fixes = {
            r'\bde\s+ned\b': 'defined',
            r'\bde\s+ning\b': 'defining',
            r'\becient\b': 'efficient',
            r'\beciency\b': 'efficiency',
            r'\bdierent\b': 'different',
            r'\bdierence\b': 'difference',
            r'\bspecied\b': 'specified',
            r'\bbriey\b': 'briefly',
            r'\bde\s+scribe\b': 'describe',
            r'\bim\s+portant\b': 'important',
            r'\bper\s+form\b': 'perform',
            r'\bper\s+formance\b': 'performance',
            r'\bim\s+plement\b': 'implement',
            r'\bim\s+plementation\b': 'implementation',
            r'\bcom\s+ponent\b': 'component',
            r'\bcom\s+ponents\b': 'components',
            r'\bstruc\s+ture\b': 'structure',
            r'\bpro\s+cess\b': 'process',
            r'\bpro\s+cessing\b': 'processing',
            r'\bpro\s+gram\b': 'program',
            r'\bpro\s+gramming\b': 'programming',
            r'\bcon\s+cept\b': 'concept',
            r'\bcon\s+cepts\b': 'concepts',
            r'\bcon\s+figuration\b': 'configuration',
            r'\bcon\s+trol\b': 'control',
            r'\bcon\s+tain\b': 'contain',
            r'\bcon\s+text\b': 'context',
            r'\bcon\s+tent\b': 'content',
            r'\bappli\s+cation\b': 'application',
            r'\bappli\s+cations\b': 'applications',
            r'\bopera\s+tion\b': 'operation',
            r'\bopera\s+tions\b': 'operations',
            r'\bfunc\s+tion\b': 'function',
            r'\bfunc\s+tions\b': 'functions',
        }

        for pattern, replacement in ocr_fixes.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)
        text = re.sub(r'\s+([.,;:!?])', r'\1', text)
        text = re.sub(r' {2,}', ' ', text)
        return text

    def _calibrate_confidence(
        self, retrieval_confidence: float, answer: str,
        relevant_chunks: list[dict], question: str,
    ) -> float:
        if not answer:
            return retrieval_confidence * 0.5

        min_words = self._minimum_answer_words(question)
        word_count = len(answer.split())
        length_factor = min(1.0, word_count / max(min_words * 1.5, 10))

        question_terms = self._terms(question)
        answer_terms = self._terms(answer)
        coverage_factor = (
            len(question_terms.intersection(answer_terms)) / len(question_terms)
            if question_terms else 1.0
        )

        all_chunk_terms = set()
        for chunk in relevant_chunks:
            all_chunk_terms.update(self._terms(chunk.get("text", "")))
        hallucination_penalty = 1.0
        if all_chunk_terms and answer_terms:
            unseen_terms = answer_terms - all_chunk_terms - question_terms
            unseen_ratio = len(unseen_terms) / len(answer_terms) if answer_terms else 0
            hallucination_penalty = max(0.0, 1.0 - max(0, unseen_ratio - 0.30) * 1.5)

        calibrated = (
            retrieval_confidence * 0.50 +
            length_factor * 0.20 +
            coverage_factor * 0.20 +
            hallucination_penalty * 0.10
        )
        return max(0.0, min(calibrated, 1.0))

    async def stream_answer(
        self, question: str, conversation_history: list[dict] | None = None,
        model: str | None = None, top_k: int | None = None,
    ) -> AsyncGenerator[str, None]:
        try:
            question = (question or "").strip()
            if not question:
                yield "Please enter a valid question."
                return

            requested_top_k = top_k or self.settings.rag_top_k

            retrieval_queries = self._generate_retrieval_queries(
                question, conversation_history
            )

            all_search_results = []
            seen_chunk_fingerprints = set()
            for retrieval_query in retrieval_queries:
                search_results = self.vector_store.search(retrieval_query, requested_top_k * 2)
                for result in search_results:
                    fingerprint = self._chunk_fingerprint(result.get("text", ""))
                    if fingerprint not in seen_chunk_fingerprints:
                        seen_chunk_fingerprints.add(fingerprint)
                        all_search_results.append(result)

            if not all_search_results:
                yield NOT_FOUND
                return

            ranked_results = self._rank_results(
                question, all_search_results,
                conversation_history=conversation_history,
            )

            if not self._is_retrieval_relevant(question, ranked_results, conversation_history):
                yield NOT_FOUND
                return

            relevant_chunks = self._select_best_chunks_mmr(
                ranked_results, question,
            )
            if not relevant_chunks:
                yield NOT_FOUND
                return

            context_blocks, _ = self._build_context(relevant_chunks)
            context_blocks = self._synthesize_context_blocks(context_blocks)
            if len(context_blocks) > 1:
                context_blocks = self._group_context_by_similarity(context_blocks)
            prompt = PromptEngineer.build_prompt(question, context_blocks, conversation_history)

            async for token in self.ollama.stream_generate(prompt, model=model):
                if token:
                    # Strip any HTML/XML tags that may have been generated by the LLM
                    cleaned_token = re.sub(r"<[^>]+>", "", token)
                    if cleaned_token:
                        yield cleaned_token

        except Exception as e:
            logger.exception(f"Streaming failed: {str(e)}")
            yield "An error occurred while streaming the response."

    def _needs_context_expansion(
        self,
        question: str,
    ) -> bool:

        return False

    def _extract_context_terms(self, conversation_history: list[dict] | None, current_question: str = "") -> set[str]:
        if not conversation_history:
            return set()
        terms: set[str] = set()
        user_questions = [
            turn["content"] for turn in conversation_history
            if turn.get("role") == "user" and (turn.get("content") or "").strip()
        ][-2:]
        for prior_question in user_questions:
            terms.update(self._terms(prior_question))
        return terms - self._terms(current_question)

    def _chunk_fingerprint(self, text: str) -> str:
        words = re.findall(r"[a-zA-Z0-9_]+", text.lower())
        content_words = list(dict.fromkeys(w for w in words if len(w) > 3))[:40]
        return " ".join(content_words) if content_words else text[:100].strip().lower()

    def _compute_retrieval_confidence(self, relevant_chunks: list[dict]) -> float:
        if not relevant_chunks:
            return 0.0
        scores = [float(row.get("final_score", 0.0)) for row in relevant_chunks]
        weights = [1.0 / (i + 1) for i in range(len(scores))]
        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        weight_sum = sum(weights)
        return weighted_sum / weight_sum if weight_sum > 0 else 0.0

    def _select_best_chunks_mmr(
        self, ranked_results: list[dict], question: str | None = None,
    ) -> list[dict]:
        """
        Select chunks using MMR with deduplication.
        """
        if not ranked_results:
            return []

        max_chunks = self._max_context_chunks(question or "")

        selected = []
        candidate_pool = list(ranked_results)
        seen_fingerprints = set()
        similarity_cache = {}

        def _mmr_similarity(chunk_a_text: str, chunk_b_text: str) -> float:
            key = (chunk_a_text[:200], chunk_b_text[:200])
            if key in similarity_cache:
                return similarity_cache[key]
            words_a = set(chunk_a_text.lower().split())
            words_b = set(chunk_b_text.lower().split())
            if not words_a or not words_b:
                sim = 0.0
            else:
                sim = (2.0 * len(words_a.intersection(words_b))) / (len(words_a) + len(words_b))
            similarity_cache[key] = sim
            return sim

        def _mmr_score(chunk: dict, selected: list[dict], lambda_param: float = MMR_LAMBDA) -> float:
            rel = float(chunk.get("final_score", 0.0))
            if not selected:
                return rel
            max_sim = 0.0
            chunk_text = chunk.get("text", "")
            for sel in selected:
                sel_text = sel.get("text", "")
                sim = _mmr_similarity(chunk_text, sel_text)
                max_sim = max(max_sim, sim)
            return lambda_param * rel - (1.0 - lambda_param) * max_sim

        # Deduplicate by fingerprint
        deduped_pool = []
        for row in candidate_pool:
            text = row.get("text", "").strip()
            fingerprint = self._chunk_fingerprint(text)
            if fingerprint in seen_fingerprints:
                continue
            seen_fingerprints.add(fingerprint)
            deduped_pool.append(row)

        # MMR selection
        while len(selected) < max_chunks and deduped_pool:
            scored_candidates = [
                (idx, _mmr_score(chunk, selected))
                for idx, chunk in enumerate(deduped_pool)
            ]
            scored_candidates.sort(key=lambda x: x[1], reverse=True)
            best_idx, best_mmr_score = scored_candidates[0]

            if best_mmr_score < MIN_CHUNK_SCORE:
                break

            best_chunk = deduped_pool.pop(best_idx)
            selected.append(best_chunk)

        return selected

    def _max_context_chunks(self, question: str) -> int:
        word_count = len(question.split())

        # FIXED: Increased from 4 to 6 so brief concept questions 
        # get enough surrounding chunks (like definitions + code + applications).
        if word_count <= 5:
            return 6
        elif word_count <= 15:
            return 7

        return 8

    def _minimum_answer_words(self, question: str) -> int:
        """Dynamically evaluates ideal content length thresholds based on question structural complexity."""
        question_clean = (question or "").lower().strip()
        
        # Pattern-based matching: Detects intent dynamically without running word-length counts
        procedural_intent = re.search(r'\b(type|procedure|step|differ|versus|vs|explain|describe|code|program)\b', question_clean)
        
        if procedural_intent:
            # Demands detailed space for complex data structures or algorithms (approx 15-20 lines)
            return 120

        # Standard definition baseline (approx 6-10 lines)
        return 60

    def _build_context(self, rows: list[dict]) -> tuple[list[str], list[dict]]:
        context_blocks = []
        sources = []
        seen_sources = set()
        seen_bigrams_list = []

        for row in rows:
            text = row.get("text", "")
            text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\b(?:Chapter|Section|Part)\s+\d+(?:\.\d+)*\b", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s+", " ", text).strip()

            if len(text.split()) < 3:
                continue

            words = text.lower().split()
            if len(words) < 6:
                continue

            bigrams = set(zip(words, words[1:]))
            is_redundant = False
            if bigrams:
                for seen_bigrams in seen_bigrams_list:
                    overlap = len(bigrams.intersection(seen_bigrams))
                    if bigrams and (overlap / len(bigrams)) > 0.85:
                        is_redundant = True
                        break
            if is_redundant:
                continue

            seen_bigrams_list.append(bigrams)
            context_blocks.append(text)

            metadata = row.get("metadata", {}) or {}
            filename = metadata.get("filename") or metadata.get("file") or "Unknown Document"
            page = metadata.get("page", "-")

            source_key = (filename, page)
            if source_key not in seen_sources:
                sources.append({
                    "file": filename,
                    "page": str(page),
                    "confidence": round(row.get("final_score", row.get("confidence", 0.0)), 3),
                })
                seen_sources.add(source_key)

        return context_blocks, sources

    def _generate_fallback_answer(self, question: str, rows: list[dict]) -> str:
        if not rows:
            return NOT_FOUND
        meaningful_sentences = []
        for row in rows:
            text = row.get("text", "").strip()
            if not text:
                continue
            sentences = re.split(r'(?<=[.!?])\s+', text)
            for sentence in sentences:
                sentence = sentence.strip()
                if len(sentence) > 30 and len(sentence.split()) > 5:
                    meaningful_sentences.append(sentence)
                if len(meaningful_sentences) >= 4:
                    break
            if len(meaningful_sentences) >= 4:
                break
        if meaningful_sentences:
            return " ".join(meaningful_sentences[:4])
        return NOT_FOUND

    def _looks_like_raw_chunk(self, text: str) -> bool:
        if not text:
            return True
        sentences = len(re.split(r'[.!?]+', text))
        return sentences < 2 and len(text.split()) > 20

    def _is_retrieval_relevant(
        self, question: str, ranked_results: list[dict],
        conversation_history: list[dict] | None = None,
    ) -> bool:
        if not ranked_results:
            return False

        top_confidence = float(ranked_results[0].get("confidence", 0.0))
        top_score = float(ranked_results[0].get("final_score", 0.0))

        # FIXED: Lowered constraints slightly to prevent the pipeline from 
        # prematurely throwing away slightly lower-scoring technical text blocks.
        return (
            top_score >= 0.20
            and top_confidence >= 0.28
        )

    def _terms(self, text: str) -> set[str]:
        """Extract meaningful terms, filtering stop words."""
        if not text:
            return set()
        clean_string = re.sub(r"[^\w\s]", " ", text.lower())
        words = clean_string.split()
        return {
            w
            for w in words
            if w not in ENGLISH_STOP_WORDS
            and len(w) > 1
        }

    def _is_not_found_response(self, answer: str) -> bool:
        if not answer:
            return True
        normalized = answer.strip().lower()
        not_found_phrases = [
            "the requested information was not found in the uploaded documents",
            "i'm sorry, but i couldn't find the information you're looking for in the uploaded documents",
            "i couldn't find the information you're looking for",
            "the information was not found",
            "information was not found",
        ]
        return (
            normalized in not_found_phrases
            or any(normalized.startswith(phrase[:30]) for phrase in not_found_phrases)
        )

    def _filter_sources_by_answer_usage(
        self, answer: str, relevant_chunks: list[dict],
        sources: list[dict], question: str = "",
    ) -> list[dict]:
        if not answer or not relevant_chunks or self._is_not_found_response(answer):
            return []

        answer_terms = self._terms(answer)
        query_terms = self._terms(question)
        scored_sources = []
        seen = set()

        for chunk in relevant_chunks:
            metadata = chunk.get("metadata", {}) or {}
            file = metadata.get("filename") or metadata.get("file") or "Unknown"
            page = str(metadata.get("page", "-"))
            key = (file, page)
            if key in seen:
                continue
            chunk_text = chunk.get("text", "").lower()
            chunk_terms = self._terms(chunk_text)
            
            # Ensure the chunk directly contributed to the answer
            answer_overlap = len(answer_terms.intersection(chunk_terms))
            required_overlap = max(1, int(len(answer_terms) * 0.01))

            if answer_overlap == 0:
                continue

            if query_terms and len(query_terms.intersection(chunk_terms)) == 0:
                continue

            query_overlap = len(query_terms.intersection(chunk_terms))
            final_relevance_score = (
                query_overlap * 5.0 + answer_overlap * 4.0 +
                float(chunk.get("final_score", 0.0)) * 3.0
            )
            scored_sources.append({"file": file, "page": page, "weight": final_relevance_score})
            seen.add(key)

        scored_sources.sort(key=lambda s: s["weight"], reverse=True)
        filtered = []
        for s in scored_sources:
            orig_match = next(
                (
                    c for c in relevant_chunks
                    if (
                        str(c.get("metadata", {}).get("page", "-")) == s["page"]
                        and
                        (c.get("metadata", {}).get("filename") or c.get("metadata", {}).get("file") or "Unknown Document") == s["file"]
                    )
                ),
                {},
            )
            confidence_val = orig_match.get("final_score", orig_match.get("confidence", 0.75))
            if float(confidence_val) >= 0.35:
                filtered.append({"file": s["file"], "page": s["page"], "confidence": round(float(confidence_val), 3)})
        return filtered[:3]