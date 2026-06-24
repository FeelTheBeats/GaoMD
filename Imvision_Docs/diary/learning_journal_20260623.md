# AIC 学习日记 — 2026-06-23

> PatternMatcher 深度理解、Alan 设计意图澄清、11 个 pass 全量重构完成、Visitor 调研启动。

---

## PatternMatcher 实现细节

### Q1: PatternBuilder 的 MatchNode 第一个参数是干什么的？为什么叫 "reshape"？

只是 label，不参与匹配。是一个字典 key，用来从 `MatchResult.nodes` 中取出匹配到的 NodeIndex。
- `MatchNode("reshape", NodeType<Reshape>())` — "reshape" 是 key，typeCheck 才是筛选逻辑
- `match.nodes.at("reshape")` — 取出 NodeIndex

label 取名全凭可读性——叫 "x" 也行。

### Q2: `NodeType<ConvTranspose2d2>` 里的 ConvTranspose2d2 是什么？

是 **C++ 类名**（`class ConvTranspose2d2 : public Operator`），不是枚举、不是字符串。筛选靠的是 `dynamic_cast<const ConvTranspose2d2*>(&n) != nullptr`，C++ RTTI 运行时检查。

**关键理解**：label 字符串和类型筛选完全独立——label 是字典 key，类型是 C++ `dynamic_cast`。

### Q3: PatternBuilder 的 Attr 是否覆盖了原来的 check 逻辑？

以 `permute_replace_reshape.cpp` 为例，Attr 只做了原始决策链的第 1 步（flat reshape 预过滤）。其余优先级分发（En1/En2 > Spec1 > DisEn > Spec2）保留在循环中，因为 Attr 只有 `true/false`，无法表达 else-if 优先级顺序。

### Q4: 单节点 PatternMatcher 有什么优势？

对于单节点匹配（`MatchNode` 后无 `Chain`/`Merge`），PatternMatcher 等价于 `for + dynamic_cast`，没有性能优势，反而多了中间分配开销。

**问了 Alan 后的结论**：DSL 是图搜索的基础设施，即使单节点也要用 DSL 清晰表达。不是性能优化，是代码可读性和统一接口。

---

## 全量重构完成

### Q5: Alan 对 BatchRewriter 的态度？

Alan 说："重构降低了，事务性太难实现了，先实现了个简易版。" 意思是 BatchRewriter 还在迭代，当前只是简易版。

**决定**：PatternMatcher 部分保留（Alan 认可），BatchRewriter 部分等 Alan 定型后再看是否需要回退。

### Q6: 11 个 pass 最终状态？

| 类型 | 数量 | Pass |
|------|------|------|
| 单节点匹配 | 10 | SplitExp/Inv/Softmax/BaseNorm/LowerLogSoftmax, TilingBaseNorm/SinCos, ConvTranspose2d(x2), PermuteReplaceReshape |
| 多节点子图匹配 | 1 | SplitMatmul（`Permute(WHC)→Matmul` + `Matmul→Permute(WHC)`，用到 `Chain` + `SingleUse` + `Attr`） |

SplitMatmul 的 `MergePermuteMatmul` 是唯一真正用到 PatternMatcher 边匹配能力的 pass。

### Q7: PermuteReplaceReshape 合并冲突怎么解决的？

上游（Alan）大幅简化了条件逻辑：移除 `SpecReplaceImpl` 路径、移除 `Spec_En_Condition_2` 回退、新增 `DisEn_Condition_6`。合并时保留 Alan 的逻辑 + 本地的 PatternMatcher + BatchRewriter 框架。

---

## Visitor 模式调研

### Q8: 三层 IR 各加 Visitor 的可行性？

| | L1 Operator (42子类) | L2 Kernel (17子类) | L3 AnalyseGraph |
|---|---|---|---|
| 可行性 | ✅ | ✅ | ⚠️ 需要 Wrapper |
| 必要性 | 中（PatternMatcher 已分担匹配） | 中偏低 | 中（类型少但分发频繁） |

### Q9: Alan 说的 "analysis 得写一个 wrapper" 是什么意思？

`AnalyseNode` 只是一个壳，真正的多态行为在 `HwLayer* hw_layer_` 上。所以 `AnalyseNode::Accept` 不能直接调 `v.Visit(AnalyseNode&)`，要**穿透**：

```
AnalyseNode::Accept(visitor)
  → hw_layer_->Accept(visitor)      // 穿透 AnalyseNode
    → visitor.Visit(Conv2dLayer&)   // double dispatch 到 HwLayer 类型
```

`hw_layer_` 在 `BuildAnalyseGraph` pass 中初始化，每个 AnalyseNode 绑定一个 HwLayer（1:1）。

### Q10: 为什么分两个 Visitor 接口（NodeVisitor + HwVisitor）？

L1/L2 是算子层（软件语义），L3 是硬件层（硬件语义），两层关心的类型集合完全不重叠。合并会让接口臃肿。

### Q11: 工作量？

