# Pattern Matcher 完整走读：以 `SliceFuse` 为例

本文档带你一行一行地跟代码，理解 Pattern Matcher 的内部数据结构和匹配流程。

---

## 零、前置知识：核心数据结构总览

```
┌─────────────────────────────────────────────────────────────────┐
│  PatternGraph::NodeDef                                           │
│  ┌─────────────┬──────────────────────────────────────────────┐ │
│  │ label       │ "dmaIn" / "hSlice" / "wSlice"               │ │
│  │ typeCheck   │ dynamic_cast<DmaInKernel*> ?                │ │
│  │ attrChecks  │ [lambda1, lambda2, ...]                     │ │
│  │ maxUses     │ 1 (SingleUse), INT_MAX (unlimited)          │ │
│  └─────────────┴──────────────────────────────────────────────┘ │
│                                                                  │
│  PatternGraph::EdgeDef                                           │
│  ┌─────────────┬──────────────────────────────────────────────┐ │
│  │ from        │ "dmaIn"                                       │ │
│  │ to          │ "hSlice"                                      │ │
│  └─────────────┴──────────────────────────────────────────────┘ │
│                                                                  │
│  MatchResult (一次完整匹配的结果)                                │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ nodes: unordered_map<string, NodeIndex>                     │ │
│  │   { "dmaIn"→5, "hSlice"→8, "wSlice"→12 }                  │ │
│  └────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

- **`NodeIndex`** 就是 `int`，图中每个算子的唯一 ID。
- **`PatternGraph`** 是构建好的"模式模板"，包含 `vector<NodeDef>` 和 `vector<EdgeDef>`。
- **`MatchResult`** 是匹配成功后，"模式标签 → 图中实际节点 ID"的映射表。

**源文件位置：**

| 文件 | 内容 |
|------|------|
| `include/aic/transforms/pattern_matcher.h` | 数据结构定义（NodeDef, EdgeDef, MatchResult） + Builder/Matcher 接口 |
| `include/aic/transforms/graph_rewriter.h` | BatchRewriter（批量删除 + 单次 Resolve） |
| `src/transforms/pattern_matcher.cpp` | 匹配算法实现 |
| `target/tensor_brain/transforms/slice_fuse.cpp` | 应用示例 |
| `tests/cpp/pattern_matcher_test.cpp` | 单元测试 |

---

## 一、第一阶段：Pattern 构建（`PatternBuilder` → `PatternGraph`）

入口代码（`slice_fuse.cpp:130-155`）：

```cpp
auto sliceFusePattern =
    PatternBuilder("SliceFuse")
        .MatchNode("dmaIn", NodeType<DmaInKernel>())
        .MatchNode("hSlice", NodeType<SliceKernel>())
        .MatchNode("wSlice", NodeType<SliceKernel>())
        .Chain("dmaIn", "hSlice")
        .Chain("hSlice", "wSlice")
        .Attr("dmaIn",
              [](const Node& n) {
                auto* dmaIn = CastNoCheck<DmaInKernel>(&n);
                if (!dmaIn) return false;
                Tensor* inTensor = Cast<Tensor>(dmaIn->GetInNodeArg(0));
                return inTensor && inTensor->pattern() == Pattern::kNHWC;
              })
        .Attr("hSlice",
              [](const Node& n) {
                auto* sk = CastNoCheck<SliceKernel>(&n);
                return sk && sk->attr_ref().mode == SliceAttr::Mode::kHeight;
              })
        .Attr("wSlice",
              [](const Node& n) {
                auto* sk = CastNoCheck<SliceKernel>(&n);
                return sk && sk->attr_ref().mode == SliceAttr::Mode::kWidth;
              })
        .SingleUse("hSlice")
        .Build();
