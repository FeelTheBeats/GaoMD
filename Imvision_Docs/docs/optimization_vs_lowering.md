# AIC_V2 优化 Pass vs 阶段性 Lowering 分类

> 回答一个关键问题：为什么 Operator Graph 层大多是 Split（拆分）Pass，真正的优化在哪里？

---

## 核心结论

Operator Graph 层的 Pass **绝大多数是阶段性 Lowering**（把硬件不支持的算子拆成基本算子），不是真优化。真正意义的优化几乎全在后面两层（Kernel 层和分析图层）。

这是编译器的标准分层——**优化必须发生在硬件感知的层级**。

---

## 三层 IR 的 Pass 分类全景

```
┌─────────────────────────────────────────────────────────┐
│  Operator Graph (L1)                                    │
│  → 硬件无关，不知道 L1 多大、DDR 带宽多少                │
│  → 只能做"拆算子"（降低抽象级别）                        │
│  → 真正优化只有 PermuteReplaceReshape 等少数几个         │
├─────────────────────────────────────────────────────────┤
│  Kernel Graph (L2)                                      │
│  → 开始知道硬件参数（L1 size、MPU 数量、VPU 数量）       │
│  → 可以做算子融合、消除冗余、权重压缩                    │
│  → FusedOp 是这层最核心的优化                           │
├─────────────────────────────────────────────────────────┤
│  Analysis Graph (L3)                                    │
│  → 完全硬件感知。知道每条指令的执行顺序和内存地址         │
│  → 做 Cascade（L1 驻留）、In-place、DMA 合并            │
│  → 这是真正决定芯片性能的一层                            │
└─────────────────────────────────────────────────────────┘
```

---

## 1. Operator Graph (L1) — 算子图层

### 1.1 阶段性 Lowering（12 个）

硬件只能执行有限的原子操作（Conv、Eltwise、Activation、DMA、LUT），复杂算子必须拆分成基本算子组合：

| Pass | 输入 | 输出（拆成的基本算子） | 硬件限制原因 |
|------|------|----------------------|------------|
| **SoftmaxSplit** | Softmax | ReduceMax → Sub → Exp → ReduceSum → Inv → Mul | 无原生 Softmax 指令，用基本运算组合 |
| **NormSplit** | LayerNorm / RMSNorm | ReduceMean → Sub → Mul → Div → Mul → Add | 无原生 Norm 指令，拆为逐元素运算 |
| **SinCosSplit** | Sin / Cos | 查表(LUT) + 多项式逼近 | 无原生三角函数指令，查表+多项式拟合 |
| **ExpSplit** | Exp | 查表 + 基本运算 | 同 Sin/Cos，通过 LUT 逼近 |
| **InvSplit** | InvSqrt | 查表 + 基本运算 | 同 Exp，通过 LUT 逼近 |
| **LowerLogSoftmax** | LogSoftmax | Softmax → Log | 先做 Softmax，再取 Log |
| **MatmulSplit** | Matmul | Reshape → Conv2d → Reshape | 复用 Conv 硬件加速矩阵乘 |
| **ConvTranspose2dSplit** | ConvTranspose2d | Upsample + Conv2d | 无原生转置卷积，先上采样再卷积 |
| **ConvTranspose2d2Split** | ConvTranspose2d2 | Upsample + Conv2d | 同上（不同版本） |
| **Yuv2rgbSplit** | Yuv2rgb | Mul + Add 等基本运算 | 无原生颜色空间转换指令 |
| **NormTiling** | 大尺寸 Norm | 分块 → 分别计算 → 拼接 | 单次 Norm 受 L1 容量限制 |
| **SinCosTiling** | 大尺寸 Sin/Cos | 分块 → 分别计算 → 拼接 | 单次 LUT 查表受 L1 容量限制 |

这些都是 **"硬件不支持，不拆就编译不了"**，不是优化。拆完之后理论上执行效率会下降（更多算子 = 更多中间结果 = 更多 DDR 读写），后面靠 Kernel 层的融合和 Cascade 层把性能补回来。

### 1.2 真正优化？（3 个）

| Pass | 做了什么 | 为什么算优化 |
|------|---------|------------|
| **PermuteReplaceReshape** | 涉及 dim=1 维度的 Permute → Reshape | 消除不必要的 DMA 搬运。Reshape 只改 view 描述符，Permute 要实际搬数据 |
| **CompressTensorShapeHandle** | 多维 shape 压缩为硬件友好格式 | 减少 shape 描述开销 |
| **ChannelLimitSplitPermute** | 超大 Permute 按通道限制拆分 | 避免后端 MTE 硬件崩溃（更偏 lowering，但算是一种防御性变换） |

### 1.3 基础设施（2 个）

| Pass | 功能 |
|------|------|
| **ReadCfgFileInfos** | 读取编译配置文件 |
| **InsertCopy** | 数据布局不兼容时插入 layout 转换（正确性补丁，而非优化） |

---

## 2. Kernel Graph (L2) — 核图层

