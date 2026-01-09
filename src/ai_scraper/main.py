import asyncio
import sys
import os

# Ensure the root directory is in sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.ai_scraper.database.connection import db_manager
from src.ai_scraper.scrapers.lexica import LexicaScraper
from src.ai_scraper.scrapers.civitai import CivitaiScraper
from src.ai_scraper.utils.logging import setup_logger

async def main():
    logger = setup_logger()
    logger.info("Starting AI Prompt Scraper Application")

    # Initialize Database
    db_manager.init_db()

    # Run Scrapers
    # Note: In a real app, these might be triggered by CLI args or a scheduler

    # 1. Lexica
    try:
        lexica = LexicaScraper()
        await lexica.scrape(query="sci-fi city")
    except Exception as e:
        logger.error(f"Main loop error (Lexica): {e}")

    # 2. Civitai
    try:
        civitai = CivitaiScraper()
        await civitai.scrape(limit=5)
    except Exception as e:
        logger.error(f"Main loop error (Civitai): {e}")

    logger.info("Scraping finished.")

if __name__ == "__main__":
    asyncio.run(main())
