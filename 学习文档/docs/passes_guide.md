# AIC_V2 Pass 流水线全解

> 面向 aicompiler 入门者的 Pass 阅读指南。  
> 基于 `src/main.cpp` 中 `RegisterPasses()` 函数的 Pass 注册顺序编写。

---

## 目录

1. [整体架构概览](#1-整体架构概览)
2. [Pass 代码结构模式](#2-pass-代码结构模式)
3. [第一阶段：配置与图预处理](#3-第一阶段配置与图预处理)
4. [第二阶段：算子图变换 (Operator Graph)](#4-第二阶段算子图变换-operator-graph)
5. [第三阶段：Lowering — 算子→Kernel](#5-第三阶段lowering--算子kernel)
6. [第四阶段：Kernel 级优化](#6-第四阶段kernel-级优化)
7. [第五阶段：硬件图构建与优化](#7-第五阶段硬件图构建与优化)
8. [第六阶段：分析图构建](#8-第六阶段分析图构建)
9. [第七阶段：内存管理与分配](#9-第七阶段内存管理与分配)
10. [第八阶段：同步与时序](#10-第八阶段同步与时序)
11. [第九阶段：代码生成与输出](#11-第九阶段代码生成与输出)
12. [Pass 依赖关系速查表](#12-pass-依赖关系速查表)
13. [阅读建议](#13-阅读建议)

---

## 1. 整体架构概览

### 编译流程总览

```
输入 JSON (模型描述)
    │
    ▼
┌─────────────────────────────┐
│  1. 配置 & 算子图预处理      │  读取配置，拆分复杂算子
├─────────────────────────────┤
│  2. Lowering               │  算子图 → Kernel 图  ←── 关键转换！
├─────────────────────────────┤
│  3. Kernel 级优化           │  融合、拆分、消除冗余
├─────────────────────────────┤
│  4. 硬件图构建              │  Kernel → HwLayer (硬件层)
├─────────────────────────────┤
│  5. 分析图 & 内存管理       │  级联、内存分配、同步
├─────────────────────────────┤
│  6. 代码生成               │  输出指令二进制
└─────────────────────────────┘
    │
    ▼
输出: .o 文件 (可执行指令) + data.json (元信息)
```

### 三层图结构

| 图类型 | 类名 | 粒度 | 说明 |
|--------|------|------|------|
| **Operator Graph** | `Net` | 算子级 | 类似 ONNX 的计算图，包含 Conv2d、Softmax 等高级算子 |
| **Kernel Graph** | `KernelNet` | Kernel 级 | Lowering 后产生，每个 Kernel 对应一个硬件可执行的操作 |
| **Analysis Graph** | `AnalyseGraph` | HwLayer 级 | 硬件层图，包含 DMA/MPU/VPU 等硬件单元，用于内存分配和同步分析 |

---

## 2. Pass 代码结构模式

每个 Pass 遵循统一模式：

### 模式一：声明式（passes.h 中声明）

```cpp
// 在 include/aic/pm/passes.h 中声明
PASS_DEFINITION(SoftmaxSplit, ModulePass);

// 在 src/transforms/complex_op_split_softmax.cpp 中实现
class SoftmaxSplit : public ModulePass {
 public:
  void Show() const override { TLOG_I("using %s Pass!\n", "SoftmaxSplit"); }
  common::Status RunOnModule(Module &mod) override;
  // ... 私有辅助函数
};

// 文件末尾注册
PM_REGISTER_PASS(ModulePassRegistry, SoftmaxSplit, "SoftmaxSplit");
```

### 模式二：自包含式（直接在 cpp 中定义）

```cpp
// 在 target/tensor_brain/transforms/xxx.cpp 中
class FusedOp : public ModulePass {
 public:
  void Show() const override { TLOG_I("using %s Pass!\n", "FusedOp"); }
  common::Status RunOnModule(Module &mod) override;
  // ... 私有成员
};
PM_REGISTER_PASS(ModulePassRegistry, FusedOp, "FusedOp");
```

### 核心接口

```cpp
class ModulePass : public Pass {
 public:
  // 每个 Pass 唯一必须实现的入口函数
  virtual common::Status RunOnModule(Module &mod) = 0;

  // 获取前序 Pass 的分析结果（用于 Pass 间通信）
  AnalysisResult *GetModulePassResult(const std::string &resultpass);
};
```

### 典型代码骨架

```
1. 从 Module 中获取当前图
   ├── Net* net = mod.GetGraphManager()->GraphPtr();        // 算子图
   ├── KernelNet* knet = ...;                                // Kernel 图
   └── AnalyseGraph* ag = ...;                               // 分析图

2. 遍历图中节点（按拓扑序）
   └── GraphViewer(*net).GetNodesInTopologicalOrder();

3. 匹配目标算子/节点类型
   └── dynamic_cast<Conv2d*>(op) 或 node->type() == kConv2d

4. 执行变换（拆分/融合/替换/删除）

5. 返回 Status::OK() 或 Status::FAIL()
```

---

## 3. 第一阶段：配置与图预处理

### 3.1 ReadCfgFileInfos

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/read_config_files.cpp` |
| **功能** | 读取编译配置文件（如 cascade 配置、量化参数等），存入 `CfgFileInfo` 供后续 Pass 使用 |
| **输入** | JSON 模型文件中的配置段 |
| **输出** | 配置信息写入 Module Context |

这是整个编译流程的**第一步**，后续很多 Pass（如 Cascade、ParamsReplace）都依赖这里读入的配置。

---

## 4. 第二阶段：算子图变换 (Operator Graph)

这一阶段的 Pass 操作的是 **Operator Graph（Net）**，在 Lowering 之前，将复杂算子拆分为硬件能处理的基本算子组合。

### 4.1 CompressTensorShapeHandle

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/compress_tensor_shape_handle.cpp` |
| **功能** | 处理 Tensor 的 shape 压缩表示。将多维 shape 压缩为硬件友好的格式（如将 4D tensor 中大小为 1 的维度压缩掉） |
| **核心思路** | 遍历所有 Operator 的输入/输出 Tensor，规范化 shape 表示 |

### 4.2 InsertCopy

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/insert_copy_pass.cpp` |
| **功能** | 在需要处插入显式的 Copy 算子，解决 tensor 内存布局不兼容问题 |
| **典型场景** | 当两个连续算子的数据布局（如 NHWC vs NCHW）不一致时，插入 layout convert |

### 4.3 Yuv2rgbSplit

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/complex_op_split_yuv2rgb.cpp` |
| **功能** | 将 YUV→RGB 颜色空间转换算子拆分为基本算子组合（Mul + Add 等） |
| **背景** | 硬件不直接支持 YUV2RGB，需要软件层面展开 |

### 4.4 NormTiling

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/complex_op_tiling_basenorm.cpp` |
| **功能** | 对 LayerNorm / RMSNorm / InstanceNorm 做 **Tiling（分块）** |
| **关键点** | 大尺寸 Norm 需要切分为多个小块分别计算，再拼接结果 |

### 4.5 NormSplit

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/complex_op_split_basenorm.cpp` |
| **功能** | 将 Norm 算子拆分为基本算子链：ReduceMean → Sub → Mul → Div → Mul → Add 等 |
| **与 NormTiling 的关系** | NormTiling 决定"切多大"，NormSplit 执行"怎么拆" |

### 4.6 MatmulSplit

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/complex_op_split_matmul.cpp` |
| **功能** | 将 Matmul 拆分为 Conv2d（利用 Conv 硬件加速矩阵乘） |
| **核心技巧** | Matmul → Reshape → Conv2d → Reshape，把矩阵乘映射到卷积运算 |

### 4.7 ConvTranspose2dSplit / ConvTranspose2d2Split

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/complex_op_split_conv_transpose2d.cpp` / `complex_op_split_conv_transpose2d2.cpp` |
| **功能** | 将转置卷积（反卷积）拆分为普通 Conv2d + Upsample/Resize 等基本操作 |
| **区别** | 两个 Pass 处理不同版本的 ConvTranspose 算子 |

### 4.8 SoftmaxSplit

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/complex_op_split_softmax.cpp` |
| **功能** | 将 Softmax 拆分为：ReduceMax → Sub → Exp → ReduceSum → Inv → Mul 六个基本步骤 |
| **公式** | `softmax(x) = exp(x - max(x)) / sum(exp(x - max(x)))` |

### 4.9 SinCosTiling / SinCosSplit

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/complex_op_tiling_sin_cos.cpp` / `complex_op_split_sin_cos.cpp` |
| **功能** | Tiling：对大尺寸 Sin/Cos 做分块；Split：将 Sin/Cos 拆为查表+多项式逼近 |
| **背景** | 硬件通过查表（LUT）+ 多项式拟合实现三角函数 |

### 4.10 ExpSplit

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/complex_op_split_exp.cpp` |
| **功能** | 将 Exp 算子拆为查表操作+基本运算 |

### 4.11 InvSplit

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/complex_op_split_inv.cpp` |
| **功能** | 将 InvSqrt（倒数平方根）拆为查表+基本运算 |

### 4.12 LowerLogSoftmax

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/complex_op_lower_logsoftmax.cpp` |
| **功能** | 将 LogSoftmax 降级为 Softmax → Log 的组合 |
| **公式** | `logsoftmax(x) = log(softmax(x))` |

### 4.13 PermuteReplaceReshape

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/permute_replace_reshape.cpp` |
| **功能** | 将特定模式的 Permute（转置）替换为 Reshape（无需实际数据搬运，仅改变 view） |
| **优化原理** | 当 Permute 只涉及大小为 1 的维度交换时，等价于 Reshape，可以消除 DMA 开销 |

### 4.14 ChannelLimitSplitPermute

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/channel_limit_split_permute.cpp` |
| **功能** | 当 Permute 的通道数超过硬件限制时，将其拆分为多个小 Permute |
| **背景** | MTE（向量转置引擎）有最大通道数限制 |

### 4.15 DumpOperatorGraphPass

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/dump_graph_pass.cpp` |
| **功能** | 将当前的 Operator Graph 导出为可视化文件（dot 格式），用于**调试** |
| **说明** | 不做任何图变换，纯调试工具 |

---

## 5. 第三阶段：Lowering — 算子→Kernel

### 5.1 Lowering

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/lowering_pass.cpp` |
| **功能** | **整个编译流程最关键的转换**：将算子图（Operator Graph）转换为 Kernel 图（KernelNet） |
| **核心逻辑** | 遍历算子图中的每个 Operator，调用对应的 `ConvertOpToKernel()`，创建对应的硬件 Kernel 节点 |
| **典型映射** | `Conv2d(Op)` → `Conv2dKernel`，`Concat(Op)` → `ConcatKernel`，`Eltwise(Op)` → `EltwiseKernel` |
| **输入** | `Net`（算子图） |
| **输出** | `KernelNet`（Kernel 图，存储于 Module 的 GraphManager） |

### 5.2 DumpKernelGraphPass（第1次）

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/dump_graph_pass.cpp` |
| **功能** | 导出 Lowering 刚完成时的 Kernel 图，供调试用。与 DumpOperatorGraphPass 是同一个类的不同实例 |

---

## 6. 第四阶段：Kernel 级优化

以下 Pass 操作 **KernelNet**，在 Lowering 之后、硬件图构建之前。

### 6.1 GenIOInfo

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/gen_io_info_pass.cpp` |
| **功能** | 生成 Kernel 图的输入/输出信息（IO 地址、大小、格式），供后续内存管理和 DMA 配置使用 |
| **依赖** | KernelNet 已存在 |

### 6.2 FusedOp

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/fused_op.cpp` |
| **功能** | **算子融合**：将相邻的 Kernel 合并为一个融合 Kernel，减少内存搬运 |
| **融合模式** | Conv+Activation, Conv+Pool, Conv+Act+Pool, Interp+Act, Pad+Conv 等 |
| **收益** | 减少中间 tensor 的读写，降低带宽压力 |

### 6.3 CompressWeight

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/compress_weight_pass.cpp` |
| **功能** | 对权重数据进行压缩（如量化压缩），减少权重占用空间 |
| **背景** | 权重数据量大，压缩后可以减少 DDR 带宽和存储 |

### 6.4 SplitOp

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/split_op.cpp` |
| **功能** | 将过大（超过硬件 capacity）的 Kernel 拆分为多个小 Kernel |
| **典型场景** | 超大 Conv2d 的通道数超过 MPU 处理能力时，沿 C 维度拆分 |

### 6.5 KernelConcatEliminate

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/kernel_concat_opt_pass.cpp` |
| **功能** | 消除冗余的 Concat Kernel（当 Concat 的多个输入来自同一个源的不同 slice 时） |

### 6.6 DeleteConcatBeforeConv

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/delete_concat_before_conv.cpp` |
| **功能** | 删除 Conv 前的冗余 Concat（如果 Concat 沿 C 维拼接后直接给 Conv，则可以让 Conv 分别处理各输入） |

### 6.7 ParamsReplace

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/params_replace_pass.cpp` |
| **功能** | 根据配置文件中的参数替换规则，替换 Kernel 的权重/参数值 |

### 6.8 BroadcastImplement

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/broadcast_implement_pass.cpp` |
| **功能** | 实现 Broadcast 操作的显式展开（将 broadcast 转为实际的数据复制或将 broadcast 语义融入下游 Kernel） |

### 6.9 TwoVpuPipeline

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/two_vpu_pipeline.cpp` |
| **功能** | 将可流水线化的 VPU 操作组织为双流水线（Two-VPU Pipeline），提高 VPU 利用率 |
| **背景** | 芯片有两个 VPU，可以交替执行以提高吞吐 |

### 6.10 SplitCascadeOp

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/support_split_cascade_ops.cpp` |
| **功能** | 为支持 Cascade（级联）的算子进行拆分预处理 |
| **依赖** | TwoVpuPipeline |

### 6.11 ConcatTreeFuse

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/concat_tree_fuse.cpp` |
| **功能** | 将多层级的 Concat 树（多个 Concat 嵌套）融合为单层 Concat |

### 6.12 BuildHwGraph

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/build_hw_graph_pass.cpp` |
| **功能** | **Kernel → HwLayer 的转换**：为每个 Kernel 创建对应的硬件层（HwLayer），如 DMA_In、Conv2d_Layer、DMA_Out 等 |
| **输入** | KernelNet |
| **输出** | 每个 Kernel 挂载一个 HwGraph（硬件子图） |

### 6.13 SliceFuse

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/slice_fuse.cpp` |
| **功能** | 融合相邻的 Slice 操作（连续切分合并为一次切分） |

### 6.14 SliceTilingMove

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/slice_tiling_move.cpp` |
| **功能** | 调整 Slice 的位置以优化 tiling 效果 |

### 6.15 DumpKernelGraphPass（第2次）

| 属性 | 内容 |
|------|------|
| **功能** | 导出 Kernel 优化后的 Kernel 图（调试用） |

### 6.16 MidResultsTransfer

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/mid_result_transfer.cpp` |
| **功能** | 处理 Cascade 模式下中间结果的传输路径（在 L1 和 DDR 之间） |
| **依赖** | BuildHwGraph |

### 6.17 MergeRdmaForCascade

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/merge_rdma_for_cascade.cpp` |
| **功能** | 合并 Cascade 场景下的多个 RDMA（DMA）传输，减少传输次数 |
| **依赖** | MidResultsTransfer |

### 6.18 PackParamDatas

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/pack_param_datas_pass.cpp` |
| **功能** | 打包参数数据（权重、bias 等）到连续内存块，便于一次性 DMA 加载 |

### 6.19 HwlayerConcatEliminate

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/hwlayer_concat_opt_pass.cpp` |
| **功能** | 在 HwLayer 级别消除冗余 Concat 层（与 KernelConcatEliminate 类似，但操作对象是 HwLayer） |
| **依赖** | KernelConcatEliminate |

### 6.20 HwLayerSliceToDummy

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/HwlayerSliceTodummy.cpp` |
| **功能** | 将不需要实际执行的 Slice HwLayer 标记为 Dummy（仅元数据操作，不消耗硬件资源） |

### 6.21 InsertParamDataFetch

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/insert_param_data_fetch_pass.cpp` |
| **功能** | 为每个需要参数的 Kernel 插入参数预取操作（ParamFetch），确保计算前权重已在 L1 |

### 6.22 InitialLoadParams

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/initial_load_params.cpp` |
| **功能** | 生成初始化阶段的参数加载指令（在推理开始前将持久权重加载到 L1） |

### 6.23 SplitLargeTensor

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/split_large_tensor.cpp` |
| **功能** | 将超大 Tensor 拆分为多个小 Tensor，避免超出硬件寻址范围或 L1 容量限制 |

### 6.24 HwLayerConcatToDummy

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/HwlayerConcatTodummy.cpp` |
| **功能** | 将不需要实际执行的 Concat HwLayer 转为 Dummy（与 HwLayerSliceToDummy 对应） |

---

## 7. 第五阶段：分析图构建

### 7.1 BuildAnalyseGraph

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/build_analyse_graph_pass.cpp` |
| **功能** | **构建分析图（AnalyseGraph）**：将每个 Kernel 的 HwGraph 组合成全局的分析图，这是后续所有分析和优化的基础 |
| **核心逻辑** | 遍历所有 Kernel，将其 HwLayer 按执行顺序链接成全局图；处理 DMA_In/DMA_Out 的匹配；处理 Concat/Slice 的连接 |
| **输入** | KernelNet（每个 Kernel 已有 HwGraph） |
| **输出** | AnalyseGraph（全局硬件层图） |

### 7.2 DumpAnalysisGraphPass（第1次）

| 属性 | 内容 |
|------|------|
| **功能** | 导出刚构建的分析图（调试用） |

---

## 8. 第六阶段：内存管理与分配

### 8.1 VbusIOMemManager

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/vbus_io_mem_manager.cpp` |
| **功能** | 管理 VBus（向量总线）上 IO 内存的分配，为输入/输出 tensor 分配地址 |
| **依赖** | InitialLoadParams |

### 8.2 MultiMpuParallelism

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/multi_mpu_parallelism_pass.cpp` |
| **功能** | 分析并将可并行的 MPU（矩阵处理单元）操作标记为多核并行执行模式 |

### 8.3 SetVpuHwTypePass

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/set_vpu_hwtype_pass.cpp` |
| **功能** | 根据操作类型和目标硬件，设置 VPU（向量处理单元）的硬件类型 |
| **依赖** | MultiMpuParallelism |

### 8.4 HandCfgHwTypePass

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/hand_cfg_hwtype_pass.cpp` |
| **功能** | 允许通过配置文件手动指定某些层的硬件类型（覆盖自动选择），提供手动调优入口 |

### 8.5 InsertSync（第1次）

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/insert_sync_pass.cpp` |
| **功能** | 在需要同步的位置插入 Sync（同步屏障），确保数据依赖正确 |
| **依赖** | BuildAnalyseGraph |
| **核心逻辑** | 分析 HwLayer 之间的数据依赖，在有 RAW 依赖的层之间插入同步指令 |

### 8.6 Cascade

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/cascade_pass.cpp` |
| **功能** | **级联优化**：将连续的 HwLayer 组织为 Cascade（级联执行），使得中间结果不写回 DDR，直接在 L1 内传递 |
| **收益** | 大幅减少 DDR 带宽消耗，是性能优化的关键 Pass |
| **两种模式** | IFM Cascade（输入特征图级联）/ WGT Cascade（权重级联） |
| **依赖** | InsertSync |

### 8.7 InvalidCascadeEliminate

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/invalid_cascade_eliminate.cpp` |
| **功能** | 消除不合法的 Cascade（如依赖不满足、内存超出等），回退为普通执行模式 |
| **依赖** | Cascade |

### 8.8 MemAlloc

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/mem_allocator_pass.cpp` |
| **功能** | **全局内存分配**：为所有 Tensor 在 L1/DDR 上分配地址 |
| **核心逻辑** | 使用内存分配策略（如 ParallelBaseHwLayerType），分析 tensor 生命周期，复用不重叠的内存 |
| **依赖** | Cascade |

### 8.9 HwLayerInplace

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/hwlayer_inplace_opt.cpp` |
| **功能** | **In-place 优化**：当输入 tensor 不再被其他层使用时，允许输出覆盖输入的内存 |
| **收益** | 减少内存占用 |

### 8.10 LiveTimeAnalyse

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/livetime_analyse.cpp` |
| **功能** | **生命周期分析**：分析每个 tensor 的活跃区间（从产生到最后一次被使用），为内存复用提供依据 |
| **依赖** | HwLayerInplace |

### 8.11 DumpAnalysisGraphPass（第2次）

| 属性 | 内容 |
|------|------|
| **功能** | 导出内存分配后的分析图（调试用） |

### 8.12 HwLayerMemAlloc

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/hwlayer_mem_allocator.cpp` |
| **功能** | **硬件层内存分配**：为每个 HwLayer 内的临时 buffer 分配内存 |
| **依赖** | LiveTimeAnalyse |

### 8.13 BuildMemNodeLinks

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/build_links_base_on_mem.cpp` |
| **功能** | 基于内存分配结果，构建节点间的内存链接关系（用于生成内存管理指令） |

---

## 9. 第七阶段：同步与时序

### 9.1 InsertDummyDma

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/insert_dummy_dma.cpp` |
| **功能** | 插入虚拟 DMA 节点（Dummy DMA），用于占位或对齐时序 |

### 9.2 InsertSync（第2次）

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/insert_sync_pass.cpp` |
| **功能** | 在内存分配和 Cascade 完成后，再次检查和插入必要的同步屏障 |

### 9.3 SyncAnalyse

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/sync_analyse.cpp` |
| **功能** | **同步分析**：检查同步插入的正确性，分析同步开销，优化同步位置 |
| **核心逻辑** | 遍历分析图，验证所有数据依赖都有正确的同步保护 |

### 9.4 InsertIdle

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/insert_idle_pass.cpp` |
| **功能** | 插入 Idle（空闲/等待）指令，用于填充流水线气泡或等待前序操作完成 |

### 9.5 PreCodeGenPass

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/pre_codegen_pass.cpp` |
| **功能** | 代码生成前的最后准备工作（如最终地址绑定、指令序排序等） |

---

## 10. 第八阶段：代码生成与输出

### 10.1 Codegen

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/codegen_pass.cpp` |
| **功能** | **指令生成**：将分析图中的每个 HwLayer 转为硬件指令序列 |
| **核心逻辑** | 按 HwLayer 分组，调用各层的 emit 函数，生成二进制指令流 |

### 10.2 AdjustIOOrderPass

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/adjust_io_tensor_order.cpp` |
| **功能** | 调整输入/输出 Tensor 的顺序以匹配硬件要求 |
| **依赖** | Codegen |

### 10.3 Analyze

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/analyze_pass.cpp` |
| **功能** | **最终分析**：统计资源使用情况（指令数、内存用量、带宽等），生成编译报告 |

### 10.4 GenFiles

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/gen_files_pass.cpp` |
| **功能** | **输出文件生成**：生成最终的输出文件（指令二进制 `.o`、模型描述 `data.json`、TLF 文件等） |
| **输出产物** | `.o` 文件（可执行指令）、`data.json`（tensor 元信息）、`tlf`（Tensor Layout Format）、ASM 文本文件等 |

---

## 11. Pass 依赖关系速查表

```
ReadCfgFileInfos
    │
    ▼
CompressTensorShapeHandle → InsertCopy
    │
    ▼
[算子拆分阶段] Yuv2rgbSplit, NormTiling, NormSplit, MatmulSplit,
    ConvTranspose2d2Split, ConvTranspose2dSplit, SoftmaxSplit,
    SinCosTiling, SinCosSplit, ExpSplit, InvSplit, LowerLogSoftmax,
    PermuteReplaceReshape, ChannelLimitSplitPermute
    │
    ▼
Lowering ─────────────────────────────────────────────┐
    │                                                   │
    ▼                                                   │
GenIOInfo → FusedOp → CompressWeight → SplitOp         │
    │                                                   │
    ▼                                                   │
KernelConcatEliminate → DeleteConcatBeforeConv         │
    │                                                   │
    ▼                                                   │
ParamsReplace → BroadcastImplement                     │
    │                                                   │
    ▼                                                   │
TwoVpuPipeline → SplitCascadeOp → ConcatTreeFuse       │
    │                                                   │
    ▼                                                   │
BuildHwGraph → SliceFuse → SliceTilingMove             │
    │                                                   │
    ▼                                                   │
MidResultsTransfer ──(依赖 BuildHwGraph)               │
    │                                                   │
    ▼                                                   │
MergeRdmaForCascade ──(依赖 MidResultsTransfer)        │
    │                                                   │
    ▼                                                   │
PackParamDatas → HwlayerConcatEliminate                │
    │              ──(依赖 KernelConcatEliminate)        │
    ▼                                                   │
HwLayerSliceToDummy → InsertParamDataFetch             │
    │                                                   │
    ▼                                                   │
InitialLoadParams → SplitLargeTensor                   │
    │                                                   │
    ▼                                                   │
HwLayerConcatToDummy                                   │
    │                                                   │
    ▼                                                   │
BuildAnalyseGraph ────────────────────────────────────┘
    │
    ▼
VbusIOMemManager ──(依赖 InitialLoadParams)
    │
    ▼
MultiMpuParallelism → SetVpuHwTypePass
    │                      ──(依赖 MultiMpuParallelism)
    ▼
HandCfgHwTypePass
    │
    ▼
InsertSync(1) ──(依赖 BuildAnalyseGraph)
    │
    ▼
Cascade ──(依赖 InsertSync)
    │
    ▼
InvalidCascadeEliminate ──(依赖 Cascade)
    │
    ▼
MemAlloc ──(依赖 Cascade)
    │
    ▼
HwLayerInplace → LiveTimeAnalyse ──(依赖 Inplace)
    │
    ▼
HwLayerMemAlloc ──(依赖 LiveTime)
    │
    ▼
BuildMemNodeLinks
    │
    ▼
InsertDummyDma → InsertSync(2) → SyncAnalyse → InsertIdle
    │
    ▼
PreCodeGenPass
    │
    ▼
Codegen → AdjustIOOrderPass ──(依赖 Codegen)
    │
    ▼
Analyze → GenFiles
```

---

## 12. 阅读建议

### 按功能模块阅读

1. **先看主干**：`main.cpp` → `Lowering` → `BuildAnalyseGraph` → `MemAlloc` → `Cascade` → `Codegen`
2. **再看优化**：`FusedOp`（算子融合）、`SplitOp`（拆分）、`Cascade`（级联）
3. **最后看细节**：各种算子 Split/Tiling（SoftmaxSplit、NormSplit 等）

### 调试技巧

- 编译时加 `--dump-pass` 可导出每个阶段后的图（DumpKernelGraphPass、DumpAnalysisGraphPass 等）
- 用 Graphviz 打开 `.dot` 文件可视化图结构

### 关键概念

| 概念 | 说明 |
|------|------|
| **Tiling** | 将大数据切分为小块处理，适配有限的 L1 内存 |
| **Cascade** | 级联执行，中间结果留在 L1 不写回 DDR |
| **Fusion** | 算子融合，多个 Kernel 合并为一个 |
| **Sync** | 同步屏障，保证数据依赖正确 |
| **In-place** | 原地操作，输出覆盖输入以节省内存 |
| **DMA** | 直接内存访问，在 DDR ↔ L1 之间搬运数据 |

### 扩展阅读

- `include/aic/pm/module_pass.h` — Pass 基类定义
- `include/aic/pm/pm.h` — Pass 注册宏和 PassManagerOptions
- `src/pm/pass_manager.cpp` — Pass 调度执行逻辑
- `include/aic/pm/passes.h` — 算子图阶段 Pass 声明汇总

---

> 文档生成时间：2026-06-16  
> 基于分支 `master`，commit `bf99b05f`
