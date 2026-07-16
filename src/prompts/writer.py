"""
Writer 角色的 Prompt 模板 —— 项目最核心的资产。

为什么 Prompt 单独放一个文件:
    Prompt 会反复迭代(面试官会问"你怎么优化 Prompt 的")。
    独立文件方便:
        1. 用 git 追踪每次改动,做 A/B 对比
        2. 未来做多语种(美/日/德)时按文件切
        3. 面试时打开这个文件讲设计思路

Prompt 设计的核心原则(写在这里,方便你面试讲):
    1. 角色明确:不是"你是一个 AI",而是"你是一个亚马逊卖家的 Listing 优化师"
    2. 上下文足够:告诉它品类、目标市场、目标读者
    3. 输出结构化:强制 JSON,方便下游解析(Sprint 2 加 Reviewer 会用)
    4. 用规则约束:Title 200 字符内、Bullet 每条以大写词开头 …
    5. Few-shot(Sprint 1 已加):RAG 提供的类目关键词库 + 竞品 Title 作为参考

Sprint 2 Step 4 追加:
    - build_writer_rewrite_message() 重写模式的 Prompt

Sprint 1 追加(2026-07-14):
    - build 函数支持 rag_context 参数,注入类目关键词库 + 竞品 Title
    - rag_context 为空时自动跳过(graceful fallback,支持没关键词库的类目)
"""

import json


SYSTEM_PROMPT = """你是一名资深亚马逊 Listing 优化专家,服务全球跨境电商卖家。

# 你的能力
- 熟悉亚马逊各主要品类的 SEO 规则和转化率优化经验
- 能把商品的技术参数翻译成"消费者语言"(利益点而非功能点)
- 懂 A9 算法:知道哪些关键词该放 Title、哪些放 Backend Keywords

# 输出要求
你必须以 JSON 格式返回,schema 如下:

{
  "title": "string, 200 字符以内, 前 5 个词内必须包含核心关键词",
  "bullet_points": [
    "string, 5 条, 每条 200-500 字符, 以大写词/短语开头",
    "..."
  ],
  "product_description": "string, 800-2000 字符, 讲故事式描述, 包含使用场景",
  "backend_keywords": "string, 空格分隔, 249 字节以内, 不包含 title 里已有的词",
  "target_search_terms": [
    "string, 5-10 个, 卖家应该投放的核心搜索词"
  ],
  "reasoning": "string, 100-200 字, 简要说明你的关键词策略和写作逻辑"
}

# 硬性规则
- Title 严格控制在 200 字符以内(超了亚马逊会截断)
- 5 条 Bullet Points,每条独立、有主次、按重要性排序
- Backend Keywords 不许重复 Title 里的词(浪费空间)
- 输出的必须是**纯 JSON**,前后不要加任何解释性文字,不要用 markdown 代码块包裹

# 写作风格
- 用"You" 直接跟消费者对话
- 每条 Bullet 先讲利益(EASY CLEANUP)再讲功能(dishwasher safe)
- 避免夸张词(BEST, PERFECT, AMAZING)—— 亚马逊 TOS 禁止
- 用具体数字建立信任(480°F, 17-inch, 3-oz)
"""


def _format_rag_context(rag_context: dict | None) -> str:
    """
    把 RAG 检索结果格式化成 Prompt 里的一个 section。

    参数:
        rag_context: {"top_keywords": [...], "competitor_titles": [...]}
                     为 None 或空 dict 时返回空字符串(graceful fallback)

    返回:
        - 有数据:格式化的 Markdown section
        - 无数据:空字符串(build 函数会跳过整个 section)

    为什么单独一个函数:
        首稿 Prompt 和重写 Prompt 都要注入 RAG context,格式一致。
        抽出来一个函数,两处调用共用逻辑,DRY 原则。
    """
    if not rag_context:
        return ""

    top_keywords = rag_context.get("top_keywords") or []
    competitor_titles = rag_context.get("competitor_titles") or []

    if not top_keywords and not competitor_titles:
        return ""

    parts: list[str] = ["# 类目参考数据(来自知识库检索,请自然融入 Listing)"]

    if top_keywords:
        parts.append(
            "\n## 该类目 Top 关键词(按 BM25 相关性排序)\n"
            + ", ".join(top_keywords)
        )

    if competitor_titles:
        titles_text = "\n".join(f"- {t}" for t in competitor_titles)
        parts.append(
            "\n## Amazon Best Seller 竞品 Title(参考结构,不要抄袭)\n"
            + titles_text
        )

    # 前后加空行,跟其他 section 视觉隔开
    return "\n" + "\n".join(parts) + "\n"


