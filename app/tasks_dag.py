TASKS_DAG = {
    "process_job_queue": ["kaggle_data_loader"],
    "kaggle_data_loader": ["kaggle_scraper"],
    "kaggle_scraper": ["code_generator"],
    "code_generator": ["job_runner"],
    "job_runner": ["poll_container_status"],
    "poll_container_status": [],
}