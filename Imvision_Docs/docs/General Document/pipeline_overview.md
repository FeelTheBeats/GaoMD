# AIC_V2 编译流水线全景

> 从输入到输出，68 个 Pass 的完整数据流。

---

## 总览

```
输入: model.json (SvJSON 格式的模型描述)
    │
    │  SvJsonParser.LoadNet()
    ▼
┌─────────────────────────────────────────┐
│  阶段 0: 解析 (Parser)                  │
│  JSON → Operator Graph (Net)            │
├─────────────────────────────────────────┤
│  阶段 1: Operator Graph 变换 (17 Pass)  │
│  拆分复杂算子 → 硬件能懂的基本算子       │
├─────────────────────────────────────────┤
│  阶段 2: Lowering (1 Pass)              │
│  Operator Graph → Kernel Graph          │
├─────────────────────────────────────────┤
│  阶段 3: Kernel 优化 (20 Pass)          │
│  融合 / 消冗 / 权重压缩 / 硬件图构建     │
├─────────────────────────────────────────┤
│  阶段 4: Analysis Graph 构建 (1 Pass)   │
│  Kernel HwGraph 拼接 → AnalyseGraph     │
├─────────────────────────────────────────┤
│  阶段 5: 内存与同步 (12 Pass)           │
│  Cascade / 分配 / In-place / 同步插入   │
├─────────────────────────────────────────┤
│  阶段 6: 代码生成 (4 Pass)              │
│  HwLayer → 指令 → 二进制                │
├─────────────────────────────────────────┤
│  阶段 7: 文件输出 (1 Pass)              │
│  生成最终产物                            │
└─────────────────────────────────────────┘
    │
    ▼
输出:  .o (指令) + data.json (元信息) + .tlf + .asm + param.bin + ...
```

---

## 阶段 0: 解析 (Parser)

```
输入:  model.json
         │
         ▼
      SvJsonParser::LoadNet()
         │  逐层解析 JSON，为每种层类型调用对应的 LayerParser
         │  (Conv2dParser, EltwiseParser, SoftmaxParser, ...)
         ▼
      Net (Operator Graph)
         │  节点 = Operator (Conv2d, Relu, Matmul, ...)
         │  边   = Tensor (NCHW, dtype, pattern)
         │  参数 = Value<ValueT> (权重, bias, LUT)
```

**关键代码** (`src/main.cpp:145-150`):
```cpp
aic::SvJsonParser parser;
parser.LoadNet(file_path, net);   // JSON → Net
```

Parser 通过 `LayerParserReg` 注册表分发到各 LayerParser：
```
Conv2d        → Conv2dParser
Eltwise3      → EltwiseParser
Softmax2      → SoftmaxParser
...（40+ 种层的 parser）
```

---

## 阶段 1: Operator Graph 变换 (17 Pass)

**操作对象**: `Net` (Operator Graph)

**目标**: 硬件不直接支持的算子，拆分为基本算子组合。

```
Softmax → ReduceMax → Sub → Exp → ReduceSum → Inv → Mul
Matmul  → Reshape → Conv2d → Reshape
LayerNorm → ReduceMean → Sub → Mul → Div → Mul → Add
Sin/Cos   → 查表(LUT) + 多项式
...
```

- 本质上不是优化，是**阶段性 Lowering**
- 唯一真优化: `PermuteReplaceReshape`（消除不必要的 DMA 搬运）

---

## 阶段 2: Lowering (1 Pass)

```
输入:  Net (Operator Graph)
         │
         ▼
      Lowering::RunOnModule()
         │  遍历每个 Operator
         │  调用 ConvertOpToKernel()
         │  创建对应的 Kernel，设置 device
         ▼
输出:  KernelNet (Kernel Graph)
         │  节点 = Kernel (Conv2dKernel, EltwiseKernel...)
         │  每个 Kernel 内有一个空的 HwGraph（待 BuildHwGraph 填充）
```

