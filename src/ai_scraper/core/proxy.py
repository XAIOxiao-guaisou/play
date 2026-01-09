from typing import Optional, Dict

class ProxyManager:
    def __init__(self, proxy_url: str = "http://127.0.0.1:7890"):
        self.default_proxy = proxy_url

    def get_proxy(self) -> Optional[str]:
        """Return the proxy string."""
        return self.default_proxy

    def get_httpx_proxy(self) -> Optional[str]:
        """Return proxy formatted for httpx (single string in recent versions or dict)."""
        return self.default_proxy

    def get_playwright_proxy(self) -> Optional[Dict[str, str]]:
        """Return proxy formatted for playwright."""
        if not self.default_proxy:
            return None
        return {"server": self.default_proxy}
