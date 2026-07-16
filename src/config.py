"""
全局配置 —— 所有可调参数的中心。

为什么单独一个 config.py：
    Prompt、模型名、温度这些参数会反复调，
    把它们集中在一个文件里，改一处所有地方生效，
    不用在业务代码里到处找 "model=..." 字符串。
    这是一个"工程习惯"，面试官会看你有没有。
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

# 启动时从 .env 文件加载环境变量到 os.environ
# override=True 让 .env 优先于 shell 已导出的环境变量
# 为什么显式 override:
#   开发时容易在 shell export 过旧值(比如切换公司中转 vs 云 provider 时),
#   如果 .env 不能覆盖 shell,配置改了没生效,是 Multi-Agent 项目最常见的隐蔽 bug。
#   显式 override=True 让 .env 是唯一 source of truth,避免"改了没生效"的困惑。
#   生产环境用 Streamlit Cloud secrets 或 systemd env,没有 .env 文件,不受影响。
load_dotenv(override=True)


@dataclass
class Settings:
    """
    使用 dataclass 而不是散落的常量：
        - 类型提示更清楚
        - 未来加参数不用改到处
        - IDE 补全体验好
    """

    # === 模型选择 ===
    # 主生成模型：claude-opus-4-8 是当前最强（1M context, 2026年基准）
    # 想省钱可以换成 claude-sonnet-5（价格 1/5 但质量降一档）
    # 或 claude-haiku-4-5（1/15 价格，快但质量差一档）
    #
    # 为什么允许通过环境变量覆盖：
    #     开发时用便宜的 sonnet，面试演示时切成 opus，不改代码
    model_main: str = os.getenv("LISTING_AGENT_MODEL", "claude-opus-4-8")

    # 评估模型（Sprint 4 会用到）：
    # 打分类任务用便宜快的 haiku 即可
    model_judge: str = os.getenv("LISTING_AGENT_JUDGE_MODEL", "claude-haiku-4-5")

    # === 生成参数 ===
    # max_tokens: 单次响应最多多少 token
    # Listing 通常一份不超过 3000 token，给 8000 留缓冲
    max_tokens: int = 8000

    # === API 接入 ===
    # API Key —— 不硬编码在代码里，从环境变量读
    api_key: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Base URL —— 如果公司有自己的 Anthropic 兼容中转服务，从这里改
    # 官方直连用户：留空即可（SDK 默认走 https://api.anthropic.com）
    # 中转服务用户：在 .env 里加 ANTHROPIC_BASE_URL=https://...
    base_url: str = os.getenv("ANTHROPIC_BASE_URL", "")

    def validate(self) -> None:
        """启动前校验：API Key 有没有配。"""
        if not self.api_key:
            raise ValueError(
                "\n[配置错误] ANTHROPIC_API_KEY 没有设置。\n"
                "请检查 .env 文件是否存在，里面是否有 ANTHROPIC_API_KEY=...\n"
                "官方 Key 去 https://console.anthropic.com/ 拿；\n"
                "公司中转服务的 Key 问你们内部平台。"
            )


# 全局单例：其他模块直接 from src.config import settings
settings = Settings()
