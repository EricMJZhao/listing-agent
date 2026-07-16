# 架构设计文档

> 这份文档是面试时给面试官看的架构说明。
> 每个 Sprint 完成一次更新,截至 2026-07-16 已完成 Sprint 0-7,Streamlit Community Cloud 上线,机制上完全成立。

## 一、项目定位

**面向谁**:跨境电商中小卖家(每天发几十个新品的运营)
**解决什么**:把商品属性一句话变成可直接上架的高质量 Listing
**为什么值得做**:2026-07 市场调研 25 个真实 JD 显示,6 家跨境电商公司(积加、易佰、谱程、云从、店管家、母婴出海品牌)都在直接招"跨境电商 AI Agent 工程师",Listing 优化是他们最想要的 Agent 动作之一。

## 二、跟 ChatGPT 直接问的差异化

面试第一问必定是 "跟 ChatGPT 直接问有什么区别",答案有 5 条:

| 差异化点 | 对应技术 | Sprint |
|---|---|---|
| 我挂了 Amazon 类目关键词知识库 | RAG · BM25 精确匹配 | 1 |
| 我参考了 Best Seller 竞品 Listing | RAG · 竞品 Title 库 | 1 |
| 我会自己审自己(写完打分不达标就重写) | Multi-Agent(Reviewer) | 2 |
| 我能主动查 Amazon 数据决策(搜索量、字节数) | Function Calling · 自研 Agent Loop | 3 |
| 我有独立的质量评估层,可以做 A/B 对比 | LLM as Judge · Batch Eval | 4 |

## 三、架构演进(Sprint 0-7)

### Sprint 0:单 Agent 端到端

```
用户 → run_cli.py → WriterAgent → Claude API → Listing JSON
```

**为什么先做这个**:验证 API 链路、验证 Prompt 设计。Agent 项目最常见死法是一上来搞 Multi-Agent 什么都做不完。

**技术决策**:
- 用 Anthropic 官方 SDK 而不是 LangChain:出海母婴 JD 明写"非纯调 LangChain / Dify",自己控制调用能面试时讲清楚每一层。
- 主模型 `claude-opus-4-8`(可切 `claude-sonnet-5` 省钱)。
- 输出强制 JSON:为 Sprint 2 的 Reviewer 消费做准备。

### Sprint 1:RAG(BM25)

```
用户 → WriterAgent
        ├─ KeywordStore.search_keywords("bamboo cutting board") → top 20 关键词
        ├─ KeywordStore.get_competitor_titles() → top 3 Best Seller Title
        └─ 把上面两坨作为 context 塞进 Prompt → Claude
```

**技术决策**:
- **BM25 不用向量库**:跨境电商关键词是精确匹配需求,不是语义泛化。BM25 零依赖、快、准。Sprint 4 后加"竞品评论洞察"才切向量库。
- **Graceful Fallback**:没类目关键词库时自动跳过 RAG,当 Sprint 0 单 Agent 跑。**单点缺失不阻塞流程**,是全项目一贯的哲学。
- **懒加载 + 缓存**:KeywordStore 首次用到才加载,同一个 WriterAgent 实例跨轮次复用。

### Sprint 2:Multi-Agent 自研循环

```
用户 → Orchestrator
        ├─ Round 1:WriterAgent 生成初稿
        ├─ ReviewerAgent 审(硬规则代码 + 软规则 LLM)
        │
        ├─ (通过) → 输出 Listing
        │
        └─ (不通过) → fix_hint 塞回 Writer.rewrite()
              ├─ Round 2:同上
              ├─ Round 3:max_rounds 到顶
              └─ 择优输出得分最高那一轮
```

**技术决策**:
- **BaseAgent 基类**:_call_llm / _parse_json_response / _log 上移,子类只关注独有逻辑。**为 Sprint 3 加 Agent Loop 铺路**。
- **硬规则 vs 软规则**:硬规则(字符数、字节数、条数、禁用词)走代码 100% 准;软规则(利益先行、语义)走 LLM Haiku 判断。**能被代码算准的事不该给 LLM**。
- **max_rounds=3 + 择优输出**:实测标定的收敛率 vs 成本最优点;应对 Multi-Agent 系统的震荡问题(Writer 修一个可能牺牲另一个)。
- **Model Fallback**:BaseAgent 内建 —— 指定 model 不可用时自动降级到默认 model,单点故障不阻塞。

