from app.workers.runners.docker import DockerRunner

class RunnerFactory:
    @staticmethod
    def get_runner(runner_name: str):
        if runner_name == "docker":
            return DockerRunner()
        else:
            raise ValueError(f"Unknown runner: {runner_name}")
