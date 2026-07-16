---
title: Listing Agent
emoji: 🤖
colorFrom: red
colorTo: blue
sdk: streamlit
sdk_version: 1.30.0
app_file: app.py
pinned: false
---

# Listing Agent · Amazon Home & Kitchen Multi-Agent Copilot

> **FDE / AI 应用工程师面试作品集项目**
> 作者:Eric(前阿里国际站销售 8 年 + AI 应用开发)

## 🚀 在线演示

**Streamlit Cloud**:`https://listing-agent-<你的子域>.streamlit.app`(GitHub push 后自动重新部署)
**源码**:https://github.com/EricMJZhao/listing-agent

面试官打开链接 → 侧栏选一个店内商品(或填表单)→ 点"生成 Listing" → 3 分钟内看到 Multi-Agent 循环完整过程 + 最终交付 Listing。

## 这是什么

针对 **Amazon.com · Home & Kitchen > Kitchen & Dining 类目**的 AI Copilot:**输入商品属性 → 输出可直接发布到 Amazon 后台的完整 Listing**(Title + 5 Bullet + Backend Keywords + Search Terms)。比人工快 20 倍,比直接问 ChatGPT 强在:
- **有类目关键词知识**(RAG · BM25 检索 · 803 词自动采集)
- **能自我审核和修正**(Writer ↔ Reviewer 循环)
- **会主动查数据决策**(Function Calling · 自研 Agent Loop + 真实 Amazon API)
- **配置驱动扩展**(YAML 加新类目零代码)

## 5 个技术亮点

| # | 亮点 | 说明 |
|---|---|---|
| 1 | **自研 Multi-Agent 闭环** | Writer + Reviewer + Orchestrator,max_rounds=3 + 择优输出 |
| 2 | **RAG(BM25 精确匹配)+ 自动化词库** | 类目关键词库(自动采集 800+ 词) + 竞品 Title,Writer 有据可依 |
| 3 | **自研 Agent Loop(tool_use)+ 真实 API tool** | 30 行 `stop_reason` 状态机 + Amazon 搜索建议真实 API 集成 |
| 4 | **Graceful Degradation** | model fallback + RAG fallback + 单点降级,单点故障不阻塞 |
| 5 | **配置驱动扩展** | YAML 配置化,加新类目不改一行代码 |

## 快速体验(3 步)

```bash
# 1. 装依赖
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 2. 配 API Key(拷贝 .env.example 成 .env 填 sk-ant-xxx)
cp .env.example .env
python check_env.py    # 验证 Key 通不通

# 3. 跑 Web UI(推荐)或 CLI
streamlit run app.py                              # 浏览器 http://localhost:8501
python run_cli.py data/sample_products/product_1.json    # CLI 版
```

## 项目形态(8 个 Sprint,已完成 8 个)

| Sprint | 内容 | 涉及技术 | 状态 |
|---|---|---|---|
| 0 | 单 Agent 端到端(输入 → LLM → 输出) | Prompt 工程 + Anthropic SDK | ✅ 完成 |
| 1 | RAG(类目关键词库 + 竞品 Listing) | BM25 + Graceful Fallback | ✅ 完成 |
| 2 | Multi-Agent 循环(Writer + Reviewer + Orchestrator) | 自研 Agent 编排 + 硬软规则分离 | ✅ 完成 |
| 3 | Function Calling + 自研 Agent Loop | Tool Use + `stop_reason` 状态机 | ✅ 完成 |
| 4 | LLM as Judge + Batch Eval | 独立评估层 + 多次采样降波动 | ✅ 完成 |
| 5 | Streamlit UI + 部署 | 展示层解耦 + 公网 URL | ✅ 完成 |
| 6 | Amazon API 逆向采集 + 静态 RAG + 真实 API tool + YAML 配置化 | BFS 递归 + 双 set 去重 + Function Calling 真实 API + 配置驱动 | ✅ 完成 |
| **7** | **Streamlit Cloud 上线 + UI 商业化改造** | **st.secrets → env 显式镜像 · 表单化输入 · 类目精准化描述** | ✅ **完成** |

## 目录结构

```
listing-agent/
├── README.md                       ← 本文件
├── app.py                          ← Streamlit UI 入口(Sprint 5)
├── run_cli.py                      ← CLI 入口
├── batch_eval.py                   ← 批量评估脚本(Sprint 4)
├── check_env.py                    ← 环境检查
├── test_rules.py                   ← 硬规则单元测试
├── test_reviewer.py                ← Reviewer 端到端测试
├── test_orchestrator.py            ← 循环回归测试
├── test_rag.py                     ← RAG 检索测试
├── requirements.txt
├── .env.example
├── .streamlit/                     ← Streamlit 部署配置
│
├── docs/
│   ├── DESIGN.md                   ← 架构设计文档
│   ├── DEMO.md                     ← 面试演示脚本(10 部分)
│   ├── bad_cases.md                ← 真实翻车 case 记录
│   └── DEPLOY.md                   ← 部署完整指南
│
├── data/
│   ├── sample_products/            ← 测试用商品样品
│   │   ├── product_1.json          ← 竹制切菜板
│   │   └── product_2.json          ← 硅胶烘焙垫
│   ├── knowledge_base/             ← RAG 知识库(Sprint 1 起步 + Sprint 6 自动化)
│   │   ├── cutting_board_keywords.json    ← 30 词(手工)
│   │   ├── baking_keywords.json           ← 803 词(Sprint 6 自动采集)
│   │   └── TEMPLATE.md             ← 200 词扩充模板
│   └── keywords/                   ← Sprint 6 采集器原始产出
│       └── baking_all_depth2.json  ← 带 depth+parent 图结构
│
├── config/                         ← Sprint 6 加入,配置驱动
│   └── categories/
│       └── baking.yaml             ← 类目配置(加新类目只改这里)
│
└── src/
    ├── config.py                   ← 全局配置(模型/Key/base_url)
    ├── llm_client.py               ← Anthropic SDK 抽象层
    ├── reporting.py                ← 打印函数(CLI + UI 共用,Sprint 5)
    │
    ├── agents/
    │   ├── base.py                 ← BaseAgent(model fallback + Agent Loop)
    │   ├── writer_agent.py         ← Writer(RAG + tool_use)
    │   ├── reviewer_agent.py       ← Reviewer(硬 + 软规则)
    │   └── orchestrator.py         ← Multi-Agent 循环协调
    │
    ├── prompts/
    │   ├── writer.py               ← 首稿 + 重写 Prompt
    │   └── reviewer.py             ← Reviewer Prompt
    │
    ├── evaluation/
    │   ├── rules.py                ← 硬规则检查器(纯代码 100% 准)
    │   └── judge.py                ← LLM as Judge(Sprint 4)
    │
    ├── rag/
    │   └── keyword_store.py        ← BM25 + KeywordStore(Sprint 1)
    │
    └── tools/
        ├── mock_tools.py           ← mock tools + schema + registry(Sprint 3)
        └── amazon_suggest.py       ← Amazon 采集器 + 真实 API tool(Sprint 6)
```

