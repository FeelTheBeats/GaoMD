# Pattern Matcher 和 BatchRewriter

本文档介绍 AIC 编译器中声明式子图匹配和批量图改写机制。

## Pattern Builder DSL

使用 `PatternBuilder` 定义要匹配的子图模式：

```cpp
auto pattern = PatternBuilder("PatternName")
    .MatchNode("label1", NodeType<OpType1>())
    .MatchNode("label2", NodeType<OpType2>())
    .Chain("label1", "label2")           // 定义边：label1 → label2
    .Merge({"A", "B"}, "C")              // 多输入：A → C, B → C
    .Attr("label1", [](const Node& n) {  // 属性约束
      return true;
    })
    .SingleUse("label1")                 // 单用户约束
    .MaxUses("label2", 3)                // 最多 3 个用户
    .Build();
```

### 关键 API

| 方法 | 说明 |
|------|------|
| `MatchNode(label, typeCheck)` | 定义节点匹配条件，`typeCheck` 通常是 `NodeType<OpType>()` |
| `Chain(from, to)` | 定义有向边 from → to |
| `Merge(inputs, output)` | 定义多输入汇聚 |
| `Attr(label, predicate)` | 添加属性检查谓词 |
| `SingleUse(label)` | 限制节点只能有一个消费者 |
| `MaxUses(label, n)` | 限制节点最多 n 个消费者 |

## 匹配算法

`PatternMatcher` 使用回溯搜索算法：

1. **种子选择**：选择约束最强的节点作为起点（边连接最多的节点）
2. **候选筛选**：遍历图中所有节点，用 `typeCheck` 和 `Attr` 谓词过滤候选
3. **递归扩展**：从种子节点沿边方向递归扩展，尝试匹配相邻节点
4. **约束验证**：检查 `SingleUse`/`MaxUses` 约束和边的连接关系
5. **结果收集**：所有节点标签都匹配成功时，记录一个 `MatchResult`

```cpp
PatternMatcher matcher(graph);
std::vector<MatchResult> matches = matcher.Match(pattern);

for (const auto& match : matches) {
  NodeIndex nodeIdx = match.nodes.at("label1");
  Node* node = graph.GetNode(nodeIdx);
  // 处理匹配结果
}
```

## 批量改写

`BatchRewriter` 累积 `ReleaseNode` 请求，在 `Commit()` 时统一执行并调用单次 `Resolve()`。

> **注意**：`BatchRewriter` **不是事务**。节点的 `SetInputs`/`SetOutputs` 由调用者直接操作，`BatchRewriter` 只负责批量删除节点和统一 `Resolve()`。如果 `Resolve()` 失败，图可能处于部分改写状态，没有回滚机制。

```cpp
BatchRewriter rewriter(graph);

// 队列化删除请求
rewriter.RemoveNode(nodeIdx);

// 一次性提交：执行所有 ReleaseNode + 单次 Resolve()
auto status = rewriter.Commit();
```

## 实际应用示例

`SliceFuse` Pass 融合 `DmaIn → Slice(H) → Slice(W)` 模式：

```cpp
// 1. 定义模式
auto sliceFusePattern =
    PatternBuilder("SliceFuse")
        .MatchNode("dmaIn", NodeType<DmaInKernel>())
        .MatchNode("hSlice", NodeType<SliceKernel>())
        .MatchNode("wSlice", NodeType<SliceKernel>())
        .Chain("dmaIn", "hSlice")
        .Chain("hSlice", "wSlice")
        .Attr("hSlice", [](const Node& n) {
          auto* sk = CastNoCheck<SliceKernel>(&n);
          return sk && sk->attr_ref().mode == SliceAttr::Mode::kHeight;
        })
        .Attr("wSlice", [](const Node& n) {
          auto* sk = CastNoCheck<SliceKernel>(&n);
          return sk && sk->attr_ref().mode == SliceAttr::Mode::kWidth;
        })
        .SingleUse("hSlice")
        .Build();

// 2. 执行匹配
BatchRewriter rewriter(*kernelNet);
auto matches = PatternMatcher(*kernelNet).Match(sliceFusePattern);

// 3. 处理每个匹配
for (const auto& match : matches) {
  auto* hSlice = CastNoCheck<SliceKernel>(
      kernelNet->GetNode(match.nodes.at("hSlice")));
  auto* wSlice = CastNoCheck<SliceKernel>(
      kernelNet->GetNode(match.nodes.at("wSlice")));

  uint32_t extraOff = 0;
  if (!CheckWsliceAlignment(hSlice, wSlice, &extraOff)) continue;

  // 直接修改 hSlice 的 IO 和属性
  hSlice->attr_ref().extra_off_en = true;
  hSlice->attr_ref().extra_off = extraOff;
  hSlice->SetOutputs({wSlice->GetOutNodeArg(0)});

  // 队列化 wSlice 删除
  rewriter.RemoveNode(wSlice->Index());
}

// 4. 一次性提交
if (rewriter.HasPending()) {
  rewriter.Commit();
}
```

## 设计要点

1. **声明式**：模式定义清晰，关注"是什么"而非"怎么找"
2. **可组合**：通过 Builder 模式灵活组合各种约束
3. **批量改写**：多次 `RemoveNode` 合并为单次 `Resolve()`，避免反复重建图拓扑
4. **轻量匹配**：基于 `dynamic_cast` 的类型检查 + 回溯搜索，适合中小规模模式

## 文件位置

- `include/aic/transforms/pattern_matcher.h` — 匹配器接口
- `include/aic/transforms/graph_rewriter.h` — BatchRewriter 接口
- `src/transforms/pattern_matcher.cpp` — 匹配算法实现
- `target/tensor_brain/transforms/slice_fuse.cpp` — 应用示例
- `tests/cpp/pattern_matcher_test.cpp` — 单元测试
