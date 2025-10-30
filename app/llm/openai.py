from openai import AsyncOpenAI
from .base import BaseLLM
from app.config import settings
import logging

logger = logging.getLogger(__name__)

class OpenAILLM(BaseLLM):
    """LLM client for OpenAI's models (e.g., GPT-4)."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("OpenAI API key is required.")
        self.client = AsyncOpenAI(api_key=api_key)
        self.model = "gpt-4-turbo" # Or another suitable model
        logger.info("OpenAI LLM client initialized.")

    async def generate_code(
        self,
        competition_instructions: str,
        previous_code: str | None = None,
        error_feedback: str | None = None
    ) -> str:
        """Generates code using the OpenAI API."""
        system_prompt, user_prompt = self._build_prompts(
            competition_instructions, previous_code, error_feedback
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.2, # Lower temperature for more deterministic code
            )
            generated_code = response.choices[0].message.content
            # Basic cleaning to remove markdown code fences
            if generated_code.startswith("```python"):
                generated_code = generated_code[len("```python"):]
            if generated_code.endswith("```"):
                generated_code = generated_code[:-len("```")]
            generated_code = generated_code.strip()

            logger.info("Code generated successfully by OpenAI.")
            return generated_code
        except Exception as e:
            logger.error(f"Error generating code with OpenAI: {e}")
            raise

    def _build_prompts(
        self,
        competition_instructions: str,
        previous_code: str | None = None,
        error_feedback: str | None = None
    ) -> tuple[str, str]:
        """Constructs the system and user prompts for the LLM."""
        system_prompt = ("You are an expert Kaggle data scientist. Your task is to write a Python script to solve a Kaggle competition. "
                         "The script must read data from a directory named '/kaggle/input', process it, train a model, make predictions, "
                         "and write the submission file to '/kaggle/working/submission.csv' in the specified format. "
                         "Provide only the complete, runnable Python script without any explanatory text and without bugs. I am using python 3.10:slim image"
                         " and pandas scikit-learn numpy stable-baselines3 libraies, so write code using only these libraries.")

        user_prompt = f"""Here are the competition details and data description:
        --- COMPETITION INSTRUCTIONS ---
        {competition_instructions}
        --- END INSTRUCTIONS ---
        """

        if previous_code and error_feedback:
            user_prompt += f"""
            
            The last attempt to run the code failed. Here is the code and the corresponding error.
            Please analyze the error and the code, fix the bug, and provide a new, corrected script.
            Give only python script no other text.

            --- PREVIOUS CODE ---
            {previous_code}
            --- END PREVIOUS CODE ---

            --- ERROR LOG ---
            {error_feedback}
            --- END ERROR LOG ---
            """
        
        return system_prompt, user_prompt
