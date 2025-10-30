# Kaggle Competition Solver

This project provides a robust, scalable system to automatically generate a `submission.csv` file for a Kaggle competition given its URL. The system is designed to be fully autonomous after the initial request.

## 1. Problem Overview

The goal is to create a system with a single entrypoint that accepts a Kaggle competition URL. This triggers a complete, unattended pipeline that:
1.  Analyzes the competition.
2.  Generates model and training code using an LLM.
3.  Executes the code in a sandboxed environment.
4.  Produces a `submission.csv` file.

A key requirement is that the system must handle high concurrency, supporting up to 50 simultaneous requests without failure.

## 2. Final Architecture: REST API + Queue-Based System

We chose a distributed, asynchronous architecture composed of a non-blocking REST API, a message queue, and independent worker processes. This design is inherently scalable, resilient, and well-suited for long-running, resource-intensive tasks.

**[TODO: Insert new architecture diagram here]**

### Components

1.  **Web Server (FastAPI):**
    *   A lightweight, high-performance ASGI web framework.
    *   Provides a single non-blocking endpoint: `/run?url=<kaggle_url>`.
    *   **Responsibilities:**
        *   Validates the incoming request.
        *   Generates a unique `job_id`.
        *   Creates a job metadata JSON object.
        *   Enqueues the job by sending it to Redis.
        *   Immediately returns the `job_id` to the client, allowing the client to poll for results.
        *   Provides another endpoint `/status/<job_id>` for polling.

2.  **Job Queue (Redis & Taskiq):**
    *   Redis is used as the message broker and result backend.
    *   Taskiq is used for creating and managing tasks.
    *   **Responsibilities:**
        *   Acts as a buffer between the web server and the workers, decoupling the two services.
        *   A List holds the queue of `job_id`s waiting to be processed.
        *   A Hash stores the job metadata JSON for each `job_id`, allowing for status tracking.
        *   Ensures job persistence. If a worker or the entire system restarts, jobs are not lost.

3.  **Worker (Taskiq Worker):**
    *   A separate process that runs the core logic. It can be scaled horizontally to handle more jobs.
    *   **Responsibilities:**
        *   Pulls a `job_id` from the Redis queue.
        *   Updates the job status to `processing`.
        *   Fetches competition data and instructions using the Kaggle API.
        *   Communicates with an LLM to generate Python code for the model.
        *   **Crucially, it spawns a Docker container to execute the untrusted code.**
        *   Monitors the container. On success, it stores the `submission.csv` path and updates the job status to `completed`.
        *   Implements a retry mechanism. If the code fails, it logs the error, increments an attempt counter, and re-enqueues the job if the maximum number of attempts has not been reached. If it has, the status is set to `failed`.

4.  **Code Execution Environment (Docker):**
    *   Provides a sandboxed environment for running the LLM-generated code.
    *   **Responsibilities:**
        *   Isolates the execution from the host system, preventing security risks.
        *   Manages dependencies by installing the required libraries specified by the LLM or a standard set of data science libraries.
        *   Ensures that the execution environment is clean and reproducible for every job.

### API Response Structure

The `/status/{job_id}` endpoint returns a consistent JSON object defined by the `StatusResponse` Pydantic model in `app/schemas/status.py`:

```python
class StatusResponse(BaseModel):
    status: str
    source: Optional[str] = None
    path: Optional[str] = None
    message: Optional[str] = None
```

*   **status:** The current status of the job (`pending`, `processing`, `completed`, `failed`).
*   **source:** The storage location of the submission file (`local` or `s3`).
*   **path:** The path to the submission file.
*   **message:** A message providing more information about the job's status.

### Why This Architecture Was Chosen

*   **Pros:**
    *   **High Scalability:** The number of workers can be increased or decreased based on the queue size, allowing the system to handle a high volume of requests.
    *   **Resilience & Fault Tolerance:** The queue ensures that jobs are not lost if a worker crashes. The retry logic handles transient errors in the generated code.
    *   **Asynchronous & Non-Blocking:** The API remains responsive to new requests, even when many jobs are being processed. Users get an immediate response and can check the status later.
    *   **Decoupling:** The API, queue, and workers are independent services. They can be developed, deployed, and scaled separately.
    *   **Security:** Running untrusted, LLM-generated code directly on a server is a major security risk. Docker containers provide a strong isolation boundary.

*   **Cons:**
    *   **Increased Complexity:** This architecture has more moving parts than a monolithic application, requiring more effort to set up and maintain (e.g., managing Redis, Docker, and multiple processes).
    *   **Requires a Message Broker:** A dependency on a service like Redis is introduced.

## 3. Alternative Architectures Considered

### a) Monolithic, Synchronous API

*   **Description:** A single web server (e.g., Flask or FastAPI) where the `/run` endpoint performs all the work in a single, blocking request-response cycle. The HTTP connection would be held open until the `submission.csv` is generated.
*   **Pros:**
    *   Simple to design and implement for a single-user, non-concurrent scenario.
*   **Cons:**
    *   **No Concurrency:** Can only process one request at a time. 50 concurrent users would overwhelm the server, and most requests would fail.
    *   **HTTP Timeouts:** Kaggle model training can take minutes or hours. This far exceeds standard HTTP timeout limits (e.g., 30-120 seconds), making this approach non-viable.
    *   **No Resilience:** If the script fails for any reason mid-process, the entire job is lost and the user receives an error with no chance for a retry.

### b) Serverless Functions (e.g., AWS Lambda)

*   **Description:** An API Gateway endpoint triggers a serverless function (like AWS Lambda) to perform the job.
*   **Pros:**
    *   Excellent auto-scaling capabilities.
    *   Pay-per-use pricing model can be cost-effective.
    *   Managed infrastructure reduces operational overhead.
*   **Cons:**
    *   **Execution Time Limits:** Major cloud providers impose a maximum execution duration (e.g., 15 minutes for AWS Lambda). This is often not long enough for serious model training.
    *   **State Management:** Long-running workflows would require a more complex setup using a service like AWS Step Functions to orchestrate multiple Lambda calls, significantly increasing complexity.
    *   **Dependency & Environment Complexity:** Packaging large data science libraries (Pandas, Scikit-learn, PyTorch/TensorFlow) and managing Docker container images for Lambda can be cumbersome.

## 4. Setup & Usage

1.  **Prerequisites:**
    *   Python 3.9+
    *   Docker
    *   Redis

2.  **Installation:**
    ```bash
    pip install -r requirements.txt
    ```

3.  **Run Services:**
    *   **Start Redis:**
        ```bash
        redis-server
        ```
    *   **Start Worker(s):**
        ```bash
        taskiq worker app.worker.main:broker
        ```
    *   **Start API Server:**
        ```bash
        uvicorn app.main:app --host 0.0.0.0 --port 8000
        ```

4.  **Run Stress Test:**
    *   To simulate 50 concurrent users:
        ```bash
        python stresstest.py
        ```
