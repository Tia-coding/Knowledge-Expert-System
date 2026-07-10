import logging
import re
from functools import lru_cache
from typing import Any

import unicodedata
from datetime import datetime
from sklearn.feature_extraction.text import ENGLISH_STOP_WORDS
import chromadb
from chromadb.config import Settings as ChromaSettings
from sentence_transformers import SentenceTransformer

from app.config.settings import get_settings
from app.services.document_processor import ExtractedChunk

logger = logging.getLogger(__name__)


class VectorStore:

    def __init__(self) -> None:
        self.settings = get_settings()

        self.client = chromadb.PersistentClient(
            path=self.settings.chroma_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        self.collection = self.client.get_or_create_collection(
            name="nrsc_documents",
            metadata={"hnsw:space": "cosine"},
        )

        self.embedding_model = SentenceTransformer(
            self.settings.embedding_model,
            local_files_only=True,
        )

    def add_document_chunks(
        self,
        document_id: int,
        chunks: list[ExtractedChunk],
    ) -> None:
        if not chunks:
            return

        ids = []
        texts = []
        metadatas = []

        for idx, chunk in enumerate(chunks):
            chunk_id = f"doc-{document_id}-{idx}"
            cleaned_text = self._normalize_text(chunk.text)

            if self._is_noisy_text(cleaned_text):
                continue

            metadata = dict(chunk.metadata)
            metadata["document_id"] = document_id
            metadata["file"] = (
                metadata.get("file")
                or metadata.get("filename")
                or "Unknown Document"
            )
            metadata["chunk_id"] = chunk_id

            ids.append(chunk_id)
            texts.append(cleaned_text)
            metadatas.append(metadata)

        if not texts:
            return

        # Batch encode for performance
        embeddings = self.embedding_model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=False,
        ).tolist()

        # Batch delete and add
        try:
            self.collection.delete(ids=ids)
        except Exception:
            pass

        # ChromaDB handles large batches internally
        self.collection.add(
            ids=ids,
            documents=texts,
            embeddings=embeddings,
            metadatas=metadatas,
        )

        logger.info("Added %s chunks for document %s", len(texts), document_id)

    def delete_document(self, document_id: int) -> None:
        self.collection.delete(where={"document_id": document_id})

    def _hybrid_term_score(self, query_terms: set[str], text: str) -> float:
        """Compute keyword overlap score for hybrid retrieval boosting."""
        if not query_terms or not text:
            return 0.0
        text_lower = text.lower()
        text_terms = set(re.findall(r'\b[a-zA-Z0-9]{2,}\b', text_lower))
        if not text_terms:
            return 0.0
        overlap = len(query_terms.intersection(text_terms))
        return overlap / max(len(query_terms), 1)

    def search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        query = query.strip()
        if not query:
            return []

        if self.count() == 0:
            logger.warning("Search query processed against an empty vector collection.")
            return []

        embedding = self.embedding_model.encode(
            [query],
            normalize_embeddings=True,
        ).tolist()[0]

        # Fetch moderate extra candidates for hybrid scoring
        fetch_k = max(top_k * 3, 20)
        result = self.collection.query(
            query_embeddings=[embedding],
            n_results=fetch_k,
            include=["documents", "metadatas", "distances"],
        )

        documents = result.get("documents") or [[]]
        metadatas = result.get("metadatas") or [[]]
        distances = result.get("distances") or [[]]

        doc_list = documents[0] if documents else []
        meta_list = metadatas[0] if metadatas else []
        dist_list = distances[0] if distances else []

        query_terms = {
            term
            for term in re.findall(r"\b[a-zA-Z0-9]{2,}\b", query.lower())
            if term not in ENGLISH_STOP_WORDS
        }

        rows = []
        seen_texts = set()

        for text, metadata, distance in zip(doc_list, meta_list, dist_list):
            if not text or not metadata:
                continue

            clean_text = self._normalize_text(text)
            if self._is_noisy_text(clean_text):
                continue

            # Fast dedup using first 80 words as key
            words = re.findall(r"\w+", clean_text.lower())
            text_key = " ".join(words[:80])
            if text_key in seen_texts:
                continue
            seen_texts.add(text_key)

            raw_dist = float(distance)
            semantic_score = max(0.0, min(1.0, 1.0 - raw_dist))

            # Hybrid keyword boost (65/35 blend)
            keyword_score = self._hybrid_term_score(query_terms, clean_text)
            #Added here
            phrase_bonus = 0.0

            query_lower = query.lower()
            text_lower = clean_text.lower()

            if query_lower in text_lower:
                phrase_bonus = 0.20
#Added changed ratio to 60/25
            blended_confidence = semantic_score * 0.60 + keyword_score * 0.25 + phrase_bonus

            rows.append({
                "text": clean_text,
                "metadata": metadata,
                "confidence": round(blended_confidence, 3),
                "distance": round(raw_dist, 4),
                "semantic_score": round(semantic_score, 3),
                "keyword_score": round(keyword_score, 3),
            })

        rows.sort(key=lambda item: item["confidence"], reverse=True)
        return rows[:top_k]

    def get_document_snippets(self, document_id: int, limit: int = 10) -> list[dict[str, Any]]:
        try:
            result = self.collection.get(
                where={"document_id": document_id},
                limit=limit,
                include=["documents", "metadatas"],
            )

            documents = result.get("documents") or []
            metadatas = result.get("metadatas") or []
            snippets = []

            for text, metadata in zip(documents, metadatas):
                if not text: continue
                snippets.append({
                    "text": text[:1200],
                    "page": metadata.get("page", "-"),
                    "file": metadata.get("file", metadata.get("filename", "Unknown Document")),
                    "chunk_id": metadata.get("chunk_id"),
                    "document_type": metadata.get("document_type"),
                })
            return snippets
        except Exception:
            logger.exception("Failed to retrieve snippets")
            return []

    def _normalize_text(self, text: str) -> str:
        if not text:
            return ""

        text = unicodedata.normalize("NFKC", text)

        text = "".join(
            ch
            for ch in text
            if unicodedata.category(ch)[0] != "C"
            or ch in "\n\t\r"
        )

        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\*{3,}", " ", text)
        text = re.sub(r"_{3,}", " ", text)
        text = text.strip()
        text = re.sub(r"\s+", " ", text)

        return text

    def _is_noisy_text(self, text: str) -> bool:
        if not text:
            return True
        if len(text) < 25:
            return True

        garbage_ratio = len(re.findall(r"[^a-zA-Z0-9\s.,!?():;\-\[\]|+=*/%<>&_$\"\'@#~]", text)) / max(len(text), 1)
        if garbage_ratio > 0.35:
            return True

        if re.search(r"[^\s]{150,}", text):
            return True

        return False

    def count(self) -> int:
        try:
            return self.collection.count()
        except Exception:
            logger.exception("Failed to count collection")
            return 0


@lru_cache
def get_vector_store() -> VectorStore:
    return VectorStore()