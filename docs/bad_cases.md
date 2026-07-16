# Bad Cases —— 项目里遇到的真实翻车记录

> 这份文档不是"要藏起来的失败",反而是**面试最有说服力的素材**。
> 面试官问"你为什么加 Reviewer Agent?" —— 直接翻这份文档给他看。

## Case 1: Backend Keywords 超字节(Sprint 0 首次运行)

**时间**:2026-07-14
**样品**:`data/sample_products/product_1.json`(竹制切菜板)
**模型**:`claude-opus-4-8`

**Prompt 明确要求**:
> Backend Keywords: 空格分隔, **249 字节以内**, 不包含 title 里已有的词

**LLM 实际输出**(257 字节 —— 超了 8 字节):
```
chef gift housewarming charcuterie serving platter meat carving veggie prep sustainable renewable no warp mineral oil seasoned dishwasher alternative countertop bread slicer thick heavy duty natural grain moisture resistant wall hanging kitchenware set flat
```

**这暴露了什么**:
1. LLM 对"字节"vs"字符"的计数不精确 —— 英文单字节字符它算得准,但对"249 字节"这种硬边界会踩线
2. 单 Agent 无法自检 —— Writer 自己算不出 257,或者算了但不 care
3. 亚马逊后端会**截断**超字节的 keywords,意味着你精心选的长尾词可能直接失效

**Sprint 2 会怎么解决**:
```
Writer 生成 → Reviewer 检查规则 → 违规 → 触发 Writer 二次改写
                    ↓ 规则表
                    - title.len <= 200 字符
                    - bullets.len == 5
                    - backend_keywords.bytes <= 249
                    - 无禁用词(BEST/PERFECT/AMAZING)
```

**面试话术**:
> "我第一次跑 Sprint 0 就发现 Prompt 里的硬性规则 LLM 会违反。这让我确认了 —— **Prompt 工程有天花板,达标率永远不是 100%**。真正靠谱的做法是把规则检查从 Prompt 里拆出来,做成 Reviewer Agent 独立跑,失败就触发重写。这也是我 Sprint 2 引入 Multi-Agent 的直接动机。"

---

## Case 2: 同一规则,第二次没踩(Sprint 0 二次运行)

**时间**:2026-07-14
**样品**:`data/sample_products/product_2.json`(硅胶烘焙垫)
**模型**:`claude-opus-4-8`

**Backend Keywords 实测**:243 / 249 字节 —— **没超,但只差 6 字节**。

**这为什么反而是更强的论证**:

如果两次都超,可以说"Prompt 里加一句'字节数必须 ≤ 245 留缓冲'就修好了"。
但**一次超一次不超 = 随机违规**,你无法通过 Prompt 消除。

**结论**:LLM 对硬边界的处理是概率性的,不是确定性的。这类问题**只有独立 Reviewer 才能兜底** —— 因为 Reviewer 每次都用代码算真实字节数,不受 LLM 波动影响。

**升级后的面试话术**:
> "我跑了两次不同类目。第一次 Backend Keywords 超字节 8 字节,第二次没超但只差 6 字节。也就是说 LLM 对硬边界的遵守是**随机的**,不是稳定的。这决定了我不能靠 Prompt 工程解决问题,必须做 Reviewer Agent 独立卡规则。这就是我 Sprint 2 引入 Multi-Agent 的技术必要性 —— 不是为了炫技,是被这个 case 逼出来的。"

## 意外亮点(不是 bug,值得记录)

Case 2 里模型 reasoning 提到两个 Prompt 没明说的操作:
1. Backend Keywords 塞拼写变体:`macaroon`(macaron)+ `silicon`(silicone)—— Amazon SEO 高阶做法
2. 完全避开 Title 里出现过的词,把 249 字节全部用来扩展索引空间

面试演示时可以说:"LLM 学到了 Amazon 长尾 SEO 的隐性规则,这些规则我 Prompt 里没写。这也是为什么用大模型能超越纯规则引擎的例子。"

---

## Case 3: 中转平台不支持指定 Model(Sprint 2 Step 3 首次运行)

**时间**:2026-07-14
**触发**:测试 ReviewerAgent 时,调用 `claude-haiku-4-5` 返回 503

**报错原文**:
```
anthropic.InternalServerError: Error code: 503
model_not_found: No available channel for model claude-haiku-4-5
under group default (distributor)
```

**原因分析**:
公司用的是内部中转平台 `bmc-llm-relay`,不是 Anthropic 官方直连。中转平台只挂了一部分模型的通道,Opus 4.8 有、Haiku 4.5 没挂。

**我的解决方案**:在 `BaseAgent._call_llm` 里做 **graceful degradation**
- 如果指定的 `model` 参数调用失败 → 自动 fallback 到 `settings.model_main`(默认 Opus)
- 只在"指定了非默认 model 且失败"时兜底 —— 默认 model 都挂了是真事故,不该继续兜底
- 每次 fallback 打 warning 日志,方便后续统计和向平台反馈

