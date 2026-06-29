# SliceFuse 重构要点分析

> 对比 `slice_fuse.cpp` 重构前后的所有变更，按维度分类分析。  
> 旧代码作者：Yiga Liu（2025-01-13），新代码作者：Alan Chen（2026-06-05 ~ 2026-06-17）

---

## 变更总览

| 维度 | 变更数 | 影响 |
|------|--------|------|
| 函数提取 | 2 个新 private 方法 | 可读性 + 可测试性 |
| Pattern 匹配 | 引入 PatternMatcher | 声明式匹配，替代手写遍历 |
| 批量改写 | 引入 BatchRewriter | N 次 Resolve → 1 次 Resolve |
| 头文件整理 | 删除 2 个、重排全部 | 编译依赖清洁 |
| 命名规范 | 全局驼峰化 | 风格统一 |
| 类结构 | 新增 private 区 | 封装性 |
| 防御性编程 | 2 处新增空指针检查 | 健壮性 |
| 控制流 | 消除 2 个中间向量 | 简化逻辑 |
| 注释文档 | 新增 Doxygen | 可维护性 |

下面逐一展开。

---

## 一、函数提取

重构最显著的结构性变化：将原本混在 80 行循环体内的两段逻辑提取为独立方法。

### 1.1 `CheckWsliceAlignment()` — 对齐检查

**旧代码位置**：`RunOnModule` 内 `/* 1.7 */` 注释段，嵌入在嵌套循环中。

**提取后**：

```cpp
bool SliceFuse::CheckWsliceAlignment(SliceKernel* hSlice, SliceKernel* wSlice,
                                     uint32_t* extraOff) const;
```

- 输入：hSlice + wSlice
- 输出：通过指针参数返回 `extraOff`，bool 返回值表示对齐是否通过
- 封装了 offsetTensor 创建、Init、GetPatchSize、32B 对齐校验的完整逻辑

### 1.2 `RewriteSlicePair()` — 改写逻辑

**旧代码位置**：`RunOnModule` 内 `/* 3.2 */` ~ `/* 3.5 */` 注释段。

**提取后**：

```cpp
void SliceFuse::RewriteSlicePair(SliceKernel* hSlice, SliceKernel* wSlice,
                                 uint32_t extraOff, BatchRewriter& rewriter) const;
```

- 封装了四步改写：更新 hSlice attr → 更新 kernel 连接 → 更新 hw layer 连接 → wSlice 入队删除
- 新增 `if (sliceLy)` 空指针保护（见第六节）

### 收益

- `RunOnModule` 从 ~80 行缩减到 ~40 行
- 对齐检查和改写逻辑可独立测试
- 职责清晰：RunOnModule 只做编排，不做细节

---

## 二、Pattern 匹配：命令式 → 声明式

### 旧代码：手动遍历 + 逐条件检查

```
for (拓扑序遍历) {
    if (不是 DmaInKernel) continue;        // 1. 类型筛选

    for (遍历 DmaIn 的 children) {
        if (input pattern != NHWC) continue;  // 1.1
        if (child 不是 SliceKernel) ...       // 1.2
        if (child mode != Height) continue;   // 1.3
        if (child output count > 1) continue; // 1.4
        if (grandchild 不是 SliceKernel) ...  // 1.5
        if (grandchild mode != Width) ...     // 1.6
        // 1.7 对齐检查 ...
    }

    if (!all_slice_flag) continue;  // 2.1
    // 3. 改写 ...
}
```

匹配条件和遍历逻辑**混杂**在一起，7 个检查步骤（1.1~1.7）嵌入在两层循环中。

### 新代码：声明 Pattern + 引擎匹配

```cpp
auto pattern = PatternBuilder("SliceFuse")
    .MatchNode("dmaIn", NodeType<DmaInKernel>())
    .MatchNode("hSlice", NodeType<SliceKernel>())
    .MatchNode("wSlice", NodeType<SliceKernel>())
    .Chain("dmaIn", "hSlice")
    .Chain("hSlice", "wSlice")
    .Attr("dmaIn", ...)    // NHWC 检查
    .Attr("hSlice", ...)   // mode==kHeight
    .Attr("wSlice", ...)   // mode==kWidth
    .SingleUse("hSlice")   // 只有一个消费者
    .Build();

auto matches = PatternMatcher(*kernelNet).Match(pattern);
```

### 对比

| 旧方式 | 新方式 |
|--------|--------|
| 检查逻辑散布在循环中 | 集中在 Builder 链式调用中 |
| "怎么找"和"找什么"混杂 | "找什么"通过 Pattern 声明，"怎么找"交给引擎 |
| 不可复用 | PatternMatcher 可被任意 pass 复用 |
| 1.1~1.7 的编号式注释 | 每个 Attr 的 lambda 自描述意图 |

---

## 三、批量改写：N 次 Resolve → 1 次

### 旧代码

```cpp
for (遍历 DmaIn) {
    for (遍历匹配到的 hSlice+wSlice 对) {
        kernel_net->ReleaseNode(next_slice->Index());   // 逐个删除
    }
    status = kernel_net->Resolve();   // 每个 DmaIn 都调用一次！
    if (status != Status::OK()) { ... }
}
```

