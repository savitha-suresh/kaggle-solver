import logging
import os

import redis.asyncio as redis
from taskiq import Context, TaskiqDepends

from app.config import settings
from app.kaggle.client import (
    scrape_competition_details,
    format_instructions_for_llm,
)
from app.logging_config import setup_logging
from app.tasks_dag import TASKS_DAG
from app.workers.dependencies import get_redis_client, get_kaggle_api
from app.workers.worker_manager import get_worker
from app.workers.broker_config import broker
from app.utils import async_write_file

setup_logging()
logger = logging.getLogger(__name__)


@broker.task(task_name="kaggle_scraper")
async def kaggle_scraper(
    job_id: str,
    competition_id: str,
    context: Context = TaskiqDepends(),
    redis_client: redis.Redis = TaskiqDepends(get_redis_client),
    kaggle_api=TaskiqDepends(get_kaggle_api),
):
    """Task to scrape Kaggle competition instructions."""
    task_name = context.message.task_name
    logger.info(f"[{job_id}] Task '{task_name}' started.")
    await redis_client.json().set(job_id, "$.current_task", task_name)

    try:
        instructions_path = os.path.join(
            settings.instructions_dir, competition_id, "instructions.md"
        )

        async with redis_client.lock(
            f"lock:scrape:{competition_id}", timeout=settings.scrape_lock_timeout
        ):
            if not os.path.exists(instructions_path):
                scraped_data = await scrape_competition_details(competition_id)
                instructions = format_instructions_for_llm(
                    scraped_data, competition_id
                )

                os.makedirs(os.path.dirname(instructions_path), exist_ok=True)
                await async_write_file(instructions_path, instructions)

                logger.info(
                    f"[{job_id}] Scraped and saved instructions for {competition_id}"
                )

        await redis_client.json().set(
            job_id, "$.instruction_path", instructions_path
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
        await redis_client.json().set(
            job_id, "$.task_error", f"Error in {task_name}: {e}"
        )