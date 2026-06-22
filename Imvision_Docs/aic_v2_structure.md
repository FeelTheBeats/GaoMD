# aic_v2 代码走读
## 一、入口-main.cpp
### int main
`main` 函数的主要工作流程：
1. 初始化和参数解析
   - 解析命令行参数（如输入文件、输出目录、SOC 类型等）
   - 配置内存追踪器（可选）

2. **创建编译环境**
   - 创建 `Module` 对象（编译上下文）
   - 将命令行参数保存到模块上下文

3. 二选一执行模式
   - 汇编模式：直接将程序集文件转换为二进制指令
   - **编译模式**（默认）：将 JSON 网络定义完整编译成硬件可执行代码
     - 解析 JSON 网络定义
     - 依次执行 100+ 个编译 Pass
     - 生成输出文件

4. 错误处理和输出
   - 若编译/汇编失败，输出错误信息
   - 若成功，输出完成提示和输出目录信息

5. 清理资源
   - 刷新内存追踪数据到文件

- 结论
main函数作为入口，做了很像LLVM中driver的事情，但是又很轻量级，直接拿到`.json`转换为Module后直接执行pass，而不是做复杂的解析。这在一定程度上说明了`.json`结构的确定性，与格式检查结构的轻，不像C编译器的source code那么复杂。作为一个囊括Pass注册和AI编译器compile流程的文件，十分的小而美。

#### 问题
- Pass注册是否需要解耦？做一个类似的PassManager，这在后续的新芯片中需要考量。
答：aic的pass比较轻量级，所有pass公用一个PassManager，暂时不需要pm进行解耦

- CompileModel是否需要单独一个类来承接，还是保持这种swift的风格？

### aic::PassManagerOptions RegisterPasses()
#### how to regist a new pass
xxxxxx

### Questions
1. module在哪里初始化，在哪里被填充
   - 在main中用构造函数初始化
   - 保存命令行参数
   - 解析并初始化网络图
   ```cpp
    // 创建网络图对象
    aic::Net *net = mod->GetGraphManager()->Create<aic::Net>();

    // 从 JSON 文件解析并填充网络图
    aic::SvJsonParser parser;
    parser.LoadNet(file_path, net);
    parser.ParseVersionInfo(&mod->GetContext()->version_info);
   ```  
   - 
2. Module 生命周期图
   ```
   main()
    ↓
    std::make_unique<aic::Module>(soc)  ← 构造函数完整初始化
    ↓ (1️⃣ 硬件配置、GraphManager、FileManager、PassContext)
    ↓
    SetModule(mod.get())                ← 保存到全局指针
    ↓
    mod->GetContext()->SetCmdArgs(...)  ← (2️⃣ 命令行参数)
    ↓
    CompileModel(mod)
    ↓
    mod->GetGraphManager()->Create<Net>() ← (3️⃣ 创建网络图容器)
    ↓
    parser.LoadNet()                    ← (4️⃣ 解析 JSON 填充网络)
    ↓
    RegisterPasses() + CreateAndRunPasses() ← Pass 管道执行
   ```
3. Net 是什么
   代码上：继承于`aic::Graph`，是一个具体的 IR 图类型
   定义上：表示一个网络模型的节点/算子和张量关系，用于保存`.json`解析后的网络解构
   意义上：Module作为最上层的容器，包含了太多信息，需要有一个单独的数据结构承载图结构的语义
   With Module：
   ```
    Module
    ├─ TargetMachine
    ├─ FileManager
    ├─ PassContext
    └─ GraphManager
        └─ Net (当前加载的网络)
   ```
4. 哪里开始正式跑pass
   src/pm/pm.cpp:CreateAndRunPasses
   main中是对其调用

## 二、编译流程总览 与 三层IR
### Summary pic
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

### Triple IR

#### 三层 IR 的 Pass 分类全景
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


简短总结：
- 三层设计按抽象与目标硬件逐步细化：从通用算子（`Net`）→ 硬件相关的 kernel 表示（`KernelNet`）→ 具体硬件单元/拓扑分析（`AnalyseGraph`），每一步都有专门的 Pass（`Lowering`、`BuildHwGraph`、`BuildAnalyseGraph`）负责转换与构建映射，方便分离前端语义、后端实现与硬件资源分析。
## 三、Passes
每个 Pass 遵循统一模式：
### Pass def
#### 模式一：声明式（passes.h 中声明）

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