Lowering 完成后，编译器知道目标硬件的参数（L1 容量、MPU 数量、支持的融合模式等），可以开始做真正的优化。

### 2.1 算子融合（2 个）

| Pass | 融合模式 | 收益 |
|------|---------|------|
| **FusedOp** | Conv+Act, Conv+Pool+Act, Interp+Act, Pad+Conv, Conv+Act+Pool, Conv+Pool+Act | 🔥 减少中间 tensor 的 DDR 读写，是 Kernel 层最重要的优化 |
| **ConcatTreeFuse** | 多层嵌套 Concat → 单层 Concat | 减少 DMA 传输次数 |

### 2.2 消除冗余（3 个）

| Pass | 消除什么 | 典型场景 |
|------|---------|---------|
| **KernelConcatEliminate** | 冗余 Concat Kernel | 多个输入来自同一源的不同 slice 时，Concat 可消除 |
| **DeleteConcatBeforeConv** | Conv 前的冗余 Concat | Concat → Conv 可以分解为 Conv 分别处理各输入再合并 |
| **SliceFuse** | 连续 Slice 合并 | 两次相邻切片合并为一次切片，减少一次 DMA 操作 |

### 2.3 并行与流水线（1 个）

| Pass | 优化什么 | 收益 |
|------|---------|------|
| **TwoVpuPipeline** | 双 VPU 交替流水线 | 🔥 提高 VPU 利用率，一个 VPU 计算时另一个准备数据 |

### 2.4 权重优化（1 个）

| Pass | 优化什么 | 收益 |
|------|---------|------|
| **CompressWeight** | 权重量化压缩 | 减少 DDR 带宽和存储占用 |

### 2.5 拆分与限制处理（3 个）

| Pass | 做什么 | 性质 |
|------|--------|------|
| **SplitOp** | 超出硬件 capacity 的 Kernel 拆分为多个小 Kernel | 偏向 lowering，但避免了无法执行 |
| **SplitLargeTensor** | 超大 Tensor 拆分 | 避免超出硬件寻址范围 |
| **SliceTilingMove** | 调整 Slice 位置优化 tiling | 优化 tiling 效果 |

### 2.6 参数管理（2 个）

| Pass | 功能 |
|------|------|
| **PackParamDatas** | 打包参数数据到连续内存，便于一次性 DMA 加载 |
| **InsertParamDataFetch** | 为每个 Kernel 插入参数预取操作（计算前权重已在 L1） |

---

## 3. Analysis Graph (L3) — 分析图层（硬件执行图层）

这一层完全硬件感知，知道每条指令的执行顺序和内存地址。**真正决定芯片性能的优化都在这层**。

### 3.1 🔥🔥🔥 Cascade 级联（核心性能优化）

| Pass | 做什么 | 收益 |
|------|--------|------|
| **Cascade** | 将连续的 HwLayer 组织为级联执行，中间结果不写回 DDR，直接在 L1 内传递 | **大幅减少 DDR 带宽消耗**。对带宽敏感模型（如 LLM）可能是 2-3x 的性能提升 |
| **InvalidCascadeEliminate** | 消除不合法的 Cascade（依赖不满足、内存超出等），回退安全模式 | 确保正确性 |
| **MergeRdmaForCascade** | 合并 Cascade 场景下的多个 DMA 传输 | 减少传输次数和 setup 开销 |
| **SplitCascadeOp** | 为支持 Cascade 的算子做拆分预处理 | Cascade 的前置准备工作 |

### 3.2 内存复用

| Pass | 做什么 | 收益 |
|------|--------|------|
| **HwLayerInplace** | 输出覆盖不再使用的输入内存（In-place） | 减少内存峰值占用 |
| **LiveTimeAnalyse** | 分析每个 tensor 的活跃区间（产生到最后一次被使用） | 为 In-place 和内存复用提供依据 |
| **HwLayerMemAlloc** | 为每个 HwLayer 的临时 buffer 精确分配地址 | 复用生命周期不重叠的内存 |

### 3.3 硬件层虚拟化与消除

| Pass | 做什么 | 收益 |
|------|--------|------|
| **HwLayerSliceToDummy** | 不需实际执行的 Slice → 标记为 Dummy | 零硬件开销（仅改元数据描述符） |
| **HwLayerConcatToDummy** | 不需实际执行的 Concat → 标记为 Dummy | 零硬件开销 |
| **HwlayerConcatEliminate** | 消除 HwLayer 级别的冗余 Concat | 减少 DMA 操作（与 Kernel 层消冗互补） |

### 3.4 同步与时序优化

| Pass | 做什么 | 收益 |
|------|--------|------|
| **SyncAnalyse** | 分析同步屏障的必要性和位置 | 减少不必要的同步等待 |
| **InsertIdle** | 精确插入 Idle 等待周期 | 用最少等待满足时序约束 |

### 3.5 多核并行

