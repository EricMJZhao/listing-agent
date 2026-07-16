"""
硬规则检查器 —— Reviewer Agent 的核心工具。

设计原则:
    1. **纯函数**:输入 listing dict → 输出 issue(或 None),不改动输入、不打日志
    2. **单一职责**:每个函数只检查一条规则,好测试、好组合
    3. **给 Writer 可执行的修改提示**:message 讲问题,fix_hint 讲怎么改
       —— Sprint 2 的 Orchestrator 会把 fix_hint 塞回 Writer 让它重写

为什么单独放 evaluation 目录而不是塞进 reviewer_agent.py:
    Sprint 4 加 LLM as Judge 时,评分逻辑也放这里(rules.py 是硬规则,scores.py 是软打分)。
    Reviewer 只是"调用者",评估逻辑是独立资产。

面试话术:
    "我把评估逻辑独立成一个包,而不是 Reviewer 内部。这样规则演化(比如加'字节数
    要留 5 字节缓冲')只改 rules.py,Reviewer 完全不用动。这是**分离关注点** ——
    Reviewer 关心'怎么审',rules.py 关心'审什么标准'。"
"""

from dataclasses import dataclass, field


# ============================================================
# 数据结构
# ============================================================


@dataclass
class RuleIssue:
    """
    一条规则违规的标准描述。

    为什么用 dataclass 而不是普通 dict:
        1. 类型清晰:IDE 能补全 issue.rule_id
        2. 字段固定:忘写某个字段 Python 会报错,不像 dict 漏字段静默失败
        3. 面试话术:"我用 dataclass 定义了 Agent 间通信协议,
                    Reviewer 和 Writer 靠这个 schema 对齐"
    """

    rule_id: str          # 规则代号,例:"backend_bytes"
    field: str            # 违规的字段名,例:"backend_keywords"
    severity: str         # "error"(必须重写) | "warning"(可选改)
    message: str          # 人类可读的问题描述
    fix_hint: str         # 给 Writer 重写时的提示词(会拼进下一轮 prompt)


# ============================================================
# 规则常量 —— 集中在这里方便调
# ============================================================

TITLE_MAX_CHARS = 200
BULLET_REQUIRED_COUNT = 5
BACKEND_MAX_BYTES = 249

# Amazon TOS 禁止的夸张词(部分,面试可以说"这是从卖家论坛整理的")
BANNED_WORDS = [
    "BEST", "PERFECT", "AMAZING", "GUARANTEE", "GUARANTEED",
    "#1", "NUMBER ONE", "TOP RATED", "FDA APPROVED",
]


# ============================================================
# 单条规则:每个函数一个检查点
# 返回 RuleIssue 表示违规,None 表示通过
# ============================================================


def check_title_length(listing: dict) -> RuleIssue | None:
    """Title 不能超 200 字符,超了 Amazon 后台会截断。"""
    title = listing.get("title", "")
    length = len(title)
    if length <= TITLE_MAX_CHARS:
        return None

    return RuleIssue(
        rule_id="title_length",
        field="title",
        severity="error",
        message=f"Title {length} 字符, 超出上限 {TITLE_MAX_CHARS}",
        fix_hint=f"把 Title 精简到 {TITLE_MAX_CHARS} 字符以内,"
                 f"当前多出 {length - TITLE_MAX_CHARS} 字符,"
                 f"优先删除通用形容词和重复的类目词",
    )


def check_bullet_count(listing: dict) -> RuleIssue | None:
    """Bullet 必须恰好 5 条,Amazon 后台就 5 个格子。"""
    bullets = listing.get("bullet_points", [])
    count = len(bullets)
    if count == BULLET_REQUIRED_COUNT:
        return None

    return RuleIssue(
        rule_id="bullet_count",
        field="bullet_points",
        severity="error",
        message=f"Bullet 数量 {count}, 要求恰好 {BULLET_REQUIRED_COUNT} 条",
        fix_hint=f"必须写 {BULLET_REQUIRED_COUNT} 条 bullet, "
                 f"{'合并较弱的' if count > BULLET_REQUIRED_COUNT else '补齐缺失的'}",
    )


def check_backend_bytes(listing: dict) -> RuleIssue | None:
    """
    Backend Keywords 的 UTF-8 字节数不能超 249。

    这就是 Sprint 0 product_1 踩坑的规则 —— 257 字节。
    面试演示时可以指着 bad_cases.md 讲:"我这条规则就是被这个 case 逼出来的。"

    为什么用字节而不是字符:
        英文 1 字符 = 1 字节,但如果 Reviewer 未来支持日文/德文 Listing,
        1 个中文字符 = 3 字节。Amazon 后端算的是字节数,必须一致。
    """
    keywords = listing.get("backend_keywords", "")
    byte_length = len(keywords.encode("utf-8"))
    if byte_length <= BACKEND_MAX_BYTES:
        return None

    over = byte_length - BACKEND_MAX_BYTES
    return RuleIssue(
        rule_id="backend_bytes",
        field="backend_keywords",
        severity="error",
        message=f"Backend Keywords {byte_length} 字节, 超出上限 {BACKEND_MAX_BYTES}",
        fix_hint=f"删掉至少 {over} 字节的关键词。"
                 f"优先删除:(1) 已经在 Title 里出现的词 "
                 f"(2) 通用度低的长尾词",
    )


def check_banned_words(listing: dict) -> list[RuleIssue]:
    """
    禁用词检查 —— 一次返回多条(每个字段都可能踩)。

    为什么返回 list 而不是单个 issue:
        title / bullet / description 都可能同时踩不同禁用词,
        我们希望 Writer 一次改完,而不是一轮改一个词循环 4 次。
    """
    issues: list[RuleIssue] = []

    # 需要扫描的字段和它们的显示名
    fields_to_check = {
        "title": "Title",
        "product_description": "Product Description",
    }

    def scan_text(text: str, source_label: str, source_key: str) -> None:
        upper = text.upper()
        hit = [w for w in BANNED_WORDS if w in upper]
        if hit:
            issues.append(
                RuleIssue(
                    rule_id="banned_words",
                    field=source_key,
                    severity="error",
                    message=f"{source_label} 含禁用词: {', '.join(hit)}",
                    fix_hint=f"从 {source_label} 中删除或替换这些词: "
                             f"{', '.join(hit)}。用具体数字或事实替代夸张词, "
                             f"例如 'BEST' → '5-Star Rated'",
                )
            )

    # 单文本字段
    for key, label in fields_to_check.items():
        scan_text(listing.get(key, ""), label, key)

    # Bullet 是列表,逐条扫
    bullets = listing.get("bullet_points", [])
    for i, bullet in enumerate(bullets, 1):
        scan_text(bullet, f"Bullet {i}", "bullet_points")

    return issues


# ============================================================
# 总入口 —— Reviewer 只调这一个函数
# ============================================================


def check_all_hard_rules(listing: dict) -> list[RuleIssue]:
    """
    跑所有硬规则,返回所有违规的 issue 列表。空列表 = 全部通过。

    为什么把所有规则藏在这一个函数后面:
        Reviewer 不需要知道"具体有几条规则、每条叫什么",
        它只关心"有没有 issue、issue 列表是什么"。
        Sprint 3 加新规则时改这一个函数,Reviewer 完全不用改。
        这就是**封装**。
    """
    issues: list[RuleIssue] = []

    # 单个 issue 的规则,None 表示通过
    for check_fn in (check_title_length, check_bullet_count, check_backend_bytes):
        result = check_fn(listing)
        if result is not None:
            issues.append(result)

    # 返回 list 的规则,直接展开
    issues.extend(check_banned_words(listing))

    return issues