### Sprint 3:Function Calling + 自研 Agent Loop

```
用户 → WriterAgent
        └─ _tool_use_loop(system, user, tools=[keyword_volume, check_bytes])
              │
              ├─ Claude 返回 stop_reason="tool_use"
              ├─   → 执行 tool → 结果塞回 messages
              ├─ Claude 返回 stop_reason="tool_use"(再调另一个)
              ├─   → 执行 → 塞回
              └─ Claude 返回 stop_reason="end_turn" → 输出 Listing JSON
```

**技术决策**:
- **自研 Agent Loop,不用 LangChain**:30 行代码手写 `stop_reason` 状态机,面试能讲清楚 tool_use block 结构、messages 拼接协议、终止条件。
- **两个 mock tools**:`search_keyword_volume` 查月搜索量 + 竞争度,`check_text_bytes` 估算字节数。**mock 是故意的**,让面试演示可预测、可复现,生产接真 API 只换 impl 函数。
- **Tool 是建议不是强制**:Prompt 明确写"不是每次都要调,只在需要决策依据时调"。**LLM 应该有 agency**。
- **max_iterations=8**:防死循环,实测大多数 case 4 轮以内结束。

### Sprint 4:LLM as Judge + Batch Eval

```
Orchestrator 生成 Listing
    │
    ├─ Reviewer(流程内 gate):pass/fail + issues,决定是否重写
    │
    └─ Judge(离线评估):0-100 分 · 4 维度 · 强弱项分析
          │
          └─ batch_eval.py: N 类目 × K 采样 → 统计表
                (通过率 · 平均轮次 · 平均分 · 方差)
```

**技术决策**:
- **Reviewer 和 Judge 拆开**:Reviewer 是流程内 gate,Judge 是离线评估。**混在一起后果是调 Reviewer 阈值,离线评估基线全失效**。
- **Judge 用最强模型**:Reviewer 用 Haiku 是判断题够,Judge 是评估层要精准,应该用 Opus。
- **多次采样取中位数**:LLM as Judge 单次打分 ±10 波动,n_samples=3 降到 ±3。

### Sprint 5:Streamlit UI + 部署

```
面试官打开 URL
        │
        ▼
Streamlit App (app.py)
    ├─ 侧栏:选样品 / 上传 JSON / 调 max_rounds
    ├─ 主区:调 Orchestrator.run() → 渲染循环轨迹 + Listing 分区
    └─ 部署:Streamlit Community Cloud(免费)+ Anthropic 官方 Key
```

**技术决策**:
- **展示层 vs 业务层完全解耦**:app.py 零业务逻辑,只调 Orchestrator。明天换 FastAPI + Vue,业务代码零改动。
- **Streamlit 不用 React**:作品集时间成本 > UI 精美。Streamlit 3 小时,React 20 小时。
- **部署切官方 Key**:公司中转平台在内网公网访问不到,切 Anthropic 官方 Key。config.py 早支持 base_url 空自动走官方 —— **Sprint 0 抽 llm_client 时留的接缝在 Sprint 5 兑现**。

### Sprint 6:Amazon API 逆向 + 静态 RAG + 真实 API tool + YAML 配置化(2026-07-16)

**做什么**:6 个 Task
1. 逆向 Amazon 前台搜索建议接口,剥离 20+ 参数到 5 个核心参数
2. v0.1 单次调用(40 行)验证老 endpoint `completion.amazon.com` 无 session
3. v0.2 BFS 递归 + 双 set 去重 + rate limit + 单点降级 → 88 词/种子
4. v0.2.5 硬编码多种子采集 → 379 词/类目(踩短种子坑得到经验)
5. Task 4 静态 RAG 集成:词库注入 KeywordStore,Writer title 出现 Macaron/Silpat/OXO
6. Task 5 包装成 Function Calling tool:Sprint 3 抽象层复用,base.py 零改
7. Task 3 v0.3 YAML 配置化:1:N 种子 + fail-fast 配置校验 → 803 词/类目

