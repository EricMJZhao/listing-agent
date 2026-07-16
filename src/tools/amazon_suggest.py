"""
Amazon 搜索建议采集器 v0.3

v0.1: 单次调用一个 prefix,拿 10 条补全
v0.2: BFS 递归扩展,一个种子词滚出几百长尾词
v0.2.5: 多种子批量采集(硬编码 seeds)
v0.3: YAML 类目化配置(seeds + alias 配置驱动) <-- 你在这
v0.4: 包装成 Function Calling tool 接入 Agent Loop
"""

from __future__ import annotations

import argparse
import json
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

AMAZON_SUGGEST_URL = "https://completion.amazon.com/api/2017/suggestions"

MARKETPLACE_US = "ATVPDKIKX0DER"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
}


def fetch_suggestions(prefix: str, alias: str = "aps", limit: int = 11) -> list[str]:
    """v0.1 保留:调一次 Amazon 建议接口,返回关键词列表。"""
    params = {
        "prefix": prefix,
        "alias": alias,
        "limit": limit,
        "mid": MARKETPLACE_US,
        "client-info": "amazon-search-ui",
    }
    response = requests.get(
        AMAZON_SUGGEST_URL,
        params=params,
        headers=HEADERS,
        timeout=10,
    )
    response.raise_for_status()
    data = response.json()

    return [
        item["value"]
        for item in data.get("suggestions", [])
        if item.get("type") == "KEYWORD"
    ]


def recursive_fetch(
    seed: str,
    max_depth: int = 2,
    sleep_sec: float = 0.5,
    alias: str = "aps",
) -> dict:
    """BFS 递归采集。

    Args:
        seed: 种子词,如 "silicone baking"
        max_depth: 最大递归深度。1=只采种子,2=种子+其子词,3=词量爆炸慎用
        sleep_sec: 每次请求间隔,礼貌+防频控
        alias: Amazon 类目 alias

    Returns:
        {seed, collected_at, request_count, total_keywords, keywords: [...]}
    """
    expanded: set[str] = set()
    collected: set[str] = set()
    queue: deque[tuple[str, int, str | None]] = deque([(seed, 0, None)])
    keywords: list[dict] = []
    request_count = 0

    while queue:
        prefix, depth, parent = queue.popleft()

        if prefix in expanded:
            continue
        expanded.add(prefix)

        try:
            suggestions = fetch_suggestions(prefix, alias=alias)
        except Exception as exc:
            print(f"  [WARN] fetch failed prefix={prefix!r}: {exc}")
            continue

        request_count += 1
        print(f"  [depth={depth}] {prefix!r} -> {len(suggestions)} suggestions")

        for value in suggestions:
            if value in collected:
                continue
            collected.add(value)
            keywords.append({
                "value": value,
                "depth": depth + 1,
                "parent": prefix,
            })
            if depth + 1 < max_depth and value not in expanded:
                queue.append((value, depth + 1, prefix))

        time.sleep(sleep_sec)

    return {
        "seed": seed,
        "max_depth": max_depth,
        "alias": alias,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "request_count": request_count,
        "total_keywords": len(keywords),
        "keywords": keywords,
    }


def batch_fetch(
    sub_categories: list[dict],
    category: str,
    max_depth: int = 2,
    sleep_sec: float = 0.5,
    alias: str = "aps",
) -> dict:
    """批量采集多个子类目,合并成一个类目结果。

    Args:
        sub_categories: [{"name": "silicone_mat", "seeds": ["silicone baking mat", "silicone mat"]}, ...]
                        每个子类目支持 1-N 个种子(v0.3 从 1:1 升级为 1:N,覆盖同义表达)
        category: 类目名,用于顶层标识和落盘文件命名
        max_depth: 每个种子的递归深度
        sleep_sec: 请求间隔
        alias: Amazon 类目 alias

    Returns:
        类目级 dict,包含每个子类目的关键词 + 跨子类目去重统计。
    """
    result_sub_categories: list[dict] = []
    all_values: set[str] = set()
    total_raw = 0
    total_requests = 0

    for i, entry in enumerate(sub_categories, 1):
        name = entry["name"]
        seeds = entry.get("seeds") or ([entry["seed"]] if "seed" in entry else [])
        if not seeds:
            print(f"  [WARN] sub_category {name!r} 没有种子,跳过")
            continue

        print(f"\n[{i}/{len(sub_categories)}] sub_category={name!r} seeds={seeds}")
        print("-" * 60)

        merged_keywords: list[dict] = []
        merged_seen: set[str] = set()
        sub_requests = 0

        for seed in seeds:
            r = recursive_fetch(
                seed, max_depth=max_depth, sleep_sec=sleep_sec, alias=alias,
            )
            sub_requests += r["request_count"]
            for kw in r["keywords"]:
                if kw["value"] in merged_seen:
                    continue
                merged_seen.add(kw["value"])
                merged_keywords.append(kw)

        result_sub_categories.append({
            "name": name,
            "seeds": seeds,
            "request_count": sub_requests,
            "total_keywords": len(merged_keywords),
            "keywords": merged_keywords,
        })
        total_raw += len(merged_keywords)
        total_requests += sub_requests
        for kw in merged_keywords:
            all_values.add(kw["value"])

    return {
        "category": category,
        "max_depth": max_depth,
        "alias": alias,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "sub_category_count": len(result_sub_categories),
        "total_requests": total_requests,
        "total_keywords_raw": total_raw,
        "unique_keywords": len(all_values),
        "sub_categories": result_sub_categories,
    }


