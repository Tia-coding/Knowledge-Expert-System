"""
Advanced prompt engineering for multimodal RAG system.

Optimized for:
- Human-like answers
- Technical correctness
- Multi-document summarization
- OCR cleanup
- Scanned PDFs
- Tables and algorithms
- Educational explanations
- Concise professional responses
"""

from typing import List
import re


class PromptEngineer:
    """Prompt engineering utility for intelligent RAG responses."""

    # =========================================================
    # QUESTION TYPE DETECTION
    # =========================================================

    @staticmethod
    def detect_question_type(question: str) -> str:

        question_lower = question.lower().strip()

        if any(
            word in question_lower
            for word in [
                "what is",
                "define",
                "meaning",
                "explain what",
            ]
        ):
            return "definition"

        if any(
            word in question_lower
            for word in [
                "how to",
                "how do",
                "steps",
                "procedure",
                "process",
            ]
        ):
            return "how-to"

        if any(
            word in question_lower
            for word in [
                "list",
                "types",
                "kinds",
                "enumerate",
            ]
        ):
            return "list"

        if any(
            word in question_lower
            for word in [
                "difference",
                "compare",
                "vs",
                "versus",
            ]
        ):
            return "comparison"

        if any(
            word in question_lower
            for word in [
                "algorithm",
                "code",
                "database",
                "implementation",
                "program",
                "function",
                "class",
                "data structure",
                "sql",
            ]
        ):
            return "technical"

        return "general"

    # =========================================================
    # COMMON RULES
    # =========================================================

    @staticmethod
    def common_rules() -> str:

        return """
IMPORTANT RULES:

1. Answer ONLY using the provided document context.
2. Never invent information not present in the documents.
3. If the context does not cover the user's topic, reply exactly:
   "I couldn't find information about that in your uploaded documents."
4. Ignore corrupted OCR text or unreadable symbols.
5. Write like a helpful expert: clear, natural, and conversational.
6. Keep answers focused: usually 1-3 short paragraphs (or brief bullets for lists).
7. Start immediately with the answer — no preamble or meta commentary.
8. NEVER use phrases such as:
   - "Here's my response"
   - "Here is the answer"
   - "Here's a rewritten response"
   - "synthesizes the provided documents"
   - "Based on the documents"
   - "According to the uploaded files"
   - "From the provided documents"
   - "The answer is"
9. Do not mention documents, files, context, rewriting, or synthesis.
10. Avoid textbook tone, storytelling, and repeated ideas.
11. Summarize in your own words; do not copy long raw passages.
12. Preserve technical accuracy; use simple language where possible.
13. Use bullet points only when listing types, steps, or comparisons.
"""

    # =========================================================
    # DEFINITION PROMPT
    # =========================================================

    @staticmethod
    def build_definition_prompt(
        question: str,
        context_blocks: List[str],
    ) -> str:

        context = "\n\n".join(context_blocks)

        return f"""
You are an advanced AI knowledge assistant.

The user is asking for a concept definition or explanation.

{PromptEngineer.common_rules()}

SPECIAL INSTRUCTIONS:

- Open with a one-sentence definition, then explain briefly.
- Stay within 1-3 short paragraphs unless listing subtypes.
- Sound natural, not like a textbook excerpt.

DOCUMENT CONTEXT:
{context}

QUESTION:
{question}

ANSWER (start directly, no preamble):
""".strip()

    # =========================================================
    # HOW-TO PROMPT
    # =========================================================

    @staticmethod
    def build_how_to_prompt(
        question: str,
        context_blocks: List[str],
    ) -> str:

        context = "\n\n".join(context_blocks)

        return f"""
You are an advanced AI assistant.

The user is asking for procedural guidance.

{PromptEngineer.common_rules()}

SPECIAL INSTRUCTIONS:

- Explain steps clearly and practically.
- Use numbered steps when useful.
- Focus on actionable guidance.
- Avoid unnecessary theory.
- Keep explanations concise.

DOCUMENT CONTEXT:
{context}

QUESTION:
{question}

STEP-BY-STEP ANSWER:
""".strip()

    # =========================================================
    # LIST PROMPT
    # =========================================================

    @staticmethod
    def build_list_prompt(
        question: str,
        context_blocks: List[str],
    ) -> str:

        context = "\n\n".join(context_blocks)

        return f"""
You are an advanced AI assistant.

The user is asking for a structured list response.

{PromptEngineer.common_rules()}

SPECIAL INSTRUCTIONS:

- Use concise bullet points for each type or item.
- One short line per bullet; no repetition.
- Do not add an introduction sentence before the list.

DOCUMENT CONTEXT:
{context}

QUESTION:
{question}

ANSWER (start directly, no preamble):
""".strip()

    # =========================================================
    # COMPARISON PROMPT
    # =========================================================

    @staticmethod
    def build_comparison_prompt(
        question: str,
        context_blocks: List[str],
    ) -> str:

        context = "\n\n".join(context_blocks)

        return f"""
You are an advanced AI assistant.

The user is asking for a comparison.

{PromptEngineer.common_rules()}

SPECIAL INSTRUCTIONS:

- Clearly explain differences and similarities.
- Focus on key distinctions.
- Keep explanations concise.
- Use tables ONLY if useful.

DOCUMENT CONTEXT:
{context}

QUESTION:
{question}

COMPARISON ANSWER:
""".strip()

    # =========================================================
    # TECHNICAL PROMPT
    # =========================================================

    @staticmethod
    def build_technical_prompt(
        question: str,
        context_blocks: List[str],
    ) -> str:

        context = "\n\n".join(context_blocks)

        return f"""
You are an expert technical AI assistant.

The user is asking a technical question.

{PromptEngineer.common_rules()}

SPECIAL INSTRUCTIONS:

- Preserve technical correctness.
- Explain technical concepts clearly.
- Simplify complex workflows naturally.
- Use concise examples only if useful.
- Avoid huge theory dumps.
- Avoid verbose explanations.

DOCUMENT CONTEXT:
{context}

QUESTION:
{question}

TECHNICAL EXPLANATION:
""".strip()

    # =========================================================
    # GENERAL PROMPT
    # =========================================================

    @staticmethod
    def build_general_prompt(
        question: str,
        context_blocks: List[str],
    ) -> str:

        context = "\n\n".join(context_blocks)

        return f"""
You are an advanced AI knowledge assistant.

{PromptEngineer.common_rules()}

SPECIAL INSTRUCTIONS:

- Answer naturally and professionally in 1-3 short paragraphs.
- Be direct and easy to read.

DOCUMENT CONTEXT:
{context}

QUESTION:
{question}

ANSWER (start directly, no preamble):
""".strip()

    # =========================================================
    # MAIN PROMPT SELECTOR
    # =========================================================

    @staticmethod
    def build_prompt(
        question: str,
        context_blocks: List[str],
    ) -> str:

        if not context_blocks:

            return (
                PromptEngineer
                .format_no_answer_response(
                    question
                )
            )

        question_type = (
            PromptEngineer
            .detect_question_type(
                question
            )
        )

        if question_type == "definition":

            return (
                PromptEngineer
                .build_definition_prompt(
                    question,
                    context_blocks,
                )
            )

        elif question_type == "how-to":

            return (
                PromptEngineer
                .build_how_to_prompt(
                    question,
                    context_blocks,
                )
            )

        elif question_type == "list":

            return (
                PromptEngineer
                .build_list_prompt(
                    question,
                    context_blocks,
                )
            )

        elif question_type == "comparison":

            return (
                PromptEngineer
                .build_comparison_prompt(
                    question,
                    context_blocks,
                )
            )

        elif question_type == "technical":

            return (
                PromptEngineer
                .build_technical_prompt(
                    question,
                    context_blocks,
                )
            )

        return (
            PromptEngineer
            .build_general_prompt(
                question,
                context_blocks,
            )
        )

    # =========================================================
    # RESPONSE CLEANING
    # =========================================================

    @staticmethod
    def clean_response(response: str) -> str:

        if not response:
            return response

        response = response.strip()

        artifacts = [
            r"^Answer:\s*",
            r"^Response:\s*",
            r"^AI Response:\s*",
            r"^FINAL ANSWER:\s*",
            r"^ANSWER \(start directly.*?\):\s*",
            r"^TECHNICAL EXPLANATION:\s*",
            r"^COMPARISON ANSWER:\s*",
            r"^STEP-BY-STEP ANSWER:\s*",
            r"^STRUCTURED ANSWER:\s*",
            r"^Here'?s my response:?\s*",
            r"^Here is (?:the |my )?(?:answer|response):?\s*",
            r"^Here'?s a rewritten response[^.]*\.?\s*",
            r"^This (?:answer|response) synthesizes[^.]*\.?\s*",
            r"\[Generated.*?\]",
        ]

        meta_line_patterns = [
            r"(?im)^.*synthesizes the provided documents.*\n?",
            r"(?im)^.*rewritten response.*\n?",
        ]

        for pattern in meta_line_patterns:
            response = re.sub(pattern, "", response)

        for pattern in artifacts:

            response = re.sub(
                pattern,
                "",
                response,
                flags=re.IGNORECASE,
            )

        response = re.sub(
            r"[^\x00-\x7F]+",
            " ",
            response,
        )

        response = re.sub(
            r"([!?.,])\1+",
            r"\1",
            response,
        )

        # Preserve paragraph breaks
        response = re.sub(
            r"\n{3,}",
            "\n\n",
            response,
        )

        # Clean up space within lines
        lines = response.split("\n")
        cleaned_lines = []

        for line in lines:
            # Normalize spaces within line
            line = re.sub(r"[ \t]+", " ", line)
            line = line.strip()

            # Only keep non-empty lines
            if line:
                cleaned_lines.append(line)

        # Reconstruct with paragraph awareness
        paragraphs = []
        current_para = []

        for line in cleaned_lines:
            # If line was empty (paragraph break)
            if not line:
                if current_para:
                    paragraphs.append(
                        " ".join(current_para)
                    )
                    current_para = []
            else:
                current_para.append(line)

        if current_para:
            paragraphs.append(
                " ".join(current_para)
            )

        # Remove duplicate paragraphs
        seen = set()
        deduped_paragraphs = []

        for para in paragraphs:
            normalized = (
                para.strip().lower()
            )

            if (
                normalized
                and normalized not in seen
            ):

                deduped_paragraphs.append(para)
                seen.add(normalized)

        response = "\n\n".join(
            deduped_paragraphs
        ).strip()

        # Remove incomplete sentence endings
        response = re.sub(
            r"(and|or|because|since|therefore)\s*$",
            "",
            response,
            flags=re.IGNORECASE,
        )

        bad_endings = [
            "thank you",
            "thanks",
            "hope this helps",
            "so there you have it",
            "let me know",
            "feel free to",
        ]

        for ending in bad_endings:

            if (
                response.lower().endswith(
                    ending
                )
            ):

                response = response[
                    : -len(ending)
                ].strip()

        paragraphs = response.split("\n\n")

        # Cap at 5 coherent paragraphs
        if len(paragraphs) > 5:

            response = "\n\n".join(
                paragraphs[:5]
            )

        # Ensure proper ending punctuation
        if (
            response
            and response[-1]
            not in ".!?"
        ):

            response += "."

        return response

    # =========================================================
    # NO ANSWER RESPONSE
    # =========================================================

    @staticmethod
    def format_no_answer_response(
        question: str,
    ) -> str:

        return (
            "I couldn't find information about that in your "
            "uploaded documents. Please ask about a topic that "
            "appears in the documents available to this assistant."
        )

    @staticmethod
    def direct_answer_reminder() -> str:
        return (
            "Rewrite as a direct expert answer only. "
            "Begin immediately with the substance. "
            "Do not mention documents, rewriting, synthesis, "
            "or say 'Here is' / 'Here's my response'."
        )

    # =========================================================
    # SOURCE EXTRACTION
    # =========================================================

    @staticmethod
    def extract_source_mention(
        response: str,
    ) -> str:

        source_pattern = (
            r"(?:Source|From|Reference):?\s*"
            r"([^,\n]+(?:\.pdf|\.docx|\.txt|\.md))[^\n]*"
        )

        match = re.search(
            source_pattern,
            response,
            re.IGNORECASE,
        )

        if match:

            return (
                match.group(1)
                .strip()
            )

        return ""

    # =========================================================
    # CONTEXT SYNTHESIS SIGNALS
    # =========================================================

    @staticmethod
    def build_context_synthesis_signal(
        context_blocks: List[str],
    ) -> str:
        """Build synthesis signals for multi-source context."""
        unique_sources = set()
        for block in context_blocks:
            # Extract source info from context
            match = re.search(
                r"DOCUMENT:\s*([^\n]+)",
                block,
            )
            if match:
                unique_sources.add(match.group(1).strip())

        if len(unique_sources) <= 1:
            return (
                "Focus on a coherent "
                "explanation from a single "
                "perspective."
            )

        return (
            "Synthesize information naturally "
            "from multiple sources without "
            "jarring transitions. "
            "Connect related concepts from "
            "different sections seamlessly."
        )

    @staticmethod
    def build_coherence_signal(
        context_blocks: List[str],
    ) -> str:
        """Build signals for answer coherence."""
        block_count = len(context_blocks)

        if block_count <= 1:
            return "Provide a complete, focused answer."

        return (
            "Structure the answer as 2-3 "
            "coherent paragraphs with natural "
            "transitions. Each paragraph should "
            "explore a distinct aspect while "
            "maintaining overall topic focus. "
            "Use transitional phrases to connect "
            "ideas naturally."
        )

    @staticmethod
    def build_continuation_signal(
        conversation_context: str | None,
    ) -> str:
        """Build signals for conversation continuity."""
        if (
            not conversation_context
            or len(conversation_context.split()) < 20
        ):
            return ""

        # Detect if this is a follow-up
        if "\n\nUser:" in conversation_context:
            return (
                "This is a follow-up question. "
                "Build on the previous context "
                "and avoid repeating information "
                "already covered. Reference prior "
                "concepts only when clarifying."
            )

        return ""