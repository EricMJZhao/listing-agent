"""
Writer Agent —— 负责写 Listing 初稿 + 重写。

Sprint 演进:
    Sprint 0:单 Agent 端到端(纯 LLM 调用)
    Sprint 1:挂 RAG(BM25 关键词检索)
    Sprint 2:降级为"初稿手 + 定向改写手",Reviewer 审核
    Sprint 3(2026-07-14):挂 tool_use,主动查搜索量 / 字节数决策

它做什么:
    - run(product_info) → Listing dict          (首稿模式,RAG + tool_use)
    - rewrite(product_info, prev, issues) → Listing dict  (重写模式,RAG + tool_use)

设计原则:**单一职责** —— Writer 只管"根据 Prompt + 工具输出结果",
        规则检查交 Reviewer、流程控制交 Orchestrator。

Sprint 3 关键决策:
    - **默认走 tool_use 模式**(不给 fallback 选项),但 max_iterations=8 兜底防死循环
    - **Prompt 里明确 tool 使用建议**,让 LLM 知道什么时候该调 —— 不然它可能不用
    - **JSON 解析放在 Agent Loop 之外** —— tool_use loop 返回文本,外面统一 parse

面试话术:
    "Writer 在 Sprint 3 从'纯 Prompt 生成'升级到'主动查数据再决策'。它可以
     用 search_keyword_volume 决定 Title 用哪些词,用 check_text_bytes estimate
     Backend Keywords 字节数 —— **不再是黑盒生成,是有可观测决策链的 Agent**。"
"""

from src.agents.base import BaseAgent
from src.prompts.writer import (
    SYSTEM_PROMPT,
    build_writer_user_message,
    build_writer_rewrite_message,
)
from src.rag.keyword_store import KeywordStore
from src.tools.mock_tools import TOOL_SCHEMAS


# 类目 → 关键词库映射(Sprint 1 引入)
CATEGORY_KB_MAP: dict[str, str] = {
    "Bamboo Cutting Board": "data/knowledge_base/cutting_board_keywords.json",
    "Wooden Cutting Board": "data/knowledge_base/cutting_board_keywords.json",
    # Sprint 6 加入:烘焙工具类目,词库来自 amazon_suggest v0.2.5 自动采集(379 词)
    "Silicone Baking Mat": "data/knowledge_base/baking_keywords.json",
    "Cake Pan": "data/knowledge_base/baking_keywords.json",
    "Measuring Cups": "data/knowledge_base/baking_keywords.json",
    "Piping Bag": "data/knowledge_base/baking_keywords.json",
    "Cookie Cutter": "data/knowledge_base/baking_keywords.json",
}


# Writer 的 Prompt 里追加的 tool 使用建议
# 单独抽出来是因为首稿和重写都要加,DRY
_TOOL_USAGE_HINT = """
# 你可以调用的工具(可选)
- `search_keyword_volume(keyword)`:在决定 Title 里放哪些词之前,可以先查
  月搜索量。搜索量 > 5000 且 competition ≠ high 的词才值得放 Title 前 5 词。
- `check_text_bytes(text)`:生成 Backend Keywords 之前,先用这个工具估算
  字节数,避免超 249 字节。
- `search_amazon_keywords(prefix, limit=10)`:**真实 Amazon API**。当你觉得
  静态 RAG 词库对当前产品不够(冷门品类/新兴趋势/长尾覆盖不足),可以传一个
  1-3 词的短入口(如 'silicone baking')拿真实用户搜索补全。返回结果里的
  `keywords` 是真实用户在搜的长尾词,优先用于 Backend Keywords 和场景型 Bullets。
  代价:1 次网络请求,只在必要时调,单个 Listing 建议不超过 2 次。

**使用建议**:不是每个 Listing 都要调工具 —— 只在需要决策依据时调。
简单商品可以直接输出,复杂商品建议先查 1-2 个核心词的搜索量再动手。
冷门品类或觉得词库覆盖不足时,再调 search_amazon_keywords。
"""


class WriterAgent(BaseAgent):
    """给一个商品,写出完整的 Amazon Listing。支持首稿 + 重写 + RAG + tool_use。"""

    name = "writer"

    def __init__(self) -> None:
        # KeywordStore 懒加载缓存(Sprint 1)
        self._kb_cache: dict[str, KeywordStore] = {}

    # ============================================================
    # 主动作:首稿 + 重写(都走 tool_use loop)
    # ============================================================

    def run(self, product_info: dict) -> dict:
        """首稿模式:给一个新商品从零开始写 Listing(RAG + tool_use)。"""
        self._log(f"开始为 SKU {product_info.get('sku', '?')} 生成首稿")

        rag_context = self._get_rag_context(product_info)
        user_message = build_writer_user_message(product_info, rag_context=rag_context)

        # 在 user_message 末尾追加 tool 使用建议
        user_message += _TOOL_USAGE_HINT

        # 走 tool_use loop 而不是普通 _call_llm
        raw_text = self._tool_use_loop(
            system_prompt=SYSTEM_PROMPT,
            user_message=user_message,
            tools=TOOL_SCHEMAS,
        )
        listing = self._parse_json_response(raw_text)

        self._log("Listing 首稿生成完成 ✓")
        return listing

    def rewrite(
        self,
        product_info: dict,
        previous_listing: dict,
        issues: list[dict],
    ) -> dict:
        """重写模式:根据 Reviewer 反馈定向修改(也支持 tool_use)。"""
        self._log(f"进入重写模式:根据 {len(issues)} 条反馈修改上一轮")

        rag_context = self._get_rag_context(product_info)
        user_message = build_writer_rewrite_message(
            product_info=product_info,
            previous_listing=previous_listing,
            issues=issues,
            rag_context=rag_context,
        )
        user_message += _TOOL_USAGE_HINT

        raw_text = self._tool_use_loop(
            system_prompt=SYSTEM_PROMPT,
            user_message=user_message,
            tools=TOOL_SCHEMAS,
        )
        listing = self._parse_json_response(raw_text)

        self._log("Listing 重写完成 ✓")
        return listing

    # ============================================================
    # RAG 相关(Sprint 1)
    # ============================================================

    def _get_rag_context(self, product_info: dict) -> dict | None:
        """Graceful fallback:没类目关键词库时返回 None。"""
        product_type = product_info.get("product_type", "")
        store = self._get_keyword_store(product_type)

        if store is None:
            self._log(f"⚠️  '{product_type}' 无关键词库,跳过 RAG(graceful fallback)")
            return None

        seed_words = " ".join(product_info.get("keywords_seed", []))
        query = f"{product_type} {seed_words}".strip()

        top_keywords = store.search_keywords(query, top_k=20)
        competitor_titles = store.get_competitor_titles(limit=3)

        self._log(
            f"RAG 检索:top {len(top_keywords)} 关键词, "
            f"{len(competitor_titles)} 个竞品 Title"
        )

        return {
            "top_keywords": top_keywords,
            "competitor_titles": competitor_titles,
        }

    def _get_keyword_store(self, product_type: str) -> KeywordStore | None:
        """懒加载 + 缓存。"""
        kb_path = CATEGORY_KB_MAP.get(product_type)
        if not kb_path:
            return None

        if product_type not in self._kb_cache:
            try:
                self._kb_cache[product_type] = KeywordStore(kb_path)
            except FileNotFoundError:
                self._log(f"⚠️  关键词库文件不存在: {kb_path}")
                return None

        return self._kb_cache[product_type]
