"""
Agent 基类 —— Sprint 2 起真正启用,Sprint 3 加 Agent Loop。

为什么要有基类:
    项目里的 Agent(Writer / Reviewer / 未来的 Planner)有公共动作:
        1. 都要调 Claude API 拿文本
        2. 都要把 LLM 返回的 JSON 文本解析成 dict
        3. 都要打日志方便 debug 和演示
        4. (Sprint 3)可能都要跑 tool_use 循环

    如果每个 Agent 自己写一遍,代码重复。抽到基类里,子类只专注独有逻辑。

    面试话术:
        "我抽了一个 BaseAgent 基类,把 LLM 调用、JSON 解析、日志、Agent Loop 上移。
         子类 WriterAgent 只有 30 行,全是它独有的逻辑。**面向对象继承的实际价值**
         —— 每次加基础设施(fallback、Agent Loop),所有 Agent 自动受益。"

Sprint 3 追加(2026-07-14):
    - _tool_use_loop() 自研 Agent Loop,处理 stop_reason=tool_use 的多轮循环
    - 不用 LangChain,自己写 30 行 —— 面试能讲清楚每一行
"""

import json
from abc import ABC, abstractmethod
from typing import Any

from anthropic.types import Message

from src.config import settings
from src.llm_client import llm
from src.tools.mock_tools import execute_tool


# Agent Loop 单次运行的最大工具调用轮次
# 防止 LLM 陷入死循环(反复调 tool 不 end_turn)
DEFAULT_MAX_TOOL_ITERATIONS = 8


