import json
from ..core.base_scraper import BaseScraper
from ..utils.logging import logger

class CivitaiScraper(BaseScraper):
    @property
    def platform_name(self) -> str:
        return "civitai"

    async def scrape(self, limit: int = 10) -> list:
        logger.info(f"Scraping Civitai (limit={limit})")
        results = []
        try:
            async with self.get_client() as client:
                url = "https://civitai.com/api/v1/images"
                params = {"limit": limit, "sort": "Most Reactions", "nsfw": "false"}
                response = await client.get(url, params=params)
                response.raise_for_status()
                data = response.json()

                if "items" in data:
                    for item in data["items"]:
                        meta = item.get("meta") or {}
                        results.append({
                            "prompt": meta.get("prompt", ""),
                            "negative_prompt": meta.get("negativePrompt"),
                            "image_url": item.get("url"),
                            "title": f"Civitai Image {item.get('id')}",
                            "metadata_json": json.dumps(item)
                        })
        except Exception as e:
            logger.error(f"Civitai scrape error: {e}")

        await self.save_items(results)
        return results
