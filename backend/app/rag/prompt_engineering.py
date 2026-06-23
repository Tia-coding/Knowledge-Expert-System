from typing import List, Optional
import re


class PromptEngineer:
    """Prompt engineering utility for intelligent RAG responses."""

    @staticmethod
    def _build_context_block(context_blocks: List[str]) -> str:
        return "\n\n".join(context_blocks)

    @staticmethod
    def _assemble_prompt(
        rules: str,
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:
        """Assemble a complete prompt from rules, context, and conversation history."""
        # Label each context block for traceability
        labeled_context = ""
        for i, block in enumerate(context_blocks, 1):
            labeled_context += f"--- Context Block {i} ---\n{block}\n\n"
        labeled_context = labeled_context.strip()

        history_block = PromptEngineer.format_conversation_history(conversation_history)

        sections = [rules.strip()]
        if history_block:
            sections.append(history_block)
        sections.append(f"DOCUMENT CONTEXT:\n{labeled_context}")
        sections.append(f"QUESTION: {question.strip()}")

        return "\n\n".join(sections)

    @staticmethod
    def format_conversation_history(
        conversation_history: Optional[List[dict]] = None,
        max_turns: int = 6,
    ) -> str:
        if not conversation_history:
            return ""
        recent = conversation_history[-(max_turns * 2) :]
        lines: list[str] = []
        for turn in recent:
            role = turn.get("role", "")
            content = (turn.get("content") or "").strip()
            if not content:
                continue
            label = "User" if role == "user" else "Assistant"
            if role == "assistant" and len(content) > 800:
                content = content[:800].strip() + "..."
            lines.append(f"{label}: {content}")
        if not lines:
            return ""
        return "RECENT CONVERSATION HISTORY:\n" + "\n\n".join(lines)

    @staticmethod
    def build_prompt(
        question: str,
        context_blocks: List[str],
        conversation_history: Optional[List[dict]] = None,
    ) -> str:
        if not context_blocks:
            return "The requested information was not found in the uploaded documents."

        rules = """You are a knowledgeable document-grounded AI assistant. Answer the user's question using ONLY the provided document context below.

GUIDELINES:
- Write naturally and conversationally, as if you are an expert explaining the topic.
- Start directly with the answer content. Do not use introductory phrases.
- Do not mention documents, sources, filenames, page numbers, or retrieval processes in your answer.
- Do not add sections like "Note:", "Summary:", "Conclusion:", "References:", or "Key Takeaways:".
- Use all relevant information from the provided context. If multiple chunks discuss the same concept, combine them into one coherent explanation.
- If the context contains definitions, characteristics, types, steps, examples, or applications, include them naturally and fully. Do not stop after a short definition if additional relevant information exists in the context.
- Do not invent facts, examples, or explanations that are not supported by the context.
- Format your answer for readability:
  - Use short paragraphs for explanations.
  - Use bullet points for lists of items or types.
  - Use numbered steps for sequential processes.
  - Use **bold** for key terms or important concepts where appropriate.
  - Use tables only for structured comparisons.
- Every sentence should start with a capital letter and end with proper punctuation.

IMPORTANT RULES:
1. Do NOT copy raw text from the context.
2. Do NOT include source document artifacts or placeholders.
3. Rewrite the answer in clear, well-structured natural language.
4. For "Types of" or characterization questions, list EVERY type mentioned in the context with an explicit bullet point.
5. For comparison questions, ALWAYS return a markdown table.
"""
        return PromptEngineer._assemble_prompt(rules, question, context_blocks, conversation_history)

    # POST-PROCESSING HELPERS

    @staticmethod
    def clean_response(response: str, question: str = "") -> str:
        """Universally sanitizes response text without hardcoded string matching or Python 11 syntax errors."""
        if not response:
            return response

        # 1. Normalize line breaks and spaces safely
        response = response.strip()
        response = response.replace("\\n", "\n")

        # 2. FIXED: Universally strip common prefixes (Moved (?i) to absolute front for Python 11)
        response = re.sub(r"(?i)^(answer|response|ai\s+response|final\s+answer|output)\s*[:\-–—]\s*", "", response)

        # 3. FIXED: Strip conversational introductions (Moved (?i) to absolute front to prevent runtime crash)
        intro_patterns = [
            r"(?i)^based\s+on\s+(the\s+)?(uploaded\s+|provided\s+)?(documents?|notes?|pdfs?|context|materials?)[^.\n]*[.!\n]*",
            r"(?i)^according\s+to\s+(the\s+)?(uploaded\s+|provided\s+)?(documents?|notes?|pdfs?|context|materials?)[^.\n]*[.!\n]*",
            r"(?i)^(sure|certainly|of\s+course|here\s+is|here\s+are)[^.\n]*[:.!\n]+",
        ]
        for pattern in intro_patterns:
            response = re.sub(pattern, "", response).strip()

        # 4. FIXED DE-HARDCODING: Universally remove the question if the model echoes it as a markdown heading
        if question:
            clean_q = question.strip().lower().rstrip('?.!')
            response = re.sub(rf"(?i)^##?\s*{re.escape(clean_q)}[?.!]*\s*\n+", "", response)

        # 5. FIXED DE-HARDCODING: Universally remove question sentence if echoed at the absolute start of text prose
        if question:
            clean_q = question.strip().lower().rstrip('?.!')
            first_sentence_match = re.match(r"^([^.!?]+[?.!]+)\s*", response)
            if first_sentence_match:
                first_sentence = first_sentence_match.group(1).strip().lower().rstrip('?.!')
                if first_sentence == clean_q or clean_q in first_sentence:
                    response = response[len(first_sentence_match.group(0)):].strip()

        # 6. Universally wipe any unrendered bracketed/parenthetical markdown annotations or placeholders
        response = re.sub(r"[\[\(]\s*(insert|refer|figure|image|diagram|chart|above|below|source)[^\]\)]*[\]\)]", "", response, flags=re.IGNORECASE)

        # 7. Clean up any inline conversational meta-commentary fragments seamlessly
        inline_patterns = [
            r"(?i)\bbased\s+on\s+the\s+(provided\s+|uploaded\s+)?(context|documents?|notes?)\b,?\s*",
            r"(?i)\baccording\s+to\s+the\s+(provided\s+|uploaded\s+)?(context|documents?|notes?)\b,?\s*",
        ]
        for pattern in inline_patterns:
            response = re.sub(pattern, "", response).strip()

        # 8. Universally clear out trailing conversational noise (pleasantries)
        pleasantry_patterns = [
            r"(?i)\n*(thank\s+you|thanks|hope\s+this\s+helps)[.!\s]*$",
            r"(?i)\n*let\s+me\s+know\s+if\s+you\s+(need|have)[^.\n]*[.!\s]*$",
        ]
        for pattern in pleasantry_patterns:
            response = re.sub(pattern, "", response).strip()

        # 9. Normalize whitespace clusters safely
        response = re.sub(r"\n{3,}", "\n\n", response)
        response = re.sub(r" {2,}", " ", response)

        return response.strip()

    # --- ENSURE THIS IS ALIGNED AT THE MODULE/CLASS LEVEL (4 SPACES) ---
    @staticmethod
    def polish_answer(text: str) -> str:
        """Final polish: capitalize first letter, ensure ending punctuation."""
        if not text:
            return text
        text = text.strip()
        if text and text[0].islower():
            text = text[0].upper() + text[1:]
        if (
            text
            and text[-1] not in ".!?"
            and "|" not in text
            and not text.rstrip().endswith("```")
        ):
            # Don't add period if it ends with markdown table, code block, or list
            if not re.search(r"[-*|:`]\s*$", text):
                text += "."
        return text

    @staticmethod
    def direct_answer_reminder() -> str:
        return "Start directly with the answer content. Do NOT include introductory phrases."

    @staticmethod
    def synthesis_reminder() -> str:
        return (
            "Synthesize information across all chunks into a single coherent explanation. "
            "Merge related information, remove duplicates, and write naturally."
        )

    @staticmethod
    def format_no_answer_response(question: str) -> str:
        return "The requested information was not found in the uploaded documents."