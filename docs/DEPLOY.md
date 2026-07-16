# 部署指南 · Streamlit Community Cloud(v2 · 已跑通)

> 目标:让面试官通过一个 URL 远程访问 Listing Agent 演示,不需要装 Python。
>
> **本文档 v1 曾推荐先走 Anthropic 官方 Key,v2 修订(2026-07-16)记录真实部署经验:HF Spaces 因免费 quota=0 走不通,最终走 Streamlit Cloud + closeai 中转成功**。
> 每一步都有真实踩坑,后面的人不用重复。

---

## 一、选平台:HF Spaces vs Streamlit Cloud

我先试了 HF Spaces,失败了。总结对比如下,后来者可以直接选 Streamlit Cloud:

| 平台 | 结论 | 关键差异 |
|---|---|---|
| **HuggingFace Spaces** | ❌ **免费账号 cpu-basic quota = 0**(2026-07 政策) | 邮箱验证也不给,`hf spaces info` 返回 `Quota exceeded for flavor cpu-basic (requested=1): current=0, limit=0`。删空所有 Space 也无效,是账号级限制,不是使用量问题。**除非升级 PRO,免费用户走不通**。 |
| **Streamlit Community Cloud** | ✅ **推荐** | Streamlit 官方托管,无 quota 限制。GitHub push 自动 rebuild。免费个人账号可无限 public app。 |

**教训**:选型时不看营销页,看 API 报错。HF 官网说"免费 cpu-basic",但真实 quota 是 0,只有部署时用 `hf spaces info <repo>` 才能看到真实 errorMessage。

---

## 二、前置条件

- [x] GitHub 账号(仓库要 **public**,Streamlit Cloud 免费版只能连 public repo)
- [x] 一个 Anthropic 兼容的 API Key(下面 3 选 1)
  - 官方 https://console.anthropic.com/(新账号 $5 免费额度)
  - 或 closeai 中转 https://api.openai-proxy.org/(支持全系列 Claude 包括 Haiku 4.5)
  - 或公司中转(注意:能否公网访问?)
- [x] 项目代码本地能跑通(`python check_env.py` + `streamlit run app.py`)

---

## 三、Step 1 · 本地跑通(部署前必做)

**不要跳过**。别到 Streamlit Cloud 才发现代码有 bug。

```bash
cd /Users/eric/projects/listing-agent

# 装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 配 .env(4 个 key)
cat > .env <<EOF
ANTHROPIC_API_KEY=你的-key
ANTHROPIC_BASE_URL=https://api.openai-proxy.org/anthropic
LISTING_AGENT_MODEL=claude-sonnet-4-5
LISTING_AGENT_JUDGE_MODEL=claude-haiku-4-5
EOF

python check_env.py                                    # 验证 Key 通不通
python run_cli.py data/sample_products/product_1.json  # 端到端
streamlit run app.py                                    # UI 也要跑
```

**跑通了才进下一步**。

---

## 四、Step 2 · 建 GitHub 仓库 + push

```bash
git init && git branch -M main

# ⚠️ 检查 .env 不会被提交
cat .gitignore | grep -E "^\.env$"  # 应该输出 .env

# 第一次提交
git add .
git commit -m "Initial commit: Sprint 0-6 complete"

# GitHub 网页建一个 public repo 叫 listing-agent
git remote add origin https://github.com/<你的用户名>/listing-agent.git
git push -u origin main
```

**关键检查**:`git log --stat` 确认 `.env` 没进 commit。有的话立刻:
1. 去 Anthropic / closeai 后台 **revoke** 那个 key
2. 生成新 key
3. `.env` 用新 key,commit history 里删掉(`git filter-repo` 或直接删 repo 重建)

---

## 五、Step 3 · 部署到 Streamlit Community Cloud

### 5.1 登录 + 授权

打开 https://share.streamlit.io/ → 用 GitHub 账号登录 → 授权访问 repos(选 public 权限即可)。

### 5.2 创建 App

点 **"Create app"** → **"Deploy a public app from GitHub"** → 填 3 个字段:

| 字段 | 填 |
|---|---|
| **Repository** | `<你的用户名>/listing-agent` |
| **Branch** | `main` |
| **Main file path** | `app.py`(默认 `streamlit_app.py`,**必须改**) |

