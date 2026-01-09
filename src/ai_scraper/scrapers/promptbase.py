from ..core.base_scraper import BaseScraper
from ..utils.logging import logger

class PromptBaseScraper(BaseScraper):
    @property
    def platform_name(self) -> str:
        return "promptbase"

    async def scrape(self) -> list:
        logger.info("Scraping PromptBase (Placeholder implementation)")
        # This would require Playwright which is not in BaseScraper's get_client
        # Placeholder for now as requested
        return []
