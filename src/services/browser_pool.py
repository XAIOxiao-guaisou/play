"""Browser Pool - Playwright browser instance pooling service.

Provides efficient reuse of Browser instances to reduce the cost of
frequent browser launches. Implements a singleton pool pattern with
reference counting and async context management.

Note:
    - Currently implements minimal viable single-instance pool.
    - BaseSpider uses its own session management; this pool is for new executors.
    - Maintains existing Session semantics and lifecycle management.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, Dict, Optional

from loguru import logger
from playwright.async_api import async_playwright, Browser, Playwright


class BrowserPool:
    _lock = asyncio.Lock()
    _playwright: Optional[Playwright] = None
    _browser: Optional[Browser] = None
    _ref: int = 0

    @classmethod
    @asynccontextmanager
    async def acquire(cls, launch_kwargs: Dict[str, Any]) -> AsyncIterator[Browser]:
        async with cls._lock:
            if cls._playwright is None:
                cls._playwright = await async_playwright().start()
            if cls._browser is None:
                cls._browser = await cls._playwright.chromium.launch(**launch_kwargs)
                logger.info("[BrowserPool] 已启动共享 Browser")
            cls._ref += 1

        try:
            yield cls._browser
        finally:
            async with cls._lock:
                cls._ref = max(0, cls._ref - 1)

    @classmethod
    async def shutdown(cls) -> None:
        async with cls._lock:
            if cls._browser:
                try:
                    await cls._browser.close()
                except Exception:
                    pass
                cls._browser = None
            if cls._playwright:
                try:
                    await cls._playwright.stop()
                except Exception:
                    pass
                cls._playwright = None
            cls._ref = 0
            logger.info("[BrowserPool] 已关闭共享 Browser")