def save_to_json(data: dict, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Saved to {path}")


# ============================================================
# Function Calling tool 集成(Sprint 6 Task 5)
#
# 这个 tool 让 Agent 运行时能主动调用 Amazon 搜索建议接口。
# 使用场景:Writer 遇到冷门产品,静态 RAG 词库召回不够时,主动查真实用户长尾表达。
#
# schema 和 impl 放在同一个文件,遵循 mock_tools.py 顶部说的"共变性设计"。
# 通过 mock_tools.py 底部的 append 集成到全局工具注册中心,base.py 无感。
# ============================================================

SEARCH_AMAZON_KEYWORDS_SCHEMA: dict[str, Any] = {
    "name": "search_amazon_keywords",
    "description": (
        "调用 Amazon 官方搜索建议接口,拿一个短前缀词的**真实用户搜索补全**。"
        "例如 prefix='silicone baking' 会返回 'silicone baking mat', "
        "'macaron silicone baking mats' 等真实用户在搜的长尾词。"
        "使用场景:遇到冷门产品、静态 RAG 词库召回不足、需要发现真实用户长尾表达时调用。"
        "**这是真实网络请求,只在必要时调,单次约 1 秒**。"
        "输入的 prefix 应该是 1-3 词的**短入口词**(如 'piping bag'),"
        "不要传完整产品名(如 'piping bag reusable professional set of 6')。"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "prefix": {
                "type": "string",
                "description": "搜索前缀,1-3 词的短入口词",
            },
            "limit": {
                "type": "integer",
                "description": "返回条数上限,默认 10,最大 11",
            },
        },
        "required": ["prefix"],
    },
}


def _tool_impl_search_amazon_keywords(prefix: str, limit: int = 10) -> dict[str, Any]:
    """Tool 实现:复用 v0.1 的 fetch_suggestions,包一层给 Agent 用的返回结构。

    刻意做的:
      - 出错时不抛异常,而是返回 error 字段。因为 Agent Loop 里 tool 抛异常
        会导致整个循环挂掉,更好的做法是把错误结构化返回,让 LLM 决定下一步。
    """
    try:
        results = fetch_suggestions(prefix, limit=limit)
        return {
            "prefix": prefix,
            "count": len(results),
            "keywords": results,
            "data_source": "amazon.com search suggestions API (real)",
        }
    except Exception as exc:
        return {
            "prefix": prefix,
            "count": 0,
            "keywords": [],
            "error": f"{type(exc).__name__}: {exc}",
            "data_source": "amazon.com search suggestions API (real, failed)",
        }


