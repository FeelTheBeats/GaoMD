# FusedOp Pattern-Match 重构可行性分析

> 分析日期：2026-06-26
> 
> 目标文件：`target/tensor_brain/transforms/fused_op.cpp`（904 行，9 种融合模式）
> 
> 已有基础设施：`PatternMatcher` + `PatternBuilder` + `BatchRewriter`（2026-06 由 Alan Chen 引入）

---

## 一、现状分析

### 1.1 FusedOp 的 9 种融合模式

| 模式 | 种子节点 | 下游节点 | 融合产物 | 复杂度 |
|------|---------|---------|---------|--------|
| `AsymmetricalPadFusionPattern` | PadKernel | Conv2dKernel / Pool2dKernel | 修改原 Kernel 属性 | ⭐⭐⭐⭐⭐ |
| `ReluFusionPattern` | Eltwise等 | ActivationKernel(ReLU) | 修改原 Kernel 属性 | ⭐⭐⭐ |
| `ConvActFusionPattern` | Conv2dKernel | ActivationKernel | ConvFusionKernel | ⭐⭐ |
| `ConvPoolFusionPattern` | Conv2dKernel | Pool2d2Kernel | ConvFusionKernel | ⭐⭐ |
| `ConvActPoolFusionPattern` | ConvFusionKernel | Pool2d2Kernel | ConvFusionKernel（三层） | ⭐⭐⭐ |
| `ConvPoolActFusionPattern` | ConvFusionKernel | ActivationKernel | ConvFusionKernel（三层） | ⭐⭐⭐ |
| `BiInterpActFusionPattern` | InterpKernel | ActivationKernel | InterpFusionKernel | ⭐⭐ |
| `ActPoolFusionPattern` | ActivationKernel | Pool2d2Kernel | 修改 Pool2d2Kernel | ⭐⭐⭐ |
| `PoolActFusionPattern` | Pool2d2Kernel | ActivationKernel | 修改 Pool2d2Kernel | ⭐⭐⭐ |

### 1.2 通用代码模式

每个 FusionPattern 都遵循相同结构：

```
1. 创建 GraphViewer，获取拓扑序遍历
2. for (auto index : order) {
3.   CastNoCheck<T>(node) 匹配种子节点
4.   检查拓扑约束（output edge count）
5.   检查数据类型约束（dtype, acc, bin_mode）
6.   CastNoCheck<U>(&*seed->OutputNodesBegin()) 匹配下游
7.   创建融合 Kernel / 修改已有 Kernel 属性
8.   重连输入输出边
9.   ReleaseNode 删除被融合节点
10.  Resolve() 更新图拓扑
11. }
```

### 1.3 当前问题

- **代码重复**：9 个方法中拓扑序遍历、output edge count 检查、nullptr 判断等代码高度重复
- **约束散落**：dtype 检查、MatchAcc、bin_mode、relu LUT 匹配等约束分散在代码中，不易复用
- **可读性差**：嵌套指针追踪（`CastNoCheck<T>(&*node->OutputNodesBegin())`）掩盖了融合逻辑
- **扩展困难**：新增一个融合模式需要完整复制 ~50 行样板代码

---

## 二、PatternMatcher 基础设施分析

### 2.1 现有 API

```cpp
// 模式定义（声明式 DSL）
PatternGraph pattern = PatternBuilder("name")
    .MatchNode("seed", NodeType<Conv2dKernel>())      // 类型匹配
    .MatchNode("sink", NodeType<ActivationKernel>())   // 类型匹配
    .Chain("seed", "sink")                              // 拓扑边
    .SingleUse("seed")                                  // 单消费者约束
    .MaxUses("sink", 2)                                 // 最大消费者数
    .Attr("sink", [](const Node& n) { ... })            // 自定义属性约束
    .Build();

// 匹配执行
auto results = PatternMatcher(graph).Match(pattern);
// → std::vector<MatchResult>  每个 MatchResult 包含 label→NodeIndex 映射

// 批量图改写
BatchRewriter rewriter(graph);
rewriter.RemoveNode(nodeIdx);
rewriter.Commit();  // 批量 ReleaseNode + 单次 Resolve
```

### 2.2 能力强项

