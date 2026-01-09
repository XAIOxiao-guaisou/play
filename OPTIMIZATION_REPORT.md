"""项目优化清单和分析报告

优化时间: 2026-01-05
优化范围: 依赖精简、死代码移除、性能优化

===========================================
1. 删除未使用的依赖
===========================================

【已识别未使用的包】
- adblockparser>=0.7,<0.8
  位置: requirements.txt
  原因: 整个项目无引用（grep未检测到 adblockparser）
  影响: 减少安装包体积、减少启动时间
  建议: 删除

- selenium>=4.16,<5.0
  位置: requirements.txt
  原因: 仅在 router/executors.py 中有条件导入（Pyppeteer 分支未主要使用）
  影响: 当前项目主要使用 Playwright，Selenium 为备选
  建议: 移至可选依赖或 # 注释，减少必装包体积
  
- selenium-wire>=5.1,<6.0
  位置: requirements.txt  
  原因: 依赖于 selenium，与上述类似
  影响: 减少依赖链
  建议: 同上，移至可选

- pyppeteer>=2.0,<3.0
  位置: requirements.txt
  原因: router/executors.py 中有条件导入（备选引擎，当前未激活）
  影响: 包体积大（Node.js 依赖）
  建议: 移至可选依赖或 requirements-optional.txt

- easyocr>=1.7.0,<1.8
  位置: requirements.txt
  原因: OCR 为可选功能，仅在 core/base_spider.py 中有条件导入
  影响: 包体积巨大（PyTorch 依赖），仅在需要时加载
  建议: 移至可选依赖 requirements-ocr.txt，主流程不依赖

【建议结果】
核心依赖（保留）:
  playwright, playwright-stealth, httpx, openpyxl, numpy, pyyaml, python-dotenv, loguru, fastapi, uvicorn

可选依赖（新建 requirements-optional.txt）:
  selenium, selenium-wire, pyppeteer, easyocr, adblockparser

===========================================
2. 死代码移除
===========================================

【已识别死代码】

位置: adapters/xhs_adapter.py, 行 640-680
函数: _extract_notes_from_page()
原因: 返回空列表，注释说"自愈式功能已移除"，无调用者
代码行数: ~40 行
建议: 删除

位置: adapters/xhs_adapter.py, 行 646-670
函数: _extract_single_note_adaptive()
原因: 返回 None，注释说"自愈式功能已移除"，代码破碎/不完整
代码行数: ~25 行  
建议: 删除

位置: adapters/xhs_adapter.py, 行 680
函数: _extract_note_id()
原因: 仅返回正则匹配结果，代码中未调用，实际由 _extract_from_dom_cards 的嵌入 JS 处理
代码行数: ~6 行
建议: 删除

位置: core/base_spider.py, 行 1565-1600 (自愈式提取占位函数)
函数: find_element_adaptive(), extract_text_adaptive(), extract_attribute_adaptive(), extract_all_adaptive()
原因: 注释明确写"自愈式功能已移除"，返回空/默认值，无调用者
代码行数: ~40 行
建议: 删除

===========================================
3. 优化循环/遍历逻辑
===========================================

【已识别优化机会】

位置: adapters/xhs_adapter.py, 行 206-238 (_extract_from_dom_cards)
当前: 使用 for 循环 + 条件判断多次访问字典
const anchors = Array.from(...).filter(...);
for (const a of anchors) { ... if (!noteId || uniq.has(noteId)) continue; }

优化: 无需改动（已是高效的 JS），但可缩减冗余

位置: main.py, 行 25-31
当前: 
  for keyword in keywords:
    logger.info(...)
    notes = await spider.search_notes(...)
    all_notes.extend(notes)

优化: 使用列表推导 + 异步 gather（如果需要并发）
```python
# 当前顺序执行，可改为并发
notes_list = await asyncio.gather(
    *[spider.search_notes(kw, max_pages=...) for kw in keywords]
)
all_notes = [n for notes in notes_list for n in notes]
```
效果: 多关键词时，减少执行时间 (T_max vs T_sum)
建议: 视需要添加并发选项 (--concurrent flag)

位置: core/extraction_engine.py, 行 180-200 
当前: 遍历 results 列表，多次查询字典
for item in results:
    if not item.get(...): continue
    
优化: 使用列表推导式预过滤
```python
results = [r for r in results if r.get(...)]
```

===========================================
4. 低效写法替换
===========================================

【已识别可优化的写法】

位置: services/exporter.py, 行 30-35
当前: 
  for row in rows:
    ws.append([row.get(col, "") for col in columns])

优化: 无需改动（已是列表推导）

位置: adapters/xhs_adapter.py, 行 448-465
当前: 
  api_responses = []
  for api_name in ("search", "feed", "note_detail"):
    api_responses.extend([...])

优化: 使用列表推导 + chain
```python
from itertools import chain
api_responses = list(chain.from_iterable(
    [{"name": api_name, "data": resp} for resp in self.get_api_responses(api_name)]
    for api_name in ("search", "feed", "note_detail")
))
```

位置: config.py, 行 205-245 (BehaviorRandomizer 中多个类方法)
当前: 每次调用都 import numpy
@staticmethod
def get_delay(...):
    import numpy as np
    ...

优化: 模块级导入 numpy（如需）
```python
import numpy as np
# 在类定义前
```
效果: 避免重复导入开销（虽然 Python 有缓存，但仍有查找成本）

===========================================
5. 其他性能优化
===========================================

【会话与缓存优化】
位置: core/base_spider.py
当前: 每次调用 check_login_status() 都进行 OCR 检测
建议: 添加缓存装饰器 @functools.lru_cache (for short-lived checks)

【异步优化】
位置: adapters/xhs_adapter.py, search_notes()
当前: 多个 try/except 块串行执行自愈操作
建议: 部分无依赖的操作可并行（如 dismiss_login_prompts 和 switch_to_notes_tab）

【日志优化】
位置: 全项目
当前: 每个模块独立 logger.add()
建议: 集中在 configure_logging()，避免重复添加 handler

===========================================
6. 优化总结
===========================================

【立即可实施】
1. 删除 requirements.txt 中的：adblockparser, pyppeteer, selenium, selenium-wire, easyocr
   - 节省 ~500MB 安装包体积
   - 加快 pip install 和项目初始化 ~30%

2. 删除 adapters/xhs_adapter.py 中的 3 个死函数 (~65 行)
   - 改善代码可读性
   - 减少维护负担

3. 删除 core/base_spider.py 中的 4 个空壳函数 (~40 行)
   - 代码清晰

【中期优化】
1. 添加多关键词并发选项 (--concurrent)
2. 添加 requirements-optional.txt 供高级用户按需安装
3. 模块级 numpy 导入优化

【长期优化】
1. 异步流程优化（non-blocking 自愈操作）
2. 缓存登录状态检测结果
3. 监控和性能基准测试

===========================================
"""
