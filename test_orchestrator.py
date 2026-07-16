"""
Orchestrator 端到端测试 —— Step 4 完工验证 + 后续回归测试用。

用法:
    python test_orchestrator.py

跟 run_cli.py 的区别:
    run_cli.py 是"用户视角"入口(接受任何商品 JSON、支持 --rounds 参数)。
    test_orchestrator.py 是"开发者视角"回归测试(锁定 product_1、锁定 max_rounds=3)。

    两者共用 src/reporting.py 里的打印函数(DRY 原则)。

Step 5 之后:
    这个脚本主要用于回归 —— 改了 Prompt、改了 Reviewer 规则后,
    跑一次确认循环还能收敛。
"""

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


def main() -> None:
    product_path = Path("data/sample_products/product_1.json")
    if not product_path.exists():
        print(f"[错误] 找不到 {product_path}")
        sys.exit(1)

    with product_path.open("r", encoding="utf-8") as f:
        product_info = json.load(f)

    print("=" * 70)
    print(f"Orchestrator 回归测试 · SKU {product_info['sku']}")
    print("=" * 70)

    orchestrator = Orchestrator(max_rounds=3)
    result = orchestrator.run(product_info)

    print_rounds_table(result["rounds"])
    print_evolution_diff(result["rounds"])
    print_final_listing(result["final_listing"])
    print_orchestrator_summary(result)


if __name__ == "__main__":
    main()
