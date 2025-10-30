import re
import asyncio
import zipfile
import aiofiles

def sanitize_job_id(job_id: str) -> str:
    """Sanitizes the job ID by replacing the colon with an underscore."""
    return job_id.replace(":", "_")

def is_valid_kaggle_url(url: str) -> bool:
    """Validates if the URL is a Kaggle competition URL."""
    pattern = r"^https?://(www\.)?kaggle\.com/(c|competitions)/[a-zA-Z0-9_-]+/?$"
    return re.match(pattern, url) is not None

async def async_unzip(zip_path: str, extract_path: str):
    """Async version of zipfile.extractall."""
    def _unzip_sync(zip_path: str, extract_path: str):
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_path)

    await asyncio.to_thread(_unzip_sync, zip_path, extract_path)

async def async_write_file(path: str, content: str):
    """Async version of writing to a file."""
    async with aiofiles.open(path, "w") as f:
        await f.write(content)

async def async_read_file(path: str) -> str:
    """Async version of reading a file."""
    async with aiofiles.open(path, "r") as f:
        return await f.read()
