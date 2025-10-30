from abc import ABC, abstractmethod

class BaseStorage(ABC):
    """Abstract base class for a file storage handler."""

    @abstractmethod
    async def save_file(self, file_path: str, content: bytes | str) -> str:
        """
        Saves content to a file.

        :param file_path: The path/key where the file should be stored.
        :param content: The content of the file (bytes or string).
        :return: The full path or URI to the saved file.
        """
        pass

    @abstractmethod
    async def read_file(self, file_path: str) -> bytes:
        """
        Reads content from a file.

        :param file_path: The path/key of the file to read.
        :return: The content of the file in bytes.
        """
        pass