**每个 DmaIn 节点处理完就调用一次 `Resolve()`**，如果有 5 个 DmaIn，就重建 5 次图拓扑。

### 新代码

```cpp
BatchRewriter rewriter(*kernelNet);

for (匹配结果) {
    rewriter.RemoveNode(wSlice->Index());  // 只入队，不执行
}

if (rewriter.HasPending()) {
    rewriter.Commit();  // 批量 ReleaseNode + 单次 Resolve()
}
```

**所有删除攒一起，最后调用一次 `Resolve()`**。对包含多个 DmaIn 的图，性能提升显著。

---

## 四、头文件整理

### 删除的无用 include

| 删除项 | 原因 |
|--------|------|
| `#include <regex>` | 从未使用 |
| `#include "aic/graph/graph_viewer.h"` | 旧代码用 `GraphViewer` 做拓扑序遍历，新代码不再需要 |

### include 排序

旧代码无明显排序规则。新代码按字母序排列：

```
旧（随机序）：
  "aic/pm/passes.h"              ← 混在中间
  "aic/base/pattern.h"
  ...
  "tensor_brain/hw_pass_context.h"  ← 和 tensor_brain/kernels 混排

新（按路径字母序）：
  "aic/base/*"
  "aic/cmdline/*"
  "aic/graph/*"
  "aic/ir/*"
  "aic/pm/*"
  "aic/transforms/*"            ← 新增
  "aic/utils/*"
  "tensor_brain/hw_layers/*"
  "tensor_brain/hw_pass_context.h"
  "tensor_brain/kernels/*"
```

新增两个 include：
- `"aic/transforms/graph_rewriter.h"` — BatchRewriter
- `"aic/transforms/pattern_matcher.h"` — PatternBuilder + PatternMatcher

---

## 五、命名规范化

全文件命名从旧风格统一为驼峰 + 引用/指针符号靠类型。

### 局部变量

| 旧名 | 新名 | 规范 |
|------|------|------|
| `kernel_net` | `kernelNet` | 驼峰 |
| `dma_in_kernel` | `dmaIn` | 驼峰 + 去掉冗余后缀 |
| `child_slice` | `hSlice` | 按角色命名而非按关系 |
| `grandchild_slice` | `wSlice` | 同上 |
| `all_slice_flag` | `allChildrenAreSlice` | 更具描述性 |
| `target_slices` | *消除* | 不再需要中间向量 |
| `target_extrainfo` | *消除* | 不再需要中间向量 |
| `extra_off` | `extraOff` | 驼峰 |
| `align_byte` | `alignByte` | 驼峰 |
| `next_slice_in_tensor` | `nextSliceInTensor` | 驼峰 |

### 类型声明中的指针/引用位置

| 旧写法 | 新写法 | 说明 |
|--------|--------|------|
| `Type *ptr` | `Type* ptr` | 星号靠类型 |
| `Type &ref` | `Type& ref` | 引用符靠类型 |
| `Module &mod` | `Module& mod` | 同上 |

### 函数参数中的空格

| 旧 | 新 |
|----|----|
| `HwGraph &hw_graph` | `HwGraph& hwGraph` |
| `SliceLayer *slice_ly` | `SliceLayer* sliceLy` |
| `Module &mod` | `Module& mod` |

---

## 六、防御性编程改进

### 6.1 Match 结果空指针检查

```cpp
auto* dmaIn = CastNoCheck<DmaInKernel>(kernelNet->GetNode(match.nodes.at("dmaIn")));
auto* hSlice = CastNoCheck<SliceKernel>(kernelNet->GetNode(match.nodes.at("hSlice")));
auto* wSlice = CastNoCheck<SliceKernel>(kernelNet->GetNode(match.nodes.at("wSlice")));

if (!dmaIn || !hSlice || !wSlice) continue;   // ← 新增
```

旧代码中 `dma_in_kernel` 在循环开头就做了 null check + continue，但对 child/grandchild 的 null check 后在 `target_slices` 中已经通过 push_back 间接保证了非空。新代码通过 `GetNode` + `CastNoCheck` 取值后再统一校验。

### 6.2 HwLayer 空指针保护

```cpp
// 旧代码（直接调用，slice_ly 可能为 nullptr 时崩溃）
SliceLayer *slice_ly = dynamic_cast<SliceLayer *>(hw_graph.GetHwLayer(0));
slice_ly->SetOutputs({next_slice_out_tensor});   // ← 未检查
slice_ly->SetExtraInfo(true, extra_off);          // ← 未检查

// 新代码
SliceLayer* sliceLy = dynamic_cast<SliceLayer*>(hwGraph.GetHwLayer(0));
if (sliceLy) {                                     // ← 新增保护
    sliceLy->SetOutputs({nextSliceOutTensor});
    sliceLy->SetExtraInfo(true, extraOff);
}
```

这是一个潜在的 bug 修复：如果 `GetHwLayer(0)` 不是 `SliceLayer` 类型，旧代码直接空指针解引用崩溃。

---

## 七、控制流简化

### 消除中间容器

