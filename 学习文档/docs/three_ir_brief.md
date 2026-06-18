# AIC 三层 IR 简介

---

#### 总览

```
L1: Operator Graph     →  "算什么"（硬件无关）
L2: Kernel Graph       →  "用什么硬件方式算"（硬件感知）
L3: Analysis Graph     →  "硬件按什么顺序执行"（硬件指令级）
```

---

#### L1 — Operator Graph

**图类型**: `Net`（继承自 `Graph`）

**节点**: `Operator`（继承自 `Node`）
- Conv2d, Softmax, Matmul, Eltwise, LayerNorm, Sin, Exp... 共 40+ 种算子
- 每个 Operator 包含一个 `Attr` 结构体（超参数）+ `Value<ValueT>`（权重/bias/LUT）
- 核心接口：`OutputInfer()` — 根据输入 shape 推导输出 shape

**数据**: `Tensor`（继承自 `NodeArg`）
- 4 维：NCHW
- 属性：dtype (Fp16/Int8...)、pattern (NpuFmt/NchwFmt...)、acc（定点位置）
- 此时**地址为空**（`addr_ = INVALIDADDR`），不知道将来放在 L1 还是 DDR

**特点**: 完全硬件无关。类似 ONNX Graph，只描述计算语义，不涉及任何硬件概念。

---

#### L2 — Kernel Graph

**图类型**: `KernelNet`（继承自 `Graph`）

**节点**: `Kernel`（继承自 `Node`）
- Conv2dKernel, EltwiseKernel, ConcatKernel, DMADataCopyKernel...
- 每个 Kernel 内含一个 `HwGraph`（硬件子图），由 `BuildHwGraph` 填充
- 核心接口：`BuildHwGraphImpl()` — 根据算子参数构建内部的 HwLayer 序列

**数据**: 还是 `Tensor`（同一对象，地址仍然为空）

**子结构 — HwGraph / HwLayer**:
- `HwGraph`（继承自 `Graph`）是 Kernel 内部的微型图，典型包含：
  ```
  DMA_In → Compute_Layer → DMA_Out
  ```
- `HwLayer`（继承自 `Node`）是硬件层的基类，子类包括：
  - `Conv2dLayer`（MPU 计算）、`EltwiseLayer`（VPU 计算）
  - `NPU_DMA_In` / `NPU_DMA_Out`（DMA 搬运）
  - `DummyConcatLayer` / `DummySliceLayer`（仅改元数据，零硬件开销）
  - 核心接口：`Codegen()` — 生成机器指令

**特点**: 开始感知硬件。知道 L1 容量、MPU 数量、支持的融合模式。但各 Kernel 的 HwGraph **彼此独立**，不知道全局执行顺序。

---

#### L3 — Analysis Graph

**图类型**: `AnalyseGraph`（继承自 `Graph`）

**核心新增**（区别于普通 Graph）:
```cpp
map<uint32_t, AnalyseNode*> order_to_node_;   // 执行序号 → 节点
map<AnalyseNode*, uint32_t> node_to_order_;   // 节点 → 执行序号（反向）
```
这是**确定的硬件指令发射顺序**，不是拓扑序（拓扑序有多种合法排序，执行序只有一种）。

**节点**: `AnalyseNode`（继承自 `Node`）
- 内部持有 `HwLayer* hw_layer_`——**不拷贝** HwLayer，直接指向 Kernel 内同一对象
- 附加 `MemAllocateFlag`（内存分配标记：是否 In-place、是否 Cascade 等）
- 所有硬件查询（IsDummy、IsCascaded、GetHwLayerType...）委托给 HwLayer

**构建方式**: `BuildAnalyseGraph` 遍历 KernelNet 拓扑序，把每个 Kernel 的 HwGraph 展开为 HwLayer 序列，按规则（DMA_In 插消费者前、DMA_Out 插生产者后）拼成全局执行序，并建立 HwLayer 间的跨 Kernel 边。

**特点**: 完全硬件感知。知道每条指令的执行顺序、每个 tensor 的去向、每个 HwLayer 的硬件单元类型。**内存分配、同步插入、Cascade 优化、代码生成全部基于这一层。**

---

#### 三层对比

| | L1 Operator Graph | L2 Kernel Graph | L3 Analysis Graph |
|---|---|---|---|
| **图** | `Net` | `KernelNet` | `AnalyseGraph` |
| **节点** | `Operator` | `Kernel` (内含 `HwGraph`) | `AnalyseNode` (包装 `HwLayer*`) |
| **数据** | `Tensor` (无地址) | `Tensor` (无地址) | `Tensor` (有地址，已分配) |
| **粒度** | 算子 | Kernel (3-5 个 HwLayer) | HwLayer (单条硬件操作) |
| **顺序** | 拓扑序 | 拓扑序 | **硬件执行序** |
| **感知硬件** | 否 | L1 大小、MPU 数量 | 全部：地址、同步、流水线 |
| **节点数量** | 几十到几百 | 几十到几百 | 几百到上千 |
