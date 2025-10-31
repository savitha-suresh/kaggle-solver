from taskiq.abc.broker import AsyncBroker

_WORKERS_DATA = {
    "process_job_queue": {
        "args": ["job_id", "competition_url"],
    },
    "kaggle_data_loader": {
        "args": ["job_id", "competition_url"],
    },
    "kaggle_scraper": {
        "args": ["job_id", "competition_id"],
    },
    "code_generator": {
        "args": ["job_id"],
    },
    "job_runner": {
        "args": ["job_id"],
    },
    "poll_runner_status": {
        "args": ["job_id", "runner_id"],
    },
}

def get_worker(broker: AsyncBroker, task_name: str) -> tuple:
    task = broker.local_task_registry.get(task_name)
    worker_data = _WORKERS_DATA.get(task_name)
    return task, worker_data