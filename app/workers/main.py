
import os
import logging
import sys

import redis.asyncio as redis
from taskiq import TaskiqDepends, Context

from app.config import settings
from app.logging_config import setup_logging
from app.tasks_dag import TASKS_DAG
from app.workers.dependencies import get_redis_client
from app.workers.worker_manager import get_worker
from app.workers.broker_config import broker


from .kaggle_data_loader import kaggle_data_loader
from .kaggle_scraper import kaggle_scraper
from .code_generator import code_generator
from .job_runner import job_runner
from .poll_runner_status import poll_runner_status

# --- Setup ---
setup_logging()
logger = logging.getLogger(__name__)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))



# --- Taskiq Tasks ---
@broker.task(task_name="process_job_queue")
async def process_job(
    job_id: str,
    competition_url: str,
    context: Context = TaskiqDepends(),
    redis_client: redis.Redis = TaskiqDepends(get_redis_client),
):
    """Taskiq task to process a Kaggle competition job."""
    task_name = context.message.task_name
    logger.info(f"[{job_id}] Task '{task_name}' started.")
    await redis_client.json().set(job_id, "$.current_task", task_name)

    try:
        next_tasks = TASKS_DAG.get(task_name, [])
        for next_task_name in next_tasks:
            task, worker_data = get_worker(broker, next_task_name)
            if not task or not worker_data:
                logger.error(f"[{job_id}] Worker for task '{next_task_name}' not found.")
                print(task, worker_data)
                continue
            # Since we use locals(), i have not abstracted this into a function
            kwargs = {}
            for arg in worker_data["args"]:
                kwargs[arg] = locals().get(arg)

            await task.kiq(**kwargs)

    except Exception as e:
        logger.error(f"[{job_id}] Error in '{task_name}' task: {e}", exc_info=True)
        await redis_client.json().set(job_id, "$.status", "failed")
        await redis_client.json().set(
            job_id, "$.task_error", f"Error in {task_name}: {e}"
        )