**架构**:
```
config/categories/baking.yaml
        │
        ▼
amazon_suggest.load_category_config()
        │
        ▼
amazon_suggest.batch_fetch(sub_categories, ...)
        │  (BFS + 双 set 去重 + 单点降级 + rate limit)
        ▼
data/keywords/baking_all_depth2.json       (原始产出,带 depth+parent 图结构)
        │
        ▼
amazon_suggest.export_to_knowledge_base()
        │
        ▼
data/knowledge_base/baking_keywords.json   (KeywordStore 兼容格式)
        │
        ▼
Sprint 1 的 KeywordStore + BM25(一行没改!)
        │
        ▼
Writer Agent(通过 CATEGORY_KB_MAP 找到词库)

  【另一条路径】
        │
amazon_suggest.SEARCH_AMAZON_KEYWORDS_SCHEMA + _tool_impl_...
        │  (mock_tools.py 底部 append 3 行注册)
        ▼
Sprint 3 的 execute_tool dispatcher(base.py 一行没改!)
        │
        ▼
Writer 运行时自主决定要不要联网查
```

**技术决策**:
- **老 endpoint vs 前台**:前台 `www.amazon.com/suggestions` 依赖 session,老接口 `completion.amazon.com` 无 session 稳定。这是 Amazon 前后台架构分层的常见特征。
- **BFS 不 DFS**:采集任务需要可中断,BFS 先浅后深,Ctrl+C 时保留完整浅层。
- **双 set 去重**:`expanded` 管 prefix 展开,`collected` 管结果收录。避免自引用词漏收。
- **单点降级 vs fail-fast**:网络错 warning continue(不能整体崩),配置错立即抛(不能跑到一半崩)。**两种错的处理策略必须相反**。
- **1:N 种子**:v0.2.5 单种子 379 词,发现同义表达覆盖不全。v0.3 每个子类目 1-3 短种子(如 piping = piping bag + piping tip + pastry bag)后 803 词。
- **YAML 而不是 JSON**:业内标准 + 支持注释 + 给人读的。
- **静态 + 动态双通道**:静态词库保速度稳定性,动态 tool 保覆盖广度。90% 场景走静态,10% 冷门走动态。**这就是工业级 Agent 做法,不是学院派 demo**。
- **抽象层复利**:Sprint 3 的 schema/impl/dispatcher 三件套,Sprint 6 加真实 API 只加 3 行注册。Sprint 1 的 KeywordStore 接口,Sprint 6 词库翻倍不用改。**Sprint 花的时间是本金,后面 Sprint 是利息**。

**产出**:
- 803 个 unique keywords(vs Sprint 1 的 30 个,提升 27 倍)
- 5 个烘焙子类目覆盖
- Writer Agent 生成 title 直接 name-drop 真实用户搜索的品牌词
- 加新类目从改 3 处 Python 变成写 1 个 YAML

详细数据洞察 + 面试话术库见 [`docs/sprint6_findings.md`](sprint6_findings.md)。

### Sprint 7:Streamlit Cloud 上线 + UI 商业化(2026-07-16)

**做什么**:
1. HF Spaces 尝试失败(免费 cpu-basic quota=0 政策)→ 转 Streamlit Community Cloud
2. app.py 顶部加 `st.secrets → os.environ` 显式镜像(适配 Streamlit Cloud secrets timing 问题)
3. README 加 HF frontmatter(为兼容留着,不影响 Streamlit Cloud)
4. UI 商业化改造:
   - 类目精准化:"跨境电商" → "Amazon.com · Home & Kitchen > Kitchen & Dining"
   - 文案:样品 → 店内商品
   - 侧栏样品显示读 JSON 的 product_type + category_leaf 生成友好 label
   - 加"填表单生成"输入模式:必填 3 字段 + 选填 5 字段 + 万能 key=value 自定义属性
   - 主页删项目介绍/技术文档/命令行提示,极简化引导

**架构**:
```
GitHub (source of truth)
        │
        ▼ (git push 触发 auto-rebuild)
Streamlit Community Cloud runtime
        │
        ▼ (启动时把 secrets 加载到 st.secrets)
app.py 顶部:
    try:
        for k, v in dict(st.secrets).items():
            os.environ.setdefault(k, str(v))
    except: pass
        │
        ▼ (业务代码 import,src/config.py 顶层 os.getenv 能命中)
Orchestrator → Writer + Reviewer → BaseAgent → Claude API
                                                   │
                                                   ▼
                                        Anthropic 或 closeai(base_url 切)
```

