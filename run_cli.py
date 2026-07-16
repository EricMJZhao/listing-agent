"""
命令行入口 —— Sprint 2 收官版本,跑 Orchestrator 完整循环。

用法:
    python run_cli.py <商品 JSON 路径> [--rounds N]

示例:
    python run_cli.py data/sample_products/product_1.json
    python run_cli.py data/sample_products/product_2.json --rounds 2

它做什么:
    1. 读一个商品 JSON
    2. 跑 Orchestrator(Writer + Reviewer 循环,最多 max_rounds 轮)
    3. 打印循环轨迹表 + 每轮演化对比 + 最终 Listing + 交付摘要

对比 Sprint 0 版本:
    Sprint 0 只调用 WriterAgent 一次,输出单份 Listing。
    Sprint 2 收官版调 Orchestrator,能显示 Multi-Agent 收敛过程 ——
    面试演示时"能亲眼看到 Agent 之间协作"。

面试话术:
    "命令签名跟 Sprint 0 保持一致(向后兼容),但内部从单 Agent 升级为
     Multi-Agent 编排。用户体验:同一条命令,输出信息量提升 3 倍,
     并且能看到收敛过程 —— 这是可演化系统的价值。"

Sprint 5 会把这个 CLI 换成 Streamlit Web UI,那时 reporting 模块的
函数会被替换成 UI 组件,run_cli.py 的调用点无感。
"""

import argparse
import json
import sys
from pathlib import Path

from src.agents.orchestrator import Orchestrator
from src.reporting import (
    print_evolution_diff,
    print_final_listing,
    print_orchestrator_summary,
    print_rounds_table,
)


def parse_args() -> argparse.Namespace:
    """
    解析命令行参数。

    为什么用 argparse 而不是 sys.argv:
        1. 自动生成 --help 帮助
        2. 类型转换、默认值、可选参数都是内置
        3. 面试点:"我用 argparse 是标准库习惯,不引入 click 依赖"
    """
    parser = argparse.ArgumentParser(
        description="Listing Agent — Multi-Agent 闭环 Listing 生成"
    )
    parser.add_argument(
        "product_json",
        type=Path,
        help="商品 JSON 文件路径,例:data/sample_products/product_1.json",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=3,
        help="最大循环轮次(默认 3),面试演示时可以调小强制看多轮",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # === 1. 校验输入 ===
    if not args.product_json.exists():
        print(f"[错误] 找不到商品文件: {args.product_json}")
        sys.exit(1)

    with args.product_json.open("r", encoding="utf-8") as f:
        product_info = json.load(f)

    # === 2. 打印任务概览 ===
    print("=" * 70)
    print(f"Listing Agent · SKU {product_info.get('sku', '?')}")
    print("=" * 70)
    print(f"品类:       {product_info.get('product_type', '?')}")
    print(f"目标市场:   {product_info.get('target_marketplace', '?')}")
    print(f"价格定位:   {product_info.get('price_positioning', '?')}")
    print(f"max_rounds: {args.rounds}")

    # === 3. 跑 Orchestrator ===
    orchestrator = Orchestrator(max_rounds=args.rounds)
    result = orchestrator.run(product_info)

    # === 4. 打印结果 ===
    print_rounds_table(result["rounds"])
    print_evolution_diff(result["rounds"])
    print_final_listing(result["final_listing"])
    print_orchestrator_summary(result)


if __name__ == "__main__":
    main()
