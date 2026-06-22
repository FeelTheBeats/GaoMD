# AIC 三层 IR 与 Codegen 概要

---

## 1. 三层 IR 的作用与关系

```
Operator Graph (Net)
    │  算子级：Conv2d, Softmax, Matmul...
    │  硬件无关，只描述"算什么"
    │
    ▼  Lowering
Kernel Graph (KernelNet)
    │  Kernel 级：Conv2dKernel, EltwiseKernel...
    │  每个 Kernel 内含 HwGraph（HwLayer 序列）
    │  硬件感知，知道"用什么硬件算"，但不知道全局执行顺序
    │
    ▼  BuildAnalyseGraph（展开各 HwGraph，拼接为全局图）
Analysis Graph (AnalyseGraph)
    │  HwLayer 级：DMA_In → Conv → DMA_Out → DMA_In → Eltwise → ...
    │  全局硬件执行序（order_to_node），地址已分配
    │  知道"每条指令什么时候执行、数据放在哪里"
    │
    ▼  Codegen
uint64_t 指令流
```

| | Operator | Kernel | Analysis |
|---|---|---|---|
| 节点 | Operator | Kernel (内含 HwGraph) | AnalyseNode (指向 HwLayer) |
| 数据 | Tensor (无地址) | Tensor (无地址) | Tensor (已分配地址) |
| 顺序 | 拓扑序 | 拓扑序 | 硬件执行序 |
| 做什么 | 拆算子 | 融合/消冗/建 HwLayer | 分配/调度/同步 |

---

## 2. 与 LLVM 编译管线逐阶段对照

### 2.1 全局对照图

```
LLVM:
  C/C++ → ┌─── Clang ────┐ → ┌── Opt ────┐ → ┌─── CodeGen ───────────────────┐ → .o
          │ IRGen         │   │ instcombine│   │ ISel → Schedule → RegAlloc    │
          │ → LLVM IR     │   │ GVN/DCE    │   │ Liveness → Spill → Prolog     │
          └───────────────┘   └────────────┘   │ Peephole → MCStreamer         │
                                                └──────────────────────────────┘

AIC:
  JSON → ┌─ Parser ───┐ → ┌─ Op Graph ────┐ → ┌─ Kernel Graph ──┐ → ┌─ Analyse Graph ───────────┐ → .o
         │ LayerParser │   │ Split/Tiling  │   │ FusedOp         │   │ Cascade → MemAlloc        │
         │ → Operator  │   │ → 拆复杂算子   │   │ BuildHwGraph    │   │ LiveTime → InsertSync     │
         └─────────────┘   └───────────────┘   │ → 建 HwLayer     │   │ Codegen（发射）            │
                                                └─────────────────┘   └───────────────────────────┘
```

### 2.2 逐阶段对照表

