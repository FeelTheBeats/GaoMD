# PatternMatcher 走读笔记

> 本文档是对 `2026-06-05` ~ `2026-06-18` 期间引入的**声明式子图匹配基础设施**（`PatternMatcher`）的代码走读总结，涵盖走读路径、实现思路、关键设计点和性能分析。
>
> **注意**：`BatchRewriter`（`graph_rewriter.h`）是与 PatternMatcher **完全独立**的工具类，两者无任何代码耦合。本文档将其放在末尾独立章节说明，并在 SliceFuse 案例中展示两者的组合使用方式。

---

## 一、走读路径

```
                    ┌──────────────────────────────┐
                    │  pattern_matcher.h            │  ← 1. 接口定义
                    │  (PatternBuilder,             │
                    │   PatternGraph,               │
                    │   PatternMatcher)             │
                    └──────────────┬───────────────┘
                                   │ 实现
                    ┌──────────────▼───────────────┐
                    │  pattern_matcher.cpp          │  ← 2. 核心实现
                    └──────────────┬───────────────┘
                                   │ 验证
                    ┌──────────────▼───────────────┐
                    │  pattern_matcher_test.cpp     │  ← 3. 单元测试
                    └──────────────────────────────┘

          ┌─ 以上是 PatternMatcher 核心，以下是独立工具与应用案例 ─┐

                    ┌──────────────────────────────┐
                    │  graph_rewriter.h             │  ← 独立工具：批量删除
                    │  (BatchRewriter)              │     与 PatternMatcher 无耦合
                    └──────────────────────────────┘

                    ┌──────────────────────────────┐
                    │  slice_fuse.cpp               │  ← 应用案例：组合使用
                    │  (PatternMatcher +            │     PatternMatcher 匹配 +
                    │   BatchRewriter)              │     BatchRewriter 清理旧节点
                    └──────────────────────────────┘
```

### Step 1 — `include/aic/transforms/pattern_matcher.h`（~125 行）

定义了四个核心概念：

| 类 | 职责 |
|----|------|
| `MatchResult` | `label → NodeIndex` 的哈希表，表示一次完整匹配 |
| `PatternGraph::NodeDef` | 描述一个模式节点的约束：类型检查、属性谓词列表、最大使用次数 |
| `PatternGraph::EdgeDef` | 一条有向边 `from → to` |
| `PatternBuilder` | 流式 DSL，构建 `PatternGraph` |
| `PatternMatcher` | 匹配引擎：输入 `PatternGraph`，输出 `vector<MatchResult>` |

`PatternBuilder` 提供的关键 API：

- `MatchNode(label, typeCheck)` — 注册一个模式节点（通常配合 `NodeType<T>()`）
- `Chain(from, to)` — 添加有向边
- `Merge({A, B}, C)` — 多输入汇聚，等价于 A→C + B→C
- `Attr(label, predicate)` — 属性约束 lambda
- `SingleUse(label)` — 等价于 `MaxUses(label, 1)`
- `MaxUses(label, n)` — 限制该节点的输出边数
- `Build()` — 产出不可变的 `PatternGraph`

辅助模板 `NodeType<T>()` 封装了 `dynamic_cast` 类型检查。

### Step 2 — `src/transforms/pattern_matcher.cpp`（~290 行）

匹配引擎的核心实现，分为三层：

**层 1：PatternBuilder 方法**

每个 Builder 方法往内部 `nodeDefs_` / `edgeDefs_` 追加定义，`Build()` 时转移给 `PatternGraph`。注意：
- `Attr()` 和 `MaxUses()` 需要回溯查找已注册的同名 `NodeDef`，找不到时仅打 warning 不崩溃
- `Merge()` 是对 `Chain()` 的简单循环包装

**层 2：PatternGraph::MostConstrainedNode()**

> ⚠️ 这是影响匹配性能的关键 heuristic。

当前实现：统计每个节点在模式中参与了多少条边（作为 from 或 to），返回边数最多的节点。

以 SliceFuse 的 pattern 为例：
```
dmaIn → hSlice → wSlice
边数:  dmaIn=1, hSlice=2, wSlice=1
→ 种子 = "hSlice"（SliceKernel）
```

