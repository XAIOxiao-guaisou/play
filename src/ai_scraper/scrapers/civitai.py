import json
import httpx
import asyncio
from ..core.base_scraper import BaseScraper
from ..utils.logging import logger

class CivitaiScraper(BaseScraper):
    @property
    def platform_name(self) -> str:
        return "civitai"

    async def scrape(self, limit: int = 50) -> list:
        logger.info(f"Scraping Civitai (target limit={limit})")
        results = []
        next_cursor = None
        fetched_count = 0

        # Determine how many pages/calls we need.
        # API usually returns a 'limit' number of items (default 100 or user specified).
        # We will request in chunks.
        chunk_size = 100 # Request max usually allowed to minimize calls

        async with self.get_client() as client:
            while fetched_count < limit:
                try:
                    url = "https://civitai.com/api/v1/images"
                    params = {
                        "limit": chunk_size,
                        "sort": "Most Reactions",
                        "period": "Week",
                        "nsfw": "false"
                    }
                    if next_cursor:
                        params["cursor"] = next_cursor

                    logger.debug(f"Requesting Civitai URL: {url} with params {params}")

                    try:
                        response = await client.get(url, params=params)
                        response.raise_for_status()
                        data = response.json()
                    except httpx.TimeoutException:
                        logger.error("Civitai API request timed out.")
                        break
                    except httpx.HTTPStatusError as exc:
                        logger.error(f"Civitai API error {exc.response.status_code}: {exc.response.text}")
                        if exc.response.status_code == 429:
                            logger.warning("Rate limited. Waiting 10s...")
                            await asyncio.sleep(10)
                            continue
                        break
                    except Exception as exc:
                        logger.error(f"Civitai connection error: {exc}")
                        break

                    items = data.get("items", [])
                    if not items:
                        logger.info("No more items found on Civitai.")
                        break

                    for item in items:
                        if fetched_count >= limit:
                            break

                        meta = item.get("meta") or {}

                        # Extract model name safely
                        model_name = "Unknown"
                        # Try to find model info in standard fields if available
                        # Civitai meta is often unstructured

                        item_data = {
                            "title": f"Civitai Image {item.get('id')}",
                            "prompt": meta.get("prompt", ""),
                            "negative_prompt": meta.get("negativePrompt"),
                            "image_url": item.get("url"),
                            "metadata_json": json.dumps({
                                "id": item.get("id"),
                                "sampler": meta.get("sampler"),
                                "cfgScale": meta.get("cfgScale"),
                                "steps": meta.get("steps"),
                                "seed": meta.get("seed"),
                                "model": meta.get("Model"),
                                "stats": item.get("stats"),
                                "username": item.get("username")
                            })
                        }
                        results.append(item_data)
                        fetched_count += 1

                    logger.info(f"Fetched {len(items)} items. Total: {fetched_count}/{limit}")

                    # Pagination
                    metadata = data.get("metadata", {})
                    next_cursor = metadata.get("nextCursor")
                    if not next_cursor:
                        break

                    # Respect rate limits nicely
                    await asyncio.sleep(1)

                except Exception as e:
                    logger.error(f"Civitai scrape loop error: {e}")
                    break

        if results:
            await self.save_items(results)

        return results