#### 模式二：自包含式（直接在 cpp 中定义）

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

- 那么为什么会有两种注册模式？
声明式的pass操作对象是算子图，而自包含式pass更加私有，归属于特定后端，操作kernal and hw 层
┌──────────┬──────────────────────┬─────────────────────────────────┐
│          │        声明式        │            自包含式             │
├──────────┼──────────────────────┼─────────────────────────────────┤
│ 所在目录 │ src/transforms/      │ target/tensor_brain/transforms/ │
├──────────┼──────────────────────┼─────────────────────────────────┤
│ 操作对象 │ 算子图（Net）        │ Kernel 图 / 硬件层              │
├──────────┼──────────────────────┼─────────────────────────────────┤
│ 代码归属 │ 公共编译框架层       │ 特定后端（TensorBrain）         │
├──────────┼──────────────────────┼─────────────────────────────────┤
│ 架构分层 │ 与硬件解耦的通用变换 │ 与特定硬件强相关的变换          │
└──────────┴──────────────────────┴─────────────────────────────────┘

本质上这是分层架构的体现：
- src/transforms/ 是硬件无关的公共层，做算子拆分、Lowering 等通用事情。它用 passes.h 统一声明，方便维护。
- target/tensor_brain/transforms/ 是 TensorBrain 

---

### 第一阶段：配置与图预处理

#### ReadCfgFileInfos

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/read_config_files.cpp` |
| **功能** | 读取编译配置文件（如 cascade 配置、量化参数等），存入 `CfgFileInfo` 供后续 Pass 使用 |
| **输入** | JSON 模型文件中的配置段 |
| **输出** | 配置信息写入 Module Context |

这是整个编译流程的**第一步**，后续很多 Pass（如 Cascade、ParamsReplace）都依赖这里读入的配置。

- 配置内容详解

| 配置字段 | 数据类型 | 说明 | 示例 |
|--------|--------|------|------|
| **type** | 字符串 | 硬件类型：指定该层使用的硬件单元 | `"MPU"`、`"VPU"`、`"DMA"` |
| **en_str_cascade** | 布尔值 | 是否启用流式级联优化 | `true`/`false` |
| **split_dim** | 字符串 | 级联时的切分维度 | `"c"`（通道维）、`"h"`（高度维） |
| **blk_c** | 整数 | 级联块的通道数大小 | `64`、`128` |
| **blk_h** | 整数 | 级联块的高度大小 | `16`、`32` |
| **blk_w** | 整数 | 级联块的宽度大小 | `16`、`32` |
| **buf_num** | 整数 | 缓冲区数量（乒乓缓冲） | `2`、`3` |
| **blk_num** | 整数 | 总块数量 | `4`、`8` |

- 级联配置文件结构示例

```json
{
  "node": [
    {
      "name": "Conv2d_1",
      "type": "MPU",
      "store": {
        "en_cascade": true,
        "split_dim": "c",
        "blk_c": 64,
        "blk_h": 16,
        "blk_w": 32,
        "buf_num": 2,
        "blk_num": 4
      }
    }
  ]
}
```

###### 后续 Pass 的使用场景

- 1️⃣ **HandCfgHwTypePass**（硬件类型配置）

```cpp
// 手动指定硬件类型，覆盖自动选择
hw_layer->SetHwLayerType(ConvertHwLayerType(cfg_infos_mp.at(hw_layer_name).type));
```

**作用**：允许编译器使用者通过配置文件手动指定某些层用哪个硬件单元执行

- 2️⃣ **CascadePass**（级联优化）  —— **关键使用者**

```cpp
// 判断是否启用级联
if (!cfg_infos_mp.at(src_name).en_str_cascade) {
  // 跳过该层的级联优化
  continue;
}

// 使用切分配置生成级联块
CfgCascadeInfo(cfg_infos_mp.at(src_name), cascade, split_infos);
// 设置块大小
cascade.block.c = cfg.split_cfg.blk_c;
cascade.block.h = cfg.split_cfg.blk_h;
cascade.block.w = cfg.split_cfg.blk_w;
```

**作用**：根据配置文件中的参数进行级联分块优化，减少 DDR 带宽

- 配置文件位置

```
模型目录/
  ├── model.json          ← 模型网络结构（必需）
  └── cascade_cfg.json    ← 级联配置文件（可选）
