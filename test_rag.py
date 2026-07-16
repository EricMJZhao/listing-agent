"""
RAG 单元测试 —— Sprint 1 Step 3 一部分。

用法:
    python test_rag.py

它做什么:
    1. 加载切菜板关键词库
    2. 跑 5 个检索用例,验证 BM25 检索质量
    3. 打印结果肉眼验收

不依赖 LLM(全离线),秒级完成。
"""

from src.rag.keyword_store import KeywordStore


def run_test(store: KeywordStore, query: str, top_k: int = 5) -> None:
    """跑一次检索并打印结果。"""
    print(f"\n--- Query: '{query}' (top {top_k}) ---")
    results = store.search_keywords(query, top_k=top_k)
    if not results:
        print("  (无结果)")
        return
    for i, kw in enumerate(results, 1):
        print(f"  {i}. {kw}")


def main() -> None:
    print("=" * 60)
    print("RAG · KeywordStore 单元测试")
    print("=" * 60)

    # === Step 1: 加载 ===
    store = KeywordStore("data/knowledge_base/cutting_board_keywords.json")

    # === Step 2: 5 个检索用例,覆盖不同意图 ===
    # 每个 query 期望的 top 结果我在注释里写好,肉眼比对
    run_test(store, "bamboo cutting board")
    # 期望:排第一的应该是 'bamboo cutting board' 或 'bamboo chopping board'

    run_test(store, "chopping board large")
    # 期望:top 应含 'chopping board', 'large cutting board'

    run_test(store, "walnut wooden")
    # 期望:top 应含 'walnut cutting board', 'wooden chopping board'

    run_test(store, "cheese charcuterie")
    # 期望:top 应含 'cheese board', 'charcuterie board'

    run_test(store, "cutting board")  # 最泛的 query,测 BM25 排序
    # 期望:短且相关的 'cutting board' / 'cutting board large' 排前

    # === Step 3: 竞品 Title ===
    print("\n--- 竞品 Best Seller Titles ---")
    for i, title in enumerate(store.get_competitor_titles(), 1):
        print(f"  {i}. {title[:100]}...")  # 只打印前 100 字符

    print("\n" + "=" * 60)
    print("肉眼验收:")
    print("  - 每个 query 的 top 结果应该跟你的查询意图相关")
    print("  - 结果排序合理(相关度高的排前)")
    print("  - 无 KeyError / FileNotFound 等异常")
    print("=" * 60)


if __name__ == "__main__":
    main()
