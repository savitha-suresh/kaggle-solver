import docker
import os
import tempfile
import logging
import shutil
import asyncio
from docker.types import Mount

from app.config import settings
from app.utils import sanitize_job_id, async_write_file, async_read_file

logger = logging.getLogger(__name__)

def _get_image_tag(job_id: str) -> str:
    """Generates the Docker image tag for a given job ID."""
    sanitized_job_id = sanitize_job_id(job_id)
    return f"kaggle-solver-job:{sanitized_job_id}"


async def run_in_executor(func, *args, **kwargs):
    """Helper to run blocking Docker SDK calls asynchronously in a thread pool."""
    return await asyncio.to_thread(func, *args, **kwargs)


async def start_container(job_id: str, code: str, data_dir: str) -> str:
    """
    Builds a Docker image and starts a container to execute the given code.

    :param job_id: The unique ID for the job.
    :param code: The Python code to execute.
    :param data_dir: The path to the directory containing the Kaggle competition data.
    :return: The ID of the started container.
    :raises Exception: If Docker build or run fails.
    """
    client = docker.from_env()
    sanitized_job_id = sanitize_job_id(job_id)

    # Create a temporary directory for the Docker build context and script
    tmpdir = tempfile.mkdtemp(prefix=f"kaggle_solver_job_{sanitized_job_id}_")
    script_path = os.path.join(tmpdir, "generated_script.py")
    dockerfile_path = os.path.join(tmpdir, "Dockerfile")

    # Write the generated code and Dockerfile to the temp directory
    await async_write_file(script_path, code)
    
    dockerfile_template = await async_read_file("app/worker/Dockerfile.template")
    await async_write_file(dockerfile_path, dockerfile_template)

    image_tag = _get_image_tag(job_id)
    container_name = f"job-container-{sanitized_job_id}"

    # Define the persistent submission output directory
    submission_output_dir = os.path.abspath(os.path.join(settings.submissions_base_path, sanitized_job_id))
    os.makedirs(submission_output_dir, exist_ok=True)
    data_dir = os.path.abspath(data_dir)

    try:
        logger.info(f"[{job_id}] Building Docker image: {image_tag}")
        image, build_logs = await run_in_executor(
            client.images.build,
            path=tmpdir,
            tag=image_tag,
            rm=True,  # Remove intermediate containers
            forcerm=True  # Force remove intermediate containers
        )
        logger.info(f"[{job_id}] Docker image built successfully: {image.id}")

        logger.info(f"[{job_id}] Running container: {container_name}")
        
        # Mount for input data (read-only)
        input_mount = Mount(target="/kaggle/input", source=data_dir, type='bind', read_only=True)
        # Mount for output submission (read-write)
        working_mount = Mount(target="/kaggle/working", source=submission_output_dir, type='bind')

        container = await run_in_executor(
            client.containers.run,
            image=image_tag,
            name=container_name,
            mounts=[input_mount, working_mount],
            environment={"JOB_ID": job_id},  # Pass job_id as env var
            detach=True,  # Run in detached mode
            remove=False,  # Don't auto-remove so we can get logs
            nano_cpus=int(settings.docker_cpu_limit) * 10**9,
            mem_limit=settings.docker_memory_limit
        )
        logger.info(f"[{job_id}] Container {container.id} started successfully.")
        return container.id

    except docker.errors.BuildError as e:
        logger.error(f"[{job_id}] Docker build failed: {e}")
        raise Exception(f"Docker build failed: {str(e)}")
    except docker.errors.ContainerError as e:
        logger.error(f"[{job_id}] Docker container error: {e}")
        raise Exception(f"Container error: {str(e)}")
    except docker.errors.APIError as e:
        logger.error(f"[{job_id}] Docker API error: {e}")
        raise Exception(f"Docker API error: {str(e)}")
    except Exception as e:
        logger.error(f"[{job_id}] Unexpected error during Docker execution: {e}", exc_info=True)
        raise
    finally:
        # Clean up the temporary build context directory
        try:
            if os.path.exists(tmpdir):
                shutil.rmtree(tmpdir)
                logger.debug(f"[{job_id}] Cleaned up temporary build directory: {tmpdir}")
        except Exception as e:
            logger.warning(f"[{job_id}] Failed to remove temporary build directory {tmpdir}: {e}")


