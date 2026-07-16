# 关键词库整理模板 · TEMPLATE.md

> **这份文档指导你把 `cutting_board_keywords.json` 从 30 词扩充到 200 词**。
> 面试演示时可以打开这个文档给面试官看,证明**关键词库是你手工整理的资产**,不是 AI 生成的。

---

## 🚀 Sprint 6 更新(2026-07-16)

**下面的"来源 1(Amazon 搜索栏建议词)"已经被自动化了**。

Sprint 6 我把这段手工 SOP 变成了 `src/tools/amazon_suggest.py`:
- 递归调用 Amazon 官方 `completion.amazon.com` 补全接口
- 40 秒采集 800+ 词(vs 手工 60 分钟 100 词,**效率提升 1000 倍**)
- YAML 配置驱动,加新类目零代码

**新加类目现在的正确姿势**:
```bash
# 1. 复制模板配置
cp config/categories/baking.yaml config/categories/YOUR_CATEGORY.yaml

# 2. 编辑改 name / seeds(1-N 短入口词)

# 3. 一键采集 → 落盘 → 导出为 KeywordStore 兼容格式
python -m src.tools.amazon_suggest --category YOUR_CATEGORY
```

**下面的手工方法仍然保留**,因为:
1. 来源 2/3(销售经验/Helium10 补充)AI 不会,你自己写才是护城河
2. 来源 1 的自动版本 + 来源 2/3 的手工版本组合起来产出最强
3. 面试演示时用"来源 1 已自动化 + 来源 2/3 保留手工"的对比,是**知道什么该自动化、什么不该自动化的判断力体现**

详细面试话术见 [`docs/sprint6_findings.md`](../../docs/sprint6_findings.md)。

---

## 目标产出

- **200 个高质量关键词**(现在起步只有 30 个)
- **5-8 个 Best Seller 竞品 Title**(现在起步只有 3 个)
- **每条关键词标注来源**(可选,加分项)

## 关键词分类结构(用来自查覆盖度)

一份好的 200 词关键词库应该覆盖 6 类:

| 类别 | 什么意思 | 目标数量 | 例子 |
|---|---|---|---|
| **Head(头部)** | 高搜索量核心词 | 20-30 | `cutting board`, `chopping board`, `bamboo cutting board` |
| **Modifier(修饰)** | 属性 + 类目组合 | 40-60 | `large cutting board`, `thick cutting board`, `reversible cutting board` |
| **Material(材质)** | 材料相关 | 20-30 | `walnut cutting board`, `acacia cutting board`, `teak butcher block` |
| **Use Case(场景)** | 使用场景 | 30-40 | `meat cutting board`, `cheese board`, `charcuterie board`, `bread carving board` |
| **Long-tail(长尾)** | 3-5 词短语,搜索量低但转化高 | 40-60 | `cutting board with juice groove and handles`, `extra thick bamboo cutting board 18 inch` |
| **Related(相关)** | 相邻类目/搭配 | 10-20 | `wooden serving tray`, `cheese knife set`, `kitchen prep set` |

**200 词 = 上面各类加起来**。可以偏重某几类,但每类都要有覆盖,面试官问"你怎么保证覆盖度"你能答。

---

## 3 个数据来源(推荐优先级)

### 来源 1:Amazon 搜索栏建议词(免费,最真实)

**做法**:
1. 打开 Amazon.com,在搜索框输入 `cutting board`
2. **不按回车**,看下拉建议 —— Amazon 自动补全的都是**真实搜索量足够高**的词
3. 逐个记录,然后换关键词开头:
   - `bamboo cutting b...` → 看建议
   - `chopping b...` → 看建议
   - `wood cutting...` → 看建议
   - 一路扫下去,能收集 60-100 个

**加分做法**:每个建议词记录**它出现在下拉的位置(1-10)**,位置越靠前搜索量越高。

### 来源 2:Helium10 Chrome 插件免费额度(30 天免费)

