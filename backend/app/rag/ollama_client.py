import json
import logging
from typing import AsyncGenerator

import httpx

from app.config.settings import (
    get_settings,
)

logger = logging.getLogger(__name__)


class OllamaClient:

    def __init__(self) -> None:

        self.settings = get_settings()

        self.base_url = (
            self.settings.ollama_base_url
        )

        self.default_model = (
            self.settings.ollama_model
        )

    # =========================================================
    # CHECK OLLAMA STATUS
    # =========================================================

    async def is_available(self) -> bool:

        try:

            async with httpx.AsyncClient(
                timeout=5
            ) as client:

                response = await client.get(
                    f"{self.base_url}/api/tags"
                )

            return (
                response.status_code == 200
            )

        except Exception as e:

            logger.warning(
                f"Ollama unavailable: {str(e)}"
            )

            return False

    # =========================================================
    # STANDARD GENERATION
    # =========================================================

    async def generate(
        self,
        prompt: str,
        model: str | None = None,
    ) -> str:

        selected_model = (
            model or self.default_model
        )

        payload = self._build_payload(
            prompt=prompt,
            model=selected_model,
            stream=False,
        )

        try:

            async with httpx.AsyncClient(
                timeout=600
            ) as client:

                response = await client.post(
                    f"{self.base_url}/api/generate",
                    json=payload,
                )

                response.raise_for_status()

                data = response.json()

                text = (
                    data.get("response")
                    or ""
                )

                return (
                    self._clean_response(
                        text
                    )
                )

        except httpx.TimeoutException:

            logger.exception(
                "Ollama request timed out"
            )

            return (
                "The AI model took too long "
                "to respond. Please try again."
            )

        except Exception as e:

            logger.exception(
                f"Ollama generation failed: {str(e)}"
            )

            return (
                "An error occurred while "
                "generating the response."
            )

    # =========================================================
    # STREAMING GENERATION
    # =========================================================

    async def stream_generate(
        self,
        prompt: str,
        model: str | None = None,
    ) -> AsyncGenerator[str, None]:

        selected_model = (
            model or self.default_model
        )

        payload = self._build_payload(
            prompt=prompt,
            model=selected_model,
            stream=True,
        )

        try:

            async with httpx.AsyncClient(
                timeout=600
            ) as client:

                async with client.stream(
                    "POST",
                    f"{self.base_url}/api/generate",
                    json=payload,
                ) as response:

                    response.raise_for_status()

                    async for line in (
                        response.aiter_lines()
                    ):

                        if not line:
                            continue

                        try:

                            data = json.loads(
                                line
                            )

                            chunk = (
                                data.get(
                                    "response",
                                    ""
                                )
                            )

                            if chunk:

                                yield chunk

                            if data.get("done"):

                                break

                        except Exception:

                            continue

        except Exception as e:

            logger.exception(
                f"Streaming generation failed: {str(e)}"
            )

            yield (
                "\n\n[Streaming failed]"
            )

    # =========================================================
    # BUILD REQUEST PAYLOAD
    # =========================================================

    def _build_payload(
        self,
        prompt: str,
        model: str,
        stream: bool,
    ) -> dict:

        system_prompt = """
You are a document-grounded assistant.

Use only the retrieved context supplied in the user prompt. If the context
does not support the answer, respond exactly:
I could not find sufficient information about this topic in the uploaded documents.

Answer the current question directly. For simple definition questions, give a
concise definition first and add only the most relevant supported details. For
detailed or comparison questions, provide a fuller answer when the retrieved
context supports it.

Do not merge related concepts unless the context explicitly connects them to
the requested topic. Do not treat examples, implementations, or neighboring
sections as definitions of the requested term. Avoid filler, repetition, and
unsupported background knowledge.
"""

        return {

            "model": model,

            "prompt": (
                f"{system_prompt}\n\n"
                f"{prompt}"
            ),

            "stream": stream,

            "options": {

                # =====================================
                # GENERATION QUALITY
                # =====================================

                "temperature": 0.15,

                "top_p": 0.9,

                "top_k": 40,

                "repeat_penalty": 1.15,

                # =====================================
                # CONTEXT + OUTPUT
                # =====================================

                "num_predict": 450,

                "num_ctx": 4096,

                # =====================================
                # STABILITY
                # =====================================

                "num_thread": 8,

            }

        }

    # =========================================================
    # CLEAN RESPONSE
    # =========================================================

    def _clean_response(
        self,
        text: str,
    ) -> str:

        if not text:

            return ""

        text = text.strip()

        replacements = [

            (
                "Based on the uploaded documents,",
                "",
            ),

            (
                "According to the documents,",
                "",
            ),

            (
                "Here is the answer:",
                "",
            ),

            (
                "The documents explain that",
                "",
            ),

        ]

        for old, new in replacements:

            text = text.replace(
                old,
                new,
            )

        # =============================================
        # REMOVE DUPLICATE LINES
        # =============================================

        seen = set()

        cleaned_lines = []

        for line in text.splitlines():

            line = line.strip()

            if not line:
                continue

            key = line.lower()

            if key in seen:
                continue

            seen.add(key)

            cleaned_lines.append(line)

        text = "\n".join(
            cleaned_lines
        )

        # =============================================
        # CLEAN SPACING
        # =============================================

        while "\n\n\n" in text:

            text = text.replace(
                "\n\n\n",
                "\n\n",
            )

        while "  " in text:

            text = text.replace(
                "  ",
                " ",
            )

        # =============================================
        # REMOVE BAD ENDINGS
        # =============================================

        bad_endings = [

            "thank you",

            "thanks",

            "hope this helps",

            "let me know if you need more",

        ]

        lower = text.lower()

        for ending in bad_endings:

            if lower.endswith(ending):

                text = text[
                    : -len(ending)
                ].strip()

        # =============================================
        # ENSURE VALID ENDING
        # =============================================

        if (
            text
            and text[-1]
            not in ".!?"
        ):

            text += "."

        return text.strip()
