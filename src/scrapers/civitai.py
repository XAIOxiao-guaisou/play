import httpx
import json
import os
from .core import BaseScraper
from .storage import Storage

class CivitaiScraper(BaseScraper):
    def __init__(self, proxy: str = "http://localhost:7890", output_dir: str = "data/scraped"):
        super().__init__(proxy, output_dir)
        self.storage = Storage()
        self.api_url = "https://civitai.com/api/v1/images"

    async def get_top_images(self, limit: int = 20, sort: str = "Most Reactions"):
        """
        Fetch top images from Civitai API.
        """
        self.log(f"Fetching top images from Civitai (limit={limit}, sort={sort})")

        proxies = self.get_proxy_settings()

        params = {
            "limit": limit,
            "sort": sort,
            "nsfw": "false" # Default to safe
        }

        proxy_url = None
        if proxies and "http://" in proxies:
             proxy_url = proxies["http://"]
        elif proxies and "https://" in proxies:
             proxy_url = proxies["https://"]

        async with httpx.AsyncClient(proxy=proxy_url, verify=False) as client:
            try:
                response = await client.get(self.api_url, params=params)
                response.raise_for_status()
                data = response.json()

                if "items" in data:
                    self.log(f"Found {len(data['items'])} results from Civitai.")
                    self._save_results(data["items"])
                else:
                    self.log("No items found in Civitai response.", level="WARNING")

            except Exception as e:
                self.log(f"Error fetching Civitai: {e}", level="ERROR")

    def _save_results(self, items: list):
        # Save raw JSON
        timestamp = os.urandom(4).hex()
        filename = f"civitai_top_{timestamp}.json"
        filepath = os.path.join(self.output_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

        self.log(f"Saved raw JSON to {filepath}")

        # Save to DB
        for item in items:
            meta = item.get("meta", {})
            prompt = meta.get("prompt", "")
            if not prompt:
                 # Try to fallback to description or other fields if prompt is missing in meta
                 # But typically it's in meta -> prompt
                 pass

            image_url = item.get("url", "")

            # Store more info in metadata
            item_meta = {
                "id": item.get("id"),
                "width": item.get("width"),
                "height": item.get("height"),
                "nsfw": item.get("nsfw"),
                "createdAt": item.get("createdAt"),
                "stats": item.get("stats"),
                "negativePrompt": meta.get("negativePrompt", ""),
                "cfgScale": meta.get("cfgScale"),
                "steps": meta.get("steps"),
                "sampler": meta.get("sampler"),
                "seed": meta.get("seed"),
                "model": meta.get("Model")
            }

            if prompt: # Only save if we have a prompt
                self.storage.save_prompt(
                    source="civitai",
                    prompt=prompt,
                    image_url=image_url,
                    metadata=item_meta
                )
