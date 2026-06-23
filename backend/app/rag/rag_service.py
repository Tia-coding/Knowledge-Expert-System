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

            requested_top_k = top_k or self.settings.rag_top_k
            query_intent = self._detect_query_intent(question)

            # Generate primary and fallback queries
            retrieval_queries = self._generate_retrieval_queries(question, conversation_history)
            primary_query = retrieval_queries[0] if retrieval_queries else question

            # Primary vector search
            search_results = self.vector_store.search(primary_query, requested_top_k * 3)

            # Keyword fallback if primary insufficient
            if not search_results or len(search_results) < 3:
                keyword_query = self._extract_keywords(question)
                if keyword_query and keyword_query != primary_query:
                    search_results = self.vector_store.search(keyword_query, requested_top_k * 3)

            if not search_results:
                return {"answer": NOT_FOUND, "sources": [], "confidence": 0.0}

            # Rank results with term-aware scoring
            ranked_results = self._rank_results(question, search_results, conversation_history)

            # Select diverse chunks
            relevant_chunks = self._select_best_chunks_mmr(ranked_results, question)
            if not relevant_chunks:
                return {"answer": NOT_FOUND, "sources": [], "confidence": 0.0}

            # Build context with source-tagged blocks
            context_blocks, sources = self._build_context(relevant_chunks)
            if not context_blocks:
                return {"answer": NOT_FOUND, "sources": [], "confidence": 0.0}

            context_blocks = self._synthesize_context_blocks(context_blocks)
            if len(context_blocks) > 1:
                context_blocks = self._group_context_by_similarity(context_blocks)

            # Compute real retrieval confidence from chunk scores
            retrieval_confidence = self._compute_retrieval_confidence(relevant_chunks)

            # Build prompt with intent and source-attribution-friendly instructions
            prompt = PromptEngineer.build_prompt(
                question, context_blocks, conversation_history,
                query_intent=query_intent
            )

            # Generate answer
            answer = await self._generate_answer(
                prompt, question, relevant_chunks, model, query_intent=query_intent
            )

            # Post-process
            answer = self._post_process_answer(answer, question)

            # Verify answer uses chunk content
            answer_terms = self._terms(answer)
            chunk_terms = set()
            for chunk in relevant_chunks:
                chunk_terms.update(self._terms(chunk.get("text", "")))

            supported_ratio = (
                len(answer_terms.intersection(chunk_terms)) / max(len(answer_terms), 1)
            )

            if supported_ratio < 0.05 and not self._is_not_found_response(answer) and len(answer_terms) > 5:
                return {"answer": NOT_FOUND, "sources": [], "confidence": 0.0}

            # Filter sources: ONLY return sources whose chunks were actually used in the answer
            sources = self._filter_sources_by_answer_usage(answer, relevant_chunks, sources, question)
            if self._is_not_found_response(answer):
                sources = []

            # Calibrate confidence using REAL retrieval confidence, not hardcoded
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

    def _detect_query_intent(self, question: str) -> str:
        if not question:
            return "general"
        q = question.lower().strip()
        if re.search(r'\b(compare|difference|versus|vs\.?|differen|similarit|contrast)\b', q):
            return "comparison"
        if re.search(r'\b(how\s+(to|do|can|would|should)|steps?|procedure|process|method|way\s+to|technique|guide|tutorial)\b', q):
            return "procedural"
        if re.search(r'\b(what\s+(is|are|was|were|defined?|mean|definition)|define|explain\s+what)\b', q):
            return "definition"
        if re.search(r'\b(list|enumerate|types?\s+of|kinds?\s+of|categories?\s+of|examples?\s+of|what\s+are\s+(the\s+)?(different|various|main|key|major|primary))\b', q):
            return "list"
        if re.search(r'\b(when|where|who|which|why|how\s+(many|much|long|often|far|big|large|small))\b', q):
            return "factual"
        return "general"

    def _generate_retrieval_queries(self, question: str, conversation_history: list[dict] | None = None) -> list[str]:
        queries = []
        base_query = re.sub(r'[?]+\s*$', '', question).strip()
        queries.append(base_query)
        keyword_query = self._extract_keywords(question)
        if keyword_query and len(keyword_query) > 3 and keyword_query.lower() != base_query.lower():
            queries.append(keyword_query)
        return queries

    def _extract_keywords(self, question: str) -> str:
        question_terms = self._terms(question)
        return " ".join(sorted(question_terms)) if question_terms else question

    def _rank_results(self, question: str, results: list[dict], conversation_history: list[dict] | None = None) -> list[dict]:
        if not results:
            return []

        question_terms = self._terms(question)
        ranked = []

        for row in results:
            text = row.get("text", "")
            text_lower = text.lower()
            text_terms = self._terms(text)
            semantic_score = float(row.get("confidence", 0.0))

            exact_matches = len(question_terms.intersection(text_terms))
            coverage = exact_matches / max(len(question_terms), 1) if question_terms else 0

            # Phrase match boost (higher weight for exact multi-word matches)
            phrase_boost = 0.0
            if len(question_terms) >= 2:
                question_words = re.findall(r'\b[a-zA-Z]{3,}\b', question.lower())
                for window_size in [4, 3, 2]:
                    for i in range(len(question_words) - window_size + 1):
                        phrase = ' '.join(question_words[i:i+window_size])
                        if phrase in text_lower:
                            phrase_boost = max(phrase_boost, 0.15)
                            break
                    if phrase_boost > 0:
                        break

            # Term overlap gets highest weight for technical accuracy
            final_score = (
                semantic_score * 0.25 +        # semantic similarity
                coverage * 0.40 +               # term coverage (highest weight for accuracy)
                min(exact_matches / 2, 1.0) * 0.20 +  # exact term matches
                phrase_boost                    # phrase matches
            )

            ranked.append({
                **row,
                "final_score": round(min(final_score, 1.0), 4),
            })

        return sorted(ranked, key=lambda item: item["final_score"], reverse=True)

    def _group_context_by_similarity(self, context_blocks: list[str]) -> list[str]:
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
                if smaller > 0 and overlap / smaller > 0.90:
                    is_duplicate = True
                    break
            if not is_duplicate:
                seen_fingerprints.add(frozenset(significant_words))
                synthesized.append(block)
        return synthesized if synthesized else context_blocks

    async def _generate_answer(self, prompt: str, question: str, relevant_chunks: list[dict], model: str | None = None, query_intent: str | None = None) -> str:
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
            or self._is_not_found_response(answer)
        )

        if needs_retry:
            retry_prompt = (
                prompt + "\n\n"
                "IMPORTANT: The document context above has the information needed to answer the user's question. "
                "Your previous response was insufficient. Please try again.\n\n"
                "Be THOROUGH. Use ALL relevant information from the context. "
                "If the context contains characteristics, examples, types, or applications related to the question, include them. "
                "Structure the answer appropriately for the question type:\n"
                "- For comparisons: highlight differences and similarities clearly.\n"
                "- For types/categories: list each one with its description.\n"
                "- For definitions: explain the concept fully with all available details.\n"
                "- For procedures: list steps in order.\n"
                "Do NOT add information that is not in the context. "
                "Do NOT use introductory phrases like 'Based on the documents...'."
            )
            try:
                retry_answer = (await self.ollama.generate(prompt=retry_prompt, model=model)).strip()
                if retry_answer and len(retry_answer.split()) >= min_words * 0.5:
                    if not self._looks_like_raw_chunk(retry_answer):
                        answer = retry_answer
            except Exception:
                pass

        if not answer:
            answer = NOT_FOUND
        return answer

    def _get_intent_instruction(self, intent: str) -> str:
        instructions = {
            "definition": (
                "Structure your answer as follows:\n"
                "- **Definition:** Start with a clear definition of the term.\n"
                "- **Key Characteristics:** List features using bullet points.\n"
                "- **Types/Categories:** Include classifications if present.\n"
                "- **Examples:** Provide examples if available."
            ),
            "comparison": (
                "Structure your answer as follows:\n"
                "- **Overview:** Brief introduction to what is being compared.\n"
                "- **Key Differences:** List differences with bullet points.\n"
                "- **Key Similarities:** List similarities with bullet points."
            ),
            "procedural": (
                "Structure your answer as follows:\n"
                "- **Overview:** Brief description of the process.\n"
                "- **Steps:** Numbered list (1., 2., 3., etc.).\n"
                "- **Requirements:** Prerequisites if mentioned."
            ),
            "list": (
                "Structure your answer as follows:\n"
                "- **Overview:** Brief introduction.\n"
                "- Each item: **Item Name:** Description with bullet points."
            ),
            "factual": (
                "Structure your answer as follows:\n"
                "- Start with the direct answer.\n"
                "- **Details:** Supporting information with bullet points.\n"
                "- Include specific numbers, dates, or specifications."
            ),
            "general": (
                "Structure your answer as follows:\n"
                "- Start with a direct answer.\n"
                "- Use **bold section headers** for each logical part.\n"
                "- Use bullet points for key information."
            ),
        }
        return instructions.get(intent, instructions["general"])

    def _post_process_answer(self, answer: str, question: str) -> str:
        if not answer:
            return answer
        answer = re.sub(r"<[^>]+>", "", answer)
        answer = PromptEngineer.clean_response(answer, question)
        answer = self._clean_natural_answer(answer)
        answer = self._fix_sentence_capitalization(answer)
        answer = self._fix_ocr_artifacts(answer)
        answer = PromptEngineer.polish_answer(answer)
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
        question_clean = (question or "").strip().lower()
        answer_clean = (answer or "").strip().lower()
        if question_clean and answer_clean.startswith(question_clean):
            answer = answer[len(question):].strip()
        return answer.strip()

    def _clean_natural_answer(self, answer: str) -> str:
        if not answer:
            return answer
        text = answer.strip()
        first_line = text.split('\n')[0].strip()
        filler_patterns = [
            r"(?i)^based on (the )?(uploaded |provided )?documents?[^.!]*[.!]?\s*$",
            r"(?i)^according to (the )?(uploaded |provided )?(notes|pdfs|materials|documents|text|context)[^.!]*[.!]?\s*$",
            r"(?i)^here is (the )?(direct )?(answer|response):?\s*$",
            r"(?i)^the (direct )?(answer|response) is:?\s*$",
            r"(?i)^sure,? here is[^:]*:?\s*$",
        ]
        for pattern in filler_patterns:
            if re.match(pattern, first_line):
                text = '\n'.join(text.split('\n')[1:]).strip()
                break
        return text.strip()

    def _fix_sentence_capitalization(self, text: str) -> str:
        if not text:
            return text
        text = text.strip()
        if text and text[0].islower() and not text.startswith(('*', '-', '1.', '2.', '3.', '4.', '5.', '6.', '7.', '8.', '9.', '0.', '#', '|', '>')):
            text = text[0].upper() + text[1:]
        return text

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
            r'\bde\s+scribe\b': 'describe',
            r'\bim\s+portant\b': 'important',
            r'\bper\s+form\b': 'perform',
            r'\bper\s+formance\b': 'performance',
            r'\bim\s+plement\b': 'implement',
            r'\bim\s+plementation\b': 'implementation',
            r'\bcom\s+ponent\b': 'component',
            r'\bcom\s+ponents\b': 'components',
            r'\bpro\s+cess\b': 'process',
            r'\bpro\s+cessing\b': 'processing',
            r'\bcon\s+cept\b': 'concept',
            r'\bcon\s+cepts\b': 'concepts',
            r'\bappli\s+cation\b': 'application',
            r'\bappli\s+cations\b': 'applications',
            r'\bfunc\s+tion\b': 'function',
            r'\bfunc\s+tions\b': 'functions',
        }
        for pattern, replacement in ocr_fixes.items():
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        text = re.sub(r'(\w)-\n(\w)', r'\1\2', text)
        text = re.sub(r'\s+([,;:!?])', r'\1', text)
        text = re.sub(r' {2,}', ' ', text)
        return text.strip()

    def _compute_retrieval_confidence(self, relevant_chunks: list[dict]) -> float:
        """Compute weighted confidence from chunk final_scores, with position weighting."""
        if not relevant_chunks:
            return 0.0
        scores = [float(row.get("final_score", row.get("confidence", 0.0))) for row in relevant_chunks]
        # Position-weighted: first chunk matters most
        weights = [1.0 / (i + 1) for i in range(len(scores))]
        weighted_sum = sum(s * w for s, w in zip(scores, weights))
        weight_sum = sum(weights)
        return weighted_sum / weight_sum if weight_sum > 0 else 0.0

    def _calibrate_confidence(self, retrieval_confidence: float, answer: str, relevant_chunks: list[dict], question: str) -> float:
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
            hallucination_penalty = max(0.0, 1.0 - max(0, unseen_ratio - 0.40) * 1.5)

        calibrated = (
            retrieval_confidence * 0.50 +
            length_factor * 0.15 +
            coverage_factor * 0.25 +
            hallucination_penalty * 0.10
        )
        return max(0.0, min(calibrated, 1.0))

    def _select_best_chunks_mmr(self, ranked_results: list[dict], question: str | None = None) -> list[dict]:
        if not ranked_results:
            return []
        max_chunks = self._max_context_chunks(question or "")
        ranked_results.sort(key=lambda x: float(x.get("final_score", 0.0)), reverse=True)
        selected = []
        seen_fingerprints = set()
        for row in ranked_results:
            if len(selected) >= max_chunks:
                break
            text = row.get("text", "").strip()
            fingerprint = self._chunk_fingerprint(text)
            if fingerprint not in seen_fingerprints:
                seen_fingerprints.add(fingerprint)
                selected.append(row)
        return selected

    def _max_context_chunks(self, question: str) -> int:
        word_count = len(question.split())
        if word_count <= 5:
            return 6
        elif word_count <= 15:
            return 7
        return 8

    def _minimum_answer_words(self, question: str) -> int:
        question_clean = (question or "").lower().strip()
        procedural_intent = re.search(r'\b(type|procedure|step|differ|versus|vs|explain|describe|code|program)\b', question_clean)
        return 80 if procedural_intent else 40

    def _build_context(self, rows: list[dict]) -> tuple[list[str], list[dict]]:
        """Build context blocks with source metadata. Each block is tagged with [Source: filename, Page X]."""
        context_blocks = []
        sources_map = {}  # filename -> page -> { chunk_index, text, score }
        source_order = []  # Track order of unique sources

        for row in rows:
            text = row.get("text", "")
            text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()

            if len(text.split()) < 5:
                continue

            metadata = row.get("metadata", {}) or {}
            filename = metadata.get("filename") or metadata.get("file") or "Unknown Document"
            page = metadata.get("page", "-")
            chunk_id = metadata.get("chunk_id", "")
            score = float(row.get("final_score", row.get("confidence", 0.0)))

            # Tag the context block with source information
            source_tag = f"[Source: {filename}, Page {page}]"
            tagged_text = f"{source_tag}\n{text}"
            context_blocks.append(tagged_text)

            # Track unique sources with their content evidence
            source_key = (filename, page)
            if source_key not in sources_map:
                sources_map[source_key] = {
                    "file": filename,
                    "page": str(page),
                    "confidence": round(score, 3),
                    "texts": [text],
                    "chunk_count": 0
                }
                source_order.append(source_key)
            else:
                # Update confidence to highest
                if score > sources_map[source_key]["confidence"]:
                    sources_map[source_key]["confidence"] = round(score, 3)
                sources_map[source_key]["texts"].append(text)
            sources_map[source_key]["chunk_count"] += 1

        # Build sources list preserving order
        sources = []
        for key in source_order:
            info = sources_map[key]
            sources.append({
                "file": info["file"],
                "page": info["page"],
                "confidence": info["confidence"],
                "chunk_count": info["chunk_count"],
            })

        return context_blocks, sources

    def _filter_sources_by_answer_usage(
        self, answer: str, relevant_chunks: list[dict],
        sources: list[dict], question: str = ""
    ) -> list[dict]:
        """
        Only return sources whose content was actually USED in the answer.
        A source is "used" if at least 2 answer terms overlap with the chunk text.
        """
        if not answer or not sources:
            return sources or []

        answer_terms = self._terms(answer)
        if not answer_terms or len(answer_terms) < 3:
            return []  # Not enough to verify

        # Build map of source_key -> chunk_texts
        source_texts = {}
        for chunk in relevant_chunks:
            metadata = chunk.get("metadata", {}) or {}
            filename = metadata.get("filename") or metadata.get("file") or "Unknown"
            page = str(metadata.get("page", "-"))
            key = (filename, page)
            if key not in source_texts:
                source_texts[key] = []
            source_texts[key].append(chunk.get("text", ""))

        filtered = []
        for source in sources:
            filename = source.get("file", "")
            page = source.get("page", "-")
            key = (filename, str(page))
            chunk_texts = source_texts.get(key, [])

            # Check if any chunk text has meaningful overlap with answer
            is_used = False
            for chunk_text in chunk_texts:
                chunk_terms = self._terms(chunk_text)
                if not chunk_terms:
                    continue
                overlap = len(answer_terms.intersection(chunk_terms))
                # Source is used if at least 3 terms overlap or 20% of answer terms match
                if overlap >= 3 or (len(answer_terms) > 0 and overlap / len(answer_terms) >= 0.15):
                    is_used = True
                    break

            if is_used:
                filtered.append(source)

        # If no sources pass filtering (narrow answer), return top sources anyway
        return filtered[:8] if filtered else sources[:8]

    def _looks_like_raw_chunk(self, text: str) -> bool:
        if not text:
            return True
        sentences = len(re.split(r'[.!?]+', text))
        return sentences < 2 and len(text.split()) > 20

    def _terms(self, text: str) -> set[str]:
        if not text:
            return set()
        clean_string = re.sub(r"[^\w\s]", " ", text.lower())
        words = clean_string.split()
        return {w for w in words if w not in ENGLISH_STOP_WORDS and len(w) > 1}

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
            "i cannot find",
            "i couldn't find",
            "does not contain",
            "doesn't contain",
            "no information",
        ]
        return (
            normalized in not_found_phrases
            or any(normalized.startswith(phrase[:30]) for phrase in not_found_phrases)
        )

    def _chunk_fingerprint(self, text: str) -> str:
        words = re.findall(r"[a-zA-Z0-9_]+", text.lower())
        content_words = list(dict.fromkeys(w for w in words if len(w) > 3))[:40]
        return " ".join(content_words) if content_words else text[:100].strip().lower()

    async def stream_answer(self, question: str, conversation_history: list[dict] | None = None, model: str | None = None, top_k: int | None = None) -> AsyncGenerator[str, None]:
        try:
            question = (question or "").strip()
            if not question:
                yield "Please enter a valid question."
                return
            requested_top_k = top_k or self.settings.rag_top_k
            retrieval_queries = self._generate_retrieval_queries(question, conversation_history)
            primary_query = retrieval_queries[0] if retrieval_queries else question
            search_results = self.vector_store.search(primary_query, requested_top_k * 3)
            if not search_results:
                yield NOT_FOUND
                return
            ranked_results = self._rank_results(question, search_results, conversation_history)
            relevant_chunks = self._select_best_chunks_mmr(ranked_results, question)
            if not relevant_chunks:
                yield NOT_FOUND
                return
            context_blocks, _ = self._build_context(relevant_chunks)
            context_blocks = self._synthesize_context_blocks(context_blocks)
            if len(context_blocks) > 1:
                context_blocks = self._group_context_by_similarity(context_blocks)
            query_intent = self._detect_query_intent(question)
            prompt = PromptEngineer.build_prompt(question, context_blocks, conversation_history, query_intent=query_intent)
            async for token in self.ollama.stream_generate(prompt, model=model):
                if token:
                    cleaned_token = re.sub(r"<[^>]+>", "", token)
                    if cleaned_token:
                        yield cleaned_token
        except Exception as e:
            logger.exception(f"Streaming failed: {str(e)}")
            yield "An error occurred while streaming the response."