```

> 如果没有 `cascade_cfg.json`，编译器会用**默认的自动级联策略**继续编译

- 关键要点总结

| 阶段 | Pass | 用到的配置 | 目的 |
|-----|------|----------|------|
| **Kernel 优化** | `ParamsReplace` | ❌ | 参数替换（暂不依赖配置） |
| **硬件类型选择** | `HandCfgHwTypePass` | `type` | 手动指定使用 MPU 还是 VPU |
| **级联优化** | `CascadePass` | `en_cascade`、`split_cfg` | 控制级联块大小和启用状态 |

所以 ReadCfgFileInfos 是**编译优化参数的配置读取器**，主要用来**精细调控级联和硬件类型选择**

---

### 第二阶段：算子图变换 (Operator Graph)

这一阶段的 Pass 操作的是 **Operator Graph（Net）**，在 Lowering 之前，将复杂算子拆分为硬件能处理的基本算子组合。

#### Operator Graph Pass 导读
Operator Graph 层的 Pass **绝大多数是阶段性 Lowering**（把硬件不支持的算子拆成基本算子），不是真优化。真正意义的优化几乎全在后面两层（Kernel 层和分析图层）。

这是编译器的标准分层——**优化必须发生在硬件感知的层级**。

##### 阶段性 Lowering（12 个）

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

##### 真正优化？（3 个）

| Pass | 做了什么 | 为什么算优化 |
|------|---------|------------|
| **PermuteReplaceReshape** | 涉及 dim=1 维度的 Permute → Reshape | 消除不必要的 DMA 搬运。Reshape 只改 view 描述符，Permute 要实际搬数据 |
| **CompressTensorShapeHandle** | 多维 shape 压缩为硬件友好格式 | 减少 shape 描述开销 |
| **ChannelLimitSplitPermute** | 超大 Permute 按通道限制拆分 | 避免后端 MTE 硬件崩溃（更偏 lowering，但算是一种防御性变换） |

##### 基础设施（2 个）

| Pass | 功能 |
|------|------|
| **ReadCfgFileInfos** | 读取编译配置文件 |
| **InsertCopy** | 数据布局不兼容时插入 layout 转换（正确性补丁，而非优化） |

---

#### Operator Graph Passes
##### 2.1 CompressTensorShapeHandle

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/compress_tensor_shape_handle.cpp` |
| **功能** | 它要在 IR 被任何优化/变形之前，捕获 Matmul 的原始 shape 语义，并写入 reference model JSON，作为后续所有对齐与验证的基准 |
| **核心思路** | 遍历所有 Operator 的输入/输出 Tensor，规范化 shape 表示 |

ps:一旦 IR 被改动，这些语义就不可逆地失真了。

##### 2.2 InsertCopy

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/insert_copy_pass.cpp` |
| **功能** | 在输入/输出边界显式插入 Copy 算子，把 global memory 和 local memory 之间的数据搬运以及 layout 转换从“隐式行为”变成“显式 IR 节点”。 |
| **典型场景** | 当两个连续算子的数据布局（如 NHWC vs NCHW）不一致时，插入 layout convert |

- 什么是"隐式的数据搬运 + layout转换"
隐式数据搬运 + layout转换 = 编译器假设“数据能直接用”，但硬件实际上必须通过 DMA + format transform 才能用

##### 2.3 Yuv2rgbSplit

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/complex_op_split_yuv2rgb.cpp` |
| **功能** | 将 YUV→RGB 颜色空间转换算子拆分为基本算子组合（Mul + Add 等） |
| **背景** | 硬件不直接支持 YUV2RGB，需要软件层面展开 |

ps：架构专用算法，需求驱动。