## 关键实测数据(面试演示用)

跑了 5 次完整循环,**全部收敛通过**:

| # | 类目 | 阶段 | Round 1 → Round N | 最终得分 |
|---|---|---|---|---|
| 1 | 竹制切菜板 | Sprint 2 无 RAG 无 tool | Backend 257 ✗ → 修复到 206 ✓ | 92 |
| 2 | 硅胶烘焙垫 | Sprint 2 无 RAG 无 tool | banned_words ✗ → 修复 ✓ | 100 |
| 3 | 竹制切菜板 | Sprint 1 有 RAG 无 tool | Backend 263 ✗ → 修复到 213 ✓ | 100 |
| 4 | 竹制切菜板 | Sprint 3 有 RAG 有 tool | 1 轮直接通过!Backend 244/249 | 92 |
| 5 | **硅胶烘焙垫** | **Sprint 6 有 803 词 RAG + 真实 Amazon tool** | **Writer 主动调 `search_amazon_keywords`,生成 title 含 Macaron/Silpat/OXO** | **88-92** |

**Sprint 6 演示重点**:Writer 生成的 title/bullets 里**直接出现真实用户搜索的品牌词**(Silpat / OXO / Wilton)+ 领域文化词(macaron / bundt),这是 803 词自动化词库 + Function Calling 真实 API 的价值证明。

## Sprint 6 快速采集(加新类目零代码)

```bash
# 采集烘焙类目(已配置好 config/categories/baking.yaml)
python -m src.tools.amazon_suggest --category baking

# 加新类目(例:户外用品)零代码:
# 1. cp config/categories/baking.yaml config/categories/outdoor.yaml
# 2. 编辑 outdoor.yaml,改 name / seeds
# 3. 跑同一条命令
python -m src.tools.amazon_suggest --category outdoor
```

## 面试演示

**如果面试有屏幕共享**:参考 [`docs/DEMO.md`](docs/DEMO.md) Part 4 的现场演示指引,每一步都有该讲的话。

**如果面试官在远程**:项目已经部署到 Streamlit Community Cloud(见页首"在线演示"),直接把 URL 发给面试官 —— 不需要装 Python。首次访问自动 rebuild。部署踩坑记录 + 完整流程见 [`docs/DEPLOY.md`](docs/DEPLOY.md)。

## 文档指引

| 文档 | 用途 |
|---|---|
| [`docs/DESIGN.md`](docs/DESIGN.md) | 架构设计 + 每个 Sprint 的设计决策 |
| [`docs/DEMO.md`](docs/DEMO.md) | 面试演示脚本(10 部分,可以背) |
| [`docs/sprint6_findings.md`](docs/sprint6_findings.md) | **Sprint 6 数据洞察 + 完整面试话术库(强推)** |
| [`docs/bad_cases.md`](docs/bad_cases.md) | 真实翻车 case + 面试话术 |
| [`docs/DEPLOY.md`](docs/DEPLOY.md) | 部署到 Streamlit Cloud 完整流程 |
| [`data/knowledge_base/TEMPLATE.md`](data/knowledge_base/TEMPLATE.md) | 200 词关键词库扩充指南(Sprint 6 后自动化) |
| [`config/categories/baking.yaml`](config/categories/baking.yaml) | 类目采集配置模板 |

## 技术栈总览

**AI/LLM**:Anthropic Claude API · Multi-Agent 编排 · 自研 Agent Loop · Prompt Engineering · JSON Schema · Tool Use(mock + 真实 API) · LLM as Judge

**编程**:Python 3.10+ · Anthropic SDK · rank-bm25 · Streamlit · requests · pyyaml · argparse · BFS 递归 · fail-fast 配置校验

**部署**:GitHub git-based auto-deploy · Streamlit Community Cloud · st.secrets → os.environ 显式镜像(适配 Streamlit Cloud timing 问题)

**领域**:Amazon A9 SEO · 跨境电商 Listing 优化 · Amazon TOS 禁用词规则 · Amazon 搜索建议接口逆向

## Related

- 后续同一作品集会加另外 2 个 Agent(3 Agent 组合):
  - Agent 2:Amazon PPC 广告调价 Agent(Multi-Agent 决策)
  - Agent 3:卖家数据 ChatBI Agent(Text-to-SQL + Code Interpreter)