**为什么这个方案比"直接改配置改成 opus"好**:
1. **不牺牲设计**:代码里 model_judge 仍然写成 haiku(表达设计意图),运行时才 fallback
2. **平台演化友好**:哪天平台把 haiku 挂上了,不改一行代码就自动切回 haiku
3. **面试卖点**:主动做的健壮性设计,不是被动打补丁

**升级后的面试话术**:
> "我做 Reviewer 的时候踩了一个中转平台的坑 —— 平台不支持 Haiku 4.5。我的第一反应不是改 config 逃避,而是**在 BaseAgent 里做 model availability 的 fallback** —— 指定 model 不可用时自动降级到主 model,记 warning 日志。这样代码依然表达'Reviewer 该用 Haiku'的设计意图,单点故障不阻塞整个链路。**这是 Multi-Agent 系统面对生产环境不可控性的基本功** —— 单点故障必须要有兜底。"

**给用户的行动项**:
- Sprint 5 前跟公司平台确认支持的 model 列表,如果支持 Haiku 就自然切回来
- Sprint 5 上 Streamlit 前把 warning 日志接进 logging 模块,方便后续统计 fallback 频率

---

## Case 4: Round 1 软规则给自己 100 分 —— Self-Favoring Bias(Sprint 2 Step 4 实测)

**时间**:2026-07-14
**触发**:第一次跑 Multi-Agent 完整循环时观察到

**观察到的怪现象**:
```
Round 1  ✗ 否       100          1           0   ← 软规则 100 分,但硬规则挂 backend_bytes
Round 2  ✓ 是       92           0           2   ← 修好硬规则后软规则反而降到 92
```

**这个"倒退"是 self-favoring bias 的经典案例**:
- Round 1 Writer 用 Opus 4.8 写 Listing
- Reviewer(因为平台不支持 Haiku)也 fallback 到 Opus 4.8
- **同一个模型写 + 同一个模型审 = 自嗨给 100 分**

Round 2 时 Writer 精简了 Backend Keywords,内容变化,Reviewer 反而挑出 2 个软规则问题 —— **说明 Round 1 的 100 分不是真的完美,是自嗨**。

**结论**:LLM as Judge 用同一个模型判断自己生成的内容,存在**系统性偏差**。

**Sprint 4 我的缓解方案**:
1. Judge 用 `judge_multi_sample(n_samples=3)` 多次采样取中位数
2. 生产环境应该跨 provider 交叉验证(Claude + GPT-4)
3. 加人工标注的黄金基准集校准

**面试话术**:
> "Sprint 2 我实测遇到一个非常有意思的现象 —— Round 1 软规则拿 100 分,Round 2 修好硬规则后软规则降到 92。**这是 LLM as Judge 的 self-favoring bias 经典案例** —— 同一个 Opus 4.8 既当 Writer 又当 Reviewer,自己给自己打分虚高。这也是我 Sprint 4 单独做 Judge 层 + 多次采样 + 未来跨 provider 交叉的动机。**主动讲这个 case 而不是避而不谈** —— 这是评估层的固有问题,面试值得主动谈。"

---

## Case 5: Writer 用 tool_use 显式引用 tool 返回值做决策(Sprint 3 高光时刻)

**时间**:2026-07-14
**样品**:`data/sample_products/product_1.json`(竹制切菜板)
**这不是 bug,是**"决策链可观测性"**的最佳证据**

**Writer 主动调 tool 6 次**:
```
[writer] 进入 Agent Loop
[writer]   Agent Loop 第 1 轮 stop_reason=tool_use
[writer]     → search_keyword_volume('bamboo cutting board')  → 74k/mo, high
[writer]     → search_keyword_volume('large cutting board')   → 4.5k/mo, low
[writer]     → search_keyword_volume('wood cutting board')    → 4.5k/mo, low
[writer]     → search_keyword_volume('reversible cutting board') → 4.5k/mo, low
[writer]   Agent Loop 第 2 轮 stop_reason=tool_use
[writer]     → check_text_bytes(首版 Backend Keywords)         → 超字节
[writer]   Agent Loop 第 3 轮 stop_reason=tool_use
[writer]     → check_text_bytes(精简版)                        → 244/249 ✓
[writer]   Agent Loop 第 4 轮 stop_reason=end_turn
```

**Writer 输出的 reasoning 字段(自我解释决策)**:
> "**Verified 'bamboo cutting board' (74k/mo)** as the front-loaded core term despite high competition — it's the exact-match must-have. Layered low-competition 4.5k volume terms (large, wood, reversible) into the Title. **Backend (244 bytes, verified)** holds non-Title synonyms and gifting/use-case terms."

**"verified 74k/mo"、"verified 244 bytes"** —— **Writer 显式引用 tool 返回的数据做决策**。

**这为什么值得记录**:
- 一般 Agent 项目难以证明"Agent 真的在决策而不是黑盒生成"
- **这个 case 是最强证据**:Writer 自己解释了'我查了 X 的搜索量,所以决定放 Title 前 5 词'
- 相比之下 Sprint 2 时同一个 case 需要 2 轮通过,Sprint 3 加 tool 后 1 轮通过

