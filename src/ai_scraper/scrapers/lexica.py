import json
from ..core.base_scraper import BaseScraper
from ..utils.logging import logger

class LexicaScraper(BaseScraper):
    @property
    def platform_name(self) -> str:
        return "lexica"

    async def scrape(self, query: str = "cyberpunk") -> list:
        logger.info(f"Scraping Lexica for query: {query}")
        results = []
        try:
            async with self.get_client() as client:
                url = f"https://lexica.art/api/v1/search?q={query}"
                response = await client.get(url)
                response.raise_for_status()
                data = response.json()

                if "images" in data:
                    for img in data["images"]:
                        results.append({
                            "prompt": img.get("prompt"),
                            "image_url": img.get("src"),
                            "metadata_json": json.dumps(img)
                        })
        except Exception as e:
            logger.error(f"Lexica scrape error: {e}")

        await self.save_items(results)
        return results
