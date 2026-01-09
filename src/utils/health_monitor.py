"""
健康监控与分级报警 (Health Monitor & Alert System)

职责：
1. 请求统计（成功率、失败率、响应时间）
2. 失败因子分析（IP封禁、Session过期、DOM变化）
3. 健康分级（健康、警告、危险、致命）
4. 自动暂停与唤醒（避免账号被封）
5. 告警通知（日志、弹窗、Webhook）
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from collections import deque
from loguru import logger
import json


class HealthLevel(Enum):
    """健康等级"""
    HEALTHY = "健康"      # 一切正常
    WARNING = "警告"      # 轻微问题
    DANGER = "危险"       # 严重问题
    CRITICAL = "致命"     # 致命问题，需要立即停止


class FailureReason(Enum):
    """失败原因分类"""
    NETWORK_ERROR = "网络错误"           # 网络连接失败
    TIMEOUT = "请求超时"                # 请求超时
    IP_BANNED = "IP被封禁"              # IP被封
    SESSION_EXPIRED = "Session过期"     # Session失效
    LOGIN_REQUIRED = "需要登录"         # 需要重新登录
    DOM_CHANGED = "DOM结构变化"         # 页面结构改变
    SELECTOR_FAILED = "选择器失效"      # 所有选择器失败
    RATE_LIMIT = "请求频率限制"         # 触发频率限制
    CAPTCHA_REQUIRED = "需要验证码"     # 需要验证码
    SERVER_ERROR = "服务器错误"         # 5xx错误
    UNKNOWN = "未知错误"                # 其他错误


@dataclass
class RequestStats:
    """请求统计"""
    total_requests: int = 0          # 总请求数
    successful_requests: int = 0      # 成功请求数
    failed_requests: int = 0          # 失败请求数
    
    # 响应时间统计
    total_response_time: float = 0.0  # 总响应时间
    min_response_time: float = float('inf')  # 最小响应时间
    max_response_time: float = 0.0    # 最大响应时间
    
    # 失败原因统计
    failure_reasons: Dict[FailureReason, int] = field(default_factory=dict)
    
    # 时间戳
    start_time: datetime = field(default_factory=datetime.now)
    last_request_time: Optional[datetime] = None
    
    def add_success(self, response_time: float):
        """记录成功请求"""
        self.total_requests += 1
        self.successful_requests += 1
        self.total_response_time += response_time
        self.min_response_time = min(self.min_response_time, response_time)
        self.max_response_time = max(self.max_response_time, response_time)
        self.last_request_time = datetime.now()
    
    def add_failure(self, reason: FailureReason):
        """记录失败请求"""
        self.total_requests += 1
        self.failed_requests += 1
        self.failure_reasons[reason] = self.failure_reasons.get(reason, 0) + 1
        self.last_request_time = datetime.now()
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        if self.total_requests == 0:
            return 1.0
        return self.successful_requests / self.total_requests
    
    @property
    def failure_rate(self) -> float:
        """失败率"""
        return 1.0 - self.success_rate
    
    @property
    def avg_response_time(self) -> float:
        """平均响应时间"""
        if self.successful_requests == 0:
            return 0.0
        return self.total_response_time / self.successful_requests
    
    def get_top_failure_reason(self) -> Optional[FailureReason]:
        """获取最主要的失败原因"""
        if not self.failure_reasons:
            return None
        return max(self.failure_reasons.items(), key=lambda x: x[1])[0]


class HealthMonitor:
    """健康监控器"""
    
    def __init__(
        self,
        window_size: int = 100,           # 滑动窗口大小
        consecutive_failures_threshold: int = 5,  # 连续失败阈值
        failure_rate_warning: float = 0.3,        # 失败率警告阈值（30%）
        failure_rate_danger: float = 0.6,         # 失败率危险阈值（60%）
        auto_pause: bool = True,                  # 是否自动暂停
        alert_callback: Optional[Callable] = None # 告警回调
    ):
        self.window_size = window_size
        self.consecutive_failures_threshold = consecutive_failures_threshold
        self.failure_rate_warning = failure_rate_warning
        self.failure_rate_danger = failure_rate_danger
        self.auto_pause = auto_pause
        self.alert_callback = alert_callback
        
        # 统计数据
        self.stats = RequestStats()
        
        # 滑动窗口（记录最近N次请求的结果）
        self.recent_results = deque(maxlen=window_size)
        
        # 连续失败计数
        self.consecutive_failures = 0
        self.max_consecutive_failures = 0
        
        # 状态
        self.health_level = HealthLevel.HEALTHY
        self.is_paused = False
        self.pause_reason = None
        self.pause_time = None
        
        # 失败历史（用于分析）
        self.failure_history: List[Dict] = []
        
        logger.info(f"🏥 健康监控器已启动 (窗口={window_size}, 连续失败阈值={consecutive_failures_threshold})")
    
    def record_success(self, response_time: float = 0.0):
        """记录成功请求"""
        self.stats.add_success(response_time)
        self.recent_results.append(True)
        self.consecutive_failures = 0  # 重置连续失败计数
        
        # 更新健康等级
        self._update_health_level()
        
        logger.debug(f"✅ 请求成功 (响应时间: {response_time:.2f}s)")
    
    def record_failure(
        self, 
        reason: FailureReason,
        details: Optional[Dict] = None
    ):
        """记录失败请求"""
        self.stats.add_failure(reason)
        self.recent_results.append(False)
        self.consecutive_failures += 1
        self.max_consecutive_failures = max(
            self.max_consecutive_failures, 
            self.consecutive_failures
        )
        
        # 记录失败详情
        failure_record = {
            'timestamp': datetime.now().isoformat(),
            'reason': reason.value,
            'consecutive_count': self.consecutive_failures,
            'details': details or {}
        }
        self.failure_history.append(failure_record)
        
        # 限制历史记录数量
        if len(self.failure_history) > 1000:
            self.failure_history = self.failure_history[-500:]
        
        logger.warning(f"❌ 请求失败 (原因: {reason.value}, 连续失败: {self.consecutive_failures}次)")
        
        # 更新健康等级
        self._update_health_level()
        
        # 检查是否需要暂停
        self._check_auto_pause()
    
    def _update_health_level(self):
        """更新健康等级"""
        old_level = self.health_level
        
        # 获取滑动窗口内的失败率
        if len(self.recent_results) == 0:
            window_failure_rate = 0.0
        else:
            window_failure_rate = 1.0 - sum(self.recent_results) / len(self.recent_results)
        
        # 根据失败率和连续失败次数判断健康等级
        if self.consecutive_failures >= self.consecutive_failures_threshold:
            self.health_level = HealthLevel.CRITICAL
        elif window_failure_rate >= self.failure_rate_danger:
            self.health_level = HealthLevel.DANGER
        elif window_failure_rate >= self.failure_rate_warning:
            self.health_level = HealthLevel.WARNING
        else:
            self.health_level = HealthLevel.HEALTHY
        
        # 健康等级变化时记录
        if old_level != self.health_level:
            logger.warning(f"🏥 健康等级变化: {old_level.value} → {self.health_level.value}")
            
            # 触发告警回调
            if self.alert_callback:
                try:
                    self.alert_callback(self.health_level, self.get_health_report())
                except Exception as e:
                    logger.error(f"告警回调执行失败: {e}")
    
    def _check_auto_pause(self):
        """检查是否需要自动暂停"""
        if not self.auto_pause or self.is_paused:
            return
        
        # 连续失败达到阈值，自动暂停
        if self.consecutive_failures >= self.consecutive_failures_threshold:
            self.pause(f"连续失败 {self.consecutive_failures} 次")
    
    def pause(self, reason: str):
        """暂停爬虫"""
        if self.is_paused:
            return
        
        self.is_paused = True
        self.pause_reason = reason
        self.pause_time = datetime.now()
        
        logger.error("=" * 60)
        logger.error(f"⏸️  爬虫已自动暂停！")
        logger.error(f"原因: {reason}")
        logger.error(f"时间: {self.pause_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.error("=" * 60)
        
        # 分析失败原因
        self._analyze_and_suggest()
        
        # 触发告警
        if self.alert_callback:
            try:
                self.alert_callback(HealthLevel.CRITICAL, {
                    'action': 'paused',
                    'reason': reason,
                    'report': self.get_health_report()
                })
            except Exception as e:
                logger.error(f"告警回调执行失败: {e}")
    
    def resume(self):
        """恢复爬虫"""
        if not self.is_paused:
            return
        
        self.is_paused = False
        pause_duration = datetime.now() - self.pause_time
        
        logger.success("=" * 60)
        logger.success(f"▶️  爬虫已恢复运行")
        logger.success(f"暂停时长: {pause_duration}")
        logger.success("=" * 60)
        
        # 重置连续失败计数
        self.consecutive_failures = 0
    
    def can_proceed(self) -> bool:
        """
        检查是否可以继续执行
        
        Returns:
            True: 可以继续
            False: 暂停中或状态异常
        """
        return not self.is_paused
    
    def _analyze_and_suggest(self):
        """分析失败原因并给出建议"""
        top_reason = self.stats.get_top_failure_reason()
        
        if not top_reason:
            return
        
        logger.info("\n" + "=" * 60)
        logger.info("🔍 失败原因分析：")
        logger.info("=" * 60)
        
        # 统计失败原因分布
        total_failures = self.stats.failed_requests
        for reason, count in sorted(
            self.stats.failure_reasons.items(), 
            key=lambda x: x[1], 
            reverse=True
        ):
            percentage = (count / total_failures) * 100
            logger.info(f"  {reason.value}: {count}次 ({percentage:.1f}%)")
        
        logger.info("\n💡 建议措施：")
        
        # 根据主要失败原因给出建议
        if top_reason == FailureReason.IP_BANNED:
            logger.warning("  1. IP 已被封禁，建议：")
            logger.warning("     - 更换代理 IP")
            logger.warning("     - 降低请求频率")
            logger.warning("     - 等待 30-60 分钟后重试")
        
        elif top_reason == FailureReason.SESSION_EXPIRED:
            logger.warning("  1. Session 已过期，建议：")
            logger.warning("     - 删除 sessions/ 目录下的 Session 文件")
            logger.warning("     - 重新登录账号")
            logger.warning("     - 运行: python test_session.py")
        
        elif top_reason == FailureReason.DOM_CHANGED:
            logger.warning("  1. DOM 结构已变化，建议：")
            logger.warning("     - 网站可能改版了")
            logger.warning("     - 检查 adaptive_config.py 中的选择器")
            logger.warning("     - 添加新的选择器到配置文件")
        
        elif top_reason == FailureReason.RATE_LIMIT:
            logger.warning("  1. 触发请求频率限制，建议：")
            logger.warning("     - 增加延迟时间")
            logger.warning("     - 在 advanced_config.py 中调整 mean/std 参数")
            logger.warning("     - 等待 10-30 分钟后重试")
        
        elif top_reason == FailureReason.CAPTCHA_REQUIRED:
            logger.warning("  1. 需要验证码，建议：")
            logger.warning("     - 启用非无头模式手动验证")
            logger.warning("     - 在 .env 中设置 HEADLESS=false")
            logger.warning("     - 集成验证码识别服务")
        
        logger.info("=" * 60 + "\n")
    
    def get_health_report(self) -> Dict:
        """获取健康报告"""
        return {
            'health_level': self.health_level.value,
            'is_paused': self.is_paused,
            'pause_reason': self.pause_reason,
            'stats': {
                'total_requests': self.stats.total_requests,
                'successful_requests': self.stats.successful_requests,
                'failed_requests': self.stats.failed_requests,
                'success_rate': f"{self.stats.success_rate * 100:.1f}%",
                'failure_rate': f"{self.stats.failure_rate * 100:.1f}%",
                'avg_response_time': f"{self.stats.avg_response_time:.2f}s",
            },
            'consecutive_failures': self.consecutive_failures,
            'max_consecutive_failures': self.max_consecutive_failures,
            'top_failure_reason': self.stats.get_top_failure_reason().value if self.stats.get_top_failure_reason() else None,
            'failure_reasons': {
                reason.value: count 
                for reason, count in self.stats.failure_reasons.items()
            },
            'runtime': str(datetime.now() - self.stats.start_time)
        }
    
    def print_report(self):
        """打印健康报告"""
        report = self.get_health_report()
        
        # 健康等级颜色
        level_colors = {
            HealthLevel.HEALTHY: "🟢",
            HealthLevel.WARNING: "🟡",
            HealthLevel.DANGER: "🟠",
            HealthLevel.CRITICAL: "🔴"
        }
        
        print("\n" + "=" * 60)
        print(f"{level_colors[self.health_level]} 健康监控报告")
        print("=" * 60)
        
        print(f"\n【健康状态】")
        print(f"  等级: {report['health_level']}")
        print(f"  状态: {'⏸️ 已暂停' if report['is_paused'] else '▶️ 运行中'}")
        if report['pause_reason']:
            print(f"  暂停原因: {report['pause_reason']}")
        
        print(f"\n【请求统计】")
        print(f"  总请求数: {report['stats']['total_requests']}")
        print(f"  成功: {report['stats']['successful_requests']} ({report['stats']['success_rate']})")
        print(f"  失败: {report['stats']['failed_requests']} ({report['stats']['failure_rate']})")
        print(f"  平均响应时间: {report['stats']['avg_response_time']}")
        
        print(f"\n【失败分析】")
        print(f"  连续失败: {report['consecutive_failures']} 次")
        print(f"  最大连续失败: {report['max_consecutive_failures']} 次")
        if report['top_failure_reason']:
            print(f"  主要原因: {report['top_failure_reason']}")
        
        if report['failure_reasons']:
            print(f"\n【失败原因分布】")
            for reason, count in sorted(
                report['failure_reasons'].items(),
                key=lambda x: x[1],
                reverse=True
            ):
                print(f"  - {reason}: {count}次")
        
        print(f"\n【运行时长】{report['runtime']}")
        print("=" * 60 + "\n")
    
    def save_report(self, filepath: str = None):
        """保存报告到文件"""
        if filepath is None:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            filepath = f"logs/health_report_{timestamp}.json"
        
        import os
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        
        report = self.get_health_report()
        report['failure_history'] = self.failure_history[-100:]  # 只保存最近100条
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        
        logger.info(f"📄 健康报告已保存: {filepath}")


class FailureAnalyzer:
    """失败原因分析器"""
    
    @staticmethod
    def analyze_error(error: Exception, page_content: str = None) -> FailureReason:
        """
        分析错误并返回失败原因
        
        Args:
            error: 异常对象
            page_content: 页面内容（可选）
            
        Returns:
            失败原因
        """
        error_msg = str(error).lower()
        
        # 网络错误
        if any(keyword in error_msg for keyword in ['connection', 'network', 'dns', 'unreachable']):
            return FailureReason.NETWORK_ERROR
        
        # 超时
        if 'timeout' in error_msg or 'timed out' in error_msg:
            return FailureReason.TIMEOUT
        
        # Session 过期
        if any(keyword in error_msg for keyword in ['unauthorized', '401', 'session', 'login']):
            return FailureReason.SESSION_EXPIRED
        
        # 频率限制
        if any(keyword in error_msg for keyword in ['rate limit', '429', 'too many']):
            return FailureReason.RATE_LIMIT
        
        # 服务器错误
        if any(keyword in error_msg for keyword in ['500', '502', '503', '504', 'server error']):
            return FailureReason.SERVER_ERROR
        
        # 分析页面内容
        if page_content:
            content_lower = page_content.lower()
            
            # IP 被封
            if any(keyword in content_lower for keyword in ['访问受限', 'access denied', '403', 'forbidden']):
                return FailureReason.IP_BANNED
            
            # 需要登录
            if any(keyword in content_lower for keyword in ['请登录', 'please login', '请先登录']):
                return FailureReason.LOGIN_REQUIRED
            
            # 验证码
            if any(keyword in content_lower for keyword in ['验证码', 'captcha', 'verify']):
                return FailureReason.CAPTCHA_REQUIRED
        
        # 默认未知错误
        return FailureReason.UNKNOWN
    
    @staticmethod
    def analyze_selector_failure(
        tried_selectors: List[str],
        page_title: str = None
    ) -> FailureReason:
        """分析选择器失败原因"""
        
        # 如果页面标题包含错误信息
        if page_title:
            title_lower = page_title.lower()
            
            if any(keyword in title_lower for keyword in ['404', 'not found']):
                return FailureReason.NETWORK_ERROR
            
            if any(keyword in title_lower for keyword in ['403', 'forbidden', 'denied']):
                return FailureReason.IP_BANNED
            
            if any(keyword in title_lower for keyword in ['login', '登录']):
                return FailureReason.LOGIN_REQUIRED
        
        # 所有选择器都失败，可能是 DOM 变化
        if len(tried_selectors) >= 3:
            return FailureReason.DOM_CHANGED
        
        return FailureReason.SELECTOR_FAILED


# 导出
__all__ = [
    'HealthLevel',
    'FailureReason',
    'RequestStats',
    'HealthMonitor',
    'FailureAnalyzer'
]
