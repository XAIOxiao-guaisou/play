import asyncio
import sys
import os
import argparse

# Allow running this file directly by adding project root to sys.path
# We assume this file is at src/ai_scraper/main.py
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, "../.."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.ai_scraper.database.connection import db_manager
from src.ai_scraper.scrapers.lexica import LexicaScraper
from src.ai_scraper.scrapers.civitai import CivitaiScraper
from src.ai_scraper.utils.logging import setup_logger

async def main():
    parser = argparse.ArgumentParser(description="AI Prompt Scraper")
    parser.add_argument("--scraper", type=str, choices=["lexica", "civitai", "all"], default="all", help="Which scraper to run")
    parser.add_argument("--keyword", type=str, default="sci-fi city", help="Keyword for search (Lexica)")
    parser.add_argument("--limit", type=int, default=50, help="Number of items to fetch (Civitai)")

    args = parser.parse_args()

    logger = setup_logger()
    logger.info("Starting AI Prompt Scraper Application")

    # Initialize Database
    db_manager.init_db()

    # 1. Lexica
    if args.scraper in ["lexica", "all"]:
        try:
            lexica = LexicaScraper()
            await lexica.scrape(query=args.keyword)
        except Exception as e:
            logger.error(f"Main loop error (Lexica): {e}")

    # 2. Civitai
    if args.scraper in ["civitai", "all"]:
        try:
            civitai = CivitaiScraper()
            await civitai.scrape(limit=args.limit)
        except Exception as e:
            logger.error(f"Main loop error (Civitai): {e}")

    logger.info("Scraping finished.")

if __name__ == "__main__":
    asyncio.run(main())