def build_writer_user_message(
    product_info: dict,
    rag_context: dict | None = None,
) -> str:
    """
    首稿模式:把产品的结构化 JSON 转成给 LLM 的用户消息。

    参数:
        product_info: 从 data/sample_products/*.json 读出来的 dict
        rag_context:  可选,RAG 检索结果 {top_keywords, competitor_titles}
                      为空时自动跳过 RAG section(graceful fallback)
    """
    rag_section = _format_rag_context(rag_context)

    return f"""请为下面这个商品生成一份高质量的 Amazon Listing。

# 商品信息
```json
{json.dumps(product_info, ensure_ascii=False, indent=2)}
```
{rag_section}
# 特别提示
- 目标市场是 {product_info.get('target_marketplace', 'amazon.com')}
- 目标语言是 {product_info.get('target_language', 'en-US')}
- 卖家提供了这些种子关键词供你参考:{product_info.get('keywords_seed', [])}
- 请充分利用商品的差异化点(differentiation 字段)—— 这是 Bullet Points 的黄金素材

现在输出你的 Listing(纯 JSON,不要加任何前后缀)。
"""


def build_writer_rewrite_message(
    product_info: dict,
    previous_listing: dict,
    issues: list[dict],
    rag_context: dict | None = None,
) -> str:
    """
    重写模式的 Prompt —— Writer 收到 Reviewer 的反馈,做**定向修改**,不是从头写。

    参数:
        product_info:      原始商品信息(不变)
        previous_listing:  Writer 上一轮的输出(现在要改的东西)
        issues:            Reviewer 反馈的问题列表,每条带 fix_hint
        rag_context:       可选,RAG 检索结果 —— 重写时也需要,方便 Writer
                           针对"关键词覆盖不足"这类反馈找到该加什么词

    为什么重写模式也要 RAG:
        Reviewer 可能反馈"缺 keyword X",Writer 需要知道"该类目还有哪些
        相关词"才能自然补充。没 RAG 的话 Writer 只能凭直觉编词。
    """
    # 把 issues 组织成"编号 + 位置 + 具体动作"的清单
    issues_text = "\n".join(
        f"{i}. [{issue.get('field', '?')}] {issue.get('message', '')}\n"
        f"   → 具体改法: {issue.get('fix_hint', '(无)')}"
        for i, issue in enumerate(issues, start=1)
    )

    rag_section = _format_rag_context(rag_context)

    return f"""你上一轮写的 Listing 被审核员挑出了几个问题,现在按反馈**定向修改**。

# 商品信息(不变,仅供参考)
```json
{json.dumps(product_info, ensure_ascii=False, indent=2)}
```

# 你上一轮的 Listing(要改的东西)
```json
{json.dumps(previous_listing, ensure_ascii=False, indent=2)}
```
{rag_section}
# 审核员反馈(必须逐条解决,不能漏)
{issues_text}

# 改写规则
- **保留上一轮做对的部分**,只改问题指出的地方 —— 不要从头重写
- 严格遵守每条 fix_hint 的具体建议
- 特别注意硬边界(字符数、字节数、条数),这些是 error 级问题,不改无法通过
- 输出格式跟上次一样(纯 JSON,不加前后缀)

现在输出**改写后的完整 Listing**。
"""
