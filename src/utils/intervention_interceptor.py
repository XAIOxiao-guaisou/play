"""
人工干预拦截器 (Manual Intervention Interceptor)

职责：
1. 智能探测验证码/滑块等人机验证
2. 声光报警（音效 + 弹窗）
3. 暂停自动操作，等待人工处理
4. 检测验证码消失后自动恢复
5. 超时处理和失败记录
"""

import asyncio
import time
from typing import Optional, Callable, List
from datetime import datetime
from enum import Enum
from loguru import logger
from playwright.async_api import Page


class InterventionType(Enum):
    """干预类型"""
    CAPTCHA = "验证码"
    SLIDER = "滑块验证"
    CLICK_VERIFY = "点击验证"
    ROTATE_VERIFY = "旋转验证"
    SMS_CODE = "短信验证码"
    LOGIN_REQUIRED = "需要登录"
    UNKNOWN = "未知验证"


class CaptchaDetector:
    """验证码检测器"""
    
    # 验证码特征关键词
    CAPTCHA_KEYWORDS = [
        '验证码', 'captcha', 'verify', 'verification',
        '滑动', 'slide', '拖动', 'drag',
        '点击', 'click', '选择', 'select',
        '旋转', 'rotate', '拼图', 'puzzle',
        '人机验证', 'robot', 'security check',
        '安全验证', 'safety verification'
    ]
    
    # 验证码元素选择器
    CAPTCHA_SELECTORS = [
        # 通用验证码容器
        '.captcha', '#captcha', '[class*="captcha"]',
        '.verify', '#verify', '[class*="verify"]',
        
        # 滑块验证
        '.slider', '.slide-verify', '[class*="slider"]',
        '.nc-container', '.sm-pop',  # 阿里云滑块
        
        # 腾讯验证码
        '#tcaptcha_iframe', '.tcaptcha',
        
        # 极验验证码
        '.geetest_radar_tip', '.geetest_slider',
        
        # 其他常见验证码
        '.yidun', '.yidun_popup',  # 网易云盾
        'iframe[src*="captcha"]',
        'iframe[src*="verify"]'
    ]
    
    @staticmethod
    async def detect(page: Page) -> tuple[bool, Optional[InterventionType], str]:
        """
        检测页面是否存在验证码或需要登录
        
        Returns:
            (是否存在, 验证类型, 描述信息)
        """
        try:
            # 0. 检查是否需要登录 (新增)
            # 检查 URL 是否包含 login
            if "login" in page.url:
                 return True, InterventionType.LOGIN_REQUIRED, "检测到登录页面 URL"
            
            # 检查常见的登录容器
            login_selectors = [
                '.login-container', '.login-box', '.login-wrapper',
                '#login-container', '#login-box',
                '.login-modal', '.login-dialog'
            ]
            for selector in login_selectors:
                if await page.query_selector(selector):
                     return True, InterventionType.LOGIN_REQUIRED, f"检测到登录弹窗 ({selector})"

            # 1. 检查页面内容关键词
            # 注意：这种方式误报率较高，因为搜索结果可能包含这些词
            # 改进：只在特定容器中查找，或者要求关键词出现频率较高，或者页面结构简单
            
            # 暂时禁用全文关键词检测，因为它太容易误报了（例如搜索"验证码"相关内容时）
            # content = await page.content()
            # content_lower = content.lower()
            
            # for keyword in CaptchaDetector.CAPTCHA_KEYWORDS:
            #     if keyword.lower() in content_lower:
            #         ...
            
            # 替代方案：只检查 Title 或特定 Meta 标签
            title = await page.title()
            if any(k in title.lower() for k in ['验证码', 'captcha', 'security check']):
                 return True, InterventionType.CAPTCHA, f"检测到验证码标题: {title}"

            # 2. 检查验证码元素
            for selector in CaptchaDetector.CAPTCHA_SELECTORS:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        # 检查元素是否可见
                        is_visible = await element.is_visible()
                        if is_visible:
                            logger.debug(f"🔍 检测到验证码元素: {selector}")
                            return True, InterventionType.CAPTCHA, f"检测到验证码元素（选择器: {selector}）"
                except Exception:
                    continue
            
            # 3. 检查 iframe（验证码常在 iframe 中）
            frames = page.frames
            for frame in frames:
                try:
                    frame_url = frame.url
                    if any(keyword in frame_url.lower() for keyword in ['captcha', 'verify', 'geetest']):
                        logger.debug(f"🔍 检测到验证码 iframe: {frame_url}")
                        return True, InterventionType.CAPTCHA, f"检测到验证码 iframe"
                except Exception:
                    continue
            
            return False, None, ""
        
        except Exception as e:
            logger.error(f"验证码检测失败: {e}")
            return False, None, ""