**做法**:
1. Chrome 装 [Helium10 Free Extension](https://www.helium10.com/tools/free/)
2. 在 Amazon 搜索页跑 "Xray" 功能
3. 免费额度够看 1-2 个类目的搜索量数据
4. 抓 top 100 by search volume

### 来源 3:你自己 8 年销售经验(**这是护城河**)

**做法**:回忆你在阿里国际站带团队时,卖切菜板类目遇到哪些**AI 不知道的关键词**?例如:
- 亚马逊禁用词的替代:"BEST cutting board" → "5-Star Rated cutting board"
- 中国供应商跟美国买家沟通的差异:"kitchen chopping" vs "kitchen prep"
- 节日/季节性词:"gift cutting board"、"housewarming cutting board"、"black friday kitchen deals"
- 目标人群专属词:"cutting board for arthritic hands"(老年人)、"kids cutting board"(亲子)

**这些词一份 200 词库有 10-20 个,就是别人抄不走的差异化**。

---

## 数据格式(必须严格遵守)

`cutting_board_keywords.json` 必须是这个 schema:

```json
{
  "category": "cutting_board",
  "description": "简短说明这个知识库覆盖什么",
  "last_updated": "YYYY-MM-DD",
  "source_notes": "数据来源说明,面试可讲",

  "keywords": [
    "keyword 1",
    "keyword 2",
    "..."
  ],

  "competitor_titles": [
    "Best Seller Title 1",
    "Best Seller Title 2",
    "..."
  ]
}
```

**关键点**:
- `keywords` 是纯字符串列表,**不要加评论、不要嵌套 dict** —— BM25 索引需要纯字符串
- 每条关键词**小写、无标点**(BM25 大小写敏感)
- 保存前用 [jsonlint.com](https://jsonlint.com/) 校验 JSON 合法性,格式错误代码会崩

---

## 5-8 个竞品 Title 怎么收集

**做法**:
1. Amazon 搜 `cutting board`,按 "Best Seller" 排序
2. 抓前 5-8 个的完整 Title(整个字符串,不删任何字)
3. 直接塞进 `competitor_titles` 数组

**质量优先**:选**类型多样**的 —— 竹制 / 木制 / 塑料 / 大 / 小 / 带凹槽 / 带把手,让 Writer 学到"不同定位怎么写 Title"。

---

## 完成后做什么

1. **JSON 合法性检查**:粘贴到 [jsonlint.com](https://jsonlint.com/) 确认无红字
2. **数量核对**:`keywords` ≥ 200,`competitor_titles` ≥ 5
3. **跑测试**:
   ```bash
   python test_rag.py
   ```
4. **跑端到端**:
   ```bash
   python run_cli.py data/sample_products/product_1.json
   ```
   看 Writer 生成的 Listing 有没有"用上"关键词库里的词。

---

## 面试话术(数据整理完后可以讲)

> "我这个 200 词关键词库不是 AI 生成的,是**我自己用 3 个来源手工整理的** —— Amazon 搜索栏建议词、Helium10 免费额度、加上我 8 年阿里国际站销售的选品直觉。里面有 15 个 '禁用词替代'、8 个 '节日季节性' 关键词、还有 10 个 '目标人群专属词' —— **这些是 AI 不会给你的,是行业里踩坑踩出来的**。"

> "这也是为什么我说 RAG 的价值不是'挂个向量库多牛逼',**是数据本身有质量**。垃圾数据挂 RAG 也是垃圾。**领域知识 + RAG 才是护城河**。"

---

## 时间预算

- **来源 1(Amazon 搜索栏)**:60 分钟,能收集 80-100 词
- **来源 2(Helium10)**:30 分钟,能收集 60-80 词
- **来源 3(销售经验)**:30 分钟,能收集 20-40 词
- **去重 + 分类 + 整理进 JSON**:30 分钟
- **总计**:约 2.5-3 小时

**建议分 2-3 天做,每天 1 小时** —— 一次做完容易累,词质量会下降。
