def sanitize_job_id(job_id: str) -> str:
    """Sanitizes the job ID by replacing the colon with an underscore."""
    return job_id.replace(":", "_")
