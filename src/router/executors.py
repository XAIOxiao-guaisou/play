"""Executor functions for router engine selection.

Implements execution strategies for different crawl engines:
- Engine E: Playwright (reuses main.crawl_keywords)
- Engine D: Pyppeteer + Selenium-Wire (hybrid minimal viable mode)

Note: Hybrid mode requires Chrome/Edge driver environment;
startup failures raise clear errors.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from loguru import logger

from config import get_config
from config import project_path
from src.services.ua_service import UAService


def _resolve_edge_executable() -> str | None:
    candidates = [
        r"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
        r"C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    return None


async def crawl_keywords_playwright(keywords: List[str], debug: bool) -> Path:
    # 复用现有实现
    from main import crawl_keywords

    return await crawl_keywords(keywords, debug=debug)


async def crawl_keywords_pywire(keywords: List[str], debug: bool) -> Path:
    """混合模式：

    - Selenium-Wire: 打开页面并捕获网络请求/响应（便于抓 API）
    - Pyppeteer: 获取渲染后的 HTML/文本（便于补充动态内容）

    输出格式：与 Playwright 保持一致（json list），字段尽量对齐。
    """

    cfg = get_config()
    output_dir = project_path("output")
    output_dir.mkdir(exist_ok=True)

    items: List[Dict[str, Any]] = []
    for kw in keywords:
        logger.info(f"[PyWire] keyword={kw}")
        per_kw = await _hybrid_fetch_xhs_search(keyword=kw, headless=cfg.browser.headless)
        items.extend(per_kw)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"xhs_pywire_{timestamp}.json"
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    logger.success(f"[PyWire] 输出完成: {output_path} (count={len(items)})")
    return output_path


async def _hybrid_fetch_xhs_search(keyword: str, headless: bool) -> List[Dict[str, Any]]:
    """抓取小红书搜索页：优先从 Selenium-Wire 捕获 JSON 接口。

    这不是“稳定破解”，但能把你要求的混合框架真正跑起来，并为后续增强留入口。
    """

    base_url = get_config().xiaohongshu.base_url.rstrip("/")
    url = f"{base_url}/search_result?keyword={keyword}"

    ua = UAService.get_random()

    # 1) Selenium-Wire 侧：抓请求包
    sw_data: List[Dict[str, Any]] = []
    sw_error: str | None = None

    def selenium_wire_worker():
        nonlocal sw_data, sw_error
        try:
            from seleniumwire import webdriver  # type: ignore
            browser = (os.getenv("SELENIUM_BROWSER", "edge") or "edge").strip().lower()

            # 复用 Playwright 的持久化 profile，确保 WebUI/路由引擎之间登录态可共享。
            # 注意：同一时间只能有一个进程占用该 profile，否则会被浏览器锁定。
            user_data_dir = project_path("data", "browser_data")

            # 优先 Edge（不需要安装 Chrome）。若 selenium-wire 不支持 Edge，则回退 Chrome。
            driver = None
            if browser in {"edge", "msedge"} and hasattr(webdriver, "Edge"):
                from selenium.webdriver.edge.options import Options as EdgeOptions  # type: ignore

                options = EdgeOptions()
                if headless:
                    options.add_argument("--headless=new")
                options.add_argument(f"--user-agent={ua}")
                options.add_argument("--disable-blink-features=AutomationControlled")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument(f"--user-data-dir={str(user_data_dir)}")
                options.add_argument("--profile-directory=Default")

                edge_exe = os.getenv("EDGE_EXECUTABLE_PATH") or _resolve_edge_executable()
                if edge_exe:
                    options.binary_location = edge_exe

                driver = webdriver.Edge(options=options)
            else:
                from selenium.webdriver.chrome.options import Options as ChromeOptions  # type: ignore

                options = ChromeOptions()
                if headless:
                    options.add_argument("--headless=new")
                options.add_argument(f"--user-agent={ua}")
                options.add_argument("--disable-blink-features=AutomationControlled")
                options.add_argument("--no-sandbox")
                options.add_argument("--disable-dev-shm-usage")
                options.add_argument(f"--user-data-dir={str(user_data_dir)}")
                options.add_argument("--profile-directory=Default")

                driver = webdriver.Chrome(options=options)

            # Selenium Manager 会尝试自动拉起 driver（Selenium 4+），Edge 也支持
            driver.scopes = [".*xhs.*", ".*/api/.*"]

            driver.get(url)

            # 等一点时间让接口请求出现
            import time

            time.sleep(6)

            for req in driver.requests:
                try:
                    if not req.response:
                        continue
                    ctype = (req.response.headers.get("Content-Type") or "").lower()
                    if "application/json" not in ctype:
                        continue
                    body = req.response.body
                    if not body:
                        continue
                    try:
                        payload = json.loads(body.decode("utf-8", errors="ignore"))
                    except Exception:
                        continue

                    sw_data.append({
                        "request_url": req.url,
                        "status_code": getattr(req.response, "status_code", None),
                        "json": payload,
                    })
                except Exception:
                    continue

            driver.quit()
        except Exception as exc:  # noqa: BLE001
            sw_error = str(exc)

    # 2) Pyppeteer 侧：抓渲染后的文本（可选）
    async def pyppeteer_fetch_text() -> Dict[str, Any]:
        try:
            from pyppeteer import launch  # type: ignore

            # Pyppeteer 默认会下载 Chromium。为了避免依赖 Chrome，优先使用本机 Edge。
            edge_exe = os.getenv("PUPPETEER_EXECUTABLE_PATH") or os.getenv("EDGE_EXECUTABLE_PATH") or _resolve_edge_executable()

            browser = await launch(
                headless=headless,
                executablePath=edge_exe,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            page = await browser.newPage()
            await page.setUserAgent(ua)
            await page.goto(url, timeout=60000)
            await asyncio.sleep(3)
            content = await page.content()
            title = await page.title()
            await browser.close()
            return {"title": title, "html_len": len(content)}
        except Exception as exc:  # noqa: BLE001
            return {"pyppeteer_error": str(exc)}

    # 并发执行：selenium-wire 放线程，pyppeteer 走协程
    loop = asyncio.get_running_loop()
    sw_future = loop.run_in_executor(None, selenium_wire_worker)
    py_result = await pyppeteer_fetch_text()
    await sw_future

    # 汇总输出
    results: List[Dict[str, Any]] = []
    if sw_error:
        results.append(
            {
                "platform": "xiaohongshu",
                "keyword": keyword,
                "source": "pywire",
                "error": sw_error,
                "note": "Selenium-Wire 启动失败，常见原因：缺少 Chrome/driver 或权限问题",
                "extra": py_result,
            }
        )
        return results

    # 目前不做复杂映射，先把捕获 JSON 原样带出，确保链路可用
    for pkt in sw_data[:20]:
        results.append(
            {
                "platform": "xiaohongshu",
                "keyword": keyword,
                "source": "pywire",
                "request_url": pkt.get("request_url"),
                "status_code": pkt.get("status_code"),
                "raw": pkt.get("json"),
                "extra": py_result,
            }
        )

    if not results:
        results.append(
            {
                "platform": "xiaohongshu",
                "keyword": keyword,
                "source": "pywire",
                "warning": "未捕获到 JSON 响应（可能被拦截/需要登录/接口加密）",
                "extra": py_result,
            }
        )

    return results