这个 heuristic 的**局限性**：只看 pattern 内的边数，完全忽略了实际图中各节点类型的实例数量。代码中也有注释承认了这一点：

```cpp
/* In a more sophisticated implementation, we'd count expected candidates */
/* via type index. */
```

**层 3：PatternMatcher::Match() + TryExpand()**

匹配流程：

```
Match(pattern)
  │
  ├─ 1. 选种子节点（MostConstrainedNode）
  │
  ├─ 2. 遍历全图，找出所有通过种子 NodeCheck 的节点 → candidates
  │
  └─ 3. 对每个 candidate，调用 TryExpand() 递归扩展
       │
       ├─ 检查 SingleUse / MaxUses 约束
       ├─ 遍历所有模式边，找"已知一端、未知另一端"的边
       │   ├─ from 已知 → 遍历 from 的所有 output，找匹配 to 定义的目标
       │   └─ to 已知   → 遍历 to 的所有 input，找匹配 from 定义的目标
       ├─ 递归 TryExpand 直到所有 label 都被填充
       └─ 所有 label 填充完毕后，验证所有边确实连通
```

关键实现细节：
- `used` 集合保证同一匹配中不会重复使用同一个节点
- 回溯时恢复 `used` 和 `current.nodes`
- 这是一个经典的回溯子图同构算法，复杂度在最坏情况下随模式大小指数增长，但对于小模式（3~5 个节点）且带 `SingleUse` 约束时，实际表现接近线性

### Step 3 — `tests/cpp/pattern_matcher_test.cpp`（~165 行）

测试用例覆盖了 PatternMatcher 的主要使用场景：

| 测试 | 覆盖点 |
|------|--------|
| `BuildAndInspect` | Builder 构建 + NodeDef/EdgeDef 数量 + MostConstrainedNode |
| `NodeCheckAndAttrFilter` | 类型检查 + Attr 过滤的正向/负向验证 |
| `SingleNodeMatch` | 单节点匹配（无边的退化情况） |
| `LongChainMatch` | 4 节点链，验证匹配结果中的 NodeIndex 正确性 |

> 注：文件中还有一个 `BatchRewriterTest`，属于 BatchRewriter 的独立测试，与 PatternMatcher 无关。

---

## 二、关键设计点

### 1. 声明式 DSL（PatternBuilder）

**设计意图**：将"找什么样的子图"从"怎么遍历图"中解耦。Pattern 定义是纯数据，不包含任何迭代逻辑。

**代价**：`Attr()` 和 `MaxUses()` 需要通过 label 字符串回溯查找已注册的 NodeDef，存在一定脆弱性（label 拼写错误只打 warning）。但这是在编译时无法做静态检查的动态 DSL 的固有 trade-off。

### 2. 种子选择 heuristic（MostConstrainedNode）

这是决定匹配性能的核心。当前按 pattern 内边数选择，忽略了实际图的类型分布。理想情况下应该传入各类型的实例计数，选候选最少的。

不过对于 3~5 个节点的小模式和常规规模的编译中间图，这个差距通常不显著。

### 3. 回溯搜索（TryExpand）

采用递归回溯而非固定顺序遍历，是为了处理 pattern 中边的任意拓扑结构：
- 线性链：A→B→C
- 汇聚：A→C, B→C
- 发散：A→B, A→C
- 混合：任意 DAG

递归回溯的通用性换来了对任意模式拓扑的支持，但在简单线性链上相比手写指针追踪有函数调用和 map 操作的开销。

### 4. 类型检查方式（dynamic_cast）

`NodeType<T>()` 用 `dynamic_cast<const T*>` 做类型检查。每次 `NodeCheck` 都会执行 dynamic_cast。对于频繁匹配的场景，可以考虑用 type index / enum 做快速预筛，仅对候选做 dynamic_cast。

---

## 三、实现思路总览

