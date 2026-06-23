import re
from typing import Any
from collections import defaultdict


class CoherenceAnalyzer:
    """
    Lightweight domain-agnostic coherence utilities.
    No topic lists.
    No transition word lists.
    No language-specific heuristics.
    """

    @staticmethod
    def detect_chunk_relationships(
        chunks: list[dict],
    ) -> list[dict]:
        """Dynamically computes overlaps between sequential text chunks."""
        if not chunks:
            return []

        for i, chunk in enumerate(chunks):
            chunk["relationships"] = []
            text_i = chunk.get("text", "").lower()
            words_i = set(re.findall(r"\b\w{4,}\b", text_i))

            if not words_i:
                continue

            # Compare current chunk with neighboring chunks to flag thematic links
            for j, other_chunk in enumerate(chunks):
                if i == j:
                    continue
                text_j = other_chunk.get("text", "").lower()
                words_j = set(re.findall(r"\b\w{4,}\b", text_j))
                
                if not words_j:
                    continue

                overlap = len(words_i.intersection(words_j))
                min_len = min(len(words_i), len(words_j))
                
                if min_len > 0 and (overlap / min_len) > 0.25:
                    chunk["relationships"].append({
                        "target_index": j,
                        "strength": round(overlap / min_len, 3),
                        "type": "thematic_overlap"
                    })

        return chunks

    @staticmethod
    def detect_topic_consistency(
        text_blocks: list[str],
    ) -> dict[str, Any]:
        """Computes true vocabulary vocabulary consistency across context blocks."""
        if not text_blocks:
            return {
                "consistency_score": 0.0,
                "block_count": 0,
            }

        # Collect unique vocab sets across all provided segments
        block_vocabs = []
        all_vocab = set()
        lengths = []

        for block in text_blocks:
            words = set(re.findall(r"\b\w{4,}\b", block.lower()))
            block_vocabs.append(words)
            all_vocab.update(words)
            lengths.append(len(block.split()))

        if not all_vocab or len(text_blocks) <= 1:
            return {
                "consistency_score": 1.0,
                "block_count": len(text_blocks),
                "average_block_length": round(sum(lengths) / max(len(lengths), 1), 1),
            }

        # Compute internal intersection ratios dynamically
        intersection_scores = []
        for i, vocab_a in enumerate(block_vocabs):
            for j, vocab_b in enumerate(block_vocabs):
                if i >= j:
                    continue
                union_len = len(vocab_a.union(vocab_b))
                if union_len > 0:
                    intersection_scores.append(len(vocab_a.intersection(vocab_b)) / union_len)

        consistency_score = sum(intersection_scores) / len(intersection_scores) if intersection_scores else 0.5

        return {
            "consistency_score": round(consistency_score, 3),
            "block_count": len(text_blocks),
            "average_block_length": round(sum(lengths) / len(lengths), 1),
        }

    @staticmethod
    def detect_fragmentation(
        answer: str,
    ) -> dict[str, Any]:
        """Detect structural and markdown alignment fragmentation parameters safely."""
        if not answer:
            return {"fragmentation_score": 0.0, "is_fragmented": False}

        paragraphs = [p.strip() for p in answer.split("\n\n") if p.strip()]
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", answer.strip()) if s.strip()]

        indicators = {
            "bullet_heavy": 0.0,
            "short_paragraphs": 0.0,
            "disjointed_sentences": 0.0,
        }

        bullet_lines = len(re.findall(r"^\s*[-•*+]\s+", answer, re.MULTILINE))
        table_lines = len(re.findall(r"^\s*\|", answer, re.MULTILINE))

        # Balance bullet density measurements against markdown table blocks
        if paragraphs and bullet_lines > (len(paragraphs) * 1.5) and table_lines == 0:
            indicators["bullet_heavy"] = 0.3

        short_paragraphs = sum(1 for p in paragraphs if len(p.split()) < 8 and not p.startswith(('-', '*', '|')))
        if paragraphs and short_paragraphs > len(paragraphs) * 0.4:
            indicators["short_paragraphs"] = 0.3

        lengths = [len(s.split()) for s in sentences]
        if len(lengths) >= 3:
            avg = sum(lengths) / len(lengths)
            outliers = sum(1 for length in lengths if length < max(3, avg * 0.20))
            if outliers > len(lengths) * 0.25:
                indicators["disjointed_sentences"] = 0.25

        fragmentation_score = sum(indicators.values())

        return {
            "fragmentation_score": round(fragmentation_score, 3),
            "is_fragmented": fragmentation_score > 0.45,
            "indicators": indicators,
            "paragraphs": len(paragraphs),
            "sentences": len(sentences),
        }

    @staticmethod
    def order_chunks_for_coherence(
        chunks: list[dict],
    ) -> list[dict]:
        """Safely sorts chunks chronologically by handling erratic string page footprints."""
        if len(chunks) <= 1:
            return chunks

        by_source = defaultdict(list)
        for chunk in chunks:
            source = chunk.get("metadata", {}) or {}
            filename = source.get("filename") or source.get("file") or "unknown"
            by_source[filename].append(chunk)

        ordered = []
        for filename, group in by_source.items():
            def extract_page_number(c):
                meta = c.get("metadata", {}) or {}
                raw_page = meta.get("page", 0)
                if isinstance(raw_page, int):
                    return raw_page
                # Safe fallback extract digits from string annotations (e.g., "p. 80" -> 80)
                digits = re.findall(r"\d+", str(raw_page))
                return int(digits[0]) if digits else 0

            try:
                group.sort(key=extract_page_number)
            except Exception:
                pass

            ordered.extend(group)

        return ordered

    @staticmethod
    def add_context_bridge_signals(
        context_blocks: list[str],
    ) -> list[dict]:
        """Enriches items with programmatic indexing markers for prompt processing maps."""
        enriched = []
        for i, block in enumerate(context_blocks):
            enriched.append({
                "text": block,
                "index": i,
                "is_first": i == 0,
                "is_last": i == len(context_blocks) - 1,
            })
        return enriched

    @staticmethod
    def score_answer_coherence(
        answer: str,
    ) -> dict[str, Any]:
        """Generic structural coherence scoring metrics wrapper block."""
        if not answer:
            return {"coherence_score": 0.0, "is_coherent": False}

        paragraphs = [p.strip() for p in answer.split("\n\n") if p.strip()]
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", answer) if s.strip()]
        word_count = len(answer.split())

        has_substance = word_count >= 30
        good_paragraph_count = len(paragraphs) >= 1
        good_sentence_count = len(sentences) >= 2

        factors = [has_substance, good_paragraph_count, good_sentence_count]
        coherence_score = sum(factors) / len(factors)

        return {
            "coherence_score": round(coherence_score, 3),
            "is_coherent": coherence_score >= 0.65,
            "metrics": {
                "word_count": word_count,
                "paragraph_count": len(paragraphs),
                "sentence_count": len(sentences),
            },
        }