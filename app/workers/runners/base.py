from abc import ABC, abstractmethod

class Runner(ABC):
    @abstractmethod
    async def submit_job(self, job_id: str, code: str, data_dir: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def poll_status(self, job_id: str, runner_id: str) -> tuple[str, str, str | None]:
        raise NotImplementedError

    @abstractmethod
    async def force_stop(self, job_id: str, runner_id: str):
        raise NotImplementedError