**技术决策**:
- **平台选型看 API 报错,不看营销页**:HF Spaces 官网说免费 cpu-basic,实际账号级 quota=0(2026-07 政策)。靠 `hf spaces info` API 才拿到真实 errorMessage(`current=0, limit=0`)。Streamlit Cloud 无 quota 限制,更适合免费个人项目。
- **secrets 显式 mirror 放在 app.py 而不是 src/config.py**:**适配层放在最边界**,业务代码保持"跨平台通用"。业务代码不应该知道自己跑在什么平台 —— **依赖倒置**。
- **`os.environ.setdefault` 而不是 `os.environ[k] = v`**:尊重外层已有环境变量,本地 `.env` 优先。同一段适配代码本地和云端行为一致,只是数据源不同。
- **try/except 兜底**:本地无 `.streamlit/secrets.toml` 时 `st.secrets` 访问会 raise,忽略即可,`python check_env.py` / `run_cli.py` 不受影响。
- **UI 文案商业化**:"样品"是实验室词(sample),"店内商品"是商业词(product in your store)。同一个技术产品换个词就换个人设,面向电商卖家的 agent 应该说卖家的语言。
- **表单三层输入模式**:店内商品(零输入)→ 填表单(30 秒)→ 粘贴 JSON(技术用户)。**progressive disclosure**:新手看到最简界面,高级用户按需展开。
- **类目精准到 Kitchen & Dining**:上位类 "Home & Kitchen" 过泛,精确到子类目反而显得专业 —— **能说清楚不做什么才证明知道做什么**。

**产出**:
- 面试可分享的公网 URL(Streamlit Community Cloud)
- GitHub public repo(源码托管 + 面试官可看代码)
- 表单模式覆盖非技术用户:面试官不用会写 JSON,填 3 个字段就能试
- 完整部署踩坑记录 → 见 [`docs/DEPLOY.md`](DEPLOY.md)

## 四、贯穿全项目的设计哲学

### Graceful Degradation(3 处贯穿)

| 位置 | 触发 | 降级动作 |
|---|---|---|
| BaseAgent._call_llm | 指定 model 不可用 | 自动降级到默认 model + warning |
| WriterAgent(RAG) | 类目无关键词库 | 跳过 RAG,当 Sprint 0 单 Agent 跑 |
| Orchestrator | max_rounds 到顶未通过 | 输出得分最高那一轮 + 未解决问题清单 |

**核心思想**:**单点缺失不阻塞整体流程**。三个位置同一个设计哲学,不是随手加的。

### 接口稳定 + 实现可替换(为 Sprint 演化预留接缝)

| 接缝 | 何时留 | 何时兑现 |
|---|---|---|
| `llm_client.py` 抽象层 | Sprint 0 | Sprint 5 部署切官方 Key + Sprint 7 切 closeai,一行不改 |
| `BaseAgent` 基类 | Sprint 2 Step 1 | Sprint 3 加 Agent Loop,所有 Agent 自动受益 |
| `dict → dict` 统一接口 | Sprint 2 | Sprint 5 UI 展示层无痛接入 |
| `reporting.py` 打印函数抽出 | Sprint 5 前 | Streamlit UI 复用 CLI 的打印逻辑 |
| `RuleIssue dataclass` | Sprint 2 Step 2 | Sprint 4 Judge 复用同一个 issue 数据结构 |
| `mock_tools.py` schema/impl/dispatcher 三件套 | Sprint 3 | Sprint 6 加真实 Amazon API tool 只加 3 行注册,base.py 零改动 |
| `os.getenv` 读环境变量 | Sprint 0 | Sprint 7 部署时用 `st.secrets → os.environ` 显式 mirror 注入,业务代码零改 |

**核心思想**:**架构演化不是拍脑袋改,是提前留接缝**。每次抽象都是复利。

## 五、技术选型 & 理由