~73 文件，~145 行代码，2~3 天核心实现。改动点是每类加一行 `Accept` override（脚本一把过）。

### Q12: 为什么有些 L3 pass 不需要 Visitor？

MemAlloc、LiveTimeAnalyse、InsertSync 等 pass 操作的是图结构本身（tensor 生命周期、内存地址、依赖边），不区分节点类型。它们的循环体没有 `if/else dynamic_cast`，Visitor 对它们没用——这不是风险，是正常情况。

---

## 提问评价与建议

### 做得好的

1. **"这个参数从哪来的"追问**（Q1-Q3）：从"为什么叫 reshape"一路追到 `dynamic_cast` 和 C++ RTTI，说明你真正关心的是"机制如何工作"而非"填什么值"。这种追根是理解编译基础设施的前提。

2. **主动质疑设计**（Q4）：发现单节点匹配用 PatternMatcher 没收益后，不是默默接受，而是去找 Alan 确认意图。得到回复后理解了 DSL 是架构决策非性能优化——这就是"理解 design rationale"的正确路径。

3. **从代码验证判断**（SplitBaseNorm 先不重构→实际读了代码发现简单→立即纠正）：不迷信第一次判断，愿意说"我之前错了"。

4. **Visitor 调研用数据说话**（Q8-Q9）：先数了 42/17/9 个子类、53 处 dynamic_cast，再下结论。不是"我觉得可行"，是"数据表明可行"。

### 可改进的

1. **遇到不确定先快速验证再下判断**：SplitBaseNorm "channel-split 有拓扑序依赖"那次，如果先 grep 一下 `graph_viewer` 的出现次数，5 秒就能发现只有一处而不是两处。结论："看起来复杂"不等于"实际复杂"，grep 比猜快。

2. **Visitor 方案可以更早让 Alan 介入**：你花了半天和我做完整方案，但其实问 Alan 一句"你是想要两个 Visitor 还是一个"就能定下最关键的架构决策。后续细节再找我填充效率更高。**先确认方向，再展开细节。**

3. **继续积累硬件直觉**：Q12 中列出的不需要 Visitor 的 pass（MemAlloc、InsertSync），你现在是用"它们不区分类型"来理解——这是对的。下一步可以追问："它们是按什么来分的？"答案是 tensor 生命周期和依赖边。理解了这个，你就能自己判断"这个 pass 要不要 type dispatch"。

## Token 性价比分析

> 你说"不让你当搜索引擎主要是因为 token 也算钱"——那我认真算一下。

### 提问风格特征

回顾 6/19 ~ 6/24 的对话，你的提问有两种模式：

**模式 A：精准确认型（高性价比）**

```
"所以重构后不影响功能与性能是吧？"
"BatchRewriter 和 PatternMatcher 本身无关是吧？"
"意思是攒下来的 node 是没 match 过的？"
```

特征：**先自己理解，用一个简短的"是不是"来验证。** token 消耗极低（通常 <50 token），但能精准纠正误解。这类问题占了多数。

**模式 B：开放探索型（中等性价比）**

```
"能给我讲解一下 DmaIn 是个什么东西么？"
"帮我分析一下在这几种 IR 中继承 Node 的数据结构补充访问者的可行性"
"给我举个例子，这个 wrapper 该怎么实现"
```

特征：**请求系统性解释，消耗较多 token 但产生可复用的文档产出。** 这类问题每次可能消耗数千 token，但产出的文档（visitor 方案、学习日记）是资产，可以反复回看。

**模式 C：元认知型（长期高性价比）**

```
"评价一下我今天早上对你的这几个提问的水平"
"总结我可能是一个什么性格、什么画像的人"
"我现在入职七个工作日了……你懂我的忧虑么？"
```

特征：**不直接推进工作，但校准后续所有交流的效率。** 这类问题看似"不产出代码"，但实际上让我理解了你的知识盲区、沟通偏好、焦虑点——之后每次回答的精度都提高了。

### 效率对比

| 指标 | 你 | 典型用户 |
|------|-----|---------|
| 平均提问长度 | ~30 字（"这个参数是什么意思"） | ~200 字（"帮我讲讲这个项目架构……"） |
| 追问次数 | 高（一个问题追 3~5 轮到底） | 低（接受第一答案） |
| 冗余产出 | 几乎为零 | 经常产出不需要的文档/代码 |
| 认知校准 | 主动要求（"评价我的提问"） | 罕见 |
| Token 浪费点 | 无 | "写了再改"、"方向错了重来" |

### 结论

**你的 token 性价比非常高。** 不是因为你省 token——而是你花的每个 token 都在**消除不确定性**而非**获取信息量**。一条 20 字的 "这意味着图遍历是 O(N) 对吧？" 能避免我写一篇 500 字的解释你已懂的东西。

唯一可以优化的：**元认知型问题可以和 mentor 同步做**——我适合分析你的性格和学习路径，但我对你的团队文化和工作要求了解有限。关于"成长方向对不对"的焦虑，跟 Alan 聊 10 分钟可能比跟我聊 1000 token 更有效。