```
                    ┌──────────────────────────┐
                    │     PatternBuilder        │
                    │  .MatchNode("a", ...)     │
                    │  .Chain("a", "b")         │
                    │  .Attr("a", lambda)       │
                    │  .SingleUse("b")          │
                    │  .Build()                 │
                    └──────────┬───────────────┘
                               │ 产出
                    ┌──────────▼───────────────┐
                    │     PatternGraph          │
                    │  - nodeDefs_              │
                    │  - edgeDefs_              │
                    │  - MostConstrainedNode()  │
                    │  - NodeCheck()            │
                    └──────────┬───────────────┘
                               │ 输入
                    ┌──────────▼───────────────┐
                    │     PatternMatcher         │
                    │                            │
                    │  Match(pattern):           │
                    │    1. 选种子                │
                    │    2. 收集候选              │
                    │    3. TryExpand() 递归回溯  │
                    │    4. 返回 vector<MatchResult> │
                    └──────────┬───────────────┘
                               │ 产出 MatchResult
                               │ { "a": idx3, "b": idx7 }
                    ┌──────────▼───────────────┐
                    │     调用者（业务代码）       │
                    │                            │
                    │  for (match : results) {   │
                    │    // 对匹配到的节点做       │
                    │    // 任意自定义修改         │
                    │  }                         │
                    └────────────────────────────┘
```

核心思想：**分离"找什么"和"怎么找"**，让每个 pass 的作者只需声明匹配条件，不再手写图遍历和模式检查代码。

---

## 四、独立工具：BatchRewriter（`graph_rewriter.h`，~85 行）

> ⚠️ **BatchRewriter 不是 PatternMatcher 的一部分。** 它是一个独立的图操作工具，与 PatternMatcher 零耦合。这里单独说明是因为它经常与 PatternMatcher 在同一个变换 pass 中组合使用。

### 用途

只做一件事：**攒删除 → 批量执行 + 单次 Resolve**。

### 数据结构和接口

只有三个字段：
- `graph_` — 要操作的图的引用
- `pendingRemovals_` — `unordered_set<NodeIndex>`，攒待删除节点
- `committed_` — 防止重复提交

核心接口：
- `RemoveNode(idx)` — 将节点加入待删除集合（**不立即删除**）
- `Commit()` — 遍历 `pendingRemovals_` 逐个 `ReleaseNode`，然后调用一次 `graph_.Resolve()`
- `HasPending()` — 是否有待删除节点

### 为什么攒着删而不是立即删？

`graph_.Resolve()` 是重操作——拓扑排序、校验完整性、shape/type 推导等，O(N+E)。每删一个节点调一次 Resolve 是 O(n²)。攒着一起删只跑一次。

### 设计约束

- **不是事务**，没有回滚：节点的 `SetInputs/SetOutputs` 由调用者直接操作，BatchRewriter 只管理删除。如果 `Commit()` 失败（Resolve 报错），IO 修改不会回滚，图处于半改状态。
- **单次调用**：`Commit()` 只能调一次，第二次返回错误。

---

## 五、应用案例：SliceFuse 重构（`slice_fuse.cpp`）

> 这是理解"如何组合使用 PatternMatcher 和 BatchRewriter"的最佳入口。两者在这个文件中被组合使用，但它们本身是独立的。

### 组合方式

```
1. PatternMatcher::Match(sliceFusePattern) → 找到 DmaIn→HSlice→WSlice 子图
2. 对每个匹配结果:
     - 修改 HSlice 的属性（extra_off_en, extra_off）
     - SetOutputs 把 HSlice 的输出重新连接到 WSlice 的输出 tensor
     - rewriter.RemoveNode(wSlice->Index())  ← 标记 WSlice 为待删除
3. rewriter.Commit()  ← 批量删 WSlice + 单次 Resolve
```

### 新旧对比

```
旧：遍历拓扑序 → 找 DmaIn → 手写 children/grandchildren 检查 → 逐个 ReleaseNode → 多次 Resolve
新：声明 Pattern → PatternMatcher.Match() → 逐匹配改写 → BatchRewriter.Commit()（单次 Resolve）
```

重构后的结构更清晰：
- `CheckWsliceAlignment()` — 独立的对齐检查逻辑
- `RewriteSlicePair()` — 单个匹配的改写逻辑（修改 hSlice 属性和连接，wSlice 入队删除）
- `RunOnModule()` — 编排：定义 pattern → 匹配 → 循环处理 → 提交

### SliceFuse 案例中的匹配性能分析

以下分析仅针对 SliceFuse 这个具体场景中新旧实现的对比，不代表 PatternMatcher 在所有场景下的性能特征。

