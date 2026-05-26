"""
Coherence analysis and semantic relationship detection for RAG context.

Provides:
- Topic consistency detection across chunks
- Semantic relationship mapping (elaboration, contrast, prerequisite)
- Fragmentation detection in answers
- Context ordering and grouping by semantic similarity
- Paragraph boundary preservation signals
"""

import re
from typing import Any
from collections import defaultdict


class CoherenceAnalyzer:
    """Analyzes and improves coherence in RAG context and answers."""

    # =========================================================
    # CHUNK RELATIONSHIP DETECTION
    # =========================================================

    @staticmethod
    def detect_chunk_relationships(
        chunks: list[dict],
    ) -> list[dict]:
        """
        Detect semantic relationships between chunks.
        Returns chunks with relationship metadata.
        """
        for i, chunk in enumerate(chunks):
            relationships = []

            if i > 0:
                prev_chunk = chunks[i - 1]
                rel_type = CoherenceAnalyzer._detect_relationship(
                    prev_chunk.get("text", ""),
                    chunk.get("text", ""),
                )
                if rel_type:
                    relationships.append({
                        "type": rel_type,
                        "reference": "previous",
                    })

            if i < len(chunks) - 1:
                next_chunk = chunks[i + 1]
                rel_type = CoherenceAnalyzer._detect_relationship(
                    chunk.get("text", ""),
                    next_chunk.get("text", ""),
                )
                if rel_type:
                    relationships.append({
                        "type": rel_type,
                        "reference": "next",
                    })

            chunk["relationships"] = relationships

        return chunks

    @staticmethod
    def _detect_relationship(
        text1: str,
        text2: str,
    ) -> str | None:
        """Detect relationship type between two text chunks."""
        text1_lower = text1.lower()
        text2_lower = text2.lower()

        # Extract key entities/topics
        topics1 = CoherenceAnalyzer._extract_topics(text1)
        topics2 = CoherenceAnalyzer._extract_topics(text2)

        overlap = len(topics1.intersection(topics2))
        total = len(topics1.union(topics2))
        similarity = overlap / total if total > 0 else 0

        # Strong topic continuity
        if similarity > 0.5:
            return "continuation"

        # Elaboration patterns
        elaboration_signals = [
            "furthermore",
            "in addition",
            "additionally",
            "moreover",
            "also",
            "for example",
            "specifically",
            "particularly",
        ]
        if any(
            signal in text2_lower
            for signal in elaboration_signals
        ):
            return "elaboration"

        # Contrast patterns
        contrast_signals = [
            "however",
            "conversely",
            "on the other hand",
            "in contrast",
            "despite",
            "whereas",
            "although",
            "unlike",
        ]
        if any(
            signal in text2_lower
            for signal in contrast_signals
        ):
            return "contrast"

        # Consequence patterns
        consequence_signals = [
            "therefore",
            "consequently",
            "as a result",
            "thus",
            "leading to",
            "causes",
            "results in",
        ]
        if any(
            signal in text2_lower
            for signal in consequence_signals
        ):
            return "consequence"

        return None

    # =========================================================
    # TOPIC EXTRACTION AND CONSISTENCY
    # =========================================================

    @staticmethod
    def _extract_topics(
        text: str,
    ) -> set[str]:
        """Extract key topics/entities from text."""
        # Simple topic extraction: capitalized phrases
        words = re.findall(
            r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b",
            text,
        )
        return set(word.lower() for word in words)

    @staticmethod
    def detect_topic_consistency(
        text_blocks: list[str],
    ) -> dict[str, Any]:
        """
        Analyze topic consistency across text blocks.
        Returns score and identified topics.
        """
        all_topics = []
        block_topics = []

        for block in text_blocks:
            topics = CoherenceAnalyzer._extract_topics(block)
            block_topics.append(topics)
            all_topics.extend(topics)

        # Calculate topic continuity
        continuity_scores = []
        for i in range(1, len(block_topics)):
            overlap = len(
                block_topics[i - 1].intersection(
                    block_topics[i]
                )
            )
            total = len(
                block_topics[i - 1].union(
                    block_topics[i]
                )
            )
            score = (
                overlap / total
                if total > 0
                else 0
            )
            continuity_scores.append(score)

        avg_continuity = (
            sum(continuity_scores)
            / len(continuity_scores)
            if continuity_scores
            else 0
        )

        dominant_topics = CoherenceAnalyzer._identify_dominant_topics(
            all_topics
        )

        return {
            "consistency_score": round(
                avg_continuity,
                3,
            ),
            "topic_continuity": continuity_scores,
            "dominant_topics": dominant_topics,
            "block_topics": [
                list(t) for t in block_topics
            ],
        }

    @staticmethod
    def _identify_dominant_topics(
        all_topics: list[str],
    ) -> list[str]:
        """Identify dominant topics in a list."""
        from collections import Counter

        if not all_topics:
            return []

        counter = Counter(all_topics)
        return [
            topic
            for topic, _ in counter.most_common(5)
        ]

    # =========================================================
    # FRAGMENTATION DETECTION
    # =========================================================

    @staticmethod
    def detect_fragmentation(
        answer: str,
    ) -> dict[str, Any]:
        """
        Detect signs of fragmentation in answer.
        Returns fragmentation score and indicators.
        """
        indicators = {
            "bullet_heavy": 0,
            "short_paragraphs": 0,
            "disjointed_sentences": 0,
            "orphaned_mentions": 0,
            "no_transitions": 0,
        }

        paragraphs = answer.split("\n\n")
        sentences = re.split(
            r"(?<=[.!?])\s+",
            answer,
        )

        # Check for bullet-heavy formatting
        bullet_lines = len(
            re.findall(
                r"^\s*[-•*]\s+",
                answer,
                re.MULTILINE,
            )
        )
        if bullet_lines > len(paragraphs) * 0.5:
            indicators["bullet_heavy"] = 0.2

        # Check for very short paragraphs
        short_paras = sum(
            1
            for p in paragraphs
            if len(p.split()) < 15
        )
        if short_paras > len(paragraphs) * 0.4:
            indicators["short_paragraphs"] = 0.2

        # Check sentence length variation
        sentence_lengths = [
            len(s.split()) for s in sentences
        ]
        if sentence_lengths:
            avg_length = (
                sum(sentence_lengths)
                / len(sentence_lengths)
            )
            outliers = sum(
                1
                for l in sentence_lengths
                if l < avg_length * 0.3
            )
            if outliers > len(sentences) * 0.3:
                indicators["disjointed_sentences"] = 0.15

        # Check for transition quality
        transition_words = [
            "furthermore",
            "moreover",
            "additionally",
            "however",
            "conversely",
            "therefore",
            "consequently",
            "building on",
            "related to",
            "similarly",
        ]
        transitions = sum(
            1
            for word in transition_words
            if word in answer.lower()
        )
        if (
            transitions == 0
            and len(paragraphs) > 2
        ):
            indicators["no_transitions"] = 0.2

        # Calculate total fragmentation score
        fragmentation_score = sum(
            indicators.values()
        ) / len(indicators)

        return {
            "fragmentation_score": round(
                fragmentation_score,
                3,
            ),
            "is_fragmented": (
                fragmentation_score > 0.35
            ),
            "indicators": indicators,
            "paragraphs": len(paragraphs),
            "sentences": len(sentences),
        }

    # =========================================================
    # CONTEXT ORDERING
    # =========================================================

    @staticmethod
    def order_chunks_for_coherence(
        chunks: list[dict],
    ) -> list[dict]:
        """
        Reorder chunks for better semantic coherence.
        Preserves document source boundaries.
        """
        if len(chunks) <= 1:
            return chunks

        # Group by source document
        by_source = defaultdict(list)
        for chunk in chunks:
            source = (
                chunk.get("metadata", {})
                .get("filename", "unknown")
            )
            by_source[source].append(chunk)

        # Order each source group internally
        ordered = []
        for source, group in by_source.items():
            if len(group) <= 1:
                ordered.extend(group)
                continue

            # Sort by page number if available
            group_with_page = [
                (
                    chunk,
                    int(
                        chunk.get("metadata", {})
                        .get("page", "0")
                    ),
                )
                for chunk in group
            ]
            sorted_group = sorted(
                group_with_page,
                key=lambda x: x[1],
            )
            ordered.extend([g[0] for g in sorted_group])

        return ordered

    # =========================================================
    # CONTEXT BRIDGE DETECTION
    # =========================================================

    @staticmethod
    def add_context_bridge_signals(
        context_blocks: list[str],
    ) -> list[dict]:
        """
        Analyze context blocks and add bridge signals.
        Returns blocks with relationship metadata.
        """
        enriched = []

        for i, block in enumerate(context_blocks):
            block_data = {
                "text": block,
                "index": i,
                "is_first": i == 0,
                "is_last": i == len(context_blocks) - 1,
                "bridges_to_next": (
                    i < len(context_blocks) - 1
                ),
                "has_prior": i > 0,
            }

            # Detect if block completes a thought
            text_lower = block.lower()
            has_conclusion = any(
                word in text_lower
                for word in [
                    "therefore",
                    "in conclusion",
                    "as a result",
                    "ultimately",
                ]
            )
            block_data["completes_thought"] = (
                has_conclusion
            )

            # Detect if block introduces new topic
            has_introduction = any(
                word in text_lower
                for word in [
                    "first",
                    "initially",
                    "beginning",
                    "to start",
                ]
            )
            block_data["introduces_topic"] = (
                has_introduction
            )

            enriched.append(block_data)

        return enriched

    # =========================================================
    # ANSWER COHERENCE SCORE
    # =========================================================

    @staticmethod
    def score_answer_coherence(
        answer: str,
    ) -> dict[str, Any]:
        """
        Score overall answer coherence.
        Returns comprehensive coherence metrics.
        """
        paragraphs = answer.split("\n\n")
        sentences = re.split(
            r"(?<=[.!?])\s+",
            answer,
        )

        # Length metrics
        has_substance = len(answer.split()) >= 40
        good_paragraph_count = (
            2 <= len(paragraphs) <= 5
        )

        # Transition quality
        transition_words = [
            "furthermore",
            "moreover",
            "additionally",
            "however",
            "conversely",
            "therefore",
            "consequently",
            "nevertheless",
            "likewise",
            "similarly",
        ]
        transition_count = sum(
            1
            for word in transition_words
            if word in answer.lower()
        )
        good_transitions = (
            transition_count >= 1
            if len(paragraphs) > 1
            else True
        )

        # Sentence variety
        if len(sentences) >= 3:
            lengths = [
                len(s.split()) for s in sentences
            ]
            avg = sum(lengths) / len(lengths)
            min_l = min(lengths)
            max_l = max(lengths)
            good_variety = (
                min_l > avg * 0.3
                and max_l < avg * 3
            )
        else:
            good_variety = True

        # Calculate coherence score
        factors = [
            has_substance,
            good_paragraph_count,
            good_transitions,
            good_variety,
        ]
        coherence_score = (
            sum(factors) / len(factors)
        )

        return {
            "coherence_score": round(
                coherence_score,
                3,
            ),
            "is_coherent": (
                coherence_score >= 0.65
            ),
            "metrics": {
                "has_substance": has_substance,
                "good_paragraph_count": good_paragraph_count,
                "good_transitions": good_transitions,
                "good_variety": good_variety,
                "transition_count": transition_count,
            },
            "paragraph_count": len(paragraphs),
            "sentence_count": len(sentences),
        }
