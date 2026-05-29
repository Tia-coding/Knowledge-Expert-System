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

from typing import List, Optional
import re


class PromptEngineer:
    """Prompt engineering utility for intelligent RAG responses."""

    # =========================================================
    # ANSWER TYPE DETECTION (dynamic, not topic-specific)
    # =========================================================

    @staticmethod
    def detect_answer_type(question: str) -> str:
        """Classify how the answer should be structured."""

        q = question.lower().strip()

        if re.search(r"\balgorithm\b", q) or "pseudocode" in q:
            return "algorithm"

        if any(
            phrase in q
            for phrase in (
                "difference between",
                "compare ",
                " vs ",
                " versus ",
                "differ from",
                "similarities and",
            )
        ):
            return "comparison"

        if any(
            word in q
            for word in ("advantage", "benefits", "pros", "merits")
        ):
            return "advantages"

        if any(
            word in q
            for word in ("disadvantage", "drawbacks", "cons", "limitations")
        ):
            return "disadvantages"

        if any(
            phrase in q
            for phrase in (
                "how to",
                "how do",
                "steps to",
                "procedure",
                "process for",
                "walk me through",
            )
        ) or re.search(r"\bsteps\b", q):
            return "procedure"

        if any(
            word in q
            for word in (
                "implementation",
                "implement",
                "write code",
                "program for",
                "source code",
            )
        ):
            return "implementation"

        if any(
            phrase in q
            for phrase in (
                "what is",
                "what are",
                "define",
                "meaning of",
                "explain what",
            )
        ):
            return "definition"

        if q.startswith("explain") or q.startswith("describe"):
            return "explanation"

        if any(
            word in q
            for word in ("list", "types of", "kinds of", "enumerate")
        ):
            return "list"

        return "general"

    @staticmethod
    def detect_question_type(question: str) -> str:
        """Backward-compatible alias for answer-type detection."""
        return PromptEngineer.detect_answer_type(question)

    @staticmethod
    def anti_copy_rules() -> str:
        return """
TUTORING & SYNTHESIS RULES:
- Read the retrieved chunks, understand them, then write a fresh explanation in your own words.
- Do NOT copy sentences or long phrases from the source text verbatim.
- Act like an academic tutor: clear, structured, and student-friendly.
- Answer ONLY the topic in the user's question; ignore unrelated concepts in the context.
- If a context block is off-topic, skip it entirely.
- Use short examples only when they clarify the concept.
"""

    @staticmethod
    def low_confidence_preamble(level: str = "limited") -> str:
        if level == "insufficient":
            return (
                "The uploaded documents do not contain enough information "
                "to answer this accurately.\n\n"
                "Here is the best grounded summary from what is available:\n\n"
            )
        return (
            "Based on the uploaded documents, the available information "
            "is limited.\n\n"
            "Here is the best grounded summary from what is available:\n\n"
        )

    @staticmethod
    def formatting_rules() -> str:
        return """
FORMATTING (required):
- Use plain text only. Do NOT use markdown: no **, no __, no #, no backticks.
- Write section titles as "Section Name:" on their own line (no bold).
- Omit any section entirely if the documents lack supporting information.
- Never leave empty sections, placeholders, or lines like "N/A" or "Not specified".
- Use numbered lists (1. 2. 3.) for steps; use hyphen bullets (- item) for characteristics.
- Complete every numbered step with real content; never output blank step numbers.
"""

    # =========================================================
    # COMMON RULES
    # =========================================================

    @staticmethod
    def format_conversation_history(
        conversation_history: Optional[List[dict]] = None,
        max_turns: int = 6,
    ) -> str:
        """Format prior turns for prompt injection (current question is separate)."""

        if not conversation_history:
            return ""

        # Each stored row is user+assistant; cap total message pairs.
        recent = conversation_history[-(max_turns * 2):]

        lines: list[str] = []
        for turn in recent:
            role = turn.get("role", "")
            content = (turn.get("content") or "").strip()
            if not content:
                continue

            label = "User" if role == "user" else "Assistant"
            if role == "assistant" and len(content) > 1200:
                content = content[:1200].strip() + "..."

            lines.append(f"{label}: {content}")

        if not lines:
            return ""

        return (
            "RECENT CONVERSATION (for follow-up context only — "
            "answer using document context below):\n"
            + "\n\n".join(lines)
        )

    @staticmethod
    def build_enrichment_signals(
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:
        """Combine synthesis, coherence, and continuation guidance."""

        signals = [
            "Use only context passages that directly relate to the current question.",
            PromptEngineer.build_context_synthesis_signal(context_blocks),
            PromptEngineer.build_coherence_signal(context_blocks),
            PromptEngineer.build_continuation_signal(conversation_history),
        ]

        return "\n".join(
            signal for signal in signals if signal
        )

    @staticmethod
    def _append_prompt_sections(
        base: str,
        context_blocks: List[str],
        question: str,
        conversation_history: Optional[List[dict]] = None,
    ) -> str:
        """Inject conversation memory and multi-chunk synthesis guidance."""

        history_block = PromptEngineer.format_conversation_history(
            conversation_history
        )
        enrichment = PromptEngineer.build_enrichment_signals(
            context_blocks,
            conversation_history,
        )

        sections = [base.strip()]

        if history_block:
            sections.append(history_block)

        if enrichment:
            sections.append(f"GUIDANCE:\n{enrichment}")

        sections.append(f"QUESTION:\n{question.strip()}")

        return "\n\n".join(sections)

    @staticmethod
    def common_rules() -> str:

        return f"""
IMPORTANT RULES:

1. Answer ONLY using the provided document context.
2. Never invent facts not supported by the context.
3. Ignore corrupted OCR text or unreadable symbols.
4. Start immediately with the answer — no preamble or meta commentary.
5. Do not mention documents, files, context, rewriting, or synthesis.
6. Preserve technical accuracy; use simple language where possible.
7. For follow-up questions, resolve pronouns using recent conversation.
8. If context is thin, give the best grounded summary you can without guessing.

{PromptEngineer.formatting_rules()}

{PromptEngineer.anti_copy_rules()}
"""

    # =========================================================
    # DEFINITION PROMPT
    # =========================================================

    @staticmethod
    def build_definition_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:

        context = "\n\n".join(context_blocks)

        base = f"""
You are an academic tutor.

{PromptEngineer.common_rules()}

FORMAT — include ONLY sections supported by the documents:

Definition:
(One clear sentence in your own words.)

Key Characteristics:
(- bullet per characteristic)

Example:
(Only if the documents provide an example.)

Applications:
(Only if the documents mention real uses.)

DOCUMENT CONTEXT:
{context}

Write the formatted answer now:
""".strip()

        return PromptEngineer._append_prompt_sections(
            base,
            context_blocks,
            question,
            conversation_history,
        )

    # =========================================================
    # HOW-TO PROMPT
    # =========================================================

    @staticmethod
    def build_procedure_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:

        context = "\n\n".join(context_blocks)

        base = f"""
You are an academic tutor explaining a procedure.

{PromptEngineer.common_rules()}

FORMAT — include ONLY sections supported by the documents:

Objective:
(One sentence goal.)

Steps:
1. (First step in your own words)
2. (Continue with complete steps only)
...

Important Notes:
(Optional caveats if in context.)

Example:
(Optional walkthrough if in context.)

DOCUMENT CONTEXT:
{context}

Write the formatted answer now:
""".strip()

        return PromptEngineer._append_prompt_sections(
            base,
            context_blocks,
            question,
            conversation_history,
        )

    @staticmethod
    def build_how_to_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:
        return PromptEngineer.build_procedure_prompt(
            question,
            context_blocks,
            conversation_history,
        )

    @staticmethod
    def build_algorithm_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:

        context = "\n\n".join(context_blocks)

        base = f"""
You are an academic tutor explaining an algorithm from the documents.

{PromptEngineer.common_rules()}

FORMAT — include ONLY sections supported by the documents:

Algorithm:
(Name of the algorithm)

Steps:
1. (Complete first step)
2. (Complete second step)
(Continue numbering; every step must have content.)

Pseudo Code:
(Only if pseudocode or code appears in the documents.)

Time Complexity:
(Only if stated in the documents.)

Space Complexity:
(Only if stated in the documents.)

Explanation:
(Short intuitive summary in your own words.)

DOCUMENT CONTEXT:
{context}

Write the formatted answer now:
""".strip()

        return PromptEngineer._append_prompt_sections(
            base,
            context_blocks,
            question,
            conversation_history,
        )

    # =========================================================
    # LIST PROMPT
    # =========================================================

    @staticmethod
    def build_list_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:

        context = "\n\n".join(context_blocks)

        base = f"""
You are an advanced AI assistant.

The user is asking for a structured list response.

{PromptEngineer.common_rules()}

SPECIAL INSTRUCTIONS:

- Use concise bullet points for each type or item.
- One short line per bullet; no repetition.
- Do not add an introduction sentence before the list.

DOCUMENT CONTEXT:
{context}

ANSWER (start directly, no preamble):
""".strip()

        return PromptEngineer._append_prompt_sections(
            base,
            context_blocks,
            question,
            conversation_history,
        )

    # =========================================================
    # COMPARISON PROMPT
    # =========================================================

    @staticmethod
    def build_comparison_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:

        context = "\n\n".join(context_blocks)

        base = f"""
You are an academic tutor comparing concepts.

{PromptEngineer.common_rules()}

FORMAT:

Comparison Table:
| Feature | Item A | Item B |
(3-6 rows; use real names from the question instead of Item A/B when possible)

Summary:
(2-3 sentences in your own words.)

DOCUMENT CONTEXT:
{context}

Write the formatted answer now:
""".strip()

        return PromptEngineer._append_prompt_sections(
            base,
            context_blocks,
            question,
            conversation_history,
        )

    # =========================================================
    # TECHNICAL PROMPT
    # =========================================================

    @staticmethod
    def build_implementation_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:

        context = "\n\n".join(context_blocks)

        base = f"""
You are an academic tutor explaining an implementation.

{PromptEngineer.common_rules()}

FORMAT:

Overview:
(Brief summary in your own words.)

Approach:
(Numbered steps or bullets for the implementation logic.)

Notes:
(Constraints, pitfalls, or requirements from context only.)

DOCUMENT CONTEXT:
{context}

Write the formatted answer now:
""".strip()

        return PromptEngineer._append_prompt_sections(
            base,
            context_blocks,
            question,
            conversation_history,
        )

    @staticmethod
    def build_explanation_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:

        context = "\n\n".join(context_blocks)

        base = f"""
You are an academic tutor giving a clear explanation.

{PromptEngineer.common_rules()}

FORMAT:

Explanation:
(2-3 short paragraphs in your own words.)

Key Points:
- (3-5 concise bullets)

DOCUMENT CONTEXT:
{context}

Write the formatted answer now:
""".strip()

        return PromptEngineer._append_prompt_sections(
            base,
            context_blocks,
            question,
            conversation_history,
        )

    @staticmethod
    def build_advantages_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:

        context = "\n\n".join(context_blocks)

        base = f"""
You are an academic tutor.

{PromptEngineer.common_rules()}

FORMAT:

Advantages:
- (Concise bullets in your own words)

Summary:
(One short closing sentence.)

DOCUMENT CONTEXT:
{context}

Write the formatted answer now:
""".strip()

        return PromptEngineer._append_prompt_sections(
            base,
            context_blocks,
            question,
            conversation_history,
        )

    @staticmethod
    def build_disadvantages_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:

        context = "\n\n".join(context_blocks)

        base = f"""
You are an academic tutor.

{PromptEngineer.common_rules()}

FORMAT:

Disadvantages:
- (Concise bullets in your own words)

Summary:
(One short closing sentence.)

DOCUMENT CONTEXT:
{context}

Write the formatted answer now:
""".strip()

        return PromptEngineer._append_prompt_sections(
            base,
            context_blocks,
            question,
            conversation_history,
        )

    @staticmethod
    def build_technical_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:
        return PromptEngineer.build_explanation_prompt(
            question,
            context_blocks,
            conversation_history,
        )

    # =========================================================
    # GENERAL PROMPT
    # =========================================================

    @staticmethod
    def build_general_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:

        context = "\n\n".join(context_blocks)

        base = f"""
You are an advanced AI knowledge assistant.

{PromptEngineer.common_rules()}

SPECIAL INSTRUCTIONS:

- Answer naturally and professionally in 1-3 short paragraphs.
- Be direct and easy to read.

DOCUMENT CONTEXT:
{context}

ANSWER (start directly, no preamble):
""".strip()

        return PromptEngineer._append_prompt_sections(
            base,
            context_blocks,
            question,
            conversation_history,
        )

    # =========================================================
    # MAIN PROMPT SELECTOR
    # =========================================================

    @staticmethod
    def build_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:

        if not context_blocks:

            return (
                PromptEngineer
                .format_no_answer_response(
                    question
                )
            )

        answer_type = PromptEngineer.detect_answer_type(question)

        builders = {
            "definition": PromptEngineer.build_definition_prompt,
            "algorithm": PromptEngineer.build_algorithm_prompt,
            "procedure": PromptEngineer.build_procedure_prompt,
            "comparison": PromptEngineer.build_comparison_prompt,
            "advantages": PromptEngineer.build_advantages_prompt,
            "disadvantages": PromptEngineer.build_disadvantages_prompt,
            "implementation": PromptEngineer.build_implementation_prompt,
            "explanation": PromptEngineer.build_explanation_prompt,
            "list": PromptEngineer.build_list_prompt,
            "general": PromptEngineer.build_general_prompt,
        }

        builder = builders.get(
            answer_type,
            PromptEngineer.build_general_prompt,
        )

        return builder(
            question,
            context_blocks,
            conversation_history,
        )

    # =========================================================
    # RESPONSE CLEANING & PRESENTATION
    # =========================================================

    @staticmethod
    def strip_markdown(text: str) -> str:
        """Remove common markdown markers from model output."""

        if not text:
            return text

        text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
        text = re.sub(r"__(.+?)__", r"\1", text)
        text = re.sub(r"\*(.+?)\*", r"\1", text)
        text = re.sub(r"`(.+?)`", r"\1", text)
        text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
        return text

    @staticmethod
    def _is_placeholder_content(content: str) -> bool:
        normalized = re.sub(
            r"\s+",
            " ",
            (content or "").strip().lower(),
        )
        normalized = normalized.rstrip(".,;:")

        if not normalized:
            return True

        placeholders = (
            "n/a",
            "na",
            "none",
            "not available",
            "not specified",
            "not specified in the documents",
            "not mentioned",
            "no information",
            "not provided",
            "-",
            "...",
        )

        if normalized in placeholders:
            return True

        return normalized.startswith(
            (
                "not specified",
                "not available",
                "no information",
            )
        )

    @staticmethod
    def remove_empty_sections(text: str) -> str:
        """Drop section headers with no substantive body."""

        if not text:
            return text

        lines = text.split("\n")
        blocks: list[tuple[str | None, list[str]]] = []
        current_header: str | None = None
        current_body: list[str] = []
        preamble: list[str] = []

        header_pattern = re.compile(
            r"^([A-Za-z][A-Za-z0-9 /&]+):\s*(.*)$",
        )

        def flush_block() -> None:
            nonlocal current_header, current_body
            if current_header is not None:
                blocks.append((current_header, current_body))
            elif current_body:
                preamble.extend(current_body)
            current_header = None
            current_body = []

        for line in lines:
            match = header_pattern.match(line.strip())
            if match and len(match.group(1)) <= 45:
                flush_block()
                current_header = match.group(1).strip()
                rest = match.group(2).strip()
                current_body = [rest] if rest else []
            else:
                if current_header is not None:
                    current_body.append(line)
                else:
                    preamble.append(line)

        flush_block()

        output: list[str] = []

        if preamble:
            preamble_text = "\n".join(preamble).strip()
            if preamble_text:
                output.append(preamble_text)

        for header, body_lines in blocks:
            body = "\n".join(body_lines).strip()
            if (
                PromptEngineer._is_placeholder_content(body)
                or not body
            ):
                continue
            output.append(f"{header}:\n{body}")

        return "\n\n".join(
            block for block in output if block.strip()
        ).strip()

    # Section titles that must not appear without body content
    _SECTION_TITLES = {
        "definition",
        "key characteristics",
        "example",
        "applications",
        "algorithm",
        "steps",
        "pseudo code",
        "pseudocode",
        "time complexity",
        "space complexity",
        "explanation",
        "objective",
        "important notes",
        "notes",
        "note",
        "comparison table",
        "summary",
        "overview",
        "approach",
        "advantages",
        "disadvantages",
        "key points",
        "section",
        "context",
        "reference",
    }

    @staticmethod
    def _is_section_title_line(line: str) -> str | None:
        stripped = line.strip()
        if not stripped:
            return None

        colon_match = re.match(
            r"^([A-Za-z][A-Za-z0-9 /&]+):\s*(.*)$",
            stripped,
        )
        if colon_match and len(colon_match.group(1)) <= 45:
            title = colon_match.group(1).strip()
            rest = colon_match.group(2).strip()
            if rest:
                return None
            if title.lower() in PromptEngineer._SECTION_TITLES:
                return title
            return title

        plain = stripped.rstrip(":").strip()
        if plain.lower() in PromptEngineer._SECTION_TITLES:
            return plain

        return None

    @staticmethod
    def remove_filler_text(text: str) -> str:
        """Strip transition fluff and meaningless standalone labels."""

        if not text:
            return text

        filler_prefixes = (
            r"to illustrate,?\s*",
            r"however,?\s*",
            r"additionally,?\s*",
            r"consequently,?\s*",
            r"nevertheless,?\s*",
            r"based on (the )?(provided )?(document )?context,?\s*",
            r"according to (the )?(uploaded )?documents?,?\s*",
            r"from the (provided )?context,?\s*",
        )

        junk_lines = {
            "section",
            "context",
            "reference",
            "note",
            "notes",
        }

        cleaned: list[str] = []

        for line in text.split("\n"):
            stripped = line.strip()
            if not stripped:
                cleaned.append("")
                continue

            lower = stripped.lower().rstrip(":")

            if lower in junk_lines:
                continue

            if PromptEngineer._is_section_title_line(stripped):
                cleaned.append(stripped)
                continue

            updated = stripped
            for pattern in filler_prefixes:
                updated = re.sub(
                    pattern,
                    "",
                    updated,
                    flags=re.IGNORECASE,
                ).strip()

            if updated:
                cleaned.append(updated)

        return "\n".join(cleaned)

    @staticmethod
    def remove_standalone_empty_sections(text: str) -> str:
        """Remove section headers not followed by substantive content."""

        if not text:
            return text

        lines = text.split("\n")
        output: list[str] = []
        index = 0

        while index < len(lines):
            line = lines[index]
            title = PromptEngineer._is_section_title_line(line)

            if not title:
                output.append(line)
                index += 1
                continue

            body_lines: list[str] = []
            cursor = index + 1

            while cursor < len(lines):
                peek = lines[cursor]
                if not peek.strip():
                    if body_lines:
                        break
                    cursor += 1
                    continue

                if PromptEngineer._is_section_title_line(peek):
                    break

                body_lines.append(peek)
                cursor += 1

            body = "\n".join(body_lines).strip()

            if body and not PromptEngineer._is_placeholder_content(
                body
            ):
                colon_match = re.match(
                    r"^([A-Za-z][A-Za-z0-9 /&]+):\s*",
                    line.strip(),
                )
                if colon_match:
                    output.append(line)
                else:
                    output.append(f"{title}:")
                output.extend(body_lines)
                if cursor < len(lines) and not lines[cursor].strip():
                    output.append("")

            index = cursor

        return "\n".join(output)

    @staticmethod
    def normalize_section_bullets(text: str) -> str:
        """Ensure characteristic-style lines use bullet prefixes."""

        if not text:
            return text

        bullet_sections = {
            "key characteristics",
            "advantages",
            "disadvantages",
            "key points",
            "important notes",
        }

        lines = text.split("\n")
        output: list[str] = []
        current_section: str | None = None

        for line in lines:
            title = PromptEngineer._is_section_title_line(line)
            if title:
                current_section = title.lower()
                output.append(line)
                continue

            stripped = line.strip()
            if (
                current_section in bullet_sections
                and stripped
                and not re.match(r"^(\d+\.|[-•*])\s+", stripped)
                and not stripped.startswith("|")
                and len(stripped.split()) <= 24
            ):
                output.append(f"- {stripped}")
                continue

            output.append(line)

        return "\n".join(output)

    @staticmethod
    def renumber_ordered_steps(text: str) -> str:
        """Renumber step lists after empty items were removed."""

        if not text:
            return text

        lines = text.split("\n")
        output: list[str] = []
        counter = 0
        in_steps = False

        for line in lines:
            title = PromptEngineer._is_section_title_line(line)
            if title:
                in_steps = title.lower() == "steps"
                counter = 0
                output.append(line)
                continue

            match = re.match(r"^\d+\.\s+(.+)$", line.strip())
            if in_steps and match and match.group(1).strip():
                counter += 1
                output.append(f"{counter}. {match.group(1).strip()}")
                continue

            if match:
                counter = 0

            output.append(line)

        return "\n".join(output)

    @staticmethod
    def polish_answer(text: str) -> str:
        """Final presentation pass before the answer is shown to the user."""

        if not text:
            return text

        text = PromptEngineer.strip_markdown(text)
        text = PromptEngineer.remove_filler_text(text)
        text = PromptEngineer.remove_standalone_empty_sections(text)
        text = PromptEngineer.fix_incomplete_steps(text)
        text = PromptEngineer.normalize_section_bullets(text)
        text = PromptEngineer.remove_empty_sections(text)
        text = PromptEngineer.renumber_ordered_steps(text)

        # Collapse excessive blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Remove duplicate non-empty lines
        seen: set[str] = set()
        deduped: list[str] = []

        for line in text.split("\n"):
            key = line.strip().lower()
            if key and key in seen:
                continue
            if key:
                seen.add(key)
            deduped.append(line)

        return "\n".join(deduped).strip()

    @staticmethod
    def fix_incomplete_steps(text: str) -> str:
        """Remove empty numbered list items."""

        if not text:
            return text

        cleaned: list[str] = []

        for line in text.split("\n"):
            stripped = line.strip()
            if re.match(r"^\d+\.\s*$", stripped):
                continue
            if re.match(r"^\d+\.\s*\.{2,}\s*$", stripped):
                continue
            cleaned.append(line)

        return "\n".join(cleaned)

    @staticmethod
    def clean_response(
        response: str,
        question: str = "",
    ) -> str:

        if not response:
            return response

        response = response.strip()
        response = PromptEngineer.strip_markdown(response)

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

        structured_line = re.compile(
            r"^(\d+\.|[-•*]|\||[A-Z][a-zA-Z ]+:|#{1,3}\s)",
        )

        for line in lines:
            line = re.sub(r"[ \t]+", " ", line)
            line = line.strip()

            if line:
                cleaned_lines.append(line)

        paragraphs = []
        current_para = []

        for line in cleaned_lines:
            if structured_line.match(line):
                if current_para:
                    paragraphs.append("\n".join(current_para))
                    current_para = []
                paragraphs.append(line)
            else:
                current_para.append(line)

        if current_para:
            paragraphs.append("\n".join(current_para))

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

        # Cap unstructured essays only; keep full structured answers intact.
        has_sections = bool(
            re.search(
                r"(?m)^[A-Z][A-Za-z0-9 /&]+:\s*$",
                response,
            )
        )

        if not has_sections:
            paragraphs = response.split("\n\n")
            if len(paragraphs) > 6:
                response = "\n\n".join(paragraphs[:6])

        if (
            response
            and response[-1] not in ".!?"
            and not response.endswith(":")
        ):
            response += "."

        return PromptEngineer.polish_answer(response.strip())

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
            "Rewrite in your own words using the required plain-text format. "
            "No markdown. No empty sections. "
            "Do not copy source sentences. "
            "Complete every numbered step. "
            "Begin immediately with the formatted sections."
        )

    @staticmethod
    def synthesis_reminder() -> str:
        return (
            "Read the context, understand it, then produce a fresh tutor-style "
            "explanation. No verbatim copying from the source text."
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
            "Synthesize only information relevant to the user's question. "
            "Ignore off-topic sections in the context. "
            "Connect related ideas smoothly in your own words."
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
        conversation_history: Optional[List[dict]] = None,
    ) -> str:
        """Build signals for conversation continuity."""
        if not conversation_history:
            return ""

        if len(conversation_history) < 2:
            return ""

        return (
            "This is a follow-up question. "
            "Resolve pronouns and references (e.g. 'them', 'it', 'both') "
            "using the recent conversation. "
            "Build on prior answers without repeating information already covered."
        )