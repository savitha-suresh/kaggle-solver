import re

def sanitize_job_id(job_id: str) -> str:
    """Sanitizes the job ID by replacing the colon with an underscore."""
    return job_id.replace(":", "_")

def is_valid_kaggle_url(url: str) -> bool:
    """Validates if the URL is a Kaggle competition URL."""
    pattern = r"^https?://(www\.)?kaggle\.com/(c|competitions)/[a-zA-Z0-9_-]+/?$"
    return re.match(pattern, url) is not None