| | AIC 阶段 | LLVM 对应 | 说明 |
|---|---|---|---|
| 输入 | JSON 模型文件 | C/C++ 源码 | 外部输入格式 |
| 解析 | `SvJsonParser` → `Net` | `Clang Frontend` → `llvm::Module` | 生成第一层 IR |
| L1 IR | **Operator Graph** | **LLVM IR**（优化前的原始 IR） | 硬件无关的语义表达 |
| 算子拆分 | `SoftmaxSplit` `NormSplit` `MatmulSplit`... | `LegalizeTypes` `Scalarize` | 把目标不支持的语义拆为基本操作 |
| Lowering | **Lowering**（Op → Kernel） | **Instruction Selection**（ISel） | IR 节点 → 目标可执行单元。区别：AIC 粒度是 Kernel（含多 HwLayer），LLVM 粒度是单条 MachineInstr |
| L2 IR | **Kernel Graph**（含 HwGraph） | **SelectionDAG** / **MI 前状态** | 已绑定目标硬件操作，但无执行序和地址 |
| 算子融合 | `FusedOp` | `instcombine` `MachineCombiner` | 相邻操作合并，减少中间结果 |
| 消冗 | `KernelConcatEliminate` `DeleteConcatBeforeConv` | `DCE` `GVN` `CSE` | 消除不必要的计算 |
| HwLayer 生成 | `BuildHwGraph` | ISel 的 Pattern Match | 语义操作展开为硬件操作序列 |
| L3 IR | **Analysis Graph** | **MachineFunction + MBB** | 硬件操作有序序列，地址/资源待分配 |
| 执行序 | `BuildAnalyseGraph` → `order_to_node` | **Instruction Scheduling**（Pre-RA） | 确定指令发射顺序。区别：AIC 顺序执行不可重排，LLVM 可重排 |
| 寄存器分配 | `MemAlloc` `HwLayerMemAlloc` | **Register Allocation** | 值 → 物理存储单元。AIC：tensor → L1 addr；LLVM：vreg → preg |
| Liveness | `LiveTimeAnalyse` | `LiveVariables` `LiveIntervals` | 分析值的生命区间 |
| In-place 复用 | `HwLayerInplace` | **Register Coalescing** | 生命周期不重叠的值复用同一物理位置 |
| Spill 决策 | `Cascade`（L1 驻留 vs DDR） | **Spill / Reload Insertion** | 决定值留在快存储还是写回慢存储 |
| 同步/屏障 | `InsertSync` `SyncAnalyse` | **无直接对应**（硬件差异） | AIC 显式同步信号；LLVM 面向乱序 CPU，硬件处理依赖 |
| 空闲等待 | `InsertIdle` | **无直接对应** | AIC 硬件有时序约束需精确等待；CPU 不需要 |
| 指令发射 | **Codegen** | **MC Emit** | 结构化指令 → 二进制编码。AIC：`uint64_t`；LLVM：`MCStreamer` |
| 文件输出 | `GenFiles` | `AsmPrinter` + `ObjectWriter` | 写出 .o / .asm |
| 后分析 | `Analyze` | `llvm-mc -stats` | 统计资源用量 |

### 2.3 关键差异点

| 维度 | LLVM | AIC |
|---|---|---|
| **核心难点在哪** | RegAlloc + Scheduling | Cascade + MemAlloc |
| **寄存器模型** | 虚拟寄存器 → 物理寄存器 | 无寄存器，用 L1 物理地址 |
| **指令调度** | 可乱序重排，填充流水线 | 顺序执行，`order_to_node` 不可改 |
| **同步** | 无（CPU 硬件处理数据依赖） | 显式 SYNC_SET/CLR 指令 |
| **Dummy/虚拟操作** | 无对应概念 | Concat/Slice 可退化为纯地址代数 |
| **Codegen 复杂度** | 多阶段迭代，最复杂的部分 | 单 Pass 发射，相对简单 |
| **优化集中在哪里** | 分散在 ISel、Schedule、RegAlloc 各阶段 | 集中在 Analyse 层（Codegen 之前全部做完） |

---

## 3. AnalyseGraph 为 Codegen 做的铺垫

Codegen 不做任何决策，只负责发射。所有决策在 AnalyseGraph 阶段已完成：

| Codegen 需要什么 | 由哪个 Pass 提供 |
|---|---|
| 每个 HwLayer 的类型 | `BuildHwGraph`（Kernel 层） |
| 全局执行顺序 | `BuildAnalyseGraph` → `order_to_node_` |
| Tensor 的物理地址 | `MemAlloc` / `HwLayerMemAlloc` |
| Cascade 状态（L1 vs DDR） | `Cascade` / `InvalidCascadeEliminate` |
| In-place 复用关系 | `HwLayerInplace` / `LiveTimeAnalyse` |
| 同步信号位置 | `InsertSync` / `SyncAnalyse` |
| Idle 等待周期 | `InsertIdle` |
| Broadcast 类型 | `PreCodeGenPass` |

Codegen 进入时，每个 HwLayer 就是一个**填好所有参数的指令模板**，只差把参数编码进 bit 域。

---

## 4. Codegen 的特点

1. **纯发射器**：不做优化，不改变指令类型、顺序或数量，只翻译
2. **模板方法模式**：框架统一（遍历 → 分组 → 6步调用），子类只覆写 `Codegen()`
3. **分组机制**：连续同类无同步的 HwLayer 打成 Group，共享 Header/Tail/Sync
4. **单 Pass 完成**：没有多轮迭代，一次遍历全部生成
5. **产出是 uint64_t 序列**：不是中间表示，是最终硬件可执行的二进制
