import httpx
import json
import os
from .core import BaseScraper
from .storage import Storage

class LexicaScraper(BaseScraper):
    def __init__(self, proxy: str = "http://localhost:7890", output_dir: str = "data/scraped"):
        super().__init__(proxy, output_dir)
        self.storage = Storage()
        self.api_url = "https://lexica.art/api/v1/search"

    async def search(self, query: str):
        """
        Search Lexica.art for images and prompts.
        """
        self.log(f"Searching Lexica for: {query}")

        proxies = self.get_proxy_settings()

        # httpx 0.28+ uses 'proxy' instead of 'proxies', but 'proxies' might be used if dict.
        # However, checking the error log 'unexpected keyword argument proxies', it seems we should use 'proxy' or mount it.
        # If proxies is a dict, we might need to pick one or pass it as 'proxy' if it supports it,
        # but httpx 0.28 deprecated 'proxies'. It wants 'proxy' (string) or 'mounts'.
        # For simplicity, if we have a single proxy in settings, use it.

        proxy_url = None
        if proxies and "http://" in proxies:
             proxy_url = proxies["http://"]
        elif proxies and "https://" in proxies:
             proxy_url = proxies["https://"]

        # Note: If proxy_url is None, it won't use proxy.

        async with httpx.AsyncClient(proxy=proxy_url, verify=False) as client:
            try:
                response = await client.get(self.api_url, params={"q": query})
                response.raise_for_status()
                data = response.json()

                if "images" in data:
                    self.log(f"Found {len(data['images'])} results from Lexica.")
                    self._save_results(data["images"], query)
                else:
                    self.log("No images found in Lexica response.", level="WARNING")

            except Exception as e:
                self.log(f"Error searching Lexica: {e}", level="ERROR")

    def _save_results(self, images: list, query: str):
        # Save raw JSON
        timestamp = os.urandom(4).hex()
        filename = f"lexica_{query.replace(' ', '_')}_{timestamp}.json"
        filepath = os.path.join(self.output_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(images, f, ensure_ascii=False, indent=2)

        self.log(f"Saved raw JSON to {filepath}")

        # Save to DB
        for img in images:
            prompt = img.get("prompt", "")
            image_url = img.get("src", "")
            meta = {
                "width": img.get("width"),
                "height": img.get("height"),
                "guidance": img.get("guidance"),
                "model": img.get("model"),
                "nsfw": img.get("nsfw"),
                "query": query
            }
            self.storage.save_prompt(
                source="lexica",
                prompt=prompt,
                image_url=image_url,
                metadata=meta
            )
