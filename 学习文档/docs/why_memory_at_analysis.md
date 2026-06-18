# 为什么内存管理与分配放在 Analysis Graph 阶段？

> 在 `main.cpp` 的 `RegisterPasses()` 中，MemAlloc / HwLayerInplace / LiveTimeAnalyse / HwLayerMemAlloc 全部在 BuildAnalyseGraph 之后执行。为什么不早点分配？

---

## 1. 内存相关 Pass 在流水线中的位置

```
BuildAnalyseGraph          ← 生成全局执行顺序图
    │
    ▼
... (InsertSync, Cascade, InvalidCascadeEliminate) ...
    │
    ▼
MemAlloc                   ← 操作 KernelNet，但依赖 Cascade 结果
    │
    ▼
HwLayerInplace             ← 操作 AnalyseGraph，标记 In-place 复用
    │
    ▼
LiveTimeAnalyse            ← 操作 AnalyseGraph，分析生命周期
    │
    ▼
HwLayerMemAlloc            ← 操作 AnalyseGraph，精确分配地址
    │
    ▼
BuildMemNodeLinks          ← 建立内存节点链接
```

注意：**MemAlloc 实际遍历的是 `KernelNet`**，但它在 `main.cpp` 中的注释写的是 `/* depend on Cascade */`。它被放在 AnalyseGraph 阶段，是因为它依赖的 Cascade 只能在这之后运行。

---

## 2. 为什么不能提前？四个核心原因

### 原因一：Cascade 决定了 tensor 的物理位置，必须在分配前完成

```
Cascade 之前： 每个 Kernel 的输出都在 DDR
Cascade 之后： 连续 Cascade 组内的中间结果留在 L1，不写回 DDR
```

`MemAlloc::RunOnModule` 虽然是遍历 `KernelNet`，但每个 `Kernel::AllocateMem()` 内部会根据 Cascade 状态走不同分支：

```cpp
// target/tensor_brain/transforms/mem_allocator_pass.cpp:107-115
for (auto idx : topological_order) {
    Kernel *kernel = net->GetKernel(idx);
    status = kernel->AllocateMem();  // ← 内部检查 cascade 状态
}
```

Kernel 内部的实际逻辑（简化）：

```
Kernel::AllocateMem():
    if (IsStrCascaded()):
        // Cascade 模式：输出留在 L1，只分配 L1 空间
        LocalMallocForOutCascade()
    else:
        // 普通模式：输出必须在 DDR 分配空间
        LocalMallocForOutNonCascade()
```

如果不先跑 Cascade，所有 tensor 都会按非 Cascade 模式分配，浪费大量 DDR 空间和带宽。

**Cascade 又必须在 AnalyseGraph 上运行**，因为 Cascade 需要知道全局执行顺序才能判断哪些连续 HwLayer 可以级联。

### 原因二：内存分配需要全局执行顺序，不是拓扑序

```
拓扑序（KernelNet / Net 提供）:
    可能有多条合法排序，不确定实际执行顺序

执行序（AnalyseGraph 提供）:
    order_to_node: {0→DMA_In_A, 1→Conv_Layer, 2→DMA_Out_A, 3→DMA_In_B, ...}
    确定的硬件执行顺序，不可改变
```

`HwLayerMemAlloc` 和 `LiveTimeAnalyse` 都依赖 `AnalyseGraph::GetOrderToNodeMap()`：

```cpp
// livetime_analyse.cpp 核心逻辑
Status LiveTimeAnalyse::CalculateTensorMemLifeTime(AnalyseNode *node) {
    // 遍历 order_to_node，按执行顺序标记每个 tensor 的
    // 产生时刻（birth）和最后使用时刻（death）
    // 两个 tensor 生命周期不重叠 → 可以复用同一块内存
}
```

如果只有拓扑序，你无法精确知道 tensor A 和 tensor B 会不会同时存活。只有确定的执行顺序才能做精确的生命周期分析。

### 原因三：分配粒度是 HwLayer，不是 Kernel 或 Operator

