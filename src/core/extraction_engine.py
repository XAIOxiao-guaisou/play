"""Three-Tier Extraction System - hierarchical data extraction with fallback mechanism.

Core Architecture:
1. Layer 1 (Priority): Network Sniffing - intercepts raw API JSON responses
2. Layer 2 (Self-healing): Heuristic XPath - visual feature-based element location
3. Layer 3 (Fallback): Intelligent Mock - generates data matching trends

Design Principles:
- Never fail: Each layer has the next as fallback mechanism
- Data integrity: Source marks indicate extraction method (api/html/mock)
- Traceability: Tracks fallback path for optimization insights
"""
import json
import random
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from loguru import logger


class ExtractionEngine:
    """三层降级抓取引擎"""
    
    def __init__(self):
        self.extraction_stats = {
            'api': 0,
            'html': 0,
            'mock': 0
        }
    
    async def extract_with_fallback(
        self,
        api_extractor: Optional[callable] = None,
        html_extractor: Optional[callable] = None,
        mock_generator: Optional[callable] = None,
        context: Dict[str, Any] = None
    ) -> List[Dict[str, Any]]:
        """
        三层降级抓取主入口
        
        Args:
            api_extractor: API 嗅探提取函数
            html_extractor: HTML 启发式提取函数
            mock_generator: Mock 数据生成函数
            context: 上下文信息（关键词、页数等）
        
        Returns:
            提取的数据列表（带来源标记）
        """
        context = context or {}
        
        # 第一层：Network Sniffing（优先）
        if api_extractor:
            logger.info("🎧 [Layer 1] 尝试 Network Sniffing...")
            try:
                api_data = await api_extractor()
                if api_data and len(api_data) > 0:
                    self.extraction_stats['api'] += len(api_data)
                    logger.success(f"✅ [Layer 1] Network Sniffing 成功！获取 {len(api_data)} 条纯净数据")
                    return self._mark_source(api_data, 'api')
            except Exception as e:
                logger.warning(f"⚠️ [Layer 1] Network Sniffing 失败: {e}")
        
        # 第二层：启发式 XPath（自愈）
        if html_extractor:
            logger.info("🔍 [Layer 2] 启动启发式 XPath 提取...")
            try:
                html_data = await html_extractor()
                if html_data and len(html_data) > 0:
                    self.extraction_stats['html'] += len(html_data)
                    logger.success(f"✅ [Layer 2] 启发式提取成功！获取 {len(html_data)} 条数据")
                    return self._mark_source(html_data, 'html')
            except Exception as e:
                logger.warning(f"⚠️ [Layer 2] 启发式提取失败: {e}")
        
        # 第三层：智能 Mock（保底）
        if mock_generator:
            logger.warning("🎭 [Layer 3] 启动智能 Mock 保底机制...")
            try:
                mock_data = await mock_generator(context)
                if mock_data:
                    self.extraction_stats['mock'] += len(mock_data)
                    logger.info(f"🎭 [Layer 3] Mock 数据生成成功！生成 {len(mock_data)} 条模拟数据")
                    return self._mark_source(mock_data, 'mock')
            except Exception as e:
                logger.error(f"❌ [Layer 3] Mock 生成失败: {e}")
        
        logger.error("❌ 三层降级全部失败！返回空数据")
        return []
    
    def _mark_source(self, data: List[Dict], source: str) -> List[Dict]:
        """标记数据来源"""
        for item in data:
            item['_extraction_source'] = source
            item['_extraction_time'] = datetime.now().isoformat()
        return data
    
    def get_stats(self) -> Dict[str, int]:
        """获取提取统计"""
        total = sum(self.extraction_stats.values())
        if total == 0:
            return self.extraction_stats
        
        stats_with_percent = {
            'api': {'count': self.extraction_stats['api'], 
                   'percent': f"{self.extraction_stats['api']/total*100:.1f}%"},
            'html': {'count': self.extraction_stats['html'], 
                    'percent': f"{self.extraction_stats['html']/total*100:.1f}%"},
            'mock': {'count': self.extraction_stats['mock'], 
                    'percent': f"{self.extraction_stats['mock']/total*100:.1f}%"},
            'total': total
        }
        return stats_with_percent


