from app.config import settings
from .base import BaseStorage
from .local import LocalStorage
from .s3 import S3Storage
import logging

logger = logging.getLogger(__name__)

class StorageFactory:
    """Factory for creating storage handlers."""

    @staticmethod
    def get_storage() -> BaseStorage:
        """Returns an instance of the configured storage provider."""
        provider = settings.storage_provider.lower()
        logger.info(f"Creating storage handler for provider: {provider}")

        if provider == "local":
            return LocalStorage(base_path=settings.local_storage_path)
        elif provider == "s3":
            return S3Storage(
                bucket_name=settings.s3_bucket,
                aws_access_key_id=settings.s3_access_key_id,
                aws_secret_access_key=settings.s3_secret_access_key
            )
        else:
            logger.error(f"Unsupported storage provider: {provider}")
            raise ValueError(f"Unsupported storage provider: {provider}")

# A single instance of the factory can be used
storage_factory = StorageFactory()
