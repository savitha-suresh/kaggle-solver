import uuid
import logging
import re
from datetime import datetime
import os
from typing import Optional

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import FileResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import taskiq_fastapi
from taskiq_redis import RedisAsyncResultBackend, ListQueueBroker

from .config import settings
from .logging_config import setup_logging
from app.schemas.status import StatusResponse
from app.workers.main import process_job
from app.utils.misc import is_valid_kaggle_url
from app.redis import get_redis_connection_kwargs

# --- Setup ---
setup_logging()
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address, default_limits=[f"{settings.rate_limit_requests}/minute"])

result_backend = RedisAsyncResultBackend(
    redis_url="redis://localhost:6379",
)

broker = ListQueueBroker(
    url="redis://localhost:6379",
).with_result_backend(result_backend)

app = FastAPI(
    title="Kaggle Solver API",
    description="An API to automatically generate Kaggle solutions."
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Initialize Taskiq FastAPI integration
taskiq_fastapi.init(broker, "app.worker.main:broker")

# --- Redis Connection (Async for direct access) ---
@app.on_event("startup")
async def startup_event():
    """Initializes async Redis connection pool on app startup."""
    try:
        app.state.redis = redis.Redis(**get_redis_connection_kwargs())
        await app.state.redis.ping()
        logger.info("Successfully connected to Redis (async client).")
    except Exception as e:
        logger.critical(f"Could not connect to Redis: {e}", exc_info=True)

@app.on_event("shutdown")
async def shutdown_event():
    """Closes Redis connection on app shutdown."""
    if hasattr(app.state, 'redis') and app.state.redis:
        await app.state.redis.close()
        logger.info("Redis connection closed.")

async def get_redis() -> redis.Redis:
    if not hasattr(app.state, 'redis') or not app.state.redis:
        raise HTTPException(status_code=503, detail="Redis connection not available.")
    return app.state.redis

# --- Helper Functions ---


# --- API Endpoints ---
@app.post("/run")
@limiter.limit(f"{settings.rate_limit_requests}/minute")
async def submit_job(request: Request, url: str, redis_client: redis.Redis = Depends(get_redis)):
    """Accepts a Kaggle URL, creates a job, and adds it to the queue."""
    logger.info(f"Received job submission request for URL: {url}")

    if not is_valid_kaggle_url(url):
        logger.warning(f"Invalid Kaggle URL submitted: {url}")
        raise HTTPException(status_code=400, detail="Invalid Kaggle competition URL provided.")

    job_id = f"job:{uuid.uuid4()}"
    job_data = {
        "id": job_id,
        "status": "pending",
        "competition_url": url,
        "current_task": None,
        "attempts": 0,
        "max_attempts": settings.max_attempts,
        "errors": [],
        "submission_path": None,
        "generated_code_path": None,
        "container_id": None, # New field for container ID
        "created_at": datetime.utcnow().isoformat(),
        "processed_at": None,
        "completed_at": None
    }

    try:
        # Use redis-py's native JSON commands
        await redis_client.json().set(job_id, "$", job_data)
        # Enqueue the Taskiq task
        await process_job.kiq(job_id, url)
        logger.info(f"Successfully enqueued Taskiq job {job_id} for URL: {url}")
    except Exception as e:
        logger.error(f"Failed to enqueue Taskiq job {job_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to enqueue job.")

    return {"message": "Job submitted successfully", "job_id": job_id}

@app.get("/status/{job_id}", response_model=StatusResponse)
async def get_job_status(job_id: str, redis_client: redis.Redis = Depends(get_redis)):
    """Retrieves the status and result of a job."""
    logger.info(f"Fetching status for job_id: {job_id}")
    try:
        job_data = await redis_client.json().get(job_id)
    except Exception as e:
        logger.error(f"Error fetching job {job_id} from Redis: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error fetching job status.")

    if not job_data:
        logger.warning(f"Job not found: {job_id}")
        raise HTTPException(status_code=404, detail="Job not found.")

    status = job_data.get("status")
    if status == "completed":
        submission_path = job_data.get("submission_path")
        if settings.storage_provider == "local":
            return StatusResponse(status="success", source="local", path=submission_path)
        else:
            return StatusResponse(status="success", source="s3", path=submission_path)
    elif status == "failed":
        return StatusResponse(status="failed", message="Failed")
    else:
        return StatusResponse(status=status)