class AlertManager:
    """报警管理器"""

    _toast_disabled: bool = False
    
    @staticmethod
    def play_sound(times: int = 3):
        """播放提示音"""
        try:
            import winsound
            for _ in range(times):
                winsound.Beep(1000, 500)  # 频率1000Hz，持续500ms
                time.sleep(0.2)
            logger.debug("🔔 已播放提示音")
        except Exception as e:
            logger.warning(f"播放提示音失败: {e}")
    
    @staticmethod
    def show_notification(title: str, message: str):
        """显示桌面通知（Windows Toast）"""
        if AlertManager._toast_disabled:
            return

        try:
            from win10toast import ToastNotifier
            toaster = ToastNotifier()
            toaster.show_toast(
                title,
                message,
                duration=10,
                # 这里不要再用 threaded=True：外层 alert() 已经用线程调用本方法，
                # threaded=True 在部分环境会产生 WNDPROC TypeError 噪音。
                threaded=False
            )
            logger.debug(f"📢 已显示桌面通知: {title}")
        except Exception as e:
            # 失败后禁用 toast，避免反复报错影响日志与稳定性
            AlertManager._toast_disabled = True
            logger.warning(f"显示桌面通知失败: {e}")
    
    @staticmethod
    def show_dialog(title: str, message: str) -> bool:
        """显示对话框（阻塞式）"""
        try:
            import tkinter as tk
            from tkinter import messagebox
            
            root = tk.Tk()
            root.withdraw()  # 隐藏主窗口
            root.attributes('-topmost', True)  # 置顶
            
            result = messagebox.askokcancel(title, message)
            root.destroy()
            
            logger.debug(f"💬 已显示对话框: {title}")
            return result
        except Exception as e:
            logger.warning(f"显示对话框失败: {e}")
            return False
    
    @staticmethod
    async def alert(
        intervention_type: InterventionType,
        description: str,
        use_sound: bool = True,
        use_toast: bool = True,
        use_dialog: bool = False
    ):
        """
        综合报警
        
        Args:
            intervention_type: 干预类型
            description: 描述信息
            use_sound: 是否播放声音
            use_toast: 是否显示Toast通知
            use_dialog: 是否显示对话框（阻塞）
        """
        title = f"⚠️ 需要人工处理: {intervention_type.value}"
        message = f"{description}\n\n请手动完成验证后，点击确定继续..."
        
        logger.warning("=" * 60)
        logger.warning(title)
        logger.warning(message)
        logger.warning("=" * 60)
        
        # 播放声音（非阻塞）
        if use_sound:
            import threading
            threading.Thread(target=AlertManager.play_sound, args=(3,), daemon=True).start()
        
        # 显示Toast通知（非阻塞）
        if use_toast:
            import threading
            threading.Thread(
                target=AlertManager.show_notification,
                args=(title, message),
                daemon=True
            ).start()
        
        # 显示对话框（阻塞）
        if use_dialog:
            return AlertManager.show_dialog(title, message)
        
        return True