class BaseAgent(ABC):
    """所有 Agent 的父类,提供公共动作。"""

    name: str = "base"

    # ============================================================
    # 抽象方法
    # ============================================================

    @abstractmethod
    def run(self, input_data: dict) -> dict:
        raise NotImplementedError

    # ============================================================
    # 公共方法:LLM 调用(带 fallback)
    # ============================================================

    def _call_llm(
        self,
        system_prompt: str,
        user_message: str,
        model: str | None = None,
    ) -> str:
        """
        调 Claude 拿文本(不带 tool_use)。

        Fallback:指定 model 不可用时自动降级到默认 model。
        """
        target_model = model or settings.model_main
        self._log(f"调 LLM(model={target_model})...")

        try:
            response = llm.chat(
                system_prompt=system_prompt,
                user_message=user_message,
                model=model,
            )
        except Exception as e:
            if model and model != settings.model_main:
                self._log(
                    f"⚠️  {target_model} 不可用 ({type(e).__name__}),"
                    f"fallback 到 {settings.model_main}"
                )
                response = llm.chat(
                    system_prompt=system_prompt,
                    user_message=user_message,
                    model=None,
                )
            else:
                raise

        self._log(f"LLM 返回 {len(response)} 字符")
        return response

    # ============================================================
    # Sprint 3 新增:自研 Agent Loop(tool_use)
    # ============================================================

    def _tool_use_loop(
        self,
        system_prompt: str,
        user_message: str,
        tools: list[dict[str, Any]],
        model: str | None = None,
        max_iterations: int = DEFAULT_MAX_TOOL_ITERATIONS,
    ) -> str:
        """
        自研 Agent Loop —— 处理 stop_reason=tool_use 的多轮循环。

        循环逻辑:
            1. 调 Claude 拿 response
            2. 检查 stop_reason:
                - "end_turn"  → LLM 说完了,返回最终文本
                - "tool_use"  → 执行 tool → 结果塞回 messages → 循环
                - 其他        → 报错(超出预期)
            3. max_iterations 到顶抛错(防死循环)

        参数:
            system_prompt:   角色 Prompt
            user_message:    用户初始消息
            tools:           tool schema 列表(Anthropic tool_use 规范)
            model:           可选 model 覆盖
            max_iterations:  最多几轮 tool_use(默认 8)

        返回:
            最终 assistant 文本(end_turn 时的 content[0].text)

        为什么手写这个 loop 不用 LangChain:
            30 行代码,每一行我都能面试讲清楚 —— stop_reason 三种状态、
            tool_use block 结构、messages 拼接协议、循环终止条件。
            LangChain 用 AgentExecutor 一个类封装,细节全黑盒,
            面试问'如果 tool 失败怎么办'我答不上来。
            **自研是玻璃盒,LangChain 是黑盒**。
        """
        target_model = model or settings.model_main
        self._log(f"进入 Agent Loop(model={target_model}, tools={len(tools)} 个)")

        # messages 是"对话历史",每轮追加内容
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_message}
        ]

        for iteration in range(1, max_iterations + 1):
            self._log(f"  Agent Loop 第 {iteration} 轮...")

            # 直接用 llm_client 的底层 client 调 —— 这个 loop 需要 tools 参数,
            # 现有 llm.chat() 只支持普通对话,不支持 tool_use
            response: Message = self._raw_call_with_tools(
                messages=messages,
                system_prompt=system_prompt,
                tools=tools,
                model=target_model,
            )

            stop_reason = response.stop_reason
            self._log(f"  stop_reason={stop_reason}")

            # === Case 1: LLM 说完了,返回文本 ===
            if stop_reason == "end_turn":
                # content 里最后一个 text block 就是最终答案
                for block in response.content:
                    if block.type == "text":
                        self._log(f"  Agent Loop 结束,共 {iteration} 轮")
                        return block.text
                raise RuntimeError("end_turn 但没有 text block,LLM 出错")

            # === Case 2: LLM 要调 tool ===
            if stop_reason == "tool_use":
                # 把 assistant 的整个 response 加进 messages(必须完整,包含 tool_use blocks)
                messages.append(
                    {"role": "assistant", "content": response.content}
                )

                # 找到所有 tool_use block(可能同轮调多个 tool)
                tool_results: list[dict[str, Any]] = []
                for block in response.content:
                    if block.type == "tool_use":
                        self._log(f"    → 调 tool: {block.name}({block.input})")
                        try:
                            result = execute_tool(block.name, block.input)
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": json.dumps(result, ensure_ascii=False),
                            })
                            self._log(f"    ← tool 返回: {json.dumps(result, ensure_ascii=False)[:100]}...")
                        except Exception as e:
                            # tool 执行失败:把错误告诉 LLM,让它决定下一步
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": f"错误: {type(e).__name__}: {e}",
                                "is_error": True,
                            })
                            self._log(f"    ✗ tool 出错: {e}")

                # 把所有 tool_result 一次性塞回 messages,循环继续
                messages.append({"role": "user", "content": tool_results})
                continue

            # === Case 3: 其他状态(超出预期)===
            raise RuntimeError(
                f"未预期的 stop_reason: {stop_reason},response={response}"
            )

        raise RuntimeError(
            f"Agent Loop 超过 {max_iterations} 轮 tool_use 仍未结束 —— "
            f"LLM 可能陷入死循环,人工检查 Prompt"
        )

    def _raw_call_with_tools(
        self,
        messages: list[dict[str, Any]],
        system_prompt: str,
        tools: list[dict[str, Any]],
        model: str,
    ) -> Message:
        """
        底层 tool_use 调用 —— 直接用 Anthropic client,因为需要 tools 参数。

        为什么不放进 llm_client.chat():
            chat() 是 Sprint 0 的简单封装,输入 str 输出 str。
            tool_use 需要 messages list + tools + 完整 Message 对象返回,
            interface 差异大,合并会污染 chat() 的简洁性。
            这一层可以未来重构成 llm.chat_with_tools()。
        """
        return llm.client.messages.create(
            model=model,
            max_tokens=settings.max_tokens,
            system=system_prompt,
            tools=tools,
            messages=messages,
        )

    # ============================================================
    # 公共方法:JSON 解析 + 日志
    # ============================================================

    def _parse_json_response(self, raw_text: str) -> dict:
        """
        把 LLM 返回的 JSON 文本解析成 dict。

        为什么单独抽出来:
            Writer 和 Reviewer 都要求 LLM 输出 JSON。
            解析失败的处理逻辑一样(打印原文 + 抛错方便调试),
            这段代码不能写两遍。

        2026-07-14 加了 markdown 容错(Sprint 3 时预判的):
            切换到 Haiku 4.5 后发现小模型不完全遵守"不要 markdown 代码块"的
            Prompt 规则,会输出 "Perfect!\\n\\n```json {...} ```\\n\\n"。
            **加容错:找到第一个 { 到最后一个 } 之间的内容再解析**。
            面试话术:"我 Sprint 3 时在这个函数的注释里预判过这个问题,
                     切 Haiku 触发,加了这层容错 —— **提前预判的兑现**。"
        """
        text = raw_text.strip()

        # 容错 1:strip markdown 代码块符号 + 前后废话
        # 找到最外层 { ... } 的边界,忽略前后所有非 JSON 内容
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end > start:
            text = text[start:end + 1]

        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            self._log(f"JSON 解析失败! LLM 原文如下:")
            print("-" * 60)
            print(raw_text)
            print("-" * 60)
            raise RuntimeError(f"[{self.name}] JSON 解析失败: {e}") from e

    def _log(self, msg: str) -> None:
        """统一格式的日志输出:[agent_name] xxx"""
        print(f"[{self.name}] {msg}")
