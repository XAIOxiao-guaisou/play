"""路由决策层 - 根据目标平台和页面特征选择最优执行引擎。

提供智能路由决策，支持 Scrapy、Pywire、Playwright、Webster 等多种引擎。
"""

from src.router.decision_engine import (
    DecisionEngine,
    EngineChoice,
    RouteContext,
)

__all__ = [
    "DecisionEngine",
    "EngineChoice",
    "RouteContext",
]
