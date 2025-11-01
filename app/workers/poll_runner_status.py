import logging
import asyncio
from datetime import datetime, timedelta
import os

import redis.asyncio as redis
from taskiq import Context, TaskiqDepends

from app.config import settings
from app.logging_config import setup_logging
from app.storage.base import BaseStorage
from app.tasks_dg import TASKS_DG
from app.utils.misc import sanitize_job_id, async_read_file
from app.workers.dependencies import get_redis_client, get_storage_client
from app.workers.runners.factory import RunnerFactory
from app.workers.broker_config import broker
from app.workers.code_generator import code_generator

setup_logging()
logger = logging.getLogger(__name__)


@broker.task(task_name="poll_runner_status")
async def poll_runner_status(
    job_id: str,
    runner_id: str,
    context: Context = TaskiqDepends(),
    redis_client: redis.Redis = TaskiqDepends(get_redis_client),
    storage: BaseStorage = TaskiqDepends(get_storage_client),
):
    """Task to poll the status of a runner."""
    task_name = context.message.task_name
    logger.info(f"[{job_id}] Task '{task_name}' started for runner {runner_id}.")
    await redis_client.json().set(job_id, "$.current_task", task_name)

    job_data = await redis_client.json().get(job_id)
    if not job_data:
        logger.error(f"[{job_id}] Job data not found in Redis during polling.")
        return

    runner = RunnerFactory.get_runner(settings.runner_provider)
    status, logs, submission_file_path = await runner.poll_status(
        job_id, runner_id
    )

    if status == "running":
        logger.info(
            f"[{job_id}] Runner {runner_id} still running. Re-queueing poll task."
        )
        runner_created_at = datetime.fromisoformat(job_data["created_at"])
        if datetime.utcnow() - runner_created_at > timedelta(
            seconds=settings.task_timeout
        ):
            logger.error(f"[{job_id}] Runner {runner_id} timed out.")
            await handle_job_failure(
                job_id, "Runner execution timed out.", logs, redis_client, is_timeout=True
            )
            return

        await asyncio.sleep(settings.poll_delay_seconds)
        await poll_runner_status.kiq(job_id, runner_id)

    elif status == "exited_success":
        logger.info(f"[{job_id}] Runner {runner_id} exited successfully.")
        try:
            submission_content = await async_read_file(submission_file_path)

            final_submission_key = os.path.join(
                sanitize_job_id(job_id), "submission.csv"
            )
            final_path = await storage.save_file(final_submission_key, submission_content)

            await redis_client.json().set(job_id, "$.status", "completed")
            await redis_client.json().set(job_id, "$.submission_path", final_path)
            await redis_client.json().set(
                job_id, "$.completed_at", datetime.utcnow().isoformat()
            )
            logger.info(
                f"[{job_id}] Job completed successfully. Submission saved to {final_path}"
            )
        except Exception as e:
            logger.error(f"[{job_id}] Error saving submission file: {e}", exc_info=True)
            await handle_job_failure(
                job_id, f"Error saving submission: {e}", logs, redis_client
            )
    elif status == "exited_error":
        logger.error(f"[{job_id}] Runner {runner_id} exited with an error.")
        await handle_job_failure(
            job_id, "Runner execution failed.", logs, redis_client
        )


async def handle_job_failure(
    job_id: str,
    error_message: str,
    logs: str | None,
    redis_client: redis.Redis,
    is_timeout: bool = False,
):
    """Handles job failure logic, including retries and status updates."""
    job_data = await redis_client.json().get(job_id)
    if not job_data:
        logger.error(f"[{job_id}] Job data not found for failure handling.")
        return

    current_attempts = job_data.get("attempts", 0)
    max_attempts = job_data.get("max_attempts", settings.max_attempts)

    error_entry = {"timestamp": datetime.utcnow().isoformat(), "message": error_message}
    if logs:
        error_entry["logs"] = logs
    await redis_client.json().arrappend(job_id, "$.errors", error_entry)

    if is_timeout or current_attempts + 1 >= max_attempts:
        await redis_client.json().set(job_id, "$.status", "failed")
        await redis_client.json().set(
            job_id, "$.completed_at", datetime.utcnow().isoformat()
        )
        logger.error(
            f"[{job_id}] Job failed permanently after {current_attempts + 1} attempts."
        )
        if job_data.get("runner_id"):
            runner = RunnerFactory.get_runner(settings.runner_provider)
            await runner.force_stop(job_id, job_data["runner_id"])
    else:
        await redis_client.json().set(job_id, "$.attempts", current_attempts + 1)
        await redis_client.json().set(job_id, "$.status", "pending_retry")
        logger.warning(
            f"[{job_id}] Job failed, re-queueing for attempt {current_attempts + 2}."
        )
        await code_generator.kiq(job_id)