**先别点 Deploy!** 先点 **"Advanced settings"** 进 Secrets 配置。

### 5.3 配 Secrets(⚠️ 关键坑)

**注意**:Streamlit Cloud 的 Secrets 用 **TOML 格式**,不是 HF Space 那种"Name / Value"表单。

在 Advanced settings → Secrets 文本框粘:

```toml
ANTHROPIC_API_KEY = "sk-你的key"
ANTHROPIC_BASE_URL = "https://api.openai-proxy.org/anthropic"
LISTING_AGENT_MODEL = "claude-sonnet-4-5"
LISTING_AGENT_JUDGE_MODEL = "claude-haiku-4-5"
```

**填完必须点 Save 按钮**(常见坑:文本框里显示但没点 Save,值不生效)。

### 5.4 点 "Deploy!"

等 2-5 分钟。首次 build 会装依赖 + 启动 Streamlit runtime。

---

## 六、⚠️ Streamlit Cloud 秘密的最大坑:st.secrets → os.environ 时机

**Streamlit 官方文档说 secrets 会自动 mirror 到 `os.environ`。但实测 2026-07 部署环境有 timing 问题**:

- 业务代码 `src/config.py` 用 `os.getenv("ANTHROPIC_API_KEY")` 读环境变量(dataclass 默认值求值时机)
- 这个求值发生在 Python **module import 时**(顶层执行)
- Streamlit 的 secrets → env mirror 可能**尚未完成**,导致 os.getenv 返回空
- 结果:`ValueError: [配置错误] ANTHROPIC_API_KEY 没有设置`

### 修复方式(已在 app.py 内)

`app.py` 顶部显式 mirror,不依赖 Streamlit 隐式行为:

```python
import os
import streamlit as st

# Streamlit Cloud 兼容:显式把 st.secrets 同步到 os.environ
# 为什么:Streamlit 官方说 secrets 自动 mirror,但 2026-07 实测有 timing 问题
# setdefault 而不是直接赋值:尊重外层已设的环境变量(本地 .env)
try:
    for _k, _v in dict(st.secrets).items():
        os.environ.setdefault(_k, str(_v))
except Exception:
    pass  # 本地无 .streamlit/secrets.toml 时 st.secrets 会 raise,忽略

from src.agents.orchestrator import Orchestrator
```

**关键点**:
- 这段代码必须在 `from src.agents.orchestrator import ...` **之前**(业务 import 会触发 config 顶层 os.getenv)
- `os.environ.setdefault` 尊重外层已有环境变量(本地 `.env` 不受影响)
- `try/except` 保证本地无 secrets.toml 时不崩

**面试可讲的一层原则**:适配层放在最边界(app.py 是 Streamlit 入口),不污染业务代码(src/config.py 保持"跨平台通用")。业务代码不应该知道"我可能跑在 Streamlit Cloud 上"。

---

## 七、Step 4 · 验证部署

Deploy 完后拿到 URL(格式类似 `https://listing-agent-<hash>.streamlit.app`)。

**逐项检查**:

- [ ] 打开 URL,页面标题"🤖 亚马逊 Listing 生成 Agent"能显示
- [ ] 左侧"选择店内商品"能选到 Bamboo Cutting Board + Silicone Baking Mat
- [ ] "填表单生成"模式必填字段填完能自动组装 JSON
- [ ] 点"🚀 生成 Listing"后 1-3 分钟内看到 Multi-Agent 循环完成
- [ ] 最终 Listing(Title / 5 Bullets / Backend Keywords)全部出现
- [ ] "🔍 完整运行日志"展开能看到 Agent Loop 每一步
- [ ] Streamlit Cloud 的 "Manage app → Logs" 里没有 ANTHROPIC_API_KEY 报错

---

## 八、Step 5 · 部署后维护

### 更新代码 → 自动 rebuild

```bash
git add .
git commit -m "描述"
git push origin main
```

Streamlit Cloud 会**在 30 秒内检测 GitHub commit,自动 rebuild**(2-3 分钟)。这就是 **Git-based deployment** —— 和 Vercel / Netlify / Railway 一样的心智模型:GitHub 是唯一 source of truth,不要在 Streamlit Cloud 页面直接改代码。

