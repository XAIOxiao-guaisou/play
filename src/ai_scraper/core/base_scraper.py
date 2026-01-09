import httpx
from abc import ABC, abstractmethod
from typing import List, Dict, Any
from ..database.connection import db_manager
from ..database.models import PromptItem
from .proxy import ProxyManager
from ..utils.logging import logger

class BaseScraper(ABC):
    def __init__(self, proxy_manager: ProxyManager = None):
        self.proxy_manager = proxy_manager or ProxyManager()
        self.db = db_manager

    @property
    def platform_name(self) -> str:
        """Name of the platform (e.g., 'lexica')."""
        raise NotImplementedError

    def get_client(self) -> httpx.AsyncClient:
        """Return an httpx AsyncClient with proxy configured."""
        proxy = self.proxy_manager.get_httpx_proxy()
        # verify=False is often needed for proxies, though insecure
        return httpx.AsyncClient(proxy=proxy, verify=False, timeout=30.0)

    @abstractmethod
    async def scrape(self, **kwargs) -> List[Dict[str, Any]]:
        """
        Main scraping logic.
        Should return a list of dictionaries ready to be converted to PromptItems.
        """
        pass

    async def save_items(self, items: List[Dict[str, Any]]):
        """Save scraped items to the database."""
        if not items:
            return

        with self.db.get_session() as session:
            count = 0
            for item in items:
                # Basic validation or transformation could happen here
                try:
                    prompt_item = PromptItem(
                        source_platform=self.platform_name,
                        title=item.get("title"),
                        prompt=item.get("prompt", ""),
                        negative_prompt=item.get("negative_prompt"),
                        image_url=item.get("image_url"),
                        metadata_json=item.get("metadata_json")
                    )
                    session.add(prompt_item)
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to create PromptItem: {e}")
            logger.info(f"Saved {count} items for {self.platform_name}")