| 能力 | 支持情况 | 对应 FusedOp 中的需求 |
|------|---------|---------------------|
| 节点类型匹配 | ✅ `NodeType<T>()` 使用 `dynamic_cast` | `CastNoCheck<T>(node)` |
| 线性链匹配 | ✅ `Chain("a", "b")` | `seed → sink` 一对一 |
| 多输入匹配 | ✅ `Merge({"a","b"}, "c")` | 暂不需要 |
| 单消费者约束 | ✅ `SingleUse()` / `MaxUses()` | `GetOutputEdgesCount() > 1` |
| 自定义属性约束 | ✅ `Attr()` lambda | `bin_mode != 1`, `MatchRelu()` |
| 批量图修改 | ✅ `BatchRewriter` | `ReleaseNode` + `Resolve` |

### 2.3 当前不足

| 缺失能力 | 影响 | 严重性 |
|---------|------|--------|
| **数据类型跨节点约束** | 无法表达 `CheckConvDtype(seed_input, seed_output)` | 🔴 高 |
| **Edge 级别的约束** | 无法检查两个节点间特定 NodeArg 的 dtype/acc 是否匹配 | 🔴 高 |
| **节点内部状态检查** | 无法表达 `HavePool()` / `HaveAct()`（需要访问具体子类方法） | 🟡 中 |
| **OR 类型匹配** | 种子可以是 `Conv2dKernel` **或** `ConvFusionKernel` | 🟡 中 |
| **匹配 + 改写交替** | 当前模式是 MATCH ALL → REWRITE ALL，而 FusedOp 需要在每个模式内 MATCH ONE → REWRITE ONE → LOOP | 🟡 中 |
| **node_arg 级别匹配** | 无法表达"两个节点共享同一个 NodeArg" | 🟢 低 |

---

## 三、逐模式适配分析

### 3.1 完美适配：2 节点 Producer-Consumer（4/9）

#### ConvActFusionPattern

```
Conv2dKernel → ActivationKernel
```

**可表达度：80%**

```cpp
auto pattern = PatternBuilder("ConvActFusion")
    .MatchNode("conv", NodeType<Conv2dKernel>())
    .MatchNode("act",  NodeType<ActivationKernel>())
    .Chain("conv", "act")
    .SingleUse("conv")
    .Attr("act", [](const Node& n) {
        return CastNoCheck<const ActivationKernel>(&n)->attr_ref().bin_mode != 1;
    })
    .Build();
```

**待解决**：
- `CheckConvDtype(conv_input, conv_output)` — 需要跨 input/output 的 dtype 约束，PatternMatcher 目前不支持
- 解决方案：在匹配后回调中补充检查，或在 `Attr("conv")` 中通过 node 访问其 input/output

**同样的模式也适用于**：
- `ConvPoolFusionPattern`（Conv2dKernel → Pool2d2Kernel）
- `BiInterpActFusionPattern`（InterpKernel → ActivationKernel）
- `PoolActFusionPattern`（Pool2d2Kernel → ActivationKernel）
- `ActPoolFusionPattern`（ActivationKernel → Pool2d2Kernel）

### 3.2 部分适配：链式融合（2/9）

#### ConvActPoolFusionPattern / ConvPoolActFusionPattern

```
ConvFusionKernel → Pool2d2Kernel     // 三层融合（Conv→Act→Pool）
ConvFusionKernel → ActivationKernel  // 三层融合（Conv→Pool→Act）
```

**可表达度：50%**

挑战：
1. **种子类型不固定**：第一次融合后种子是 `ConvFusionKernel`，但 PatternBuilder 要求编译期指定类型 — 需要有 `NodeTypeOr<Conv2dKernel, ConvFusionKernel>()` 
2. **内部状态检查**：`HavePool()` / `HaveAct()` 避免重复融合，需要在 `Attr()` 中处理
3. **依赖前序融合结果**：这些模式必须在 ConvActFusion / ConvPoolFusion 之后运行

### 3.3 不推荐适配（3/9）

#### AsymmetricalPadFusionPattern

**可表达度：10%**

原因：
- 不是创建新 Kernel，而是**就地修改** Conv2dKernel 或 Pool2dKernel 的 pad 属性
- `FusePadOp` 使用模板特化，逻辑高度定制化（包括 MPU pad 计算公式、Pool2d pad 合法性验证等）
- 需要 `dynamic_cast` 尝试多种类型（先试 Conv2dKernel，再试 Pool2dKernel）
- 用 PatternMatcher 重构收益极低，反而增加复杂度

#### ReluFusionPattern

**可表达度：20%**