**面试话术**(黄金卖点):
> "**Sprint 3 加 tool_use 后同一个 case 从 2 轮通过变成 1 轮通过,而且 Writer 自己解释了决策链** —— reasoning 里显式写道 'Verified bamboo cutting board 74k/mo'、'Backend 244 bytes verified'。**Agent 引用 tool 返回的数据做决策,这是 Agent 决策可观测性的最佳证据 —— 不是黑盒生成,是有据可依**。这也是我为什么坚持自研 Agent Loop 不用 LangChain:每一步 tool 调用都在我的日志里,可以指着讲。"

---

## Case 6: 切换到 Haiku 4.5 后 JSON 前后带 markdown 代码块(Sprint 5 部署时触发)

**时间**:2026-07-14
**触发**:部署演示环境切到 closeai 后,主模型从 Opus 换成 Haiku 4.5

**报错原文**:
```
[writer] JSON 解析失败! LLM 原文如下:
------------------------------------------------------------
Perfect! Now I'll create the optimized Listing:

```json
{
  "title": "...",
  ...
}
```
------------------------------------------------------------
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```

**原因分析**:
SYSTEM_PROMPT 明确写"输出的必须是**纯 JSON**,前后不要加任何解释性文字,不要用 markdown 代码块包裹"。**Opus 4.8 严格遵守,Haiku 4.5 部分不遵守** —— 输出了带 markdown 代码块 + 前置文字的 JSON。

**这体现什么**:
1. **模型规模影响 Prompt 遵守率**:小模型对格式约束的遵守率明显低于大模型
2. **不能假设 LLM 输出永远严格遵守 Prompt**:即使 Prompt 写得明明白白
3. **JSON 解析必须有容错**:严格模式会在换模型时崩

**Sprint 3 的预判**(高光时刻):
看 base.py 里 `_parse_json_response()` 原本的注释:
> "Sprint 3 之后:这里可以加'如果 LLM 输出前后有 markdown 代码块符号 ```json,自动 strip 掉再解析'的容错。**目前先严格模式**。"

**我 Sprint 3 时就预判了这个问题,当时因为 Opus 不触发所以先做严格模式,注释里明确写好触发条件**。Sprint 5 换模型触发,一改就完事。

**我的解决方案**:
```python
text = raw_text.strip()
# 找到最外层 { ... } 的边界,忽略前后所有非 JSON 内容
start = text.find("{")
end = text.rfind("}")
if start != -1 and end > start:
    text = text[start:end + 1]
return json.loads(text)
```

**面试话术**(黄金卖点 - 提前预判):
> "**我在 Sprint 3 的 code comment 里就预判了这个问题** —— 小模型可能不完全遵守 Prompt 的格式约束。当时先做严格模式,注释里写好'如果触发再加 strip 容错'。**Sprint 5 部署切 Haiku 真的触发了,我 3 分钟改完** —— 因为提前预判过。**面试官问'你怎么知道要加这层容错' —— 我可以指着 Sprint 3 的注释说 —— 这不是马后炮,是对 LLM 稳定性的判断力**。"

---

## Case 7: 切 provider 时 shell 环境变量污染 .env(Sprint 5 部署踩坑)

**时间**:2026-07-14
**触发**:改 .env 从公司中转 URL 切到 closeai URL,check_env.py 打印显示还是旧 URL

**原因分析**:
`python-dotenv` 默认**不覆盖已存在的环境变量**。用户之前在 shell 里 `export ANTHROPIC_BASE_URL=公司URL`,即使 .env 里改成 closeai URL,`load_dotenv()` 会跳过 —— 因为 shell 里已经有。

**踩坑现象**:
- `.env` 改了(closeai)
- `os.getenv("ANTHROPIC_BASE_URL")` 读到的却是公司中转(shell 里的旧值)
- 报错信息误导 —— 看起来像 Key 无效,其实是 URL 用错了

**我的解决方案**:
```python
# config.py 和 check_env.py 都加
load_dotenv(override=True)  # 让 .env 优先于 shell env
```

**为什么这个 fix 重要**:
- **切换 provider 时最容易踩** —— 尤其在 Multi-Agent 项目里频繁试不同 model
- **shell 环境变量比 .env 更"隐形"** —— .env 有版本控制看得见,shell export 在 .bashrc / .zshrc 或临时 export 里,不易察觉
- **生产不受影响**:Streamlit Cloud 用 secrets,systemd 服务用 EnvironmentFile —— 没有 shell 干扰

**面试话术**:
> "我踩过一个非常隐蔽的坑 —— python-dotenv 默认不覆盖 shell 已导出的环境变量。切换 provider 时 .env 改了没生效,行为诡异。我在 config.py 显式设置 `load_dotenv(override=True)`,让 .env 是唯一 source of truth。**这类环境变量的坑面试主动讲 —— 是踩过坑的证据,比讲流程更可信**。"