```

### 1.1 `PatternBuilder("SliceFuse")` — 构造函数

```cpp
explicit PatternBuilder(const std::string& name) : name_(name) {}
```

只存名字。此时：

```
PatternBuilder {
  name_ = "SliceFuse"
  nodeDefs_ = []       // 空
  edgeDefs_ = []       // 空
}
```

### 1.2 `MatchNode` — 填充 `nodeDefs_`

三次 `.MatchNode(...)` 调用。以第一个为例：

```cpp
.MatchNode("dmaIn", NodeType<DmaInKernel>())
```

`NodeType<DmaInKernel>()` 展开（`pattern_matcher.h:101-105`）是一个模板函数，返回一个 lambda：

```cpp
template<typename OpType>
inline std::function<bool(const Node&)> NodeType() {
  return [](const Node& n) -> bool {
    return dynamic_cast<const OpType*>(&n) != nullptr;
  };
}
```

即：`[](const Node& n) -> bool { return dynamic_cast<const DmaInKernel*>(&n) != nullptr; }`

`MatchNode()` 实现（`pattern_matcher.cpp:19-26`）：

```cpp
PatternBuilder& PatternBuilder::MatchNode(
    const std::string& label, std::function<bool(const Node&)> typeCheck) {
  PatternGraph::NodeDef def;
  def.label = label;                          // "dmaIn"
  def.typeCheck = std::move(typeCheck);       // dynamic_cast lambda
  // def.attrChecks 默认为空 vector
  // def.maxUses 默认为 INT_MAX（无限制）
  nodeDefs_.push_back(std::move(def));
  return *this;
}
```

**三次 MatchNode 之后，`nodeDefs_`：**

```
nodeDefs_ = [
  { label:"dmaIn",  typeCheck: IsDmaInKernel?,   attrChecks:[], maxUses:∞ },
  { label:"hSlice", typeCheck: IsSliceKernel?,   attrChecks:[], maxUses:∞ },
  { label:"wSlice", typeCheck: IsSliceKernel?,   attrChecks:[], maxUses:∞ },
]
```

### 1.3 `Chain` — 填充 `edgeDefs_`

两次 `.Chain(...)` 调用（`pattern_matcher.cpp:28-35`）：

```cpp
PatternBuilder& PatternBuilder::Chain(const std::string& from,
                                       const std::string& to) {
  PatternGraph::EdgeDef edge;
  edge.from = from;
  edge.to = to;
  edgeDefs_.push_back(std::move(edge));
  return *this;
}
```

**两次 Chain 之后：**

```
edgeDefs_ = [
  { from:"dmaIn",  to:"hSlice" },      // Chain("dmaIn", "hSlice")
  { from:"hSlice", to:"wSlice" },      // Chain("hSlice", "wSlice")
]
```

表达的拓扑关系：**`dmaIn → hSlice → wSlice`**（一条三节点的有向链）。

### 1.4 `Attr` — 往 NodeDef 里追加属性检查

三次 `.Attr(...)` 调用。以 `.Attr("hSlice", ...)` 为例（`pattern_matcher.cpp:45-58`）：

```cpp
PatternBuilder& PatternBuilder::Attr(
    const std::string& label, std::function<bool(const Node&)> predicate) {
  for (auto& def : nodeDefs_) {
    if (def.label == label) {   // 找到 label=="hSlice" 的那条 NodeDef
      def.attrChecks.push_back(std::move(predicate));  // 追加到 attrChecks 列表
      return *this;
    }
  }
  // 找不到 label 就打印 warning
  TLOG_W(...);
  return *this;
}
```

SliceFuse 传递的三个 Attr predicate：

| label | predicate 做的事 |
|-------|-----------------|
| `"dmaIn"` | 检查 DmaIn 的输入 Tensor 的 `pattern()` 是否为 `kNHWC`（NHWC 内存排布） |
| `"hSlice"` | 检查 SliceKernel 的 `attr_ref().mode` 是否为 `kHeight`（H 方向切片） |
| `"wSlice"` | 检查 SliceKernel 的 `attr_ref().mode` 是否为 `kWidth`（W 方向切片） |

**Attr 之后，`nodeDefs_`：**

```
nodeDefs_ = [
  { label:"dmaIn",  typeCheck: IsDmaInKernel?,
    attrChecks:[IsNHWC?],                           maxUses:∞ },
  { label:"hSlice", typeCheck: IsSliceKernel?,
    attrChecks:[mode==kHeight?],                    maxUses:∞ },
  { label:"wSlice", typeCheck: IsSliceKernel?,
    attrChecks:[mode==kWidth?],                     maxUses:∞ },
]
```

### 1.5 `SingleUse("hSlice")` — 设置消费者上限

`SingleUse` 是 `MaxUses(label, 1)` 的语法糖（`pattern_matcher.cpp:60-61`）：

```cpp
PatternBuilder& PatternBuilder::SingleUse(const std::string& label) {
  return MaxUses(label, 1);
}
```

`MaxUses` 实现（`pattern_matcher.cpp:64-76`）：

```cpp
PatternBuilder& PatternBuilder::MaxUses(const std::string& label, int maxUses) {
  for (auto& def : nodeDefs_) {
    if (def.label == label) {
      def.maxUses = maxUses;          // 设为 1
      return *this;
    }
  }
  // 找不到 label 就打印 warning
  TLOG_W(...);
  return *this;
}
```

这表示：hSlice 只能有 **1 个消费者**（即只有 wSlice 这一个下游）。如果 hSlice 在图中被多个下游消费，就不能安全融合（融合后会断掉其他分支）。

**最终 `nodeDefs_`：**

```
nodeDefs_ = [
  { label:"dmaIn",  typeCheck: IsDmaInKernel?,
    attrChecks:[IsNHWC?],                           maxUses:∞    },
  { label:"hSlice", typeCheck: IsSliceKernel?,
    attrChecks:[mode==kHeight?],                    maxUses:1    },  ← SingleUse
  { label:"wSlice", typeCheck: IsSliceKernel?,
    attrChecks:[mode==kWidth?],                     maxUses:∞    },
]
```

### 1.6 `Build()` — 产出 `PatternGraph`

```cpp
PatternGraph PatternBuilder::Build() {
  PatternGraph graph;
  for (auto& def : nodeDefs_) graph.AddNodeDef(std::move(def));
  for (auto& edge : edgeDefs_) graph.AddEdgeDef(std::move(edge));
  return graph;
}
```

就是把 Builder 里累积的 `nodeDefs_` 和 `edgeDefs_` 搬进 `PatternGraph` 对象。

**构建阶段到此结束。** 此时 `sliceFusePattern` 已经是一个完整定义好的模式，描述了"要匹配什么样的子图"。

---

## 二、第二阶段：模式匹配（`PatternMatcher::Match`）

调用入口（`slice_fuse.cpp:158`）：

```cpp
auto matches = PatternMatcher(*kernelNet).Match(sliceFusePattern);
```

### 2.1 主流程框架

```cpp
// pattern_matcher.cpp:136-165
std::vector<MatchResult> PatternMatcher::Match(const PatternGraph& pattern) {
  std::vector<MatchResult> results;

  if (pattern.NodeDefs().empty()) {
    return results;                                  // 空模式 → 空结果
  }

  /* Seed selection */
  const std::string& seedLabel = pattern.MostConstrainedNode();

  /* Find candidates */
  std::vector<NodeIndex> candidates;
  for (auto& node : graph_.Nodes()) {
    if (pattern.NodeCheck(seedLabel, node)) {        // 用种子标签的约束去筛
      candidates.push_back(node.Index());
    }
  }

  /* Try match from each candidate */
  for (NodeIndex seedIdx : candidates) {
    MatchResult current;
    current.nodes[seedLabel] = seedIdx;
    std::unordered_set<NodeIndex> used{seedIdx};

    if (TryExpand(seedLabel, seedIdx, pattern, current, used)) {
      results.push_back(std::move(current));          // 匹配成功，收集结果
    }
  }

  return results;
}
```

整个流程分 4 步，下面逐个展开。

---

### 2.2 Step 1: 种子选择 — `MostConstrainedNode()`

算法（`pattern_matcher.cpp:91-117`）：统计每个 NodeDef 相连的边数，返回最多的那个。

```
统计边数：
  "dmaIn"  → 1 条边 (dmaIn→hSlice)
  "hSlice" → 2 条边 (dmaIn→hSlice, hSlice→wSlice)   ← 最多！
  "wSlice" → 1 条边 (hSlice→wSlice)