原因：
- 种子是 ActivationKernel(ReLU)，**向上游**匹配（找 input node）
- 改写是调用 `kernel->EnableRelu()` 的**就地修改**，不创建新 Kernel
- 匹配逻辑（`MatchRelu` 模板、LUT 比较）已很好地封装
- 本质上是一个"反向边遍历"模式，PatternMatcher 设计为"顺向匹配"

#### ConvPoolActFusionPattern / ConvActPoolFusionPattern 的部分逻辑

这两个模式的约束检查（`HavePool()` / `HaveAct()`、`bin_mode`）与普通 2 节点模式混合，不适合完全声明式表达。

---

## 四、核心挑战

### 4.1 图状态：匹配与改写的交替

**当前方式**（work-while-you-go）：

```
for each node in topological_order:
    match one pattern instance
    modify graph (create fusion kernel, release nodes, resolve)
    continue to next node
```

**PatternMatcher 方式**（batch）：

```
matches = PatternMatcher(graph).Match(pattern)  // 收集所有匹配
for each match:
    rewrite graph
    // ❌ 图已变化，后续 MatchResult 的 NodeIndex 可能失效
```

**解决方案选项**：

| 方案 | 描述 | 优缺点 |
|------|------|--------|
| A. 单次匹配+立即改写 | 每匹配一个就立即改写，然后重新匹配 | 安全但对大图效率低 |
| B. 匹配+标记+批量改写 | 先收集所有匹配，标记被融合节点，跳过冲突匹配 | 高效但实现复杂 |
| C. 匹配+改写后 invalidate | 改写时主动更新/失效受影响的 MatchResult | 需要 NodeIndex remapping 机制 |

**建议**：对于 FusedOp，**方案 A** 最简单且安全。每个匹配只改 2-3 个节点，图变化不大，重新匹配的开销可接受。

### 4.2 跨节点数据流约束

当前模式中大量约束跨越节点边界：

```cpp
// 检查 Conv 的输入和输出 dtype
Tensor *mac_in_tensor = Cast<Tensor>(conv->MutableInputs()[0]);
Tensor *mac_out_tensor = Cast<Tensor>(conv->MutableOutputs()[0]);
CheckConvDtype(*mac_in_tensor, *mac_out_tensor);

// 检查 Act 和 Pool 的 input tensor 的 acc 是否匹配
MatchAcc(*act_in_tensor, *pool_in_tensor);

// 检查 Interp 和 Act 的 input Tensor dtype 一致
interp_in_tensor->data_type() != act_in_tensor->data_type();
```

**解决方案**：扩展 `Attr()` 或新增 `EdgeAttr()`：

```cpp
// 方案1：在 Attr 中通过 node 访问其 context
.Attr("conv", [](const Node& n) {
    auto& conv = static_cast<const Conv2dKernel&>(n);
    auto* in  = Cast<Tensor>(conv.Inputs()[0]);
    auto* out = Cast<Tensor>(conv.Outputs()[0]);
    return !CheckConvDtype(*in, *out);
})

// 方案2：新增 EdgeAttr（推荐）
.EdgeAttr("conv", "act", [](const Node& from, const Node& to) {
    auto* from_out = Cast<Tensor>(from.Outputs()[0]);
    auto* to_in    = Cast<Tensor>(to.Inputs()[0]);
    return MatchAcc(*from_out, *to_in);
})
```

### 4.3 RewriteRefModelJson 副作用

每种融合都需要更新 `ref_model.json`（记录 pack/unpack 信息），逻辑各异：

- 2 节点融合：`RewriteRefModelJson(mac_name, ff_name)`
- 3 节点融合：`RewriteRefModelJson(fusion_name, sink_name, true)`（`multi_mac_name=true`）
- In-place 修改：不调用 `RewriteRefModelJson`

这部分不适合声明式表达，应在 rewrite callback 中保留命令式代码。

### 4.4 性能考量

- `CastNoCheck` vs `dynamic_cast`：当前使用 `CastNoCheck`（static_cast）获得零开销类型转换，PatternMatcher 使用 `dynamic_cast`。对 2-3 万节点的中等图，这个差异在匹配阶段可忽略，但需要关注。
- 重复 Resolve 开销：PatternMatcher 批处理模式下，每次 Resolve 会重建边索引。对于 FusedOp 的场景（每匹配一个就改图），Resolve 次数不变。

---

