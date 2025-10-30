from abc import ABC, abstractmethod

class BaseLLM(ABC):
    """Abstract base class for a Large Language Model client."""

    @abstractmethod
    async def generate_code(
        self,
        competition_instructions: str,
        previous_code: str | None = None,
        error_feedback: str | None = None
    ) -> str:
        """
        Generates code based on competition instructions and optional feedback from previous runs.

        :param competition_instructions: The main prompt describing the Kaggle competition.
        :param previous_code: The code from a previous failed attempt.
        :param error_feedback: The error message or traceback from the failed attempt.
        :return: A string containing the generated Python code.
        """
        pass
