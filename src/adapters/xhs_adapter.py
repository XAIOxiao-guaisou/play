"""
适配层 (Adapter Layer) - 小红书适配器

职责:
1. 小红书平台特定的 HTML 元素定位（自愈式提取）
2. 数据提取和结构化（笔记、作者、互动数据）
3. 处理小红书的反爬机制（如动态加载、懒加载）
4. API 嗅探（Network Sniffing）
5. 三层降级抓取体系（API → HTML → Mock）

核心技术规则（金科玉律）：
- 第一层（优先）：Network Sniffing 截获原始 JSON
- 第二层（自愈）：启发式 XPath 基于视觉特征
- 第三层（保底）：智能 Mock 确保流程不中断
"""

from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio
import os
import re
from urllib.parse import quote
from loguru import logger
from src.core.base_spider import BaseSpider
from src.core.extraction_engine import ExtractionEngine
from config import (
    NetworkInterceptorConfig,
)


class XiaohongshuAdapter(BaseSpider):
    """小红书适配器 - 继承基础爬虫能力 + 三层降级抓取"""
    
    def __init__(
        self,
        config_path: str = "config.yaml",
        debug_mode: bool = False,
        use_persistent_session: bool = True,
        use_api_sniffing: bool = True,
        use_context_pool: Optional[bool] = None,
    ):
        super().__init__(
            config_path,
            debug_mode,
            platform='xiaohongshu',
            use_persistent_session=use_persistent_session,
            use_context_pool=use_context_pool,
        )
        self.xhs_config = self.config.xiaohongshu
        self.base_url = self.xhs_config.base_url
        self.use_api_sniffing = use_api_sniffing
        
        
        # 初始化三层降级抓取引擎
        self.extraction_engine = ExtractionEngine()
        
        logger.success("🎭 小红书适配器已启用: 三层降级抓取 + Stealth 2.0")
    
    async def search_notes(
        self,
        keyword: str,
        max_pages: int = None,
        fetch_detail: bool = False,
        detail_limit: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        搜索小红书笔记（三层降级抓取体系）
        
        执行顺序:
        1. Network Sniffing (page.on('response')) - 优先
        2. 启发式 XPath (视觉特征) - 自愈
        3. 智能 Mock (模拟数据) - 保底
        
        Args:
            keyword: 搜索关键词
            max_pages: 最大爬取页数
            
        Returns:
            笔记列表（带 _extraction_source 标记）
        """
        max_pages = max_pages or self.xhs_config.max_pages
        
        logger.info(f"🔍 开始搜索小红书关键词: {keyword} (三层降级模式)")

        # 预热 explore 并确保已登录，避免搜索页重定向到登录导致空白
        await self.ensure_login_ready()
        
        # 先挂载网络拦截器，再访问搜索页，确保首屏请求被捕获
        if self.use_api_sniffing:
            await self.setup_network_interceptor(NetworkInterceptorConfig.XIAOHONGSHU_APIS)

        # 访问搜索页
        # 强制落在「笔记」tab（type=51），以稳定触发 /api/sns/web/v1/search/notes
        # 说明：不引入 &source=web_explore_feed（按你的要求移除），仅补足必要的 type。
        kw = quote(str(keyword), safe="")
        search_url = f"{self.base_url}/search_result?keyword={kw}&type=51"
        await self.goto(search_url)
        
        # 智能等待内容加载
        await self.wait_for_load_state('networkidle', timeout=10000)

        # 搜索页渲染自愈：若未见到卡片/锚点，尝试 reload + 轻滚动
        await self._ensure_search_page_rendered()

        # 若出现登录遮罩/弹窗，尽量关闭，避免遮挡渲染/滚动
        await self._dismiss_login_prompts()

        # 如果仍检测到登录提示，尝试先访问 explore 再回到搜索，触发会话加载
        await self._rehit_search_if_login_prompt(keyword, search_url)

        # 尽量切到「笔记」结果页签，避免落在综合/其他类型导致卡片/接口偏少
        try:
            await self._try_switch_to_notes_tab()
        except Exception:
            pass

        # 若首屏仍无卡片，直接在搜索框重新提交关键词以触发请求
        try:
            await self._nudge_search_if_empty(keyword)
        except Exception:
            pass

        # 轻量用户行为触发：滚动一下，让页面按“正常用户”路径发起请求
        try:
            await self.human_scroll()
            await asyncio.sleep(1.5)
        except Exception:
            pass

        # 注意：此前的主动 API 触发会在部分账号上返回“账号异常”，默认禁用。
        # 如需强制触发用于调试，可设置环境变量 XHS_FORCE_TRIGGER_API=1
        if self.use_api_sniffing and str(os.getenv('XHS_FORCE_TRIGGER_API', '')).lower() in {'1', 'true', 'yes'}:
            await self._trigger_search_api(keyword)
        
        # 定义三层提取器
        async def api_extractor():
            """第一层：Network Sniffing"""
            if self.use_api_sniffing:
                logger.info("🎧 [Layer 1] 启动 Network Sniffing...")
                notes = await self._extract_from_api()
                if notes:
                    return notes

                # 兜底策略：未拦截到 search 包时，再切换「笔记」+滚动+主动调接口
                logger.warning("⚠️ 未拦截到 search 数据，尝试兜底：切换笔记页签+滚动+主动搜索 API")
                try:
                    await self._try_switch_to_notes_tab()
                    await self.human_scroll()
                    await asyncio.sleep(1.2)
                except Exception:
                    pass

                try:
                    await self._trigger_search_api(keyword)
                    await asyncio.sleep(1.0)
                except Exception:
                    logger.debug("主动搜索 API 兜底失败(已忽略)")

                return await self._extract_from_api()
            return []
        
        async def html_extractor():
            logger.info("🔍 [Layer 2] 启用最小 DOM 提取 (Fallback)")
            return await self._extract_from_dom_cards(limit=max_pages * 20)
        
        # 执行三层降级抓取
        all_notes = await self.extraction_engine.extract_with_fallback(
            api_extractor=api_extractor,
            html_extractor=html_extractor,
            mock_generator=None,  # 关闭 Mock，确保只返回真实数据
            context={
                'keyword': keyword,
                'count': max_pages * 20,
                'platform': 'xiaohongshu'
            }
        )
        
        # 添加通用字段
        for note in all_notes:
            note['platform'] = 'xiaohongshu'
            note['keyword'] = keyword
            note['crawl_time'] = datetime.now().isoformat()

        # 触发详情页请求以拦截 note_detail（可选）
        if fetch_detail and self.use_api_sniffing:
            await self._warm_note_details(all_notes, limit=detail_limit)
        
        # 打印统计信息
        stats = self.extraction_engine.get_stats()
        logger.info(f"📊 提取统计: {stats}")
        logger.success(f"✅ 搜索完成！共提取 {len(all_notes)} 条笔记")
        
        return all_notes[:max_pages * 20]  # 限制数量

    async def _extract_from_dom_cards(self, limit: int = 60) -> List[Dict[str, Any]]:
        """最小 DOM 提取：从搜索结果页中抓取卡片链接与文本。

        目标：在 API 嗅探被风控/加密时，仍能返回可用的 note_id/url/title。
        """
        if not self.page:
            return []

        try:
            items = await self.page.evaluate(
                                r"""
                (limit) => {
                  const uniq = new Set();
                  const out = [];
                  const anchors = Array.from(document.querySelectorAll('a[href]'))
                    .filter(a => (a.getAttribute('href') || '').includes('/explore/'));

                  for (const a of anchors) {
                    if (out.length >= limit) break;
                    const href = a.getAttribute('href') || '';
                    const m = href.match(/\/explore\/(\w+)/);
                    const noteId = m ? m[1] : null;
                    const url = href.startsWith('http') ? href : (location.origin + href);
                    const text = (a.innerText || '').trim();

                    if (!noteId || uniq.has(noteId)) continue;
                    uniq.add(noteId);

                    out.push({
                      note_id: noteId,
                      url,
                      title: text ? text.split(/\n|\r/)[0].slice(0, 80) : '',
                      raw_text: text.slice(0, 200),
                    });
                  }
                  return out;
                }
                """,
                limit,
            )
        except Exception:
            items = []

        results: List[Dict[str, Any]] = []
        for it in items or []:
            if not isinstance(it, dict):
                continue
            note_id = it.get('note_id')
            if not note_id:
                continue
            results.append({
                'note_id': note_id,
                'url': it.get('url'),
                'title': it.get('title') or it.get('raw_text') or '',
                'source': 'html',
            })
        return results

    async def _ensure_search_page_rendered(self) -> None:
        if not self.page:
            return

        selectors = [
            ".note-item",
            "[data-note-id]",
            "a[href*='/explore/']",
        ]

        for attempt in range(2):
            for sel in selectors:
                try:
                    await self.page.wait_for_selector(sel, timeout=3500)
                    logger.debug(f"🖼️ 搜索页渲染检测通过: {sel}")
                    return
                except Exception:
                    continue

            # 未检测到卡片，尝试自愈：reload + 轻滚动
            try:
                logger.info("🔄 搜索页疑似未完全渲染，尝试 reload + 轻滚动 自愈…")
                await self.page.reload(wait_until='domcontentloaded', timeout=15000)
                await self.wait_for_load_state('networkidle', timeout=12000)
                try:
                    await self.human_scroll()
                    await asyncio.sleep(0.8)
                except Exception:
                    pass
            except Exception as exc:
                logger.debug(f"reload 自愈失败(已忽略): {exc}")

        logger.warning("⚠️ 搜索页未检测到卡片元素，可能渲染不全或被风控")

    async def _dismiss_login_prompts(self) -> None:
        if not self.page:
            return
        selectors = [
            "button:has-text('登录')",
            "button:has-text('去登录')",
            "button:has-text('取消')",
            "[aria-label='关闭']",
            "svg[aria-label='关闭']",
            "div[class*='modal'] button",
        ]
        for sel in selectors:
            try:
                loc = self.page.locator(sel).first
                if await loc.count() == 0:
                    continue
                await loc.click(timeout=1000)
                await asyncio.sleep(0.5)
                logger.debug(f"🧹 已尝试关闭登录提示: {sel}")
                return
            except Exception:
                continue

    async def _rehit_search_if_login_prompt(self, keyword: str, search_url: str) -> None:
        if not self.page:
            return
        try:
            body = (await self.page.content() or "").lower()
        except Exception:
            body = ""

        login_signals = ["登录", "login", "account-login", "verify"]
        if any(sig in body for sig in login_signals):
            try:
                logger.info("🔁 搜索页仍有登录提示，先访问 explore 再返回搜索以加载会话")
                await self.goto(f"{self.base_url}/explore")
                await self.wait_for_load_state('networkidle', timeout=10000)
                try:
                    await self.human_scroll()
                    await asyncio.sleep(0.8)
                except Exception:
                    pass
                await self.goto(search_url)
                await self.wait_for_load_state('networkidle', timeout=10000)
            except Exception as exc:
                logger.debug(f"rehit search after explore 失败(已忽略): {exc}")

    async def _try_switch_to_notes_tab(self) -> None:
        if not self.page:
            return
        candidates = [
            "[role='tab']:has-text('笔记')",
            "a:has-text('笔记')",
            "div:has-text('笔记')",
            "span:has-text('笔记')",
            # 新版导航文案（“笔记”改为“图文”或“全部”）
            "[role='tab']:has-text('图文')",
            "a:has-text('图文')",
            "div:has-text('图文')",
            "span:has-text('图文')",
            "[role='tab']:has-text('全部')",
            "a:has-text('全部')",
            "div:has-text('全部')",
            "span:has-text('全部')",
        ]
        for selector in candidates:
            try:
                loc = self.page.locator(selector).first
                if await loc.count() == 0:
                    continue
                await loc.click(timeout=1500)
                await asyncio.sleep(0.8)
                return
            except Exception:
                continue

    async def _retry_search_via_input(self, keyword: str) -> None:
        """当首屏无卡片时，直接在搜索框再次提交关键词。"""
        if not self.page:
            return

        input_selectors = [
            "input[placeholder*='搜索']",
            "input[type='search']",
            "input[type='text']",
        ]
        search_btn_candidates = [
            "button:has-text('搜索')",
            "button[aria-label*='搜索']",
            "svg[aria-label*='搜索']",
            "[data-testid*='search']",
        ]

        for sel in input_selectors:
            try:
                loc = self.page.locator(sel).first
                if await loc.count() == 0:
                    continue
                await loc.click(timeout=1500)
                try:
                    await loc.fill(keyword, timeout=1500)
                except Exception:
                    # 回退：全选+键盘输入
                    await loc.press("Control+A")
                    await loc.type(keyword, delay=30)

                # 优先点击搜索按钮，其次回车
                clicked = False
                for btn_sel in search_btn_candidates:
                    btn = self.page.locator(btn_sel).first
                    if await btn.count() == 0:
                        continue
                    try:
                        await btn.click(timeout=1200)
                        clicked = True
                        break
                    except Exception:
                        continue

                if not clicked:
                    await loc.press("Enter")

                await self.wait_for_load_state('networkidle', timeout=10000)
                try:
                    await self.human_scroll()
                    await asyncio.sleep(0.8)
                except Exception:
                    pass
                return
            except Exception:
                continue

    async def _nudge_search_if_empty(self, keyword: str) -> None:
        """首屏未出现卡片时，主动重新提交关键词一次。"""
        if not self.page:
            return

        try:
            count = await self.page.evaluate(
                """
                () => document.querySelectorAll('a[href*="/explore/"]').length
                """
            )
        except Exception:
            count = 0

        if count and count > 0:
            return

        logger.warning("⚠️ 搜索页未检测到卡片，尝试重新提交关键词以触发加载…")
        await self._retry_search_via_input(keyword)

    async def _extract_from_api(self) -> List[Dict[str, Any]]:
        """
        从拦截的 API 数据中提取笔记（Network Sniffing）
        
        Returns:
            笔记列表
        """
        import asyncio
        
        # 等待 API 响应
        await asyncio.sleep(2)
        
        # 获取拦截的 API 数据（search + feed + note_detail）
        api_responses = []
        for api_name in ("search", "feed", "note_detail"):
            api_responses.extend([
                {
                    'name': api_name,
                    'data': resp
                }
                for resp in self.get_api_responses(api_name)
            ])

        if not api_responses:
            logger.info("⚠️ 未拦截到 API 数据，使用 HTML 提取")
            return []

        all_notes = []

        for response in api_responses:
            raw = response.get('data')
            payload = raw.get('data') if isinstance(raw, dict) else raw

            # 提取并映射数据
            notes = self.extract_from_api(
                api_data=payload,
                data_path=NetworkInterceptorConfig.XIAOHONGSHU_APIS[response['name']]['data_path'],
                mapping=NetworkInterceptorConfig.XIAOHONGSHU_MAPPING
            )
            
            # 添加额外字段
            for note in notes:
                note['platform'] = 'xiaohongshu'
                note['crawl_time'] = datetime.now().isoformat()
                note['source'] = 'api'  # 标记数据来源

                # 构造可访问的详情链接（需要 xsec_token）
                nid = note.get('note_id')
                token = note.get('xsec_token')
                if nid and token and not note.get('url'):
                    note['url'] = f"{self.base_url}/explore/{nid}?xsec_token={token}&xsec_source=pc_search"
            
            all_notes.extend(notes)

        if not all_notes:
            logger.warning("⚠️ [Layer 1] API 提取结果为空")
        else:
            logger.success(f"✅ [Layer 1] API 提取成功: {len(all_notes)} 条")
        
        return all_notes

    async def _warm_note_details(self, notes: List[Dict[str, Any]], limit: int = 5) -> None:
        """依次访问笔记详情页，触发 note_detail 接口以便拦截。

        Args:
            notes: 已提取的笔记列表（需包含 note_id）
            limit: 最多触发的笔记数量，避免过多跳转
        """
        if not notes or limit <= 0:
            return

        # 去重并截断
        note_ids = []
        seen = set()
        for item in notes:
            nid = item.get('note_id')
            if nid and nid not in seen:
                seen.add(nid)
                note_ids.append(nid)
            if len(note_ids) >= limit:
                break

        if not note_ids:
            return

        logger.info(f"🎯 触发 {len(note_ids)} 条笔记详情以拦截 note_detail API")

        for idx, nid in enumerate(note_ids, 1):
            try:
                token = None
                for item in notes:
                    if item.get('note_id') == nid and item.get('xsec_token'):
                        token = item.get('xsec_token')
                        break

                if token:
                    detail_url = f"{self.base_url}/explore/{nid}?xsec_token={token}&xsec_source=pc_search"
                else:
                    detail_url = f"{self.base_url}/explore/{nid}"
                await self.goto(detail_url)
                await self.wait_for_load_state('networkidle', timeout=8000)
                await asyncio.sleep(1.5)  # 留时间让 note_detail 返回
                logger.debug(f"✅ 详情触发 {idx}/{len(note_ids)}: {nid}")
            except Exception as exc:
                logger.warning(f"⚠️ 详情触发失败 {nid}: {exc}")

    async def _trigger_search_api(self, keyword: str) -> None:
        """主动请求搜索 API，帮助在首屏就捕获 JSON。

        依赖已有登录 Cookie，若未登录可能返回 401 或空数据。
        """
        try:
            from urllib.parse import quote

            kw = quote(keyword, safe="")
            candidates = [
                (
                    "GET",
                    "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes"
                    f"?keyword={kw}&page=1&page_size=20&sort=general&note_type=0"
                    "&image_formats=jpg,webp,avif",
                    None,
                ),
                (
                    "GET",
                    f"{self.base_url}/api/sns/web/v1/search/notes"
                    f"?keyword={kw}&page=1&page_size=20&sort=general&note_type=0"
                    "&image_formats=jpg,webp,avif",
                    None,
                ),
                (
                    "POST",
                    "https://edith.xiaohongshu.com/api/sns/web/v1/search/notes",
                    {
                        "keyword": keyword,
                        "page": 1,
                        "page_size": 20,
                        "sort": "general",
                        "note_type": 0,
                        "image_formats": "jpg,webp,avif",
                    },
                ),
            ]

            for method, url, payload in candidates:
                try:
                    if method == "POST":
                        resp = await self.page.request.post(url, data=payload)
                    else:
                        resp = await self.page.request.get(url)
                    status = resp.status
                    if status != 200:
                        try:
                            text = await resp.text()
                            text = (text or "").strip().replace("\n", " ")
                            text = text[:200]
                        except Exception:
                            text = ""
                        logger.debug(f"🔄 主动触发搜索 API({method}): {url} -> {status} {text}")
                    else:
                        logger.debug(f"🔄 主动触发搜索 API({method}): {url} -> {status}")

                        # 注意：page.request 不会触发 page.on('response')，因此需要手动灌入拦截缓存
                        # 以便后续 Network Sniffing 层可直接消费。
                        if method == "POST":
                            try:
                                json_data = await resp.json()

                                # Debug：落盘一份 API 响应样本，便于校准 data_path（仅 debug_mode）
                                try:
                                    if getattr(self, 'debug_mode', False):
                                        from pathlib import Path
                                        import json as _json
                                        from datetime import datetime as _dt

                                        Path('logs').mkdir(exist_ok=True)
                                        ts = _dt.now().strftime('%Y%m%d_%H%M%S')
                                        dump_path = Path('logs') / f"debug_xhs_search_api_{ts}.json"
                                        dump_path.write_text(_json.dumps(json_data, ensure_ascii=False, indent=2), encoding='utf-8')
                                        logger.info(f"🧾 已写入搜索 API 样本: {dump_path}")
                                except Exception:
                                    pass

                                if not hasattr(self, 'intercepted_apis'):
                                    self.intercepted_apis = {}
                                self.intercepted_apis.setdefault('search', []).append({
                                    'url': url,
                                    'method': method,
                                    'status': status,
                                    'data': json_data,
                                    'timestamp': datetime.now().isoformat(),
                                })
                                logger.success("✅ 已将主动搜索 API 响应写入拦截缓存 (search)")
                            except Exception as inject_exc:
                                logger.debug(f"⚠️ 写入拦截缓存失败: {inject_exc}")
                        break
                except Exception as inner_exc:
                    logger.debug(f"🔄 主动触发搜索 API({method}) 失败: {url} -> {inner_exc}")
        except Exception as exc:
            logger.warning(f"⚠️ 主动触发搜索 API 失败: {exc}")
    
    # 自愈式功能已移除，已优化为三层降级提取（API → HTML → Mock）
    
    async def _load_more_notes(self) -> None:
        """
        加载更多笔记（小红书采用无限滚动）
        """
        # 滚动到底部触发加载
        await self.scroll_to_bottom(max_scrolls=3, delay_range=(1, 2))
        
        # 智能等待新内容加载（等待网络空闲）
        await self.wait_for_load_state('networkidle', timeout=5000)
        
        logger.debug("已触发加载更多内容")
    
    async def get_note_detail(self, note_url: str) -> Dict[str, Any]:
        """
        获取笔记详情
        
        Args:
            note_url: 笔记链接
            
        Returns:
            详细数据
        """
        logger.info(f"正在获取笔记详情: {note_url}")
        
        await self.goto(note_url)
        
        # 智能等待笔记内容加载
        await self.wait_for_load_state('networkidle', timeout=10000)
        await self.wait_for_selector('.note-content, .content', timeout=10000)
        
        # 提取详情数据
        detail = {}
        
        try:
            # 标题
            title_elem = await self.page.query_selector('.title, h1')
            detail['title'] = await title_elem.inner_text() if title_elem else ""
            
            # 内容
            content_elem = await self.page.query_selector('.note-content, .desc')
            detail['content'] = await content_elem.inner_text() if content_elem else ""
            
            # 作者信息
            author_elem = await self.page.query_selector('.author-name, .user-name')
            detail['author'] = await author_elem.inner_text() if author_elem else ""
            
            # 互动数据
            likes_elem = await self.page.query_selector('[class*="like-count"]')
            detail['likes'] = await self._extract_number(likes_elem) if likes_elem else 0
            
            comments_elem = await self.page.query_selector('[class*="comment-count"]')
            detail['comments'] = await self._extract_number(comments_elem) if comments_elem else 0
            
            collects_elem = await self.page.query_selector('[class*="collect-count"]')
            detail['collects'] = await self._extract_number(collects_elem) if collects_elem else 0
            
            # 发布时间
            time_elem = await self.page.query_selector('.publish-time, .date')
            detail['publish_time'] = await time_elem.inner_text() if time_elem else ""
            
            # 标签
            tag_elems = await self.page.query_selector_all('.tag, .hashtag')
            detail['tags'] = [await tag.inner_text() for tag in tag_elems]
            
            detail['url'] = note_url
            detail['crawl_time'] = datetime.now().isoformat()
            
            logger.success(f"详情获取成功: {detail['title'][:30]}...")
            
        except Exception as e:
            logger.error(f"获取笔记详情失败: {e}")
            await self.screenshot(f"./logs/xhs_detail_error_{datetime.now().strftime('%H%M%S')}.png")
        
        return detail
    
    async def batch_search(self, keywords: List[str], max_pages: int = 3) -> Dict[str, List[Dict]]:
        """
        批量搜索多个关键词
        
        Args:
            keywords: 关键词列表
            max_pages: 每个关键词的最大页数
            
        Returns:
            {关键词: [笔记列表]}
        """
        results = {}
        
        for idx, keyword in enumerate(keywords, 1):
            logger.info(f"[{idx}/{len(keywords)}] 开始搜索关键词: {keyword}")
            
            try:
                notes = await self.search_notes(keyword, max_pages)
                results[keyword] = notes
                logger.success(f"关键词 '{keyword}' 完成，获取 {len(notes)} 条数据")
            except Exception as e:
                logger.error(f"关键词 '{keyword}' 搜索失败: {e}")
                results[keyword] = []
            
            # 关键词之间的延迟
            if idx < len(keywords):
                await self.random_delay(3, 6)
        
        return results


# 使用示例
async def demo():
    """演示小红书适配器使用"""
    async with XiaohongshuAdapter() as spider:
        # 单个关键词搜索
        notes = await spider.search_notes("瑜伽垫", max_pages=2)
        print(f"找到 {len(notes)} 条笔记")
        
        # 批量搜索
        results = await spider.batch_search(["瑜伽垫", "健身器材"], max_pages=2)
        for kw, notes in results.items():
            print(f"{kw}: {len(notes)} 条")


if __name__ == "__main__":
    import asyncio
    asyncio.run(demo())
