"""小红书爬取最小可运行实现 (MVP)

提供命令行入口和批量关键词搜索功能，支持 JSON 导出、Excel 导出和企业微信推送。
"""

import argparse
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

from loguru import logger

from src.adapters import XiaohongshuAdapter
from src.services.exporter import export_to_excel
from src.services.notifier import send_wecom_text
from config import get_config, configure_logging, project_path


async def crawl_keywords(keywords: List[str], debug: bool) -> Path:
    """批量抓取小红书笔记并导出结果。

    执行流程：
        1. 逐个搜索关键词，并通过三层降级提取获取笔记数据
        2. 将结果聚合为 JSON 文件（utf-8 编码，2 空格缩进）
        3. 生成等价的 Excel 文件（方便数据分析）
        4. 发送企业微信推送通知（如设置 WECOM_WEBHOOK 环境变量）

    Args:
        keywords: 搜索关键词列表，如 ['瑜伽垫', '健身器材']
        debug: 是否启用调试模式（保留浏览器样式和图片资源）

    Returns:
        JSON 输出文件的 Path 对象

    Raises:
        Exception: 爬虫初始化或搜索过程中的任何异常
    """

    config = get_config()
    output_dir = project_path("output")
    output_dir.mkdir(exist_ok=True)

    async with XiaohongshuAdapter(
        debug_mode=debug,
        use_persistent_session=config.scraper.use_persistent_session,
        use_api_sniffing=True,
        use_context_pool=config.scraper.use_context_pool,
    ) as spider:

        all_notes = []
        for keyword in keywords:
            logger.info(f"🔍 关键词: {keyword}")
            notes = await spider.search_notes(keyword, max_pages=config.xiaohongshu.max_pages)
            all_notes.extend(notes)
            logger.info(f"✅ {keyword}: 获取 {len(notes)} 条")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = output_dir / f"xhs_{timestamp}.json"
        with json_path.open("w", encoding="utf-8") as f:
            json.dump(all_notes, f, ensure_ascii=False, indent=2)

        excel_path = output_dir / f"xhs_{timestamp}.xlsx"
        export_to_excel(all_notes, excel_path)

        # 企业微信机器人推送（可选，设置环境变量 WECOM_WEBHOOK 即可启用）
        webhook = os.getenv("WECOM_WEBHOOK")
        if webhook:
            try:
                await send_wecom_text(webhook, f"抓取完成，共 {len(all_notes)} 条，文件: {json_path.name} / {excel_path.name}")
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"WeCom 推送失败: {exc}")

        logger.success(f"🎯 抓取完成，已写入 {json_path} 和 {excel_path}")
        return json_path


def parse_args() -> argparse.Namespace:
    """解析命令行参数。

    Returns:
        解析后的命令行参数对象，包含以下属性：
            - keywords (str): 逗号分隔的搜索关键词
            - debug (bool): 是否启用调试模式
            - headless (bool): 强制无头模式
            - no_headless (bool): 强制有头模式
    """
    parser = argparse.ArgumentParser(description="小红书爬取最小可运行 MVP")
    parser.add_argument(
        "--keywords",
        type=str,
        required=True,
        help="关键词，逗号分隔，例如: 瑜伽垫,健身器材",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="启用调试模式（保留样式/图片，便于观察界面）",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="强制无头模式运行（默认使用配置或环境变量）",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="强制有头模式运行，便于人工登录或观察页面",
    )
    return parser.parse_args()


if __name__ == "__main__":
    # 文件日志，便于定位错误
    configure_logging()

    args = parse_args()
    cfg = get_config()
    if args.headless and args.no_headless:
        raise SystemExit("--headless 与 --no-headless 不能同时使用")
    if args.headless:
        cfg.browser.headless = True
    if args.no_headless:
        cfg.browser.headless = False
    keywords = [kw.strip() for kw in args.keywords.split(",") if kw.strip()]

    if not keywords:
        raise SystemExit("请至少提供一个关键词，例如 --keywords 瑜伽垫,健身器材")

    asyncio.run(crawl_keywords(keywords, debug=args.debug))
