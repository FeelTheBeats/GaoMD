# AnalyseGraph 分层走读指南

> 从 KernelNet（L2）到指令输出（Codegen），分 5 层走读完 AnalyseGraph（L3）。

---

## 零、速览：AnalyseGraph 在你已有文档中的位置

你已经写了三份参考：
- `docs/Multi Level IR/analyse_graph_deep_dive.md` — 数据结构详解（order_to_node、AnalyseNode、HwLayer）
- `docs/codegen/codegen_vs_llvm.md` — 与 LLVM CodeGen 的对比
- `docs/General Document/why_memory_at_analysis.md` — 为什么内存分配在 L3 做

这份指南不讲细节，只讲**走读顺序**——哪层读什么、前后怎么衔接、和 LLVM 怎么类比。

---

## 第一层：L2→L3 的桥梁 — BuildAnalyseGraph

**文件**：`build_analyse_graph_pass.cpp`

**做什么**：遍历 KernelNet 的拓扑序，把每个 Kernel 内部的 HwGraph 展开，所有 HwLayer 逐个包装为 AnalyseNode，拼成一张全局图，并建立跨 Kernel 的 HwLayer 间边。

**走读重点**：
- `AddAnalyseNode(name)` — 每个 HwLayer 分配一个 AnalyseNode + 执行序号
- `node.SetHwLayer(hw_layer)` — 1:1 绑定，不拷贝
- DMA_In / DMA_Out 的插入规则（DMA_In 在消费者前、DMA_Out 在生产后）

**LLVM 类比**：这是 **ISel（指令选择）→ MachineFunction 构建** 的对应步骤。Kernel 是"上层算子"，HwLayer 是"机器指令"。BuildAnalyseGraph 把 `Conv2dKernel → {DMA_In, Conv2d_Layer, DMA_Out}` 展开成具体的硬件操作序列。

---

## 第二层：执行序上的优化 — Cascade 系列

**文件**：
- `cascade_pass.cpp` — 级联优化，核心
- `invalid_cascade_eliminate.cpp` — 消除非法级联
- `mid_result_transfer.cpp` — 级联中间结果传输
- `merge_rdma_for_cascade.cpp` — 合并级联 DMA

**做什么**：把相邻的 HwLayer 组织为 Cascade——中间 tensor 不写回 DDR，直接在 L1 内传递。对带宽敏感模型是 2~3x 的性能提升。

**走读重点**：
- 只读 `cascade_pass.cpp` 即可，理解"什么条件下两个 HwLayer 可以级联"的判定逻辑
- L1 buffer 容量计算、split_dim 怎么决定分块策略
- Cascade 的两种模式：IFM cascade（输入特征图驻留）和 WGT cascade（权重驻留）

**LLVM 类比**：相当于 **MachineScheduler + 寄存器分配的一部分决策**——哪些中间值留在 L1（寄存器），哪些 spill 到 DDR（栈）。

---

## 第三层：内存与生命周期 — MemAlloc 系列

**文件**：
- `mem_allocator_pass.cpp` — 全局内存分配
- `hwlayer_mem_allocator.cpp` — HwLayer 内部 buffer 分配
- `hwlayer_inplace_opt.cpp` — In-place 优化
- `livetime_analyse.cpp` — tensor 生命周期分析

**做什么**：Cascade 决定了哪些 tensor 留 L1、哪些走 DDR。MemAlloc 在此基础上为每个 tensor 分配具体地址，liveness 分析找出生死区间，in-place 复用不再使用的 tensor 内存。

**走读重点**：
- 按依赖顺序读：`Cascade → MemAlloc → HwLayerInplace → LiveTimeAnalyse → HwLayerMemAlloc`
- tensor 的"生"和"死"由 `order_to_node` 的执行序号精确定义
- 内存复用的核心：两个 tensor 的生命周期不重叠 → 可以放在同一块 L1 区域

**LLVM 类比**：就是 **寄存器分配 + liveness 分析**。区别只在于 LLVM 的"寄存器"是 32 个物理寄存器，AIC 的"寄存器"是一块 L1 buffer 区域。Spill = 写回 DDR。