##### 2.4 NormTiling

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/complex_op_tiling_basenorm.cpp` |
| **功能** | 当 LayerNorm 的输入太大（满足条件）时，把 W 维切成多个 slice → 每个 slice 单独跑 LayerNorm → 最后 concat 回去。 |
| **关键点** | 大尺寸 Norm 需要切分为多个小块分别计算，再拼接结果 |

- LayerNorm（Layer Normalization）是一种对单个样本内部做归一化的操作。
- 代码里的 tensor：{1, C, H, W}
- 什么是 W 维？W = 最后一维（宽度 / sequence length / token 维 / spatial width）
- 为什么只能 split W？W 是“局部可独立计算的 block”,W slice 不破坏数学依赖
- 什么是沿着某一维度进行归一化？沿某维归一化 = 该维度上的元素共同参与 mean/variance 的计算。

##### 2.5 NormSplit

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/complex_op_split_basenorm.cpp` |
| **功能** | 把硬件不直接支持的高级 Norm 算子（LayerNorm / InstanceNorm / RMSNorm）拆解成硬件已经支持的小算子组合。 |
| **与 NormTiling 的关系** | NormTiling 决定"切多大"，NormSplit 执行"怎么拆" |

- 在整个计算图中，按拓扑顺序扫描所有 Norm 节点，并根据 Norm 类型分发到对应的 lowering / transformation 实现函数进行图改写。
- Norm Split 本质上也是个Lowering的过程，为什么aic的Lowering流程这么分散？
  AIC 把 lowering 从“函数式阶段”改成了“逐约束演化过程（constraint-driven IR refinement）”
   ✅ AIC 用“多pass分阶段 lowering”，替代“单一 lowering 层”
   ✅ 本质是 IR refinement pipeline，而不是 monolithic lowering

#### Operator Graph 遗留算子（未走读）
##### 2.6 MatmulSplit

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/complex_op_split_matmul.cpp` |
| **功能** | 将 Matmul 拆分为 Conv2d（利用 Conv 硬件加速矩阵乘） |
| **核心技巧** | Matmul → Reshape → Conv2d → Reshape，把矩阵乘映射到卷积运算 |

##### 2.7 ConvTranspose2dSplit / ConvTranspose2d2Split

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/complex_op_split_conv_transpose2d.cpp` / `complex_op_split_conv_transpose2d2.cpp` |
| **功能** | 将转置卷积（反卷积）拆分为普通 Conv2d + Upsample/Resize 等基本操作 |
| **区别** | 两个 Pass 处理不同版本的 ConvTranspose 算子 |

##### 2.8 SoftmaxSplit

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/complex_op_split_softmax.cpp` |
| **功能** | 将 Softmax 拆分为：ReduceMax → Sub → Exp → ReduceSum → Inv → Mul 六个基本步骤 |
| **公式** | `softmax(x) = exp(x - max(x)) / sum(exp(x - max(x)))` |

##### 2.9 SinCosTiling / SinCosSplit

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/complex_op_tiling_sin_cos.cpp` / `complex_op_split_sin_cos.cpp` |
| **功能** | Tiling：对大尺寸 Sin/Cos 做分块；Split：将 Sin/Cos 拆为查表+多项式逼近 |
| **背景** | 硬件通过查表（LUT）+ 多项式拟合实现三角函数 |

##### 2.10 ExpSplit

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/complex_op_split_exp.cpp` |
| **功能** | 将 Exp 算子拆为查表操作+基本运算 |

##### 2.11 InvSplit

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/complex_op_split_inv.cpp` |
| **功能** | 将 InvSqrt（倒数平方根）拆为查表+基本运算 |

##### 2.12 LowerLogSoftmax

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/complex_op_lower_logsoftmax.cpp` |
| **功能** | 将 LogSoftmax 降级为 Softmax → Log 的组合 |
| **公式** | `logsoftmax(x) = log(softmax(x))` |

##### 2.13 PermuteReplaceReshape

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/permute_replace_reshape.cpp` |
| **功能** | 将特定模式的 Permute（转置）替换为 Reshape（无需实际数据搬运，仅改变 view） |
| **优化原理** | 当 Permute 只涉及大小为 1 的维度交换时，等价于 Reshape，可以消除 DMA 开销 |

##### 2.14 ChannelLimitSplitPermute

| 属性 | 内容 |
|------|------|
| **文件** | `src/transforms/channel_limit_split_permute.cpp` |
| **功能** | 当 Permute 的通道数超过硬件限制时，将其拆分为多个小 Permute |
| **背景** | MTE（向量转置引擎）有最大通道数限制 |

