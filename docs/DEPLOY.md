# 部署指南 · Streamlit Community Cloud

> 目标:让面试官能通过一个 URL 远程访问你的 Listing Agent 演示。

## 前置条件

- [x] GitHub 账号
- [x] Anthropic API Key(去 https://console.anthropic.com/ 拿,新账号有 $5 免费额度)
- [x] 项目代码已经能本地跑通

---

## Step 1 · 本地验证 Anthropic 官方 Key 能跑通(部署前必做)

**先切换到官方 API 跑一次,确认没问题再部署** —— 别到 Streamlit Cloud 才发现代码有 bug。

### 1.1 临时改 `.env`

```env
# 注释掉公司中转平台
# ANTHROPIC_API_KEY=blueai-xxx
# ANTHROPIC_BASE_URL=https://bmc-llm-relay.bluemediagroup.cn

# 用 Anthropic 官方
ANTHROPIC_API_KEY=sk-ant-your-real-key
LISTING_AGENT_MODEL=claude-sonnet-5   # 省钱模式;跑通再切 opus
```

### 1.2 本地跑一次

```bash
python check_env.py                                    # 先验证 key 通
python run_cli.py data/sample_products/product_1.json  # 端到端
```

**跑通了才进 Step 2**。跑不通不要往下 —— 先解决问题。

### 1.3 跑 Streamlit UI

```bash
pip install streamlit
streamlit run app.py
```

浏览器会自动打开 http://localhost:8501。**验证能生成 Listing 后再部署**。

---

## Step 2 · 建 GitHub 仓库

```bash
cd /Users/eric/projects/listing-agent

# 初始化 git(如果还没做)
git init
git branch -M main

# 检查什么会被提交(确认 .env 不在里面!!)
git status

# 添加 + 提交
git add .
git commit -m "Sprint 0-5 complete: Multi-Agent + RAG + Tool Use + UI"

# 推到 GitHub(先去 github.com 建一个 public repo 叫 listing-agent)
git remote add origin https://github.com/<你的用户名>/listing-agent.git
git push -u origin main
```

**关键**:`git status` 或者 `git log --stat` 检查 `.env` 文件**没有**被提交 —— 有的话 API Key 就泄露到公网了。

---

## Step 3 · 部署到 Streamlit Community Cloud

### 3.1 登录

打开 https://share.streamlit.io/ → 用 GitHub 账号登录 → 授权访问你的 repos。

### 3.2 创建 App

- 点 "New app"
- Repository: `<你的用户名>/listing-agent`
- Branch: `main`
- Main file path: `app.py`
- App URL: `listing-agent-<你的用户名>.streamlit.app`(自动生成,可自定义子域名)

### 3.3 设置 Secrets(**关键一步**)

在 App Settings → Secrets,粘贴:

```toml
ANTHROPIC_API_KEY = "sk-ant-your-real-key"
LISTING_AGENT_MODEL = "claude-sonnet-5"
```

**注意**:
- 不要设 `ANTHROPIC_BASE_URL`(让 SDK 走官方)
- 用 sonnet-5 而不是 opus-4-8,省钱 5 倍,面试演示够用

### 3.4 点 "Deploy"

等 2-3 分钟(Streamlit 装依赖 + 启动)。

**首次部署可能报错**:
- `ModuleNotFoundError`: 检查 `requirements.txt` 是否完整
- `KeyError: ANTHROPIC_API_KEY`: Secrets 没设好
- `403 Forbidden`: API Key 无效

---

## Step 4 · 拿到 URL,面试用

部署成功后你会拿到:
```
https://listing-agent-<你的用户名>.streamlit.app
```

**面试时**:
1. 简历项目行加上这个 URL
2. 面试开场发给面试官:"这是我的项目在线 demo,你可以自己试"
3. 现场演示时打开这个 URL,不需要装环境

---

## Step 5 · 部署后的维护

### 更新代码

```bash
# 本地改代码后
git add .
git commit -m "描述"
git push origin main
```

Streamlit Cloud 会**自动重新部署**(2-3 分钟)。

### 监控用量

- Anthropic 用量:https://console.anthropic.com/settings/usage
- **$5 免费额度 = 约 500K tokens = 15-25 次完整循环**
- 想省钱:模型切 `claude-haiku-4-5-20251001` 或 `claude-sonnet-5`

### 加访问密码(防面试官之外的人乱调)

Streamlit Cloud 支持 SSO / 邮箱白名单,在 App Settings → Sharing 里设。

---

## 部署踩坑清单

**踩坑 1**:忘了在 GitHub 上 gitignore `.env`,API Key 泄露
→ **必检查**:`git log --all --oneline -p -- .env`,如果有内容,**立刻去 Anthropic 后台 revoke 那个 key + 生成新的**

**踩坑 2**:Streamlit Cloud 上跑 Orchestrator 超时(默认 30 秒)
→ 我们的循环可能 1-3 分钟,Streamlit Cloud 上没超时限制(它是 long-running app),但**用户可能等不及关掉**。建议在 UI 里加 spinner + 进度提示(已加)

**踩坑 3**:公司中转平台的 model ID 跟官方不一样
→ 官方支持:`claude-sonnet-5-20250929`, `claude-opus-4-8-20250929`, `claude-haiku-4-5-20251001`
→ 完整列表:https://docs.claude.com/en/docs/about-claude/models

**踩坑 4**:sample_products 里的数据不合规(JSON 语法错)
→ 部署前用 https://jsonlint.com/ 校验一遍

---

## 部署完成的 checklist

- [ ] 本地用官方 Key 跑通 `run_cli.py`
- [ ] 本地用官方 Key 跑通 `streamlit run app.py`
- [ ] GitHub repo 已推上,`.env` 没被提交
- [ ] Streamlit Cloud 已部署,secrets 设好
- [ ] 打开公网 URL 能生成 Listing
- [ ] 简历项目行加上 URL
- [ ] 通知一个朋友帮你测一下(找 bug)
