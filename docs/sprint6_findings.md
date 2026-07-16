# Sprint 6 数据洞察 + 面试话术库

> Sprint 6(2026-07-16 完成):从 Amazon 官方搜索建议接口自动采集烘焙类目关键词库,
> 静态 RAG 集成 + Function Calling 真实 API 集成 + YAML 配置驱动。
>
> **词库产出**:
> - v0.2.5 硬编码多种子:379 unique keywords
> - v0.3 YAML 1:N 种子:**803 unique keywords**(翻倍以上)

---

## 一、Sprint 6 完整技术版图

### 版本演进

| 版本 | 能力 | 单类目产出 | 关键设计决策 |
|---|---|---|---|
| v0.1 | 单次调用 | 10 词 | 老 endpoint `completion.amazon.com` 无 session |
| v0.2 | BFS 递归 + rate limit | 88 词/种子 | 双 set 去重 + 单点降级 + BFS 可中断 |
| v0.2.5 | 硬编码多种子 | 379 词/类目 | 短种子策略(踩坑得来) |
| **v0.3** | **YAML 配置驱动 + 1:N 种子** | **803 词/类目** | **fail-fast 配置校验 + 单点降级并存** |
| v0.4 | Function Calling tool | (Agent 运行时调用) | Sprint 3 抽象层复用,base.py 零改动 |

### 5 个核心资产

1. `src/tools/amazon_suggest.py` —— 采集器 + tool 定义(4 层 API)
2. `config/categories/baking.yaml` —— 类目配置模板(加新类目只改这个)
3. `data/keywords/baking_all_depth2.json` —— 803 词原始数据(带 depth + parent 图结构)
4. `data/knowledge_base/baking_keywords.json` —— KeywordStore 兼容格式
5. Writer Agent CATEGORY_KB_MAP 新增 5 个烘焙 product_type 映射

---

## 二、真实数据洞察(演示核心素材)

### 洞察 1:**领域文化词是垂直 Agent 的护城河**

采集到但通用 LLM 词表罕见的词:

| 词 | 含义 | 意义 |
|---|---|---|
| `macaron` | 法式马卡龙 | 硅胶烤垫使用场景,通用词库无 |
| `silpat` | 法国头部烘焙垫品牌 | 面试演示 Writer 主动 name-drop 该品牌 |
| `wilton` | 美国头部烘焙器械品牌 | 裱花袋子类必带,通用 LLM 未必想到 |
| `bundt` | 圆环形蛋糕专用模具 | 蛋糕模子类头部词 |
| `springform` | 活底蛋糕模 | 卖家必知术语,买家会主动搜 |

**面试话术**:
> "我采到的 `macaron`, `silpat`, `wilton`, `bundt` 这些词,通用 LLM 或通用词库很少直接给你。它们是**烘焙文化词**——只有真实用户在 Amazon 上搜过,才会出现在补全里。这就是垂直 Agent 的护城河:**数据结构里编码了行业知识**。"

### 洞察 2:**尺寸修饰词的绝对权重**

在 379 词跨子类 Top 15 高频词统计里,**`inch` 出现 46 次**,同时 `mini`, `large`, `small`, `1/2`, `quarter`, `half sheet` 频繁出现。

**决策价值**:烘焙品类**尺寸是核心购买决策因素**,而不是"可选属性"。

**面试话术**:
> "数据反过来告诉我 prompt 该怎么写。原来我的 Writer prompt 里尺寸是可选字段,数据一跑我发现尺寸词占 Top 15 的 3 席以上,说明**用户是带着尺寸需求来搜索的**。所以 Writer prompt 升级——尺寸必须在 Title 前 8 词内出现。**数据反哺 Prompt 设计**,不是 prompt 拍脑袋。"

### 洞察 3:**节日营销词是隐藏机会**

饼干模子类里,同时出现 `halloween cookie cutters`, `christmas cookie cutters`, `dinosaur cookie cutters`, `easter cookie cutters` 等大量节日/主题词。

**决策价值**:季节性品类 listing 需要**多版本变体**,不是一份 listing 打天下。