## 五、推荐方案

### 5.1 分层重构策略

```
┌──────────────────────────────────────────────────┐
│  Layer 3: 融合 Rewrite 回调（命令式，保留现状）     │
│  - CreateFusionKernel / ModifyKernelAttributes    │
│  - RewriteRefModelJson                            │
│  - SetInputs / SetOutputs                         │
├──────────────────────────────────────────────────┤
│  Layer 2: 匹配结果  →  改写调度                    │
│  - for each MatchResult: rewrite callback →       │
│    BatchRewriter.Commit()                         │
├──────────────────────────────────────────────────┤
│  Layer 1: Pattern 声明（声明式 DSL）               │
│  - PatternBuilder 定义节点类型 + 拓扑 + 约束       │
│  - PatternMatcher 执行匹配                         │
└──────────────────────────────────────────────────┘
```

### 5.2 具体建议

#### 第一阶段（推荐立即做）：重构 7 个链式融合模式

`SliceFuse`（`docs/PATTERN_MATCHER.md`）已证明现有 API 支持 3 节点链（`DmaIn → Slice(H) → Slice(W)`），FusedOp 全部 7 个模式均可直接用 `Chain` + `Attr` 表达，无需 API 扩展。

| 模式 | 类型 | 优先级 |
|------|------|--------|
| `ConvActFusionPattern` | 2-node | P0 |
| `ConvPoolFusionPattern` | 2-node | P0 |
| `BiInterpActFusionPattern` | 2-node | P1 |
| `PoolActFusionPattern` | 2-node | P1 |
| `ActPoolFusionPattern` | 2-node | P1 |
| `ConvActPoolFusionPattern` | 3-node chain | P1 |
| `ConvPoolActFusionPattern` | 3-node chain | P1 |

预期效果：减少 ~370 行重复代码，每个模式从 ~65 行缩减到 ~35 行（pattern 定义 ~12 行 + rewrite 回调 ~23 行）。

> **关于 Phase 2 扩展**：原设计提出的 `EdgeAttr`、`NodeTypeOr<T,U>`、`InputAttr`/`OutputAttr` 三项扩展经验证均为**非必要的语法糖**。`EdgeAttr` 可用 `Attr("from")` 内 `node.OutputNodesBegin()` 走到邻居替代；`NodeTypeOr` 可用 `Attr()` 内 `CastNoCheck<T> || CastNoCheck<U>` 替代；`InputAttr` 只是省一行 `Cast<Tensor>`。`SliceFuse` 的 3 节点链反例已证明现有 API 即可覆盖所有场景，无需等待任何 API 扩展。

#### 不建议重构

- `AsymmetricalPadFusionPattern`：高度定制化（`FusePadOp` 模板特化 + MPU pad 计算），用 PatternMatcher 反而增加复杂度
- `ReluFusionPattern`：反向边匹配（ActivationKernel → upstream Kernel），`EnableRelu()` 就地修改，与 PatternMatcher 的顺向 Chain 设计方向不一致

### 5.3 重构示例

**重构前** (`ConvActFusionPattern`, ~75 行)：

```cpp
common::Status FusedOp::ConvActFusionPattern(KernelNet *kernel_net) {
  auto graph_viewer = GraphViewer(*kernel_net);
  for (auto index : graph_viewer.GetNodesInTopologicalOrder()) {
    Node *node = kernel_net->GetNode(index);
    Conv2dKernel *conv2d_kernel = CastNoCheck<Conv2dKernel>(node);
    if ((conv2d_kernel == nullptr) || (conv2d_kernel->GetOutputEdgesCount() > 1))
      continue;
    Tensor *mac_in_tensor = Cast<Tensor>(conv2d_kernel->MutableInputs()[0]);
    Tensor *mac_out_tensor = Cast<Tensor>(conv2d_kernel->MutableOutputs()[0]);
    if (CheckConvDtype(*mac_in_tensor, *mac_out_tensor))
      continue;
    if (conv2d_kernel->GetOutputEdgesCount() != 1) { ... continue; }
    auto out_act_kernel = CastNoCheck<ActivationKernel>(&*conv2d_kernel->OutputNodesBegin());
    if (!out_act_kernel || out_act_kernel->attr_ref().bin_mode == 1) { ... continue; }

    // 创建融合 kernel...（~30 行）
    // 更新 ref_model.json
    // ReleaseNode × 2, Resolve
  }
  return common::Status::OK();
}
```

