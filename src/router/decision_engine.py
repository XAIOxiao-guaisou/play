"""Lightweight routing decision engine for multi-engine selection.

Routes requests to optimal execution engine based on platform, page type,
threat level, success rate, and cost using rule-based decision making.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict


class EngineChoice(str, Enum):
    SCRAPY = "C"          # 静态/轻动态
    PYWIRE = "D"          # Pyppeteer + Selenium-Wire 细粒度控制
    PLAYWRIGHT = "E"      # 主力复杂 SPA
    WEBSTER = "F"         # 极端反爬/指纹防护


@dataclass
class RouteContext:
    platform: str
    page_type: str  # static | basic_dynamic | complex_spa | extreme
    threat_level: str = "medium"  # low | medium | high
    success_rate: float = 0.9      # 历史成功率 0~1
    resource_cost: str = "medium"  # low | medium | high


class DecisionEngine:
    def __init__(self) -> None:
        # 可扩展为从配置文件/Redis 拉取动态权重
        self.default_choice = EngineChoice.PLAYWRIGHT

    def decide(self, ctx: RouteContext) -> Dict[str, Any]:
        """
        核心决策：同步规则版，便于快速接入。
        返回包含 engine 与决策原因的字典。
        """
        reasons = []

        # 静态内容优先 Scrapy
        if ctx.page_type == "static":
            reasons.append("page_type=static -> SCRAPY")
            return self._result(EngineChoice.SCRAPY, reasons)

        # 轻动态或需要请求级精细控制
        if ctx.page_type == "basic_dynamic":
            reasons.append("page_type=basic_dynamic -> PYWIRE")
            return self._result(EngineChoice.PYWIRE, reasons)

        # 极端反爬或高威胁
        if ctx.page_type == "extreme" or ctx.threat_level == "high":
            reasons.append("threat_level high or extreme page -> WEBSTER")
            return self._result(EngineChoice.WEBSTER, reasons)

        # 成功率低且威胁中等，尝试更强的 Playwright 主力
        if ctx.success_rate < 0.6:
            reasons.append("success_rate<0.6 -> PLAYWRIGHT (stronger)")
            return self._result(EngineChoice.PLAYWRIGHT, reasons)

        # 资源成本高且页面并不复杂，可降级到 PYWIRE 节省成本
        if ctx.resource_cost == "high" and ctx.page_type == "basic_dynamic":
            reasons.append("cost high + basic_dynamic -> PYWIRE")
            return self._result(EngineChoice.PYWIRE, reasons)

        # 默认主力：Playwright 处理 90% 现代网页
        reasons.append("default -> PLAYWRIGHT")
        return self._result(EngineChoice.PLAYWRIGHT, reasons)

    def _result(self, engine: EngineChoice, reasons: list[str]) -> Dict[str, Any]:
        return {
            "engine": engine.value,
            "engine_name": engine.name,
            "reasons": reasons,
        }

    def report_health(self, engine: EngineChoice, success: bool, meta: Dict[str, Any] | None = None) -> None:
        """
        占位：用于上报执行健康（成功/失败、验证码率、耗时等）。
        未来可写入 Redis/DB 供自学习模型使用。
        当前为空实现，保持接口形式便于后续接线。
        """
        _ = (engine, success, meta)
        return None


# 简单工厂实例，避免多处重复创建
engine = DecisionEngine()
