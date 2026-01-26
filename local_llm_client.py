"""
Local LLM Client using Ollama
Replaces OpenAI integration with local model
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
import httpx
from config import settings

logger = logging.getLogger(__name__)


class LocalLLMClient:
    """
    Client for interacting with Ollama local LLM
    """

    def __init__(self):
        self.base_url = settings.ollama_host
        self.model = settings.ollama_model
        self.timeout = settings.ollama_timeout

    async def chat(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 150
    ) -> str:
        """
        Generate chat completion using Ollama

        Args:
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate

        Returns:
            Generated response text
        """
        try:
            # Convert messages to Ollama format
            # Ollama expects messages in the same format as OpenAI

            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "temperature": temperature,
                            "num_predict": max_tokens,  # Ollama uses num_predict instead of max_tokens
                        }
                    }
                )

                response.raise_for_status()
                result = response.json()

                # Extract the response
                message = result.get("message", {})
                content = message.get("content", "")

                logger.info(f"Ollama response (first 100 chars): {content[:100]}...")
                return content

        except httpx.TimeoutException:
            logger.error(f"Ollama timeout after {self.timeout}s")
            raise Exception(f"Local LLM timeout after {self.timeout}s")
        except httpx.HTTPStatusError as e:
            logger.error(f"Ollama HTTP error: {e.response.status_code} - {e.response.text}")
            raise Exception(f"Local LLM error: {e.response.status_code}")
        except Exception as e:
            logger.error(f"Ollama error: {str(e)}", exc_info=True)
            raise Exception(f"Local LLM error: {str(e)}")

    async def extract_field(
        self,
        user_input: str,
        field_name: str
    ) -> str:
        """
        Extract a specific field value from user input

        Args:
            user_input: The user's speech text
            field_name: Field to extract (e.g., "name", "email")

        Returns:
            Extracted value or "NOT_FOUND"
        """
        messages = [
            {
                "role": "system",
                "content": f"""Extract only the {field_name} from the user's message.
Return ONLY the value, nothing else.
If not found, return exactly "NOT_FOUND".

Examples:
- "My name is John" → John
- "It's john@email.com" → john@email.com
- "I need help" → NOT_FOUND"""
            },
            {
                "role": "user",
                "content": user_input
            }
        ]

        try:
            result = await self.chat(messages, temperature=0, max_tokens=50)
            return result.strip()
        except Exception as e:
            logger.error(f"Field extraction error: {str(e)}")
            return "NOT_FOUND"

    async def health_check(self) -> bool:
        """
        Check if Ollama is running and model is available

        Returns:
            True if healthy, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                # Check if Ollama is running
                response = await client.get(f"{self.base_url}/api/tags")
                response.raise_for_status()

                # Check if our model is available
                models = response.json().get("models", [])
                model_names = [m.get("name") for m in models]

                if self.model not in model_names:
                    logger.warning(f"Model {self.model} not found. Available: {model_names}")
                    return False

                logger.info(f"Ollama health check passed. Model {self.model} ready.")
                return True

        except Exception as e:
            logger.error(f"Ollama health check failed: {str(e)}")
            return False


# Global client instance
_llm_client: Optional[LocalLLMClient] = None


def get_llm_client() -> LocalLLMClient:
    """Get or create the global LLM client instance"""
    global _llm_client
    if _llm_client is None:
        _llm_client = LocalLLMClient()
    return _llm_client
