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

        self.base_url = self.settings.llm_base_url

        self.default_model = self.settings.llm_model

    async def is_available(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                response = await client.get(f"{self.base_url}/api/tags")
                # For vLLM use
                # response = await client.get(f"{self.base_url}/models")
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Ollama unavailable: {str(e)}")
            return False

    async def generate(self, prompt: str, model: str | None = None) -> str:
        """Generate a response using the fully engineered RAG prompt context wrapper."""
        selected_model = model or self.default_model

        # FIXED: Pass the prompt as a singular execution statement block. 
        # The PromptEngineer class has already established the constraints.
        payload = {
            "model": selected_model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "stream": False,
            "options": {
                "temperature": 0.15,
                "top_p": 0.85,
                "top_k": 40,
                "repeat_penalty": 1.05,
                "num_ctx": 8192,
                "num_predict": 1024,
                "num_thread": 8
            }
        }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(connect=30.0, read=600.0, write=600.0, pool=600.0)
            ) as client:
                logger.info(f"Prompt length: {len(prompt)}")
                response = await client.post(f"{self.base_url}/api/chat", json=payload)
                response.raise_for_status()
                data = response.json()
                text = data.get("message", {}).get("content") or ""
                return self._clean_response(text)
        except httpx.TimeoutException:
            logger.exception("Ollama request timed out")
            return "The AI model took too long to respond. Please try again with a simpler question."
        except Exception as e:
            logger.exception(f"Ollama generation failed: {str(e)}")
            return "An error occurred while generating the response."

    async def stream_generate(self, prompt: str, model: str | None = None) -> AsyncGenerator[str, None]:
        """Stream a response token-by-token directly from the engineered prompt wrapper."""
        selected_model = model or self.default_model
        
        payload = {
            "model": selected_model,
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "stream": True,
            # "options": {
            #     "temperature": 0.15,
            #     "top_p": 0.85,
            #     "top_k": 40,
            #     "repeat_penalty": 1.05,
            #     "presence_penalty": 0.05,
            #     "frequency_penalty": 0.05,
            #     "num_ctx": 8192,
            #     "num_predict": 1024,
            #     "num_thread": 8,
            # }
            "options": {
                # FIXED: Raised from 0.15 to 0.35 to allow the model to write more naturally 
                # and fully explain concepts using definitions + examples.
                "temperature": 0.35,
                "top_p": 0.90,
                "top_k": 50,
                
                # FIXED: Balanced penalty constraints to prevent line repetition without truncating answers early
                "repeat_penalty": 1.10,
                "presence_penalty": 0.0,
                "frequency_penalty": 0.0,
                
                # FIXED: Extended generation window to ensure steps and tables finish writing completely
                "num_ctx": 8192,
                "num_predict": 2048, 
                "num_thread": 8
            }
        }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(connect=30.0, read=600.0, write=600.0, pool=600.0)
            ) as client:
                async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            chunk = data.get("message", {}).get("content", "")
                            if chunk:
                                yield chunk
                            if data.get("done"):
                                break
                        except Exception:
                            continue
        except Exception as e:
            logger.exception(f"Streaming failed: {str(e)}")
            yield "\n\n[Streaming interrupted]"

    def _clean_response(self, text: str) -> str:
        """Clean the raw LLM response of common artifacts without breaking markdown structural text grids."""
        if not text:
            return ""
        
        text = re.sub(r"\n[-=]{3,}\n", "\n\n", text)
        text = text.strip()

        # Remove response label prefixes cleanly
        artifacts = [
            r"(?i)^based on (the )?(uploaded |provided )?documents?,?\s*",
            r"(?i)^according to the context,?\s*",
            r"(?i)^here is (the |my )?answer:?\s*",
            r"(?i)^the answer is:?\s*",
            r"(?i)^here is the direct answer:?\s*",
            r"(?i)^response:?\s*",
            r"(?i)^here is a (brief )?(definition|explanation|comparison):?\s*",
            r"(?i)^answer:?\s*",
        ]
        for pattern in artifacts:
            text = re.sub(pattern, "", text)

        # Remove trailing pleasantries smoothly
        bad_endings = [
            r"(?i)\n*thank you\.?\s*$",
            r"(?i)\n*thanks\.?\s*$",
            r"(?i)\n*hope this helps\.?\s*$",
            r"(?i)\n*let me know.*$",
            r"(?i)\n*feel free to.*$",
        ]
        for pattern in bad_endings:
            text = re.sub(pattern, "", text, flags=re.MULTILINE)

        # Remove HTML/XML tags
        text = re.sub(r"<[^>]+>", "", text)

        # FIXED: Collapses trailing horizontal spaces safely, but avoids breaking 
        # necessary markdown block newline grids (\n\n) or structural table walls.
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        # FIXED: Ensure markdown headers are isolated with standard double breaks without squashing list structures
        text = re.sub(r'\s*(##+\s+[^\n]+)', r'\n\n\1\n\n', text)

        return text.strip()