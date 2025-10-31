"""
Standalone script to scrape Kaggle competition details.
Usage: python scrape_kaggle.py <competition_id>
Example: python scrape_kaggle.py titanic
"""

import os
import sys
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.proxy import Proxy, ProxyType
from markdownify import markdownify


def append_url(base_url: str, path: str) -> str:
    """Append path to base URL, handling trailing slashes."""
    base_url = base_url.rstrip('/')
    return f"{base_url}/{path}"


def scrape_competition_details_sync(competition_id: str) -> dict:
    """
    Scrape competition details from Kaggle using Selenium.
    
    Args:
        competition_id: Kaggle competition ID (e.g., 'titanic')
        
    Returns:
        Dictionary with 'description', 'evaluation', and 'data_details' keys
    """
    challenge_url = f"https://www.kaggle.com/competitions/{competition_id}"
    
    # Setup Chrome options
    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    
    # Setup proxy if available
    proxy = os.getenv("HTTP_PROXY")
    if proxy:
        print(f"Using proxy: {proxy}")
        p = Proxy()
        p.proxy_type = ProxyType.MANUAL
        p.http_proxy = proxy
        p.ssl_proxy = proxy
        options.proxy = p
        options.add_argument(f"--proxy-server={proxy}")
    
    driver = None
    try:
        print(f"Starting Chrome driver...")
        driver = webdriver.Chrome(options=options)
        
        # --- Scrape Description and Evaluation from Overview Page ---
        print(f"Navigating to: {append_url(challenge_url, 'overview')}")
        driver.get(append_url(challenge_url, "overview"))
        
        wait = WebDriverWait(driver, 35)
        print("Waiting for description element...")
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "#description")))
        
        print("Extracting description...")
        challenge_description = driver.find_element(
            By.CSS_SELECTOR, "#description > div > div:nth-child(2)"
        ).get_attribute("innerHTML")
        
        print("Extracting evaluation criteria...")
        challenge_evaluation = driver.find_element(
            By.CSS_SELECTOR, "#evaluation > div > div:nth-child(2)"
        ).get_attribute("innerHTML")
        
        # --- Scrape Data Details from Data Page ---
        print(f"Navigating to: {append_url(challenge_url, 'data')}")
        driver.get(append_url(challenge_url, "data"))
        
        print("Waiting for data details element...")
        child_div = wait.until(
                    EC.presence_of_element_located(
        (By.CSS_SELECTOR, 
         "div[data-testid='competition-detail-render-tid'] div.sc-iRTMaw.buAyFc")
            )
        )
                
        
        print("Extracting data details...")
        challenge_data_details = child_div.get_attribute("innerHTML")
        
        
        # Convert HTML to Markdown
        print("Converting HTML to Markdown...")
        scraped_data = {
            "description": markdownify(challenge_description),
            "evaluation": markdownify(challenge_evaluation),
            "data_details": markdownify(challenge_data_details),
        }
        
        print("✅ Successfully scraped competition details!")
        return scraped_data
        
    except Exception as e:
        print(f"❌ Error scraping competition details: {e}")
        raise
    finally:
        if driver:
            print("Closing browser...")
            driver.quit()


def format_instructions_for_llm_sync(scraped_data: dict, competition_id: str) -> str:
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


def save_to_files(scraped_data: dict, competition_id: str, output_dir: str = "./output"):
    """Save scraped data to individual markdown files."""
    os.makedirs(output_dir, exist_ok=True)
    
    for key, value in scraped_data.items():
        filename = f"{competition_id}_{key}.md"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(value)
        print(f"Saved: {filepath}")
    
    # Also save the formatted instructions
    instructions = format_instructions_for_llm_sync(scraped_data, competition_id)
    instructions_path = os.path.join(output_dir, f"{competition_id}_instructions.md")
    with open(instructions_path, "w", encoding="utf-8") as f:
        f.write(instructions)
    print(f"Saved: {instructions_path}")


def main():
    if len(sys.argv) < 2:
        print("Usage: python scrape_kaggle.py <competition_id>")
        print("Example: python scrape_kaggle.py titanic")
        sys.exit(1)
    
    competition_id = sys.argv[1]
    
    print(f"\n{'='*60}")
    print(f"Scraping Kaggle Competition: {competition_id}")
    print(f"{'='*60}\n")
    
    try:
        # Scrape the competition
        scraped_data = scrape_competition_details_sync(competition_id)
        
        # Save to files
        save_to_files(scraped_data, competition_id)
        
        print(f"\n{'='*60}")
        print("✅ Scraping completed successfully!")
        print(f"{'='*60}\n")
        
        # Print preview
        print("\n--- Description Preview (first 500 chars) ---")
        print(scraped_data['description'][:500] + "...")
        
    except Exception as e:
        print(f"\n{'='*60}")
        print(f"❌ Error: {e}")
        print(f"{'='*60}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()


