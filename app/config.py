import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings(BaseSettings):
    # LLM API Keys
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")

    # Kaggle API Credentials
    kaggle_username: str = os.getenv("KAGGLE_USERNAME", "")
    kaggle_key: str = os.getenv("KAGGLE_KEY", "")

    # Redis Connection
    redis_host: str = os.getenv("REDIS_HOST", "localhost")
    redis_port: int = int(os.getenv("REDIS_PORT", 6379))
    redis_db: int = int(os.getenv("REDIS_DB", 0))

    # Job Settings
    max_attempts: int = 3
    poll_delay_seconds: int = 100 # Delay between polling container status


    # Rate Limiting (requests per minute)
    rate_limit_requests: int = 50
    rate_limit_period_minutes: int = 1

    # Factory settings
    llm_provider: str = "gemini"  # or "openai"
    storage_provider: str = "local" # or "s3"

    # Local storage path
    local_storage_path: str = "/tmp/kaggle_solver"
    submissions_base_path: str = "./app/submissions"
    competition_data_base_path: str = "./app/data"

    # S3 Storage Settings
    s3_bucket: str = os.getenv("S3_BUCKET", "")
    s3_access_key_id: str = os.getenv("S3_ACCESS_KEY_ID", "")
    s3_secret_access_key: str = os.getenv("S3_SECRET_ACCESS_KEY", "")


# Create a single settings instance to be used across the application
settings = Settings()
