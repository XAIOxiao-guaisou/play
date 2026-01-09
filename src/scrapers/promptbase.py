from playwright.async_api import async_playwright
import os
import json
from .core import BaseScraper
from .storage import Storage

class PromptBaseScraper(BaseScraper):
    def __init__(self, proxy: str = "http://localhost:7890", output_dir: str = "data/scraped"):
        super().__init__(proxy, output_dir)
        self.storage = Storage()
        self.base_url = "https://promptbase.com"

    async def scrape_categories(self):
        """
        Navigate PromptBase and extract category/title metadata.
        """
        self.log(f"Starting PromptBase scraping: {self.base_url}")

        proxy_settings = None
        if self.proxy:
             proxy_settings = {"server": self.proxy}

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True, proxy=proxy_settings)
            page = await browser.new_page()

            try:
                # Go to Marketplace which lists categories or prompts
                # For demo purposes, we'll visit the marketplace page
                await page.goto(f"{self.base_url}/marketplace", timeout=60000)
                await page.wait_for_load_state("networkidle")

                # Extract prompt cards
                # Selectors are hypothetical and need adjustment based on real site structure.
                # Assuming cards have titles and maybe categories.

                # Check if we have cards
                cards = await page.locator("div.marketplace-card").all() # Hypothetical class

                # If hypothetical class doesn't work, let's try a more generic approach or assume structure
                # Since I cannot see the live site, I will use a generic extraction strategy
                # looking for common elements like 'a' tags with titles.

                # Let's try to find links that look like prompts
                links = await page.locator("a[href^='/prompt/']").all()
                self.log(f"Found {len(links)} potential prompt links.")

                results = []
                for link in links[:20]: # Limit to 20 for now
                    title = await link.text_content()
                    href = await link.get_attribute("href")

                    if title and href:
                        item = {
                            "title": title.strip(),
                            "url": f"{self.base_url}{href}",
                            "source": "promptbase"
                        }
                        results.append(item)

                        # Save to DB
                        self.storage.save_prompt(
                            source="promptbase",
                            prompt=title.strip(), # PromptBase usually sells prompts, so title might be the description or partial prompt
                            image_url=None, # Image might need deeper scraping
                            metadata={"url": item["url"]}
                        )

                self._save_results(results)

            except Exception as e:
                self.log(f"Error scraping PromptBase: {e}", level="ERROR")
                # Take screenshot on error
                screenshot_path = os.path.join(self.output_dir, "promptbase_error.png")
                await page.screenshot(path=screenshot_path)
                self.log(f"Screenshot saved to {screenshot_path}")
            finally:
                await browser.close()

    def _save_results(self, items: list):
        timestamp = os.urandom(4).hex()
        filename = f"promptbase_categories_{timestamp}.json"
        filepath = os.path.join(self.output_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(items, f, ensure_ascii=False, indent=2)

        self.log(f"Saved results to {filepath}")
