"""核心能力层 - 基础爬虫引擎、提取引擎、协议突破等核心模块。

提供高级浏览器自动化、数据提取、反爬突破的基础能力。
"""

from src.core.base_spider import BaseSpider
from src.core.extraction_engine import ExtractionEngine
from src.core.protocol_breakthrough import ProtocolBreakthrough

__all__ = [
    "BaseSpider",
    "ExtractionEngine",
    "ProtocolBreakthrough",
]
