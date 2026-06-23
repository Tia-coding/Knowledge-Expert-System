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
        recent = conversation_history[-(max_turns * 2):]
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
        query_intent: str | None = None,
    ) -> str:
        if not context_blocks:
            return "The requested information was not found in the uploaded documents."

        # Detect the type of question for structure guidance
        structure_guidance = PromptEngineer._get_structure_guidance(question)

        rules = f"""You are an AI assistant that answers questions based ONLY on the provided document context.

CRITICAL RULES:
- Answer the user's EXACT question using the document context provided below.
- Use ALL relevant information from the context. Do not leave out details, characteristics, examples, or explanations that answer the question.
- Start directly with the answer. No introductory phrases like "Based on the documents..." or "According to the context...".
- Be thorough. If the context has multiple pieces of information related to the question, include ALL of them.
- The context comes from source documents. Each block starts with [Source: filename, Page X] — use the information from these sources to build your answer.

RESPONSE STRUCTURE:
{structure_guidance}

ADDITIONAL GUIDELINES:
- Use **bold** for key terms and section labels where helpful.
- Use bullet points (-) for lists, features, characteristics, or multiple items.
- Use numbered lists (1., 2., 3.) for steps, procedures, or ranked items.
- Use a markdown table when comparing multiple items across several dimensions.
- If the user asks for a comparison (compare X and Y, difference between X and Y, X vs Y), present the information in a structured way that makes the differences and similarities easy to see.
- If the user asks for types, kinds, or categories of something, list each one with its description.
- If the user asks how something works or how to do something, explain step by step.
- Do NOT add concluding summaries, pleasantries, or meta-commentary.
- Do NOT mention you are using documents or context in your answer.
- If the context genuinely does not contain the answer, respond with: "I'm sorry, but I couldn't find the information you're looking for in the uploaded documents." """

        return PromptEngineer._assemble_prompt(rules, question, context_blocks, conversation_history)

    @staticmethod
    def _get_structure_guidance(question: str) -> str:
        """
        Provides structure guidance based on question type.
        This is GUIDANCE, not a rigid template. It suggests good formats for each question type
        while letting the model adapt based on what information is actually available.
        """
        if not question:
            return "Organize the answer in whatever way best addresses the user's question. Be thorough and use all relevant context."

        q = question.lower().strip()

        # Comparison questions: compare X and Y, difference between X and Y, X vs Y
        if re.search(r'\b(compare|difference|differen|versus|vs\.?|similarit|contrast|both|alike)\b', q):
            return (
                "This appears to be a COMPARISON question. Structure the answer to clearly show how the items compare:\n"
                "- Start with a brief overview of what is being compared.\n"
                "- Present the comparison in a way that highlights key differences and similarities.\n"
                "- If comparing across multiple aspects, consider using a table or structured points.\n"
                "- Cover all aspects from the context — characteristics, features, applications, etc.\n"
                "- Be thorough: include ALL relevant information from the context."
            )

        # Types/kinds/categories questions: types of X, kinds of X, categories of X, list X
        if re.search(r'\b(types?\s+of|kinds?\s+of|categories?\s+of|classes?\s+of|forms?\s+of|varieties?\s+of|classify|classification|categor|categorize|list|enumerate|what\s+are\s+(the\s+)?(different|various|main|key|major|primary|types?))\b', q):
            return (
                "This appears to be a LIST or CLASSIFICATION question. Structure the answer to present each item clearly:\n"
                "- Start with a brief overview of the category or classification.\n"
                "- Present each type/category/kind as a separate point with its description.\n"
                "- Use bullet points for each item, with the item name in **bold**.\n"
                "- Include characteristics, examples, or applications for each item if present in the context.\n"
                "- Cover all items mentioned in the context — do not leave any out."
            )

        # Procedural/steps questions: how to, steps, procedure, process, method
        if re.search(r'\b(how\s+(to|do|can|would|should|is|are)|steps?|procedure|process|method|way\s+to|technique|guide|tutorial|workflow)\b', q):
            return (
                "This appears to be a PROCEDURAL or STEP-BY-STEP question. Structure the answer to explain the process clearly:\n"
                "- Start with a brief overview of what the process does.\n"
                "- List the steps in order using a numbered list (1., 2., 3., etc.).\n"
                "- Include any prerequisites, requirements, or important notes from the context.\n"
                "- Explain each step with enough detail from the context."
            )

        # Definition questions: what is X, define X, what are X
        if re.search(r'\b(what\s+(is|are|was|were)|defined?|definition|define|explain\s+what|meaning|means?)\b', q):
            return (
                "This appears to be a DEFINITION or EXPLANATION question. Structure the answer to explain the concept fully:\n"
                "- Start with a clear definition or direct answer to the question.\n"
                "- Then cover key characteristics, features, or aspects from the context.\n"
                "- Include any types, components, or classifications if present.\n"
                "- Include examples, applications, or additional details if available in the context.\n"
                "- Be thorough — use ALL relevant information from the context."
            )

        # Factual questions: when, where, who, which, why, how many/much/long
        if re.search(r'\b(when|where|who|which|why|how\s+(many|much|long|often|far|big|large|small|old|tall|wide|deep|high|low)|what\s+(time|date|year|month|day))\b', q):
            return (
                "This appears to be a FACTUAL question. Structure the answer to provide the specific facts requested:\n"
                "- Start with the direct answer to the question.\n"
                "- Then provide supporting details, context, or evidence from the documents.\n"
                "- Include specific numbers, dates, names, or specifications when present.\n"
                "- Use bullet points if there are multiple facts to present."
            )

        # Default: general question
        return (
            "Organize the answer in whatever way best addresses the user's question.\n"
            "- Start with a direct answer.\n"
            "- Then include all supporting details, characteristics, and information from the context.\n"
            "- Use bullet points for multiple points, bold for key terms.\n"
            "- Be thorough and use ALL relevant information."
        )

    # POST-PROCESSING HELPERS

    @staticmethod
    def clean_response(response: str, question: str = "") -> str:
        if not response:
            return response
        response = response.strip()
        response = response.replace("\\n", "\n")
        response = re.sub(r"(?i)^(answer|response|ai\s+response|final\s+answer|output)\s*[:\-–—]\s*", "", response)
        intro_patterns = [
            r"(?i)^based\s+on\s+(the\s+)?(uploaded\s+|provided\s+)?(documents?|notes?|pdfs?|context|materials?)[^.\n]*[.!\n]*",
            r"(?i)^according\s+to\s+(the\s+)?(uploaded\s+|provided\s+)?(documents?|notes?|pdfs?|context|materials?)[^.\n]*[.!\n]*",
            r"(?i)^(sure|certainly|of\s+course|here\s+is|here\s+are)[^.\n]*[:.!\n]+",
        ]
        for pattern in intro_patterns:
            response = re.sub(pattern, "", response).strip()
        if question:
            clean_q = question.strip().lower().rstrip('?.!')
            response = re.sub(rf"(?i)^##?\s*{re.escape(clean_q)}[?.!]*\s*\n+", "", response)
        if question:
            clean_q = question.strip().lower().rstrip('?.!')
            first_sentence_match = re.match(r"^([^.!?]+[?.!]+)\s*", response)
            if first_sentence_match:
                first_sentence = first_sentence_match.group(1).strip().lower().rstrip('?.!').replace('*', '')
                if first_sentence == clean_q or clean_q in first_sentence:
                    response = response[len(first_sentence_match.group(0)):].strip()
        inline_patterns = [
            r"(?i)\bbased\s+on\s+the\s+(provided\s+|uploaded\s+)?(context|documents?|notes?)\b,?\s*",
            r"(?i)\baccording\s+to\s+the\s+(provided\s+|uploaded\s+)?(context|documents?|notes?)\b,?\s*",
        ]
        for pattern in inline_patterns:
            response = re.sub(pattern, "", response).strip()
        pleasantry_patterns = [
            r"(?i)\n*(thank\s+you|thanks|hope\s+this\s+helps)[.!\s]*$",
            r"(?i)\n*let\s+me\s+know\s+if\s+you\s+(need|have)[^.\n]*[.!\s]*$",
        ]
        for pattern in pleasantry_patterns:
            response = re.sub(pattern, "", response).strip()
        response = re.sub(r"\n{3,}", "\n\n", response)
        response = re.sub(r" {2,}", " ", response)
        return response.strip()

    @staticmethod
    def polish_answer(text: str) -> str:
        if not text:
            return text
        text = text.strip()
        if text and text[0].islower():
            text = text[0].upper() + text[1:]
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