##### 2.15 DumpOperatorGraphPass

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/dump_graph_pass.cpp` |
| **功能** | 将当前的 Operator Graph 导出为可视化文件（dot 格式），用于**调试** |
| **说明** | 不做任何图变换，纯调试工具 |

---

### 第三阶段：Kernel 级优化

#### Kernel Graph Pass 导读

##### 1 算子融合（2 个）

| Pass | 融合模式 | 收益 |
|------|---------|------|
| **FusedOp** | Conv+Act, Conv+Pool+Act, Interp+Act, Pad+Conv, Conv+Act+Pool, Conv+Pool+Act | 🔥 减少中间 tensor 的 DDR 读写，是 Kernel 层最重要的优化 |
| **ConcatTreeFuse** | 多层嵌套 Concat → 单层 Concat | 减少 DMA 传输次数 |

##### 2 消除冗余（3 个）

| Pass | 消除什么 | 典型场景 |
|------|---------|---------|
| **KernelConcatEliminate** | 冗余 Concat Kernel | 多个输入来自同一源的不同 slice 时，Concat 可消除 |
| **DeleteConcatBeforeConv** | Conv 前的冗余 Concat | Concat → Conv 可以分解为 Conv 分别处理各输入再合并 |
| **SliceFuse** | 连续 Slice 合并 | 两次相邻切片合并为一次切片，减少一次 DMA 操作 |

##### 3 并行与流水线（1 个）

| Pass | 优化什么 | 收益 |
|------|---------|------|
| **TwoVpuPipeline** | 双 VPU 交替流水线 | 🔥 提高 VPU 利用率，一个 VPU 计算时另一个准备数据 |

##### 2 权重优化（1 个）

| Pass | 优化什么 | 收益 |
|------|---------|------|
| **CompressWeight** | 权重量化压缩 | 减少 DDR 带宽和存储占用 |

##### 5 拆分与限制处理（3 个）

| Pass | 做什么 | 性质 |
|------|--------|------|
| **SplitOp** | 超出硬件 capacity 的 Kernel 拆分为多个小 Kernel | 偏向 lowering，但避免了无法执行 |
| **SplitLargeTensor** | 超大 Tensor 拆分 | 避免超出硬件寻址范围 |
| **SliceTilingMove** | 调整 Slice 位置优化 tiling | 优化 tiling 效果 |

##### 3 参数管理（2 个）

| Pass | 功能 |
|------|------|
| **PackParamDatas** | 打包参数数据到连续内存，便于一次性 DMA 加载 |
| **InsertParamDataFetch** | 为每个 Kernel 插入参数预取操作（计算前权重已在 L1） |

---

#### Kernal Graph Passes

##### 3.1 GenIOInfo

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/gen_io_info_pass.cpp` |
| **功能** | 生成 Kernel 图的输入/输出信息（IO 地址、大小、格式），供后续内存管理和 DMA 配置使用 |
| **依赖** | KernelNet 已存在 |

##### 3.2 FusedOp

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/fused_op.cpp` |
| **功能** | **算子融合**：将相邻的 Kernel 合并为一个融合 Kernel，减少内存搬运 |
| **融合模式** | Conv+Activation, Conv+Pool, Conv+Act+Pool, Interp+Act, Pad+Conv 等 |
| **收益** | 减少中间 tensor 的读写，降低带宽压力 |

##### 3.3 CompressWeight

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/compress_weight_pass.cpp` |
| **功能** | 对权重数据进行压缩（如量化压缩），减少权重占用空间 |
| **背景** | 权重数据量大，压缩后可以减少 DDR 带宽和存储 |

##### 3.4 SplitOp

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/split_op.cpp` |
| **功能** | 将过大（超过硬件 capacity）的 Kernel 拆分为多个小 Kernel |
| **典型场景** | 超大 Conv2d 的通道数超过 MPU 处理能力时，沿 C 维度拆分 |

##### 3.5 KernelConcatEliminate

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/kernel_concat_opt_pass.cpp` |
| **功能** | 消除冗余的 Concat Kernel（当 Concat 的多个输入来自同一个源的不同 slice 时） |

##### 3.6 DeleteConcatBeforeConv

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/delete_concat_before_conv.cpp` |
| **功能** | 删除 Conv 前的冗余 Concat（如果 Concat 沿 C 维拼接后直接给 Conv，则可以让 Conv 分别处理各输入） |

##### 3.7 ParamsReplace

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/params_replace_pass.cpp` |
| **功能** | 根据配置文件中的参数替换规则，替换 Kernel 的权重/参数值 |