**关键映射** (简化):
```
Operator::Conv2d        → Kernel::Conv2dKernel
Operator::Eltwise       → Kernel::EltwiseKernel
Operator::Concat        → Kernel::ConcatKernel
Operator::Softmax(已拆分)→ 多个 EltwiseKernel + ActivationKernel
...
```

---

## 阶段 3: Kernel 优化 (20 Pass)

**操作对象**: `KernelNet` + 嵌入式 `HwGraph`

**核心优化**:

| Pass | 做什么 |
|------|--------|
| `FusedOp` | 🔥 Conv+Act, Conv+Pool+Act 等融合 |
| `CompressWeight` | 权重量化压缩 |
| `KernelConcatEliminate` | 消除冗余 Concat |
| `SliceFuse` | 合并连续 Slice |
| `TwoVpuPipeline` | VPU 双流水线组织 |

**核心构建**:

| Pass | 做什么 |
|------|--------|
| `BuildHwGraph` | 🔥 `Kernel::BuildHwGraphImpl()` → HwGraph 内填充 HwLayer |
| `GenIOInfo` | 生成 IO 地址/大小信息 |
| `BroadcastImplement` | 广播操作显式展开 |

```
BuildHwGraph 之前:
  Conv2dKernel {
    hw_graph_: 空
    attr_, weight_, bias_
  }

BuildHwGraph 之后:
  Conv2dKernel {
    hw_graph_: HwGraph {
      DMA_In_Layer  (加载输入特征图)
      Conv2d_Layer  (卷积计算)
      DMA_Out_Layer (写出结果)
    }
  }
```

---

## 阶段 4: Analysis Graph 构建 (1 Pass)

```
输入:  KernelNet（每个 Kernel 内有一个 HwGraph）
         │
         ▼
      BuildAnalyseGraph::RunOnModule()
         │  遍历每个 Kernel
         │  将其 HwGraph 中的 HwLayer 按执行顺序拼接到全局图
         │  处理 DMA_In/DMA_Out 匹配、Concat/Slice 连接
         ▼
输出:  AnalyseGraph
         │  节点 = AnalyseNode (包装 HwLayer*)
         │  全局执行顺序: order_to_node: {0→DMA_In, 1→Conv, 2→DMA_Out, ...}
         │  完全硬件感知
```

**这是整个编译流程的分水岭**：
- 之前：只知道"要算什么"和"用什么硬件方式算"
- 之后：知道"每条指令的精确执行顺序"

---

## 阶段 5: 内存与同步 (12 Pass)

**操作对象**: `AnalyseGraph`（其中 MemAlloc 读 KernelNet）

```
InsertSync(1)  ─── 插入同步屏障
    │
Cascade  ─── 🔥 级联优化（中间结果 L1 驻留）
    │
InvalidCascadeEliminate  ─── 移除非法 Cascade
    │
MemAlloc  ─── Kernel 级粗分配（读 KernelNet，依赖 Cascade 状态）
    │
HwLayerInplace  ─── 标记 In-place 复用
    │
LiveTimeAnalyse  ─── 分析 tensor 生命周期
    │
HwLayerMemAlloc  ─── HwLayer 级精细分配（复用不重叠生命周期）
    │
BuildMemNodeLinks  ─── 建立内存节点链接
    │
InsertDummyDma → InsertSync(2) → SyncAnalyse → InsertIdle
```

**Cascade 的效果**（简化）:
```
Cascade 前:                      Cascade 后:
  Conv ──DDR──→ Relu              Conv ──L1──→ Relu (中间结果不写 DDR)
    DDR 读写: 2 次                  DDR 读写: 1 次
```

---

## 阶段 6: 代码生成 (4 Pass)

