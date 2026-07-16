"""
类目关键词库 + BM25 检索器 —— Sprint 1 核心。

为什么单独一个类而不是几个 free-standing 函数:
    KeywordStore 有内部状态(BM25 索引、原始关键词列表、竞品 Title)。
    加载一次索引后多次检索,状态封装在类里最自然。
    面试话术:"这是**懒加载 + 缓存**的实践 —— 索引在 __init__ 时构建一次,
              每次 search 复用,避免每次调用都重新 tokenize。"

关键决策:
    1. **BM25 而非向量检索**:关键词精确匹配够用,零依赖
    2. **返回原始关键词字符串**:调用方直接拼进 Prompt,不需要额外映射
    3. **数据文件用 JSON**:作品集不需要数据库,一个文件搞定,git 追踪方便
"""

import json
from pathlib import Path

from rank_bm25 import BM25Okapi


class KeywordStore:
    """
    一个类目的关键词库 + 竞品 Title,提供 BM25 检索。

    使用方式:
        store = KeywordStore("data/knowledge_base/cutting_board_keywords.json")
        top_20 = store.search_keywords("bamboo cutting board", top_k=20)
        titles = store.get_competitor_titles()
    """

    def __init__(self, json_path: str | Path) -> None:
        """
        加载知识库 + 构建 BM25 索引。

        参数:
            json_path: 关键词库 JSON 路径,schema 见 TEMPLATE.md
        """
        self.json_path = Path(json_path)
        if not self.json_path.exists():
            raise FileNotFoundError(f"关键词库不存在: {self.json_path}")

        with self.json_path.open("r", encoding="utf-8") as f:
            data = json.load(f)

        self.category: str = data.get("category", "unknown")
        self.keywords: list[str] = data.get("keywords", [])
        self.competitor_titles: list[str] = data.get("competitor_titles", [])

        # === 构建 BM25 索引 ===
        # 每条关键词 tokenize 成小写词列表
        # 为什么不做 stemming/lemmatization:
        #   Amazon 搜索是精确匹配,'cutting boards' 和 'cutting board' 用户会
        #   分别搜。做 stemming 反而丢信息。这是**领域驱动的选择**,不是通用 NLP。
        tokenized_corpus = [kw.lower().split() for kw in self.keywords]
        self.bm25 = BM25Okapi(tokenized_corpus)

        print(
            f"[KeywordStore] 加载 {self.category} 类目, "
            f"{len(self.keywords)} 关键词, "
            f"{len(self.competitor_titles)} 个竞品 Title"
        )

    def search_keywords(self, query: str, top_k: int = 20) -> list[str]:
        """
        BM25 检索 top_k 关键词。

        参数:
            query:  查询字符串,通常是商品类目 + 种子词
            top_k:  返回多少个关键词

        返回:
            list[str]: 按 BM25 分数从高到低排的关键词列表

        为什么返回原始字符串而不是 (kw, score) tuple:
            调用方(Writer 的 build_prompt)只需要关键词本身拼进 prompt,
            不需要分数。**接口应该只暴露调用方需要的信息**,减少认知负担。
        """
        if not self.keywords:
            return []

        tokenized_query = query.lower().split()
        # get_top_n 直接返回原始文档(关键词字符串),不用手动排序
        return self.bm25.get_top_n(tokenized_query, self.keywords, n=top_k)

    def get_competitor_titles(self, limit: int = 3) -> list[str]:
        """
        直接拿前 limit 个竞品 Title(不用检索,顺序即优先级)。

        为什么不做 BM25 检索:
            作品集阶段竞品 Title 就 3-5 个,全都塞进 prompt 就够,
            不需要检索。Sprint 4 加更多竞品后再考虑检索。
        """
        return self.competitor_titles[:limit]
