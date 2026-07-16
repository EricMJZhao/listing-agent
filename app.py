"""
Streamlit UI —— Sprint 5 演示界面。

用法:
    streamlit run app.py

打开浏览器 http://localhost:8501,面试官/用户可以:
    1. 选一个样品 或 上传自己的商品 JSON
    2. 点"生成 Listing" → 看 Multi-Agent 循环实时打印
    3. 看最终 Listing 分区展示 + 循环轨迹图表

面试价值:
    - **面试官可以远程访问**(部署后)—— 让面试官不需要装 Python 就能试
    - **可视化循环轨迹** —— 比 CLI 输出更直观
    - **架构图 + 技术栈标签** —— 面试官第一眼就看到你做了什么

关键设计:
    1. **展示层完全独立于业务层** —— app.py 只调 Orchestrator,不含业务逻辑
    2. **日志捕获 + 实时打印** —— 通过 StringIO 捕获 print 输出,st.expander 展示
    3. **一键复现** —— 侧栏保留最近 3 次运行结果,方便对比
"""

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import streamlit as st

from src.agents.orchestrator import Orchestrator


# ============================================================
# 页面配置(必须放最前)
# ============================================================
st.set_page_config(
    page_title="Listing Agent · 跨境电商 Multi-Agent Copilot",
    page_icon="🤖",
    layout="wide",
)


# ============================================================
# 顶部标题 + 技术栈标签
# ============================================================
st.title("🤖 Listing Agent")
st.markdown(
    "**跨境电商 Multi-Agent Copilot** — "
    "Writer + Reviewer + Orchestrator 闭环 · RAG · Tool Use · 自研 Agent Loop"
)

