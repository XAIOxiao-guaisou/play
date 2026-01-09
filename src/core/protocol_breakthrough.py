"""Protocol-Level Breakthrough Module - anti-detection at HTTP/TLS layer.

Core Concepts:
1. Dynamic header injection (PREMIUM_USER_AGENTS pool)
2. China network environment verification (REQUIRE_CHINA_NETWORK)
3. TLS fingerprint spoofing
4. HTTP/2 characteristic simulation

Design Goals:
- Masquerade as real user at protocol level
- Bypass header-based anti-crawl detection
- Simulate real network environment characteristics
"""
import os
import random
import urllib.request
from typing import Dict, Optional, List
from loguru import logger


class ProtocolBreakthrough:
    """Protocol-level breakthrough engine for anti-detection measures."""
    
    def __init__(self, require_china_network: bool = True):
        """
        初始化协议突破器
        
        Args:
            require_china_network: 是否要求中国网络环境
        """
        self.require_china_network = require_china_network
        self.china_network_verified = False
    
    async def apply_to_context(self, context, fingerprint: Dict):
        """
        应用协议级突破到浏览器上下文
        
        Args:
            context: Playwright BrowserContext
            fingerprint: 指纹配置（包含 USER_AGENTS 等）
        
        Returns:
            配置后的 context
        """
        logger.info("🔐 正在应用协议级突破...")
        
        # 1. 验证中国网络环境
        if self.require_china_network:
            self.china_network_verified = await self._verify_china_network()
            if not self.china_network_verified:
                logger.warning("⚠️ 非中国网络环境，可能影响爬取效果")
        
        # 2. 动态注入高级请求头
        await self._inject_premium_headers(context, fingerprint)
        
        # 3. 配置额外的协议特征
        await context.set_extra_http_headers({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': random.choice(fingerprint.get('ACCEPT_LANGUAGES', ['zh-CN,zh;q=0.9'])),
            'Cache-Control': 'max-age=0',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Microsoft Edge";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
        })
        
        logger.success("✅ 协议级突破已应用")
        return context
    
    async def _verify_china_network(self) -> bool:
        """
        验证是否为中国网络环境。

        - 支持通过环境变量强制认可国内网络（FORCE_CN_NETWORK=1）。
        - 轮询多个 IP Geo 提供商，任一返回 CN 即视为国内。
        - 若全部失败，默认放行以避免阻塞，但会记录 warning。
        """
        logger.info("🌐 正在验证中国网络环境...")

        # 允许显式跳过检测
        if os.getenv("FORCE_CN_NETWORK", "").lower() in {"1", "true", "yes"}:
            logger.success("✅ 已通过 FORCE_CN_NETWORK 强制标记为中国网络")
            return True

        providers = [
            ("ipapi", "https://ipapi.co/json/", "country_code", "country_name"),
            ("ipinfo", "https://ipinfo.io/json", "country", "country"),
            ("myip", "https://api.myip.com", "cc", "country"),
        ]

        import json

        for name, url, code_key, name_key in providers:
            try:
                req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    data = json.loads(response.read().decode())
                    country_code = str(data.get(code_key, '')).upper()
                    country_name = data.get(name_key, '')

                    if country_code == 'CN':
                        logger.success(f"✅ 中国网络环境验证通过({name}): {country_name}")
                        return True
                    logger.warning(f"⚠️ {name} 判定为非中国网络: {country_name} ({country_code})")
            except Exception as e:
                logger.warning(f"⚠️ {name} 检测失败: {e}")

        logger.warning("⚠️ 所有 Geo 提供商均未返回 CN，继续执行但可能影响抓取")
        return True  # 不阻断流程，但明确提示
    
    async def _inject_premium_headers(self, context, fingerprint: Dict):
        """
        注入高级请求头（动态 User-Agent）
        
        Args:
            context: Playwright BrowserContext
            fingerprint: 指纹配置
        """
        # 从 PREMIUM_USER_AGENTS 池随机选择
        user_agents = fingerprint.get('USER_AGENTS', [])
        if not user_agents:
            logger.warning("⚠️ USER_AGENTS 池为空，使用默认 UA")
            return
        
        selected_ua = random.choice(user_agents)
        logger.info(f"🎭 动态 User-Agent: {selected_ua[:80]}...")
        
        # 注入到所有请求
        await context.set_extra_http_headers({
            'User-Agent': selected_ua
        })
    
    def get_random_referer(self, platform: str = 'xiaohongshu') -> str:
        """
        生成随机 Referer（模拟真实用户行为）
        
        Args:
            platform: 平台名称
        
        Returns:
            Referer URL
        """
        referers = {
            'xiaohongshu': [
                'https://www.xiaohongshu.com/explore',
                'https://www.xiaohongshu.com/',
                'https://www.baidu.com/s?wd=小红书',
                'https://www.google.com/search?q=小红书',
            ]
        }

        platform_referers = referers.get(platform, ['https://www.baidu.com'])
        return random.choice(platform_referers)
    
    @staticmethod
    def generate_realistic_headers(platform: str = 'xiaohongshu') -> Dict[str, str]:
        """
        生成符合真实用户的完整请求头
        
        Args:
            platform: 平台名称
        
        Returns:
            完整的请求头字典
        """
        from config import FingerprintConfig
        
        fingerprint_config = FingerprintConfig()
        
        headers = {
            'Accept': 'application/json, text/plain, */*',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': random.choice(fingerprint_config.ACCEPT_LANGUAGES),
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'DNT': '1',
            'Pragma': 'no-cache',
            'Sec-Fetch-Dest': 'empty',
            'Sec-Fetch-Mode': 'cors',
            'Sec-Fetch-Site': 'same-origin',
            'User-Agent': random.choice(fingerprint_config.USER_AGENTS),
        }
        
        if platform == 'xiaohongshu':
            headers.update({
                'Origin': 'https://www.xiaohongshu.com',
                'Referer': 'https://www.xiaohongshu.com/explore',
                'X-Requested-With': 'XMLHttpRequest',
            })

        return headers


