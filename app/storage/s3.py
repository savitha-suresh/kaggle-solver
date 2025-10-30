import aiobotocore
from botocore.exceptions import ClientError
import logging
from .base import BaseStorage

logger = logging.getLogger(__name__)

class S3Storage(BaseStorage):
    """Handles saving and reading files from an S3 bucket asynchronously."""

    def __init__(self, bucket_name: str, aws_access_key_id: str, aws_secret_access_key: str):
        if not all([bucket_name, aws_access_key_id, aws_secret_access_key]):
            raise ValueError("S3 bucket name and credentials are required.")
        
        self.bucket_name = bucket_name
        self.session = aiobotocore.get_session()
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        logger.info(f"S3 storage initialized for bucket: {self.bucket_name}")

    async def _get_client(self):
        return self.session.create_client(
            's3',
            aws_access_key_id=self.aws_access_key_id,
            aws_secret_access_key=self.aws_secret_access_key
        )

    async def save_file(self, file_path: str, content: bytes | str) -> str:
        """Saves a file to S3 asynchronously.

        :param file_path: The object key in the S3 bucket.
        :param content: The content to upload.
        :return: The S3 URI of the object.
        """
        body = content if isinstance(content, bytes) else content.encode('utf-8')
        async with await self._get_client() as client:
            try:
                await client.put_object(Bucket=self.bucket_name, Key=file_path, Body=body)
                s3_uri = f"s3://{self.bucket_name}/{file_path}"
                logger.info(f"File saved successfully to {s3_uri}")
                return s3_uri
            except ClientError as e:
                logger.error(f"Failed to save file to S3 bucket {self.bucket_name}: {e}")
                raise

    async def read_file(self, file_path: str) -> bytes:
        """Reads a file from S3 asynchronously.

        :param file_path: The object key in the S3 bucket.
        :return: The content of the file in bytes.
        """
        async with await self._get_client() as client:
            try:
                response = await client.get_object(Bucket=self.bucket_name, Key=file_path)
                logger.info(f"Reading file from s3://{self.bucket_name}/{file_path}")
                async with response['Body'] as stream:
                    return await stream.read()
            except ClientError as e:
                logger.error(f"Failed to read file from S3 bucket {self.bucket_name}: {e}")
                raise