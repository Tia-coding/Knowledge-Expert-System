import logging
import re
from collections import defaultdict
from typing import AsyncGenerator

from sqlalchemy.orm import Session

from app.config.settings import get_settings
from app.models.models import User
from app.rag.ollama_client import OllamaClient
from app.rag.prompt_engineering import PromptEngineer
from app.rag.vector_store import get_vector_store
from app.rag.coherence_analyzer import CoherenceAnalyzer

logger = logging.getLogger(__name__)

NOT_FOUND = (
    "I couldn't find information about that in your "
    "uploaded documents. Please ask about a topic that "
    "appears in the documents available to this assistant."
)

# Minimum retrieval quality before the LLM is invoked
MIN_CHUNK_SCORE = 0.34
MIN_TOP_RELEVANCE_SCORE = 0.40
MIN_TERM_OVERLAP_RATIO = 0.18


class RAGService:

    def __init__(self) -> None:

        self.settings = get_settings()

        self.vector_store = (
            get_vector_store()
        )

        self.ollama = OllamaClient()

    # =========================================================
    # MAIN ANSWER METHOD
    # =========================================================

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

            question = (
                question or ""
            ).strip()

            if not question:

                return {
                    "answer":
                    "Please enter a valid question.",
                    "sources": [],
                    "confidence": 0.0,
                }

            requested_top_k = (
                top_k
                or max(
                    self.settings.rag_top_k,
                    10,
                )
            )

            # Retrieval uses an expanded query for vague follow-ups;
            # the LLM receives the current question plus structured history.
            retrieval_query = self._build_retrieval_query(
                question,
                conversation_history,
            )
            context_terms = self._extract_context_terms(
                conversation_history,
            )

            search_results = (
                self.vector_store.search(
                    retrieval_query,
                    requested_top_k,
                )
            )

            if not search_results:

                return {
                    "answer": NOT_FOUND,
                    "sources": [],
                    "confidence": 0.0,
                }

            # =====================================================
            # RERANK RESULTS
            # =====================================================

            ranked_results = (
                self._rank_results(
                    retrieval_query,
                    search_results,
                    context_terms=context_terms,
                )
            )

            if not self._is_retrieval_relevant(
                retrieval_query,
                ranked_results,
            ):
                return {
                    "answer": NOT_FOUND,
                    "sources": [],
                    "confidence": 0.0,
                }

            # =====================================================
            # FILTER RESULTS
            # =====================================================

            relevant_chunks = (
                self._select_best_chunks(
                    ranked_results
                )
            )

            if not relevant_chunks:

                return {
                    "answer": NOT_FOUND,
                    "sources": [],
                    "confidence": 0.0,
                }

             # =====================================================
             # BUILD CONTEXT
             # =====================================================

            context_blocks, sources = (
                self._build_context(
                    relevant_chunks
                )
            )

            # =====================================================
            # BUILD PROMPT
            # =====================================================

            prompt = (
                PromptEngineer.build_prompt(
                    question,
                    context_blocks,
                    conversation_history,
                )
            )

            # =====================================================
            # GENERATE ANSWER
            # =====================================================

            answer = ""

            try:

                answer = (
                    await self.ollama.generate(
                        prompt=prompt,
                        model=model,
                    )
                ).strip()

            except Exception as e:

                logger.exception(
                    f"LLM generation failed: {str(e)}"
                )

            # =====================================================
            # FALLBACK RETRY
            # =====================================================

            if (
                not answer
                or len(answer.split()) < 12
                or self._looks_like_raw_chunk(
                    answer
                )
            ):

                retry_prompt = (
                    prompt
                    + "\n\n"
                    + PromptEngineer.direct_answer_reminder()
                )

                try:

                    retry_answer = (
                        await self.ollama.generate(
                            prompt=retry_prompt,
                            model=model,
                        )
                    ).strip()

                    if (
                        retry_answer
                        and len(
                            retry_answer.split()
                        )
                        >= 12
                    ):

                        answer = retry_answer

                except Exception as e:

                    logger.exception(
                        f"Retry generation failed: {str(e)}"
                    )

            # =====================================================
            # FALLBACK GENERATION
            # =====================================================

            if (
                not answer
                or self._is_not_found_response(
                    answer
                )
            ):

                answer = (
                    self._generate_fallback_answer(
                        question,
                        relevant_chunks,
                    )
                )

            # =====================================================
            # CLEAN RESPONSE
            # =====================================================

            answer = (
                PromptEngineer.clean_response(
                    answer
                )
            )

            answer = self._enhance_answer_coherence(
                answer
            )

            # Keep only sources whose content informed the final answer.
            sources = self._filter_sources_by_answer_usage(
                answer,
                relevant_chunks,
                sources,
            )

            if not self._answer_matches_question(
                question,
                answer,
                conversation_history,
            ):
                return {
                    "answer": NOT_FOUND,
                    "sources": [],
                    "confidence": 0.0,
                }

            # =====================================================
            # FINAL VALIDATION
            # =====================================================

            if (
                not answer
                or len(answer.strip()) < 20
                or self._is_not_found_response(answer)
            ):

                return {
                    "answer": NOT_FOUND,
                    "sources": [],
                    "confidence": 0.0,
                }

            # =====================================================
            # CALCULATE CONFIDENCE
            # =====================================================

            confidence = round(

                sum(
                    row["final_score"]
                    for row in relevant_chunks
                )
                / len(relevant_chunks),

                3,

            )

            confidence = max(
                0.10,
                min(confidence, 0.99)
            )

            return {

                "answer": answer,

                "sources": sources,

                "confidence": confidence,

            }

        except Exception as e:

            logger.exception(
                f"RAG pipeline failed: {str(e)}"
            )

            return {

                "answer":
                "An error occurred while "
                "processing your request.",

                "sources": [],

                "confidence": 0.0,

            }

    # =========================================================
    # STREAMING ANSWER
    # =========================================================

    async def stream_answer(
        self,
        question: str,
        conversation_history: list[dict] | None = None,
        model: str | None = None,
        top_k: int | None = None,
    ) -> AsyncGenerator[str, None]:

        try:

            question = (
                question or ""
            ).strip()

            if not question:

                yield (
                    "Please enter a valid question."
                )

                return

            requested_top_k = (
                top_k
                or self.settings.rag_top_k
            )

            retrieval_query = self._build_retrieval_query(
                question,
                conversation_history,
            )
            context_terms = self._extract_context_terms(
                conversation_history,
            )

            search_results = (
                self.vector_store.search(
                    retrieval_query,
                    requested_top_k,
                )
            )

            if not search_results:

                yield NOT_FOUND

                return

            ranked_results = (
                self._rank_results(
                    retrieval_query,
                    search_results,
                    context_terms=context_terms,
                )
            )

            if not self._is_retrieval_relevant(
                retrieval_query,
                ranked_results,
            ):
                yield NOT_FOUND
                return

            relevant_chunks = (
                self._select_best_chunks(
                    ranked_results
                )
            )

            if not relevant_chunks:

                yield NOT_FOUND

                return

            context_blocks, _ = (
                self._build_context(
                    relevant_chunks
                )
            )

            prompt = (
                PromptEngineer.build_prompt(
                    question,
                    context_blocks,
                    conversation_history,
                )
            )

            async for token in (
                self.ollama.stream_generate(
                    prompt,
                    model=model,
                )
            ):

                if token:
                    yield token

        except Exception as e:

            logger.exception(
                f"Streaming failed: {str(e)}"
            )

            yield (
                "An error occurred while "
                "streaming the response."
            )

    # =========================================================
    # CONVERSATION-AWARE RETRIEVAL
    # =========================================================

    def _needs_context_expansion(
        self,
        question: str,
    ) -> bool:
        """Detect vague follow-ups that need prior-turn terms for retrieval."""

        q = question.lower().strip()
        words = q.split()

        reference_words = {
            "them", "their", "they", "it", "its",
            "this", "that", "these", "those",
            "both", "each", "other", "former", "latter",
        }

        has_pronoun = any(
            word.strip("?.,!") in reference_words
            for word in words
        )

        comparison_phrases = (
            "difference between",
            "compare",
            " vs ",
            " versus ",
            "similarities",
            "differences",
            "tell me more",
            "explain more",
            "explain further",
            "what about",
            "how about",
        )

        if has_pronoun or any(
            phrase in q for phrase in comparison_phrases
        ):
            return True

        # Very short utterances in a thread are usually follow-ups.
        return len(words) <= 4

    def _extract_context_terms(
        self,
        conversation_history: list[dict] | None,
    ) -> set[str]:
        """Pull topic terms from recent turns to enrich retrieval queries."""

        if not conversation_history:
            return set()

        terms: set[str] = set()

        user_questions = [
            turn["content"]
            for turn in conversation_history
            if turn.get("role") == "user"
            and (turn.get("content") or "").strip()
        ][-3:]

        for prior_question in user_questions:
            terms.update(self._terms(prior_question))

        assistant_answers = [
            turn["content"]
            for turn in conversation_history
            if turn.get("role") == "assistant"
            and (turn.get("content") or "").strip()
        ][-2:]

        for prior_answer in assistant_answers:
            answer_terms = list(self._terms(prior_answer))
            terms.update(answer_terms[:10])

        return terms

    def _build_retrieval_query(
        self,
        question: str,
        conversation_history: list[dict] | None,
    ) -> str:
        """Build search query: current question, expanded with history when needed."""

        if not conversation_history or not self._needs_context_expansion(
            question
        ):
            return question

        context_terms = self._extract_context_terms(
            conversation_history
        )

        if not context_terms:
            return question

        return (
            f"{question} "
            f"{' '.join(sorted(context_terms))}"
        ).strip()

    def _chunk_fingerprint(
        self,
        text: str,
    ) -> str:
        """Content-based fingerprint for near-duplicate chunk detection."""

        words = re.findall(
            r"[a-zA-Z0-9_]+",
            text.lower(),
        )

        content_words = sorted(
            {
                word
                for word in words
                if len(word) > 3
            }
        )[:40]

        if content_words:
            return " ".join(content_words)

        return text[:250].strip().lower()

    def _filter_sources_by_answer_usage(
        self,
        answer: str,
        relevant_chunks: list[dict],
        sources: list[dict],
    ) -> list[dict]:
        """Return deduplicated sources whose chunks overlap with the final answer."""

        if not answer or not sources:
            return sources

        answer_terms = self._terms(answer)

        if not answer_terms:
            return sources

        used_keys: set[tuple[str, str]] = set()

        for row in relevant_chunks:
            chunk_terms = self._terms(
                row.get("text", "")
            )

            overlap = len(
                answer_terms.intersection(chunk_terms)
            )

            overlap_ratio = overlap / max(
                len(chunk_terms),
                1,
            )

            if overlap >= 2 or overlap_ratio >= 0.12:
                metadata = row.get("metadata", {})
                filename = (
                    metadata.get("filename")
                    or metadata.get("file")
                    or "Unknown Document"
                )
                page = str(metadata.get("page", "-"))
                used_keys.add((filename, page))

        if not used_keys:
            return sources[:1]

        filtered: list[dict] = []
        seen: set[tuple[str, str]] = set()

        for source in sources:
            key = (source["file"], source["page"])
            if key in used_keys and key not in seen:
                filtered.append(source)
                seen.add(key)

        return filtered

    # =========================================================
    # SELECT BEST CHUNKS
    # =========================================================

    def _select_best_chunks(
        self,
        ranked_results: list[dict],
    ) -> list[dict]:

        relevant_chunks = []

        document_usage = defaultdict(
            int
        )

        semantic_fingerprints = set()

        for row in ranked_results:

            text = (
                row.get("text", "")
                .strip()
            )

            metadata = row.get(
                "metadata",
                {}
            )

            filename = (
                metadata.get("filename")
                or metadata.get("file")
                or "Unknown Document"
            )

            # Prevent one document domination
            if (
                document_usage[filename]
                >= 3
            ):
                continue

            if row.get("final_score", 0) < MIN_CHUNK_SCORE:
                continue

            # Reject weak chunks
            if len(text.split()) < 20:
                continue

            # Reject OCR garbage
            if self._is_garbage_text(
                text
            ):
                continue

            # Prevent semantic duplicates (content fingerprint, not prefix-only)
            fingerprint = self._chunk_fingerprint(text)

            if fingerprint in semantic_fingerprints:
                continue

            semantic_fingerprints.add(fingerprint)

            relevant_chunks.append(
                row
            )

            document_usage[
                filename
            ] += 1

            if len(relevant_chunks) >= 8:
                break

        return relevant_chunks

    # =========================================================
    # BUILD CONTEXT
    # =========================================================

    def _build_context(
        self,
        rows: list[dict],
    ) -> tuple[list[str], list[dict]]:

        context_blocks = []

        sources = []

        seen_sources = set()

        # Reorder chunks for coherence
        ordered_rows = (
            CoherenceAnalyzer.order_chunks_for_coherence(
                rows
            )
        )

        for row in ordered_rows:

            metadata = row.get(
                "metadata",
                {}
            )

            filename = (
                metadata.get("filename")
                or metadata.get("file")
                or "Unknown Document"
            )

            page = metadata.get(
                "page",
                "-"
            )

            source_key = (
                filename,
                page,
            )

            if source_key not in seen_sources:

                sources.append(
                    {
                        "file": filename,
                        "page": str(page),
                        "confidence": round(
                            row["final_score"],
                            3,
                        ),
                    }
                )

                seen_sources.add(
                    source_key
                )

            text = (
                row.get("text", "")
                .replace(
                    "[TABLE]",
                    "Table Information:"
                )
                .replace(
                    "[IMAGE_TEXT]",
                    "Image Text:"
                )
                .replace(
                    "[OCR]",
                    ""
                )
            )

            text = re.sub(
                r"\s+",
                " ",
                text,
            ).strip()

            context_blocks.append(
                f"""
DOCUMENT: {filename}
PAGE: {page}

{text}
"""
            )

        return context_blocks, sources

    # =========================================================
    # RERANK RESULTS
    # =========================================================

    def _rank_results(
        self,
        question: str,
        results: list[dict],
        context_terms: set[str] | None = None,
    ) -> list[dict]:

        question_terms = self._terms(question)

        if context_terms:
            question_terms = question_terms.union(
                context_terms
            )

        ranked = []

        for row in results:

            text = row.get(
                "text",
                ""
            )

            text_terms = self._terms(
                text
            )

            semantic_score = float(
                row.get(
                    "confidence",
                    0.0,
                )
            )

            overlap = (

                len(
                    question_terms.intersection(
                        text_terms
                    )
                )

                / max(
                    len(question_terms),
                    1,
                )

            )

            context_overlap = 0.0

            if context_terms:
                context_overlap = (
                    len(
                        context_terms.intersection(
                            text_terms
                        )
                    )
                    / max(len(context_terms), 1)
                )

            definition_bonus = (
                0.10
                if self._looks_like_definition(
                    text
                )
                else 0.0
            )

            exact_phrase_bonus = 0.0

            question_lower = (
                question.lower()
            )

            if (
                question_lower
                in text.lower()
            ):

                exact_phrase_bonus = 0.10

            final_score = min(
                1.0,
                (
                    semantic_score * 0.50
                    + overlap * 0.30
                    + context_overlap * 0.15
                    + definition_bonus
                    + exact_phrase_bonus
                ),
            )

            ranked.append(
                {
                    **row,
                    "final_score": final_score,
                }
            )

        return sorted(
            ranked,
            key=lambda item: item[
                "final_score"
            ],
            reverse=True,
        )

    # =========================================================
    # FALLBACK ANSWER
    # =========================================================

    def _generate_fallback_answer(
        self,
        question: str,
        rows: list[dict],
    ) -> str:

        for row in rows:

            text = row.get(
                "text",
                ""
            )

            sentences = (
                self._extract_sentences(
                    text
                )
            )

            for sentence in sentences:

                cleaned = (
                    self._clean_sentence(
                        sentence
                    )
                )

                if (
                    len(cleaned.split())
                    >= 12
                ):

                    return cleaned

        return NOT_FOUND

    # =========================================================
    # HELPERS
    # =========================================================

    def _extract_sentences(
        self,
        text: str,
    ) -> list[str]:

        text = re.sub(
            r"\s+",
            " ",
            text,
        )

        return re.split(
            r"(?<=[.!?])\s+",
            text,
        )

    def _clean_sentence(
        self,
        sentence: str,
    ) -> str:

        sentence = re.sub(
            r"`+",
            "",
            sentence,
        )

        sentence = re.sub(
            r"\s+",
            " ",
            sentence,
        )

        sentence = re.sub(
            r"[^\x00-\x7F]+",
            " ",
            sentence,
        )

        return sentence.strip()

    def _looks_like_definition(
        self,
        text: str,
    ) -> bool:

        text = text.lower()

        patterns = [

            " is ",

            " refers to ",

            " defined as ",

            " consists of ",

        ]

        return any(
            pattern in text
            for pattern in patterns
        )

    def _looks_like_raw_chunk(
        self,
        text: str,
    ) -> bool:
        """Detect answers that look like unprocessed document excerpts."""

        indicators = (
            "chapter ",
            "figure ",
            "table of contents",
            "see exercise",
            "page ",
            "section ",
        )

        text_lower = text.lower()

        # Multiple structural markers suggest a raw paste, not synthesis.
        marker_count = sum(
            1 for item in indicators if item in text_lower
        )

        return marker_count >= 2

    def _is_garbage_text(
        self,
        text: str,
    ) -> bool:

        if len(text) < 40:
            return True

        weird_ratio = len(

            re.findall(
                r"[^a-zA-Z0-9\s.,!?():;-]",
                text,
            )

        ) / max(len(text), 1)

        return weird_ratio > 0.20

    def _term_overlap_ratio(
        self,
        question: str,
        text: str,
    ) -> float:

        question_terms = self._terms(question)

        if not question_terms:
            return 0.0

        text_terms = self._terms(text)

        matched = len(
            question_terms.intersection(text_terms)
        )

        return matched / len(question_terms)

    def _is_retrieval_relevant(
        self,
        question: str,
        ranked_results: list[dict],
    ) -> bool:

        if not ranked_results:
            return False

        top = ranked_results[0]
        top_score = float(
            top.get("final_score", 0.0)
        )

        if top_score < MIN_TOP_RELEVANCE_SCORE:
            return False

        overlaps = [
            self._term_overlap_ratio(
                question,
                row.get("text", ""),
            )
            for row in ranked_results[:4]
        ]

        max_overlap = max(overlaps) if overlaps else 0.0
        avg_overlap = (
            sum(overlaps) / len(overlaps)
            if overlaps
            else 0.0
        )

        question_terms = self._terms(question)

        if not question_terms:
            return top_score >= 0.52

        if max_overlap >= MIN_TERM_OVERLAP_RATIO:
            return True

        question_lower = question.lower().strip()

        if question_lower in (
            top.get("text", "").lower()
        ):
            return True

        # High embedding score but no lexical overlap → off-topic query
        if max_overlap < 0.10 and avg_overlap < 0.08:
            return False

        if max_overlap < MIN_TERM_OVERLAP_RATIO:
            return top_score >= 0.62

        return True

    def _answer_matches_question(
        self,
        question: str,
        answer: str,
        conversation_history: list[dict] | None = None,
    ) -> bool:

        if not answer or self._is_not_found_response(answer):
            return False

        question_terms = self._terms(question)

        # Follow-ups may omit explicit topic words; include recent context.
        if (
            self._needs_context_expansion(question)
            and conversation_history
        ):
            question_terms = question_terms.union(
                self._extract_context_terms(
                    conversation_history
                )
            )

        if len(question_terms) < 2:
            return True

        answer_lower = answer.lower()
        matched = sum(
            1
            for term in question_terms
            if term in answer_lower
        )

        if matched >= 1:
            return True

        return len(answer.split()) < 40

    def _terms(
        self,
        text: str,
    ) -> set[str]:

        stop_words = {

            "what",
            "is",
            "are",
            "the",
            "a",
            "an",
            "of",
            "to",
            "in",
            "and",
            "or",
            "for",
            "with",
            "on",
            "by",
            "from",
            "as",
            "this",
            "that",
            "explain",
            "define",
            "describe",
            "give",
            "tell",
            "about",

        }

        words = re.findall(
            r"[a-zA-Z0-9_]+",
            text.lower(),
        )

        return {

            word

            for word in words

            if (
                len(word) > 2
                and word not in stop_words
            )

        }

    def _is_not_found_response(
        self,
        answer: str,
    ) -> bool:

        answer_lower = answer.lower()

        indicators = [
            "not found",
            "no relevant information",
            "could not find",
            "not available",
            "couldn't find information",
            "i couldn't find information",
        ]

        return any(
            item in answer_lower
            for item in indicators
        )

    # =========================================================
    # ANSWER COHERENCE ENHANCEMENT
    # =========================================================

    def _enhance_answer_coherence(
        self,
        answer: str,
    ) -> str:
        """
        Enhance answer coherence by improving transitions
        and paragraph structure.
        """
        paragraphs = answer.split("\n\n")

        if len(paragraphs) <= 1:
            return answer

        # Detect major topic shifts and add transitions
        enhanced_paragraphs = []

        for i, para in enumerate(paragraphs):

            if i == 0:
                enhanced_paragraphs.append(para)
                continue

            # Check if paragraph seems disconnected
            prev_para = paragraphs[i - 1]

            is_disconnected = (
                self._detect_paragraph_disconnect(
                    prev_para,
                    para,
                )
            )

            if is_disconnected:

                # Try to add natural transition
                transition = (
                    self._suggest_transition(
                        prev_para,
                        para,
                    )
                )

                if transition:
                    para = f"{transition} {para}"

            enhanced_paragraphs.append(para)

        return "\n\n".join(
            enhanced_paragraphs
        )

    def _detect_paragraph_disconnect(
        self,
        prev_text: str,
        curr_text: str,
    ) -> bool:
        """
        Detect if two paragraphs are disconnected
        semantically.
        """
        prev_words = set(
            re.findall(
                r"\b[a-zA-Z]+\b",
                prev_text.lower(),
            )
        )

        curr_words = set(
            re.findall(
                r"\b[a-zA-Z]+\b",
                curr_text.lower(),
            )
        )

        # Calculate overlap
        overlap = len(
            prev_words.intersection(curr_words)
        )
        total = len(
            prev_words.union(curr_words)
        )

        similarity = (
            overlap / total
            if total > 0
            else 0
        )

        # If too little overlap, likely disconnected
        return similarity < 0.15

    def _suggest_transition(
        self,
        prev_text: str,
        curr_text: str,
    ) -> str | None:
        """
        Suggest a transition phrase between
        two paragraphs.
        """
        curr_lower = curr_text.lower()

        # Check if it's an elaboration
        if any(
            word in curr_lower
            for word in [
                "example",
                "specific",
                "detail",
                "case",
            ]
        ):
            return "To illustrate,"

        # Check if it's a continuation
        if any(
            word in curr_lower
            for word in [
                "also",
                "another",
                "additional",
                "further",
            ]
        ):
            return "Additionally,"

        # Check if it's a conclusion
        if any(
            word in curr_lower
            for word in [
                "result",
                "conclusion",
                "therefore",
                "ultimately",
            ]
        ):
            return "Consequently,"

        # Check if it's a contrast
        if any(
            word in curr_lower
            for word in [
                "however",
                "different",
                "unlike",
                "contrast",
                "rather",
            ]
        ):
            return "However,"

        return None