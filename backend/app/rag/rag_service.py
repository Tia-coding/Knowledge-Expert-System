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
    "Relevant information was not found "
    "in the uploaded documents."
)


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

            # =====================================================
            # VECTOR SEARCH
            # =====================================================

            search_results = (
                self.vector_store.search(
                    question,
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
                    question,
                    search_results,
                )
            )

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
            # BUILD PROMPT WITH COHERENCE SIGNALS
            # =====================================================

            prompt = (
                PromptEngineer.build_prompt(
                    question,
                    context_blocks,
                )
            )

            # Add dynamic coherence and synthesis signals
            coherence_signal = (
                PromptEngineer.build_coherence_signal(
                    context_blocks
                )
            )
            synthesis_signal = (
                PromptEngineer.build_context_synthesis_signal(
                    context_blocks
                )
            )
            continuation_signal = (
                PromptEngineer.build_continuation_signal(
                    question
                )
            )

            if coherence_signal or synthesis_signal:
                prompt += (
                    f"\n\n"
                    f"SYNTHESIS GUIDANCE:\n"
                    f"- {synthesis_signal}\n"
                    f"- {coherence_signal}"
                )
                if continuation_signal:
                    prompt += f"\n- {continuation_signal}"

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
                    + "Rewrite the answer naturally "
                    + "in concise professional language. "
                    + "Avoid textbook narration."
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

            # =====================================================
            # VALIDATE AND ENHANCE COHERENCE
            # =====================================================

            coherence_analysis = (
                CoherenceAnalyzer.score_answer_coherence(
                    answer
                )
            )

            # If answer is low coherence, try refinement
            if (
                not coherence_analysis["is_coherent"]
                and answer
                and len(answer) > 50
            ):

                refined_answer = (
                    self._enhance_answer_coherence(
                        answer
                    )
                )

                if refined_answer:
                    answer = refined_answer

            # =====================================================
            # FINAL VALIDATION
            # =====================================================

            if (
                not answer
                or len(answer.strip()) < 20
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

            search_results = (
                self.vector_store.search(
                    question,
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
                )
            )

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

            # Reject weak chunks
            if len(text.split()) < 20:
                continue

            # Reject OCR garbage
            if self._is_garbage_text(
                text
            ):
                continue

            # Prevent semantic duplicates
            fingerprint = (
                text[:250]
                .strip()
                .lower()
            )

            if (
                fingerprint
                in semantic_fingerprints
            ):
                continue

            semantic_fingerprints.add(
                fingerprint
            )

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
    ) -> list[dict]:

        question_terms = self._terms(
            question
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
                    semantic_score * 0.72
                    + overlap * 0.22
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

        indicators = [

            "chapter",

            "figure",

            "table",

            "exercise",

            "primitive data structures",

            "linked lists are one",

        ]

        text_lower = text.lower()

        return any(
            item in text_lower
            for item in indicators
        )

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