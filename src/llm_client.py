"""
LLM 客户端封装 —— 所有跟 Claude API 的交互都走这里。

为什么要封装：
    1. 未来换模型（比如加个国内 DeepSeek 备份），只改这一个文件
    2. 统一加日志、重试、成本统计
    3. 面试时可以指着这个文件说"我做了 provider 抽象层"

对小白的重点：这一版故意做得很简单，只封装一个 chat() 方法。
              Sprint 2 加 tool use 时会扩展这个类。
"""

from anthropic import Anthropic
from src.config import settings


class LLMClient:
    """封装 Anthropic 官方 SDK 的薄壳。"""

    def __init__(self) -> None:
        # 校验：确保 API Key 已配
        settings.validate()

        # 构造 Anthropic 客户端
        # - 官方直连：Anthropic() 无参构造，自动读 ANTHROPIC_API_KEY 环境变量
        # - 公司/中转服务：显式传 base_url 覆盖默认地址
        #
        # 为什么这么写：中转服务通常"协议兼容 Anthropic 官方 API"，
        # 只是把请求转发到另一个地址，SDK 代码不用改，只换 base_url。
        # 这就是"面向接口而非实现编程"—— 面试可以讲这句。
        if settings.base_url:
            self.client = Anthropic(
                api_key=settings.api_key,
                base_url=settings.base_url,
            )
            print(f"[LLMClient] 使用中转服务: {settings.base_url}")
        else:
            self.client = Anthropic()  # 自动读环境变量
            print("[LLMClient] 使用 Anthropic 官方地址")

    def chat(
        self,
        system_prompt: str,
        user_message: str,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """
        发一次消息给 Claude，拿到文本响应。

        参数:
            system_prompt: 系统提示词（告诉 Claude 扮演什么角色）
            user_message: 用户消息（本次要它做什么）
            model: 覆盖默认模型（不传就用 config 里的 model_main）
            max_tokens: 覆盖默认输出长度

        返回:
            Claude 的回复文本（纯字符串）

        为什么 system 和 user 分开：
            Anthropic API 的设计：system 放角色设定（稳定不变），
            messages 里放对话（每次变）。分开传是官方 API 的形状，
            也方便未来做 Prompt Caching（省钱）。
        """
        response = self.client.messages.create(
            model=model or settings.model_main,
            max_tokens=max_tokens or settings.max_tokens,
            system=system_prompt,
            messages=[
                {"role": "user", "content": user_message},
            ],
        )

        # response.content 是一个 block 列表，Sprint 0 只有一个文本 block
        # Sprint 3 加 tool_use 之后会有多个 block，那时再改这里
        return response.content[0].text


# 全局单例，其他模块 from src.llm_client import llm 直接用
llm = LLMClient()
