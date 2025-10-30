from app.config import settings
from .base import BaseLLM
from .gemini import GeminiLLM
from .openai import OpenAILLM
import logging

logger = logging.getLogger(__name__)

class LLMFactory:
    """Factory for creating LLM clients."""

    @staticmethod
    def get_llm() -> BaseLLM:
        """Returns an instance of the configured LLM provider."""
        provider = settings.llm_provider.lower()
        logger.info(f"Creating LLM client for provider: {provider}")

        if provider == "gemini":
            return GeminiLLM(api_key=settings.gemini_api_key)
        elif provider == "openai":
            return OpenAILLM(api_key=settings.openai_api_key)
        else:
            logger.error(f"Unsupported LLM provider: {provider}")
            raise ValueError(f"Unsupported LLM provider: {provider}")

# A single instance of the factory can be used
llm_factory = LLMFactory()