**面试话术**:
> "节日词在饼干模子类占比很高——`halloween` / `christmas` / `easter` 都在前 30。这告诉我季节性品类的 Reviewer 应该加规则:如果产品在这些子类,title 必须提供**节日变体建议**。这是**数据驱动的 Reviewer 规则**——不是我拍脑袋写的规则,是数据告诉我该写什么规则。"

### 洞察 4:**用户拼写变体真实存在**

采到 `silpat silicone baking mat` 和 `sil pat silicone baking mat` 两种拼写,是同一个品牌的不同用户拼法。

**决策价值**:Backend Keywords 应该**主动覆盖拼写变体**,不是只放"正确拼法"。

**面试话术**:
> "同一个词我采到了两种拼写:`silpat` 和 `sil pat`。这说明**真实用户会打错**。Amazon A9 算法虽然做 fuzzy match,但完全命中的排名更高。所以我的 Backend Keywords 策略应该主动放拼写变体——**这个洞察是从数据看出来的,不是从 SEO 教科书学的**。"

---

## 三、Sprint 6 6 个 Task 的完整面试话术(建议背下来)

### Task 1:API 逆向工程

> "我通过 Chrome DevTools 逆向了 Amazon 前台搜索建议的真实请求。原始接口有 20+ 个参数,大部分是埋点和追踪。我剥离到 5 个核心参数,验证了**无 cookie、无 session** 也能稳定返回结果。前台 `www.amazon.com/suggestions` 需要 session 会给 0 结果,老接口 `completion.amazon.com` 一发即通。这个决策不是靠试错,是靠**理解 Amazon 前后台架构分层**——前台严反爬,后台老接口更稳。**这类判断力比单纯写代码更值钱**。"

### Task 2:v0.1 单次调用

> "v0.1 只有 40 行,只验证'能不能拿到数据'一个问题。因为逆向接口最大的风险不是代码写不出,是**接口有反爬机制导致方案不成立**。用最小代价证伪或证实,才能决定 v0.2 要不要投入。这个'先跑通再迭代'的习惯,是我在这个项目上学到的最重要工程思维。"

### Task 6:v0.2 递归 + rate limit

> "递归采集我做了 4 个设计决策:第一,双 set 去重(`expanded` 管展开,`collected` 管收录),因为 Amazon 会返回自引用词,单个 set 会漏收 5-8%。第二,BFS 不 DFS,因为采集任务需要**可中断**——BFS 保证浅层先采完,Ctrl+C 时至少有完整浅层。第三,`try/except` 单点降级,不整体崩溃。第四,输出带 `depth` + `parent` 的图结构,为后续 RAG 主题聚类留接口。**数据结构选对了,后面所有算法都省力**。"

### Task 7:v0.2.5 多种子 + 踩坑经验

> "我第一次种子词选错了,选了完整产品名 `piping bags tips set`,数据一跑分布严重倾斜——它只补出 1 条。切换到短种子 `piping bag` 后 379 词。教训是:**Amazon 补全接口输入必须是短入口词,不是产品全称**。这类**跑完看数据才能发现的经验**,是这个项目最真实的价值。"

### Task 4:静态 RAG 集成

> "Sprint 1 我用 30 个手工挑的词做 RAG。Sprint 6 我发现自己 Sprint 1 的 TEMPLATE.md 里说'手工爬 Amazon 搜索栏 60 分钟收 100 词',这是**可自动化的过程**——所以我在 Sprint 6 把它变成代码,40 秒收 803 词,**效率提升 1000 倍**。集成时我选择不改 KeywordStore 接口,加了个 `export_to_knowledge_base` 转换函数——**采集器和消费者解耦**,任意一边升级都不影响另一边。跑 product_2(硅胶烤垫)端到端,Writer 生成的 title 里出现了 `Macaron`,bullets 里出现了 `Silpat` 和 `OXO`——**这些品牌词都来自真实用户搜索,通用 LLM 不会主动写**。这个改动的收益不是'词多了',是**Agent 有了行业耳朵**。"

### Task 5:Function Calling tool 集成

> "Sprint 3 我做 Function Calling 时,建立了 schema + impl + dispatcher 三件套。Sprint 6 加真实 Amazon 工具时,base.py 一行没改,Writer 一行没改,只在 amazon_suggest.py 加 tool 定义,mock_tools.py 底部 append 3 行。**这就是抽象层的复利——Sprint 3 花的时间,Sprint 6 收租**。而且 Writer **不是每次都调这个工具**,是自主判断——RAG 词库覆盖够就不调,不够就调。**这就是 Agent 和 workflow 的本质区别**:workflow 是编排好的固定路径,Agent 是根据上下文自主决策。**我的架构里 tool 是能力,不是流程**。"

