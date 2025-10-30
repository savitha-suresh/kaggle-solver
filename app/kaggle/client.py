import os
import logging
import re
import asyncio
import zipfile

from kaggle.api.kaggle_api_extended import KaggleApi
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.proxy import Proxy, ProxyType
from markdownify import markdownify
from cache import AsyncLRU

from app.config import settings
from app.utils import is_valid_kaggle_url


logger = logging.getLogger(__name__)

# Global Kaggle API instance (authenticate once)
_kaggle_api: KaggleApi | None = None


async def get_kaggle_api() -> KaggleApi:
    """Get or initialize the global Kaggle API instance."""
    global _kaggle_api
    if _kaggle_api is None:
        _kaggle_api = KaggleApi()
        await asyncio.to_thread(_kaggle_api.authenticate)
        logger.info("Kaggle API authenticated successfully")
    return _kaggle_api


def extract_competition_id(url: str) -> str:
    """Extract competition ID from Kaggle URL."""
    match = re.search(r"kaggle\.com/(c|competitions)/([a-zA-Z0-9_-]+)", url)
    if not match:
        raise ValueError(f"Could not extract competition ID from URL: {url}")
    return match.group(2)


def append_url(base_url: str, path: str) -> str:
    """Append path to base URL, handling trailing slashes."""
    base_url = base_url.rstrip('/')
    return f"{base_url}/{path}"


@AsyncLRU(maxsize=32)
async def scrape_competition_details(competition_id: str) -> dict:
    """Scrape competition details using Selenium.
    
    Returns dict with 'description', 'evaluation', and 'data_details' keys.
    """
    def _scrape():
        challenge_url = f"https://www.kaggle.com/competitions/{competition_id}"
        
        options = webdriver.ChromeOptions()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        
        proxy = os.getenv("HTTP_PROXY")
        if proxy:
            logger.info(f"Using proxy: {proxy}")
            p = Proxy()
            p.proxy_type = ProxyType.MANUAL
            p.http_proxy = proxy
            p.ssl_proxy = proxy
            options.proxy = p
            options.add_argument(f"--proxy-server={proxy}")
        
        driver = None
        try:
            driver = webdriver.Chrome(options=options)
            
            # Scrape overview page
            driver.get(append_url(challenge_url, "overview"))
            wait = WebDriverWait(driver, 35)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#description")))
            
            challenge_description = driver.find_element(
                By.CSS_SELECTOR, "#description > div > div:nth-child(2)"
            ).get_attribute("innerHTML")
            
            challenge_evaluation = driver.find_element(
                By.CSS_SELECTOR, "#evaluation > div > div:nth-child(2)"
            ).get_attribute("innerHTML")
            
            # Scrape data page
            driver.get(append_url(challenge_url, "data"))
            child_div = wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, 
                    "div[data-testid='competition-detail-render-tid'] div.sc-iRTMaw.buAyFc")
                )
            )

            challenge_data_details = child_div.get_attribute("innerHTML")
            
            return {
                "description": markdownify(challenge_description),
                "evaluation": markdownify(challenge_evaluation),
                "data_details": markdownify(challenge_data_details),
            }
            
        finally:
            if driver:
                driver.quit()
    
    return await asyncio.to_thread(_scrape)


def format_instructions_for_llm(scraped_data: dict, competition_id: str) -> str:
    """Format scraped data into instructions for LLM agent."""
    instructions = f"""You are solving the Kaggle competition: {competition_id}

## Competition Description
{scraped_data['description']}

## Evaluation Criteria
{scraped_data['evaluation']}

## Data Details
{scraped_data['data_details']}

## Your Task
1. The competition data is located in: /kaggle/input
2. Analyze the data files and understand the problem
3. Build a machine learning model to make predictions
4. Generate predictions and save them as submission.csv in /kaggle/working
5. Follow the submission format specified in the evaluation criteria

Focus on creating an accurate model that performs well on the evaluation metric described above.
"""
    return instructions


async def setup_kaggle_api(job_id: str, competition_url: str) -> tuple[str, str]:
    """Setup Kaggle API, download data, and scrape instructions.
    
    Returns:
        Tuple of (llm_instructions, data_path)
    """
    # Validate URL
    if not is_valid_kaggle_url(competition_url):
        raise ValueError(f"Invalid Kaggle competition URL: {competition_url}")
    
    # Get authenticated API instance (only authenticates once)
    api = await get_kaggle_api()
    
    # Extract competition ID
    competition_id = extract_competition_id(competition_url)
    logger.info(f"[{job_id}] Processing competition: {competition_id}")
    
    # Setup data directory
    data_path = os.path.join(
        settings.competition_data_base_path, 
        competition_id
    )
    os.makedirs(data_path, exist_ok=True)

    # Download and unzip competition data if not already present
    if not os.listdir(data_path):
        logger.info(f"[{job_id}] Downloading data for '{competition_id}' to {data_path}")
        try:
            await asyncio.to_thread(
                api.competition_download_files, 
                competition_id, 
                path=data_path, 
                quiet=False
            )
            logger.info(f"[{job_id}] Kaggle data downloaded successfully.")

            # Unzip the downloaded file
            for item in os.listdir(data_path):
                if item.endswith(".zip"):
                    zip_path = os.path.join(data_path, item)
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(data_path)
                    os.remove(zip_path)
                    logger.info(f"[{job_id}] Unzipped and removed {item}")

        except Exception as e:
            logger.error(f"[{job_id}] Failed to download or unzip Kaggle data: {e}")
            # Create dummy data for testing
    else:
        logger.info(f"[{job_id}] Data for '{competition_id}' already exists at {data_path}. Skipping download.")
        
    
    # Scrape competition details
    logger.info(f"[{job_id}] Scraping competition instructions...")
    scraped_data = await scrape_competition_details(competition_id)
    
    # Format instructions for LLM
    llm_instructions = format_instructions_for_llm(scraped_data, competition_id)
    logger.info(f"[{job_id}] Instructions prepared for LLM agent")
    
    return llm_instructions, data_path
