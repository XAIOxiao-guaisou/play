from typing import Optional
from loguru import logger
import os

class BaseScraper:
    def __init__(self, proxy: str = "http://localhost:7890", output_dir: str = "data/scraped"):
        self.proxy = proxy
        self.output_dir = output_dir
        self._setup_output_dir()

    def _setup_output_dir(self):
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

    def get_proxy_settings(self) -> dict:
        """Return proxy settings formatted for httpx or playwright."""
        if not self.proxy:
            return {}
        return {
            "http://": self.proxy,
            "https://": self.proxy
        }

    def log(self, message: str, level: str = "INFO"):
        """Wrapper for logging."""
        if level == "INFO":
            logger.info(message)
        elif level == "ERROR":
            logger.error(message)
        elif level == "WARNING":
            logger.warning(message)
        elif level == "DEBUG":
            logger.debug(message)