### Sleep-on-idle 行为

免费 CPU basic 有个 **sleep-on-idle** 机制:一段时间无访问会自动睡眠。面试前 24 小时先预热一下,避免面试当场看到"Zzz"页面。唤醒后 10-30 秒可用。

### 监控用量 + 成本控制

- 用量:https://console.anthropic.com/settings/usage(或 closeai 后台)
- **单次完整循环成本**:closeai + Haiku 4.5 约 ¥0.02-0.05,Anthropic 官方 + Sonnet 约 $0.01-0.03
- 想再省钱:model 切 `claude-haiku-4-5`(记忆里已配),Writer + Reviewer 都用 Haiku

---

## 九、Deploy 阶段真实踩坑清单

**踩坑 1(账号级):HF Spaces 免费 cpu-basic quota = 0**
→ 邮箱验证也没用,`hf spaces info` API 才看得到真实 errorMessage `current=0, limit=0`。**教训:平台免费额度看 API 报错,不看营销页**。

**踩坑 2(认证):HF 的 git 认证 `hf auth login` 走浏览器不写 git credential**
→ 必须 `hf auth login --token <token> --add-to-git-credential`。remote URL 里加 `username@` 反而干扰 macOS keychain 匹配。

**踩坑 3(secrets timing):Streamlit Cloud secrets → os.environ mirror 有 timing 问题**
→ 必须在 app.py 顶部显式 mirror(见 Section 六)。**教训:平台"自动"行为不可靠,关键路径显式化**。

**踩坑 4(API key 泄露):secrets 值只在部署页填**
→ 不要复制到聊天工具 / 截图 / commit message / 文档。一旦泄露立刻 revoke + 重建。**教训:secrets 一次泄露永久压力**。

**踩坑 5(git repo private):Streamlit Cloud 免费版只支持 public repo**
→ Repo 要 public,否则 Streamlit 找不到。作品集本来就是给面试官看的,public 反而加分。

**踩坑 6(依赖冲突):Python 版本导致 `st.line_chart` 参数不认**
→ `x_axis_label` / `y_axis_label` 在旧 Streamlit 版本不是合法参数。**教训:LLM 生成代码可能出现"看起来合理但不存在"的 API 参数(hallucination),必须查文档验证**。

**踩坑 7(命名默认):Streamlit Cloud 默认 main file 是 `streamlit_app.py`**
→ 项目入口是 `app.py`,创建时必须改。

---

## 十、部署完成 checklist

- [ ] 本地 `run_cli.py` + `streamlit run app.py` 都跑通
- [ ] GitHub public repo 已推,`.env` 没在 commit history 里
- [ ] Streamlit Cloud app 创建完成,Main file 是 `app.py`
- [ ] Secrets 4 个 key 填完 + 点了 Save
- [ ] `app.py` 顶部有 `st.secrets → os.environ` 显式 mirror 代码
- [ ] 首次 build 完成(2-5 分钟),访问 URL 页面能加载
- [ ] 选商品 + 点生成能跑通,最终 Listing 出现
- [ ] 简历项目行加上 URL
- [ ] 通知 1-2 个朋友帮测,找 bug

---

## 十一、面试可讲的部署经验(2 个层次)

**层次 1:HF quota=0 说明平台选型经验**
> "我先试了 HuggingFace Spaces —— 部署时才发现免费账号 cpu-basic quota = 0(2026-07 政策),必须升级 PRO。我通过 `hf spaces info` API 拿到真实错误信息,判断这是**账号级平台限制,不是我能修的**。转 Streamlit Cloud 5 分钟搞定。**教训:选平台看 API 报错,不看营销页**。"

**层次 2:secrets timing 说明适配层设计**
> "Streamlit Cloud 部署时踩了一个 timing 坑:官方文档说 secrets 自动 mirror 到 os.environ,但实测业务代码顶层的 os.getenv 读不到。修复靠在 app.py 顶部显式 mirror。**这个 fix 的位置很关键:放在 app.py(Streamlit 入口)而不是 src/config.py(业务层),因为业务代码不应该知道自己跑在什么平台**。这是**适配层放在最边界**的实践,和依赖倒置一个思路。"
