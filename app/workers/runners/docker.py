from app.workers.runners.base import Runner
from app.workers.docker_utils import start_container, get_container_status_and_logs, cleanup_container_force

class DockerRunner(Runner):
    async def submit_job(self, job_id: str, code: str, data_dir: str) -> str:
        return await start_container(job_id, code, data_dir)

    async def poll_status(self, job_id: str, runner_id: str) -> tuple[str, str, str | None]:
        return await get_container_status_and_logs(job_id, runner_id)

    async def force_stop(self, job_id: str, runner_id: str):
        await cleanup_container_force(job_id, runner_id)
