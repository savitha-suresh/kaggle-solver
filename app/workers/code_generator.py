import logging
import os
import json

import redis.asyncio as redis
from taskiq import Context, TaskiqDepends

from app.config import settings
from app.llm.base import BaseLLM
from app.logging_config import setup_logging
from app.storage.base import BaseStorage
from app.tasks_dag import TASKS_DAG
from app.utils.misc import sanitize_job_id, async_read_file
from app.workers.dependencies import get_llm_client, get_redis_client, get_storage_client
from app.workers.worker_manager import get_worker
from app.workers.broker_config import broker

setup_logging()
logger = logging.getLogger(__name__)


@broker.task(task_name="code_generator")
async def code_generator(
    job_id: str,
    context: Context = TaskiqDepends(),
    redis_client: redis.Redis = TaskiqDepends(get_redis_client),
    llm: BaseLLM = TaskiqDepends(get_llm_client),
    storage: BaseStorage = TaskiqDepends(get_storage_client),
):
    """Task to generate code using LLM."""
    task_name = context.message.task_name
    logger.info(f"[{job_id}] Task '{task_name}' started.")
    await redis_client.json().set(job_id, "$.current_task", task_name)

    try:
        job_data = await redis_client.json().get(job_id)
        if not job_data:
            logger.error(f"[{job_id}] Job data not found in Redis.")
            return

        instructions_path = job_data.get("instruction_path")
        if not instructions_path or not os.path.exists(instructions_path):
            logger.error(f"[{job_id}] Instructions not found at {instructions_path}")
            await redis_client.json().set(job_id, "$.status", "failed")
            await redis_client.json().set(
                job_id, "$.error", "Instructions not found"
            )
            return

        competition_instructions = await async_read_file(instructions_path)

        previous_code = None
        error_feedback = None
        if job_data.get("attempts", 0) > 0 and job_data.get("generated_code_path"):
            try:
                previous_code_bytes = await storage.read_file(
                    job_data["generated_code_path"]
                )
                previous_code = previous_code_bytes.decode("utf-8")
                error_feedback = json.dumps(job_data.get("errors", []))
                logger.info(f"[{job_id}] Retrying with context from previous attempt.")
            except Exception as e:
                logger.warning(
                    f"[{job_id}] Could not read previous code/errors for retry: {e}"
                )

        logger.info(f"[{job_id}] Requesting code generation from LLM.")
        generated_code = await llm.generate_code(
            competition_instructions=competition_instructions,
            previous_code=previous_code,
            error_feedback=error_feedback,
        )

        code_file_path = os.path.join(sanitize_job_id(job_id), "generated_script.py")
        saved_code_path = await storage.save_file(code_file_path, generated_code)
        await redis_client.json().set(job_id, "$.generated_code_path", saved_code_path)

        next_tasks = TASKS_DAG.get(task_name, [])
        for next_task_name in next_tasks:
            task, worker_data = get_worker(broker, next_task_name)
            if not task or not worker_data:
                continue

            kwargs = {}
            for arg in worker_data["args"]:
                kwargs[arg] = locals().get(arg)

            await task.kiq(**kwargs)

        logger.info(f"[{job_id}] Task '{task_name}' finished successfully.")

    except Exception as e:
        logger.error(f"[{job_id}] Error in '{task_name}' task: {e}")
        await redis_client.json().set(job_id, "$.status", "failed")
        await redis_client.json().set(
            job_id, "$.task_error", f"Error in {task_name}: {e}"
        )