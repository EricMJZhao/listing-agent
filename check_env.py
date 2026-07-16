"""
最小环境检查脚本 —— 独立于业务代码,只回答一个问题:
    "我的 API Key 和 Base URL 到底能不能通?"

用法:
    python check_env.py

它会按顺序做 3 件事,任何一步失败都会明确告诉你哪里出问题:
    1. 检查 .env 文件是否被正确读取
    2. 检查环境变量里 API Key / Base URL 的值
    3. 真的发一次最小请求,看能不能拿到回复
"""

import os
import sys

# === Step 1: 加载 .env ===
try:
    from dotenv import load_dotenv
except ImportError:
    print("[FAIL] 没装 python-dotenv,先跑: pip install -r requirements.txt")
    sys.exit(1)

load_dotenv(override=True)  # override=True 让 .env 覆盖 shell 里已导出的旧变量
print("[Step 1] .env 已加载 ✓")

# === Step 2: 检查环境变量 ===
api_key = os.getenv("ANTHROPIC_API_KEY", "")
base_url = os.getenv("ANTHROPIC_BASE_URL", "")
model = os.getenv("LISTING_AGENT_MODEL", "claude-opus-4-8")

if not api_key:
    print("[FAIL] ANTHROPIC_API_KEY 是空的,检查 .env 文件")
    sys.exit(1)

# 只显示前后几位,不打印完整 key 到屏幕
masked = f"{api_key[:8]}...{api_key[-4:]}" if len(api_key) > 12 else "***"
print(f"[Step 2] API Key 已读到: {masked}")
print(f"         Base URL: {base_url or '(空 = 走 Anthropic 官方)'}")
print(f"         Model:    {model}")

# === Step 3: 发一次真实请求 ===
try:
    from anthropic import Anthropic
except ImportError:
    print("[FAIL] 没装 anthropic SDK,先跑: pip install -r requirements.txt")
    sys.exit(1)

print("\n[Step 3] 尝试发一次最小请求...")

if base_url:
    client = Anthropic(api_key=api_key, base_url=base_url)
else:
    client = Anthropic(api_key=api_key)

try:
    resp = client.messages.create(
        model=model,
        max_tokens=32,
        messages=[{"role": "user", "content": "回一个 pong"}],
    )
    reply = resp.content[0].text
    print(f"[Step 3] 连通成功 ✓  Claude 回复: {reply}")
    print("\n[结论] Key 配置 OK,可以跑 run_cli.py 了")
except Exception as e:
    import traceback
    print(f"[FAIL] 请求失败: {type(e).__name__}: {e}")
    print("\n=== 详细错误堆栈(诊断用)===")
    traceback.print_exc()
    print("=" * 40)
    # 如果错误链里有原始异常(比如 httpx 层的错误),打印出来
    if e.__cause__:
        print(f"\n根本原因: {type(e.__cause__).__name__}: {e.__cause__}")
    print("\n常见原因:")
    print("  - 401/403: Key 无效或过期")
    print("  - 404 model not found: model 名字不对(问下中转平台支持哪些)")
    print("  - Connection error: base_url 不对或网络不通(代理挂了/瞬时抖动)")
    sys.exit(1)