**重构后** (~35 行，其中 ~15 行 pattern 定义 + ~20 行 rewrite 回调)：

```cpp
common::Status FusedOp::ConvActFusionPattern(KernelNet *kernel_net) {
  auto pattern = PatternBuilder("ConvActFusion")
      .MatchNode("conv", NodeType<Conv2dKernel>())
      .MatchNode("act",  NodeType<ActivationKernel>())
      .Chain("conv", "act")
      .SingleUse("conv")
      .Attr("act", [](const Node& n) {
          return CastNoCheck<const ActivationKernel>(&n)->attr_ref().bin_mode != 1;
      })
      .Attr("conv", [](const Node& n) {    // 内联 dtype 检查
          auto& c = static_cast<const Conv2dKernel&>(n);
          auto* in  = Cast<Tensor>(c.Inputs()[0]);
          auto* out = Cast<Tensor>(c.Outputs()[0]);
          return !CheckConvDtype(*in, *out);
      })
      .Build();

  for (;;) {  // 循环直到没有新匹配（因为图在每次改写后变化）
    auto matches = PatternMatcher(*kernel_net).Match(pattern);
    if (matches.empty()) break;

    auto& m = matches[0];  // 每次处理一个匹配
    auto* conv = Cast<Conv2dKernel>(kernel_net->GetNode(m.nodes["conv"]));
    auto* act  = Cast<ActivationKernel>(kernel_net->GetNode(m.nodes["act"]));

    RewriteRefModelJson(conv->name(), act->name());

    auto& fused = kernel_net->AddKernel<ConvFusionKernel>(conv->name() + ".fused." + act->name());
    // ... 设置属性 ...
    fused.SetInputs(conv->MutableInputs());
    fused.SetOutputs(act->MutableOutputs());

    BatchRewriter rewriter(*kernel_net);
    rewriter.RemoveNode(act->Index());
    rewriter.RemoveNode(conv->Index());
    AIC_RETURN_IF_ERROR(rewriter.Commit());
  }
  return common::Status::OK();
}
```

**净收益**：
- 模式定义（节点类型 + 拓扑 + 约束）从 ~15 行散落的 if-continue 变为 ~10 行声明式 DSL
- 匹配逻辑完全消除，交给 PatternMatcher 引擎
- 改写逻辑保留原有的灵活性
- 单模式代码量减少 ~50%

---

## 六、风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| `dynamic_cast` 性能 | 大图匹配变慢 | 引入 `NodeKind` 枚举 + 类型索引加速；或给 `NodeType` 模板增加编译期 type_id |
| Pattern 无法表达复杂约束 | 仍需保留手写匹配 | 通过 `Attr()` lambda 兜底，任意约束都可用 lambda 表达 |
| 图变化后 NodeIndex 失效 | 匹配结果不可用 | 每次只用一个 MatchResult，改完立即重匹配（方案 A） |
| 引入新 bug | 融合逻辑错误 | 有 `pattern_matcher_test.cpp` 测试框架，重构后增加融合模式专项测试 |
| BatchRewriter 不处理 Resolve 失败回滚 | 图损坏 | 当前 `ReleaseNode` + `Resolve` 也是同样的"无回滚"模式，风险不变 |

---

## 七、结论

**Pattern-Match 方式重构 FusedOp 是可行的，推荐分阶段推进**：

1. **可立即重构**（7/9 模式）：ConvAct、ConvPool、BiInterpAct、PoolAct、ActPool、ConvActPool、ConvPoolAct — 现有 API（`Chain` + `Attr`）已完整支持 2 节点和 3 节点链式模式（见 `SliceFuse` 示例），无需 API 扩展
2. **不建议重构**（2/9 模式）：AsymmetricalPad、ReluFusion — 高度定制化改写逻辑，声明式表达收益不足

重构的核心价值不在于消除代码行数，而在于**分离关注点**：匹配逻辑用声明式 DSL 表达（可读、可测、可复用），改写逻辑保留命令式的灵活性。这与 LLVM 的 PatFrag / MLIR 的 DRR 设计理念一致。





核心发现：

