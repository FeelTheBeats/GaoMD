# AIC 学习日记 — 2026-06-24

> 11 个 pass 全量重构完成、Visitor 模式从调研到落地实施、SPEC 设计文档撰写。

---

## SplitMatmul 与全量重构收尾

### Q1: SplitMatmul 为什么特别？

SplitMatmul 是 11 个 pass 中唯一真正用到 PatternMatcher 边匹配能力的 pass。`MergePermuteMatmul` 阶段匹配两个多节点子图：`Permute(kWHC)→Matmul`（输入侧）和 `Matmul→Permute(kWHC)`（输出侧），分别用 `Chain` + `SingleUse` + `Attr` 声明式匹配。

其余 10 个 pass 全是单节点（`MatchNode` 无 `Chain`/`Merge`）——PatternMatcher 在这些场景下等价于 `for + dynamic_cast`。

### Q2: Merge 冲突怎么解决的？

`permute_replace_reshape.cpp` 因 Alan 上游简化条件逻辑（移除 SpecReplaceImpl、新增 DisEn_Condition_6）产生冲突。合并策略：保留 Alan 的上游逻辑 + 本地的 PatternMatcher + BatchRewriter 框架。

---

## Visitor 模式：从调研到落地

### Q3: 三层 IR 各加 Visitor 的可行性与必要性的判断标准？

**可行性**：`Node` 基类只加 1 行 `Accept`，子类各加 1 行 override（纯机械操作）。关键约束是头文件的编译依赖——`node.h` 的 `Accept` 是 inline 的，调了 `v.Visit(*this)`，必须 include `NodeVisitor` 完整定义而非前置声明。

**必要性判断标准**：不是"这个类有没有 `dynamic_cast`"，而是"是否有 pass 需要从 `Node*`（基类指针）恢复出具体类型"。BatchNorm 虽然被大量创建，但没有 pass 对 BatchNorm 做类型分发——它总是在创建后通过具体类引用直接使用，不需要从 `Node*` 恢复。

### Q4: 为什么要两个 Visitor（NodeVisitor + HwVisitor）？

两层关心的类型集合完全不重叠——Operator/Kernel 是软件算子语义，HwLayer 是硬件指令语义。合并后接口臃肿（27 个 Visit 方法，每个 pass 只关心其中少数几个）。

### Q5: Alan 说 "analysis 得写一个 wrapper" 是什么意思？

`AnalyseNode` 是壳，真正的多态行为在 `HwLayer* hw_layer_` 上。`AnalyseNode::Accept` 不做类型分发，只做路由穿透：`hw_layer_->Accept(visitor)`。

`hw_layer_` 在 `BuildAnalyseGraph` 阶段初始化，每个 AnalyseNode 绑定一个 HwLayer（1:1），早于所有 L3 pass。

### Q6: 编译问题怎么解决的？

两个：
1. `node_visitor.h` 的 Kernel Visit 默认实现用了 `static_cast<Node&>(k)` → 前置声明下 `static_cast` 需要完整类型 → 改为 `{}`
2. `node.h` 只有 `class NodeVisitor;` 前置声明 → inline 方法调 `v.Visit()` 需要完整定义 → 改为 `#include "aic/transforms/node_visitor.h"`（反向只做前置声明，无循环依赖）

### Q7: 实际落地改了多少？

115 个文件、256 行。新增 2 个 Visitor 接口、Node 基类加 1 行 Accept、114 个 Accept override。0 处 pass 修改。纯增量基础设施。

### Q8: Visitor 到底解决了什么？

**替代的是改写阶段的 `dynamic_cast`，不是匹配阶段。** 和 PatternMatcher 分工：PatternMatcher 找节点（子图匹配），Visitor 对找到的节点做类型特定操作（类型分发）。

核心收益是"在不修改类的前提下添加新操作"——类体系 42 个 Operator 几年不变，但 pass 数量可以无限增长，每个新 pass 就是一个 Visitor 子类。

---

## SPEC 文档撰写

### Q9: 规范文档应该包含什么？

从空白大纲到完整 SPEC，覆盖：问题场景（附全仓统计数据）、设计思想、支持场景对比表、整体流程图、数据结构（每个类有代码 + 设计决策 + rationale）、子模块设计、向后兼容策略。关键是每个设计决策都写清楚"为什么这么做"而非只写"做了什么"。

### Q10: 有什么要改进的？

- 去掉站不住脚的痛点（"新增 Operator 不可发现"——新增时开发者本来就知道）
- 拆分过大的流程图（L1/L2 和 L3 各一张）
- 踩坑记录放重构记录，精华融入设计决策注释

---

## 提问评价与建议

### 此次做得很好的

1. **对设计的持续追问**（Q3-Q5）：从"要不要加 Visit"到"怎么判断标准"到"为什么是两层 Visitor"到"wrapper 怎么穿透"——每一层都被你追到底了。

2. **"意义"段落的主动书写**：你出手写的意义三点理解到位，尤其是"集中管理同一功能不同入参对象的方法"这句。虽然漏了"操作可无限扩展"这一点（后来补上了），但整体方向准确。

3. **编译问题不甩锅**：编译报错后你不是说"帮我修"，而是自己理解了问题根因——我确认修复方案后你让我执行。这说明你在建立"头文件依赖关系"的直觉。

4. **文档审美**：踩坑记录放 SPEC 你觉得"奇怪"——这是对的，设计文档和操作记录应该有边界。把细节搬到重构记录、精华融入设计决策的做法正是文档工程的标准操作。

### 可改进的

1. **SPEC 的增量迭代方式可以更高效**：今天你总共让我改了 SPEC 不下 10 次。如果先把大纲在脑子里过一遍，把觉得缺的部分列成清单一次性让我补，会少很多来回。

2. **编译验证应该更早做**：基础设施搭完后我们聊了很久的设计文档才去编译。如果搭完立刻跑一次编译，那两个 `static_cast` 和 include 问题会更早暴露。

3. **对 Alan 反馈的利用**：wrapper 概念是 Alan 提的——他一句话定下了 L3 的设计方向。以后类似的关键架构决策，先和 Alan 对 10 分钟再回来展开细节，效率最高。
