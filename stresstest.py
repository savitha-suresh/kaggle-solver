import asyncio
import httpx
import time

# Configuration
BASE_URL = "http://127.0.0.1:8000"
ENDPOINT = "/run"
# A dummy URL for testing purposes
KAGGLE_URL = "https://www.kaggle.com/c/titanic"

NUM_CONCURRENT_USERS = 50

async def make_request(client: httpx.AsyncClient, user_id: int):
    """Simulates a single user making a request to the API."""
    url = f"{BASE_URL}{ENDPOINT}"
    params = {"url": KAGGLE_URL}
    try:
        print(f"[User {user_id}] Sending request to {url}")
        response = await client.get(url, params=params, timeout=30.0)

        if 200 <= response.status_code < 300:
            job_id = response.json().get("job_id")
            print(f"[User {user_id}] Success! Status: {response.status_code}. Got job_id: {job_id}")
            return (user_id, True, response.status_code, job_id)
        else:
            print(f"[User {user_id}] Failure! Status: {response.status_code}. Response: {response.text}")
            return (user_id, False, response.status_code, response.text)

    except httpx.RequestError as e:
        print(f"[User {user_id}] Request failed: {e.__class__.__name__}")
        return (user_id, False, None, str(e))
    except Exception as e:
        print(f"[User {user_id}] An unexpected error occurred: {e}")
        return (user_id, False, None, str(e))

async def main():
    """Runs the stress test by spawning concurrent requests."""
    print(f"Starting stress test with {NUM_CONCURRENT_USERS} concurrent users...")
    start_time = time.time()

    async with httpx.AsyncClient() as client:
        tasks = [make_request(client, i + 1) for i in range(NUM_CONCURRENT_USERS)]
        results = await asyncio.gather(*tasks)

    end_time = time.time()
    duration = end_time - start_time

    print(f"\n--- Stress Test Complete in {duration:.2f} seconds ---")

    success_count = sum(1 for r in results if r[1])
    failure_count = NUM_CONCURRENT_USERS - success_count

    print(f"Total Requests: {NUM_CONCURRENT_USERS}")
    print(f"Successful:     {success_count}")
    print(f"Failed:         {failure_count}")

    if failure_count > 0:
        print("\n--- Failure Details ---")
        for result in results:
            if not result[1]:
                user_id, _, status, detail = result
                print(f"  User {user_id}: Status={status}, Detail={detail}")

if __name__ == "__main__":
    # This check is important to run the test only when the script is executed directly
    # It assumes the FastAPI server is running and accessible at BASE_URL
    print("NOTE: Ensure the FastAPI server is running before starting the test.")
    asyncio.run(main())