##### 3.8 BroadcastImplement

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/broadcast_implement_pass.cpp` |
| **功能** | 实现 Broadcast 操作的显式展开（将 broadcast 转为实际的数据复制或将 broadcast 语义融入下游 Kernel） |

##### 3.9 TwoVpuPipeline

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/two_vpu_pipeline.cpp` |
| **功能** | 将可流水线化的 VPU 操作组织为双流水线（Two-VPU Pipeline），提高 VPU 利用率 |
| **背景** | 芯片有两个 VPU，可以交替执行以提高吞吐 |

##### 3.10 SplitCascadeOp

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/support_split_cascade_ops.cpp` |
| **功能** | 为支持 Cascade（级联）的算子进行拆分预处理 |
| **依赖** | TwoVpuPipeline |

##### 3.11 ConcatTreeFuse

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/concat_tree_fuse.cpp` |
| **功能** | 将多层级的 Concat 树（多个 Concat 嵌套）融合为单层 Concat |

##### 3.12 BuildHwGraph

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/build_hw_graph_pass.cpp` |
| **功能** | **Kernel → HwLayer 的转换**：为每个 Kernel 创建对应的硬件层（HwLayer），如 DMA_In、Conv2d_Layer、DMA_Out 等 |
| **输入** | KernelNet |
| **输出** | 每个 Kernel 挂载一个 HwGraph（硬件子图） |

##### 3.13 SliceFuse

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/slice_fuse.cpp` |
| **功能** | 融合相邻的 Slice 操作（连续切分合并为一次切分） |

##### 3.14 SliceTilingMove

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/slice_tiling_move.cpp` |
| **功能** | 调整 Slice 的位置以优化 tiling 效果 |

##### 3.15 DumpKernelGraphPass（第2次）

| 属性 | 内容 |
|------|------|
| **功能** | 导出 Kernel 优化后的 Kernel 图（调试用） |

##### 3.16 MidResultsTransfer

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/mid_result_transfer.cpp` |
| **功能** | 处理 Cascade 模式下中间结果的传输路径（在 L1 和 DDR 之间） |
| **依赖** | BuildHwGraph |

##### 3.17 MergeRdmaForCascade

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/merge_rdma_for_cascade.cpp` |
| **功能** | 合并 Cascade 场景下的多个 RDMA（DMA）传输，减少传输次数 |
| **依赖** | MidResultsTransfer |

##### 3.18 PackParamDatas

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/pack_param_datas_pass.cpp` |
| **功能** | 打包参数数据（权重、bias 等）到连续内存块，便于一次性 DMA 加载 |

##### 3.19 HwlayerConcatEliminate

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/hwlayer_concat_opt_pass.cpp` |
| **功能** | 在 HwLayer 级别消除冗余 Concat 层（与 KernelConcatEliminate 类似，但操作对象是 HwLayer） |
| **依赖** | KernelConcatEliminate |

##### 3.20 HwLayerSliceToDummy

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/HwlayerSliceTodummy.cpp` |
| **功能** | 将不需要实际执行的 Slice HwLayer 标记为 Dummy（仅元数据操作，不消耗硬件资源） |

##### 3.21 InsertParamDataFetch

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/insert_param_data_fetch_pass.cpp` |
| **功能** | 为每个需要参数的 Kernel 插入参数预取操作（ParamFetch），确保计算前权重已在 L1 |

##### 3.22 InitialLoadParams

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/initial_load_params.cpp` |
| **功能** | 生成初始化阶段的参数加载指令（在推理开始前将持久权重加载到 L1） |

##### 3.23 SplitLargeTensor

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/split_large_tensor.cpp` |
| **功能** | 将超大 Tensor 拆分为多个小 Tensor，避免超出硬件寻址范围或 L1 容量限制 |

##### 3.24 HwLayerConcatToDummy

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/HwlayerConcatTodummy.cpp` |
| **功能** | 将不需要实际执行的 Concat HwLayer 转为 Dummy（与 HwLayerSliceToDummy 对应） |

---
### 第四阶段：Analysis 级优化