| 选择 | 理由 |
|---|---|
| Python 3.10+ | Anthropic SDK 官方主力语言 |
| Anthropic Python SDK | 官方支持 tool use、streaming、prompt caching |
| Claude Opus 4.8(主)+ Haiku 4.5(评估) | 分层用模型:贵的用在写作 + Judge,便宜的用在 Reviewer |
| 自研 Agent Loop | JD 要求"非纯调 LangChain",能面试讲清楚每一层 |
| BM25 而非向量库 | 跨境电商关键词是精确匹配需求,不是语义泛化 |
| JSON 文件当数据源 | 作品集不需要 Postgres,简单直接,git 追踪方便 |
| Streamlit 演示 UI | 3 小时能起界面,方便面试演示 |
| Streamlit Community Cloud | 免费部署,不用买服务器 |

## 六、实测数据(5 次完整循环,面试演示核心素材)

| # | 类目 | 阶段 | Round 1 → Round N | 最终得分 |
|---|---|---|---|---|
| 1 | 竹制切菜板 | Sprint 2 无 RAG 无 tool | Backend 257 ✗ → 修复到 206 ✓ | 92 |
| 2 | 硅胶烘焙垫 | Sprint 2 无 RAG 无 tool | banned_words 'PERFECT' ✗ → 修复 ✓ | 100 |
| 3 | 竹制切菜板 | Sprint 1 有 RAG 无 tool | Backend 263 ✗ → 修复到 213 ✓ | 100 |
| 4 | 竹制切菜板 | Sprint 3 Opus + RAG + tool | 1 轮通过!Backend 244/249 | 92 |
| 5 | **竹制切菜板** | **Sprint 5 部署后 · Haiku + RAG + tool** | **1 轮通过!Backend 192/249** | **88** |

**核心观察**:
- Sprint 2 让 Sprint 0 的 257 字节 bug 自动修复
- Sprint 3 tool_use 让 Writer 提前调 tool 避免违规,从 2 轮通过变成 1 轮通过
- **Sprint 5 部署切 closeai 后 Writer + Reviewer 都用 Haiku,依然 1 轮通过** —— 演示环境成本 <¥0.05
- 不同类目触发不同硬规则,同一套循环机制都能修
- LLM 输出有天然波动,max_rounds=3 是保守合理的实测标定

## 七、已知短板 & 面试反问答案

**Q:你的类目关键词库怎么来的?**
A:起步 30 词来自 Amazon 搜索栏建议词 + 8 年销售经验直觉。`data/knowledge_base/TEMPLATE.md` 里写了 200 词扩充指引 —— 3 个来源(Amazon 搜索栏、Helium10 免费额度、销售经验)、6 类结构、时间预算 2-3 小时。作品集不追求全类目覆盖,能演示"RAG 有效"就够。

**Q:为什么不直接用 GPT-4?**
A:我做的是国内 hiring manager 会看的作品。国内头部 Agent 团队(澜舟、深信服、亚信、Dify)当前主推 Claude 生态 —— 长上下文 1M、Tool Use 稳定、Prompt Caching 便宜。选 Claude 是跟目标岗位技术栈对齐。

**Q:怎么验证生成的 Listing 真的好?**
A:三层验证。硬规则代码 100% 准。Sprint 4 的 Judge 打 0-100 分 + 多次采样降波动。Sprint 4 的下一步是加人工标注黄金基准集校准 —— 作品集阶段还没做到那一步。

**Q:真上生产要考虑什么?**
A:四件事 ——
1. **成本**:现在 fallback 到 Opus 一份 ¥0.3,加 Prompt Caching 降到 ¥0.1;Judge 换 sonnet-5 可以再降。
2. **多语种**:Sprint 1 后加 en-US / ja-JP / de-DE 三套 Prompt,逻辑复用。
3. **合规**:Reviewer 的禁用词列表要跟 Amazon TOS 演化同步,接 web scraper 定期同步官方禁用词。
4. **规模**:生产要 50-100 个 case 自动回归 + 批量 A/B 对比,Sprint 4 的 batch_eval 机制已经支持,只是数据没做大。

**Q:Sprint 4 的 Judge 会不会 self-favoring(同一个 LLM 给自己打分虚高)?**
A:会,这是 LLM as Judge 的固有问题。三个缓解方案:(1) 多次采样取中位数,我做了;(2) 跨 provider 交叉(Claude + GPT-4);(3) 人工标注黄金基准集校准。作品集阶段做到第 1 层,第 2/3 层预留在 Sprint 4 下一步。
