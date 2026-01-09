"""适配层 - 平台特定的爬虫适配器。

提供小红书等目标平台的数据提取、元素定位和反爬处理。
核心特性：三层降级抓取（API → HTML → Mock）。
"""

from src.adapters.xhs_adapter import XiaohongshuAdapter
from src.core.base_spider import BaseSpider

__all__ = [
    "XiaohongshuAdapter",
    "BaseSpider",
]