### Task 3:v0.3 YAML 配置化

> "抽 YAML 时我做了两个升级:第一,schema 从 1:1 种子升级为 1:N,因为 v0.2.5 单种子覆盖同义表达不够(`piping bag` 采不到 `pastry bag` 用户表达),1:N 后单类目从 60-80 词升到 150-200 词,总产出 379 → 803。第二,校验策略分两种——配置字段错 fail-fast 立即抛,网络请求错 warning 继续。**这两种错的处理成本和后果完全不一样**。用户是 SaaS 平台的话,他们自己就能加新类目,不用找我改代码——**Agent 的可扩展性,80% 靠这种边界抽象,不是靠算法**。"

---

## 四、Sprint 6 完整故事线(一段话讲透)

> "Sprint 1 我用 30 个手工挑的词做 RAG。Sprint 6 我读自己 Sprint 1 的 TEMPLATE.md,发现里面'手工爬 Amazon 搜索栏 60 分钟收 100 词'的 SOP,是**可完全自动化的过程**。所以我做了 `amazon_suggest.py` —— 逆向 Amazon 前台补全接口,剥离到 5 个核心参数,验证老公开接口无 session 可用。然后递归采集(BFS + 双 set 去重 + 单点降级),v0.2 单种子 88 词,v0.2.5 硬编码 5 种子 379 词。踩了一个坑:短种子召回好,长种子废了 —— 这是**数据实测教会我的经验**,写在 `bad_cases.md` 里作为面试素材。
>
> 接着我做了双通道集成:静态通道把 803 词导入 KeywordStore(Sprint 1 的 BM25 索引直接复用,一行没改),让 Writer 每次都能召回;动态通道把采集器包成 Function Calling tool(Sprint 3 的 schema + dispatcher 直接复用,base.py 零改动),Writer 遇到冷门产品时自主联网查。跑 product_2 端到端,Writer 生成的 title 里出现了 `Macaron`,bullets name-drop 了 `Silpat` 和 `OXO`—— 这些是真实用户搜索的品牌词。
>
> 最后我抽 YAML 配置层,加新类目从 20 分钟改代码变成 2 分钟改 YAML。整个 Sprint 6 我最自豪的不是词库,是**每一层抽象都在为下一层付利息**——Sprint 3 的 tool 三件套在 Sprint 6 收租,Sprint 1 的 KeywordStore 接口在 Sprint 6 收租,Sprint 6 的 YAML schema 会在 Sprint 7 找卖家试用时收租。**Agent 项目的核心竞争力是复利,不是单点技术**。"

---

## 五、Sprint 6 前后数据对比(适合演示时展示)

| 维度 | Sprint 6 前 | Sprint 6 后 |
|---|---|---|
| 关键词库规模 | 30(手工) | 803(自动) |
| 类目覆盖 | 1(切菜板) | 2(切菜板 + 烘焙 5 子类) |
| 词库获取方式 | 手工 60 分钟 | 自动 40 秒 |
| Writer 可用工具数 | 2 个 mock | 3 个(2 mock + 1 real API) |
| 加新类目成本 | 改 3 处 Python | 写 1 个 YAML |
| 数据可复现性 | 手工不可复现 | 一条命令重跑 |

---

## 六、演示时可以打开的证据

面试演示时按顺序打开这些窗口/文件,叙事流畅:

1. `config/categories/baking.yaml` —— "加新类目就是改这个"
2. `data/keywords/baking_all_depth2.json`(顶部)—— "803 词的原始产出"
3. `src/tools/amazon_suggest.py`(recursive_fetch 附近)—— "BFS + 双 set 去重的实现"
4. `src/tools/mock_tools.py`(文件底部 3 行)—— "Sprint 3 的抽象层让 Sprint 6 只加 3 行"
5. **跑一次** `python run_cli.py data/sample_products/product_2.json` —— 看到 `Macaron` / `Silpat` 出现在生成的 title/bullets 里
