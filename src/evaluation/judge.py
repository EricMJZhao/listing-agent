"""
LLM as Judge —— Sprint 4 引入的**离线评估**器。

跟 Reviewer 的区别(重要):
    Reviewer:流程内 gate,决定"要不要重写",输出 pass/fail + issues
    Judge:   离线评估,给"生成质量"打 0-100 连续分,用于 A/B 对比

为什么要分开:
    1. **职责不同**:Reviewer 保 baseline,Judge 打质量分
    2. **模型可以不同**:Reviewer 用 Haiku(便宜快),Judge 应该用最强模型(评估要精准)
    3. **可独立演进**:Judge 的 rubric 演化不影响 Reviewer 的 gate 逻辑

面试话术:
    "我把 Reviewer 和 Judge 分成两个组件 —— **一个是流程内 gate(pass/fail),
     一个是离线评估(0-100 分)**。这两件事在很多项目里被混在一起,后果是
     Reviewer 的分数线一调整,离线评估的历史数据全失效。我分开设计后,可以
     独立调 gate 阈值不影响评估基线。**这是 Multi-Agent 系统的信号解耦**。"
"""

import json
from dataclasses import asdict, dataclass

from src.config import settings
from src.llm_client import llm


# Judge 的评分维度(每个 0-25 分,总分 100)
JUDGE_RUBRIC = """
你是一名 Amazon Listing 专家评审,给下面这份 Listing 打质量分。
按 4 个维度打分,每维度 0-25 分,总分 100。

## 维度 1: SEO 质量 (0-25)
- Title 前 5 词是否含核心关键词? (0-8)
- Backend Keywords 是否高效利用 249 字节(不重复 Title 已有词)? (0-8)
- 长尾关键词是否自然融入 Bullet 和 Description? (0-9)

## 维度 2: 用户价值 (0-25)
- Bullet 是否"利益先行"(前 3 词是 benefit)? (0-10)
- 是否用具体数字建立信任(0.8-inch, 3-oz)? (0-8)
- Description 是否有场景画面感? (0-7)

## 维度 3: 差异化 (0-25)
- 商品的 differentiation 字段每条是否都讲清楚? (0-15)
- 竞争优势是否显性化(vs. 标准产品的对比)? (0-10)

## 维度 4: 合规性 (0-25)
- 是否有 Amazon TOS 禁用词(BEST/PERFECT/GUARANTEE)? (0-10)
- Title 字符数 / Backend 字节数是否在限制内? (0-8)
- Bullet 数是否恰好 5 条? (0-7)

## 输出格式(严格 JSON,不加 markdown 包裹)
{
  "seo_score": 0-25,
  "user_value_score": 0-25,
  "differentiation_score": 0-25,
  "compliance_score": 0-25,
  "total_score": 上面 4 项之和,
  "strengths": ["优点 1", "优点 2"],
  "weaknesses": ["不足 1", "不足 2"],
  "verdict": "excellent | good | acceptable | needs_work"
}
"""


@dataclass
class JudgeReport:
    """Judge 的评估报告(强类型,便于下游消费)。"""

    seo_score: int
    user_value_score: int
    differentiation_score: int
    compliance_score: int
    total_score: int
    strengths: list[str]
    weaknesses: list[str]
    verdict: str


class ListingJudge:
    """给一份 Listing 打质量分,离线评估用。"""

    def __init__(self, model: str | None = None) -> None:
        # Judge 应该用最强模型(评估要精准) —— 默认走 model_main(Opus)
        # 未来可以切 gpt-4 / 其他 provider 做交叉验证
        self.model = model or settings.model_main

    def judge(self, listing: dict, product_info: dict) -> JudgeReport:
        """
        对一份 Listing 打分。

        参数:
            listing:       Writer/Orchestrator 输出的 Listing dict
            product_info:  卖家原始商品信息(用于对照 differentiation)

        返回:
            JudgeReport dataclass
        """
        user_message = f"""请评审下面这份 Amazon Listing。

# 商品原始信息(用于对照 differentiation)
```json
{json.dumps(product_info, ensure_ascii=False, indent=2)}
```

# Listing 待评审
```json
{json.dumps(listing, ensure_ascii=False, indent=2)}
```

现在按 rubric 打分,输出严格 JSON。
"""

        raw_text = llm.chat(
            system_prompt=JUDGE_RUBRIC,
            user_message=user_message,
            model=self.model,
        )

        try:
            data = json.loads(raw_text)
        except json.JSONDecodeError as e:
            print(f"[Judge] JSON 解析失败,原文:\n{raw_text}")
            raise RuntimeError(f"Judge 解析失败: {e}") from e

        return JudgeReport(**{
            "seo_score": int(data.get("seo_score", 0)),
            "user_value_score": int(data.get("user_value_score", 0)),
            "differentiation_score": int(data.get("differentiation_score", 0)),
            "compliance_score": int(data.get("compliance_score", 0)),
            "total_score": int(data.get("total_score", 0)),
            "strengths": data.get("strengths", []),
            "weaknesses": data.get("weaknesses", []),
            "verdict": data.get("verdict", "unknown"),
        })

    def judge_multi_sample(
        self,
        listing: dict,
        product_info: dict,
        n_samples: int = 3,
    ) -> dict:
        """
        多次采样打分取中位数 —— Sprint 4 关键设计。

        为什么多次采样:
            LLM as Judge 单次打分有波动,同一个 Listing 一次给 85 一次给 92
            都是可能的。多次采样取中位数可以显著降低单次波动的影响。

        面试话术:
            "LLM as Judge 的固有问题是分数波动。我用 n_samples=3 采样取中位数,
             把单次 ±10 的波动降到 ±3 以内。生产环境可以加大到 n=5 或者用
             不同 provider 做交叉验证(Claude + GPT-4 + Gemini),那是**评估共识**
             的做法。"
        """
        reports = [self.judge(listing, product_info) for _ in range(n_samples)]

        # 每个维度取中位数(排序中间那个,不用 statistics.median 避免小数)
        def median(scores: list[int]) -> int:
            return sorted(scores)[len(scores) // 2]

        return {
            "n_samples": n_samples,
            "median_scores": {
                "seo_score": median([r.seo_score for r in reports]),
                "user_value_score": median([r.user_value_score for r in reports]),
                "differentiation_score": median([r.differentiation_score for r in reports]),
                "compliance_score": median([r.compliance_score for r in reports]),
                "total_score": median([r.total_score for r in reports]),
            },
            "score_range": {
                "min": min(r.total_score for r in reports),
                "max": max(r.total_score for r in reports),
                "variance": max(r.total_score for r in reports) - min(r.total_score for r in reports),
            },
            "all_reports": [asdict(r) for r in reports],
        }