# 技术栈标签(用 st.badge 风格显示)
st.markdown(
    """
    <div style='margin: 10px 0;'>
        <span style='background:#FF6B6B; color:white; padding:4px 10px; border-radius:12px; margin:2px; font-size:12px;'>Anthropic Claude</span>
        <span style='background:#4ECDC4; color:white; padding:4px 10px; border-radius:12px; margin:2px; font-size:12px;'>Multi-Agent</span>
        <span style='background:#45B7D1; color:white; padding:4px 10px; border-radius:12px; margin:2px; font-size:12px;'>Tool Use</span>
        <span style='background:#96CEB4; color:white; padding:4px 10px; border-radius:12px; margin:2px; font-size:12px;'>RAG (BM25)</span>
        <span style='background:#FFA07A; color:white; padding:4px 10px; border-radius:12px; margin:2px; font-size:12px;'>Graceful Fallback</span>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 侧栏:样品选择 + 参数
# ============================================================
with st.sidebar:
    st.header("⚙️ 配置")

    # === 样品选择 ===
    samples_dir = Path("data/sample_products")
    sample_files = sorted(samples_dir.glob("*.json"))

    sample_names = [f.stem for f in sample_files]

    input_mode = st.radio(
        "输入方式",
        ["选择内置样品", "粘贴自定义 JSON"],
        index=0,
    )

    product_info: dict | None = None

    if input_mode == "选择内置样品":
        selected = st.selectbox("样品", sample_names, index=0)
        selected_path = samples_dir / f"{selected}.json"
        with selected_path.open("r", encoding="utf-8") as f:
            product_info = json.load(f)
        with st.expander("查看商品 JSON"):
            st.json(product_info)
    else:
        custom_json_str = st.text_area(
            "粘贴商品 JSON",
            height=300,
            placeholder='{"sku": "...", "product_type": "...", ...}',
        )
        if custom_json_str.strip():
            try:
                product_info = json.loads(custom_json_str)
            except json.JSONDecodeError as e:
                st.error(f"JSON 解析失败: {e}")

    # === 参数 ===
    st.subheader("Orchestrator 参数")
    max_rounds = st.slider("max_rounds(最多几轮循环)", 1, 5, 3)
    st.caption("面试演示时把 max_rounds 调 1 可以强制看 fallback 场景")

    # === 运行按钮 ===
    run_button = st.button("🚀 生成 Listing", type="primary", use_container_width=True)


# ============================================================
# 主区:运行结果
# ============================================================
if run_button and product_info is not None:
    st.subheader(f"生成中 · SKU {product_info.get('sku', '?')}")

    # 捕获 print 输出到内存
    log_buffer = io.StringIO()

    with st.spinner("Multi-Agent 循环运行中(可能 1-3 分钟)..."):
        try:
            orchestrator = Orchestrator(max_rounds=max_rounds)
            with redirect_stdout(log_buffer):
                result = orchestrator.run(product_info)
            success = True
        except Exception as e:
            st.error(f"运行失败: {type(e).__name__}: {e}")
            success = False
            result = None

    if success and result is not None:
        # === 顶部摘要卡片 ===
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("结束原因", result["reason"])
        col2.metric("总轮次", result["total_rounds"])
        col3.metric("最终得分", f"{result['final_report']['overall_score']}/100")
        col4.metric("是否通过", "✓" if result["final_report"]["passed"] else "✗")

        # === 循环轨迹表 ===
        st.subheader("📊 循环轨迹(Multi-Agent 收敛过程)")
        trajectory_data = []
        for r in result["rounds"]:
            hard = sum(1 for i in r["report"]["issues"] if i["source"] == "hard")
            soft = sum(1 for i in r["report"]["issues"] if i["source"] == "soft")
            trajectory_data.append({
                "轮次": f"Round {r['round']}",
                "passed": "✓" if r["passed"] else "✗",
                "软规则分": r["score"],
                "硬 issue": hard,
                "软 issue": soft,
            })
        st.table(trajectory_data)

        # === 分数变化折线图 ===
        if len(result["rounds"]) > 1:
            st.subheader("📈 分数演化")
            scores = [r["score"] for r in result["rounds"]]
            st.line_chart(
                {"软规则分": scores},
                y_axis_label="分数",
                x_axis_label="轮次",
            )

        # === 最终 Listing 分区展示 ===
        st.subheader("✨ 最终交付 Listing")
        listing = result["final_listing"]

        st.markdown(f"### Title")
        st.info(listing.get("title", ""))
        st.caption(f"字符数: {len(listing.get('title', ''))} / 200")

        st.markdown(f"### Bullet Points")
        for i, bullet in enumerate(listing.get("bullet_points", []), 1):
            st.markdown(f"**{i}.** {bullet}")

        st.markdown(f"### Product Description")
        st.write(listing.get("product_description", ""))

        st.markdown(f"### Backend Keywords")
        st.code(listing.get("backend_keywords", ""), language=None)
        byte_len = len(listing.get("backend_keywords", "").encode("utf-8"))
        st.caption(f"字节数: {byte_len} / 249 {'⚠️ 超限' if byte_len > 249 else '✓'}")

        st.markdown(f"### Target Search Terms")
        for term in listing.get("target_search_terms", []):
            st.markdown(f"- {term}")

        if listing.get("reasoning"):
            with st.expander("💡 Writer 的推理(展开看 Agent 决策链)"):
                st.write(listing["reasoning"])

        # === 完整日志(可折叠)===
        with st.expander("🔍 完整运行日志(Agent Loop / RAG / Reviewer 每一步)"):
            st.code(log_buffer.getvalue(), language=None)

        # === 每轮的完整 Listing + Issues(可折叠)===
        with st.expander(f"📚 每轮完整数据(共 {result['total_rounds']} 轮)"):
            for r in result["rounds"]:
                st.markdown(f"#### Round {r['round']}  ·  score={r['score']}  ·  passed={r['passed']}")
                if r["report"]["issues"]:
                    st.markdown("**Issues**")
                    for issue in r["report"]["issues"]:
                        source_emoji = "🔴" if issue["source"] == "hard" else "🟡"
                        st.markdown(
                            f"{source_emoji} `[{issue['rule_id']}]` {issue['message']}"
                        )
                        st.caption(f"→ fix_hint: {issue.get('fix_hint', '')}")
                with st.expander(f"Round {r['round']} 的 Listing JSON"):
                    st.json(r["listing"])

elif run_button and product_info is None:
    st.warning("请先选择样品或粘贴合法 JSON")

else:
    # 未点运行时,显示项目介绍
    st.markdown("---")
    st.markdown(
        """
        ### 👋 欢迎

        这是一个跨境电商 Listing 生成 Agent 的演示。
        **在左侧选一个样品,点"生成 Listing"** 即可看到 Multi-Agent 循环工作。

        ### 🎯 项目特色

        - **Multi-Agent 闭环**:Writer 写、Reviewer 审、Orchestrator 循环协调
        - **自研 Agent Loop**:不用 LangChain,手写 `stop_reason` 状态机
        - **Tool Use**:Writer 主动调 `search_keyword_volume` / `check_text_bytes` 决策
        - **RAG (BM25)**:类目关键词库 + 竞品 Title,Writer 有据可依写作
        - **Graceful Degradation**:model fallback + RAG fallback + 择优输出,三处贯穿

        ### 📚 技术文档

        - `docs/DEMO.md` — 面试演示脚本(10 部分完整)
        - `docs/DESIGN.md` — 架构设计
        - `docs/bad_cases.md` — 真实翻车 case 记录

        ### 🔧 命令行也可用

        ```bash
        python run_cli.py data/sample_products/product_1.json
        python batch_eval.py --n-samples 3
        ```
        """
    )

# ============================================================
# 底部
# ============================================================
st.markdown("---")
st.caption(
    "Made by Eric · 前阿里国际站销售(8 年)+ AI 应用开发者 · "
    "Python · Anthropic Claude · 自研 Multi-Agent 编排 · 2026-07"
)