返回: "hSlice"
```

为什么要选约束最强的？因为约束越多 → 候选越少 → 搜索空间越小。hSlice 既是 SliceKernel 类型，又要求 mode==kHeight，还要求 SingleUse，这些约束叠加起来会让候选集很小，从它开始能最快收敛。

---

### 2.3 Step 2: 海选候选节点 — `NodeCheck()`

```cpp
for (auto& node : graph_.Nodes()) {
    if (pattern.NodeCheck(seedLabel, node)) {
        candidates.push_back(node.Index());
    }
}
```

对图中所有 100 个节点（举例），逐个跑 `NodeCheck("hSlice", node)`：

`NodeCheck` 实现（`pattern_matcher.cpp:119-130`）：

```cpp
bool PatternGraph::NodeCheck(const std::string& label, const Node& node) const {
  for (const auto& def : nodeDefs_) {
    if (def.label == label) {
      // ① 类型检查
      if (!def.typeCheck(node)) return false;
      // ② 属性检查（逐个 lambda）
      for (const auto& check : def.attrChecks) {
        if (!check(node)) return false;
      }
      return true;    // 全部通过
    }
  }
  return false;       // 找不到 label（不应该发生）
}
```

对于种子 `"hSlice"`，检查过程：

```
对图中每个节点：
  ├─ typeCheck:  dynamic_cast<SliceKernel*>(&node) != nullptr ?
  │   不是 SliceKernel → false，跳过
  │   是 SliceKernel   → 继续
  └─ attrChecks[0]:  sk->attr_ref().mode == kHeight ?
      不是 kHeight → false，跳过
      是 kHeight   → true，加入候选
