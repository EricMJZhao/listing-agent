"""
硬规则检查器的自测脚本 —— Step 2 完工验证用。

用法:
    python test_rules.py

它做什么:
    构造 5 个测试用例(1 个全通过 + 4 个各踩一条规则),
    确认 check_all_hard_rules() 每次都返回预期结果。

为什么用这种方式而不是 pytest:
    你还是编程新手,pytest 的装饰器和 fixture 概念会分散注意力。
    Sprint 5 之前先用"打印 → 肉眼看"的方式,直觉清楚。
    Sprint 5 上 Streamlit 前会切成 pytest。
"""

from src.evaluation.rules import check_all_hard_rules


# ============================================================
# 测试用例 1: 完全正常的 Listing —— 应该 0 个 issue
# ============================================================

VALID_LISTING = {
    "title": "Bamboo Cutting Board Large 17x12 with Juice Groove and Handles",
    "bullet_points": [
        "EXTRA THICK - Won't warp",
        "DEEP GROOVE - Catches juices",
        "REVERSIBLE - Two sides in one",
        "NATURAL BAMBOO - Eco-friendly",
        "EASY CARE - Hand wash safe",
    ],
    "product_description": "A solid bamboo cutting board built for daily use.",
    "backend_keywords": "chef gift housewarming charcuterie serving platter",
    "target_search_terms": ["bamboo board", "cutting board"],
    "reasoning": "test",
}


# ============================================================
# 测试用例 2: Title 超 200 字符 —— 应触发 title_length
# ============================================================

BAD_TITLE = {**VALID_LISTING, "title": "X" * 250}


# ============================================================
# 测试用例 3: Bullet 只有 3 条 —— 应触发 bullet_count
# ============================================================

BAD_BULLETS = {**VALID_LISTING, "bullet_points": ["A", "B", "C"]}


# ============================================================
# 测试用例 4: Backend Keywords 257 字节 —— 这就是 Sprint 0 真实踩过的 case!
# 直接从 docs/bad_cases.md 复制过来,验证规则能抓到。
# ============================================================

REAL_BAD_CASE_FROM_SPRINT_0 = {
    **VALID_LISTING,
    "backend_keywords": (
        "chef gift housewarming charcuterie serving platter meat carving "
        "veggie prep sustainable renewable no warp mineral oil seasoned "
        "dishwasher alternative countertop bread slicer thick heavy duty "
        "natural grain moisture resistant wall hanging kitchenware set flat"
    ),
}


# ============================================================
# 测试用例 5: 用了禁用词 BEST —— 应触发 banned_words
# ============================================================

BAD_BANNED_WORDS = {
    **VALID_LISTING,
    "title": "BEST Bamboo Cutting Board on Amazon",
    "bullet_points": [
        "PERFECT for kitchen use",  # 又一个禁用词
        "EXTRA THICK - Won't warp",
        "DEEP GROOVE - Catches juices",
        "REVERSIBLE - Two sides in one",
        "EASY CARE - Hand wash safe",
    ],
}


# ============================================================
# 跑测试
# ============================================================


def run_test(name: str, listing: dict, expected_rule_ids: set[str]) -> None:
    """
    参数:
        name: 用例名(打印用)
        listing: 输入的 listing
        expected_rule_ids: 期望触发的规则 id 集合,空集表示"应该全通过"
    """
    issues = check_all_hard_rules(listing)
    actual_ids = {issue.rule_id for issue in issues}

    print(f"\n--- 用例: {name} ---")
    print(f"期望触发: {expected_rule_ids or '(无)'}")
    print(f"实际触发: {actual_ids or '(无)'}")

    if actual_ids == expected_rule_ids:
        print("✓ 通过")
    else:
        print("✗ 失败!")
        print("  详细 issue 列表:")
        for i in issues:
            print(f"    - [{i.rule_id}] {i.message}")
            print(f"        fix_hint: {i.fix_hint}")

    # 无论通过还是失败,都把 issue 详情打出来方便看
    if issues:
        print(f"  规则给的 fix_hint 示例:")
        for i in issues:
            print(f"    · {i.rule_id}: {i.fix_hint[:80]}...")


if __name__ == "__main__":
    print("=" * 60)
    print("硬规则检查器 · 自测")
    print("=" * 60)

    run_test("完全正常", VALID_LISTING, set())
    run_test("Title 超 250 字符", BAD_TITLE, {"title_length"})
    run_test("Bullet 只有 3 条", BAD_BULLETS, {"bullet_count"})
    run_test(
        "Sprint 0 真实翻车 case(257 字节)",
        REAL_BAD_CASE_FROM_SPRINT_0,
        {"backend_bytes"},
    )
    run_test("用了 BEST + PERFECT", BAD_BANNED_WORDS, {"banned_words"})

    print("\n" + "=" * 60)
    print("测试结束 —— 5 个用例全部 ✓ 表示 Step 2 完工")
    print("=" * 60)
