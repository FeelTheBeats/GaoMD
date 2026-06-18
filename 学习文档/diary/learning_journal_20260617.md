# AIC 学习日记 — 2026-06-17

> 按对话顺序，每轮一问一答，精简要点。

---

### Q1: Pass 注册为什么有两种模式？

**发现**：`passes.h` 声明了 28 个 Pass（声明式），但 `RegisterPasses()` 注册了 68 个，差 37 个。

**原因**：分层架构。
- `src/transforms/` → 硬件无关的通用 Pass，用 `passes.h` 统一声明
- `target/tensor_brain/transforms/` → 硬件相关的后端 Pass，类定义+实现+注册全在一个 .cpp 里

---

### Q2: 各层 IR 有哪些重要数据结构？（类比 LLVM Module/Function/Instruction）

三层 IR + LLVM 对照：

| LLVM | AIC |
|---|---|
| `Module` | `Module` |
| `Function` | `Graph` |
| `BasicBlock` | 拓扑序 `NodeIndex[]` |
| `Instruction` | `Node` |
| `Value` | `NodeArg` / `Tensor` |
| `Use` | `EdgeEnd` |
| 常量 | `Value<ValueT>`（权重/bias） |

关键区别：LLVM 的 `Instruction` 本身就是 `Value`，AIC 的数据（Tensor）和操作（Node）是分离的。

---

### Q3: Operator Graph 层为什么大多是 Split，真正的优化在哪？

**结论**：Operator 层 12 个 Split 都是阶段性 Lowering（硬件不支持原语，必须拆）。真正的优化全在 Kernel 层和 Analyse 层：

- Kernel 层：`FusedOp`（融合）、`ConcatEliminate`（消冗）、`CompressWeight`
- Analyse 层：`Cascade`（L1 驻留，🔥 核心优化）、`HwLayerInplace`、`LiveTimeAnalyse`

**原因**：优化必须发生在硬件感知的层级。Operator 层不知道 L1 多大、DDR 带宽多少，没法做优化决策。

---

### Q4: 为什么内存分配放在 Analysis Graph 阶段？

四个原因：

1. **Cascade 先跑**：决定 tensor 在 L1 还是 DDR，分配必须等这个结论
2. **需要全局执行顺序**：拓扑序有多义性，只有 `order_to_node` 能精确定义 tensor 的"生"和"死"时刻
3. **粒度是 HwLayer 不是 Kernel**：一个 Kernel 展开后 3-5 个 HwLayer，每个都需要独立 buffer
4. **In-place 需要全局消费者图**：必须知道所有下游使用者才能判断能否复用

---

### Q5: 编译流水线全貌？

```
JSON → Parser → Operator Graph → Lowering → Kernel Graph
    → BuildAnalyseGraph → Analyse Graph
    → (Cascade/MemAlloc/Sync) → Codegen → uint64_t → .o
```

中间经历了 68 个 Pass。输出的 .o 是 uint64_t 指令流，data.json 是 tensor 元信息。

---

### Q6: AnalyseGraph 是什么数据结构？

`Graph` 子类，核心新增：

```cpp
map<uint32_t, AnalyseNode*> order_to_node_;   // 执行序号 → 节点
map<AnalyseNode*, uint32_t> node_to_order_;   // 反向索引
```

这是**确定的硬件执行序**（不是拓扑序）。节点 `AnalyseNode` 包装 `HwLayer*`，不拷贝。

与 KernelNet 的关系：`BuildAnalyseGraph` 把每个 Kernel 的 HwGraph 展开 → 按规则拼成全局图 → 建立 HwLayer 间跨 Kernel 边。

---

### Q7: Codegen 与 LLVM Codegen 的异同？

**相同**：都有 Machine IR 层、MC 指令抽象、代码生成与文件输出分离。

**关键不同**：

| | LLVM | AIC |
|---|---|---|
| 没有 | — | 寄存器分配、指令选择、指令调度 |
| 原因 | — | VLIW + 固定功能单元 + 物理地址 |
| 真正难的 | RegAlloc + Scheduling | Cascade + MemAlloc |
| Codegen 是 | 最复杂的后端阶段 | 纯发射器 |

---

### Q8: HwLayer 是什么？Dummy 层是什么？

**HwLayer**：一条硬件可执行操作的抽象基类。子类覆盖所有硬件单元（DMA_In、Conv2dLayer、EltwiseLayer、PermuteLayer...）。持有输入/输出 tensor、Cascade 配置、同步信号、指令容器。核心接口 `Codegen()` 把自己翻译为 uint64_t 指令序列。

**Dummy 层**：`is_dummy_ = true` 的虚拟 HwLayer。当 Concat/Slice 的数据已在物理上连续时，操作退化为地址代数（零硬件指令）。在 AnalyseGraph 中占位维持数据流，但在 Codegen 中直接跳过。

与 LLVM 的 i64→i32 拆分不同：LLVM 是"硬件不支持，产生更多指令"，Dummy 是"数据已在，产生零条指令"。

---

### Q9: 怎么理解 Analysis Graph 级别的优化？Kernel 层像什么？

**Analysis Graph 优化** = 为 tensor buffer 做寄存器分配 + liveness + spill 决策。类比：

| 传统编译器 | AIC |
|---|---|
| 寄存器分配 | MemAlloc / HwLayerMemAlloc |
| Liveness | LiveTimeAnalyse |
| Register Coalescing | HwLayerInplace |
| Spill/Reload | Cascade（L1 驻留 vs DDR） |

**Kernel 层定位**：做传统编译器 IR 层中间优化（融合≈instcombine，消冗≈DCE/GVN），但也开始引入硬件信息（BuildHwGraph）。大致对应 LLVM IR target-specific 之后、ISel 之前。

---

### Q10: Codegen 简易流程？

```
PreCodeGenPass
    ↓
Codegen::RunOnModule()
    ├─ 获取 AnalyseGraph 执行序
    ├─ 遍历，跳过 Dummy，收集 node_list
    ├─ GetHwLayerGroupList() 分组（连续同类无sync→打包）
    ├─ 对每个 Group：
    │    ├─ 每个 HwLayer: SatisfyHardwareConstrain() → Codegen()
    │    ├─ CodegenHeaderInsts() → 模块头
    │    ├─ CodegenSyncInst()    → 同步信号
    │    ├─ CodegenTailInsts()   → 校验和
    │    └─ CodegenIdleInstsIfNeeded() → Idle等待
    └─ 重排 inputs/outputs 顺序
    ↓
AdjustIOOrderPass → Analyze → GenFiles → .o
```

所有 HwLayer 走同一流程，唯一例外是 Dummy 层（直接跳过）。

---

### Q11: Codegen 做流水线优化吗？

不。Codegen 是**纯发射器**，分组只是机械规则（连续+同类+无sync→打包）。真正的流水线优化（TwoVpuPipeline、Cascade、MergeRdmaForCascade）全在前面完成。

LLVM 的 "CodeGen" 包含了 AIC 的 Kernel 层后半 + Analyse 层 + Codegen。AIC 的 Codegen 只对应 LLVM 的最后一步 MC Emit。

---

### Q12: Kernel 层有大概的执行顺序吗？

有拓扑序，拓扑序**有多义性**。一个 DAG 可能有多种合法拓扑排序。Kernel 层只有依赖图，Analyse 层选定一种具体执行顺序，并决定数据路径（L1/DDR）和同步位置。

类比修正：**"one DAG, multi valid schedules"**，而非 "one instruction multi choices"（指令类型已确定，HwLayer 类型在 Kernel 层就写死了）。