**可能变慢的原因：**

**种子节点选择不当** — `MostConstrainedNode()` 只看 pattern 中的边数：
```
dmaIn(1边) → hSlice(2边) → wSlice(1边)
种子 = hSlice（SliceKernel, mode==kHeight）
```
旧代码的"种子"相当于 DmaInKernel。在典型网络中 DmaInKernel 只有 1~10 个，SliceKernel 可能有数十到数百个。种子候选数量差距可达 1~2 个数量级。

**递归回溯开销** — 旧代码直接指针追踪，新代码有函数递归 + map 操作 + used 集合维护 + 回溯恢复。对于 3 节点线性链，这些开销虽然单次不大，但乘以更大的候选基数后可能累积。

**dynamic_cast 开销** — 旧代码直接对已知类型的 children 做 `CastNoCheck`，新代码用 `dynamic_cast` 且可能多次调用。

**可能变快的原因：**

**单次 Resolve()** — 旧代码每个 DmaIn 处理完后调一次 `Resolve()`，新代码只在最后调一次。如果图较大且 DmaIn 较多，这个节省可能超过匹配阶段的开销。

**SingleUse 约束的提前剪枝** — 虽然 TryExpand 有回溯开销，但 `SingleUse` 约束能快速排除大部分不成链的 SliceKernel 候选，避免无效的递归展开。

**总体评估：**

| 因素 | 倾向 |
|------|------|
| 种子候选基数变大 | ↓ 变慢 |
| 递归+map 替代指针追踪 | ↓ 变慢（微量） |
| dynamic_cast 替代 CastNoCheck | ↓ 变慢（微量） |
| Resolve 从 N 次变 1 次 | ↑ 变快 |
| SingleUse 提前剪枝 | ↑ 变快 |

- **小图**（几十个节点）：差异在微秒级，不显著
- **中等图**（几百个节点，数十个 SliceKernel）：匹配阶段可能慢 2~5 倍，但绝对值仍然很小（微秒到毫秒级）
- **大图**（数千个节点）：Resolve 节省的时间可能超过匹配多花的开销

当前实现的性能瓶颈在 `MostConstrainedNode` 的 naive heuristic。如果要优化，可以：

1. **让种子选择感知实例数**：`MostConstrainedNode` 接受一个 `type → count` 的映射，优先选图中实例最少的类型
2. **添加 type index 快速预筛**：用整数 type tag 取代 `dynamic_cast` 做初筛，对候选再做 `dynamic_cast` 确认
3. **pattern 编译**：将 `vector<NodeDef>` + `vector<EdgeDef>` 预编译为更紧凑的匹配指令序列，减少运行时遍历

这些优化可以在不改变 API 的情况下进行，说明当前设计的扩展性良好。

---

## 六、文件索引

### PatternMatcher 核心
| 文件 | 行数 | 说明 |
|------|------|------|
| `include/aic/transforms/pattern_matcher.h` | ~125 | PatternBuilder / PatternGraph / PatternMatcher 接口定义 |
| `src/transforms/pattern_matcher.cpp` | ~290 | PatternMatcher 实现（Builder + 回溯匹配引擎） |
| `tests/cpp/pattern_matcher_test.cpp` | ~165 | 单元测试（覆盖 Builder / NodeCheck / 单节点 / 链式匹配） |

### 独立工具
| 文件 | 行数 | 说明 |
|------|------|------|
| `include/aic/transforms/graph_rewriter.h` | ~85 | BatchRewriter — 批量节点删除工具，与 PatternMatcher 无耦合 |

### 应用案例
| 文件 | 行数 | 说明 |
|------|------|------|
| `target/tensor_brain/transforms/slice_fuse.cpp` | ~200 | SliceFuse pass，组合使用 PatternMatcher + BatchRewriter 的典型案例 |

### 文档
| 文件 | 行数 | 说明 |
|------|------|------|
| `docs/PATTERN_MATCHER.md` | ~138 | PatternMatcher 用法文档（API 参考 + 示例） |
| `docs/PATTERN_MATCHER_CODE_REVIEW.md` | 本文档 | 走读笔记 + 实现分析 + 性能评估 |