```

**假设图中 100 个节点，3 个是 SliceKernel(kHeight) → 候选集 = {8, 20, 35}。**

这就是一个粗筛过程：用最严的约束先把搜索空间缩小。

---

### 2.4 Step 3: 逐个种子候选尝试匹配

```cpp
for (NodeIndex seedIdx : candidates) {   // seedIdx = 8, 20, 35 ...
    MatchResult current;
    current.nodes[seedLabel] = seedIdx;                // {"hSlice": 8}
    std::unordered_set<NodeIndex> used{seedIdx};       // used = {8}

    if (TryExpand(seedLabel, seedIdx, pattern, current, used)) {
        results.push_back(std::move(current));
    }
}
```

对每个候选，初始化一个部分匹配状态，然后调用 `TryExpand` 去尝试把模式的其余部分补全。

---

### 2.5 Step 4: 递归扩展 — `TryExpand()`（匹配的灵魂）

这是整个匹配器的核心。我们以 `TryExpand("hSlice", 8, ...)` 为起点，逐步展开。

#### 参数说明：

| 参数 | 含义 | 初始值 |
|------|------|--------|
| `label` | 当前正在处理的模式标签 | `"hSlice"` |
| `nodeIdx` | 图中已匹配该标签的节点 ID | `8` |
| `current` | 当前的部分匹配结果 | `{"hSlice": 8}` |
| `used` | 已被匹配占用的节点集合（防重复） | `{8}` |

#### 4a. SingleUse / MaxUses 检查

```cpp
// pattern_matcher.cpp:175-183
for (const auto& def : pattern.NodeDefs()) {
    if (def.label == label) {
        if (def.maxUses != std::numeric_limits<int>::max() &&
            static_cast<int>(node->GetOutputEdgesCount()) > def.maxUses) {
            return false;   // 输出边数 > 允许值 → 不匹配
        }
        break;
    }
}
```

对于 `label="hSlice"`，`maxUses=1`：
- 如果节点 #8 有 >1 条输出边（即被多个下游消费） → 不能安全融合，返回 false
- 如果 ≤1 → 继续

> **注意**：这个检查在递归的每一层都会执行。当 TryExpand 递归到 `"wSlice"` 时，也会查 wSlice 的 maxUses（∞，跳过）。

#### 4b. 全部匹配？最终检查

```cpp
// pattern_matcher.cpp:186-210
bool allFilled = true;
for (const auto& def : pattern.NodeDefs()) {
    if (current.nodes.find(def.label) == current.nodes.end()) {
        allFilled = false;
        break;
    }
}
```

当前 `current.nodes` 只有 `{"hSlice": 8}`，缺 `"dmaIn"` 和 `"wSlice"`。`allFilled=false`，跳过"全部匹配"验证，进入**沿边扩展**。

如果 `allFilled=true`，则验证所有模式边在图中是否真的连接：

```cpp
if (allFilled) {
    for (const auto& edge : pattern.EdgeDefs()) {
        const Node* fromNode = graph_.GetNode(current.nodes.at(edge.from));
        const Node* toNode   = graph_.GetNode(current.nodes.at(edge.to));
        // 遍历 fromNode 的所有输出，看 toNode 是否在其中
        // 如果有一条边不连 → return false
    }
    return true;   // 🎉 完整匹配！
}
```

#### 4c. 沿边扩展 — 核心逻辑

```cpp
// pattern_matcher.cpp:212-277
for (const auto& edge : pattern.EdgeDefs()) {
    auto fromIt = current.nodes.find(edge.from);
    auto toIt   = current.nodes.find(edge.to);
    bool fromMatched = fromIt != current.nodes.end();
    bool toMatched   = toIt   != current.nodes.end();
```

遍历所有模式边：`dmaIn→hSlice` 和 `hSlice→wSlice`。

---

##### 情况 A：`fromMatched && toMatched` — 两端都已知

边已经在 current 中绑定了两端节点，验证图中是否存在这条边。

```cpp
if (fromMatched && toMatched) {
    const Node* matchedFrom = graph_.GetNode(fromIt->second);
    const Node* matchedTo   = graph_.GetNode(toIt->second);
    // 遍历 matchedFrom 的所有输出，看 matchedTo 是否在其中
    // 如果存在 → continue（这条边没问题）
    // 如果不存在 → return false（模式说它们应该连接，但实际没连）
}
```

##### 情况 B：`fromMatched && !toMatched` — 只有 from 已知（正向扩展）

已知头部节点，沿输出方向找尾部。例如边 `hSlice→wSlice`，已知 `hSlice=#8`，要找 `wSlice`。

```cpp
if (fromMatched) {
    const Node* matchedFrom = graph_.GetNode(fromIt->second);  // hSlice(#8)

    // 遍历 hSlice 的所有输出节点
    for (auto it = matchedFrom->OutputNodesBegin();
         it != matchedFrom->OutputNodesEnd(); ++it) {
        if (used.count(it->Index())) continue;                 // 已被占用，跳过
        if (!pattern.NodeCheck(edge.to, *it)) continue;        // 不满足 wSlice 约束，跳过

        // 找到候选！临时绑定
        current.nodes[edge.to] = it->Index();                  // {"wSlice": 12}
        used.insert(it->Index());                              // used = {8, 12}

        if (TryExpand(edge.to, it->Index(), pattern, current, used)) {
            return true;    // 递归成功，一路返回 true
        }

        // 递归失败 → 回溯
        used.erase(it->Index());
        current.nodes.erase(edge.to);
    }
    return false;   // 所有输出都试过了，没有匹配的
}
```

假设 hSlice(#8) 的输出节点是 `[Slice(#12), ReLU(#15)]`：

| 输出节点 | IsSliceKernel? | mode==kWidth? | NodeCheck 通过? |
|---------|---------------|---------------|----------------|
| Slice(#12) | true (dynamic_cast 成功) | true | ✓ |
| ReLU(#15) | false (dynamic_cast 失败) | — | ✗ |

只有 Slice(#12) 通过检查：

```
current.nodes = { "hSlice": 8, "wSlice": 12 }
used = {8, 12}

→ 递归 TryExpand("wSlice", 12, ...)
```

##### 情况 C：`!fromMatched && toMatched` — 只有 to 已知（反向扩展）

已知尾部节点，沿输入方向找头部。例如边 `dmaIn→hSlice`，已知 `hSlice=#8`，要找 `dmaIn`。

```cpp
if (toMatched) {
    const Node* matchedTo = graph_.GetNode(toIt->second);  // hSlice(#8)

    // 遍历 hSlice 的所有输入节点
    for (auto it = matchedTo->InputNodesBegin();
         it != matchedTo->InputNodesEnd(); ++it) {
        if (used.count(it->Index())) continue;
        if (!pattern.NodeCheck(edge.from, *it)) continue;   // 用 "dmaIn" 的约束检查

        current.nodes[edge.from] = it->Index();              // {"dmaIn": 5}
        used.insert(it->Index());

        if (TryExpand(edge.from, it->Index(), pattern, current, used)) {
            return true;
        }

        // 回溯
        used.erase(it->Index());
        current.nodes.erase(edge.from);
    }
    return false;
}
```

假设 hSlice(#8) 的输入节点是 `[Conv(#3), DmaIn(#5), Pool(#7)]`：

| 输入节点 | IsDmaInKernel? | NHWC? | NodeCheck 通过? |
|---------|---------------|-------|----------------|
| Conv(#3) | false | — | ✗ |
| DmaIn(#5) | true | true | ✓ |
| Pool(#7) | false | — | ✗ |

只有 DmaIn(#5) 通过：

```
current.nodes = { "hSlice": 8, "dmaIn": 5 }
used = {8, 5}

→ 递归 TryExpand("dmaIn", 5, ...)
```

---

### 2.6 完整递归调用链追踪

用我们之前梳理的示例，完整展示 `TryExpand` 的调用栈：

```
Match() 发现候选: 种子 hSlice, candidates = [8, 20, 35]

┌─ 候选 #1: hSlice=8 ──────────────────────────────────────────────┐
│                                                                     │
│ TryExpand("hSlice", 8)          current={"hSlice":8}               │
│  ├─ SingleUse 检查: outputEdges≤1 ✓                               │
│  ├─ allFilled 检查: 缺 "dmaIn" 和 "wSlice" → 继续                  │
│  │                                                                  │
│  ├─ 处理边 dmaIn→hSlice:                                          │
│  │   fromMatched=false, toMatched=true → 反向扩展                  │
│  │   遍历 hSlice(#8) 的输入: [Conv#3, DmaIn#5, Pool#7]            │
│  │     Conv#3  → NodeCheck("dmaIn") → false, 跳过                  │
│  │     DmaIn#5 → NodeCheck("dmaIn") → true!                       │
│  │       current={"hSlice":8, "dmaIn":5}, used={8,5}              │
│  │                                                                  │
│  │       ┌ TryExpand("dmaIn", 5) ───────────────────────────┐     │
│  │       │  ├─ SingleUse: maxUses=∞, 跳过                    │     │
│  │       │  ├─ allFilled: 缺 "wSlice" → 继续                 │     │
│  │       │  │                                                │     │
│  │       │  ├─ 边 dmaIn→hSlice:                              │     │
│  │       │  │  两边都已知(#5, #8) → 验证图中连接: ✓          │     │
│  │       │  │                                                │     │
│  │       │  ├─ 边 hSlice→wSlice:                             │     │
│  │       │  │  fromMatched=true(#8), toMatched=false         │     │
│  │       │  │  正向扩展，遍历 hSlice(#8) 输出:               │     │
│  │       │  │    [Slice#12, ReLU#15]                         │     │
│  │       │  │    Slice#12 → NodeCheck("wSlice") → true!      │     │
│  │       │  │      current={"hSlice":8,"dmaIn":5,"wSlice":12}│     │
│  │       │  │      used={8,5,12}                              │     │
│  │       │  │                                                │     │
│  │       │  │      ┌ TryExpand("wSlice", 12) ─────────┐      │     │
│  │       │  │      │  ├─ SingleUse: maxUses=∞, 跳过    │      │     │
│  │       │  │      │  ├─ allFilled: dmaIn✓ hSlice✓     │      │     │
│  │       │  │      │  │   wSlice✓ → ALL FILLED!        │      │     │
│  │       │  │      │  │                                │      │     │
│  │       │  │      │  ├─ 验证所有边:                   │      │     │
│  │       │  │      │  │   dmaIn(#5)→hSlice(#8): ✓     │      │     │
│  │       │  │      │  │   hSlice(#8)→wSlice(#12): ✓   │      │     │
│  │       │  │      │  │                                │      │     │
│  │       │  │      │  └─ return true 🎯               │      │     │
│  │       │  │      └──────────────────────────────────┘      │     │
│  │       │  │                                                │     │
│  │       │  │   递归成功 → return true                        │     │
│  │       │  └────────────────────────────────────────────────┘     │
│  │       │                                                          │
│  │       └─ return true ──────────────────────────────────────┘     │
│  │                                                                  │
│  └─ return true → Match() 将 current 加入 results                   │
│                                                                     │
│  results = [{ nodes: {"dmaIn":5, "hSlice":8, "wSlice":12} }]       │
│                                                                     │
│  继续候选 #2: hSlice=20 ...                                         │
│  继续候选 #3: hSlice=35 ...                                         │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.7 回溯机制

如果某个候选在某层搜索中，所有分支都返回 false：

```
例：hSlice(#35) 的输入中有 DmaIn(#40)，但 DmaIn(#40) 的输出都不是 SliceKernel(kWidth)
     → TryExpand("wSlice") 遍历完所有输出都没找到
     → return false
     → TryExpand("dmaIn") 收到 false，回溯：erase("dmaIn"), erase from used
     → 继续尝试 hSlice(#35) 的下一个输入
     → 如果所有输入都不行 → return false
     → 候选 #35 被跳过
```

`used` 集合的作用：防止同一个图中的节点被匹配到多个模式标签（保证一对一映射）。

---

## 三、匹配算法流程图

```
                ┌──────────────────────┐
                │ 选出种子标签 "hSlice"  │
                │ (边连接最多=约束最强)  │
                └──────────┬───────────┘
                           │
                ┌──────────▼───────────┐
                │ 遍历全图节点           │
                │ NodeCheck("hSlice")   │
                │ → 候选集 {8,20,35}     │
                └──────────┬───────────┘
                           │
              ┌────────────▼────────────┐
              │ for each candidate:     │
              │   current={hSlice:8}    │
              │   TryExpand("hSlice")   │
              └────────────┬────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    ┌────▼────┐      ┌─────▼─────┐     ┌─────▼─────┐
    │边: dmaIn│      │边: hSlice │     │           │
    │ →hSlice │      │ →wSlice   │     │   ...     │
    │         │      │           │     │           │
    │ to已知  │      │ from已知  │     │           │
    │ 反向扩展│      │ 正向扩展  │     │           │
    │ 找上游  │      │ 找下游    │     │           │
    └────┬────┘      └─────┬─────┘     └───────────┘
         │                 │
    ┌────▼────┐      ┌─────▼─────┐
    │dmaIn=5  │      │wSlice=12  │
    │递归     │      │递归       │
    │TryExpand│      │TryExpand  │
    │("dmaIn")│      │("wSlice") │
    └────┬────┘      └─────┬─────┘
         │                 │
         └────────┬────────┘
                  │
          ┌───────▼───────┐
          │ allFilled?    │
          │ 验证所有边     │
          │ 返回 true 🎯  │
          └───────────────┘
```

---

## 四、第三阶段：改写（Rewrite）

匹配结果出来后（`slice_fuse.cpp:160-187`）：

```cpp
BatchRewriter rewriter(*kernelNet);
auto matches = PatternMatcher(*kernelNet).Match(sliceFusePattern);

for (const auto& match : matches) {
    // match.nodes = { "dmaIn":5, "hSlice":8, "wSlice":12 }

    auto* dmaIn  = CastNoCheck<DmaInKernel>(kernelNet->GetNode(5));
    auto* hSlice = CastNoCheck<SliceKernel>(kernelNet->GetNode(8));
    auto* wSlice = CastNoCheck<SliceKernel>(kernelNet->GetNode(12));

    if (!dmaIn || !hSlice || !wSlice) continue;

    // 额外业务校验 ①：DmaIn 的所有子节点必须全是 Slice
    //   （保证不会误伤 — 如果 DmaIn 还连着非 Slice 的消费者就不融合）
    bool allChildrenAreSlice = true;
    for (auto it = dmaIn->OutputNodesBegin();
         it != dmaIn->OutputNodesEnd(); ++it) {
        if (!CastNoCheck<SliceKernel>(&(*it))) {
            allChildrenAreSlice = false;
            break;
        }
    }
    if (!allChildrenAreSlice) continue;

    // 额外业务校验 ②：wSlice 的起始偏移必须 32B 对齐
    uint32_t extraOff = 0;
    if (!CheckWsliceAlignment(hSlice, wSlice, &extraOff)) continue;

    // 执行改写：绕开 wSlice
    RewriteSlicePair(hSlice, wSlice, extraOff, rewriter);
}
```

### `RewriteSlicePair` 做了什么

```cpp
void SliceFuse::RewriteSlicePair(SliceKernel* hSlice, SliceKernel* wSlice,
                                 uint32_t extraOff,
                                 BatchRewriter& rewriter) const {
  // ① 拿到 wSlice 的输出 Tensor（最终输出目标）
  Tensor* nextSliceOutTensor = Cast<Tensor>(wSlice->GetOutNodeArg(0));

  // ② 更新 hSlice 的属性，开启 extra_off 模式
  hSlice->attr_ref().extra_off_en = true;
  hSlice->attr_ref().extra_off = extraOff;

  // ③ hSlice 直接输出到原来 wSlice 的输出 Tensor
  hSlice->SetOutputs({nextSliceOutTensor});

  // ④ 同步更新 HW Layer 的 connection
  HwGraph& hwGraph = hSlice->HwGraphRef();
  SliceLayer* sliceLy = dynamic_cast<SliceLayer*>(hwGraph.GetHwLayer(0));
  if (sliceLy) {
    sliceLy->SetOutputs({nextSliceOutTensor});
    sliceLy->SetExtraInfo(true, extraOff);
  }

  // ⑤ 标记 wSlice 待删除
  rewriter.RemoveNode(wSlice->Index());
}
```

### 改写前后对比

```
改写前:
  DmaIn ──→ hSlice(kHeight) ──→ wSlice(kWidth) ──→ outputTensor

改写后:
  DmaIn ──→ hSlice(kHeight, extra_off=32B对齐偏移) ──→ outputTensor
                                      wSlice (已删除 ✗)
```

### `BatchRewriter::Commit()`

```cpp
if (rewriter.HasPending()) {
    auto status = rewriter.Commit();
}
```

`Commit()` 做的事（`graph_rewriter.h:48-69`）：

```cpp
common::Status Commit() {
    // ① 批量执行 ReleaseNode（删除所有标记的节点）
    for (auto idx : pendingRemovals_) {
        graph_.ReleaseNode(idx);
    }
    // ② 单次 Resolve()（重建图拓扑）
    auto status = graph_.Resolve();
    pendingRemovals_.clear();
    return status;
}
```

**关键设计**：多个匹配对应多个 `RemoveNode`，但只在最后调用一次 `Resolve()`。避免每删除一个节点就重建一次拓扑。

---

## 五、关键设计要点总结

### 5.1 回溯搜索

- 可以正着找（from 已知沿输出找 to）或反着找（to 已知沿输入找 from）
- 自动适应部分匹配状态：无需规定匹配顺序
- 匹配失败时自动回溯（erase + resume），尝试下一个候选

### 5.2 `used` 集合

保证同一个图中节点不会被匹配到多个模式标签（一对一映射）。没有这个集合，同一个节点可能被匹配为 `hSlice` 后又匹配为 `wSlice`。

### 5.3 约束分层（从粗到细）

| 层级 | 检查内容 | 检查时机 |
|------|---------|---------|
| typeCheck | `dynamic_cast` 类型匹配 | 候选筛选 + 边扩展时 |
| attrChecks | 属性谓词（如 mode==kHeight） | 候选筛选 + 边扩展时 |
| maxUses | 输出边数限制（如 SingleUse） | TryExpand 递归层中 |
| 边连接 | 图中是否真的有这条边 | allFilled 最终验证 |

### 5.4 非事务性改写

`BatchRewriter` 只负责：
1. 批量 `ReleaseNode`
2. 单次 `Resolve()`

节点的 IO 修改（如 `SetOutputs`）由调用者直接操作。如果 `Resolve()` 失败，图可能处于部分改写状态——**没有回滚机制**。文档里也明确说明了这一点。

### 5.5 种子选择策略

当前实现：简单启发式 — 选边最多的节点（`MostConstrainedNode`）。

为什么？边越多 = 参与的模式约束越多 = 候选越少 = 搜索空间越小。未来可以做更高级的策略（如基于类型索引统计实际候选数）。

### 5.6 匹配是"贪婪"的

每个种子候选只产生 **一个** 成功的匹配结果（`TryExpand` 返回 true 就立即 `return true`，不会继续搜索同一个种子的其他可能绑定）。

对于 `SliceFuse` 的场景（三节点线性链，SingleUse 约束），这种策略是合理的——同一个 hSlice 不可能有第二个 wSlice 下游。

---

## 六、文件索引

| 文件 | 内容 |
|------|------|
| `include/aic/transforms/pattern_matcher.h` | PatternGraph::NodeDef/EdgeDef、MatchResult、PatternBuilder/PatternMatcher 接口 |
| `include/aic/transforms/graph_rewriter.h` | BatchRewriter 接口 |
| `src/transforms/pattern_matcher.cpp` | 匹配算法实现（Match, TryExpand, MostConstrainedNode, NodeCheck） |
| `target/tensor_brain/transforms/slice_fuse.cpp` | SliceFuse Pass — 完整的 Pattern Builder + Match + Rewrite 示例 |
| `tests/cpp/pattern_matcher_test.cpp` | 单元测试 |
| `docs/PATTERN_MATCHER.md` | 原设计文档 |