class HeuristicExtractor:
    """启发式提取器（基于视觉特征）"""
    
    @staticmethod
    async def extract_by_visual_features(page, platform: str = 'xiaohongshu') -> List[Dict]:
        """
        基于视觉特征提取数据（第二层）
        
        核心思想：
        - 不依赖 CSS 类名（易变）
        - 使用视觉特征：图标、布局、文本模式
        - XPath + 语义化定位
        
        Args:
            page: Playwright Page 对象
            platform: 平台名称
        
        Returns:
            提取的数据列表
        """
        if platform == 'xiaohongshu':
            return await HeuristicExtractor._extract_xiaohongshu_by_visual(page)
        else:
            logger.warning(f"未支持的平台: {platform}")
            return []
    
    @staticmethod
    async def _extract_xiaohongshu_by_visual(page) -> List[Dict]:
        """
        小红书视觉特征提取（启发式）
        
        特征识别：
        1. 笔记卡片：包含图片 + 标题 + 作者
        2. 点赞图标：❤️ 或 like-icon
        3. 互动容器：固定布局位置
        """
        notes = []
        
        # 策略1: 通过图片容器查找笔记卡片
        visual_xpath = """
        //section[.//img and .//a[@title]]
        | //div[contains(@class, 'note') or contains(@class, 'card')][.//img]
        | //article[.//img and .//h3]
        """
        
        try:
            cards = await page.locator(visual_xpath).all()
            logger.info(f"🔍 视觉特征定位到 {len(cards)} 个笔记容器")
            
            for idx, card in enumerate(cards):
                try:
                    # 提取标题（优先级：h3 > h2 > a[@title] > strong）
                    title = ""
                    for title_xpath in ['.//h3', './/h2', './/a[@title]', './/strong']:
                        try:
                            title_elem = card.locator(title_xpath).first
                            title_text = await title_elem.text_content()
                            if title_text and len(title_text) > 3:
                                title = title_text.strip()
                                break
                        except:
                            continue
                    
                    # 提取图片链接
                    image_url = ""
                    try:
                        img = card.locator('img').first
                        image_url = await img.get_attribute('src')
                    except:
                        pass
                    
                    # 提取点赞数（查找❤️图标附近的数字）
                    likes = 0
                    try:
                        # 策略：查找包含数字且靠近 like/heart 图标的元素
                        like_xpath = './/*[contains(@class, "like") or contains(@class, "heart")]/..//*[contains(text(), "")]'
                        like_text = await card.locator(like_xpath).first.text_content()
                        likes = HeuristicExtractor._parse_interaction_count(like_text)
                    except:
                        pass
                    
                    if title:  # 至少有标题才认为是有效数据
                        notes.append({
                            'title': title,
                            'image_url': image_url,
                            'likes': likes,
                            'author': '',  # 待提取
                            'platform': 'xiaohongshu'
                        })
                        
                except Exception as e:
                    logger.debug(f"提取笔记 {idx} 失败: {e}")
                    continue
            
            return notes
            
        except Exception as e:
            logger.error(f"视觉特征提取失败: {e}")
            return []
    
    @staticmethod
    def _parse_interaction_count(text: str) -> int:
        """解析互动数（支持 1.2w、5k 等格式）"""
        if not text:
            return 0
        
        import re
        # 移除非数字字符，保留 w/k/万/千
        text = text.lower().strip()
        
        # 匹配模式：123、1.2w、5k
        match = re.search(r'([\d.]+)([wk万千]?)', text)
        if not match:
            return 0
        
        num_str, unit = match.groups()
        try:
            num = float(num_str)
            if unit in ['w', '万']:
                return int(num * 10000)
            elif unit in ['k', '千']:
                return int(num * 1000)
            else:
                return int(num)
        except:
            return 0


class SmartMockGenerator:
    """智能 Mock 数据生成器（第三层保底）"""
    
    @staticmethod
    async def generate_trending_data(context: Dict[str, Any]) -> List[Dict]:
        """
        生成符合趋势的模拟数据
        
        Args:
            context: 上下文信息
                - keyword: 搜索关键词
                - count: 生成数量
                - platform: 平台名称
        
        Returns:
            模拟数据列表
        """
        keyword = context.get('keyword', '默认话题')
        count = context.get('count', 10)
        platform = context.get('platform', 'xiaohongshu')
        
        logger.info(f"🎭 生成 Mock 数据: {keyword} x {count} 条")
        
        mock_data = []
        
        # 标题模板（符合小红书风格）
        title_templates = [
            f"{keyword}｜这个方法真的有用！",
            f"分享一个{keyword}的小技巧",
            f"{keyword}避坑指南📝",
            f"关于{keyword}，我想说...",
            f"{keyword}入门必看！",
            f"真实测评｜{keyword}",
            f"{keyword}宝藏分享✨",
            f"超详细{keyword}教程",
        ]
        
        for i in range(count):
            # 随机选择标题模板
            title = random.choice(title_templates)
            
            # 模拟互动数据（符合真实分布）
            likes = random.randint(50, 5000)
            collects = int(likes * random.uniform(0.3, 0.8))
            comments = int(likes * random.uniform(0.05, 0.2))
            
            # 模拟发布时间（最近7天）
            days_ago = random.randint(0, 7)
            publish_time = (datetime.now() - timedelta(days=days_ago)).isoformat()
            
            mock_note = {
                'id': f'mock_{int(datetime.now().timestamp())}_{i}',
                'title': title,
                'author': f'用户{random.randint(1000, 9999)}',
                'likes': likes,
                'collects': collects,
                'comments': comments,
                'publish_time': publish_time,
                'platform': platform,
                '_is_mock': True,  # 标记为 Mock 数据
                '_mock_reason': 'API和HTML提取均失败，启用保底机制'
            }
            
            mock_data.append(mock_note)
        
        return mock_data


# 使用示例
async def demo_extraction():
    """演示三层降级抓取"""
    engine = ExtractionEngine()
    
    async def mock_api_extractor():
        """模拟 API 提取"""
        # 假设 API 被拦截，返回空
        return []
    
    async def mock_html_extractor():
        """模拟 HTML 提取"""
        # 假设 HTML 结构变化，返回空
        return []
    
    async def mock_generator(context):
        """Mock 生成器"""
        return await SmartMockGenerator.generate_trending_data(context)
    
    # 执行三层降级抓取
    results = await engine.extract_with_fallback(
        api_extractor=mock_api_extractor,
        html_extractor=mock_html_extractor,
        mock_generator=mock_generator,
        context={'keyword': '小红书爬虫', 'count': 5, 'platform': 'xiaohongshu'}
    )
    
    print(f"提取结果: {len(results)} 条")
    print(f"统计信息: {engine.get_stats()}")
    return results


if __name__ == "__main__":
    import asyncio
    asyncio.run(demo_extraction())
