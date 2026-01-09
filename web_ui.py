"""FastAPI web UI for Xiaohongshu MVP.

Provides a web interface for managing crawl tasks, viewing results,
and monitoring system health in real-time.
"""

import json
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from config import get_config, configure_logging, project_path, PROJECT_ROOT
from src.core.protocol_breakthrough import NetworkEnvironmentDetector
from main import crawl_keywords
from src.router.decision_engine import DecisionEngine, RouteContext, EngineChoice
from src.router.executors import (
    crawl_keywords_playwright,
    crawl_keywords_pywire,
)

app = FastAPI(title="XHS Cyber UI", version="0.1.0")

# 路由决策引擎（同步规则版）
decision_engine = DecisionEngine()

# 启用文件日志，便于排查（logs/app.log）
configure_logging()

STATIC_DIR = project_path("webui")
app.mount("/webui", StaticFiles(directory=STATIC_DIR), name="webui")


@app.get("/", response_class=FileResponse)
async def serve_index() -> FileResponse:
    """Serve the main index.html file for the web UI frontend.

    Returns:
        FileResponse with the index.html file from webui directory.

    Raises:
        HTTPException: 500 if frontend files are missing.
    """
    index_path = STATIC_DIR / "index.html"
    if not index_path.exists():
        raise HTTPException(status_code=500, detail="Frontend files missing in webui directory")
    return FileResponse(index_path)


@app.post("/api/crawl")
async def api_crawl(payload: Dict[str, Any]) -> JSONResponse:
    """Legacy crawl endpoint - directly executes with Playwright (Engine E)."""

    raw_keywords = payload.get("keywords", "") if payload else ""
    debug = bool(payload.get("debug", False)) if payload else False
    headless_override = payload.get("headless") if payload else None
    allow_no_login = bool(payload.get("allow_no_login", False)) if payload else False

    keywords = [kw.strip() for kw in str(raw_keywords).split(",") if kw.strip()]
    if not keywords:
        raise HTTPException(status_code=400, detail="关键词不能为空")

    logger.info(f"[WebUI] 接收到关键词: {keywords} (debug={debug}, allow_no_login={allow_no_login})")

    # 运行时允许切换 headless，未传则沿用配置文件/环境变量
    cfg = get_config()
    if headless_override is not None:
        cfg.browser.headless = bool(headless_override)
        logger.info(f"[WebUI] 覆盖 headless={cfg.browser.headless}")
    
    # 覆盖免登录配置
    cfg.scraper.allow_no_login = allow_no_login
    if allow_no_login:
        logger.info("[WebUI] 已启用免登录（无痕爆破）模式")

    try:
        output_path = await crawl_keywords(keywords, debug=debug)

        items: List[Dict[str, Any]] = []
        try:
            with output_path.open("r", encoding="utf-8") as f:
                items = json.load(f)
        except Exception:
            logger.warning("输出解析失败，但文件已生成", exc_info=True)

        return JSONResponse({"output_path": str(output_path), "count": len(items), "keywords": keywords})

    except Exception as exc:  # noqa: BLE001
        logger.exception(f"[WebUI] 抓取失败: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/route_crawl")
async def api_route_crawl(payload: Dict[str, Any]) -> JSONResponse:
    """Unified crawl endpoint with intelligent routing to optimal executor.

    Uses DecisionEngine to select best executor based on platform,
    page type, threat level, and historical success rate.
    Engine choices: E=Playwright, D=Pywire, C=Scrapy, F=Webster.
    """
    raw_keywords = payload.get("keywords", "") if payload else ""
    platform = str(payload.get("platform", "xiaohongshu") if payload else "xiaohongshu")
    page_type = str(payload.get("page_type", "complex_spa") if payload else "complex_spa")
    threat_level = str(payload.get("threat_level", "medium") if payload else "medium")
    success_rate = float(payload.get("success_rate", 0.9) if payload else 0.9)
    resource_cost = str(payload.get("resource_cost", "medium") if payload else "medium")
    debug = bool(payload.get("debug", False)) if payload else False
    headless_override = payload.get("headless") if payload else None
    allow_no_login = bool(payload.get("allow_no_login", False)) if payload else False

    keywords = [kw.strip() for kw in str(raw_keywords).split(",") if kw.strip()]
    if not keywords:
        raise HTTPException(status_code=400, detail="关键词不能为空")

    # 运行时允许切换 headless，未传则沿用配置文件/环境变量
    cfg = get_config()
    if headless_override is not None:
        cfg.browser.headless = bool(headless_override)
        logger.info(f"[WebUI] 覆盖 headless={cfg.browser.headless}")
    
    # 覆盖免登录配置
    cfg.scraper.allow_no_login = allow_no_login
    if allow_no_login:
        logger.info("[WebUI] 已启用免登录（无痕爆破）模式")

    ctx = RouteContext(
        platform=platform,
        page_type=page_type,
        threat_level=threat_level,
        success_rate=success_rate,
        resource_cost=resource_cost,
    )

    decision = decision_engine.decide(ctx)
    selected = decision.get("engine")
    reasons = decision.get("reasons", [])

    logger.info(
        f"[Router] platform={platform}, page_type={page_type}, "
        f"threat={threat_level}, engine={selected}, reasons={reasons}"
    )

    try:
        if selected == EngineChoice.PYWIRE.value:
            output_path = await crawl_keywords_pywire(keywords, debug=debug)
        else:
            if selected != EngineChoice.PLAYWRIGHT.value:
                reasons.append(f"engine {selected} 未对接，回退 Playwright (E)")
                selected = EngineChoice.PLAYWRIGHT.value
            output_path = await crawl_keywords_playwright(keywords, debug=debug)

        items: List[Dict[str, Any]] = []
        try:
            with output_path.open("r", encoding="utf-8") as f:
                items = json.load(f)
        except Exception:
            logger.warning("输出解析失败，但文件已生成", exc_info=True)

        return JSONResponse(
            {
                "engine": selected,
                "reasons": reasons,
                "output_path": str(output_path),
                "count": len(items),
                "keywords": keywords,
            }
        )

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception(f"[WebUI] 路由抓取失败: {exc}")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/health")
async def api_health() -> Dict[str, Any]:
    cfg = get_config()
    env: Dict[str, Any] = {}
    try:
        env = await NetworkEnvironmentDetector.detect_environment()
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"网络环境检测失败: {exc}")

    profile_dir = project_path("data", "browser_data")
    sessions_dir = project_path("sessions")

    return {
        "status": "ok",
        "browser": cfg.browser.browser_type,
        "headless": cfg.browser.headless,
        "max_pages": cfg.xiaohongshu.max_pages,
        "project_root": str(PROJECT_ROOT),
        "profile_dir": str(profile_dir),
        "sessions_dir": str(sessions_dir),
        "network": env or {"country": "Unknown", "is_china": None},
    }


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("web_ui:app", host="0.0.0.0", port=8000, reload=False)
