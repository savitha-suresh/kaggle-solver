
import logging
from datetime import datetime

import redis.asyncio as redis
from taskiq import Context, TaskiqDepends

from app.config import settings
from app.kaggle.client import download_kaggle_data
from app.logging_config import setup_logging
from app.tasks_dg import TASKS_DG
from app.workers.dependencies import get_redis_client, get_kaggle_api
from kaggle.api.kaggle_api_extended import KaggleApi
from app.workers.worker_manager import get_worker
from app.workers.broker_config import broker

setup_logging()
logger = logging.getLogger(__name__)


@broker.task(task_name="kaggle_data_loader")
async def kaggle_data_loader(
    job_id: str,
    competition_url: str,
    context: Context = TaskiqDepends(),
    redis_client: redis.Redis = TaskiqDepends(get_redis_client),
    kaggle_api: KaggleApi = TaskiqDepends(get_kaggle_api),
):
    """Task to download Kaggle data for a given competition."""
    task_name = context.message.task_name
    logger.info(f"[{job_id}] Task '{task_name}' started.")
    await redis_client.json().set(job_id, "$.current_task", task_name)

    try:
        await redis_client.json().set(job_id, "$.status", "processing")
        await redis_client.json().set(job_id, "$.processed_at", datetime.utcnow().isoformat())

        competition_id, data_path = await download_kaggle_data(
            job_id,
            competition_url,
            redis_client,
            kaggle_api,
        )
        await redis_client.json().set(job_id, "$.competition_id", competition_id)
        await redis_client.json().set(job_id, "$.data_path", data_path)

        next_tasks = TASKS_DG.get(task_name, [])
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

