import os
import logging
import json
from datetime import datetime, timedelta
import asyncio
import sys
import traceback

import redis.asyncio as redis
from taskiq_redis import RedisAsyncResultBackend, ListQueueBroker
from taskiq import TaskiqDepends

from app.config import settings
from app.logging_config import setup_logging
from app.llm.factory import llm_factory
from app.storage.factory import storage_factory
from app.worker.docker_utils import start_container, get_container_status_and_logs
from app.kaggle.client import setup_kaggle_api
from app.utils import sanitize_job_id


# --- Setup ---
setup_logging()
logger = logging.getLogger(__name__)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

result_backend = RedisAsyncResultBackend(
    redis_url="redis://localhost:6379",
)

broker = ListQueueBroker(
    url="redis://localhost:6379",
).with_result_backend(result_backend)


async def get_redis_client() -> redis.Redis:
    """Get Redis client instance."""
    return redis.Redis(
        host=settings.redis_host,
        port=settings.redis_port,
        db=settings.redis_db,
        decode_responses=True
    )


# --- Taskiq Tasks ---
@broker.task(task_name="process_job_queue")
async def process_job(
    job_id: str,
    redis_client: redis.Redis = TaskiqDepends(get_redis_client)
):
    """Taskiq task to process a Kaggle competition job."""
    logger.info(f"[{job_id}] Taskiq task 'process_job' started.")
    job_data = await redis_client.json().get(job_id)
    if not job_data:
        logger.error(f"[{job_id}] Job data not found in Redis.")
        return

    try:
        # 1. Update status and timestamp
        await redis_client.json().set(job_id, "$.status", "processing")
        await redis_client.json().set(job_id, "$.processed_at", datetime.utcnow().isoformat())

        # 2. Setup directories and Kaggle API
        llm_instructions, data_path = await setup_kaggle_api(
            job_id, 
            job_data['competition_url']
        )
        # 3. Prepare for LLM call (check for previous errors)
        previous_code = None
        error_feedback = None
        if job_data.get('attempts', 0) > 0 and job_data.get('generated_code_path'):
            storage = storage_factory.get_storage()
            try:
                previous_code_bytes = await storage.read_file(job_data['generated_code_path'])
                previous_code = previous_code_bytes.decode('utf-8')
                error_feedback = json.dumps(job_data.get('errors', []))
                logger.info(f"[{job_id}] Retrying with context from previous attempt.")
            except Exception as e:
                logger.warning(f"[{job_id}] Could not read previous code/errors for retry: {e}")

        # 4. Generate code
        llm = llm_factory.get_llm()
        generated_code = await llm.generate_code(
            competition_instructions=llm_instructions,
            previous_code=previous_code,
            error_feedback=error_feedback
        )
        
        # 5. Save the generated code
        storage = storage_factory.get_storage()
        code_file_path = os.path.join(sanitize_job_id(job_id), "generated_script.py")
        saved_code_path = await storage.save_file(code_file_path, generated_code)
        await redis_client.json().set(job_id, "$.generated_code_path", saved_code_path)

        # 6. Start Docker container
        container_id = await start_container(job_id, generated_code, data_path)
        await redis_client.json().set(job_id, "$.container_id", container_id)
        logger.info(f"[{job_id}] Docker container {container_id} started. Enqueuing polling task.")

        # 7. Enqueue polling task
        await poll_container_status.kiq(job_id, container_id)

    except Exception as e:
        tb_str = traceback.format_exc()
        logger.error(f"[{job_id}] Error in process_job task: {e}", exc_info=True)
        await handle_job_failure(job_id, str(e), tb_str, redis_client)

@broker.task(task_name="poll_container_queue")
async def poll_container_status(
    job_id: str,
    container_id: str,
    redis_client: redis.Redis = TaskiqDepends(get_redis_client)
):
    """Taskiq task to poll the status of a Docker container."""
    logger.info(f"[{job_id}] Taskiq task 'poll_container_status' started for container {container_id}.")
    job_data = await redis_client.json().get(job_id)
    if not job_data:
        logger.error(f"[{job_id}] Job data not found in Redis during polling.")
        return

    status, logs, submission_file_path = await get_container_status_and_logs(job_id, container_id)

    if status == "running":
        logger.info(f"[{job_id}] Container {container_id} still running. Re-queueing poll task.")
        # Re-queue with a delay
        await (poll_container_status.kicker()
               .with_labels(delay=settings.poll_delay_seconds)
               .kiq(job_id, container_id))
        
    elif status == "exited_success":
        logger.info(f"[{job_id}] Container {container_id} exited successfully.")
        try:
            storage = storage_factory.get_storage()
            # Read submission file content from the persistent path
            # Standard open is blocking, run in a thread pool
            submission_content = await asyncio.to_thread(lambda: open(submission_file_path, 'rb').read())
            
            # Save submission file using storage factory
            final_submission_key = os.path.join(sanitize_job_id(job_id), "submission.csv")
            final_path = await storage.save_file(final_submission_key, submission_content)
            
            await redis_client.json().set(job_id, "$.status", "completed")
            await redis_client.json().set(job_id, "$.submission_path", final_path)
            logger.info(f"[{job_id}] Job completed successfully. Submission saved to {final_path}")
        except Exception as e:
            logger.error(f"[{job_id}] Error saving submission file: {e}", exc_info=True)
            await handle_job_failure(job_id, f"Error saving submission: {e}", logs, redis_client)
    elif status == "exited_error":
        logger.error(f"[{job_id}] Container {container_id} exited with an error.")
        await handle_job_failure(job_id, "Container execution failed.", logs, redis_client)

async def handle_job_failure(job_id: str, error_message: str, logs: str | None, redis_client: redis.Redis):
    """Handles job failure logic, including retries and status updates."""
    job_data = await redis_client.json().get(job_id)
    if not job_data:
        logger.error(f"[{job_id}] Job data not found for failure handling.")
        return

    current_attempts = job_data.get('attempts', 0)
    max_attempts = job_data.get('max_attempts', settings.max_attempts)

    # Append error message and logs if available
    error_entry = {"timestamp": datetime.utcnow().isoformat(), "message": error_message}
    if logs:
        error_entry["logs"] = logs # Store logs only if there was a container error
    await redis_client.json().arrappend(job_id, "$.errors", error_entry)

    if current_attempts + 1 >= max_attempts:
        await redis_client.json().set(job_id, "$.status", "failed")
        logger.error(f"[{job_id}] Job failed permanently after {current_attempts + 1} attempts.")
    else:
        await redis_client.json().set(job_id, "$.attempts", current_attempts + 1)
        await redis_client.json().set(job_id, "$.status", "pending_retry")
        logger.warning(f"[{job_id}] Job failed, re-queueing for attempt {current_attempts + 2}.")
        # Re-enqueue the initial processing task for retry
        await process_job.kiq(job_id)

# To run the worker:
# taskiq worker app.worker.main:broker