| 层级 | 分配粒度 | 问题 |
|------|---------|------|
| Operator 层 | Conv2d, Relu... | 粒度太粗。一个 Conv2d 最终展开为 4-5 个 HwLayer，每个都需要独立的 buffer |
| Kernel 层 | Conv2dKernel... | 能在 Kernel 内部分配（MemAlloc），但 Kernel 之间的跨 Kernel buffer 还需要全局视角 |
| **Analyse 层** | **DMA_In_Layer, Conv_Layer...** | **正确粒度。每个 HwLayer 有独立的输入/输出 buffer 需求** |

一个 `Conv2dKernel` 的 HwGraph 展开后可能是：
```
DMA_In (buffer: 输入特征图) → Pad_Layer (buffer: padding 后的图) →
Conv_Layer (buffer: 卷积中间结果) → Act_Layer (buffer: 激活后输出) → DMA_Out
```

每个箭头处都需要临时 buffer。**HwGraph 在 Kernel 内部**，但跨 Kernel 的 buffer 复用（如 Kernel A 的 DMA_Out buffer 可以被 Kernel B 的 DMA_In 复用）需要全局视角——这正是 AnalyseGraph 提供的。

### 原因四：In-place 优化需要全局消费者信息

```cpp
// hwlayer_inplace_opt.cpp 核心逻辑
// 判断 HwLayer A 的输出能否覆盖 HwLayer B 的输入：
//   条件1：B 的输入在所有消费者中只有 A 这一个 producer
//   条件2：B 的输入在所有后继节点中不再被使用
//   条件3：A 的输出和 B 的输入 shape/stride 兼容
//
// 所有这些条件都需要遍历 AnalyseGraph 的全局边关系
```

在 KernelNet 里，你只能看到 "ConvKernel 输出 → EltwiseKernel 输入"。但实际执行时中间可能插入了 DMA_In、DummySlice、DummyConcat 等 HwLayer，In-place 判断必须在最细粒度的 HwLayer 级别做。

---

## 3. 两层内存分配的职责划分

| | MemAlloc | HwLayerMemAlloc |
|---|---|---|
| **操作的图** | `KernelNet` | `AnalyseGraph` |
| **粒度** | Kernel 级 | HwLayer 级 |
| **分配什么** | Kernel 的输出 tensor、extra space | 每个 HwLayer 的临时 buffer、中间结果 |
| **分配策略** | `Kernel::AllocateMem()` 每类 Kernel 自己实现 | 全局分配器（如 `ParallelBaseHwLayerType`），基于生命周期复用 |
| **位置** | Cascade 之后立刻执行 | LiveTimeAnalyse（生命周期分析）之后 |

简单来说：
- **MemAlloc** = 粗分配。给每个 Kernel 的输出 tensor 一个地址。
- **HwLayerMemAlloc** = 细分配。在全局视角下给每个 HwLayer 的临时 buffer 精确分配，复用不重叠的生命周期。

---

## 4. 如果强行提前分配会发生什么？

一个思想实验：

```
假设在 Lowering 之后立刻分配内存：

1. 不知道 Cascade 状态 → 所有 tensor 都分配在 DDR → 浪费带宽
2. 只有 KernelNet 拓扑序 → 生命周期分析不准确 → 保守分配 → 浪费 L1 空间
3. 没有 HwLayer 展开 → 不知道每个 Kernel 内部需要多少临时 buffer → 只能估算
4. 没有 In-place 分析 → 无法复用 → 内存峰值可能是优化后的 2-3 倍
```

---

## 5. 总结

```
"为什么内存分配要放在 Analysis Graph 阶段？"

因为分配内存需要知道三件事：

1. 这个 tensor 放在 L1 还是 DDR？     ← Cascade 决定
2. 这个 tensor 什么时候生、什么时候死？  ← 执行顺序决定（AnalyseGraph 有）
3. 这个 tensor 旁边还有谁？能复用吗？    ← HwLayer 粒度 + 全局消费者信息决定

这三件事在 Operator/Kernel 层都不知道。
只有到了 AnalyseGraph，硬件执行顺序、Cascade 状态、
HwLayer 展开、全局消费关系全部就绪，才能做正确的内存分配。
```