1. 现有 PatternMatcher API 已足够覆盖 FusedOp 全部 7 个链式融合模式。Phase 2 的三项扩展（`EdgeAttr`、`NodeTypeOr`、`InputAttr`/`OutputAttr`）均可用 `Attr()` lambda 绕过，本质是语法糖而非功能缺口——`SliceFuse`（3 节点链 `DmaIn → Slice(H) → Slice(W)`）已证明这一点
2. BatchRewriter 的 batch 语义与 FusedOp 的 work-while-you-go 模式冲突——需要每次只取一个 MatchResult、改写后立即重匹配，但开销可控
3. 匹配和改写分离是最大的架构收益：当前每个模式的 ~15 行散落约束检查（nullptr、output edge count、dtype、bin_mode）将收敛到 ~10 行声明式 DSL

---

## 八、重构实施记录（2026-06-29）

### 8.1 实施内容

| 项目 | 数量 |
|------|------|
| 重构模式 | 7/9 |
| 未重构模式 | 2/9（AsymmetricalPad、ReluFusion） |
| 新增 include | 2 个（`pattern_matcher.h`、`graph_rewriter.h`） |
| 编译状态 | ✅ fused_op.cpp 编译通过 |

### 8.2 代码量变化

| 指标 | 重构前 | 重构后 | 变化 |
|------|--------|--------|------|
| 总行数 | 904 | 531 | -373 行（-41%） |
| 7 个模式平均行数 | ~65 | ~35 | -46% |
| 样板代码（GraphViewer + for-loop + CastNoCheck） | 每模式 ~10 行 × 7 | 消除 | -70 行 |

### 8.3 未重构模式的原因

| 模式 | 原因 | 可能的简单重构 |
|------|------|--------------|
| `ReluFusionPattern` | ① 向上游匹配（反向边），PatternMatcher 设计为顺向 Chain；② 改写是 `EnableRelu()` 的就地修改，非创建融合 Kernel；③ LUT 比较（`MatchRelu` 模板）已很好封装 | 如果 PatternMatcher 未来支持 `ReverseChain()`，可用 ~10 行 pattern + ~15 行 rewrite 替代当前 ~45 行 |
| `AsymmetricalPadFusionPattern` | ① 改写是 pad 属性的就地修改（`FusePadOp` 模板特化）；② 包含 MPU pad 计算公式和 Pool2d pad 合法性验证，逻辑高度定制化；③ 使用 try-both-types（`dynamic_cast<Conv2dKernel>` 或 `Pool2dKernel`） | 可将 Pad → downstream 的拓扑匹配用 PatternMatcher 替代（~8 行），但 rewrite 逻辑保留命令式。优先级低——模式体已较紧凑（~40 行） |

### 8.4 重构模式统一结构

```cpp
common::Status XxxFusionPattern(KernelNet *net) {
  auto pattern = PatternBuilder("name")
      .MatchNode("seed", NodeType<SeedKernel>())
      .MatchNode("sink", NodeType<SinkKernel>())
      .Chain("seed", "sink")
      .SingleUse("seed")
      .Attr(...)         // 约束在 pattern 定义阶段声明
      .Build();

  for (;;) {             // match-one-rewrite-one loop
    auto matches = PatternMatcher(*net).Match(pattern);
    if (matches.empty()) break;
    auto& m = matches[0];

    // cast + cross-node check + RewriteRefModelJson + fusion kernel create
    // ...

    BatchRewriter rewriter(*net);
    rewriter.RemoveNode(sink->Index());
    rewriter.RemoveNode(seed->Index());
    AIC_RETURN_IF_ERROR(rewriter.Commit());
  }
  return Status::OK();
}
```

### 8.5 核心收益

1. **关注点分离**：匹配逻辑（"找什么"）收敛到 `PatternBuilder` 声明式 DSL，可读、可测、可复用；改写逻辑（"怎么做"）保留命令式灵活性
2. **消除样板**：`GraphViewer` + `for` + `CastNoCheck` + `nullptr check` + `GetOutputEdgesCount` 在每个模式中重复的 ~10 行代码完全消除
3. **约束前置**：`bin_mode != 1`、`CheckConvDtype`、`HavePool()/HaveAct()` 等约束在 Pattern 定义阶段声明，匹配引擎统一校验，不再散落在 `if-continue` 链中
4. **批量改写**：`BatchRewriter::Commit()` 合并多次 `ReleaseNode` + 单次 `Resolve()`，避免每删除一个节点就重建图拓扑
5. **扩展性提升**：新增融合模式只需定义 Pattern + 写 rewrite 回调（~40 行），不用复制完整的拓扑遍历样板