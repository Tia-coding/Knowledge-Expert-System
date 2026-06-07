from typing import List, Optional
import re


class PromptEngineer:
    """Prompt engineering utility for intelligent RAG responses with professional Markdown formatting."""

    # =========================================================
    # ANSWER TYPE DETECTION (dynamic, not topic-specific)
    # =========================================================

    @staticmethod
    def detect_answer_type(question: str) -> str:
        """Classify answer structure: structured only when the question needs it."""
        q = question.lower().strip()

        # Explicit algorithm requests → structured
        if re.search(r"\balgorithm\b", q) or "pseudocode" in q:
            return "algorithm"

        # Comparisons → table format
        if any(
            phrase in q
            for phrase in (
                "difference between",
                "compare",
                "comparison",
                " vs ",
                " versus ",
                "differ from",
                "similarities and",
                "tabular form",
                "table",
            )
        ):
            return "comparison"

        # Clear procedures → structured steps
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

        # List-style requests → light structure
        if (
            re.search(
                r"\b(types|kinds|categories|classifications)\s+of\b",
                q,
            )
            or re.search(
                r"^(please\s+)?(list|enumerate)\b",
                q,
            )
            or re.search(
                r"\b(give|show|provide)\s+(me\s+)?(a\s+)?list\s+of\b",
                q,
            )
        ):
            return "list"

        return "conversational"

    @staticmethod
    def answer_depth(question: str) -> str:
        """Infer how much detail the user is asking for, without topic rules."""
        q = question.lower().strip()
        words = q.split()

        if any(
            phrase in q
            for phrase in (
                "explain in detail",
                "describe in detail",
                "in detail",
                "elaborate",
                "comprehensive",
                "deeply explain",
                "tell me more",
                "more detail",
            )
        ):
            return "detailed"

        if (
            re.match(r"^(what is|what are|define|definition of)\b", q)
            or len(words) <= 5
        ):
            return "brief"

        return "normal"

    @staticmethod
    def length_guidance(question: str) -> str:
        """Give the LLM a strict but intent-sensitive length target."""
        answer_type = PromptEngineer.detect_answer_type(question)
        depth = PromptEngineer.answer_depth(question)

        if answer_type == "comparison":
            return (
                "Length target: Return only the comparison table. "
                "Do not generate bullet points, notes, summaries, or additional sections."
            )

        if answer_type == "list":
            return (
                "Length target: List only the supported items using Markdown bullet points. "
                "Add one short explanation per item when the context supports it."
            )

        if depth == "detailed":
            return (
                "Length target: Provide a comprehensive explanation. "
                "Cover all relevant information from the retrieved knowledge. "
                "Combine related information into coherent sections. "
                "Avoid copying document structure directly. "
                "Use headings and bullet points only when they improve readability."
            )

        if depth == "brief":
            return (
                "Length target: One short Markdown header plus 1-2 natural paragraphs. "
                "Give a clear definition and include only useful supported details."
            )

        return (
            "Length target: Answer only what the question asks. "
            "Provide additional sections such as characteristics, types, advantages, "
            "disadvantages, applications, examples, or implementation details only "
            "when they are relevant to the user's request."
        )

    @staticmethod
    def detect_question_type(question: str) -> str:
        """Backward-compatible alias for answer-type detection."""
        return PromptEngineer.detect_answer_type(question)

    @staticmethod
    def grounding_rules() -> str:
        return """
DOCUMENT GROUNDING:
* Use only information supported by the retrieved document context.
* Never invent facts or add unsupported information.
* Do not include chapter numbers, section numbers, page numbers, figure references, or document references in the answer body text.
* Never include raw placeholder links like 'https://example.com' or text brackets like '[DOCUMENT GROUNDING]'.
"""

    @staticmethod
    def anti_copy_rules() -> str:
        return """
TUTORING & SYNTHESIS RULES:

* Answer the user's question directly with educational clarity.
* Focus purely on the topic requested.
* Explain concepts clearly in your own words while preserving technical accuracy.
* Short technical definitions or exact values may be used directly when accuracy requires it.
* Do not copy document sections verbatim.
* Synthesize information from multiple retrieved passages.
* Do not reproduce source headings exactly.
* Remove document formatting artifacts before answering.
* Convert raw notes into natural explanations.
* When a retrieved passage begins mid-sentence, rewrite it into a complete grammatical sentence.
* Ensure every sentence starts with a capital letter.
* Do not copy fragmented text directly from retrieved passages.
"""

    @staticmethod
    def low_confidence_preamble(level: str = "limited") -> str:
        if level == "insufficient":
            return (
                "I could not find sufficient information about this topic "
                "in the uploaded documents."
            )
        return ""

    @staticmethod
    def formatting_rules_conversational() -> str:
        return """
FORMATTING RULES:

- Use Markdown headings when useful.
- Use bullet points for key details.
- Keep paragraphs short and readable.
- Highlight important terms using bold text.
- Avoid unnecessary tables.
"""

    @staticmethod
    def formatting_rules_structured() -> str:
        return """
FORMATTING (STRUCTURED STYLE):
- Use bullet points for comparisons unless the user explicitly requests a table.
- Use ordered lists (1. Step one) for sequential workflows, processes, or algorithms.
- Use code blocks (```python ... ``` or similar languages) for any technical code blocks or pseudocode snippets.
- Ensure all markdown elements are complete and well-formed.
"""

    @staticmethod
    def formatting_rules() -> str:
        return PromptEngineer.formatting_rules_conversational()

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
            "RECENT CONVERSATION (For context tracking only — rely primarily on document content):\n"
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
        return "\n".join(signal for signal in signals if signal)

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

        sections.append(
            "PRIORITY:\n"
            "Answer the CURRENT QUESTION below. "
            "Use conversation history only to clarify follow-ups."
        )
        sections.append(f"CURRENT QUESTION:\n{question.strip()}")

        return "\n\n".join(sections)

    @staticmethod
    def common_rules(conversational: bool = True) -> str:
        return f"""
IMPORTANT SYSTEM CONSTRAINTS:

1. Answer directly using only retrieved document content.
2. Never invent facts.
3. If and only if no relevant information exists in the retrieved context,
respond exactly:
"The requested information was not found in the uploaded documents."
4. Preserve technical accuracy.
5. Use clean Markdown formatting.
6. Keep answers focused on the question.
7. Do not include greetings or conversational filler.
8. Sources are displayed separately by the system; do not mention page numbers or document names inside the answer body.
9. Never mention:
   - document context
   - provided context
   - uploaded documents
   - source material
   inside the answer body.
10. Do not use phrases such as:
    - According to the definition
    - In summary
    - It can be understood that
    - This means that
unless they are necessary for clarity.
11. Never output raw markdown examples, document fragments,
    OCR artifacts, code snippets, or formatting remnants
    unless the user explicitly requests them.

12. Convert extracted content into natural language explanations.


- When the user explicitly requests a table, generate a valid Markdown table with:
  - a header row
  - a separator row
  - at least one data row

- Never use H1 (# Heading).
- Use H2 (##) or H3 (###) headings only.
- Use bullet points for comparisons by default.
- Generate markdown tables only when the user explicitly requests a table.

{PromptEngineer.grounding_rules()}
{PromptEngineer.anti_copy_rules()}
"""

    @staticmethod
    def build_conversational_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:
        context = "\n\n".join(context_blocks)

        base = f"""
    You are an intelligent document-grounded AI assistant.

    Answer using ONLY the retrieved document context.

    If the answer cannot be supported by the retrieved context, respond exactly:
    "The requested information was not found in the uploaded documents."

    {PromptEngineer.common_rules(conversational=True)}

    ANSWER STYLE:

- Adapt the structure naturally to the user's question.
- Use clear markdown formatting.
- When using a section title, always generate a valid Markdown heading using ##.
- Never output plain text titles without Markdown heading syntax.
- Use bullet points for collections, classifications, advantages, disadvantages, features, or comparisons.
- Choose concise topic-based section titles only when necessary.
- Avoid creating unnecessary headings for short answers.
- Avoid generic headings such as "Answer", "List", "Details", or "Differences".
- Do not generate markdown tables unless explicitly requested by the user.


    QUESTION INTENT RULES:

Definition Questions:
- Give a direct definition first.
- Provide a brief explanation.
- Do not include code, pseudocode, algorithms, implementation details, or lengthy examples unless explicitly requested.

Explanation Questions:
- Provide a detailed explanation.
- Include structure, working, characteristics, types, examples, advantages, disadvantages, and applications when supported by the documents.

Comparison Questions:
- Always use a markdown comparison table when enough information exists.
- The first column must be "Feature".
- The remaining columns must contain the compared concepts.


Do NOT add generic statements such as:
- The information was found in the uploaded documents.
- The requested information was found in the context.
- Based on the uploaded documents.


    GENERAL RULES:

    * Answer the user's question directly.
    * Use clear Markdown formatting.
    * Use headings only when they improve readability.
    * Prefer natural explanations over rigid templates.
    * Avoid repeating information.
    * Do not echo the user's question.
    * Do not mention document names, page numbers, chapters, or references.
    * Keep simple questions short.
    * Provide more detail only when the question requires it.

    DEFINITION RULES:

    - For questions beginning with "What is", "What are", "Define", or "Definition of":
    * Start with a direct definition.
    * Keep the first explanation concise.
    * Do not automatically include types, advantages, disadvantages, applications,
        examples, implementation details, or comparisons unless requested.
    * Provide only the definition and a brief explanation.
    * Do not include algorithms, pseudocode, source code, implementation examples, or detailed procedures unless explicitly requested.
    * Do not include code snippets for "What is", "Define", or "Meaning of" questions.

    RETRIEVED KNOWLEDGE:
    {context}

    {PromptEngineer.length_guidance(question)}

    Generate the answer following the instructions above.
    """.strip()

        return PromptEngineer._append_prompt_sections(
            base,
            context_blocks,
            question,
            conversation_history,
        )
    

    @staticmethod
    def build_definition_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:
        return PromptEngineer.build_conversational_prompt(
            question, context_blocks, conversation_history
        )

    # =========================================================
    # HOW-TO / PROCEDURE PROMPT
    # =========================================================

    @staticmethod
    def build_procedure_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:
        context = "\n\n".join(context_blocks)

        base = f"""
You are an intelligent document-grounded AI assistant.{PromptEngineer.common_rules(conversational=False)}

PROCEDURE ANSWERING RULES:
* Present steps as a numbered list.
* Add short explanations where necessary.
* Keep steps concise and easy to follow.
* Put step titles in bold (e.g., "1. **Initialize System**: ...").
* Keep things highly structural, functional, and organized.

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
            question, context_blocks, conversation_history
        )

    @staticmethod
    def build_algorithm_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:
        context = "\n\n".join(context_blocks)

        base = f"""