Analysis Graph 做的是传统编译器后端在 指令选择之后、指令发射之前 做的事情
```
传统编译器后端:
  IR → ISel → Schedule → ┌─ RegAlloc ──────────┐ → Code Emission
                          │  liveness分析        │
                          │  spill/reload决策    │
                          │  stack slot复用      │
                          │  load/store合并      │
                          └─────────────────────┘

AIC:
  KernelNet → BuildAnalyseGraph → ┌─ Cascade ──────────┐ → Codegen
                                   │  MemAlloc           │
                                   │  HwLayerInplace     │
                                   │  LiveTimeAnalyse    │
                                   │  HwLayerMemAlloc    │
                                   │  MergeRdmaForCascade│
                                   │  InsertSync         │
                                   │  SyncAnalyse        │
                                   └────────────────────┘
```
区别只是：传统编译器管理的是寄存器，AIC 管理的是 L1 buffer。
Analysis Graph 优化 = 为 tensor buffer 做寄存器分配 + liveness 分析 + spill 决策，只不过"寄存器"是 L1 的一块区域，"spill"是写回 DDR。
这一层完全硬件感知，知道每条指令的执行顺序和内存地址。**真正决定芯片性能的优化都在这层**。

#### Analysis Graph Pass 导读

##### 1 🔥🔥🔥 Cascade 级联（核心性能优化）

| Pass | 做什么 | 收益 |
|------|--------|------|
| **Cascade** | 将连续的 HwLayer 组织为级联执行，中间结果不写回 DDR，直接在 L1 内传递 | **大幅减少 DDR 带宽消耗**。对带宽敏感模型（如 LLM）可能是 2-3x 的性能提升 |
| **InvalidCascadeEliminate** | 消除不合法的 Cascade（依赖不满足、内存超出等），回退安全模式 | 确保正确性 |
| **MergeRdmaForCascade** | 合并 Cascade 场景下的多个 DMA 传输 | 减少传输次数和 setup 开销 |
| **SplitCascadeOp** | 为支持 Cascade 的算子做拆分预处理 | Cascade 的前置准备工作 |

##### 2 内存复用

| Pass | 做什么 | 收益 |
|------|--------|------|
| **HwLayerInplace** | 输出覆盖不再使用的输入内存（In-place） | 减少内存峰值占用 |
| **LiveTimeAnalyse** | 分析每个 tensor 的活跃区间（产生到最后一次被使用） | 为 In-place 和内存复用提供依据 |
| **HwLayerMemAlloc** | 为每个 HwLayer 的临时 buffer 精确分配地址 | 复用生命周期不重叠的内存 |

##### 3 硬件层虚拟化与消除

| Pass | 做什么 | 收益 |
|------|--------|------|
| **HwLayerSliceToDummy** | 不需实际执行的 Slice → 标记为 Dummy | 零硬件开销（仅改元数据描述符） |
| **HwLayerConcatToDummy** | 不需实际执行的 Concat → 标记为 Dummy | 零硬件开销 |
| **HwlayerConcatEliminate** | 消除 HwLayer 级别的冗余 Concat | 减少 DMA 操作（与 Kernel 层消冗互补） |

##### 4 同步与时序优化

| Pass | 做什么 | 收益 |
|------|--------|------|
| **SyncAnalyse** | 分析同步屏障的必要性和位置 | 减少不必要的同步等待 |
| **InsertIdle** | 精确插入 Idle 等待周期 | 用最少等待满足时序约束 |

##### 5 多核并行

| Pass | 做什么 | 收益 |
|------|--------|------|
| **MultiMpuParallelism** | 可并行的 MPU 操作标记为多核模式 | 多个 MPU 同时计算 |

---

#### Analysis Graph Passes
##### 内存管理与分配
###### 4.1 VbusIOMemManager

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/vbus_io_mem_manager.cpp` |
| **功能** | 管理 VBus（向量总线）上 IO 内存的分配，为输入/输出 tensor 分配地址 |
| **依赖** | InitialLoadParams |

###### 4.2 MultiMpuParallelism

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/multi_mpu_parallelism_pass.cpp` |
| **功能** | 分析并将可并行的 MPU（矩阵处理单元）操作标记为多核并行执行模式 |

