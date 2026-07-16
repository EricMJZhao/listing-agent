"""
Orchestrator —— Sprint 2 的收官作品,协调 Writer 和 Reviewer 的闭环循环。

它做什么:
    输入 product_info → 编排 Writer / Reviewer 循环 → 输出最终 Listing + 完整轨迹

它不做什么:
    - 不写 Listing(Writer 的事)
    - 不检查规则(Reviewer 的事)
    - 不判断软规则质量(Reviewer 的事)
    - 只做**流程控制** —— "什么时候调谁、什么时候停"

面试话术:
    "Orchestrator 是 Sprint 2 的收官作品。它把 Writer 和 Reviewer 用
     max_rounds=3 的循环串起来 —— 出稿、审核、有 issue 就把 fix_hint 塞回 Writer
     做定向修改、再审。这是 Multi-Agent **闭环** 的真正实现,不是简单的
     agent1 → agent2 一次性流水线。**闭环的关键是 fix_hint 让下一轮可执行**,
     否则 Writer 拿到反馈也不知道怎么改。"

一个反直觉的设计:
    max_rounds 到顶后,不返回**最后一轮**,返回**得分最高的那一轮**。
    实测发现 LLM 有时会为了修一个问题牺牲原本对的部分,
    最后一轮不一定最好。择优输出是最简单的震荡应对方案。
"""

from src.agents.reviewer_agent import ReviewerAgent
from src.agents.writer_agent import WriterAgent


# 循环上限:实测大多数 case 1-2 轮通过,3 轮以上边际收益低成本翻倍
DEFAULT_MAX_ROUNDS = 3


class Orchestrator:
    """
    Multi-Agent 闭环协调员。

    不继承 BaseAgent —— 因为它不是 Agent,不调 LLM,只做流程控制。
    面试可以说这句:"Orchestrator 是**协调者**不是**执行者**,不该跟
    Writer/Reviewer 混在同一个抽象层次。"
    """

    def __init__(self, max_rounds: int = DEFAULT_MAX_ROUNDS) -> None:
        self.writer = WriterAgent()
        self.reviewer = ReviewerAgent()
        self.max_rounds = max_rounds

    def run(self, product_info: dict) -> dict:
        """
        跑一次完整的 Writer ↔ Reviewer 循环。

        参数:
            product_info: 卖家给的商品信息

        返回:
            {
                "final_listing": {...},       最终交付的 Listing
                "final_report":  {...},       Reviewer 对 final_listing 的报告
                "reason":        str,         结束原因:"passed_at_round_N" / "max_rounds_best_score"
                "total_rounds":  int,         实际跑了几轮
                "rounds":        [ ... ],     每轮的 listing + report(演示用)
            }
        """
        self._log(f"===== 开始编排 (max_rounds={self.max_rounds}) =====")

        rounds: list[dict] = []
        previous_listing: dict | None = None
        previous_issues: list[dict] = []

        for round_num in range(1, self.max_rounds + 1):
            self._log(f"----- Round {round_num} -----")

            # === 1. Writer 出稿(首稿 or 重写)===
            if previous_listing is None:
                listing = self.writer.run(product_info)
            else:
                listing = self.writer.rewrite(
                    product_info=product_info,
                    previous_listing=previous_listing,
                    issues=previous_issues,
                )

            # === 2. Reviewer 审 ===
            report = self.reviewer.run({
                "listing": listing,
                "product_info": product_info,
            })

            # === 3. 记录本轮 ===
            rounds.append({
                "round": round_num,
                "listing": listing,
                "report": report,
                "passed": report["passed"],
                "score": report["overall_score"],
            })

            # === 4. 决定继续还是收工 ===
            if report["passed"]:
                self._log(
                    f"===== Round {round_num} passed ✓ "
                    f"(score={report['overall_score']}) 结束 ====="
                )
                return {
                    "final_listing": listing,
                    "final_report": report,
                    "reason": f"passed_at_round_{round_num}",
                    "total_rounds": round_num,
                    "rounds": rounds,
                }

            # 没通过,准备下一轮
            previous_listing = listing
            previous_issues = report["issues"]

        # === 走到这里说明 max_rounds 用完了都没过 ===
        # 择优输出:选得分最高的那一轮
        best = max(rounds, key=lambda r: r["score"])
        self._log(
            f"===== {self.max_rounds} 轮都未通过,择优输出 Round {best['round']} "
            f"(score={best['score']}) ====="
        )

        return {
            "final_listing": best["listing"],
            "final_report": best["report"],
            "reason": "max_rounds_best_score",
            "total_rounds": self.max_rounds,
            "rounds": rounds,
        }

    def _log(self, msg: str) -> None:
        """跟 BaseAgent 的日志格式对齐,方便统一读日志。"""
        print(f"[orchestrator] {msg}")