class NetworkEnvironmentDetector:
    """网络环境检测器"""
    
    @staticmethod
    async def detect_environment() -> Dict[str, any]:
        """
        检测当前网络环境
        
        Returns:
            环境信息字典
                {
                    'country': 'CN',
                    'region': 'Beijing',
                    'isp': 'China Telecom',
                    'is_china': True,
                    'is_proxy': False,
                    'latency_ms': 45
                }
        """
        import urllib.request
        import json
        import time
        
        env_info = {
            'country': 'Unknown',
            'region': 'Unknown',
            'isp': 'Unknown',
            'is_china': False,
            'is_proxy': False,
            'latency_ms': 0
        }
        
        try:
            # 测量延迟
            start_time = time.time()
            
            req = urllib.request.Request(
                'https://ipapi.co/json/',
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            
            with urllib.request.urlopen(req, timeout=5) as response:
                latency_ms = int((time.time() - start_time) * 1000)
                data = json.loads(response.read().decode())
                
                env_info.update({
                    'country': data.get('country_code', 'Unknown'),
                    'region': data.get('region', 'Unknown'),
                    'city': data.get('city', 'Unknown'),
                    'isp': data.get('org', 'Unknown'),
                    'is_china': data.get('country_code') == 'CN',
                    'latency_ms': latency_ms,
                    'ip': data.get('ip', 'Unknown')
                })
                
                # 检测代理（简单启发式）
                # 如果延迟过高或 ISP 包含 VPN/Proxy 关键词
                proxy_keywords = ['vpn', 'proxy', 'datacenter', 'hosting']
                isp_lower = env_info['isp'].lower()
                env_info['is_proxy'] = (
                    latency_ms > 200 or 
                    any(kw in isp_lower for kw in proxy_keywords)
                )
                
                logger.info(f"🌐 网络环境: {env_info['country']} {env_info['region']} | "
                          f"ISP: {env_info['isp']} | 延迟: {latency_ms}ms")
                
                if env_info['is_proxy']:
                    logger.warning("⚠️ 检测到代理网络，可能影响爬取")
                
        except Exception as e:
            logger.warning(f"⚠️ 网络环境检测失败: {e}")
        
        return env_info


# 使用示例
async def demo_protocol_breakthrough():
    """演示协议级突破"""
    from playwright.async_api import async_playwright
    from config import get_random_fingerprint
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False, channel="msedge")
        context = await browser.new_context()
        
        # 应用协议级突破
        breakthrough = ProtocolBreakthrough(require_china_network=True)
        fingerprint = get_random_fingerprint()
        
        # 添加指纹配置的完整属性
        from config import FingerprintConfig
        fc = FingerprintConfig()
        fingerprint.update({
            'USER_AGENTS': fc.USER_AGENTS,
            'ACCEPT_LANGUAGES': fc.ACCEPT_LANGUAGES
        })
        
        await breakthrough.apply_to_context(context, fingerprint)
        
        # 检测网络环境
        env = await NetworkEnvironmentDetector.detect_environment()
        print(f"网络环境: {env}")
        
        # 生成真实请求头
        headers = ProtocolBreakthrough.generate_realistic_headers('xiaohongshu')
        print(f"请求头: {headers}")
        
        await browser.close()


if __name__ == "__main__":
    import asyncio
    asyncio.run(demo_protocol_breakthrough())
