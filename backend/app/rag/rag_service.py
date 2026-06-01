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
    "I could not find sufficient information about this topic "
    "in the uploaded documents."
)

NOT_FOUND_INSUFFICIENT = (
    "I could not find sufficient information about this topic "
    "in the uploaded documents."
)

# Minimum retrieval quality before the LLM is invoked
MIN_CHUNK_SCORE = 0.34
MIN_TOP_RELEVANCE_SCORE = 0.40
MIN_TERM_OVERLAP_RATIO = 0.18
LOW_CONFIDENCE_THRESHOLD = 0.48
INSUFFICIENT_CONFIDENCE_THRESHOLD = 0.38
MAX_RETRIEVAL_EXPANSION_TERMS = 6


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
            is_follow_up = self._needs_context_expansion(
                question
            )
            context_terms = (
                self._extract_context_terms(
                    conversation_history,
                    question,
                )
                if is_follow_up
                else None
            )
            current_terms = self._terms(question)

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

            ranked_results = (
                self._rank_results(
                    question,
                    search_results,
                    context_terms=context_terms,
                    primary_terms=current_terms,
                )
            )

            ranked_results = (
                self._filter_by_question_focus(
                    question,
                    ranked_results,
                    conversation_history,
                )
            )

            self._log_retrieval_diagnostics(
                question,
                ranked_results[:8],
                label="ranked",
            )

            if not self._is_retrieval_relevant(
                question,
                ranked_results,
                conversation_history,
            ):
                return {
                    "answer": NOT_FOUND,
                    "sources": [],
                    "confidence": 0.0,
                }

            relevant_chunks = (
                self._select_best_chunks(
                    ranked_results,
                    question,
                )
            )

            if not relevant_chunks:

                return {
                    "answer": NOT_FOUND,
                    "sources": [],
                    "confidence": 0.0,
                }

            context_blocks, sources = (
                self._build_context(
                    relevant_chunks
                )
            )

            retrieval_confidence = (
                self._compute_retrieval_confidence(
                    relevant_chunks
                )
            )

            self._log_retrieval_diagnostics(
                question,
                relevant_chunks,
                label="selected",
            )

            if (
                retrieval_confidence
                < INSUFFICIENT_CONFIDENCE_THRESHOLD
            ):
                return {
                    "answer": NOT_FOUND_INSUFFICIENT,
                    "sources": [],
                    "confidence": 0.0,
                }

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
                or self._is_verbatim_copy(
                    answer,
                    relevant_chunks,
                )
            ):

                retry_prompt = (
                    prompt
                    + "\n\n"
                    + PromptEngineer.synthesis_reminder()
                    + "\n"
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

            answer = PromptEngineer.clean_response(
                answer,
                question,
            )

            # Only add paragraph transitions for structured (algorithm/procedure) answers.
            if re.search(
                r"(?im)^(algorithm|steps|comparison table|objective)\s*:",
                answer,
            ):
                answer = self._enhance_answer_coherence(
                    answer
                )

            answer = PromptEngineer.polish_answer(
                answer
            )

            answer = self._remove_unsupported_claims(
                answer,
                relevant_chunks,
            )

            sources = self._filter_sources_by_answer_usage(
                answer,
                relevant_chunks,
                sources,
                question,
            )

            if retrieval_confidence < LOW_CONFIDENCE_THRESHOLD:
                answer = self._apply_low_confidence_notice(
                    answer,
                    retrieval_confidence,
                )

            if not self._answer_matches_question(
                question,
                answer,
                conversation_history,
            ):
                if (
                    conversation_history
                    and self._needs_context_expansion(question)
                    and relevant_chunks
                    and len(answer.split()) >= 20
                    and not self._is_not_found_response(answer)
                ):
                    pass
                else:
                    return {
                        "answer": (
                            NOT_FOUND_INSUFFICIENT
                            if retrieval_confidence
                            < INSUFFICIENT_CONFIDENCE_THRESHOLD
                            else NOT_FOUND
                        ),
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
                retrieval_confidence,
                3,
            )

            confidence = max(
                0.10,
                min(confidence, 0.99),
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
            is_follow_up = self._needs_context_expansion(
                question
            )
            context_terms = (
                self._extract_context_terms(
                    conversation_history,
                    question,
                )
                if is_follow_up
                else None
            )
            current_terms = self._terms(question)

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
                    question,
                    search_results,
                    context_terms=context_terms,
                    primary_terms=current_terms,
                )
            )

            ranked_results = (
                self._filter_by_question_focus(
                    question,
                    ranked_results,
                    conversation_history,
                )
            )

            self._log_retrieval_diagnostics(
                question,
                ranked_results[:8],
                label="ranked",
            )

            if not self._is_retrieval_relevant(
                question,
                ranked_results,
                conversation_history,
            ):
                yield NOT_FOUND
                return

            relevant_chunks = (
                self._select_best_chunks(
                    ranked_results,
                    question,
                )
            )

            if not relevant_chunks:

                yield NOT_FOUND

                return

            retrieval_confidence = (
                self._compute_retrieval_confidence(
                    relevant_chunks
                )
            )

            self._log_retrieval_diagnostics(
                question,
                relevant_chunks,
                label="selected",
            )

            if (
                retrieval_confidence
                < INSUFFICIENT_CONFIDENCE_THRESHOLD
            ):
                yield NOT_FOUND_INSUFFICIENT
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
            "explain in detail",
            "in detail",
            "more detail",
            "elaborate",
            "go deeper",
            "expand on",
            "what about",
            "how about",
        )

        if q.startswith("explain") and len(words) <= 6:
            return True

        if has_pronoun or any(
            phrase in q for phrase in comparison_phrases
        ):
            return True

        # Very short utterances in a thread are usually follow-ups.
        return len(words) <= 2

    def _extract_context_terms(
        self,
        conversation_history: list[dict] | None,
        current_question: str = "",
    ) -> set[str]:
        """Minimal terms from recent user questions only (avoids answer-topic bleed)."""

        if not conversation_history:
            return set()

        terms: set[str] = set()
        current = self._terms(current_question)

        q_lower = (current_question or "").lower()
        needs_broad_history = any(
            word in q_lower
            for word in (
                "them",
                "both",
                "these",
                "those",
                "difference between",
                "compare",
            )
        )

        history_limit = 4 if needs_broad_history else 2
        term_cap = 10 if needs_broad_history else MAX_RETRIEVAL_EXPANSION_TERMS

        user_questions = [
            turn["content"]
            for turn in conversation_history
            if turn.get("role") == "user"
            and (turn.get("content") or "").strip()
        ][-history_limit:]

        for prior_question in user_questions:
            terms.update(self._terms(prior_question))

        terms -= current

        if len(terms) > term_cap:
            terms = set(sorted(terms)[:term_cap])

        return terms

    def _build_retrieval_query(
        self,
        question: str,
        conversation_history: list[dict] | None,
    ) -> str:
        """Expand retrieval only for vague follow-ups, with a small term cap."""

        if not conversation_history or not self._needs_context_expansion(
            question
        ):
            return question

        extra_terms = self._extract_context_terms(
            conversation_history,
            question,
        )

        if not extra_terms:
            return question

        return (
            f"{question} {' '.join(sorted(extra_terms))}"
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
        question: str = "",
    ) -> list[dict]:
        """Map sources to chunks that support both the answer and the question."""

        if not answer or not sources:
            return sources

        answer_terms = self._terms(answer)
        question_terms = self._terms(question)

        if not answer_terms:
            return sources

        scored_sources: list[tuple[float, dict]] = []

        for row in relevant_chunks:
            metadata = row.get("metadata", {})
            filename = (
                metadata.get("filename")
                or metadata.get("file")
                or "Unknown Document"
            )
            page = str(metadata.get("page", "-"))
            chunk_terms = self._terms(row.get("text", ""))

            if not chunk_terms:
                continue

            answer_overlap = len(
                answer_terms.intersection(chunk_terms)
            )
            question_overlap = len(
                question_terms.intersection(chunk_terms)
            )
            answer_ratio = answer_overlap / max(
                len(chunk_terms),
                1,
            )

            relevance = (
                answer_ratio * 0.6
                + (
                    question_overlap
                    / max(len(question_terms), 1)
                )
                * 0.4
            )

            if (
                answer_overlap >= 3
                or (
                    answer_overlap >= 2
                    and question_overlap >= 1
                )
                or answer_ratio >= 0.14
            ):
                scored_sources.append(
                    (
                        relevance,
                        {
                            "file": filename,
                            "page": page,
                            "confidence": round(
                                row.get("final_score", 0.0),
                                3,
                            ),
                        },
                    )
                )

        if not scored_sources:
            return sources[:1]

        scored_sources.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        filtered: list[dict] = []
        seen: set[tuple[str, str]] = set()

        for _, source in scored_sources:
            key = (source["file"], source["page"])
            if key not in seen:
                filtered.append(source)
                seen.add(key)

        return filtered

    def _filter_by_question_focus(
        self,
        question: str,
        ranked_results: list[dict],
        conversation_history: list[dict] | None = None,
    ) -> list[dict]:
        """Drop chunks weakly related to the current question (reduces cross-topic bleed)."""

        if len(ranked_results) <= 2:
            return ranked_results

        focus_question = question
        if (
            conversation_history
            and self._needs_context_expansion(question)
        ):
            extra = self._extract_context_terms(
                conversation_history,
                question,
            )
            if extra:
                focus_question = (
                    f"{question} {' '.join(sorted(extra))}"
                )

        question_terms = self._terms(focus_question)

        if not question_terms:
            return ranked_results

        overlaps = [
            self._term_overlap_ratio(
                focus_question,
                row.get("text", ""),
            )
            for row in ranked_results
        ]

        top_overlap = max(overlaps) if overlaps else 0.0
        min_keep = max(0.10, top_overlap * 0.40)

        focused = [
            row
            for row, overlap in zip(
                ranked_results,
                overlaps,
            )
            if overlap >= min_keep
            or float(row.get("final_score", 0)) >= 0.58
        ]

        return focused if focused else ranked_results[:4]

    def _compute_retrieval_confidence(
        self,
        relevant_chunks: list[dict],
    ) -> float:
        if not relevant_chunks:
            return 0.0

        return sum(
            float(row.get("final_score", 0.0))
            for row in relevant_chunks
        ) / len(relevant_chunks)

    def _log_retrieval_diagnostics(
        self,
        question: str,
        chunks: list[dict],
        label: str = "selected",
    ) -> None:
        """Log retrieval evidence without printing to stdout."""

        if not logger.isEnabledFor(logging.INFO):
            return

        logger.info(
            "RAG retrieval %s question=%r chunk_count=%s",
            label,
            question,
            len(chunks),
        )

        for idx, row in enumerate(chunks, start=1):
            metadata = row.get("metadata", {})
            logger.info(
                (
                    "RAG chunk %s file=%r page=%r semantic=%s "
                    "final=%s distance=%s kind=%r phase=%s text=%r"
                ),
                idx,
                metadata.get("filename") or metadata.get("file"),
                metadata.get("page"),
                row.get("confidence"),
                round(float(row.get("final_score", 0.0)), 3),
                row.get("distance"),
                metadata.get("chunk_kind"),
                label,
                row.get("text", "")[:500],
            )

    def _apply_low_confidence_notice(
        self,
        answer: str,
        retrieval_confidence: float,
    ) -> str:
        if not answer or self._is_not_found_response(answer):
            return answer

        if (
            answer.startswith("Based on the uploaded documents")
            or answer.startswith("I found limited information")
            or answer.startswith("The uploaded documents do not")
        ):
            return answer

        level = (
            "insufficient"
            if retrieval_confidence
            < INSUFFICIENT_CONFIDENCE_THRESHOLD
            else "limited"
        )

        return (
            PromptEngineer.low_confidence_preamble(level)
            + answer.strip()
        )

    def _is_verbatim_copy(
        self,
        answer: str,
        chunks: list[dict],
    ) -> bool:
        """Detect answers pasted from retrieved chunks."""

        answer_norm = re.sub(
            r"\s+",
            " ",
            answer.lower(),
        ).strip()

        for row in chunks:
            text = row.get("text", "")
            for sentence in self._extract_sentences(text):
                sent = re.sub(
                    r"\s+",
                    " ",
                    sentence.lower(),
                ).strip()
                if (
                    len(sent.split()) >= 10
                    and sent in answer_norm
                ):
                    return True

            words = text.lower().split()
            for idx in range(len(words) - 11):
                phrase = " ".join(
                    words[idx: idx + 12]
                )
                if (
                    len(phrase) > 45
                    and phrase in answer_norm
                ):
                    return True

        return False

    # =========================================================
    # SELECT BEST CHUNKS
    # =========================================================

    def _select_best_chunks(
        self,
        ranked_results: list[dict],
        question: str | None = None,
    ) -> list[dict]:

        relevant_chunks = []

        document_usage = defaultdict(
            int
        )

        semantic_fingerprints = set()

        top_question_overlap = 0.0

        if question and ranked_results:
            top_question_overlap = (
                self._term_overlap_ratio(
                    question,
                    ranked_results[0].get("text", ""),
                )
            )

        max_chunks = self._max_context_chunks(question or "")

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
                >= 2
            ):
                continue

            if row.get("final_score", 0) < MIN_CHUNK_SCORE:
                continue

            if question:
                chunk_overlap = (
                    self._term_overlap_ratio(
                        question,
                        text,
                    )
                )
                min_overlap = max(
                    0.15,
                    top_question_overlap * 0.50,
                )
                if (
                    chunk_overlap < min_overlap
                    and row.get("final_score", 0) < 0.52
                ):
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

            if len(relevant_chunks) >= max_chunks:
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

            text = text[:1400]

            context_blocks.append(
                f"""
                    DOCUMENT: {filename}
                    PAGE: {page}

                    {text}
                """.strip()
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
        primary_terms: set[str] | None = None,
    ) -> list[dict]:
        """Rerank: prioritize current-question overlap; light history boost on follow-ups."""

        current_terms = primary_terms or self._terms(
            question
        )
        intent = self._question_intent(question)

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
                    current_terms.intersection(
                        text_terms
                    )
                )
                / max(len(current_terms), 1)
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

            metadata = row.get("metadata", {})
            chunk_kind = metadata.get("chunk_kind", "general")

            intent_bonus = (
                self._intent_match_bonus(
                    intent,
                    text,
                    chunk_kind,
                )
            )

            exact_topic_bonus = (
                self._exact_topic_bonus(
                    question,
                    text,
                )
            )

            question_lower = (
                question.lower()
            )

            if (
                question_lower
                in text.lower()
            ):

                exact_topic_bonus += 0.10

            history_weight = (
                0.06 if context_terms else 0.0
            )

            semantic_only_penalty = (
                0.12
                if overlap == 0.0
                and not exact_topic_bonus
                and semantic_score < 0.72
                else 0.0
            )

            final_score = min(
                1.0,
                max(
                    0.0,
                    (
                        semantic_score * 0.46
                        + overlap * 0.40
                        + context_overlap * history_weight
                        + intent_bonus
                        + exact_topic_bonus
                        - semantic_only_penalty
                    ),
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

    def _question_intent(
        self,
        question: str,
    ) -> str:
        q = question.lower().strip()

        if any(
            phrase in q
            for phrase in (
                "difference between",
                "compare",
                " vs ",
                " versus ",
                "differentiate",
                "similarities",
            )
        ):
            return "comparison"

        if re.search(r"\b(types|kinds|classification)\s+of\b", q):
            return "type_list"

        if re.match(r"^(what is|what are|define|definition of)\b", q):
            return "definition"

        return "general"

    def _intent_match_bonus(
        self,
        intent: str,
        text: str,
        chunk_kind: str = "general",
    ) -> float:
        lowered = text.lower()

        if intent == "definition":
            return (
                0.18
                if chunk_kind == "definition"
                or self._looks_like_definition(text)
                else 0.0
            )

        if intent == "type_list":
            if chunk_kind == "type_list" or re.search(
                r"\b(types of|kinds of|classified into|classification|include|includes)\b",
                lowered,
            ):
                return 0.18

        if intent == "comparison":
            if chunk_kind == "comparison" or re.search(
                r"\b(difference|compare|comparison|versus|whereas|while)\b",
                lowered,
            ):
                return 0.18

        return 0.0

    def _exact_topic_bonus(
        self,
        question: str,
        text: str,
    ) -> float:
        terms = self._question_topic_terms(question)

        if not terms:
            return 0.0

        lowered = text.lower()
        bonus = 0.0

        if all(
            self._term_in_text(term, lowered)
            for term in terms[:4]
        ):
            bonus += 0.08

        if len(terms) == 1 and self._term_in_text(
            terms[0],
            lowered,
        ):
            bonus += 0.08

        words = re.findall(
            r"[a-zA-Z0-9_]+",
            question.lower(),
        )
        topic_words = [
            self._normalize_term(word)
            for word in words
            if word in terms
            or self._normalize_term(word) in terms
        ]

        for left, right in zip(topic_words, topic_words[1:]):
            if f"{left} {right}" in lowered:
                bonus += 0.04

        return min(bonus, 0.16)

    def _question_topic_terms(
        self,
        question: str,
    ) -> list[str]:
        stop_words = self._stop_words()
        words = re.findall(
            r"[a-zA-Z0-9_]+",
            question.lower(),
        )

        terms: list[str] = []
        seen: set[str] = set()

        for word in words:
            term = self._normalize_term(word)
            if (
                len(term) <= 2
                or term in stop_words
                or term in seen
            ):
                continue
            terms.append(term)
            seen.add(term)

        return terms

    def _normalize_term(
        self,
        word: str,
    ) -> str:
        word = word.lower().strip()

        if len(word) > 4 and word.endswith("ies"):
            return word[:-3] + "y"

        if (
            len(word) > 4
            and re.search(r"(ches|shes|sses|xes|zes)$", word)
        ):
            return word[:-2]

        if len(word) > 3 and word.endswith("s"):
            return word[:-1]

        return word

    def _term_in_text(
        self,
        term: str,
        lowered_text: str,
    ) -> bool:
        return bool(
            re.search(
                rf"\b{re.escape(term)}s?\b",
                lowered_text,
            )
        )

    def _max_context_chunks(
        self,
        question: str,
    ) -> int:
        q = question.lower()

        if any(
            phrase in q
            for phrase in (
                "explain in detail",
                "describe in detail",
                "comprehensive",
                "elaborate",
            )
        ):
            return 5

        if self._question_intent(question) in {
            "comparison",
            "type_list",
        }:
            return 4

        return 3

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
        conversation_history: list[dict] | None = None,
    ) -> bool:

        if not ranked_results:
            return False

        top = ranked_results[0]
        top_score = float(
            top.get("final_score", 0.0)
        )

        # Follow-ups like "explain in detail" rely on history for topic terms.
        if (
            conversation_history
            and self._needs_context_expansion(question)
            and top_score >= 0.36
        ):
            return True

        if top_score < MIN_TOP_RELEVANCE_SCORE:
            return False

        overlap_question = question
        if (
            conversation_history
            and self._needs_context_expansion(question)
        ):
            context_terms = self._extract_context_terms(
                conversation_history,
                question,
            )
            if context_terms:
                overlap_question = (
                    f"{question} {' '.join(sorted(context_terms))}"
                )

        overlaps = [
            self._term_overlap_ratio(
                overlap_question,
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

        # Conversational follow-ups: accept substantive answers on the thread topic.
        if (
            conversation_history
            and self._needs_context_expansion(question)
            and len(answer.split()) >= 20
        ):
            context_terms = self._extract_context_terms(
                conversation_history,
                question,
            )
            if context_terms:
                answer_lower = answer.lower()
                if any(
                    term in answer_lower
                    for term in context_terms
                ):
                    return True
            return len(answer.split()) >= 35

        question_terms = self._terms(question)

        if (
            self._needs_context_expansion(question)
            and conversation_history
        ):
            question_terms = question_terms.union(
                self._extract_context_terms(
                    conversation_history,
                    question,
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

    def _remove_unsupported_claims(
        self,
        answer: str,
        relevant_chunks: list[dict],
    ) -> str:
        """Drop risky technical claims when retrieved context does not support them."""

        if not answer or not relevant_chunks:
            return answer

        context = " ".join(
            row.get("text", "")
            for row in relevant_chunks
        ).lower()

        risky_claims = (
            "direct access",
            "random access",
            "any particular element",
            "any element directly",
            "both directions",
            "bidirectional",
            "at any position",
            "constant time",
            "o(1)",
            "o(n)",
            "o(log n)",
        )

        sentences = self._extract_sentences(answer)
        kept: list[str] = []

        for sentence in sentences:
            sentence_lower = sentence.lower()
            unsupported = any(
                claim in sentence_lower
                and claim not in context
                for claim in risky_claims
            )

            if unsupported:
                logger.info(
                    "Removed unsupported generated claim: %s",
                    sentence[:250],
                )
                continue

            kept.append(sentence.strip())

        cleaned = " ".join(
            sentence for sentence in kept if sentence
        ).strip()

        return cleaned or answer

    def _terms(
        self,
        text: str,
    ) -> set[str]:

        stop_words = self._stop_words()

        words = re.findall(
            r"[a-zA-Z0-9_]+",
            text.lower(),
        )

        return {

            self._normalize_term(word)

            for word in words

            if (
                len(self._normalize_term(word)) > 2
                and self._normalize_term(word) not in stop_words
            )

        }

    def _stop_words(
        self,
    ) -> set[str]:
        return {
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
            "type",
            "types",
            "kind",
            "kinds",
            "classification",
            "compare",
            "difference",
            "between",
            "versus",
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
            "does not appear to be covered",
            "do not contain enough information",
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
