"""
ReviewerAgent 端到端测试 —— Step 3 完工验证用。

用法:
    python test_reviewer.py

它做什么:
    1. 直接用 Sprint 0 真实生成的 Listing(带 257 字节 backend keywords 的坏 case)
    2. 跑 ReviewerAgent 审核
    3. 打印完整体检报告

预期看到:
    - 硬规则触发 backend_bytes(源自 Sprint 0 真实翻车)
    - 软规则拿到一个 0-100 的分数
    - passed = False(因为硬规则一票否决)

为什么不跑完整 Writer→Reviewer 链路:
    - 想省 Writer 那次 Opus 调用(~¥0.3)
    - 想验证 Reviewer 能吃"人为构造的坏 case",不依赖 Writer 的随机输出
    - Step 4 的 Orchestrator 会跑完整链路
"""

import json

from src.agents.reviewer_agent import ReviewerAgent


# ============================================================
# 输入 1: Sprint 0 真实生成的 Listing(product_1 竹制切菜板)
# 直接从当时的输出复制过来 —— 这就是我们要"审"的初稿
# 关键坑点:backend_keywords 是 257 字节(超 8 字节)
# ============================================================

SPRINT_0_REAL_LISTING = {
    "title": (
        "Bamboo Cutting Board Large 17x12 - Organic Wood Chopping Board for "
        "Kitchen with Juice Groove & Side Handles, Reversible Thick Butcher "
        "Block, Eco-Friendly Cutting Boards with Hanging Rope"
    ),
    "bullet_points": [
        "EXTRA THICK, WON'T WARP - You get a full 0.8-inch thick board, "
        "versus the flimsy 0.5-inch boards most sellers offer. This extra "
        "density resists warping, splitting, and cracking wash after wash.",
        "DEEP JUICE GROOVE KEEPS COUNTERS CLEAN - The channel routed around "
        "the edge holds up to 3 fluid ounces, catching juices from roast "
        "beef, watermelon, and tomatoes before they spill over.",
        "REVERSIBLE DUAL-SIDE DESIGN - Use one side with the juice groove "
        "for meats and juicy produce, then flip to the flat side for bread, "
        "cheese, and everyday chopping.",
        "NATURALLY ANTIBACTERIAL & EASY CARE - Made from 100% organic bamboo "
        "that is naturally mold- and moisture-resistant, this board is "
        "pre-seasoned with food-grade mineral oil.",
        "SPACE-SAVING WITH HANGING ROPE - Measuring 17 x 12 x 0.8 inches at "
        "2.3 pounds, this board gives you plenty of prep space yet stays "
        "light enough to handle.",
    ],
    "product_description": (
        "There is a certain satisfaction in reaching for a cutting board "
        "that feels solid the moment your knife touches it. That is exactly "
        "what you get here. Whether you are dicing onions for a weeknight "
        "dinner, breaking down a whole chicken, or arranging cheeses and "
        "fruit for friends, this bamboo board becomes the workhorse of "
        "your kitchen."
    ),
    # 关键坑点:257 字节,超 8 字节
    "backend_keywords": (
        "chef gift housewarming charcuterie serving platter meat carving "
        "veggie prep sustainable renewable no warp mineral oil seasoned "
        "dishwasher alternative countertop bread slicer thick heavy duty "
        "natural grain moisture resistant wall hanging kitchenware set flat"
    ),
    "target_search_terms": [
        "bamboo cutting board large",
        "wood cutting board with juice groove",
        "large chopping board with handles",
    ],
    "reasoning": "Front-loaded title with core keywords, bullets benefit-first.",
}


# ============================================================
# 输入 2: 对应的商品原始 JSON(Reviewer 用它对照 seed keywords 和 differentiation)
# 从 data/sample_products/product_1.json 简化过来
# ============================================================

PRODUCT_1_INFO = {
    "sku": "BAM-CB-001",
    "product_type": "Bamboo Cutting Board",
    "target_marketplace": "amazon.com",
    "attributes": {
        "material": "100% organic bamboo",
        "dimensions_inches": "17 x 12 x 0.8",
        "features": [
            "juice groove around perimeter",
            "reversible design",
            "side handles",
            "pre-seasoned",
        ],
    },
    "differentiation": [
        "0.8-inch thick vs. competitors' 0.5 inch",
        "Juice groove holds 3 fluid ounces",
        "Includes hanging rope",
    ],
    "keywords_seed": [
        "bamboo cutting board",
        "wood cutting board",
        "large cutting board",
        "kitchen chopping board",
    ],
}


# ============================================================
# 跑测试
# ============================================================


def pretty_print_report(report: dict) -> None:
    """漂亮打印体检报告,面试演示时也这么用。"""
    print("\n" + "=" * 70)
    print(f"体检报告 — passed: {report['passed']}, "
          f"score: {report['overall_score']}/100")
    print("=" * 70)
    print(f"\n[总结] {report['summary']}\n")

    if not report["issues"]:
        print("[Issues] 无 ✓")
        return

    # 按 source 分组显示
    hard = [i for i in report["issues"] if i["source"] == "hard"]
    soft = [i for i in report["issues"] if i["source"] == "soft"]

    print(f"[硬规则违规] {len(hard)} 条")
    for i in hard:
        print(f"  · [{i['rule_id']}] {i['message']}")
        print(f"      fix_hint: {i['fix_hint']}")

    print(f"\n[软规则问题] {len(soft)} 条")
    for i in soft:
        sev = i.get("severity", "?")
        print(f"  · [{i['rule_id']}] ({sev}) {i['message']}")
        print(f"      fix_hint: {i.get('fix_hint', '')}")


if __name__ == "__main__":
    print("=" * 70)
    print("ReviewerAgent · 端到端测试")
    print("=" * 70)
    print("\n输入:Sprint 0 真实生成的 product_1 Listing(有 257 字节 backend 违规)")
    print("期望:硬规则抓到 backend_bytes,软规则给出 0-100 分数\n")

    reviewer = ReviewerAgent()
    report = reviewer.run({
        "listing": SPRINT_0_REAL_LISTING,
        "product_info": PRODUCT_1_INFO,
    })

    pretty_print_report(report)

    print("\n" + "=" * 70)
    print("完整 JSON 报告(Sprint 4 的 Orchestrator 会消费这个):")
    print("=" * 70)
    print(json.dumps(report, ensure_ascii=False, indent=2))
