import time
import requests
import sys
import logging
import os

# Configure basic logging for the client
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

API_BASE_URL = "http://127.0.0.1:8000"
POLL_INTERVAL_SECONDS = 60
DOWNLOAD_DIR = "./downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def main(kaggle_url: str):
    """
    Client script to submit a job and poll for its result.
    """
    # 1. Submit the job
    job_id = None
    try:
        logging.info(f"Submitting job for URL: {kaggle_url}")
        response = requests.post(f"{API_BASE_URL}/run", params={"url": kaggle_url}, timeout=30)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        result = response.json()
        job_id = result.get("job_id")
        if not job_id:
            logging.error("Failed to get job_id from server.")
            return

        logging.info(f"Job submitted successfully. Got job_id: {job_id}")

    except requests.RequestException as e:
        logging.error(f"Error submitting job: {e}")
        return
    except Exception as e:
        logging.error(f"An unexpected error occurred during submission: {e}")
        return

    # 2. Poll for the result
    logging.info("Polling for job status...")
    while True:
        try:
            status_response = requests.get(f"{API_BASE_URL}/status/{job_id}", timeout=30)
            status_response.raise_for_status()

            status_data = status_response.json()
            status = status_data.get("status")

            logging.info(f"Current job status: {status.upper()}")

            if status == "success":
                logging.info("\n--- Job Completed Successfully! ---")
                source = status_data.get("source")
                path = status_data.get("path")
                logging.info(f"Submission file is available at source: '{source}' at path: {path}")
                break
            
            if status == "failed":
                logging.error("\n--- Job Failed ---")
                message = status_data.get("message")
                logging.error(f"Failure message: {message}")
                break
            
        except requests.RequestException as e:
            logging.error(f"Error polling for status: {e}")
        except Exception as e:
            logging.error(f"An unexpected error occurred during polling: {e}")

        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python client.py <kaggle_competition_url>")
        sys.exit(1)
    
    url = sys.argv[1]
    main(url)
