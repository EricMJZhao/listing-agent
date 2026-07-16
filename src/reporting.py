"""
共享打印函数 —— CLI 和测试脚本都用它。

为什么单独一个文件:
    run_cli.py 和 test_orchestrator.py 都要漂亮打印
    "循环轨迹表" + "最终 Listing"。抽出来避免重复。

    Sprint 5 上 Streamlit UI 时,这些函数会变成 UI 组件
    —— 提前抽出,那时只替换实现,调用点无感。

面试话术:
    "我把展示层从业务逻辑里剥离出来,放在独立的 reporting 模块。
     现在是 print 到终端,未来会变成 Streamlit 的 st.table / st.json。
     **展示层和业务层解耦,是所有可演化系统的基础**。"
"""


def print_rounds_table(rounds: list[dict]) -> None:
    """
    打印每轮分数演化,面试演示的核心画面。

    参数:
        rounds: Orchestrator 返回的 rounds 列表,每项含 {round, passed, score, report}
    """
    print("\n" + "=" * 70)
    print("循环轨迹(Multi-Agent 收敛过程)")
    print("=" * 70)
    print(f"{'轮次':<8}{'passed':<10}{'软规则分':<12}{'硬 issue':<12}{'软 issue'}")
    print("-" * 70)

    for r in rounds:
        hard_count = sum(1 for i in r["report"]["issues"] if i["source"] == "hard")
        soft_count = sum(1 for i in r["report"]["issues"] if i["source"] == "soft")
        passed_mark = "✓ 是" if r["passed"] else "✗ 否"
        print(
            f"Round {r['round']:<3}"
            f"{passed_mark:<10}"
            f"{r['score']:<12}"
            f"{hard_count:<12}"
            f"{soft_count}"
        )


def print_final_listing(listing: dict) -> None:
    """
    打印最终交付的 Listing,格式为便于面试演示的分区结构。
    """
    print("\n" + "=" * 70)
    print("最终交付 Listing")
    print("=" * 70)

    print("\n[Title]")
    print(f"  {listing['title']}")
    print(f"  字符数: {len(listing['title'])} / 200")

    print("\n[Bullet Points]")
    for i, bullet in enumerate(listing["bullet_points"], 1):
        print(f"  {i}. {bullet}")

    print("\n[Product Description]")
    print(f"  {listing['product_description']}")

    print("\n[Backend Keywords]")
    print(f"  {listing['backend_keywords']}")
    print(f"  字节数: {len(listing['backend_keywords'].encode('utf-8'))} / 249")

    print("\n[Target Search Terms]")
    for term in listing["target_search_terms"]:
        print(f"  - {term}")

    if listing.get("reasoning"):
        print("\n[Writer 的推理]")
        print(f"  {listing['reasoning']}")


def print_orchestrator_summary(result: dict) -> None:
    """
    打印 Orchestrator 结果的一句话摘要 —— CLI 和测试脚本收尾都用。

    参数:
        result: Orchestrator.run() 返回的完整 dict
    """
    print("\n" + "=" * 70)
    print("交付摘要")
    print("=" * 70)
    print(f"结束原因: {result['reason']}")
    print(f"总轮次:   {result['total_rounds']}")
    print(f"最终得分: {result['final_report']['overall_score']}/100")
    print(f"是否通过: {'✓' if result['final_report']['passed'] else '✗'}")

    # 未解决问题清单(如果最终仍未通过 = max_rounds 到顶)
    if not result["final_report"]["passed"]:
        print("\n⚠️  最终仍有未解决问题:")
        for issue in result["final_report"]["issues"]:
            print(f"  · [{issue['source']}][{issue['rule_id']}] {issue['message']}")

    print("=" * 70)


def print_evolution_diff(rounds: list[dict]) -> None:
    """
    打印每轮 Listing 的关键指标演化(字符数、字节数、分数),
    让面试官清楚看到"每一轮改了什么"。

    Round 2 之后才有意义,只打变化的字段。
    """
    if len(rounds) < 2:
        return

    print("\n" + "=" * 70)
    print("演化对比(轮次 → 轮次,只显示变化的指标)")
    print("=" * 70)
    print(f"{'指标':<25}{'Round 1':<15}{'→':<5}{'Round N'}")
    print("-" * 70)

    first = rounds[0]["listing"]
    last = rounds[-1]["listing"]

    metrics = [
        ("Title 字符数", len(first["title"]), len(last["title"])),
        (
            "Backend 字节数",
            len(first["backend_keywords"].encode("utf-8")),
            len(last["backend_keywords"].encode("utf-8")),
        ),
        ("Bullet 数量", len(first["bullet_points"]), len(last["bullet_points"])),
        (
            "软规则分数",
            rounds[0]["score"],
            rounds[-1]["score"],
        ),
    ]

    for name, before, after in metrics:
        arrow = "→" if before != after else "="
        mark = "" if before == after else ("↑" if after > before else "↓")
        print(f"{name:<25}{before:<15}{arrow:<5}{after} {mark}")