---

## 第四层：同步与时序 — Sync 系列

**文件**：
- `insert_sync_pass.cpp` — 插入同步屏障
- `sync_analyse.cpp` — 同步分析
- `insert_idle_pass.cpp` — 插入 Idle 等待
- `insert_dummy_dma.cpp` — 插入虚拟 DMA 占位

**做什么**：确保 VLIW 流水线中的数据依赖正确。在需要同步的 HwLayer 之间插入 Sync 指令，在不满足时序约束的位置插入 Idle。

**走读重点**：
- `insert_sync_pass.cpp` 运行两次（Cascade 前一次、Cascade 后一次，因级联改变了数据路径）
- Sync 的粒度是 HwLayerType（MPU/VPU/DMA/MTE 等硬件单元）
- Idle 的插入逻辑：计算两条指令之间的最小等待周期

**LLVM 类比**：这部分 LLVM 没有直接对应——LLVM 的 VLIW 目标（如 Hexagon）有类似的 **packetization + hazard detection**，但 AIC 因为固定功能单元组合简化了这个问题。

---

## 第五层：指令发射 — Codegen

**文件**：
- `codegen_pass.cpp` — Codegen pass 主逻辑
- `hw_layer.cpp` — HwLayer 基类方法
- `hw_layers/{mpu,vpu,dma,mte,spu}/` — 各 PE 的 Codegen 实现

**做什么**：遍历 `order_to_node`，跳过 Dummy 节点，每个 HwLayer 调 `Codegen()` 生成 `uint64_t` 指令序列，分组打包，写文件。

**走读重点**：
- Codegen 是**纯发射器**——不做优化，只做"把 HwLayer 翻译成指令 → 写进 buffer"
- 分组逻辑：连续 + 同类 HW + 无 sync → 一个 Group，一起发
- `HwLayer::Codegen()` 是纯虚函数，每个 PE 自己实现（Conv2dLayer 生成 Conv 指令，EltwiseLayer 生成 VPU 指令）

**LLVM 类比**：相当于 **MC 层的 `MCCodeEmitter` + `AsmPrinter`**。LLVM 的 CodeGen 是一个大阶段（ISel→Sched→RegAlloc→Emit），AIC 的 Codegen 只是最后一步"发射指令"。**AIC 的"真 Codegen"比 LLVM 简单得多，因为优化都在前面做完了。**

---

## 与 LLVM 的整体对比

```
LLVM                              AIC
────                              ───
SelectionDAG / GlobalISel  ────→  BuildAnalyseGraph（Kernel→HwLayer）
MachineScheduler           ────→  Cascade（L1驻留 vs DDR spill）
Register Allocation        ────→  MemAlloc + LiveTimeAnalyse
Hazard Detection           ────→  InsertSync + InsertIdle
MCCodeEmitter + AsmPrinter ────→  Codegen（纯发射）
```

---

## 建议走读顺序

```
Day 1:
  先不要看代码。重读你自己写的 analyse_graph_deep_dive.md。
  搞清三个问题：
    1. AnalyseNode 和 HwLayer 是什么关系？（1:1 绑定，前者是壳）
    2. order_to_node 和拓扑序的区别？（执行序只有一种，拓扑序有多种）
    3. AnalyseGraph 怎么从 KernelNet 构建出来的？

Day 2:
  BuildAnalyseGraph（第一层）→ 只看 insert 规则和 DMA placement
  Cascade（第二层）→ 只读懂"什么条件下可以级联"

Day 3:
  MemAlloc + LiveTimeAnalyse（第三层）→ 重点看一个 tensor 的生→死区间怎么算
  InsertSync + SyncAnalyse（第四层）→ 看同步怎么插在 PE 之间

Day 4:
  Codegen（第五层）→ 挑一个 HwLayer（如 Conv2dLayer）的 Codegen()，看它怎么生成指令
```

**每层都问自己**："这一层相当于 LLVM 的哪一步？做了 LLVM 的什么，没做什么？"
