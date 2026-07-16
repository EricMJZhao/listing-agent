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
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

import streamlit as st

# Streamlit Cloud 兼容:显式把 st.secrets 同步到 os.environ。
# 为什么显式做:Streamlit 官方文档说 secrets 会自动 mirror 到 os.environ,
# 但实测(2026-07)Streamlit Cloud 部署环境下,业务代码顶层 os.getenv
# 有 timing 问题读不到。显式一次搞定,行为可预测。
# setdefault 而不是直接赋值:尊重外层已设的环境变量(比如本地 .env)。
try:
    for _k, _v in dict(st.secrets).items():
        os.environ.setdefault(_k, str(_v))
except Exception:
    pass  # 本地开发无 .streamlit/secrets.toml 时 st.secrets 会 raise,忽略

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
st.title("🤖 亚马逊 Listing 生成 Agent")
st.markdown(
    "**针对 Amazon.com · Home & Kitchen > Kitchen & Dining 类目** — "
    "输入商品属性,输出可直接发布的完整 Listing(Title / 5 Bullets / Backend Keywords / Search Terms)"
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

    sample_options = []
    for _f in sample_files:
        with _f.open("r", encoding="utf-8") as _fp:
            _d = json.load(_fp)
        _category_leaf = _d["category_path"].split(">")[-1].strip()
        sample_options.append({
            "file": _f,
            "label": f"{_d['product_type']} · Amazon {_category_leaf}",
            "data": _d,
            "category_path": _d["category_path"],
        })

    input_mode = st.radio(
        "输入方式",
        ["选择店内商品", "填表单生成", "粘贴自定义 JSON"],
        index=0,
    )

    product_info: dict | None = None

    if input_mode == "选择店内商品":
        _labels = [s["label"] for s in sample_options]
        selected_idx = st.selectbox(
            "选择商品",
            range(len(sample_options)),
            format_func=lambda i: _labels[i],
            index=0,
        )
        selected_sample = sample_options[selected_idx]
        product_info = selected_sample["data"]
        st.caption(f"📍 亚马逊类目路径:{selected_sample['category_path']}")
        with st.expander("查看商品 JSON"):
            st.json(product_info)
    elif input_mode == "填表单生成":
        st.caption("填几个字段,自动组装成商品 JSON")

        _product_type = st.text_input(
            "产品类型 *",
            placeholder="Kitchen Towel",
            help="用英文,越具体越好",
        )
        _category_leaf = st.text_input(
            "亚马逊类目(最后一级)*",
            placeholder="Kitchen Towels",
            help="会自动补前缀 Home & Kitchen > Kitchen & Dining >",
        )
        _differentiation = st.text_area(
            "差异化亮点 *(每行一条)",
            placeholder="Thicker than competitors\nSet of 6 vs. their 4\nMachine washable",
            height=100,
        )

        with st.expander("补充字段(可选,填了效果更好)"):
            _material = st.text_input("材质", placeholder="100% cotton")
            _dimensions = st.text_input("尺寸", placeholder="16 x 12 x 0.8 inches")
            _weight = st.text_input("重量", placeholder="2.3 lbs")
            _color = st.text_input("颜色", placeholder="natural / white / black")
            _package_contents = st.text_area(
                "包装内容(每行一条)",
                placeholder="1x main product\n1x hanging rope",
                height=70,
            )
            _features = st.text_area(
                "核心特性(每行一条)",
                placeholder="Absorbent\nQuick-dry\nDishwasher safe",
                height=80,
            )
            _target_audience = st.text_input(
                "目标客户",
                placeholder="home cooks aged 25-45",
            )
            _price_positioning = st.text_input(
                "价格定位",
                placeholder="$19.99, competitors $12-25",
            )
            _keywords_seed = st.text_input(
                "关键词种子(逗号分隔)",
                placeholder="kitchen towel, dish towel, tea towel",
            )

        with st.expander("自定义属性(想加什么加什么)"):
            st.caption("每行填一条,格式:属性名 = 值。可以填任何字段,比如认证、保修、温度范围等。")
            _custom_attrs = st.text_area(
                "自定义属性",
                placeholder="warranty = 2 years\ncertification = FDA-approved\ntemperature_range_f = -40 to 480",
                height=100,
                label_visibility="collapsed",
            )

        if _product_type and _category_leaf and _differentiation.strip():
            _attrs: dict = {"material": _material or "unspecified"}
            if _dimensions:
                _attrs["dimensions"] = _dimensions
            if _weight:
                _attrs["weight"] = _weight
            if _color:
                _attrs["color"] = _color
            if _package_contents:
                _attrs["package_contents"] = [_l.strip() for _l in _package_contents.split("\n") if _l.strip()]
            if _features:
                _attrs["features"] = [_l.strip() for _l in _features.split("\n") if _l.strip()]
            if _custom_attrs:
                for _line in _custom_attrs.split("\n"):
                    if "=" in _line:
                        _k, _v = _line.split("=", 1)
                        _k = _k.strip()
                        if _k:
                            _attrs[_k] = _v.strip()

            product_info = {
                "sku": f"CUSTOM-{_product_type.upper().replace(' ', '-')[:12]}-001",
                "category_path": f"Home & Kitchen > Kitchen & Dining > {_category_leaf}",
                "product_type": _product_type,
                "target_marketplace": "amazon.com",
                "target_language": "en-US",
                "attributes": _attrs,
                "differentiation": [_l.strip() for _l in _differentiation.split("\n") if _l.strip()],
                "target_audience": _target_audience or "general consumers",
                "price_positioning": _price_positioning or "mid-market",
                "keywords_seed": [_k.strip() for _k in _keywords_seed.split(",") if _k.strip()] if _keywords_seed else [],
            }
            with st.expander("查看自动生成的商品 JSON"):
                st.json(product_info)
        else:
            st.caption("💡 填完必填 * 字段就自动组装 JSON")
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
            st.line_chart({"软规则分": scores})

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
    st.warning("请先选择商品或填完表单必填字段")

else:
    st.markdown("---")
    st.info("👈 从左侧选一个商品,点 **🚀 生成 Listing** 开始。")

# ============================================================
# 底部
# ============================================================