旧代码用两个 `std::vector` 缓存匹配结果，分两阶段处理：

```cpp
// 阶段1：收集
std::vector<SliceKernel*> target_slices = {};
std::vector<uint32_t> target_extrainfo = {};
for (遍历 children) {
    // ... 检查 ...
    target_extrainfo.push_back(extra_off);
    target_slices.push_back(child_slice);
}

// 阶段2：改写
for (size_t i = 0; i < target_slices.size(); ++i) {
    auto* slice = target_slices[i];
    uint32_t extra_off = target_extrainfo[i];
    // 改写 ...
}
```

新代码一次循环直接处理：

```cpp
for (const auto& match : matches) {
    // 检查 + 改写，无中间向量
    RewriteSlicePair(hSlice, wSlice, extraOff, rewriter);
}
```

**消除原因**：旧代码需要两阶段是因为要在 children 循环内完成所有检查，然后把合格的收集起来再统一改写。新代码的 PatternMatcher 已预先完成了匹配筛选，业务循环只需处理已确认的匹配对。

### 消除 GraphViewer

```cpp
// 旧
auto graph_viewer = GraphViewer(*kernel_net);
for (auto index : graph_viewer.GetNodesInTopologicalOrder()) {
    ...
}

// 新 — 不需要了，PatternMatcher 内部自己遍历
```

### 消除状态变量

```cpp
// 旧
auto status = Status::OK();        // 函数开头声明
...
status = kernel_net->Resolve();    // 中间赋值
...
return status;                     // 函数结尾返回

// 新
return Status::OK();               // 正常路径直接返回
auto status = rewriter.Commit();   // 需要时局部声明
return status;
```

---

## 八、注释与文档

### 新增文件级 Doxygen

```cpp
/**
 * @brief
 * @date    2025-01-13
 *
 * SliceFuse Pass: Fuses DmaIn → Slice(H) → Slice(W) pattern.
 *
 * Pattern:
 *   DmaIn (NHWC input)
 *     └── SliceKernel (Mode::kHeight) — single output
 *           └── SliceKernel (Mode::kWidth, 32B-aligned start)
 *
 * Rewrite:
 *   - Update HSlice attr with extra_off info from WSlice
 *   - HSlice outputs directly to WSlice's output tensor
 *   - Release WSlice node
 *   - Single Resolve at the end
 */
```

用 ASCII 图清晰描述了 pattern 拓扑和改写步骤，新人无需读代码就能理解这个 pass 做什么。

### Change Log 补充

```cpp
// 旧
* 2025-01-13     Yiga Liu  Initialize.

// 新
* 2025-01-13     Yiga Liu       Initialize.
* 2026-06-05     Alan Chen      Refactored to use PatternMatcher + GraphRewriter.
* 2026-06-17     Alan Chen      Updated to use BatchRewriter (renamed from GraphRewriteTransaction).
```

### 注释风格变化

```cpp
// 旧：编号式，需要对应到代码位置才能理解
/* 0 find each copyin */
/* 1.1 input must be nhwc */
/* 1.2 child must be slice */
/* 3.4 update hslice hwly attr */

// 新：描述式，直接说明意图
/* Build the DmaIn → Slice(H) → Slice(W) pattern */
/* Update HSlice attr */
/* Update HSlice kernel connection */
/* Queue WSlice for removal */
```

---

## 九、类结构

```cpp
// 旧
class SliceFuse : public ModulePass {
 public:
  void Show() const override { ... }
  common::Status RunOnModule(Module &mod) override;   // 无 private 区
};

// 新
class SliceFuse : public ModulePass {
 public:
  void Show() const override { ... }
  common::Status RunOnModule(Module& mod) override;

 private:                                              // ← 新增封装
  bool CheckWsliceAlignment(...) const;
  void RewriteSlicePair(...) const;
};
```

两个辅助方法声明为 `private const`，明确了"这些是实现细节，不对外暴露"。

---

## 十、总结：重构层次

```
┌────────────────────────────────────────────────┐
│  架构层：引入 PatternMatcher + BatchRewriter     │  ← 最大变化
│         声明式匹配 + 批量改写                     │
├────────────────────────────────────────────────┤
│  结构层：函数提取（2 个 private 方法）            │  ← 可读性
│         消除中间容器（2 个 vector）               │
│         消除中间变量（graph_viewer）              │
├────────────────────────────────────────────────┤
│  风格层：驼峰命名                                │  ← 一致性
│         指针/引用靠类型                           │
│         include 字母序                           │
├────────────────────────────────────────────────┤
│  质量层：新增空指针检查（hSlice/wSlice/sliceLy）  │  ← 健壮性
│         新增 BatchRewriter commit 状态检查       │
├────────────────────────────────────────────────┤
│  文档层：文件级 Doxygen + 函数级注释              │  ← 可维护性
│         Change log 记录                          │
└────────────────────────────────────────────────┘
```

**一句话**：这不是简单的"换个 API"，而是一次从遍历方式、函数划分、命名风格、错误处理到文档的**全方位规范化重构**。PatternMatcher 的引入是其中最显著的变化，但函数提取和防御性改进同样重要。
