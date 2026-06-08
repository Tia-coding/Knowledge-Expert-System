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

        # Explicit structured procedure requests (Priority given to algorithmic step structures)
        if re.search(
            r"\b(algorithm|procedure|steps|workflow|methodology)\b",
            q
        ):
            return "algorithm"

        if "pseudocode" in q:
            return "algorithm"

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
            "Include additional detail only when it is directly relevant "
            "to the user's request and supported by the retrieved context."
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
SYNTHESIS RULES:

* Answer the user's question directly and clearly.
* Focus purely on the topic requested.
* Explain information in your own words while preserving factual accuracy.
* Short definitions, names, dates, or exact values may be used directly when accuracy requires it.
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
- Use fenced code blocks only when the retrieved context contains code or structured technical notation relevant to the question.
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
    OCR artifacts, or formatting remnants.

12. When code or structured technical notation exists in the retrieved
    context and is relevant to the user's question, render it using
    proper fenced code blocks.

13. Convert extracted content into natural language explanations.


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
- Use bullet points for lists, key points, requirements, or comparisons when they improve readability.
- Choose concise topic-based section titles only when necessary.
- Avoid creating unnecessary headings for short answers.
- Avoid generic headings such as "Answer", "List", "Details", or "Differences".
- Do not generate markdown tables unless explicitly requested by the user.


    QUESTION INTENT RULES:

For definition questions:

- Start with a direct definition.
- Include only information necessary to understand the concept.
- Include additional details only when they are strongly related to the definition and supported by retrieved content.
- Avoid unrelated procedures, implementations, comparisons, applications, or complexity analysis unless explicitly requested.

Explanation Questions:
- Provide a clear explanation of the requested topic.
- Organize the answer using headings only when they improve readability.
- Cover the major information available in the retrieved context that answers the question.
- Include supporting details from the documents when they help answer the question.
- Do not omit important information that is present in the retrieved context.
- Include examples only if they significantly improve understanding.
- Do not automatically include procedural steps, formulas, or code unless relevant to the question.
- Do not generate Conclusion or Summary sections.
- Prefer concise, well-organized sections over long unstructured paragraphs.

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

- Do NOT repeat the user's question.
- Do NOT use the question as a heading.
- Start directly with the definition.
- Do NOT generate titles
- Don't repeat questions in answers 
- The first sentence must be the definition itself.

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
You are an intelligent document-grounded AI assistant.
{PromptEngineer.common_rules(conversational=False)}

PROCEDURE ANSWERING RULES:

- Answer ONLY using the retrieved document context.
- Focus strictly on the procedure, operation, workflow, algorithm, or process requested.
- The answer MUST be a numbered list.
- Every step MUST begin with:
  1.
  2.
  3.
  ...
- Do not explain the procedure in paragraph form.
- Do not generate introductory paragraphs.
- Do not generate concluding paragraphs.
- Start directly with Step 1.
- End after the final step.
- Each step must be concise and meaningful.
- Add a short explanation only when it helps understand the step.
- Do not add introductory paragraphs unless required by the context.
- Do not generate definitions unless they are necessary to understand the procedure.
- Do not generate examples unless explicitly present and essential in the retrieved content.
- Do not generate advantages, disadvantages, applications, notes, conclusions, summaries, or additional sections.
- Do not add time complexity, space complexity, implementation details, or code unless explicitly requested.
- Do not create extra steps that are not supported by the retrieved document context.
- If the document provides operation names with descriptions, format them as numbered items.
- Preserve the logical order of steps exactly as described in the retrieved content.
- Keep the response clean, structured, and focused on the requested procedure only.

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
You are an intelligent document-grounded AI assistant.
{PromptEngineer.common_rules(conversational=False)}

ALGORITHM ANSWERING RULES:

