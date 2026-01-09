from src.scrapers.lexica import LexicaScraper
from src.scrapers.civitai import CivitaiScraper
from src.scrapers.promptbase import PromptBaseScraper
import asyncio
from loguru import logger

async def main():
    # Configure logger to stdout for demo
    logger.add("demo.log", rotation="1 MB")

    # NOTE: Set proxy to None for sandbox environment if localhost:7890 is not available.
    # The prompt asked for localhost:7890 default, so we keep it in class init,
    # but for this demo to run in sandbox (which likely doesn't have that proxy), we might need to disable it
    # or assume it's mocked.
    # However, since I cannot confirm if the user has a proxy running, I will try to run with empty proxy for now
    # to avoid connection errors if the user didn't start one.
    # The user asked for "proxy support (localhost:7890)", so the default is correct in the code.
    # But for this test script, I'll allow overriding it.

    proxy = None # Disable proxy for sandbox test unless we know it exists.
    # If the user specifically wanted to test WITH proxy, they should have it running.
    # Given I am an agent in a sandbox, I assume no external proxy is running on localhost:7890.

    logger.info("Starting Scraper Demo...")

    # 1. Lexica
    try:
        lexica = LexicaScraper(proxy=proxy)
        await lexica.search("cyberpunk city")
    except Exception as e:
        logger.error(f"Lexica demo failed: {e}")

    # 2. Civitai
    try:
        civitai = CivitaiScraper(proxy=proxy)
        await civitai.get_top_images(limit=5)
    except Exception as e:
        logger.error(f"Civitai demo failed: {e}")

    # 3. PromptBase
    try:
        promptbase = PromptBaseScraper(proxy=proxy)
        await promptbase.scrape_categories()
    except Exception as e:
        logger.error(f"PromptBase demo failed: {e}")

    logger.info("Demo completed. Check 'data/scraped' and 'data/prompts.db'.")

if __name__ == "__main__":
    asyncio.run(main())
