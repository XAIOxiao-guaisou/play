"""
能力层 (Base Layer) - 基础爬虫类

职责:
1. Playwright 浏览器初始化和生命周期管理
2. Stealth 反检测补丁注入
3. 人类行为模拟（鼠标移动、滚动、随机延迟、打字模拟）
4. Session 持久化管理（自动登录检测）
5. 指纹多样化（User-Agent、Viewport随机）
6. 行为随机化（正态分布）
7. 通用工具方法（截图、等待、异常处理）
"""

import asyncio
import random
import json
import time
import os
import tempfile
import re
import inspect
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime, timedelta
from urllib.parse import urlsplit, parse_qsl, urlunsplit, unquote
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

# playwright-stealth 在不同版本/分支中导出的函数名可能不同。
# 这里做兼容导入，避免因环境差异导致程序无法启动。
try:  # 常见: stealth_async
    from playwright_stealth import stealth_async as _pw_stealth
except Exception:  # noqa: BLE001
    try:  # 有些版本: stealth_sync
        from playwright_stealth import stealth_sync as _pw_stealth
    except Exception:  # noqa: BLE001
        try:  # 也可能直接叫 stealth
            from playwright_stealth import stealth as _pw_stealth
        except Exception:  # noqa: BLE001
            _pw_stealth = None
import yaml
from loguru import logger

# 导入统一配置
from config import (
    get_config,
    get_random_fingerprint,
    BehaviorRandomizer,
    SessionConfig,
    FingerprintConfig,
    project_path,
)

# 导入健康监控
from src.utils.health_monitor import (
    HealthMonitor,
    FailureAnalyzer,
    FailureReason,
    HealthLevel
)

# 导入人工干预拦截器
from src.utils.intervention_interceptor import (
    InterventionInterceptor,
    InterventionType,
    CaptchaDetector
)

# 导入协议级突破
from src.core.protocol_breakthrough import ProtocolBreakthrough, NetworkEnvironmentDetector