You are an intelligent document-grounded AI assistant.{PromptEngineer.common_rules(conversational=False)}

ALGORITHM ANSWERING RULES:
* Use explicit code markdown blocks (e.g., ```python) to display structured pseudocode or algorithmic implementations.
* List operational bounds, parameters, or time/space complex metrics using clear Markdown bullet items.

DOCUMENT CONTEXT:
{context}

Write the formatted markdown answer now:
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
You are an advanced AI assistant providing a clean structured list.
{PromptEngineer.common_rules(conversational=False)}

LIST ANSWERING RULES:

* Present each item as a bullet point.
* Add a short explanation when supported by the retrieved knowledge.
* Do not introduce unsupported items.
* Avoid repeating information across bullets.
* Keep each bullet concise.
* Do not add introductory paragraphs unless necessary.
* Organize the list using a meaningful title when helpful.
* Avoid generic headings.

For list or types questions:

- Return only the requested list and brief explanations.
- Do not automatically continue into detailed subsections.
- Do not expand each item into separate sections unless explicitly requested.
- Do not add source citations inside the answer body.
- Do not generate sections such as:
  - References
  - Sources
  - Notes
  - Additional Information
- End the answer after the final list item.


DOCUMENT CONTEXT:
{context}

ANSWER:
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
You are an intelligent document-grounded AI assistant.
{PromptEngineer.common_rules(conversational=False)}

COMPARISON RULES:

- If the user requests a table, tabular form, comparison table, or markdown table:
  * Return a valid GitHub-Flavored Markdown table.
  * Use one header row.
  * Use one separator row.
  * Ensure every row has the same number of columns.
  * Do not add blank lines inside the table.

- Otherwise:
  * Present differences as bullet points.
  * Each bullet should describe one difference.
  * Avoid long paragraphs.



For comparison questions:

- Generate ONLY a markdown table.
- The first column must be "Feature".
- The remaining columns must be the compared concepts.
- Include all comparison points inside the table.
- Do NOT generate sections such as:
  - Characteristics
  - Features
  - Additional Notes
  - Summary
  - Conclusion
- Do NOT generate bullet points outside the table.
- End the answer immediately after the table.


Never generate:
- Note
- Notes
- Additional Information
- Remarks
- Conclusion

unless the user explicitly requests them.

COMPARISON OUTPUT RULES:

- Return exactly one markdown table.
- The response must begin with the table header.
- The response must end at the last table row.
- Do not generate:
  - Notes
  - Conclusions
  - Summaries
  - Characteristics
  - Additional Information
  - Remarks
  - Explanatory paragraphs
  - Bullet points

Any content outside the table is invalid.


IMPORTANT:

Return ONLY a markdown table.

The response must start with:

| Feature |

and must end at the last row of the table.

Do not write any text before or after the table.

COMPARISON FORMAT:

When comparing two or more concepts, generate a markdown table.

The first column must be named Feature.

The remaining columns must use the actual concepts being compared from the user's question.

Each subsequent row must describe one comparison criterion.

Do not create tables with only two columns unless the source information genuinely contains only two fields.

STRICT OUTPUT RULES:

- Output ONLY a markdown table.
- The first character of the response must be "|".
- Do not write introductions.
- Do not write explanations.
- Do not write notes.
- Do not write conclusions.
- Do not write "Here is the markdown table".
- Do not write any text before or after the table.

DOCUMENT CONTEXT:
{context}

Write the formatted markdown answer now:
""".strip()

        return PromptEngineer._append_prompt_sections(
            base,
            context_blocks,
            question,
            conversation_history,
        )

    # =========================================================
    # TECHNICAL PROMPTS & ALIASES
    # =========================================================

    @staticmethod
    def build_implementation_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:
        context = "\n\n".join(context_blocks)
        base = f"""
You are an intelligent document-grounded AI assistant.
{PromptEngineer.common_rules(conversational=False)}

DOCUMENT CONTEXT:
{context}

Write the formatted markdown answer now:
""".strip()
        return PromptEngineer._append_prompt_sections(
            base, context_blocks, question, conversation_history
        )

    @staticmethod
    def build_explanation_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:
        return PromptEngineer.build_conversational_prompt(
            question, context_blocks, conversation_history
        )

    @staticmethod
    def build_advantages_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:
        return PromptEngineer.build_conversational_prompt(
            question, context_blocks, conversation_history
        )

    @staticmethod
    def build_disadvantages_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:
        return PromptEngineer.build_conversational_prompt(
            question, context_blocks, conversation_history
        )

    @staticmethod
    def build_technical_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:
        return PromptEngineer.build_conversational_prompt(
            question, context_blocks, conversation_history
        )

    @staticmethod
    def build_general_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:
        return PromptEngineer.build_conversational_prompt(
            question, context_blocks, conversation_history
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
            return PromptEngineer.format_no_answer_response(question)

        q = question.lower().strip()
        
        # PRIORITY RULE: If the user is explicitly asking for a definition, force the brief conversational prompt
        

        answer_type = PromptEngineer.detect_answer_type(question)

        builders = {
            "conversational": PromptEngineer.build_conversational_prompt,
            "algorithm": PromptEngineer.build_algorithm_prompt,
            "procedure": PromptEngineer.build_procedure_prompt,
            "comparison": PromptEngineer.build_comparison_prompt,
            "list": PromptEngineer.build_list_prompt,
        }

        builder = builders.get(answer_type, PromptEngineer.build_general_prompt)
        return builder(question, context_blocks, conversation_history)

    # =========================================================
    # CLEANING AND POST-PROCESSING (REFACTORED TO PRESERVE MARKDOWN)
    # =========================================================

    @staticmethod
    def strip_markdown(text: str) -> str:
        """DEPRECATED DESTRUCTIVE STRIPPER - Preserves formatting markup now."""
        # We return text unmodified here to prevent dropping critical bolding,
        # lists, tables, and headers required by our frontend.
        return text

    @staticmethod
    def polish_answer(text: str) -> str:
        """Alias method wrapper to ensure smooth backward-compatibility integration across components."""
        return PromptEngineer.clean_response(text)

    @staticmethod
    def _is_placeholder_content(content: str) -> bool:
        normalized = re.sub(
            r"\s+", " ", (content or "").strip().lower()
        ).rstrip(".,;:")
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
        return normalized in placeholders or normalized.startswith(
            ("not specified", "not available", "no information")
        )

    @staticmethod
    def remove_filler_text(text: str) -> str:
        """Strip transition fluff while retaining structural content."""
        if not text:
            return text

        filler_prefixes = (
            r"consequently,?\s*",
            r"nevertheless,?\s*",
            r"historically speaking,?\s*",
            r"in essence,?\s*",
            r"fundamentally,?\s*",
            r"generally speaking,?\s*",
            r"based on (the )?(provided )?(document )?context,?\s*",
            r"according to (the )?(uploaded )?documents?,?\s*",
            r"from the (provided )?context,?\s*",
        )

        cleaned: list[str] = []
        for line in text.split("\n"):
            updated = line.strip()
            # Don't destroy Markdown tables or formatting lines
            if updated.startswith("|") or updated.startswith("#"):
                cleaned.append(line)
                continue

            for pattern in filler_prefixes:
                updated = re.sub(
                    pattern, "", updated, flags=re.IGNORECASE
                ).strip()

            cleaned.append(updated if updated else line.strip())

        return "\n".join(cleaned)

    @staticmethod
    def clean_response(response: str, question: str = "") -> str:
        """Cleans structural output artifacts without destroying Markdown elements."""
        if not response:
            return response

        response = response.strip()

        # Handle explicit escape characters safely
        response = response.replace("\\n", "\n")

        # Remove systemic prefixes text models use sometimes
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
        ]

        for pattern in artifacts:
            response = re.sub(pattern, "", response, flags=re.IGNORECASE)

        # Standardize conversational layout details
        response = re.sub(r"\n{3,}", "\n\n", response)

        # Remove standard polite closing scripts if present
        bad_endings = [
            "thank you",
            "thanks",
            "hope this helps",
            "let me know if you need anything else",
        ]
        for ending in bad_endings:
            if response.lower().endswith(ending):
                response = response[: -len(ending)].strip()

        # Final pass matching clean presentation requirements
        response = PromptEngineer.remove_filler_text(response)

        return response.strip()
    
        

    @staticmethod
    def format_no_answer_response(question: str) -> str:
        # return "I could not find sufficient information about this topic in the uploaded documents."
        return (
            "The requested information was not found in the uploaded documents."
        )

    @staticmethod
    def direct_answer_reminder() -> str:
        return "Provide a complete answer focusing on direct metrics, using standard clear Markdown style rules."

    @staticmethod
    def synthesis_reminder() -> str:
        return "Synthesize information logically from your document contexts into coherent, bolded-header layout structures."

    @staticmethod
    def extract_source_mention(response: str) -> str:
        source_pattern = r"(?:Source|From|Reference):?\s*([^,\n]+(?:\.pdf|\.docx|\.txt|\.md))[^\n]*"
        match = re.search(source_pattern, response, re.IGNORECASE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def build_context_synthesis_signal(context_blocks: List[str]) -> str:
        if len(context_blocks) <= 1:
            return "Use available context to provide a focused answer."
        # return "Combine critical points across distinct contexts systematically using structured tables or headings."
        return "Combine relevant information from multiple contexts into a coherent answer while following the required response format."
    @staticmethod
    def build_coherence_signal(context_blocks: List[str]) -> str:
        return "Organize sections logically via standard Markdown syntax templates."

    @staticmethod
    def build_continuation_signal(conversation_history: Optional[List[dict]] = None) -> str:
        if not conversation_history or len(conversation_history) < 2:
            return ""
        return "Build seamlessly on past details, preserving stylistic continuity across messages."