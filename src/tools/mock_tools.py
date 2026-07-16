"""
Mock 工具集 —— Sprint 3 核心。

包含 3 个东西:
    1. TOOL_SCHEMAS:Anthropic tool_use 规范的 schema 定义(告诉 LLM 有哪些工具)
    2. 每个 tool 的 mock 实现函数
    3. execute_tool(name, input) 统一分发器(Agent Loop 里调用)

设计原则:
    - Tool schema 和实现在同一个文件,方便面试指着文件讲
    - Mock 数据带一定"随机性"(基于 keyword 长度而非固定值),模拟真实 API 行为
    - 有明确的错误处理(不认识的 tool_name 抛 ValueError,不静默)

面试话术:
    "我把 tool schema、实现、分发放在同一个文件。为什么?—— **一个 tool 是原子单位**,
     schema 和实现分开等于文档和代码分开,容易漂移。这是**共变性设计** —— 应该一起变的东西
     放一起。生产环境如果要接真 API,只要改 impl 函数体,schema 完全不动,upstream(Writer)
     完全无感。"
"""

from typing import Any


# ============================================================
# Tool 1: search_keyword_volume
# 查一个关键词的 Amazon 月搜索量 + 竞争度
# 生产接:Helium10 / Jungle Scout / DataDive API
# ============================================================

SEARCH_KEYWORD_VOLUME_SCHEMA: dict[str, Any] = {
    "name": "search_keyword_volume",
    "description": (
        "查一个关键词在 Amazon US 站的月搜索量和竞争度。"
        "用于在写 Title 或 Bullet 之前决定这个词值不值得放。"
        "月搜索量 > 5000 且 competition = low/medium 才值得放 Title。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "keyword": {
                "type": "string",
                "description": "要查询的关键词,例如 'bamboo cutting board'",
            },
        },
        "required": ["keyword"],
    },
}


def _mock_search_keyword_volume(keyword: str) -> dict[str, Any]:
    """
    Mock 实现 —— 基于关键词特征生成"看起来真实"的数据。

    生成逻辑(不是纯随机,便于面试演示可预测性):
        - 词越短 → 搜索量越高(head keyword)
        - 词越长 → 搜索量越低(long-tail)
        - "cutting board"、"baking mat" 这类头部词强制高分
    """
    keyword_lower = keyword.lower().strip()
    word_count = len(keyword_lower.split())

    # 头部词强制高分(演示时容易讲)
    head_keywords = {
        "cutting board": 165000,
        "bamboo cutting board": 74000,
        "chopping board": 33000,
        "silicone baking mat": 22000,
        "reusable parchment paper": 8100,
    }
    if keyword_lower in head_keywords:
        volume = head_keywords[keyword_lower]
    elif word_count == 1:
        volume = 50000  # 单词泛词
    elif word_count == 2:
        volume = 15000
    elif word_count == 3:
        volume = 4500
    elif word_count == 4:
        volume = 1200
    else:
        volume = 350  # 长尾

    # 竞争度和搜索量正相关(高搜索量 = 高竞争)
    if volume > 30000:
        competition = "high"
    elif volume > 8000:
        competition = "medium"
    else:
        competition = "low"

    return {
        "keyword": keyword,
        "monthly_search_volume": volume,
        "competition": competition,
        "data_source": "mock (Sprint 3 演示用,生产接 Helium10 API)",
    }


# ============================================================
# Tool 2: check_text_bytes
# 让 Writer 自己 estimate 字节数,不用等 Reviewer 挂了才知道
# 生产环境也可以保留 —— Writer 边写边 estimate 效率更高
# ============================================================

CHECK_TEXT_BYTES_SCHEMA: dict[str, Any] = {
    "name": "check_text_bytes",
    "description": (
        "计算一段文本的 UTF-8 字节数,返回是否超过 Amazon Backend Keywords 249 字节上限。"
        "在生成 Backend Keywords 之前建议先调用这个工具估算,避免超字节被截断。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "text": {
                "type": "string",
                "description": "要检查的文本,通常是候选 Backend Keywords",
            },
        },
        "required": ["text"],
    },
}


def _check_text_bytes(text: str) -> dict[str, Any]:
    """
    真实计算(不是 mock)—— 直接算 UTF-8 字节数。

    为什么 Sprint 3 保留这个"工具":
        虽然是纯计算,但通过 tool_use 让 Writer 主动调用,可以观察它
        "什么时候意识到需要检查字节数" —— 这是 Agent 决策链的可观测性。
    """
    byte_len = len(text.encode("utf-8"))
    limit = 249
    return {
        "text_preview": text[:60] + ("..." if len(text) > 60 else ""),
        "byte_length": byte_len,
        "limit": limit,
        "is_over_limit": byte_len > limit,
        "bytes_over": max(0, byte_len - limit),
    }


# ============================================================
# 对外接口:所有 tool 的 schema 列表 + 统一分发器
# ============================================================

TOOL_SCHEMAS: list[dict[str, Any]] = [
    SEARCH_KEYWORD_VOLUME_SCHEMA,
    CHECK_TEXT_BYTES_SCHEMA,
]


# tool_name → 实现函数的映射(方便 dispatcher 扩展)
_TOOL_IMPL: dict[str, Any] = {
    "search_keyword_volume": _mock_search_keyword_volume,
    "check_text_bytes": _check_text_bytes,
}


def execute_tool(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """
    统一执行入口 —— Agent Loop 拿到 tool_use block 后调这个函数。

    参数:
        name:        Anthropic 返回的 tool_use.name
        tool_input:  Anthropic 返回的 tool_use.input(已经是 dict)

    返回:
        dict:  tool 执行结果,会被序列化成 JSON 塞回给 LLM

    为什么用统一分发器而不是 if-elif:
        1. 扩展新 tool 只加一行 _TOOL_IMPL 映射,不改 dispatcher 代码
        2. 未来加通用装饰器(日志、重试、超时)只改一处
        3. **开闭原则** —— 对扩展开放,对修改关闭
    """
    impl = _TOOL_IMPL.get(name)
    if impl is None:
        # 明确抛错,不静默 —— LLM 输出错 tool_name 是 bug 应该暴露
        raise ValueError(
            f"未知 tool: {name}. 可用 tools: {list(_TOOL_IMPL.keys())}"
        )
    return impl(**tool_input)


# ============================================================
# Sprint 6 Task 5:注册真实 API 工具
#
# 这个文件历史上叫 mock_tools,但实际扮演"工具注册中心"角色。
# Sprint 6 之后 mock 和真实 API 工具在这里共存 —— schema/impl 放在
# 各自的采集器/客户端文件里(共变性),此处只做**注册**。
# 未来 mock 全部替换成真实 API 后,可以重命名文件为 tool_registry.py。
# ============================================================

from src.tools.amazon_suggest import (  # noqa: E402
    SEARCH_AMAZON_KEYWORDS_SCHEMA,
    _tool_impl_search_amazon_keywords,
)

TOOL_SCHEMAS.append(SEARCH_AMAZON_KEYWORDS_SCHEMA)
_TOOL_IMPL["search_amazon_keywords"] = _tool_impl_search_amazon_keywords