class InterventionInterceptor:
    """人工干预拦截器"""
    
    def __init__(
        self,
        check_interval: float = 2.0,      # 检测间隔（秒）
        timeout: int = 300,                # 超时时间（秒）
        auto_check: bool = True,           # 是否自动检测
        use_sound: bool = True,            # 是否使用声音报警
        use_toast: bool = True,            # 是否使用Toast通知
        use_dialog: bool = False,          # 是否使用对话框（阻塞）
        on_intervention: Optional[Callable] = None  # 干预回调
    ):
        """
        初始化拦截器
        
        Args:
            check_interval: 检测间隔
            timeout: 超时时间
            auto_check: 是否自动检测
            use_sound: 是否使用声音报警
            use_toast: 是否使用Toast通知
            use_dialog: 是否使用对话框
            on_intervention: 干预回调函数
        """
        self.check_interval = check_interval
        self.timeout = timeout
        self.auto_check = auto_check
        self.use_sound = use_sound
        self.use_toast = use_toast
        self.use_dialog = use_dialog
        self.on_intervention = on_intervention
        
        # 状态
        self.is_waiting = False
        self.wait_start_time = None
        self.intervention_count = 0
        
        logger.info(
            f"🛡️ 人工干预拦截器已启动 "
            f"(检测间隔={check_interval}s, 超时={timeout}s, "
            f"声音={use_sound}, 通知={use_toast})"
        )
    
    async def check_and_wait(self, page: Page, message: str = None) -> bool:
        """
        检查验证码并等待人工处理
        
        Args:
            page: 页面对象
            message: 自定义提示消息
            
        Returns:
            是否成功通过验证
        """
        # 检测验证码
        has_captcha, intervention_type, description = await CaptchaDetector.detect(page)
        
        # 如果传入了自定义消息，强制进入等待状态（用于登录等场景）
        if message:
            has_captcha = True
            intervention_type = InterventionType.LOGIN_REQUIRED
            description = message
        
        if not has_captcha:
            return True  # 无验证码，继续
        
        # 发现验证码，触发干预
        logger.warning(f"🚨 触发人工干预: {intervention_type.value} - {description}")
        self.intervention_count += 1
        
        # 触发回调
        if self.on_intervention:
            try:
                self.on_intervention(intervention_type, description)
            except Exception as e:
                logger.error(f"干预回调执行失败: {e}")
        
        # 报警
        await AlertManager.alert(
            intervention_type,
            description,
            use_sound=self.use_sound,
            use_toast=self.use_toast,
            use_dialog=self.use_dialog
        )
        
        # 等待人工处理
        return await self._wait_for_manual_completion(page, message)
    
    async def _wait_for_manual_completion(self, page: Page, custom_message: str = None) -> bool:
        """
        等待人工完成验证
        
        Args:
            page: 页面对象
            custom_message: 自定义消息（如果存在，则不依赖验证码检测，而是等待用户确认或特定条件）
            
        Returns:
            是否在超时前完成
        """
        self.is_waiting = True
        self.wait_start_time = time.time()
        
        logger.info("⏸️  已暂停自动操作，等待人工处理...")
        msg = custom_message or "请在浏览器中完成验证，系统将自动检测并继续"
        logger.info(f"💡 {msg}（超时: {self.timeout}秒）")
        logger.warning("⚠️ 注意：请勿关闭浏览器窗口！验证完成后请保持窗口开启。")
        
        check_count = 0
        
        while True:
            # 检查超时
            elapsed = time.time() - self.wait_start_time
            if elapsed > self.timeout:
                self.is_waiting = False
                logger.error(f"❌ 等待超时（{self.timeout}秒），人工干预失败")
                return False
            
            # 检查浏览器是否存活
            try:
                if page.is_closed():
                    self.is_waiting = False
                    logger.error("❌ 浏览器已关闭，人工干预终止")
                    return False
            except Exception:
                self.is_waiting = False
                logger.error("❌ 浏览器连接丢失，人工干预终止")
                return False

            # 等待一段时间
            await asyncio.sleep(self.check_interval)
            check_count += 1
            
            # 如果是自定义消息（如登录），我们需要一种方式来判断是否完成
            # 这里我们假设如果是登录，我们检查是否还有登录相关的元素
            # 或者简单地，如果用户手动关闭了浏览器，或者页面跳转了
            
            # 检查验证码是否消失
            try:
                has_captcha, _, _ = await CaptchaDetector.detect(page)
            except Exception as e:
                # 如果检测过程中发生错误（如页面关闭），视为失败
                logger.error(f"检测验证码状态失败: {e}")
                self.is_waiting = False
                return False
            
            # 如果是登录场景，我们需要检查是否登录成功
            # 这里简单复用 CaptchaDetector，如果它没检测到验证码，且我们处于登录等待中
            # 我们可能需要更具体的检查。
            # 但为了通用性，如果传入了 custom_message，我们假设调用者希望我们等待直到某种状态
            # 可是 _wait_for_manual_completion 不知道调用者的意图。
            # 让我们修改调用逻辑：调用者应该传递一个 check_callback
            
            # 临时修复：如果是登录，我们检查 URL 是否不再包含 login，或者页面上没有登录按钮
            # 但这在通用类里不好写。
            # 让我们依赖 CaptchaDetector，如果它没检测到"验证码"（包括我们可能添加的登录检测逻辑），就认为成功
            
            # 对于登录，我们在 CaptchaDetector 里添加 LOGIN_REQUIRED 类型检测吗？
            # 不，我们在调用 check_and_wait 时已经手动触发了。
            # 现在的逻辑是：只要 detect 返回 False，就认为通过。
            # 所以我们需要确保 detect 能检测到"未登录"状态。
            
            # 让我们修改 CaptchaDetector.detect 来支持检测登录页
            
            if not has_captcha:
                # 验证码消失，验证成功
                self.is_waiting = False
                elapsed_str = f"{elapsed:.1f}秒"
                logger.success(f"✅ 验证/登录已完成，人工处理成功！（耗时: {elapsed_str}）")
                
                # 额外等待，确保页面稳定
                await asyncio.sleep(2)
                return True
            
            # 定期提示
            if check_count % 5 == 0:
                remaining = self.timeout - elapsed
                logger.info(f"⏳ 仍在等待人工处理... (剩余 {remaining:.0f}秒)")
    
    async def auto_check_loop(self, page: Page, interval: float = 5.0):
        """
        自动检测循环（后台运行）
        
        Args:
            page: 页面对象
            interval: 检测间隔
        """
        logger.info(f"🔄 自动验证码检测已启动 (间隔={interval}s)")
        
        while True:
            try:
                if not self.is_waiting:
                    has_captcha, intervention_type, description = await CaptchaDetector.detect(page)
                    
                    if has_captcha:
                        logger.warning(f"🚨 后台检测到验证码: {intervention_type.value}")
                        await self.check_and_wait(page)
                
                await asyncio.sleep(interval)
            
            except Exception as e:
                logger.error(f"自动检测异常: {e}")
                await asyncio.sleep(interval)
    
    def get_statistics(self) -> dict:
        """获取统计信息"""
        return {
            'intervention_count': self.intervention_count,
            'is_waiting': self.is_waiting,
            'wait_time': time.time() - self.wait_start_time if self.is_waiting else 0
        }


# 导出
__all__ = [
    'InterventionType',
    'InterventionInterceptor',
    'CaptchaDetector',
    'AlertManager'
]
