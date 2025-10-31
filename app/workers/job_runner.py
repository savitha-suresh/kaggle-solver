import logging

import redis.asyncio as redis
from taskiq import Context, TaskiqDepends

from app.logging_config import setup_logging
from app.storage.base import BaseStorage
from app.tasks_dag import TASKS_DAG
from app.workers.dependencies import get_redis_client, get_storage_client
from app.workers.broker_config import broker
from app.workers.worker_manager import get_worker
from app.workers.runners.factory import RunnerFactory
from app.config import settings

setup_logging()
logger = logging.getLogger(__name__)


@broker.task(task_name="job_runner")
async def job_runner(
    job_id: str,
    context: Context = TaskiqDepends(),
    redis_client: redis.Redis = TaskiqDepends(get_redis_client),
    storage: BaseStorage = TaskiqDepends(get_storage_client),
):
    """Task to run the generated code in a runner."""
    task_name = context.message.task_name
    logger.info(f"[{job_id}] Task '{task_name}' started.")
    await redis_client.json().set(job_id, "$.current_task", task_name)

    try:
        job_data = await redis_client.json().get(job_id)
        if not job_data:
            logger.error(f"[{job_id}] Job data not found in Redis.")
            return

        generated_code_path = job_data.get("generated_code_path")
        if not generated_code_path:
            logger.error(f"[{job_id}] Generated code path not found in Redis.")
            await redis_client.json().set(job_id, "$.status", "failed")
            await redis_client.json().set(
                job_id, "$.error", "Generated code path not found"
            )
            return

        generated_code_bytes = await storage.read_file(generated_code_path)
        generated_code = generated_code_bytes.decode("utf-8")
        data_path = job_data.get("data_path")

        runner = RunnerFactory.get_runner(settings.runner_provider)
        runner_id = await runner.submit_job(job_id, generated_code, data_path)
        await redis_client.json().set(job_id, "$.runner_id", runner_id)
        logger.info(
            f"[{job_id}] Runner {runner_id} started. Enqueuing polling task."
        )

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
        await redis_client.json().set(job_id, "$.task_error", f"Error in {task_name}: {e}")