def export_to_knowledge_base(
    batch_result: dict | str | Path,
    output_path: str | Path,
    description: str = "",
    extra_source_notes: str = "",
) -> Path:
    """把 batch_fetch 的结果转成 KeywordStore 兼容的 knowledge_base JSON。

    KeywordStore 期望 schema:
        {category, description, last_updated, source_notes,
         keywords: [str], competitor_titles: [str]}

    本函数负责:
      1. 从 sub_categories 摊平成扁平 keywords 列表
      2. 全局去重、小写化(BM25 大小写敏感,keyword_store.py 里明确要求)
      3. 生成 source_notes 说明数据来源(面试可讲的痕迹)
      4. competitor_titles 暂留空,后续单独采集

    Args:
        batch_result: batch_fetch 返回的 dict,或它的 JSON 文件路径
        output_path: 目标路径,通常 data/knowledge_base/{category}_keywords.json
        description: 覆盖默认描述
        extra_source_notes: 追加到 source_notes 的额外说明

    Returns:
        写入的 Path 对象。
    """
    if isinstance(batch_result, (str, Path)):
        with open(batch_result, encoding="utf-8") as f:
            batch_result = json.load(f)

    category = batch_result["category"]

    keywords: list[str] = []
    seen: set[str] = set()
    for sc in batch_result["sub_categories"]:
        for kw in sc["keywords"]:
            value = kw["value"].lower().strip()
            if value and value not in seen:
                seen.add(value)
                keywords.append(value)

    base_notes = (
        f"自动采集自 Amazon 搜索建议接口 (completion.amazon.com)。"
        f"{batch_result['sub_category_count']} 个子类目种子,"
        f"递归深度 {batch_result['max_depth']},"
        f"共 {batch_result['total_requests']} 次请求。"
        f"采集时间 {batch_result['collected_at']}。"
    )
    if extra_source_notes:
        base_notes = f"{base_notes} {extra_source_notes}"

    kb_data = {
        "category": category,
        "description": description or f"{category} 类目自动采集关键词库(amazon_suggest v0.2.5)",
        "last_updated": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "source_notes": base_notes,
        "keywords": keywords,
        "competitor_titles": [],
    }

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(kb_data, f, ensure_ascii=False, indent=2)

    print(f"Exported {len(keywords)} keywords to {path}")
    return path


# ============================================================
# YAML 配置驱动(Sprint 6 Task 3 v0.3)
#
# 目标:加一个新类目零改代码。
#   1. cp config/categories/baking.yaml new.yaml
#   2. 改 name / seeds
#   3. python -m src.tools.amazon_suggest --category new
# ============================================================

def load_category_config(
    category: str,
    config_dir: str | Path = "config/categories",
) -> dict:
    """从 YAML 加载一个类目的采集配置,做最小 schema 校验。

    Raises:
        FileNotFoundError: 配置文件不存在(提示怎么创建)
        ValueError: 缺必填字段
    """
    path = Path(config_dir) / f"{category}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"类目配置不存在: {path}. "
            f"参考 config/categories/baking.yaml,改 name/seeds 就能加新类目。"
        )
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    missing = {"name", "sub_categories"} - config.keys()
    if missing:
        raise ValueError(f"{path} 缺必填字段: {missing}")
    for sc in config["sub_categories"]:
        if "name" not in sc or not (sc.get("seeds") or sc.get("seed")):
            raise ValueError(
                f"{path} 中 sub_category 必须有 name 和 seeds(或 seed): {sc}"
            )
    return config


def run_category(
    category: str,
    config_dir: str | Path = "config/categories",
    keywords_output_dir: str | Path = "data/keywords",
    knowledge_base_output_dir: str | Path = "data/knowledge_base",
) -> dict:
    """一站式:读 YAML → 采集 → 落盘 batch JSON → 导出 KeywordStore 格式。

    这是 v0.3 "配置驱动"的 CLI 核心,面试话术:
        "加一个新类目就是写一个 YAML 文件,一行代码不改。"
    """
    config = load_category_config(category, config_dir=config_dir)
    print(f"Loaded config: {category!r}")
    print(f"  description: {config.get('description', '(none)')}")
    print(f"  alias:       {config.get('alias', 'aps')}")
    print(f"  max_depth:   {config.get('max_depth', 2)}")
    print(f"  sub_cats:    {len(config['sub_categories'])}")
    print("=" * 60)

    result = batch_fetch(
        sub_categories=config["sub_categories"],
        category=config["name"],
        max_depth=config.get("max_depth", 2),
        alias=config.get("alias", "aps"),
    )
    print("=" * 60)
    print(f"Done.")
    print(f"  Sub-categories:      {result['sub_category_count']}")
    print(f"  Total requests:      {result['total_requests']}")
    print(f"  Raw keywords:        {result['total_keywords_raw']}")
    print(f"  Unique keywords:     {result['unique_keywords']}")

    batch_output = Path(keywords_output_dir) / f"{config['name']}_all_depth{result['max_depth']}.json"
    kb_output = Path(knowledge_base_output_dir) / f"{config['name']}_keywords.json"
    save_to_json(result, batch_output)
    export_to_knowledge_base(
        result, kb_output,
        description=config.get("description", ""),
    )
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Amazon 搜索建议采集器(v0.3 配置驱动)。示例:\n"
                    "  python -m src.tools.amazon_suggest --category baking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--category", "-c",
        default="baking",
        help="类目名,对应 config/categories/{category}.yaml。默认 baking。",
    )
    parser.add_argument(
        "--config-dir",
        default="config/categories",
        help="配置文件目录",
    )
    args = parser.parse_args()

    run_category(category=args.category, config_dir=args.config_dir)