```
PreCodeGenPass  ─── 最终地址绑定、指令排序
    │
Codegen  ─── 每个 HwLayer 生成 MCInstr 序列
    │         HwLayer::Codegen() → MCInstr[]
    │         HwLayer::CodegenSyncInst() → 同步指令
    │         HwLayer::CodegenHeaderInsts() → 包头
    │         HwLayer::CodegenTailInsts() → 校验和
    │
AdjustIOOrderPass  ─── 调整 IO tensor 顺序
    │
Analyze  ─── 统计资源使用（指令数、内存用量、带宽）
```

**指令生成示例** (简化):
```
HwLayer: Conv2d_Layer
  ↓ Codegen()
MCInstr[]: {
  {opcode: "CONV_CFG",   operands: {kernel_w, stride_h, ...}}
  {opcode: "DMA_IN",     operands: {src_addr, dst_addr, size}}
  {opcode: "CONV_EXEC",  operands: {weight_addr, bias_addr, act_type}}
  {opcode: "DMA_OUT",    operands: {src_addr, dst_addr, size}}
  {opcode: "SYNC_SET",   operands: {signal_id}}
  {opcode: "SYNC_CLR",   operands: {signal_id}}
}
```

---

## 阶段 7: 文件输出 (1 Pass)

```
GenFiles::RunOnModule()
    │
    ├── GenFileType::InsBin      → .o 文件（硬件可执行指令二进制）
    ├── GenFileType::AsmTxt      → .asm（汇编文本，调试用）
    ├── GenFileType::ParamBin    → param.bin（权重参数二进制）
    ├── GenFileType::DataJson    → data.json（tensor 元信息：地址/大小/dtype）
    ├── GenFileType::ModelTLF    → .tlf（Tensor Layout Format，完整模型包）
    ├── GenFileType::LocalMem    → local_mem.log（L1 内存分配日志）
    ├── GenFileType::OpTensorMap → optensor.map（算子-tensor 映射）
    └── GenFileType::RefModelJson→ ref_model.json（参考模型 JSON）
```

### 最终产物一览

| 文件 | 内容 | 用途 |
|------|------|------|
| **`.o`** | 硬件指令二进制 | 🔥 运行时加载执行 |
| **`data.json`** | Tensor 地址/大小/dtype/pattern | 运行时内存配置 |
| **`param.bin`** | 权重/bias 打包二进制 | 运行时加载到 L1 |
| **`.tlf`** | TLF 格式模型包（指令+参数+描述） | 完整部署包 |
| **`.asm`** | 指令汇编文本 | 调试/性能分析 |
| **`local_mem.log`** | L1 内存分配详情 | 内存调试 |
| **`optensor.map`** | 算子与 tensor 的映射关系 | 调试/可视化 |
| **`ref_model.json`** | 输入模型的副本 | 参考/对比 |

---

## 完整流水线（68 Pass 一览）

