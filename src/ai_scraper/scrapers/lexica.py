import json
import httpx
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
                url = f"https://lexica.art/api/v1/search"
                params = {"q": query}

                try:
                    response = await client.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()
                except httpx.TimeoutException:
                    logger.error("Lexica API request timed out.")
                    return []
                except httpx.HTTPStatusError as exc:
                    logger.error(f"Lexica API error {exc.response.status_code}: {exc.response.text}")
                    return []
                except Exception as exc:
                    logger.error(f"Lexica connection error: {exc}")
                    return []

                if "images" in data:
                    logger.info(f"Found {len(data['images'])} images from Lexica.")
                    for img in data["images"]:
                        # Lexica 'prompt' field usually contains the full prompt
                        # 'src' is the image URL
                        # 'guidance', 'model', etc are in the root of the img object

                        item_data = {
                            "title": f"Lexica: {query}",
                            "prompt": img.get("prompt", ""),
                            "negative_prompt": img.get("negative_prompt", ""), # Lexica API sometimes has this
                            "image_url": img.get("src"),
                            "metadata_json": json.dumps({
                                "width": img.get("width"),
                                "height": img.get("height"),
                                "guidance": img.get("guidance"),
                                "model": img.get("model"),
                                "nsfw": img.get("nsfw"),
                                "site_id": img.get("id")
                            })
                        }
                        results.append(item_data)
                else:
                    logger.warning("No 'images' field in Lexica response.")

        except Exception as e:
            logger.error(f"Lexica scrape unhandled error: {e}")

        if results:
            await self.save_items(results)

        return results
