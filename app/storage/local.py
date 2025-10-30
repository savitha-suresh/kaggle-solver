import os
import aiofiles
from .base import BaseStorage
from app.config import settings
import logging

logger = logging.getLogger(__name__)

class LocalStorage(BaseStorage):
    """Handles saving and reading files from the local disk."""

    def __init__(self, base_path: str):
        self.base_path = base_path
        os.makedirs(self.base_path, exist_ok=True)
        logger.info(f"Local storage initialized at base path: {self.base_path}")

    async def save_file(self, file_path: str, content: bytes | str) -> str:
        """Saves a file to the local filesystem."""
        full_path = os.path.join(self.base_path, file_path)
        # Ensure the directory exists
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        
        mode = 'wb' if isinstance(content, bytes) else 'w'
        try:
            async with aiofiles.open(full_path, mode) as f:
                await f.write(content)
            logger.info(f"File saved successfully to {full_path}")
            return full_path
        except Exception as e:
            logger.error(f"Failed to save file to {full_path}: {e}")
            raise

    async def read_file(self, file_path: str) -> bytes:
        """Reads a file from the local filesystem."""
        full_path = os.path.join(self.base_path, file_path)
        try:
            async with aiofiles.open(full_path, 'rb') as f:
                logger.info(f"Reading file from {full_path}")
                return await f.read()
        except FileNotFoundError:
            logger.error(f"File not found at {full_path}")
            raise
        except Exception as e:
            logger.error(f"Failed to read file from {full_path}: {e}")
            raise
