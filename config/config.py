"""小红书爬虫配置中心。

提供统一的配置管理，包括浏览器、爬虫参数、平台配置、Session 管理、指纹池等。
支持环境变量覆盖，采用 singleton 模式确保全局唯一配置实例。
"""

import logging
import os
import random
import re
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger


# 项目根目录（从 config/ 的父级计算）
# 避免不同 cwd 启动导致 profile/session/log/output 分裂
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def project_path(*parts: str) -> Path:
    """构建项目相对路径。

    Args:
        *parts: 路径片段，如 "logs", "app.log"

    Returns:
        相对于项目根目录的 Path 对象
    """
    return PROJECT_ROOT.joinpath(*parts)


@dataclass
class BrowserConfig:
    """浏览器运行配置。

    Attributes:
        headless: 是否以无头模式运行（不显示浏览器窗口）。默认 False。
        browser_type: 浏览器类型，支持 'chromium', 'firefox', 'webkit', 'msedge'。默认 'msedge'。
        proxy: 代理地址，如 'http://127.0.0.1:7890' 或 'socks5://127.0.0.1:1080'。默认 None（无代理）。
    """
    headless: bool = False
    browser_type: str = "msedge"
    proxy: Optional[str] = None


@dataclass
class ScraperConfig:
    """爬虫运行参数。

    Attributes:
        min_delay: 请求间最小延迟（秒）。默认 3.0。
        max_delay: 请求间最大延迟（秒）。默认 6.0。
        use_persistent_session: 是否使用持久化 Session（加快后续请求）。默认 True。
        use_context_pool: 是否使用浏览器上下文池。默认 False。
        use_resource_block: 是否拦截图片/样式（加快加载）。默认 False。
        allow_no_login: 是否允许无登录状态下爬取（可能被限制）。默认 False。
    """
    min_delay: float = 3.0
    max_delay: float = 6.0
    use_persistent_session: bool = True
    use_context_pool: bool = False
    use_resource_block: bool = False
    allow_no_login: bool = False


@dataclass
class XiaohongshuConfig:
    """小红书平台相关配置。

    Attributes:
        base_url: 小红书主站 URL。
        search_url: 搜索页 URL。
        login_url: 登录页 URL。
        explore_url: 发现页 URL。
        max_pages: 单个关键词最多爬取页数。默认 5。
    """
    base_url: str = "https://www.xiaohongshu.com"
    search_url: str = "https://www.xiaohongshu.com/search_result"
    login_url: str = "https://www.xiaohongshu.com/login"
    explore_url: str = "https://www.xiaohongshu.com/explore"
    max_pages: int = 5


class SessionConfig:
    """Session 持久化配置"""
    SESSION_DIR = "sessions"
    EXPIRE_DAYS = 30
    LOGIN_TIMEOUT = 180  # 登录等待超时（秒）
    PLATFORM_LOGIN_URLS = {
        "xiaohongshu": "https://www.xiaohongshu.com/login",
    }
    LOGIN_SUCCESS_SELECTORS = {
        "xiaohongshu": "header .header-user, .user-card, [class*='user-card'], .avatar-wrapper, .side-bar .user-avatar, img.avatar-item",
    }


