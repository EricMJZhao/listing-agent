"""
Reviewer Agent —— Sprint 2 的第二个 Agent,专司审核。

它做什么:
    输入 Writer 生成的 Listing → 硬规则(代码)+ 软规则(LLM Haiku) → 统一体检报告

它不做什么:
    - 不重写 Listing(那是 Writer 的事)
    - 不决定要不要继续循环(那是 Orchestrator 的事)

关键设计:
    1. 硬规则和软规则用**同一个 issue 数据结构**,只多一个 source 字段区分
       —— Orchestrator 后续不用区分来源就能把 issues 塞回 Writer
    2. Reviewer 用 model_judge(Haiku 4.5),不用 model_main(Opus 4.8)
       —— 打分判断题不需要顶配模型,便宜快就够
    3. 硬规则任何一条 error 即 passed=False;软规则总分 < 阈值也 passed=False

面试话术:
    "Reviewer 是 Sprint 2 的核心增量。它左手拿代码卡尺(硬规则,100% 准),
    右手拿 LLM 判断软规则(利益先行、关键词覆盖)。合并成一份统一 issues 列表,
    每条 issue 都带 fix_hint —— 这样 Orchestrator 拿到报告可以直接把可执行提示塞回
    Writer 让它重写。这就是 Multi-Agent 之间**互相 actionable** 的设计。"
"""

from dataclasses import asdict

from src.agents.base import BaseAgent
from src.config import settings
from src.evaluation.rules import check_all_hard_rules
from src.prompts.reviewer import REVIEWER_SYSTEM_PROMPT, build_reviewer_user_message


# 软规则通过分数线:低于此分即使硬规则全过,也判 passed=False,触发重写
SOFT_PASS_THRESHOLD = 75


class ReviewerAgent(BaseAgent):
    """审 Writer 生成的 Listing,输出统一体检报告。"""

    name = "reviewer"

    def run(self, input_data: dict) -> dict:
        """
        运行 Reviewer 审核。

        参数:
            input_data: {
                "listing": Writer 生成的 Listing dict,
                "product_info": 卖家原始商品 dict(Reviewer 需要它做关键词覆盖判断)
            }

        返回:
            {
                "passed": bool,
                "overall_score": 0-100(软规则得分),
                "summary": "...",
                "issues": [ {source, rule_id, field, severity, message, fix_hint}, ... ]
            }
        """
        listing = input_data["listing"]
        product_info = input_data["product_info"]

        self._log(f"开始审核 SKU {product_info.get('sku', '?')}")

        # === Step 1: 硬规则(代码,零 LLM 调用) ===
        hard_issues = self._run_hard_rules(listing)
        self._log(f"硬规则:{len(hard_issues)} 个 issue")

        # === Step 2: 软规则(LLM Haiku 判断) ===
        soft_report = self._run_soft_rules(listing, product_info)
        self._log(
            f"软规则:得分 {soft_report['overall_score']}/100,"
            f"{len(soft_report['issues'])} 个 issue"
        )

        # === Step 3: 合并 + 判定通过 ===
        all_issues = hard_issues + soft_report["issues"]
        passed = self._decide_passed(hard_issues, soft_report["overall_score"])

        report = {
            "passed": passed,
            "overall_score": soft_report["overall_score"],
            "summary": soft_report["summary"],
            "issues": all_issues,
        }

        verdict = "✓ 通过" if passed else "✗ 需要重写"
        self._log(f"最终判定:{verdict}")
        return report

    # ============================================================
    # 内部方法
    # ============================================================

    def _run_hard_rules(self, listing: dict) -> list[dict]:
        """
        跑硬规则,把 RuleIssue dataclass 转成 dict 统一格式。

        为什么要 dict 化:
            软规则 Reviewer 直接输出 dict(LLM 的 JSON),
            为了让 Orchestrator 拿到的 issues 列表**同构**,
            硬规则也要转成 dict,加一个 source 字段区分来源。
        """
        rule_issues = check_all_hard_rules(listing)
        return [
            {"source": "hard", **asdict(issue)}
            for issue in rule_issues
        ]

    def _run_soft_rules(self, listing: dict, product_info: dict) -> dict:
        """
        调 LLM(Haiku)判断软规则,返回 LLM 的原始 JSON 输出。

        为什么用 Haiku 而不是 Opus:
            软规则本质是**判断题**(打分 + 找问题),不是写作题。
            Haiku 4.5 在判断类任务上跟 Opus 4.8 差距很小,
            但成本 1/15、速度快 3-5 倍。
            Sprint 2 里 Reviewer 平均跑 1.5 次(触发重写会跑二遍),
            成本差异累积起来很显著。
        """
        user_msg = build_reviewer_user_message(listing, product_info)

        # 关键:model 传 settings.model_judge,不走默认的 model_main
        raw = self._call_llm(
            system_prompt=REVIEWER_SYSTEM_PROMPT,
            user_message=user_msg,
            model=settings.model_judge,
        )
        parsed = self._parse_json_response(raw)

        # 给每个软 issue 加 source: "soft" 标记
        for issue in parsed.get("issues", []):
            issue["source"] = "soft"

        return parsed

    def _decide_passed(self, hard_issues: list[dict], soft_score: int) -> bool:
        """
        综合判定 passed。

        判定逻辑(可以在这里演化):
            - 硬规则任何 error 严重程度 → False(硬规则违规不可协商)
            - 软规则 < 75 分 → False
            - 都过 → True

        为什么硬规则 error 一票否决:
            硬规则违反了 Amazon 后台会直接截断/拒绝,不是"扣分"问题,
            是"发不出去"问题。这类问题必须重写。
        """
        # 只要有一条硬规则是 error 级别就直接失败
        for issue in hard_issues:
            if issue.get("severity") == "error":
                return False

        # 软规则分数线
        if soft_score < SOFT_PASS_THRESHOLD:
            return False

        return True