- Answer ONLY using the retrieved document context.
- Focus strictly on the algorithm, workflow, or process requested.
- Present the algorithm as a numbered sequence of steps.
- Each step should describe a specific action in the correct execution order.
- Keep steps concise and easy to follow.
- Include conditions, iterations, or decision points only when supported by the retrieved context.
- Do not generate introductory paragraphs unless required by the context.
- Do not generate examples unless explicitly present and important in the retrieved content.
- Do not generate advantages, disadvantages, applications, notes, summaries, or conclusions.
- Do not automatically include time complexity or space complexity unless explicitly requested by the user or clearly present in the retrieved context.
- Do not automatically include implementation details or programming code.
- Use fenced code blocks only when actual code exists in the retrieved context.
- Do not invent steps that are not supported by the retrieved documents.
- Preserve the logical order of the algorithm exactly as described in the retrieved context.
- If the retrieved content describes operations rather than an algorithm, present them as numbered operational steps.
- Do not generate sample outputs.
- Do not generate example executions.
- Do not generate illustrative scenarios unless explicitly present in the retrieved context.

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
You are an intelligent document-grounded AI assistant.
{PromptEngineer.common_rules(conversational=False)}

LIST ANSWERING RULES:

- Answer ONLY using the retrieved document context.
- Present items as a clean Markdown bullet list.
- Include ALL relevant items found in the retrieved content.
- Do not stop after the first item when multiple items exist.
- Add a brief explanation for each item only when supported by the retrieved content.
- Keep explanations concise and focused.
- Avoid repeating information across list items.
- Do not introduce unsupported items.
- Do not generate introductory paragraphs unless necessary for understanding the list.
- Do not generate detailed subsections for each item.
- Do not expand items into separate sections unless explicitly requested.
- Do not generate examples unless explicitly present and important in the retrieved content.
- Do not generate advantages, disadvantages, applications, notes, summaries, conclusions, references, sources, or additional information sections.
- Do not add source citations inside the answer body.
- End the answer immediately after the final list item.
- Do not generate introductory sentences before the list.
- Do not generate concluding sentences after the list.
- Start directly with the first list item.

For "types", "categories", "kinds", "classifications", "operations", "features", or similar list-based questions:
- Return only the requested items and their brief descriptions.
- Preserve the order in which the items appear in the retrieved content whenever possible.
- If the retrieved content contains numbered items, preserve that logical ordering.

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

COMPARISON ANSWERING RULES:

- Answer ONLY using the retrieved document context.
- When comparing two or more concepts, generate a valid GitHub-Flavored Markdown table.
- The table must begin immediately without introductory text.
- Do not generate phrases such as:
  - "Here is the comparison"
  - "The following table"
  - "Comparison Table"
  - "Note"
  - "Summary"
  - "Conclusion"
  - "Additional Information"
- Use exactly one header row and one separator row.
- Ensure every row contains the same number of columns as the header.
- The first column must be named "Feature".
- Remaining columns must represent the concepts being compared.
- Include ALL meaningful comparison points available in the retrieved content.
- Keep cell values concise.
- Do not merge multiple features into one row.
- Do not create rows unsupported by the retrieved content.
- Do not add source citations inside table cells.
- Do not generate explanatory paragraphs before or after the table.
- End the answer immediately after the final table row.

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

        response = re.sub(
            r"(?i)\n*in summary[:,]?\s*",
            "\n",
            response
        )

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

        response = re.sub(
            r"(?i)note that.*?$",
            "",
            response,
            flags=re.MULTILINE,
        )

        response = re.sub(
            r'^(what is|define|definition of)\s+.*?:\s*\n*',
            '',
            response,
            flags=re.IGNORECASE
        )

        return response.strip()

    @staticmethod
    def format_no_answer_response(question: str) -> str:
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
        return "Combine relevant information from multiple contexts into a coherent answer while following the required response format."

    @staticmethod
    def build_coherence_signal(context_blocks: List[str]) -> str:
        return "Organize sections logically via standard Markdown syntax templates."

    @staticmethod
    def build_continuation_signal(conversation_history: Optional[List[dict]] = None) -> str:
        if not conversation_history or len(conversation_history) < 2:
            return ""
        return "Build seamlessly on past details, preserving stylistic continuity across messages."