| Pass | 做什么 | 收益 |
|------|--------|------|
| **MultiMpuParallelism** | 可并行的 MPU 操作标记为多核模式 | 多个 MPU 同时计算 |

---

## 4. 为什么 Operator 层几乎没有优化？

```
为什么不在 Operator 层做算子融合？

   Conv2d + Relu 在 ONNX 里是两个节点
   ↓
   如果在 Operator 层融合 → 创建一个"ConvRelu"算子
   ↓
   问题来了：
   ❌ 不知道 Conv 和 Relu 在哪个硬件上执行
   ❌ 不知道硬件是否支持 Conv+Act 融合执行
   ❌ 不知道 L1 够不够放下融合后的中间结果
   ❌ 不知道融合后是否需要额外的 DMA
   ↓
   结论：不做过早优化，等 Lowering 后硬件信息齐全了再融
```

**编译器的标准分层逻辑**：

| 层级 | 知道什么 | 不知道什么 | 能做的优化 |
|------|---------|-----------|-----------|
| Operator | 算子语义（Conv, Relu, Add...） | L1 容量、DDR 带宽、MPU 数量 | 语义等价变换（Permute→Reshape） |
| Kernel | 硬件 Kernel 类型、融合支持 | 内存地址、执行顺序 | 算子融合、消冗、权重压缩 |
| Analysis | 执行顺序、内存地址、硬件单元 | — | Cascade、In-place、DMA 合并、同步优化 |

---

## 5. 完整 Pass 分类速查表

### 按"优化 vs Lowering vs 基础设施"分类

#### 🔧 Lowering（硬件不支持，必须拆分）

| Pass | Layer |
|------|-------|
| SoftmaxSplit | Operator |
| NormSplit | Operator |
| NormTiling | Operator |
| SinCosSplit | Operator |
| SinCosTiling | Operator |
| ExpSplit | Operator |
| InvSplit | Operator |
| LowerLogSoftmax | Operator |
| MatmulSplit | Operator |
| ConvTranspose2dSplit | Operator |
| ConvTranspose2d2Split | Operator |
| Yuv2rgbSplit | Operator |
| Lowering | Operator→Kernel |
| SplitOp | Kernel |
| SplitLargeTensor | Kernel |
| ChannelLimitSplitPermute | Operator |
| BroadcastImplement | Kernel |

#### ⚡ 真正优化

| Pass | Layer | 类型 |
|------|-------|------|
| **Cascade** | Analysis | 🔥🔥🔥 级联执行 |
| **FusedOp** | Kernel | 🔥🔥 算子融合 |
| **HwLayerInplace** | Analysis | 🔥🔥 内存复用 |
| **TwoVpuPipeline** | Kernel | 🔥 VPU 流水线 |
| **LiveTimeAnalyse** | Analysis | 生命周期分析 |
| **HwLayerMemAlloc** | Analysis | 内存精确分配 |
| **MergeRdmaForCascade** | Analysis | DMA 传输合并 |
| **CompressWeight** | Kernel | 权重压缩 |
| **MultiMpuParallelism** | Analysis | 多核并行 |
| **SyncAnalyse** | Analysis | 同步优化 |
| **InsertIdle** | Analysis | 等待周期优化 |
| PermuteReplaceReshape | Operator | 语义等价变换 |
| KernelConcatEliminate | Kernel | 消除冗余 |
| DeleteConcatBeforeConv | Kernel | 消除冗余 |
| ConcatTreeFuse | Kernel | 融合 |
| SliceFuse | Kernel | 融合 |
| SliceTilingMove | Kernel | tiling 优化 |
| HwlayerConcatEliminate | Analysis | 消除冗余 |
| HwLayerSliceToDummy | Analysis | 虚拟化 |
| HwLayerConcatToDummy | Analysis | 虚拟化 |

#### 🏗️ 基础设施

| Pass | Layer |
|------|-------|
| ReadCfgFileInfos | Operator |
| InsertCopy | Operator |
| CompressTensorShapeHandle | Operator |
| GenIOInfo | Kernel |
| ParamsReplace | Kernel |
| BuildHwGraph | Kernel |
| BuildAnalyseGraph | Analysis |
| PackParamDatas | Kernel |
| InsertParamDataFetch | Kernel |
| InitialLoadParams | Kernel |
| InsertSync | Analysis |
| InsertDummyDma | Analysis |
| PreCodeGenPass | Analysis |
| Codegen | Analysis |
| AdjustIOOrderPass | Analysis |
| Analyze | Analysis |
| GenFiles | Analysis |
| BuildMemNodeLinks | Analysis |
| MemAlloc | Analysis |
| VbusIOMemManager | Analysis |
| SetVpuHwTypePass | Analysis |
| HandCfgHwTypePass | Analysis |
| MidResultsTransfer | Kernel |
| SplitCascadeOp | Kernel |
| InvalidCascadeEliminate | Analysis |
| DumpOperatorGraphPass | All |
| DumpKernelGraphPass | All |
| DumpAnalysisGraphPass | All |