###### 4.3 SetVpuHwTypePass

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/set_vpu_hwtype_pass.cpp` |
| **功能** | 根据操作类型和目标硬件，设置 VPU（向量处理单元）的硬件类型 |
| **依赖** | MultiMpuParallelism |

###### 4.4 HandCfgHwTypePass

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/hand_cfg_hwtype_pass.cpp` |
| **功能** | 允许通过配置文件手动指定某些层的硬件类型（覆盖自动选择），提供手动调优入口 |

###### 4.5 InsertSync（第1次）

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/insert_sync_pass.cpp` |
| **功能** | 在需要同步的位置插入 Sync（同步屏障），确保数据依赖正确 |
| **依赖** | BuildAnalyseGraph |
| **核心逻辑** | 分析 HwLayer 之间的数据依赖，在有 RAW 依赖的层之间插入同步指令 |

###### 4.6 Cascade

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/cascade_pass.cpp` |
| **功能** | **级联优化**：将连续的 HwLayer 组织为 Cascade（级联执行），使得中间结果不写回 DDR，直接在 L1 内传递 |
| **收益** | 大幅减少 DDR 带宽消耗，是性能优化的关键 Pass |
| **两种模式** | IFM Cascade（输入特征图级联）/ WGT Cascade（权重级联） |
| **依赖** | InsertSync |

###### 4.7 InvalidCascadeEliminate

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/invalid_cascade_eliminate.cpp` |
| **功能** | 消除不合法的 Cascade（如依赖不满足、内存超出等），回退为普通执行模式 |
| **依赖** | Cascade |

###### 4.8 MemAlloc

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/mem_allocator_pass.cpp` |
| **功能** | **全局内存分配**：为所有 Tensor 在 L1/DDR 上分配地址 |
| **核心逻辑** | 使用内存分配策略（如 ParallelBaseHwLayerType），分析 tensor 生命周期，复用不重叠的内存 |
| **依赖** | Cascade |

###### 4.9 HwLayerInplace

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/hwlayer_inplace_opt.cpp` |
| **功能** | **In-place 优化**：当输入 tensor 不再被其他层使用时，允许输出覆盖输入的内存 |
| **收益** | 减少内存占用 |

###### 4.10 LiveTimeAnalyse

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/livetime_analyse.cpp` |
| **功能** | **生命周期分析**：分析每个 tensor 的活跃区间（从产生到最后一次被使用），为内存复用提供依据 |
| **依赖** | HwLayerInplace |

###### 4.11 DumpAnalysisGraphPass（第2次）

| 属性 | 内容 |
|------|------|
| **功能** | 导出内存分配后的分析图（调试用） |

###### 4.12 HwLayerMemAlloc

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/hwlayer_mem_allocator.cpp` |
| **功能** | **硬件层内存分配**：为每个 HwLayer 内的临时 buffer 分配内存 |
| **依赖** | LiveTimeAnalyse |

###### 4.13 BuildMemNodeLinks

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/build_links_base_on_mem.cpp` |
| **功能** | 基于内存分配结果，构建节点间的内存链接关系（用于生成内存管理指令） |
##### 同步与时序

###### 4.14 InsertDummyDma

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/insert_dummy_dma.cpp` |
| **功能** | 插入虚拟 DMA 节点（Dummy DMA），用于占位或对齐时序 |

###### 4.15 InsertSync（第2次）

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/insert_sync_pass.cpp` |
| **功能** | 在内存分配和 Cascade 完成后，再次检查和插入必要的同步屏障 |

###### 4.16 SyncAnalyse

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/sync_analyse.cpp` |
| **功能** | **同步分析**：检查同步插入的正确性，分析同步开销，优化同步位置 |
| **核心逻辑** | 遍历分析图，验证所有数据依赖都有正确的同步保护 |

###### 4.17 InsertIdle

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/insert_idle_pass.cpp` |
| **功能** | 插入 Idle（空闲/等待）指令，用于填充流水线气泡或等待前序操作完成 |

###### 4.18 PreCodeGenPass

| 属性 | 内容 |
|------|------|
| **文件** | `target/tensor_brain/transforms/pre_codegen_pass.cpp` |
| **功能** | 代码生成前的最后准备工作（如最终地址绑定、指令序排序等） |

---

### 第五阶段：codegen(重点看)
参考codegen_reading_guide.md