class BaseSpider:
    """基础爬虫类 - 提供浏览器能力、行为模拟和 Session 管理"""

    def __init__(
        self,
        config_path: str = "config.yaml",
        debug_mode: bool = False,
        platform: Optional[str] = None,
        use_persistent_session: bool = True,
        enable_health_monitor: bool = True,
        health_callback: Optional[callable] = None,
        enable_intervention: bool = True,
        intervention_timeout: int = 300,
        use_context_pool: bool = False,
    ) -> None:
        self.config = get_config()
        self.debug_mode = debug_mode
        self.platform = platform
        self.use_persistent_session = use_persistent_session
        self.use_context_pool = use_context_pool

        self.playwright: Optional[Playwright] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._login_prompted = False
        self._ocr_reader = None
        self._ocr_init_failed = False
        self._ocr_last_fail_ts: Optional[float] = None
        self._api_debug_dumped: set[str] = set()

        self.session_dir = project_path(SessionConfig.SESSION_DIR)
        self.session_dir.mkdir(parents=True, exist_ok=True)

        # 随机指纹和协议级突破
        self.fingerprint = get_random_fingerprint()
        fingerprint_config = FingerprintConfig()
        allow_mobile = os.getenv("ALLOW_MOBILE_UA", "").lower() in {"1", "true", "yes"}
        user_agents = fingerprint_config.USER_AGENTS
        if not allow_mobile:
            user_agents = [ua for ua in user_agents if not re.search(r"\b(mobile|android|iphone|ipad)\b", ua, re.IGNORECASE)]
            if not user_agents:
                user_agents = fingerprint_config.USER_AGENTS

        self.fingerprint.update({
            'USER_AGENTS': user_agents,
            'ACCEPT_LANGUAGES': fingerprint_config.ACCEPT_LANGUAGES,
        })
        self.protocol_breakthrough = ProtocolBreakthrough(
            require_china_network=fingerprint_config.REQUIRE_CHINA_NETWORK
        )

        # 健康监控
        self.health_monitor: Optional[HealthMonitor] = None
        if enable_health_monitor:
            self.health_monitor = HealthMonitor(
                window_size=100,
                consecutive_failures_threshold=5,
                failure_rate_danger=0.6,
                auto_pause=True,
                alert_callback=health_callback,
            )

        # 人工干预拦截器
        self.intervention_interceptor: Optional[InterventionInterceptor] = None
        if enable_intervention:
            try:
                self.intervention_interceptor = InterventionInterceptor(
                    check_interval=2.0,
                    timeout=intervention_timeout,
                    use_sound=True,
                    use_toast=True,
                )
            except Exception:
                logger.warning("初始化 InterventionInterceptor 失败，降级为 None")
                self.intervention_interceptor = None

    async def init_browser(self) -> None:
        """初始化浏览器、上下文与页面 (使用持久化上下文)"""
        if self.playwright:
            return

        headless = getattr(self.config.browser, 'headless', True)
        browser_type = getattr(self.config.browser, 'browser_type', 'msedge')
        proxy = getattr(self.config.browser, 'proxy', None)

        self.playwright = await async_playwright().start()

        # 使用本地数据目录，实现真正的浏览器持久化
        user_data_dir = project_path("data", "browser_data")
        user_data_dir.mkdir(parents=True, exist_ok=True)

        launch_kwargs: Dict[str, Any] = {
            'headless': headless,
            'user_data_dir': str(user_data_dir.absolute()),
            'args': [
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-infobars',
                '--start-maximized',
                # Windows/RDP/高 DPI 下偶发“窗口未最大化/显示不全/布局错位”，固定窗口参数提升稳定性
                '--window-position=0,0',
                '--window-size=1920,1080',
                '--force-device-scale-factor=1',
                '--high-dpi-support=1',
                '--disable-plugins-discovery',
            ]
        }

        if proxy:
            launch_kwargs['proxy'] = {'server': proxy}

        if browser_type == 'msedge':
            launch_kwargs['channel'] = 'msedge'
            launcher = self.playwright.chromium
        else:
            launcher = getattr(self.playwright, browser_type, self.playwright.chromium)

        # Viewport 和 UA 设置
        if headless:
            launch_kwargs['viewport'] = self.fingerprint.get('viewport')
            launch_kwargs['user_agent'] = self.fingerprint.get('user_agent')
        else:
            launch_kwargs['viewport'] = None  # Native viewport

        # HTTP Headers
        accept_langs = self.fingerprint.get('ACCEPT_LANGUAGES') or []
        if accept_langs:
            launch_kwargs['extra_http_headers'] = {'Accept-Language': accept_langs[0]}

        # 启动持久化上下文
        # 注意: launch_persistent_context 直接返回 context，不返回 browser
        logger.info(f"🚀 启动本地浏览器 (Persistent Context): {user_data_dir}")
        self.context = await launcher.launch_persistent_context(**launch_kwargs)
        self.browser = None # Persistent context 模式下没有独立的 browser 对象

        # 应用协议级突破
        await self.protocol_breakthrough.apply_to_context(self.context, self.fingerprint)

        # 获取或创建页面
        if self.context.pages:
            self.page = self.context.pages[0]
        else:
            self.page = await self.context.new_page()

        # 注入 Stealth 补丁
        await self._apply_stealth(self.page)
        await self._inject_anti_detection()
        logger.success("✅ 浏览器初始化完成 (Native Mode)")

    async def _apply_stealth(self, page: Page) -> None:
        """兼容调用 playwright-stealth 的注入函数。"""
        if _pw_stealth is None:
            return
        try:
            fn = _pw_stealth
            if not callable(fn):
                for name in ("stealth_async", "stealth_sync", "stealth"):
                    cand = getattr(fn, name, None)
                    if callable(cand):
                        fn = cand
                        break

            if not callable(fn):
                return

            result = fn(page)
            if inspect.isawaitable(result):
                await result
        except Exception as e:
            logger.debug(f"⚠️ stealth 注入失败(已忽略): {e}")

    @staticmethod
    def _resolve_edge_executable() -> Optional[str]:
        """尝试定位本地 Edge 安装路径，确保优先使用本机浏览器。"""
        candidates = [
            r"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
            r"C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
        ]
        for candidate in candidates:
            if Path(candidate).exists():
                return str(Path(candidate))
        return None
    
    async def _inject_anti_detection(self) -> None:
        """注入额外的反检测 JavaScript 代码 (Stealth 2.0)
        
        核心突破:
        1. 覆盖 navigator.webdriver
        2. WebGL 随机噪点注入 (仅 Headless)
        3. Canvas 指纹随机化 (仅 Headless)
        4. 模拟真实浏览器环境
        """
        
        # 基础绕过：webdriver (所有模式都需要)
        js_parts = [
            """
            // 1. 覆盖 navigator.webdriver
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // 2. 覆盖 permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
            
            // 3. 覆盖 languages
            Object.defineProperty(navigator, 'languages', {
                get: () => ['zh-CN', 'zh', 'en-US', 'en']
            });
            """
        ]

        # 强伪装模式：仅在 Headless 模式下启用 WebGL/Canvas 噪音和更深层的 Mock
        # 在有头模式下，使用真实浏览器的指纹反而更安全，注入噪音反而可能被识别为异常
        is_headless = getattr(self.config.browser, 'headless', False)
        
        if is_headless:
            js_parts.append("""
            // 4. 覆盖 plugins (仅 Headless)
            Object.defineProperty(navigator, 'plugins', {
                get: () => {
                    // 模拟常见的插件列表
                    const plugins = [
                        { name: 'PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                        { name: 'Chrome PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                        { name: 'Chromium PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                        { name: 'Microsoft Edge PDF Viewer', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
                        { name: 'WebKit built-in PDF', filename: 'internal-pdf-viewer', description: 'Portable Document Format' }
                    ];
                    return plugins;
                }
            });
            
            // 5. 模拟真实的 Chrome (仅 Headless)
            if (!window.chrome) {
                window.chrome = {
                    runtime: {}
                };
            }
            
            // 6. WebGL 随机噪点注入 (Stealth 2.0 核心 - 仅 Headless)
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                // 随机化 WebGL 渲染器和厂商信息
                if (parameter === 37445) {
                    return 'Intel Inc.';
                }
                if (parameter === 37446) {
                    return 'Intel Iris OpenGL Engine';
                }
                return getParameter.call(this, parameter);
            };
            
            // 7. Canvas 指纹随机化 (Stealth 2.0 核心 - 仅 Headless)
            const toBlob = HTMLCanvasElement.prototype.toBlob;
            const toDataURL = HTMLCanvasElement.prototype.toDataURL;
            const getImageData = CanvasRenderingContext2D.prototype.getImageData;
            
            // 生成随机噪点种子
            const noiseSeed = Math.random() * 0.0001;
            
            // 注入噪点到 Canvas
            HTMLCanvasElement.prototype.toBlob = function(callback, type, quality) {
                const context = this.getContext('2d');
                if (context) {
                    const imageData = context.getImageData(0, 0, this.width, this.height);
                    for (let i = 0; i < imageData.data.length; i += 4) {
                        imageData.data[i] += Math.floor(noiseSeed * 255);
                    }
                    context.putImageData(imageData, 0, 0);
                }
                return toBlob.call(this, callback, type, quality);
            };
            
            HTMLCanvasElement.prototype.toDataURL = function(type, quality) {
                const context = this.getContext('2d');
                if (context) {
                    const imageData = context.getImageData(0, 0, this.width, this.height);
                    for (let i = 0; i < imageData.data.length; i += 4) {
                        imageData.data[i] += Math.floor(noiseSeed * 255);
                    }
                    context.putImageData(imageData, 0, 0);
                }
                return toDataURL.call(this, type, quality);
            };
            console.log('✅ Stealth 2.0 (Headless Mode) 已激活: WebGL + Canvas 噪点注入完成');
            """)
        else:
            js_parts.append("""
            console.log('✅ Stealth 2.0 (Headful Mode) 已激活: 使用原生指纹，仅覆盖 webdriver');
            """)

        anti_detection_js = "\n".join(js_parts)
        await self.page.add_init_script(anti_detection_js)
        
        mode_str = "Headless (强伪装)" if is_headless else "Headful (原生指纹)"
        logger.success(f"✅ Stealth 2.0 已激活 [{mode_str}]")
    
    async def _setup_resource_blocking(self) -> None:
        """
        设置资源拦截（阻止 CSS、图片、字体等加载以提升性能）
        
        注意：Debug 模式下不会执行此方法
        """
        async def block_resources(route, request):
            """拦截并阻止特定资源类型"""
            resource_type = request.resource_type
            
            # 阻止的资源类型
            blocked_types = ['stylesheet', 'image', 'font', 'media']
            
            if resource_type in blocked_types:
                await route.abort()
            else:
                await route.continue_()
        
        # 注册路由拦截器
        await self.page.route('**/*', block_resources)
        logger.debug("已启用资源拦截（CSS、图片、字体）以提升性能")
    
    async def human_type(self, selector: str, text: str) -> None:
        """
        模拟人类打字行为（正态分布延迟）
        
        Args:
            selector: 输入框选择器
            text: 要输入的文本
        """
        await self.page.click(selector)
        await asyncio.sleep(BehaviorRandomizer.get_delay() * 0.3)  # 点击后的停顿
        
        for char in text:
            delay = BehaviorRandomizer.get_typing_delay()
            await self.page.type(selector, char, delay=delay)
            
        logger.debug(f"已模拟打字输入: {text[:20]}... (正态分布延迟)")
    
    async def human_click(self, selector: str, move_mouse: bool = True) -> None:
        """
        模拟人类点击行为（带正态分布的鼠标移动）
        
        Args:
            selector: 点击元素选择器
            move_mouse: 是否模拟鼠标移动
        """
        if move_mouse:
            # 获取元素位置
            box = await self.page.locator(selector).bounding_box()
            if box:
                # 目标位置（带随机偏移）
                target_x = box['x'] + box['width'] / 2 + random.uniform(-5, 5)
                target_y = box['y'] + box['height'] / 2 + random.uniform(-5, 5)
                
                # 获取当前鼠标位置（假设从随机起点）
                current_x = random.randint(0, self.fingerprint['viewport']['width'])
                current_y = random.randint(0, self.fingerprint['viewport']['height'])
                
                # 正态分布的移动步数
                steps = BehaviorRandomizer.get_mouse_steps()
                
                # 分步移动鼠标（贝塞尔曲线模拟）
                for i in range(steps):
                    t = (i + 1) / steps
                    # 使用缓动函数使移动更自然
                    eased_t = t * t * (3 - 2 * t)  # Smoothstep
                    
                    x = current_x + (target_x - current_x) * eased_t + random.uniform(-2, 2)
                    y = current_y + (target_y - current_y) * eased_t + random.uniform(-2, 2)
                    
                    await self.page.mouse.move(x, y)
                    await asyncio.sleep(0.01)
                
                await asyncio.sleep(BehaviorRandomizer.get_delay() * 0.1)
        
        await self.page.click(selector)
        logger.debug(f"已点击元素: {selector} (正态分布鼠标移动)")
    
    async def human_scroll(self, distance: int = None, smooth: bool = True) -> None:
        """
        模拟人类滚动行为（正态分布距离）
        
        Args:
            distance: 滚动距离（像素），不传则使用正态分布随机
            smooth: 是否平滑滚动
        """
        if distance is None:
            distance = BehaviorRandomizer.get_scroll_distance()
        
        if smooth:
            # 正态分布的滚动步数
            steps = random.randint(5, 10)
            step_distance = distance // steps
            
            for _ in range(steps):
                await self.page.evaluate(f'window.scrollBy(0, {step_distance})')
                await asyncio.sleep(BehaviorRandomizer.get_delay() * 0.05)
        else:
            await self.page.evaluate(f'window.scrollBy(0, {distance})')
        
        logger.debug(f"已滚动 {distance} 像素 (正态分布)")
    
    async def scroll_to_bottom(self, max_scrolls: int = 10, delay_range: tuple = (1, 3)) -> None:
        """
        滚动到页面底部（模拟真实用户逐步滚动，正态分布延迟）
        
        Args:
            max_scrolls: 最大滚动次数
            delay_range: 每次滚动的延迟范围（秒）- 废弃，使用正态分布
        """
        for i in range(max_scrolls):
            # 获取当前滚动位置
            prev_height = await self.page.evaluate('document.body.scrollHeight')
            
            # 滚动一段距离（正态分布）
            await self.human_scroll()
            
            # 正态分布延迟
            await asyncio.sleep(BehaviorRandomizer.get_delay())
            
            # 检查是否到底
            new_height = await self.page.evaluate('document.body.scrollHeight')
            if new_height == prev_height:
                logger.debug("已滚动到页面底部")
                break
    
    async def wait_for_selector(self, selector: str, timeout: int = 30000, state: str = 'visible') -> bool:
        """
        智能等待元素出现（替代固定延迟）
        
        Args:
            selector: 元素选择器
            timeout: 超时时间（毫秒）
            state: 等待状态 ('visible', 'attached', 'hidden')
            
        Returns:
            是否成功等到元素
        """
        try:
            await self.page.wait_for_selector(selector, timeout=timeout, state=state)
            logger.debug(f"✅ 元素已加载: {selector}")
            return True
        except Exception as e:
            logger.warning(f"⏱️ 等待元素 {selector} 超时: {e}")
            return False
    
    async def wait_for_load_state(self, state: str = 'networkidle', timeout: int = 30000) -> bool:
        """
        智能等待页面加载状态（替代固定延迟）
        
        Args:
            state: 加载状态 
                - 'load': 页面 load 事件触发
                - 'domcontentloaded': DOMContentLoaded 事件触发
                - 'networkidle': 网络空闲（至少500ms无网络连接）
            timeout: 超时时间（毫秒）
            
        Returns:
            是否成功等到状态
        """
        try:
            await self.page.wait_for_load_state(state, timeout=timeout)
            logger.debug(f"✅ 页面已到达 {state} 状态")
            return True
        except Exception as e:
            logger.warning(f"⏱️ 等待 {state} 状态超时: {e}")
            return False
    
    async def random_delay(self, min_sec: float = 1.0, max_sec: float = 3.0) -> None:
        """
        随机延迟（正态分布）
        
        Args:
            min_sec: 最小延迟（秒）
            max_sec: 最大延迟（秒）
        """
        delay = BehaviorRandomizer.get_delay(min_sec, max_sec)
        await asyncio.sleep(delay)
    
    async def wait_for_selector(self, selector: str, timeout: int = 30000, state: str = 'visible') -> bool:
        """
        等待元素出现
        
        Args:
            selector: 元素选择器
            timeout: 超时时间（毫秒）
            state: 等待状态 ('visible', 'attached', 'hidden')
            
        Returns:
            是否成功等到元素
        """
        try:
            await self.page.wait_for_selector(selector, timeout=timeout, state=state)
            return True
        except Exception as e:
            logger.warning(f"等待元素 {selector} 超时: {e}")
            return False
    
    async def screenshot(self, path: str = None, full_page: bool = True) -> str:
        """
        截图
        
        Args:
            path: 保存路径，不传则自动生成
            full_page: 是否截取整个页面
            
        Returns:
            截图保存路径
        """
        if path is None:
            timestamp = asyncio.get_event_loop().time()
            path = f"./logs/screenshot_{int(timestamp)}.png"
        
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        await self.page.screenshot(path=path, full_page=full_page)
        logger.info(f"已截图: {path}")
        return path
    
    async def get_page_content(self) -> str:
        """获取页面 HTML 内容"""
        return await self._safe_page_content()

    async def _safe_page_content(self, timeout: int = 5000) -> str | None:
        """在可能的导航过程中安全获取页面内容，避免 Page.content 抛错。"""
        if not self.page:
            return None
        try:
            await self.page.wait_for_load_state('domcontentloaded', timeout=timeout)
        except Exception:
            # 即使仍在导航也尝试读取，若失败则返回 None
            pass
        try:
            return await self.page.content()
        except Exception as e:
            logger.debug(f"⚠️ 获取页面内容失败（可能仍在导航）：{e}")
            return None

    def _has_login_signal(self, content: str | None) -> bool:
        """粗略检测页面中是否含登录提示关键词。"""
        if not content:
            return False
        body_snippet = content[:5000].lower()
        login_signals = ["登录", "login", "passport", "account-login", "verify"]
        return any(sig.lower() in body_snippet for sig in login_signals)

    async def _detect_login_overlay(self) -> Dict[str, Any]:
        """基于页面结构的轻量视觉理解，探测是否存在登录弹窗或二维码区域。"""
        if not self.page:
            return {}

        script = """
        () => {
            const containsLoginText = (el) => {
                const t = (el.innerText || '').toLowerCase();
                return ['登录','login','验证码','扫码','手机号','password','verify'].some(k => t.includes(k));
            };

            const candidates = Array.from(document.querySelectorAll('div,section,aside,main'))
                .filter((el) => {
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return false;
                    const area = el.offsetWidth * el.offsetHeight;
                    if (!area || area < 20000) return false;
                    const z = parseInt(style.zIndex || '0', 10);
                    const fixed = style.position === 'fixed' || style.position === 'sticky';
                    if (!containsLoginText(el)) return false;
                    return (fixed && z >= 10) || z >= 999;
                })
                .slice(0, 5)
                .map((el) => ({
                    text: (el.innerText || '').slice(0, 120),
                    z: window.getComputedStyle(el).zIndex,
                    rect: { w: el.offsetWidth, h: el.offsetHeight },
                    cls: el.className,
                }));

            const qrImg = Array.from(document.images).find((img) => {
                const src = img.src || '';
                const alt = (img.alt || '').toLowerCase();
                const area = (img.naturalWidth || img.width || 0) * (img.naturalHeight || img.height || 0);
                return area > 30000 && (src.includes('qr') || alt.includes('qr') || alt.includes('码'));
            });

            const phoneInput = document.querySelector('input[type="tel"], input[placeholder*="手机"], input[placeholder*="phone"]');
            const smsBtn = Array.from(document.querySelectorAll('button,div,span'))
                .find((el) => (el.innerText || '').includes('验证码'));

            return {
                has_modal: candidates.length > 0,
                overlays: candidates,
                has_qr: Boolean(qrImg),
                qr_src: qrImg ? qrImg.src : null,
                has_phone_input: Boolean(phoneInput),
                has_sms_button: Boolean(smsBtn),
            };
        }
        """

        try:
            detection = await self.page.evaluate(script)
            return detection or {}
        except Exception as exc:
            logger.debug(f"[LoginCheck] 视觉检测失败: {exc}")
            return {}

    async def _get_ocr_reader(self):
        """延迟初始化 OCR Reader（依赖 easyocr，缺失则跳过）。"""
        if self._ocr_reader:
            return self._ocr_reader

        # 若近期初始化失败（通常是模型下载中断），先冷却一段时间再重试，避免刷屏。
        if self._ocr_init_failed and self._ocr_last_fail_ts is not None:
            if (time.monotonic() - self._ocr_last_fail_ts) < 60:
                return None
            # 允许重试
            self._ocr_init_failed = False

        try:
            import easyocr  # type: ignore
        except Exception as exc:
            logger.debug(f"[LoginCheck][OCR] easyocr 未安装或导入失败: {exc}")
            self._ocr_init_failed = True
            return None

        try:
            # 固定模型目录，便于手动下载/缓存（也避免默认写到用户目录导致权限/多环境混乱）
            model_dir = project_path("data", "ocr_models")
            model_dir.mkdir(parents=True, exist_ok=True)

            # Pillow>=10 移除了 Image.ANTIALIAS，部分 easyocr 版本仍会引用；这里做兼容兜底
            try:
                from PIL import Image  # type: ignore

                if not hasattr(Image, "ANTIALIAS") and hasattr(Image, "Resampling"):
                    Image.ANTIALIAS = Image.Resampling.LANCZOS  # type: ignore[attr-defined]
            except Exception:
                pass

            # GPU 可能不可用，显式关闭
            # download_enabled=True 会自动下载模型；若网络不稳会抛异常，这里会进入重试逻辑
            self._ocr_reader = easyocr.Reader(
                ['ch_sim', 'en'],
                gpu=False,
                model_storage_directory=str(model_dir.absolute()),
                download_enabled=True,
            )
            logger.info(f"[LoginCheck][OCR] easyocr Reader 初始化完成 (model_dir={model_dir})")
        except Exception as exc:
            # 常见：<urlopen error retrieval incomplete ...>
            logger.warning(f"[LoginCheck][OCR] 初始化失败（可能模型下载中断）: {exc}")
            logger.warning("[LoginCheck][OCR] 你可以稍后重试，或手动把模型文件放到 data/ocr_models 后再启动")
            self._ocr_init_failed = True
            self._ocr_last_fail_ts = time.monotonic()
            self._ocr_reader = None

        return self._ocr_reader

    async def _ocr_login_overlay(self) -> Dict[str, Any]:
        """OCR 辅助理解：截图并识别登录相关文本信号。"""
        if not self.page:
            return {}

        reader = await self._get_ocr_reader()
        if not reader:
            return {}

        tmp_path = None
        try:
            shot_bytes = await self.page.screenshot(full_page=False)
            with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
                tmp.write(shot_bytes)
                tmp_path = tmp.name

            results = reader.readtext(tmp_path, detail=1, paragraph=False) or []
            texts = [r[1] for r in results if len(r) > 1]
            combined = " ".join(texts).lower()
            signals = ["登录", "login", "验证码", "扫码", "phone", "手机号", "sms"]
            has_login = any(sig.lower() in combined for sig in signals)

            return {
                'enabled': True,
                'has_login': has_login,
                'text_count': len(texts),
                'texts': texts[:20],
            }
        except Exception as exc:
            logger.debug(f"[LoginCheck][OCR] 识别失败: {exc}")
            return {}
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    async def _observe_login_flow(self, explore_url: str, cycles: int = 3) -> Dict[str, Any]:
        """从页面加载开始循环观察，结合视觉+OCR，并尝试主动触发登录 CTA。"""
        history: List[Dict[str, Any]] = []
        for idx in range(cycles):
            visual = await self._detect_login_overlay()
            ocr_info = await self._ocr_login_overlay()
            current_url = self.page.url if self.page else ''

            snapshot = {
                'url': current_url,
                'visual': visual,
                'ocr': ocr_info,
                'cycle': idx + 1,
            }
            history.append(snapshot)

            if visual.get('has_modal') or visual.get('has_qr') or visual.get('has_phone_input') or ocr_info.get('has_login'):
                logger.info(
                    "[LoginCheck] 视觉/OCR 检测到登录提示 (cycle=%s, url=%s)",
                    idx + 1,
                    current_url,
                )
                return {'needs_login': True, 'triggered': False, 'history': history}

            # 若无信号，尝试点击登录入口拉起弹窗
            triggered = await self._force_login_prompt()
            if triggered:
                await self.wait_for_load_state('domcontentloaded', timeout=8000)
                return {'needs_login': True, 'triggered': True, 'history': history}

            await asyncio.sleep(1.2)

        return {'needs_login': False, 'triggered': False, 'history': history}

    async def _force_login_prompt(self) -> bool:
        """在小红书首页主动点击登录入口以拉起登录弹窗。"""
        if not self.page:
            return False

        # 0) 暴力尝试：针对 XHS 侧边栏的特定选择器（最优先）
        # 这些选择器基于常见的侧边栏结构推测，使用 force=True 强点
        xhs_sidebar_selectors = [
            ".side-bar .login-btn",
            ".side-bar-container .login-button",
            "#global .side-bar button",
            "div[class*='side-bar'] button:has-text('登录')",
            "div[class*='side-bar'] div:has-text('登录')",
        ]
        for sel in xhs_sidebar_selectors:
            try:
                loc = self.page.locator(sel)
                if await loc.count() > 0:
                    # 只要存在，就尝试点击，不管是否可见（force=True）
                    logger.info(f"[LoginCheck] 尝试暴力点击侧边栏选择器: {sel}")
                    await loc.first.click(force=True, timeout=2000)
                    await self.random_delay(0.8, 1.5)
                    # 检查是否生效
                    visual = await self._detect_login_overlay()
                    if visual.get('has_modal') or visual.get('has_qr') or visual.get('has_phone_input'):
                        logger.info(f"[LoginCheck] 通过 {sel} 成功拉起登录弹窗")
                        return True
            except Exception:
                continue

        # 1) 智能定位：定位左侧栏的大按钮“登录”，避免误点顶部“登录探索更多内容”等文案
        try:
            pick = await self.page.evaluate(
                """
                () => {
                  const isVisible = (el) => {
                    if (!el) return false;
                    const style = window.getComputedStyle(el);
                    if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) return false;
                    const rect = el.getBoundingClientRect();
                    return rect.width > 0 && rect.height > 0;
                  };

                  const candidates = Array.from(document.querySelectorAll('button,a,div,span'))
                    .filter((el) => {
                      const t = (el.innerText || '').trim();
                      if (t !== '登录') return false;
                      if (!isVisible(el)) return false;
                      const rect = el.getBoundingClientRect();
                      // 左侧栏区域（大致）
                      if (rect.left > 420) return false;
                      // 需要有一定尺寸，排除小文字
                      if (rect.width < 60 || rect.height < 28) return false;
                      // 必须可点：pointer 或 role
                      const style = window.getComputedStyle(el);
                      const clickable = style.cursor === 'pointer' || el.tagName === 'BUTTON' || el.tagName === 'A' || el.getAttribute('role') === 'button';
                      return clickable;
                    })
                    .map((el) => {
                      const r = el.getBoundingClientRect();
                      const cx = r.left + r.width / 2;
                      const cy = r.top + r.height / 2;
                      const topEl = document.elementFromPoint(cx, cy);
                      const covered = topEl && !el.contains(topEl) && !topEl.contains(el);
                      return {
                        tag: el.tagName,
                        cls: el.className || '',
                        rect: { left: r.left, top: r.top, width: r.width, height: r.height },
                        center: { x: cx, y: cy },
                        covered,
                        topTag: topEl ? topEl.tagName : null,
                        topCls: topEl ? (topEl.className || '') : null,
                        area: r.width * r.height,
                      };
                    })
                    .sort((a, b) => b.area - a.area);

                  return candidates.length ? candidates[0] : null;
                }
                """
            )

            if pick and pick.get('center'):
                x = float(pick['center']['x'])
                y = float(pick['center']['y'])
                logger.info(
                    f"[LoginCheck] 尝试点击左侧登录按钮: tag={pick.get('tag')} covered={pick.get('covered')} at=({x:.0f},{y:.0f})"
                )
                await self.page.mouse.click(x, y)
                await self.random_delay(0.6, 1.2)

                # 强校验：是否出现弹窗/二维码/手机号输入
                visual = await self._detect_login_overlay()
                if visual.get('has_modal') or visual.get('has_qr') or visual.get('has_phone_input'):
                    logger.info("[LoginCheck] 已点击左侧登录按钮并检测到登录弹窗")
                    return True

                # 再补一层：常见弹窗 DOM
                modal_selectors = [
                    ".login-container, .login-modal, .login-dialog, [class*='login']",
                    "img[alt*='码'], img[src*='qr']",
                    "input[type='tel'], input[placeholder*='手机']",
                ]
                for sel in modal_selectors:
                    try:
                        loc = self.page.locator(sel)
                        if await loc.count() > 0:
                            if await loc.first.is_visible():
                                logger.info(f"[LoginCheck] 检测到登录弹窗信号: {sel}")
                                return True
                    except Exception:
                        continue
        except Exception as exc:
            logger.debug(f"[LoginCheck] 左侧登录按钮定位/点击失败: {exc}")

        # 2) 回退：用更收敛的选择器（避免 div:has-text('登录') 这种误命中）
        fallback_selectors = [
            "button:has-text('登录')",
            "a:has-text('登录')",
            "[role='button']:has-text('登录')",
        ]

        for selector in fallback_selectors:
            try:
                loc = self.page.locator(selector)
                if await loc.count() == 0:
                    continue
                await loc.first.scroll_into_view_if_needed(timeout=3000)
                await loc.first.click(timeout=3000)
                await self.random_delay(0.6, 1.2)
                visual = await self._detect_login_overlay()
                if visual.get('has_modal') or visual.get('has_qr') or visual.get('has_phone_input'):
                    logger.info(f"[LoginCheck] 已通过 {selector} 拉起登录弹窗")
                    return True
            except Exception:
                continue

        logger.debug("[LoginCheck] 未能拉起登录弹窗：可能被站点风控禁用按钮或页面结构变更")
        return False

    async def _prepare_for_manual_interaction(self) -> None:
        """进入需要人工操作前，尽量确保窗口可交互且不被脚本打断。"""
        if not self.page:
            return
        try:
            # 将页面置前（Windows/RDP 下尤其有用）
            await self.page.bring_to_front()
        except Exception:
            pass

        # 可选：在等待人工登录期间暂停任何“主动触发登录/跳转”的脚本逻辑
        # 通过环境变量控制，避免默认改变行为。
        if os.getenv("MANUAL_LOGIN_ONLY", "").lower() in {"1", "true", "yes"}:
            self._login_prompted = True
    
    async def evaluate(self, script: str) -> Any:
        """执行 JavaScript 代码"""
        return await self.page.evaluate(script)
    
    async def goto(self, url: str, wait_until: str = 'domcontentloaded', timeout: int = 30000) -> None:
        """
        访问 URL
        
        Args:
            url: 目标 URL
            wait_until: 等待条件 ('load', 'domcontentloaded', 'networkidle')
            timeout: 超时时间（毫秒）
        """
        pretty_url = self._pretty_url_for_log(url)
        logger.info(f"正在访问: {pretty_url}")
        if pretty_url != url:
            logger.debug(f"[URL] raw={url}")
        
        start_time = time.time()
        try:
            # 检查是否暂停
            if self.health_monitor and self.health_monitor.is_paused:
                logger.error("⏸️ 爬虫已暂停，无法执行请求")
                raise Exception("爬虫已暂停，请调用 health_monitor.resume() 恢复")
            
            response = await self.page.goto(url, wait_until=wait_until, timeout=timeout)
            status_code = response.status if response else None
            if status_code in {401, 403, 404}:
                logger.warning(f"⚠️ 请求返回异常状态码: {status_code} - 可能未登录或地区限制")
                if (
                    self.platform == 'xiaohongshu'
                    and not self._login_prompted
                    and self.config
                    and getattr(self.config, 'xiaohongshu', None)
                ):
                    login_url = getattr(self.config.xiaohongshu, 'login_url', None)
                    if login_url and login_url not in url:
                        self._login_prompted = True
                        logger.info(f"➡️ 状态码 {status_code}，尝试打开登录页: {login_url}")
                        response = await self.page.goto(login_url, wait_until='domcontentloaded', timeout=timeout)
                        status_code = response.status if response else status_code

            await self.random_delay(1, 2)  # 页面加载后的停顿

            # 记录状态/标题，辅助空白页诊断
            try:
                title = await self.page.title()
                current_url = self.page.url
                logger.info(f"🌐 加载完成: status={status_code}, title='{title}', url={current_url}")
            except Exception:
                pass

            # 登录页或 4xx/空白时：截图 + 一次性自愈 reload（解决偶发渲染半截/空白）
            content_snippet = await self._safe_page_content()
            is_suspicious_blank = bool(content_snippet is not None and len(content_snippet) < 800)
            if (status_code and status_code >= 400) or ('/login' in self.page.url) or is_suspicious_blank:
                shot = await self.screenshot()
                logger.warning(
                    f"⚠️ 页面异常/空白: status={status_code}, len={len(content_snippet) if content_snippet else 0}, 已截图: {shot}"
                )

                # 只在非 4xx 且不是登录页时尝试一次 reload（避免干扰人工登录流程）
                if (not status_code or status_code < 400) and ('/login' not in self.page.url):
                    try:
                        logger.info("🔄 页面疑似未渲染完整，尝试 reload 自愈一次...")
                        await self.page.reload(wait_until='domcontentloaded', timeout=timeout)
                        await self.random_delay(0.8, 1.4)
                        content_snippet = await self._safe_page_content()
                        logger.info(f"🔄 reload 后页面内容长度: {len(content_snippet) if content_snippet else 0}")
                    except Exception as _reload_exc:
                        logger.debug(f"reload 自愈失败(已忽略): {_reload_exc}")

            # 登录状态提示（软提示，不中断流程）：检测页面内容中是否出现登录提示关键词
            # 注意：小红书 /explore 页面本身就含“登录探索更多内容”等文案，不能据此自动跳转到 /login，
            # 否则会打断用户在首页弹窗中的扫码/短信登录操作。
            body_snippet = (content_snippet or "")[:5000].lower()
            login_signals = ["登录", "login", "passport", "account-login", "verify"]
            if any(sig.lower() in body_snippet for sig in login_signals):
                logger.warning("⚠️ 可能未登录：页面包含登录提示，建议先完成登录再抓取。")
            
            # 检查验证码并等待人工处理
            if self.intervention_interceptor:
                success = await self.intervention_interceptor.check_and_wait(self.page)
                if not success:
                    logger.error("❌ 人工干预失败（超时或验证失败）")
                    if self.health_monitor:
                        self.health_monitor.record_failure(
                            FailureReason.CAPTCHA_REQUIRED,
                            {'url': url, 'reason': '人工干预超时'}
                        )
                    raise Exception("人工干预失败：验证码处理超时")
            
            # 记录成功
            if self.health_monitor:
                response_time = time.time() - start_time
                self.health_monitor.record_success(response_time)
        
        except Exception as e:
            # 分析失败原因
            if self.health_monitor:
                page_content = await self._safe_page_content()
                reason = FailureAnalyzer.analyze_error(e, page_content)
                self.health_monitor.record_failure(reason, {
                    'url': url,
                    'error': str(e)
                })
            raise

    @staticmethod
    def _pretty_url_for_log(url: str) -> str:
        """让日志里 URL 更可读（仅用于显示，不影响真实请求）。

        典型场景：keyword=xxx 被 percent-encoding 后在日志里像“乱码”。
        """
        try:
            parts = urlsplit(url)
            if not parts.query or "keyword=" not in parts.query:
                return url

            q = parse_qsl(parts.query, keep_blank_values=True)
            if not q:
                return url

            items: list[str] = []
            for k, v in q:
                if k == "keyword":
                    items.append(f"{k}={unquote(v)}")
                else:
                    items.append(f"{k}={v}")

            return urlunsplit((parts.scheme, parts.netloc, parts.path, "&".join(items), parts.fragment))
        except Exception:
            return url

    async def _navigate_via_search_engine(self, keyword: str = "小红书") -> None:
        """通过搜索引擎（Bing）模拟人工搜索进入目标网站"""
        try:
            logger.info("🔍 [Navigation] 正在访问 Bing 搜索...")
            await self.page.goto("https://cn.bing.com", wait_until='domcontentloaded')
            await self.random_delay(1, 2)

            # 寻找搜索框
            search_input = self.page.locator("#sb_form_q")
            if await search_input.count() == 0:
                search_input = self.page.locator("[name='q']")
            
            if await search_input.count() > 0:
                # 模拟人工输入
                await self.human_type("#sb_form_q" if await self.page.locator("#sb_form_q").count() > 0 else "[name='q']", keyword)
                await self.random_delay(0.5, 1)
                await self.page.keyboard.press("Enter")
                
                # 等待结果
                await self.page.wait_for_selector("h2 a", timeout=10000)
                await self.random_delay(1, 3)
                
                # 寻找目标 (优先找 href 包含 xiaohongshu.com 的)
                target = self.page.locator("h2 a[href*='xiaohongshu.com']").first
                if await target.count() > 0:
                    logger.info("✅ [Navigation] 找到小红书链接，正在点击...")
                    
                    # 检查是否新标签页打开
                    is_new_tab = await target.get_attribute("target") == "_blank"
                    
                    if is_new_tab:
                        async with self.context.expect_page() as new_page_info:
                            await target.click()
                        new_page = await new_page_info.value
                        await new_page.wait_for_load_state('domcontentloaded')
                        
                        # 切换 self.page
                        old_page = self.page
                        self.page = new_page
                        await old_page.close() # 关闭搜索页
                        
                        # 新页面重新注入 stealth
                        await self._apply_stealth(self.page)
                        await self._inject_anti_detection()
                        logger.info("🔄 [Navigation] 已切换至新标签页")
                    else:
                        await target.click()
                        await self.page.wait_for_load_state('networkidle')

                    logger.success(f"✅ [Navigation] 已通过搜索进入: {self.page.url}")
                else:
                    logger.warning("⚠️ 未在搜索结果中找到小红书链接")
                    raise Exception("Target link not found")
            else:
                raise Exception("Search input not found")

        except Exception as e:
            logger.warning(f"⚠️ [Navigation] 搜索跳转失败: {e}，回退到直接访问")
            explore_url = getattr(self.config.xiaohongshu, 'explore_url', "https://www.xiaohongshu.com/explore")
            await self.goto(explore_url, wait_until='networkidle')

    async def ensure_login_ready(self) -> None:
        """
        确保登录就绪：
        1. 通过搜索引擎进入 (模拟人工)
        2. 检查登录状态
        3. 若未登录，尝试唤起弹窗
        4. 等待人工登录
        """
        if self.platform != 'xiaohongshu':
            return

        # 1. 通过搜索引擎进入
        await self._navigate_via_search_engine("小红书")
        
        # 2. 检查是否已登录
        if await self.check_login_status():
            logger.success("✅ [LoginCheck] 已处于登录状态，无需干预")
            return

        logger.warning("⚠️ [LoginCheck] 未检测到登录状态，准备唤起登录流程...")

        # 3. 检测当前是否有弹窗
        visual = await self._detect_login_overlay()
        has_overlay = visual.get('has_modal') or visual.get('has_qr') or visual.get('has_phone_input')

        # 4. 如果没有弹窗，尝试暴力点击唤起
        if not has_overlay:
            logger.info("👉 [LoginCheck] 未发现登录弹窗，尝试主动点击侧边栏...")
            if await self._force_login_prompt():
                logger.success("✅ [LoginCheck] 成功唤起登录弹窗")
            else:
                logger.warning("❌ [LoginCheck] 自动唤起失败，请手动点击左侧'登录'按钮")

        # 5. 强制进入等待循环 (无论是否检测到弹窗，只要没登录就等)
        # 检查是否启用了“免登录模式”（无痕爆破）
        if getattr(self.config.scraper, 'allow_no_login', False):
            logger.warning("⚠️ [LoginCheck] 检测到需要登录，但已启用 'allow_no_login' 模式，跳过强制等待！")
            logger.info("🚀 尝试以未登录状态继续抓取（可能受限）...")
            return

        self._login_prompted = True
        await self._prepare_for_manual_interaction()
        
        logger.info("⏳ [LoginCheck] 进入人工登录等待模式 (限时 180s)...")
        success = await self._wait_for_login_success(timeout_sec=getattr(SessionConfig, 'LOGIN_TIMEOUT', 180))
        
        if success:
            logger.success("🎉 [LoginCheck] 登录成功！保存会话...")
            if self.use_persistent_session:
                await self.save_session()
        else:
            raise Exception("登录超时或失败，无法继续抓取")

    async def _wait_for_login_success(self, timeout_sec: int = 180) -> bool:
        """等待登录成功（以成功选择器为准），避免误判导致提前继续抓取。"""
        if not self.page:
            return False

        selector = SessionConfig.LOGIN_SUCCESS_SELECTORS.get(self.platform or '')
        deadline = time.monotonic() + max(5, int(timeout_sec or 180))

        # 轮询等待：尽量不执行任何会影响交互的操作
        last_log = 0.0
        while time.monotonic() < deadline:
            try:
                if selector:
                    loc = self.page.locator(selector)
                    if await loc.count() > 0:
                        try:
                            if await loc.first.is_visible():
                                logger.success("✅ 已检测到登录成功标志")
                                return True
                        except Exception:
                            # 有元素但暂不可见，继续等
                            pass

                # 备选弱信号：URL 不在 login 且页面上不再出现明显“登录”入口/弹窗
                # （避免 selector 变更时完全卡死）
                current_url = self.page.url or ''
                if 'login' not in current_url.lower():
                    visual = await self._detect_login_overlay()
                    if not (visual.get('has_modal') or visual.get('has_qr') or visual.get('has_phone_input')):
                        # “登录”按钮可能仍存在，但至少不在登录页/弹窗中；再做一次 selector 检查后继续
                        if not selector:
                            return True

                # 周期性提示剩余时间
                now = time.monotonic()
                if now - last_log > 10:
                    last_log = now
                    remaining = int(deadline - now)
                    logger.info(f"⏳ 等待你完成登录... (剩余 {remaining}s)")

            except Exception:
                # 页面可能在导航中，稍后重试
                pass

            await asyncio.sleep(1.5)

        logger.error("❌ 等待登录超时")
        return False
    
    async def close(self) -> None:
        """关闭浏览器并清理资源
        
        ⚠️ 核心规则 (Session 持久化红线):
        - 禁止调用 self.context.close() 或 self.page.close()
        - 必须仅使用 self.playwright.stop() 以确保 browser_profile 缓存不被损毁
        - 96.7MB+ 的 Session 数据必须完整保留
        """
        # 打印健康报告
        if self.health_monitor:
            self.health_monitor.print_report()
            self.health_monitor.save_report()
        
        # ❌ 禁止执行：await self.page.close()
        # ✅ 允许关闭 Context (Persistent Context 模式下，数据已落盘，关闭是安全的)
        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass
        # ❌ 禁止执行：await self.browser.close()
        
        # ✅ 仅停止 Playwright，保留所有 Session 缓存
        if self.playwright:
            await self.playwright.stop()
            logger.success("✅ 浏览器已安全关闭 (Session 数据已完整保留)")
        else:
            logger.info("浏览器未初始化，跳过关闭")
    
    async def check_captcha(self) -> bool:
        """
        手动检查验证码
        
        Returns:
            是否通过验证（无验证码或人工处理成功）
        """
        if not self.intervention_interceptor or not self.page:
            return True
        
        return await self.intervention_interceptor.check_and_wait(self.page)
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self.init_browser()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        # 退出时保存 Session
        if self.use_persistent_session and self.platform:
            await self.save_session()
        
        await self.close()
    
    # ==================== Session 持久化管理 ====================
    
    def _get_session_path(self) -> Path:
        """获取 Session 存储路径"""
        if not self.platform:
            raise ValueError("平台名称未设置，无法使用 Session 持久化")
        return self.session_dir / f"{self.platform}_session.json"
    
    async def save_session(self) -> None:
        """保存当前 Session 到文件"""
        if not self.use_persistent_session or not self.platform:
            return
        
        try:
            session_path = self._get_session_path()
            storage_state = await self.context.storage_state()
            
            # 添加时间戳
            storage_state['timestamp'] = datetime.now().isoformat()
            
            with open(session_path, 'w', encoding='utf-8') as f:
                json.dump(storage_state, f, ensure_ascii=False, indent=2)
            
            logger.success(f"💾 Session 已保存: {session_path}")
        except Exception as e:
            logger.error(f"保存 Session 失败: {e}")
    
    def is_session_expired(self) -> bool:
        """检查 Session 是否过期"""
        session_path = self._get_session_path()
        
        if not session_path.exists():
            return True
        
        try:
            with open(session_path, 'r', encoding='utf-8') as f:
                storage_state = json.load(f)
            
            timestamp_str = storage_state.get('timestamp')
            if not timestamp_str:
                return True
            
            timestamp = datetime.fromisoformat(timestamp_str)
            expire_days = getattr(SessionConfig, 'EXPIRE_DAYS', 30)
            
            is_expired = (datetime.now() - timestamp).days > expire_days
            
            if is_expired:
                logger.warning(f"⏰ Session 已过期（超过 {expire_days} 天）")
            else:
                logger.info(f"✅ Session 仍然有效")
            
            return is_expired
            
        except Exception as e:
            logger.error(f"检查 Session 过期失败: {e}")
            return True
    
    async def check_login_status(self) -> bool:
        """
        检查当前登录状态 (Cookie + DOM)
        
        Returns:
            True: 已登录, False: 未登录
        """
        if not self.page:
            return False
        
        has_session = False
        overlay_has_login = False
        # 1. 检查 Cookie (web_session)
        try:
            cookies = await self.context.cookies()
            has_session = any(c['name'] == 'web_session' for c in cookies)
            if has_session:
                logger.debug("✅ [LoginCheck] 检测到 web_session Cookie")
                # 即使有 Cookie，也建议校验一下页面元素，防止 Cookie 过期但未清除
            else:
                logger.debug("⚠️ [LoginCheck] 未检测到 web_session Cookie")
        except Exception as e:
            logger.warning(f"检查 Cookie 失败: {e}")

        # 1.1 检测是否存在登录遮罩/二维码，避免仅凭 Cookie 误判已登录
        try:
            visual = await self._detect_login_overlay()
            overlay_has_login = bool(
                visual.get('has_modal')
                or visual.get('has_qr')
                or visual.get('has_phone_input')
            )
        except Exception as exc:
            logger.debug(f"[LoginCheck] 登录遮罩检测失败(已忽略): {exc}")

        # 2. 检查 DOM (头像/用户卡片)
        try:
            selector = SessionConfig.LOGIN_SUCCESS_SELECTORS.get(self.platform or 'xiaohongshu')
            if selector:
                # 使用 waitForSelector 的极短超时版本来检测
                try:
                    await self.page.wait_for_selector(selector, state='visible', timeout=3000)
                    logger.success("✅ [LoginCheck] DOM 检测到登录状态 (头像/用户卡片)")
                    return True
                except Exception:
                    pass
        except Exception as e:
            logger.error(f"检查登录状态失败: {e}")

        # 3. 检查明确的未登录标志 (如侧边栏登录按钮)
        # 如果页面上明确显示了“登录”按钮，说明 Cookie 可能已失效
        try:
            # 针对小红书侧边栏登录按钮的检测
            login_btn_selectors = [
                ".side-bar .login-btn", 
                ".side-bar-container .login-button",
                ".side-bar button",
                ".login-container"
            ]
            for sel in login_btn_selectors:
                # 查找可见的、包含“登录”文本的按钮
                btn = self.page.locator(sel).filter(has_text="登录").first
                if await btn.count() > 0 and await btn.is_visible():
                     logger.warning(f"⚠️ [LoginCheck] 检测到页面存在登录按钮，判定为未登录 (Cookie 可能失效)")
                     return False
        except Exception:
            pass

        # 3.1 如果页面仍存在登录遮罩/二维码，不再单靠 Cookie 判定为已登录
        if overlay_has_login:
            if has_session:
                logger.warning("⚠️ [LoginCheck] 页面存在登录遮罩，web_session 可能失效，判定为未登录")
            else:
                logger.warning("⚠️ [LoginCheck] 页面存在登录遮罩，判定为未登录")
            return False

        # 4. OCR 辅助检测 (如果 DOM 检测失败)
        # 尝试识别页面中是否有“登录”字样的大按钮，或者是否有“我”等已登录标志
        try:
            ocr_result = await self._ocr_login_overlay()
            if ocr_result.get('enabled'):
                # 检查是否有“登录”关键字
                if ocr_result.get('has_login'):
                    logger.warning("⚠️ [LoginCheck][OCR] 视觉识别到'登录'相关文本，判定为未登录")
                    return False
                
                # 检查是否有“我”等已登录关键字 (针对侧边栏)
                texts = ocr_result.get('texts', [])
                combined_text = " ".join(texts)
                if "我" in combined_text or "消息" in combined_text or "创作中心" in combined_text:
                    logger.success("✅ [LoginCheck][OCR] 视觉识别到'我/消息/创作中心'，判定为已登录")
                    return True
        except Exception as e:
            logger.debug(f"[LoginCheck][OCR] 辅助检测异常: {e}")

        # 如果 Cookie 存在但 DOM 没刷出来，可能需要刷新，但这里我们保守一点，
        # 只要 DOM 没出来就认为没登录（或者登录失效），除非 Cookie 非常明确。
        # 考虑到 XHS 的特性，web_session 存在通常意味着已登录，但需要排除遮罩场景。
        if has_session and not overlay_has_login:
            logger.success("✅ [LoginCheck] 检测到 web_session Cookie，且未见登录遮罩，判定为已登录 (DOM 可能延迟)")
            return True

        logger.warning("⚠️ [LoginCheck] 未检测到登录状态")
        return False
    
    async def auto_login_flow(self) -> bool:
        """
        自动登录流程：检测过期 -> 打开登录页 -> 等待手动登录 -> 保存 Session
        
        Returns:
            True: 登录成功, False: 登录失败/超时
        """
        if not self.use_persistent_session or not self.platform:
            logger.info("Session 持久化未启用，跳过登录流程")
            return True
        
        # 检查 Session 是否过期
        if not self.is_session_expired():
            # Session 未过期，检查登录状态
            is_logged_in = await self.check_login_status()
            if is_logged_in:
                return True
        
        # Session 过期或未登录，需要手动登录
        logger.warning("🔐 Session 已过期或未登录，需要手动登录")
        
        login_url = SessionConfig.PLATFORM_LOGIN_URLS.get(self.platform)
        if not login_url:
            logger.error(f"平台 {self.platform} 未配置登录 URL")
            return False
        
        # 打开登录页
        logger.info(f"正在打开登录页: {login_url}")
        await self.goto(login_url)
        
        # 弹出提示
        logger.warning("=" * 60)
        logger.warning("⚠️  请在浏览器窗口中手动完成登录")
        logger.warning(f"⏱️  等待时间: {SessionConfig.LOGIN_TIMEOUT} 秒")
        logger.warning("=" * 60)
        
        # 等待登录成功（检测登录成功元素）
        selector = SessionConfig.LOGIN_SUCCESS_SELECTORS.get(self.platform)
        if not selector:
            # 如果没有配置选择器，等待固定时间
            logger.info(f"等待 {SessionConfig.LOGIN_TIMEOUT} 秒...")
            await asyncio.sleep(SessionConfig.LOGIN_TIMEOUT)
            login_success = True
        else:
            # 等待登录成功元素出现
            login_success = await self.wait_for_selector(
                selector, 
                timeout=SessionConfig.LOGIN_TIMEOUT * 1000
            )
        
        if login_success:
            logger.success("🎉 登录成功！")
            
            # 保存 Session
            await self.save_session()
            
            logger.success("✅ 自动登录流程完成")
            return True
        else:
            logger.error("❌ 登录超时或失败")
            return False
    
    # 自愈式提取已优化为三层降级体系（API → HTML → Mock），不再需要适配层包装
    
    async def setup_network_interceptor(self, api_patterns: Dict[str, Dict]) -> None:
        """
        设置网络拦截器 - Network Sniffing (API 嗅探)
        
        直接监听网页背后的 JSON 数据包，获取比 HTML 更纯净的数据
        
        Args:
            api_patterns: API 模式配置字典
                {
                    'search': {
                        'pattern': r'/api/search',
                        'method': 'GET',
                        'data_path': 'data.items'
                    }
                }
        """
        self.intercepted_apis = {}  # 存储拦截到的 API 数据
        
        async def handle_response(response):
            """处理响应"""
            try:
                url = response.url

                # 先过滤：仅对疑似 API/JSON 响应做后续处理，减少开销
                try:
                    ctype = (response.headers.get('content-type') or '').lower()
                except Exception:
                    ctype = ''
                if ('application/json' not in ctype) and ('/api/' not in url):
                    return
                
                # 检查是否匹配任何 API 模式
                for api_name, config in api_patterns.items():
                    import re
                    if re.search(config['pattern'], url):
                        # 请求方法过滤：method 为空则不过滤，非空则需匹配
                        required_method = config.get('method')
                        if required_method and response.request.method != required_method:
                            continue

                        logger.debug(f"🎯 拦截到 API: {api_name} - {url[:80]}...")
                        
                        try:
                            # 获取 JSON 数据：优先 response.json，失败则回退到 text + json.loads
                            try:
                                json_data = await response.json()
                            except Exception:
                                text = await response.text()
                                json_data = json.loads(text)
                            
                            # 存储数据
                            if api_name not in self.intercepted_apis:
                                self.intercepted_apis[api_name] = []
                            
                            self.intercepted_apis[api_name].append({
                                'url': url,
                                'method': response.request.method,
                                'status': response.status,
                                'data': json_data,
                                'timestamp': datetime.now().isoformat()
                            })

                            # Debug: 仅落盘首条 search payload，便于校准 data_path/风控判断
                            if self.debug_mode and api_name == 'search' and api_name not in self._api_debug_dumped:
                                try:
                                    os.makedirs('logs', exist_ok=True)
                                    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
                                    dump_path = os.path.join('logs', f'debug_api_{api_name}_{ts}.json')
                                    with open(dump_path, 'w', encoding='utf-8') as f:
                                        json.dump({
                                            'api_name': api_name,
                                            'url': url,
                                            'method': response.request.method,
                                            'status': response.status,
                                            'payload': json_data,
                                        }, f, ensure_ascii=False, indent=2)
                                    self._api_debug_dumped.add(api_name)
                                    logger.warning(f"⚠️ [Debug] 已保存首条 API payload: {dump_path}")
                                except Exception:
                                    pass
                            
                            logger.success(f"✅ API 数据已捕获: {api_name}")
                            
                        except Exception as e:
                            logger.debug(f"⚠️ 解析 JSON 失败: {e}")
                
            except Exception as e:
                pass  # 忽略非目标请求的错误
        
        # 注册响应监听器
        self.page.on("response", handle_response)
        logger.info(f"🎧 网络拦截器已启动，监听 {len(api_patterns)} 个 API 模式")
    
    def get_api_responses(self, api_name: str = None) -> List[Dict]:
        """
        获取拦截到的 API 数据
        
        Args:
            api_name: API 名称，不传则返回所有
            
        Returns:
            API 响应数据列表
        """
        if not hasattr(self, 'intercepted_apis'):
            logger.warning("⚠️ 网络拦截器未启动，请先调用 setup_network_interceptor()")
            return []
        
        if api_name:
            data = self.intercepted_apis.get(api_name, [])
            logger.info(f"📦 获取 API 数据: {api_name} - 共 {len(data)} 条")
            return data
        else:
            total = sum(len(v) for v in self.intercepted_apis.values())
            logger.info(f"📦 获取所有 API 数据 - 共 {total} 条")
            return self.intercepted_apis
    
    def extract_from_api(
        self, 
        api_data: Dict, 
        data_path: str,
        mapping: Dict[str, List[str]]
    ) -> List[Dict]:
        """
        从 API 数据中提取并映射字段
        
        Args:
            api_data: API 响应数据
            data_path: 数据路径（如 'data.items'）
            mapping: 字段映射配置
                {
                    'id': ['note_id', 'id'],
                    'title': ['title', 'desc']
                }
                
        Returns:
            映射后的数据列表
        """
        try:
            # 按路径获取数据
            data = api_data
            for key in data_path.split('.'):
                data = data.get(key, {})
            
            if not isinstance(data, list):
                data = [data]
            
            # 映射字段
            results = []
            for item in data:
                mapped_item = {}
                for target_field, source_fields in mapping.items():
                    # 尝试所有可能的源字段
                    for source_field in source_fields:
                        value = self._get_nested_value(item, source_field)
                        if value is not None:
                            mapped_item[target_field] = value
                            break
                
                if mapped_item:
                    results.append(mapped_item)
            
            logger.success(f"✅ API 数据提取成功: {len(results)} 条")
            return results
            
        except Exception as e:
            logger.error(f"❌ API 数据提取失败: {e}")
            return []
    
    def _get_nested_value(self, data: Dict, path: str) -> Any:
        """获取嵌套字典的值"""
        try:
            keys = path.split('.')
            value = data
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError, IndexError):
            return None


# 使用示例
async def demo():
    """演示基础爬虫的使用"""
    async with BaseSpider() as spider:
        # 访问页面
        await spider.goto("https://www.baidu.com")
        
        # 模拟人类行为
        await spider.human_type('input#kw', '测试关键词')
        await spider.human_click('input#su')
        
        # 等待结果
        await spider.wait_for_selector('.result')
        
        # 滚动页面
        await spider.human_scroll()
        
        # 截图
        await spider.screenshot()


if __name__ == "__main__":
    asyncio.run(demo())