```
JSON 模型文件
    │  SvJsonParser
    ▼
┌─ 阶段 0: 解析 ─────────────────────────────────────────┐
│  LoadNet() → Net (Operator Graph)                       │
└────────────────────────────────────────────────────────┘
    │
    ▼
┌─ 阶段 1: Operator Graph 变换 ──────────────────────────┐
│  ReadCfgFileInfos                                       │
│  CompressTensorShapeHandle → InsertCopy                 │
│  Yuv2rgbSplit    NormTiling   NormSplit                 │
│  MatmulSplit     ConvTranspose2d2Split                  │
│  ConvTranspose2dSplit  SoftmaxSplit                     │
│  SinCosTiling    SinCosSplit   ExpSplit   InvSplit      │
│  LowerLogSoftmax                                        │
│  PermuteReplaceReshape  ChannelLimitSplitPermute        │
│  DumpOperatorGraphPass                                  │
└────────────────────────────────────────────────────────┘
    │
    ▼
┌─ 阶段 2: Lowering ─────────────────────────────────────┐
│  Lowering:  Net → KernelNet                             │
│  DumpKernelGraphPass                                    │
└────────────────────────────────────────────────────────┘
    │
    ▼
┌─ 阶段 3: Kernel 优化 ──────────────────────────────────┐
│  GenIOInfo → FusedOp → CompressWeight → SplitOp         │
│  KernelConcatEliminate → DeleteConcatBeforeConv         │
│  ParamsReplace → BroadcastImplement                     │
│  TwoVpuPipeline → SplitCascadeOp → ConcatTreeFuse       │
│  BuildHwGraph → SliceFuse → SliceTilingMove             │
│  DumpKernelGraphPass                                    │
│  MidResultsTransfer → MergeRdmaForCascade               │
│  PackParamDatas → HwlayerConcatEliminate                │
│  HwLayerSliceToDummy → InsertParamDataFetch             │
│  InitialLoadParams → SplitLargeTensor                   │
│  HwLayerConcatToDummy                                   │
└────────────────────────────────────────────────────────┘
    │
    ▼
┌─ 阶段 4: Analysis Graph 构建 ──────────────────────────┐
│  BuildAnalyseGraph  (各 Kernel 的 HwGraph → AnalyseGraph)│
│  DumpAnalysisGraphPass                                  │
└────────────────────────────────────────────────────────┘
    │
    ▼
┌─ 阶段 5: 内存与同步 ───────────────────────────────────┐
│  VbusIOMemManager → MultiMpuParallelism                 │
│  SetVpuHwTypePass → HandCfgHwTypePass                   │
│  InsertSync(1) → Cascade → InvalidCascadeEliminate      │
│  MemAlloc → HwLayerInplace → LiveTimeAnalyse            │
│  DumpAnalysisGraphPass                                  │
│  HwLayerMemAlloc → BuildMemNodeLinks                    │
│  InsertDummyDma → InsertSync(2) → SyncAnalyse           │
│  InsertIdle → PreCodeGenPass                            │
└────────────────────────────────────────────────────────┘
    │
    ▼
┌─ 阶段 6: 代码生成 ─────────────────────────────────────┐
│  Codegen → AdjustIOOrderPass → Analyze                  │
└────────────────────────────────────────────────────────┘
    │
    ▼
┌─ 阶段 7: 文件输出 ─────────────────────────────────────┐
│  GenFiles                                               │
│    ├── .o (指令二进制)                                   │
│    ├── .asm (汇编文本)                                   │
│    ├── param.bin (参数二进制)                            │
│    ├── data.json (tensor 元信息)                         │
│    ├── .tlf (完整模型包)                                 │
│    ├── local_mem.log (内存日志)                          │
│    ├── optensor.map (算子-tensor 映射)                   │
│    └── ref_model.json (模型副本)                         │
└────────────────────────────────────────────────────────┘
```

---

## 三层 IR 的数据流

```
          Module
            │
    ┌───────┼───────┐
    │       │       │
GraphManager │  FileManager
    │       │       │
    ▼       ▼       ▼
   Net   KernelNet  AnalyseGraph
  (L1)    (L2)       (L3)
    │       │          │
    │  Lowering        │  BuildAnalyseGraph
    ├──────►│          │
    │       ├─────────►│
    │       │          │
    │       │  BuildHwGraph  Codegen
    │       │  (Kernel→       │
    │       │   HwGraph)      ▼
    │       │             MCInstr[]
    │       │               │
    │       │               ▼
    │       │          GenFiles → .o + data.json + ...
```

---

## 相关文档

| 文档 | 内容 |
|------|------|
| [passes_guide.md](passes_guide.md) | 每个 Pass 的详细说明 |
| [ir_data_structures.md](ir_data_structures.md) | 三层 IR 核心数据结构（LLVM 类比） |
| [optimization_vs_lowering.md](optimization_vs_lowering.md) | 优化 Pass vs 阶段性 Lowering 分类 |
| [why_memory_at_analysis.md](why_memory_at_analysis.md) | 为什么内存分配在 Analysis Graph 阶段 |
