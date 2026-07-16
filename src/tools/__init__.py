"""
tools 包 —— Sprint 3 引入。

给 Writer Agent 挂"外部工具",让它能主动查数据再决策 —— 这才是真正意义上的 Agent Loop。

Sprint 3 只做 mock tools,理由:
    1. 作品集不该被 API key 限制(Helium10 付费,爬虫违反 TOS)
    2. mock 数据可以**故意设计**,让面试演示"tool 返回不同数据,Writer 做不同决策"
    3. 面试话术:"mock 是为了演示 tool_use 机制,生产接真实 API 只换 impl 函数"

外部只需 from src.tools.mock_tools import TOOL_SCHEMAS, execute_tool
"""
