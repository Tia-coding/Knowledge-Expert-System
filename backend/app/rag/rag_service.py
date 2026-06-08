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
    "The requested information was not found in the uploaded documents."
)

NOT_FOUND_INSUFFICIENT = (
    "The requested information was not found in the uploaded documents."
)

MIN_CHUNK_SCORE = 0.30
MIN_TOP_RELEVANCE_SCORE = 0.25
MIN_TERM_OVERLAP_RATIO = 0.05
LOW_CONFIDENCE_THRESHOLD = 0.35
INSUFFICIENT_CONFIDENCE_THRESHOLD = 0.10
MAX_RETRIEVAL_EXPANSION_TERMS = 8


class RAGService:

    def __init__(self) -> None:
        self.settings = get_settings()
        self.vector_store = get_vector_store()
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
            question = (question or "").strip()

            self._current_question = question

            if not question:
                return {
                    "answer": "Please enter a valid question.",
                    "sources": [],
                    "confidence": 0.0,
                }

            requested_top_k = top_k or max(self.settings.rag_top_k, 12)

            retrieval_query = self._build_retrieval_query(
                question,
                conversation_history,
            )

            logger.info("=" * 60)
            logger.info("QUESTION: %s", question)
            logger.info("RETRIEVAL QUERY: %s", retrieval_query)
            logger.info(
                "HISTORY COUNT: %s",
                len(conversation_history or [])
            )
            logger.info("=" * 60)

            is_follow_up = self._needs_context_expansion(question)
            context_terms = (
                self._extract_context_terms(conversation_history, question)
                if is_follow_up
                else None
            )
            current_terms = self._terms(question)

            search_results = self.vector_store.search(
                retrieval_query,
                requested_top_k,
            )

            if not search_results:
                return {
                    "answer": NOT_FOUND,
                    "sources": [],
                    "confidence": 0.0,
                }

            ranked_results = self._rank_results(
                question,
                search_results,
                context_terms=context_terms,
                primary_terms=current_terms,
            )

            ranked_results = self._filter_by_question_focus(
                question,
                ranked_results,
                conversation_history,
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

            relevant_chunks = self._select_best_chunks(
                ranked_results,
                question,
            )

            if not relevant_chunks:
                return {
                    "answer": NOT_FOUND,
                    "sources": [],
                    "confidence": 0.0,
                }

            context_blocks, sources = self._build_context(relevant_chunks)
            retrieval_confidence = self._compute_retrieval_confidence(relevant_chunks)

            if retrieval_confidence < INSUFFICIENT_CONFIDENCE_THRESHOLD:
                return {
                    "answer": NOT_FOUND_INSUFFICIENT,
                    "sources": [],
                    "confidence": 0.0,
                }

            # =====================================================
            # BUILD PROMPT
            # =====================================================
            prompt = PromptEngineer.build_prompt(
                question,
                context_blocks,
                conversation_history,
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

                # Clean markdown table wrappers generated by the model
                if "|" in answer:
                    lines = answer.splitlines()
                    cleaned_lines = []

                    for line in lines:
                        lower = line.strip().lower()
                        if lower.startswith("here is the markdown table"):
                            continue
                        if lower.startswith("note:"):
                            continue
                        cleaned_lines.append(line)

                    answer = "\n".join(cleaned_lines).strip()

                logger.info("RAW LLM ANSWER:")
                logger.info(answer[:3000])

            except Exception as e:
                logger.exception(f"LLM generation failed: {str(e)}")

            # =====================================================
            # FALLBACK RETRY & CONDITIONS
            # =====================================================
            min_words = self._minimum_answer_words(question)

            if (
                not answer
                or len(answer.split()) < min_words
                or self._looks_like_raw_chunk(answer)
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

                    if retry_answer and len(retry_answer.split()) >= min_words:
                        answer = retry_answer
                except Exception as e:
                    logger.exception(f"Retry generation failed: {str(e)}")

            logger.info("FINAL GENERATED ANSWER:")
            logger.info(answer[:3000] if answer else "EMPTY")

            if not answer:
                answer = self._generate_fallback_answer(
                    question,
                    relevant_chunks,
                )

            # =====================================================
            # POST-PROCESSING CLEANUPS
            # =====================================================
            answer = PromptEngineer.clean_response(answer, question)

            # Remove broken empty code blocks
            answer = re.sub(
                r"``+\w*\s*\n\s*//.*?\n\s*``+",
                "",
                answer,
                flags=re.DOTALL
            )
            answer = self._clean_natural_answer(answer)

            # Highly accurate text-matching reference extraction engine
            sources = self._filter_sources_by_answer_usage(
                answer,
                relevant_chunks,
                sources,
                question,
            )

            if self._is_not_found_response(answer):
                sources = []

            return {
                "answer": answer,
                "sources": sources,
                "confidence": max(0.10, min(round(retrieval_confidence, 3), 0.99)),
            }

        except Exception as e:
            logger.exception(f"RAG pipeline failed: {str(e)}")
            return {
                "answer": "An error occurred while processing your request.",
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
            question = (question or "").strip()
            if not question:
                yield "Please enter a valid question."
                return

            requested_top_k = top_k or self.settings.rag_top_k

            retrieval_query = self._build_retrieval_query(
                question,
                conversation_history,
            )
            search_results = self.vector_store.search(
                retrieval_query,
                requested_top_k,
            )

            if not search_results:
                yield NOT_FOUND
                return

            ranked_results = self._rank_results(
                question,
                search_results,
                context_terms=None,
                primary_terms=self._terms(question),
            )

            relevant_chunks = self._select_best_chunks(
                ranked_results,
                question,
            )

            if not relevant_chunks:
                yield NOT_FOUND
                return

            context_blocks, _ = self._build_context(relevant_chunks)
            prompt = PromptEngineer.build_prompt(
                question,
                context_blocks,
                conversation_history,
            )

            async for token in self.ollama.stream_generate(
                prompt,
                model=model,
            ):
                if token:
                    yield token

        except Exception as e:
            logger.exception(f"Streaming failed: {str(e)}")
            yield "An error occurred while streaming the response."

    # =========================================================
    # INTERNAL STRUCTURAL METHODS
    # =========================================================

    def _needs_context_expansion(self, question: str) -> bool:
        q = question.lower().strip()
        words = q.split()
        reference_words = {"them", "their", "they", "it", "its", "this", "that", "these", "those"}
        return any(word.strip("?.,!") in reference_words for word in words) or len(words) <= 2

    def _extract_context_terms(self, conversation_history: list[dict] | None, current_question: str = "") -> set[str]:
        if not conversation_history: return set()
        terms: set[str] = set()
        user_questions = [turn["content"] for turn in conversation_history if turn.get("role") == "user" and (turn.get("content") or "").strip()][-2:]
        for prior_question in user_questions:
            terms.update(self._terms(prior_question))
        return terms - self._terms(current_question)

    def _build_retrieval_query(self, question: str, conversation_history: list[dict] | None) -> str:
        if not conversation_history or not self._needs_context_expansion(question):
            return question
        extra_terms = self._extract_context_terms(conversation_history, question)
        if not extra_terms: return question
        return f"{question} {' '.join(sorted(extra_terms))}".strip()

    def _chunk_fingerprint(self, text: str) -> str:
        words = re.findall(r"[a-zA-Z0-9_]+", text.lower())
        content_words = sorted({w for w in words if len(w) > 3})[:40]
        return " ".join(content_words) if content_words else text[:250].strip().lower()

    def _filter_by_question_focus(self, question: str, ranked_results: list[dict], conversation_history: list[dict] | None = None) -> list[dict]:
        return ranked_results

    def _compute_retrieval_confidence(self, relevant_chunks: list[dict]) -> float:
        if not relevant_chunks: 
            return 0.0
        scores = [float(row.get("final_score", 0.0)) for row in relevant_chunks]
        return sum(scores) / len(scores) if scores else 0.0

    def _select_best_chunks(self, ranked_results: list[dict], question: str | None = None) -> list[dict]:
        relevant_chunks = []
        seen_pages = set()
        seen_fingerprints = set()
        max_chunks = self._max_context_chunks(question or "")

        for row in ranked_results:
            metadata = row.get("metadata", {})
            filename = metadata.get("filename") or metadata.get("file") or "Unknown"
            page = metadata.get("page", "-")
            
            if row.get("final_score", 0) < MIN_CHUNK_SCORE:
                continue
                
            text = row.get("text", "").strip()

            page_key = (filename, page)
            seen_pages.add(page_key)

            fingerprint = self._chunk_fingerprint(text)
            if fingerprint in seen_fingerprints:
                continue

            seen_fingerprints.add(fingerprint)
            relevant_chunks.append(row)

            if len(relevant_chunks) >= max_chunks:
                break

        return relevant_chunks

    def _build_context(self, rows: list[dict]) -> tuple[list[str], list[dict]]:
        context_blocks = []
        sources = []
        seen_sources = set()

        ordered_rows = CoherenceAnalyzer.order_chunks_for_coherence(rows)

        for row in ordered_rows:
            metadata = row.get("metadata", {})
            filename = metadata.get("filename") or metadata.get("file") or "Unknown Document"
            page = metadata.get("page", "-")

            source_key = (filename, page)
            if source_key not in seen_sources:
                sources.append({
                    "file": filename,
                    "page": str(page),
                    "confidence": round(row["final_score"], 3),
                })
                seen_sources.add(source_key)

            text = row.get("text", "")


            question_lower = getattr(self, "_current_question", "").lower()

            

            text = re.sub(
                r"```.*?```",
                "",
                text,
                flags=re.DOTALL,
            )
            text = re.sub(
                r"\b(?:Chapter|Section|Part)\s+\d+(?:\.\d+)*\b",
                "",
                text,
                flags=re.IGNORECASE,
            )
            text = re.sub(r"\s+", " ", text).strip()

            if text and text[0].islower():
                first_period = text.find(".")
                if 0 < first_period < 150:
                    text = text[first_period + 1 :].strip()

            logger.info("=" * 80)
            logger.info(text[:500])
            logger.info("=" * 80)
            
            context_blocks.append(text)

        return context_blocks, sources

    def _rank_results(self, question: str, results: list[dict], context_terms: set[str] | None = None, primary_terms: set[str] | None = None) -> list[dict]:
        current_terms = primary_terms or self._terms(question)
        ranked = []

        for row in results:
            text = row.get("text", "")
            text_terms = self._terms(text)
            semantic_score = float(row.get("confidence", 0.0))

            overlap = len(current_terms.intersection(text_terms)) / max(len(current_terms), 1)

            coverage = len(current_terms.intersection(text_terms))
            coverage = coverage / max(len(current_terms), 1)

            final_score = (
                semantic_score * 0.70
            ) + (
                coverage * 0.30
            )
            ranked.append({**row, "final_score": final_score})

            chunk_kind = row.get("metadata", {}).get("chunk_kind", "general")

            boost = 0

            if question.lower().startswith(("what is", "define")):
                if chunk_kind == "definition":
                    boost += 0.15

            elif "compare" in question.lower():
                if chunk_kind == "comparison":
                    boost += 0.15

            elif any(x in question.lower() for x in ["types", "kinds"]):
                if chunk_kind == "type_list":
                    boost += 0.15

            final_score += boost

        return sorted(ranked, key=lambda item: item["final_score"], reverse=True)

    def _filter_sources_by_answer_usage(self, answer: str, relevant_chunks: list[dict], sources: list[dict], question: str = "") -> list[dict]:
        if not answer or not relevant_chunks: 
            return sources
            
        answer_terms = self._terms(answer)
        query_terms = self._terms(question)
        
        scored_sources = []
        seen = set()

        for chunk in relevant_chunks:
            metadata = chunk.get("metadata", {})
            file = metadata.get("filename") or metadata.get("file") or "Unknown"
            page = str(metadata.get("page", "-"))
            
            key = (file, page)
            if key in seen:
                continue
                
            chunk_text = chunk.get("text", "").lower()
            chunk_terms = self._terms(chunk_text)
            
            query_overlap = len(query_terms.intersection(chunk_terms))
            answer_overlap = len(answer_terms.intersection(chunk_terms))
            
            final_relevance_score = (
                query_overlap * 5.0
                + answer_overlap * 4.0
                + float(chunk.get("final_score", 0.0)) * 3.0
            )
            
            scored_sources.append({
                "file": file,
                "page": page,
                "weight": final_relevance_score
            })
            seen.add(key)

        scored_sources.sort(key=lambda s: s["weight"], reverse=True)

        filtered_sources = []
        for s in scored_sources:
            orig_match = next((c for c in relevant_chunks if str(c.get("metadata", {}).get("page", "-")) == s["page"]), {})
            confidence_val = orig_match.get("final_score", 0.75)

            filtered_sources.append({
                "file": s["file"],
                "page": s["page"],
                "confidence": round(float(confidence_val), 3)
            })

        is_direct_def = question.lower().strip().startswith(("define", "what is", "meaning of"))
        return filtered_sources[:2] if is_direct_def else filtered_sources[:4]

    def _generate_fallback_answer(self, question: str, rows: list[dict]) -> str:
        return NOT_FOUND

    def _extract_sentences(self, text: str) -> list[str]:
        return re.split(r"(?<=[.!?])\s+", text)

    def _max_context_chunks(self, question: str) -> int:
        answer_type = PromptEngineer.detect_answer_type(question)
        depth = PromptEngineer.answer_depth(question)
        q = question.lower().strip()

        if answer_type in ("comparison", "list", "procedure", "algorithm"):
            return 6

        if depth == "brief":
            return 2

        if depth == "detailed" or re.search(
            r"\b(explain|describe|detail|elaborate)\b",
            q,
        ):
            return 5

        return 4

    def _minimum_answer_words(self, question: str) -> int:
        q = question.lower().strip()

        if q.startswith(("what is", "define", "meaning of")):
            return 3

        if "detail" in q:
            return 40

        if "explain" in q:
            return 25

        if any(
            word in q
            for word in [
                "procedure",
                "algorithm",
                "steps",
                "workflow",
                "process",
            ]
        ):
            return 8

        return 15

    def _looks_like_raw_chunk(self, text: str) -> bool:
        return False

    def _is_retrieval_relevant(
        self,
        question: str,
        ranked_results: list[dict],
        conversation_history: list[dict] | None = None,
    ) -> bool:

        if not ranked_results:
            return False

        top_score = ranked_results[0].get("final_score", 0)
        return top_score >= MIN_TOP_RELEVANCE_SCORE

    def _clean_natural_answer(self, answer: str) -> str:
        if not answer: return answer
        text = answer.strip()
        text = re.sub(r"(?i)^\s*based on the (uploaded |provided )?documents?.*\n?", "", text)
        return text.strip()

    def _terms(self, text: str) -> set[str]:
        if not text:
            return set()
        clean_string = re.sub(r"[^\w\s]", " ", text.lower())
        words = clean_string.split()
        
        stop_words = {
            "what", "is", "are", "the", "a", "an", "of", "to", "in", "and", "or", "for", 
            "about", "define", "explain", "describe", "document", "context", "uploaded",
            "compare", "comparison", "different", "difference", "tabular", "table", "form",
            "show", "find", "summarize", "give", "list", "get", "please", 
        }
        return {w for w in words if w not in stop_words and (not w.isdigit() or len(w) >= 1)}

    def _is_not_found_response(self, answer: str) -> bool:
        normalized = answer.strip().lower()
        return normalized in (
            "The requested information was not found in the uploaded documents.",
            "I could not find sufficient information about this topic in the uploaded documents.",
        )