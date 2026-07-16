"""
批量评估脚本 —— Sprint 4 Step 2。

用法:
    python batch_eval.py                    # 跑所有样品,每个 1 次
    python batch_eval.py --n-samples 3      # 每个样品跑 3 次(降低单次波动)
    python batch_eval.py --n-samples 3 --output reports/eval_after_tool_use.json

它做什么:
    1. 遍历 data/sample_products/*.json
    2. 每个样品跑 N 次 Orchestrator(完整循环)
    3. 每次结果传给 ListingJudge 打分
    4. 汇总输出:类目 × 样本次数矩阵,平均分/方差/通过率/平均轮次

面试价值:
    "作品集阶段的鲁棒性证据"—— 面试官问'你怎么知道你的系统稳定'的答案。

注意:
    一次跑 N=3 samples × 2 products,总共 6 次完整循环,可能 10-15 分钟。
    建议先 N=1 跑通,再看要不要提高采样数。
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from src.agents.orchestrator import Orchestrator
from src.evaluation.judge import ListingJudge


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch evaluation — 跑所有样品输出统计表"
    )
    parser.add_argument(
        "--n-samples",
        type=int,
        default=1,
        help="每个样品跑几次(默认 1,想降低波动可以设 3-5)",
    )
    parser.add_argument(
        "--samples-dir",
        type=Path,
        default=Path("data/sample_products"),
        help="样品目录",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="报告输出路径(默认打印到 stdout)",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=3,
        help="Orchestrator max_rounds(默认 3)",
    )
    return parser.parse_args()


def run_single_case(
    orchestrator: Orchestrator,
    judge: ListingJudge,
    product_info: dict,
    sample_idx: int,
    total_samples: int,
) -> dict:
    """
    跑一次单一样品 → 打分 → 返回一条记录。
    """
    sku = product_info.get("sku", "?")
    print(f"\n  [Sample {sample_idx}/{total_samples}] Running SKU {sku}...")

    t0 = time.time()
    result = orchestrator.run(product_info)
    duration = time.time() - t0

    print(f"  [Sample {sample_idx}/{total_samples}] 循环完成,耗时 {duration:.1f}s")
    print(f"  [Sample {sample_idx}/{total_samples}] 调 Judge 打分...")

    judge_report = judge.judge(result["final_listing"], product_info)

    return {
        "sku": sku,
        "sample_idx": sample_idx,
        "orchestrator_reason": result["reason"],
        "total_rounds": result["total_rounds"],
        "reviewer_final_score": result["final_report"]["overall_score"],
        "reviewer_passed": result["final_report"]["passed"],
        "judge_seo": judge_report.seo_score,
        "judge_user_value": judge_report.user_value_score,
        "judge_differentiation": judge_report.differentiation_score,
        "judge_compliance": judge_report.compliance_score,
        "judge_total": judge_report.total_score,
        "judge_verdict": judge_report.verdict,
        "duration_seconds": round(duration, 1),
    }


def aggregate_stats(records: list[dict]) -> dict:
    """
    从记录列表汇总统计。
    """
    if not records:
        return {}

    def stats(values: list[float]) -> dict:
        if not values:
            return {"mean": 0, "median": 0, "min": 0, "max": 0}
        return {
            "mean": round(statistics.mean(values), 1),
            "median": round(statistics.median(values), 1),
            "min": min(values),
            "max": max(values),
        }

    return {
        "n_records": len(records),
        "pass_rate": round(sum(1 for r in records if r["reviewer_passed"]) / len(records), 3),
        "avg_rounds": round(statistics.mean(r["total_rounds"] for r in records), 2),
        "reviewer_score": stats([r["reviewer_final_score"] for r in records]),
        "judge_total": stats([r["judge_total"] for r in records]),
        "judge_seo": stats([r["judge_seo"] for r in records]),
        "judge_user_value": stats([r["judge_user_value"] for r in records]),
        "judge_differentiation": stats([r["judge_differentiation"] for r in records]),
        "judge_compliance": stats([r["judge_compliance"] for r in records]),
        "avg_duration_seconds": round(statistics.mean(r["duration_seconds"] for r in records), 1),
    }


def print_summary_table(records: list[dict], group_by: str = "sku") -> None:
    """打印结果分组统计。"""
    print("\n" + "=" * 80)
    print(f"分组统计(按 {group_by})")
    print("=" * 80)

    # 分组
    groups: dict[str, list[dict]] = {}
    for r in records:
        key = r[group_by]
        groups.setdefault(key, []).append(r)

    for key, group_records in groups.items():
        stats = aggregate_stats(group_records)
        print(f"\n[{group_by}={key}]  (n={stats['n_records']})")
        print(f"  通过率:            {stats['pass_rate'] * 100:.1f}%")
        print(f"  平均轮次:          {stats['avg_rounds']} 轮")
        print(f"  平均耗时:          {stats['avg_duration_seconds']} 秒")
        print(f"  Reviewer 分数:     mean={stats['reviewer_score']['mean']}, "
              f"range=[{stats['reviewer_score']['min']}, {stats['reviewer_score']['max']}]")
        print(f"  Judge 总分:        mean={stats['judge_total']['mean']}, "
              f"range=[{stats['judge_total']['min']}, {stats['judge_total']['max']}]")
        print(f"  Judge · SEO:       mean={stats['judge_seo']['mean']}")
        print(f"  Judge · 用户价值:  mean={stats['judge_user_value']['mean']}")
        print(f"  Judge · 差异化:    mean={stats['judge_differentiation']['mean']}")
        print(f"  Judge · 合规:      mean={stats['judge_compliance']['mean']}")


def main() -> None:
    args = parse_args()

    # === 1. 加载样品 ===
    sample_paths = sorted(args.samples_dir.glob("*.json"))
    if not sample_paths:
        print(f"[错误] {args.samples_dir} 下没有 .json 样品文件")
        sys.exit(1)

    samples: list[dict] = []
    for p in sample_paths:
        with p.open("r", encoding="utf-8") as f:
            samples.append(json.load(f))

    total_runs = len(samples) * args.n_samples

    print("=" * 80)
    print(f"Batch Evaluation · {len(samples)} 个样品 × {args.n_samples} 次采样 = {total_runs} 次完整运行")
    print("=" * 80)
    print(f"最长预估:{total_runs * 90} 秒(~{total_runs * 1.5:.1f} 分钟)")

    # === 2. 初始化 orchestrator + judge(复用实例避免重复加载) ===
    orchestrator = Orchestrator(max_rounds=args.max_rounds)
    judge = ListingJudge()

    # === 3. 主循环 ===
    all_records: list[dict] = []
    for product_info in samples:
        sku = product_info.get("sku", "?")
        print(f"\n{'#' * 80}")
        print(f"# 样品: {sku} — {product_info.get('product_type', '?')}")
        print(f"{'#' * 80}")

        for i in range(1, args.n_samples + 1):
            try:
                record = run_single_case(orchestrator, judge, product_info, i, args.n_samples)
                all_records.append(record)
            except Exception as e:
                print(f"  [Sample {i}] ✗ 失败: {type(e).__name__}: {e}")

    # === 4. 汇总 + 打印 ===
    print_summary_table(all_records, group_by="sku")

    overall = aggregate_stats(all_records)
    print("\n" + "=" * 80)
    print("总体统计")
    print("=" * 80)
    print(f"  总运行次数:       {overall.get('n_records', 0)}")
    print(f"  总体通过率:       {overall.get('pass_rate', 0) * 100:.1f}%")
    print(f"  平均轮次:         {overall.get('avg_rounds', 0)}")
    print(f"  平均 Judge 总分:  {overall.get('judge_total', {}).get('mean', 0)}")

    # === 5. 可选保存 JSON 报告 ===
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "config": {
                "n_samples": args.n_samples,
                "max_rounds": args.max_rounds,
                "n_products": len(samples),
            },
            "per_sku": {
                sku: aggregate_stats([r for r in all_records if r["sku"] == sku])
                for sku in {r["sku"] for r in all_records}
            },
            "overall": overall,
            "records": all_records,
        }
        with args.output.open("w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f"\n✓ 报告已保存到: {args.output}")

    print("=" * 80)


if __name__ == "__main__":
    main()
