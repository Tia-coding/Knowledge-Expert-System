import json
import logging
from typing import AsyncGenerator
import httpx
import re

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

class OllamaClient:

    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = self.settings.ollama_base_url
        self.default_model = self.settings.ollama_model

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/api/tags")
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama unavailable: {str(e)}")
            return False

    async def generate(self, prompt: str, model: str | None = None) -> str:
        selected_model = model or self.default_model
        payload = self._build_payload(prompt=prompt, model=selected_model, stream=False)

        try:
            async with httpx.AsyncClient(timeout=600) as client:
                response = await client.post(f"{self.base_url}/api/generate", json=payload)
                response.raise_for_status()
                data = response.json()
                text = data.get("response") or ""
                return self._clean_response(text)
        except httpx.TimeoutException:
            logger.exception("Ollama request timed out")
            return "The AI model took too long to respond."
        except Exception as e:
            logger.exception(f"Ollama generation failed: {str(e)}")
            return "An error occurred while generating the response."

    async def stream_generate(self, prompt: str, model: str | None = None) -> AsyncGenerator[str, None]:
        selected_model = model or self.default_model
        payload = self._build_payload(prompt=prompt, model=selected_model, stream=True)

        try:
            async with httpx.AsyncClient(timeout=600) as client:
                async with client.stream("POST", f"{self.base_url}/api/generate", json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line: continue
                        try:
                            data = json.loads(line)
                            chunk = data.get("response", "")
                            if chunk: yield chunk
                            if data.get("done"): break
                        except Exception: continue
        except Exception as e:
            logger.exception(f"Streaming failed: {str(e)}")
            yield "\n\n[Streaming interrupted]"

    def _build_payload(self, prompt: str, model: str, stream: bool) -> dict:
        """
        Builds payload with a minimal system identity. 
        Formatting rules are managed by PromptEngineer to avoid conflicts.
        """
        system_identity = (
            "You are an intelligent document-grounded AI assistant. "
            "Answer only using the provided document context. "
            "Do not invent information. "
            "If the answer is not supported by the context, state that it was not found in the uploaded documents."
        )

        return {
            "model": model,
            "prompt": f"{system_identity}\n\n{prompt}",
            "stream": stream,
            "options": {
                "temperature": 0.15, # Slightly higher for better formatting variety
                "top_p": 0.85,
                "repeat_penalty": 1.18,
                "num_ctx": 8192,
                "num_predict": 1200, # Increased to allow for tables/detailed code
                "num_thread": 8,
            }
        }

    def _clean_response(self, text: str) -> str:
        if not text: return ""
        
        text = text.strip()

        # FIXED: Placed (?i) at the absolute start of the regex expressions
        artifacts = [
            r"(?i)^based on the (uploaded |provided )?documents?,?\s*",
            r"(?i)^according to the context,?\s*",
            r"(?i)^here is (the |my )?answer:?\s*",
        ]
        for pattern in artifacts:
            text = re.sub(pattern, "", text)

        # Markdown-Safe Cleaning: 
        # We only remove empty lines if there are more than two in a row.
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        # Remove polite endings
        bad_endings = [r"thank you\.?$", r"thanks\.?$", r"hope this helps\.?$", r"let me know.*$"]
        for pattern in bad_endings:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.MULTILINE)

        return text.strip()