@dataclass
class FingerprintConfig:
    """浏览器指纹池配置（用于反爬虫伪装）。

    Attributes:
        USER_AGENTS: User-Agent 字符串列表，随机选择以伪装不同浏览器。
        VIEWPORTS: 视口尺寸列表，如 {"width": 1920, "height": 1080}。
        REQUIRE_CHINA_NETWORK: 是否要求在中国 IP 网络运行。默认 True。
        ACCEPT_LANGUAGES: Accept-Language 头列表。
    """
    USER_AGENTS: List[str] = field(default_factory=list)
    VIEWPORTS: List[Dict[str, int]] = field(default_factory=list)
    REQUIRE_CHINA_NETWORK: bool = True
    ACCEPT_LANGUAGES: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """初始化，填充默认值。"""
        if not self.USER_AGENTS:
            self.USER_AGENTS = [
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                " (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                " (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                " (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                " (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36 Edg/119.0.0.0",
            ]

        if not self.VIEWPORTS:
            self.VIEWPORTS = [
                {"width": 1920, "height": 1080},
                {"width": 1366, "height": 768},
                {"width": 1440, "height": 900},
                {"width": 1536, "height": 864},
                {"width": 2560, "height": 1440},
            ]

        if not self.ACCEPT_LANGUAGES:
            self.ACCEPT_LANGUAGES = [
                "zh-CN,zh;q=0.9,en;q=0.8",
                "zh-CN,zh;q=0.9",
                "zh-CN,zh-TW;q=0.9,zh;q=0.8,en;q=0.7",
            ]


class AdaptiveSelectors:
    """小红书自适应选择器"""

    XIAOHONGSHU = {
        "note_item": [
            ".note-item",
            "[data-note-id]",
            ".search-note",
        ],
        "note_title": [
            ".note-title",
            ".title",
            "a.title",
        ],
        "note_author": [
            ".author-name",
            ".user-name",
            "[data-author]",
        ],
        "note_likes": [
            ".like-wrapper .count",
            ".likes",
            "[data-likes]",
        ],
    }


class NetworkInterceptorConfig:
    """小红书 API 拦截配置"""

    BLOCK_RESOURCES = ["image", "stylesheet", "font"]
    XIAOHONGSHU_APIS: Dict[str, Dict[str, str]] = {
        "search": {
            "pattern": r"/api/sns/web/v1/search/notes",
            "method": None,  # 允许 GET/POST
            "data_path": "data.items",
        },
        "feed": {
            "pattern": r"/api/sns/web/v1/feed",
            "method": None,  # 允许 GET/POST
            "data_path": "data.items",
        },
        "note_detail": {
            "pattern": r"/api/sns/web/v1/note\?",
            "method": None,  # 允许 GET/POST
            "data_path": "data.note",
        },
    }
    XIAOHONGSHU_MAPPING: Dict[str, List[str]] = {
        # 核心标识与文本
        "note_id": ["note_card.note_id", "note.note_id", "id", "note_id"],
        "xsec_token": ["xsec_token"],
        "title": ["note_card.title", "note_card.display_title", "note_card.desc", "note.title", "note.desc", "title", "desc"],
        "desc": ["note_card.desc", "note.desc", "desc"],
        "note_type": ["note_card.type", "note.type"],

        # 作者信息
        "author": ["note_card.user.nickname", "note.user.nickname", "user.nickname", "user.name"],
        "author_id": ["note_card.user.user_id", "note.user.user_id", "user.user_id"],
        "author_avatar": ["note_card.user.avatar", "note.user.avatar", "user.avatar"],

        # 互动计数
        "likes": ["note_card.interact_info.liked_count", "note.interact_info.liked_count", "liked_count", "likes"],
        "collects": ["note_card.interact_info.collected_count", "note.interact_info.collected_count"],
        "comments": ["note_card.interact_info.comment_count", "note.interact_info.comment_count"],
        "shares": ["note_card.interact_info.share_count", "note_card.interact_info.shared_count", "note.interact_info.share_count", "note.interact_info.shared_count"],
        "views": [
            "note.interact_info.view_count",
            "note.interact_info.read_count",
            "note.statistics.play_count",
            "note.statistics.show_count",
            "note.statistics.view_count",
        ],

        # 媒体与标签
        "image_list": ["note_card.image_list", "note.image_list"],
        "video": ["note_card.video", "note.video"],
        "tag_list": ["note_card.tag_list", "note.tag_list"],

        # 其他元数据
        "ip_location": ["note_card.ip_location", "note.ip_location", "ip_location"],
        "publish_time": ["note_card.time", "note.time"],
        "last_update_time": ["note_card.last_update_time", "note.last_update_time"],
        "share_info": ["note_card.share_info", "note.share_info"],
        "cursor_score": ["cursor_score"],

        # URL 相关（部分接口无链接，保留兼容路径）
        "url": ["note_card.note_url", "note.note_url", "note_url", "share_info.link"],
    }


class ExtractionStrategy:
    """提取策略占位，兼容旧接口"""
    API_FIRST = "api_first"
    HTML_ONLY = "html_only"
    HYBRID = "hybrid"


class BehaviorRandomizer:
    """行为随机化器 (Stealth 2.0)"""

    @staticmethod
    def get_delay(min_val: float = 1.0, max_val: float = 3.0, jitter: float = 0.1) -> float:
        import numpy as np

        mean = (min_val + max_val) / 2
        std = (max_val - min_val) / 6
        base_delay = np.random.normal(mean, std)
        jitter_value = np.random.uniform(-jitter, jitter)
        final_delay = base_delay + jitter_value
        return max(min_val, min(max_val, final_delay))

    @staticmethod
    def get_typing_delay(fast_mode: bool = False) -> float:
        import numpy as np

        if fast_mode:
            return max(0.08, min(0.15, np.random.normal(0.115, 0.02)))
        return max(0.10, min(0.30, np.random.normal(0.18, 0.05)))

    @staticmethod
    def get_mouse_steps(distance: float = 500) -> int:
        import numpy as np

        base_steps = int(distance / 30)
        variation = np.random.normal(0, base_steps * 0.2)
        return max(10, min(50, int(base_steps + variation)))

    @staticmethod
    def get_scroll_distance(smooth: bool = True) -> int:
        import numpy as np

        if smooth:
            return int(max(300, min(800, np.random.normal(500, 100))))
        return int(max(500, min(1200, np.random.normal(800, 150))))

    @staticmethod
    def should_pause(probability: float = 0.15) -> bool:
        return random.random() < probability

    @staticmethod
    def get_pause_duration() -> float:
        import numpy as np

        return max(0.5, min(2.5, np.random.normal(1.2, 0.4)))


class Config:
    """统一配置对象（单例模式）。

    整合浏览器、爬虫、平台等各类配置，支持环境变量覆盖和自动验证。

    Attributes:
        browser: 浏览器配置对象
        scraper: 爬虫参数对象
        xiaohongshu: 小红书平台配置对象
        fingerprint: 浏览器指纹池配置对象
    """

    def __init__(self) -> None:
        """初始化配置对象。"""
        self._load_env()
        self.browser = BrowserConfig()
        self.scraper = ScraperConfig()
        self.xiaohongshu = XiaohongshuConfig()
        self.fingerprint = FingerprintConfig()
        self._override_from_env()
        self._validate()

    def _load_env(self) -> None:
        """加载 .env 环境变量文件。"""
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

    def _override_from_env(self) -> None:
        """从环境变量覆盖配置值。

        支持的环境变量：
            - HEADLESS: 'true'/'false' 覆盖 headless 模式
            - XHS_MAX_PAGES: 整数，覆盖最大页数
            - PROXY/HTTPS_PROXY/HTTP_PROXY: 代理地址
        """
        if os.getenv("HEADLESS"):
            self.browser.headless = os.getenv("HEADLESS").lower() == "true"
        if os.getenv("XHS_MAX_PAGES"):
            try:
                self.xiaohongshu.max_pages = int(os.getenv("XHS_MAX_PAGES", "5"))
            except ValueError:
                logger.warning("XHS_MAX_PAGES 环境变量无效，使用默认值 5")

        # 优先级：PROXY > HTTPS_PROXY > HTTP_PROXY
        proxy_env = (
            os.getenv("PROXY")
            or os.getenv("HTTPS_PROXY")
            or os.getenv("HTTP_PROXY")
        )
        if proxy_env:
            self.browser.proxy = proxy_env

    def _validate(self) -> None:
        """验证并创建必要的目录。"""
        project_path("data").mkdir(exist_ok=True)
        project_path("logs").mkdir(exist_ok=True)
        project_path("output").mkdir(exist_ok=True)
        project_path(SessionConfig.SESSION_DIR).mkdir(exist_ok=True)

    def print_summary(self) -> None:
        """打印配置摘要。"""
        logger.info("\n📋 配置摘要")
        logger.info(f"浏览器: {self.browser.browser_type},"
                    f" headless={self.browser.headless}")
        logger.info(f"XHS 页面数: {self.xiaohongshu.max_pages}")
        logger.info(f"Session 持久化: {self.scraper.use_persistent_session}")


def get_config() -> Config:
    """获取全局配置单例。

    Returns:
        全局 Config 实例
    """
    return config


def reload_config() -> Config:
    """重新加载配置。

    Returns:
        刷新后的 Config 实例
    """
    global config
    config = Config()
    return config


def get_random_fingerprint() -> Dict[str, Any]:
    """获取随机的浏览器指纹。

    Returns:
        包含 'user_agent' 和 'viewport' 的字典
    """
    fp_config = FingerprintConfig()
    allow_mobile = os.getenv("ALLOW_MOBILE_UA", "").lower() in {"1", "true", "yes"}
    user_agents = fp_config.USER_AGENTS

    if not allow_mobile:
        user_agents = [
            ua for ua in user_agents
            if not re.search(r"\b(mobile|android|iphone|ipad)\b",
                           ua, re.IGNORECASE)
        ]
        if not user_agents:
            user_agents = fp_config.USER_AGENTS

    return {
        "user_agent": random.choice(user_agents),
        "viewport": random.choice(fp_config.VIEWPORTS),
    }


def configure_logging(
    log_path: Optional[Path] = None,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> None:
    """配置日志系统。

    Args:
        log_path: 日志文件路径。默认 logs/app.log。
        max_bytes: 单个日志文件大小上限（字节）。默认 10MB。
        backup_count: 保留的备份日志数量。默认 5。
    """
    if log_path is None:
        log_path = project_path("logs", "app.log")

    log_path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_path,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
    )
    handler.setFormatter(formatter)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    if not any(isinstance(h, RotatingFileHandler) for h in root_logger.handlers):
        root_logger.addHandler(handler)

    logger.add(
        handler,
        level="INFO",
        enqueue=True,
        backtrace=False,
        diagnose=False
    )


config = Config()


if __name__ == "__main__":
    config.print_summary()
