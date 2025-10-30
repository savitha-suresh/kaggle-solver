import google.generativeai as genai
from .base import BaseLLM
from app.config import settings
import logging

logger = logging.getLogger(__name__)

class GeminiLLM(BaseLLM):
    """LLM client for Google's Gemini model."""

    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("Gemini API key is required.")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(settings.gemini_model_name)
        logger.info("Gemini LLM client initialized.")

    async def generate_code(
        self,
        competition_instructions: str,
        previous_code: str | None = None,
        error_feedback: str | None = None
    ) -> str:
        """Generates code using the Gemini model."""
        prompt = self._build_prompt(competition_instructions, previous_code, error_feedback)

        try:
            # The google-generativeai library's generate_content is awaitable
            response = await self.model.generate_content_async(prompt)
            generated_code = response.text
            # Basic cleaning to remove markdown code fences
            if generated_code.startswith("```python"):
                generated_code = generated_code[len("```python"):].strip()
            if generated_code.endswith("```"):
                generated_code = generated_code[:-len("```")].strip()
            
            logger.info("Code generated successfully by Gemini.")
            return generated_code
        except Exception as e:
            logger.error(f"Error generating code with Gemini: {e}")
            raise

    def _build_prompt(
        self,
        competition_instructions: str,
        previous_code: str | None = None,
        error_feedback: str | None = None
    ) -> str:
        """Constructs the prompt for the LLM."""
        prompt = f"""
        You are an expert Kaggle data scientist. Your task is to write a Python script to solve a Kaggle competition.
        The script must read data from a directory named '/kaggle/input', process it, train a model, make predictions, 
        and write the submission file to '/kaggle/working/submission.csv' in the specified format.
        All the data files are within the '/kaggle/input' directory 
        and not nested within further subdirectories with competition id.
        Here are the competition details and data description:
        --- COMPETITION INSTRUCTIONS ---
        {competition_instructions}
        --- END INSTRUCTIONS ---

        Please provide only the complete, runnable Python script without bugs.
        I am using python 3.10:slim image
        and pandas scikit-learn numpy stable-baselines3 libraies, so write code using only these libraries.
        """

        if previous_code and error_feedback:
            prompt += f"""
            
            The last attempt to run the code failed. Here is the code and the corresponding error.
            Please analyze the error and the code, fix the bug, and provide a new, corrected script.

            --- PREVIOUS CODE ---
            {previous_code}
            --- END PREVIOUS CODE ---

            --- ERROR LOG ---
            {error_feedback}
            --- END ERROR LOG ---
            
            Your task is to provide the corrected, complete Python script. Give only python script no other text.
            """
        
        return prompt