async def get_container_status_and_logs(job_id: str, container_id: str) -> tuple[str, str, str | None]:
    """
    Checks the status of a Docker container, retrieves its logs, and cleans it up if finished.

    :param job_id: The unique ID for the job.
    :param container_id: The ID of the container to check.
    :return: A tuple containing:
             - str: "running", "exited_success", or "exited_error".
             - str: The container logs.
             - str | None: Path to submission.csv if successful, else None.
    """
    client = docker.from_env()
    sanitized_job_id = sanitize_job_id(job_id)
    submission_output_dir = os.path.join(settings.submissions_base_path, sanitized_job_id)
    submission_file_path = os.path.join(submission_output_dir, "submission.csv")

    try:
        # Get container and reload to get latest status
        container = await run_in_executor(client.containers.get, container_id)
        await run_in_executor(container.reload)

        status = container.status
        logger.info(f"[{job_id}] Container {container_id} status: {status}")

        if status == 'running':
            logger.info(f"[{job_id}] Container is still running.")
            return "running", "", None
        
        # Container has stopped, get logs
        logs_bytes = await run_in_executor(container.logs, stdout=True, stderr=True)
        logs = logs_bytes.decode('utf-8', errors='replace')
        
        # Get exit code
        exit_code = container.attrs['State']['ExitCode']
        logger.info(f"[{job_id}] Container exited with code: {exit_code}")
        logger.debug(f"[{job_id}] Container logs:\n{logs}")

        # Check if submission file was created
        if exit_code == 0:
            if os.path.exists(submission_file_path):
                logger.info(f"[{job_id}] Submission file found: {submission_file_path}")
                return "exited_success", logs, submission_file_path
            else:
                logger.warning(f"[{job_id}] Container exited successfully but no submission.csv found")
                return "exited_error", logs + "\n[Error: No submission.csv generated]", None
        else:
            logger.error(f"[{job_id}] Container exited with error code: {exit_code}")
            return "exited_error", logs, None

    except docker.errors.NotFound:
        logger.warning(f"[{job_id}] Container {container_id} not found.")
        return "exited_error", "Container not found. It may have been removed.", None
    except Exception as e:
        logger.error(f"[{job_id}] Error checking container status: {e}", exc_info=True)
        return "exited_error", f"Error checking container status: {str(e)}", None
    finally:
        # Clean up container if it's not running
        await cleanup_container(job_id, container_id, client)

async def cleanup_container(job_id: str, container_id: str, client: docker.DockerClient = None):
    """
    Remove a stopped container and optionally its image.
    
    :param job_id: The unique ID for the job.
    :param container_id: The ID of the container to clean up.
    :param client: Docker client instance (creates new one if not provided).
    """
    if client is None:
        client = docker.from_env()
    
    try:
        container = await run_in_executor(client.containers.get, container_id)
        
        # Only remove if not running
        if container.status != 'running':
            await run_in_executor(container.remove, force=True)
            logger.info(f"[{job_id}] Removed container: {container_id}")
            
            #Optionally remove the image (commented out by default as it can be slow)
            image_tag = _get_image_tag(job_id)
            try:
                await run_in_executor(client.images.remove, image_tag, force=True)
                logger.info(f"[{job_id}] Removed image: {image_tag}")
            except Exception as e:
                logger.warning(f"[{job_id}] Could not remove image {image_tag}: {e}")
        else:
            logger.info(f"[{job_id}] Container is still running, skipping cleanup")
            
    except docker.errors.NotFound:
        logger.debug(f"[{job_id}] Container {container_id} already removed")
    except Exception as e:
        logger.warning(f"[{job_id}] Error during container cleanup: {e}")


async def cleanup_container_force(job_id: str, container_id: str):
    """
    Forcefully stops and removes a container and its image.
    """
    client = docker.from_env()
    try:
        container = await run_in_executor(client.containers.get, container_id)
        logger.info(f"[{job_id}] Forcefully stopping and removing container {container_id}.")
        await run_in_executor(container.remove, force=True)
        logger.info(f"[{job_id}] Removed container: {container_id}")

        image_tag = _get_image_tag(job_id)
        try:
            await run_in_executor(client.images.remove, image_tag, force=True)
            logger.info(f"[{job_id}] Removed image: {image_tag}")
        except Exception as e:
            logger.warning(f"[{job_id}] Could not remove image {image_tag}: {e}")

    except docker.errors.NotFound:
        logger.warning(f"[{job_id}] Container {container_id} not found for forced cleanup.")
    except Exception as e:
        logger.error(f"[{job_id}] Error during forceful container cleanup: {e}", exc_info=True)


async def stop_container(job_id: str, container_id: str, timeout: int = 10):
    """
    Stop a running container gracefully.
    
    :param job_id: The unique ID for the job.
    :param container_id: The ID of the container to stop.
    :param timeout: Seconds to wait before killing the container.
    """
    client = docker.from_env()
    
    try:
        container = await run_in_executor(client.containers.get, container_id)
        logger.info(f"[{job_id}] Stopping container {container_id}...")
        await run_in_executor(container.stop, timeout=timeout)
        logger.info(f"[{job_id}] Container stopped successfully")
        
        # Clean up after stopping
        await cleanup_container(job_id, container_id, client)
        
    except docker.errors.NotFound:
        logger.warning(f"[{job_id}] Container {container_id} not found")
    except Exception as e:
        logger.error(f"[{job_id}] Error stopping container: {e}", exc_info=True)
        raise