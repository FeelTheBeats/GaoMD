# AIC_V2 三层 IR 核心数据结构

> 用 LLVM IR 做类比，帮助快速建立心智模型。  
> 关键区别：AIC 有**三层 IR**，不是 LLVM 的一层。每层有自己的"图 + 节点 + 边"体系。

---

## 0. 先看全景：三层 IR 的演进

```
JSON 模型文件
    │  Parser (SvJsonParser)
    ▼
┌──────────────────────────────────────────────────────┐
│  L1: Operator Graph (算子图)                         │
│  Graph: Net    Node: Operator    Data: Tensor/Value  │
│  类似 ONNX Graph，表达"做什么计算"                    │
│  例: Conv2d, Softmax, Matmul, Eltwise...             │
├──────────────────────────────────────────────────────┤
│  L2: Kernel Graph (内核图)     ← Lowering 转换       │
│  Graph: KernelNet   Node: Kernel    Data: Tensor     │
│  类似 LLVM IR，表达"用什么硬件方式算"                  │
│  例: Conv2dKernel, ConcatKernel, DMADataCopyKernel   │
│  每个 Kernel 内部包含一个 HwGraph (硬件子图)          │
├──────────────────────────────────────────────────────┤
│  L3: Analysis Graph (分析图)   ← BuildAnalyseGraph   │
│  Graph: AnalyseGraph  Node: AnalyseNode              │
│  Node 包含 HwLayer 指针                               │
│  类似 Machine IR / Schedule IR，表达"硬件怎么执行"    │
│  例: NPU_DMA_IN_Layer, Conv2d_Layer, NPU_DMA_OUT...  │
└──────────────────────────────────────────────────────┘
    │  Codegen
    ▼
二进制指令流 (.o 文件)
```

---

## 1. 全局容器：`Module`（类比 `llvm::Module`）

```
LLVM:   llvm::Module → 包含 Function 列表 + 全局变量
AIC:    aic::Module  → 包含三层 Graph + TargetMachine + FileManager
```

| 成员 | 类型 | 用途 |
|------|------|------|
| `graph_manager_` | `GraphManager` | 管理所有 IR 图的创建/销毁/查找 |
| `target_machine_` | `TargetMachine` | 目标硬件信息（指令集、内存规格） |
| `file_manager_` | `FileManager` | 输入/输出文件路径管理 |
| `context_` | `PassContext` | Pass 执行上下文（计数器、version info 等） |

```cpp
// include/aic/ir/module.h
class Module final {
  unique_ptr<TargetMachine>  target_machine_;   // 硬件抽象
  unique_ptr<GraphManager>   graph_manager_;    // 图管理器
  unique_ptr<FileManager>    file_manager_;     // 文件管理
  unique_ptr<PassContext>    context_;           // Pass 上下文
};
```

**关键操作**：`mod.GetGraphManager()->Create<Net>(name)` 创建图。

---

## 2. 图与节点基类（三层共享的骨架）

### 2.1 `Graph`（类比 `llvm::Function` 的容器能力 + `llvm::Module` 的 Node 管理）

```
LLVM:   Function 是 Instruction 的容器，有 BasicBlock 列表
AIC:    Graph    是 Node 的容器，有 Node 列表 + NodeArg 列表 + 边关系
```

```cpp
// include/aic/graph/graph.h
class Graph {
  string name_;                                        // 图名
  vector<unique_ptr<Node>> nodes_;                     // 所有节点（索引即 NodeIndex）
  unordered_map<string, NodeIndex> node_name_to_idx_;  // 名字→索引
  unordered_map<string, unique_ptr<NodeArg>> node_args_;// 所有数据（Tensor）
  vector<const NodeArg*> graph_inputs_;                // 图输入
  vector<const NodeArg*> graph_outputs_;               // 图输出
  vector<NodeIndex> nodes_in_topological_order_;       // 拓扑序（Resolve 后有效）

  // 添加节点
  template<class NodeChild> NodeChild& AddNode(string name);
  // 添加/获取 Tensor
  template<class NodeArgChild> NodeArgChild& GetOrCreateNodeArg(string name);
  // 添加边
  void AddEdge(src_idx, dst_idx, src_arg, dst_arg);
  // 验证图合法性（检查 DAG、连接关系、类型匹配）
  Status Resolve();
};
```

### 2.2 `Node`（类比 `llvm::Instruction` 的基类地位）

```
LLVM:   Instruction : Value    （指令本身也是值，有 use-def 链）
AIC:    Node : 独立类            （节点不是值，节点通过 NodeArg 连接）
```

```cpp
// include/aic/graph/node.h
class Node {
  string name_;                    // 节点名
  NodeIndex index_;                // 在图中的索引
  Graph* graph_;                   // 所属 Graph

  Definitions definitions_;        // 输入/输出 NodeArg 列表
  Relationships relationships_;    // 上下游边关系

  // 遍历上下游
  NodeConstIterator InputNodesBegin/End();
  NodeConstIterator OutputNodesBegin/End();

  // 获取输入/输出 NodeArg
  vector<NodeArg*>& MutableInputs();
  vector<NodeArg*>& MutableOutputs();
};
```

**与 LLVM 的关键差异**：
- LLVM 中 `Instruction` **是** `Value`，指令直接连指令（use-def chain）
- AIC 中 `Node` **不是**数据，数据是独立的 `NodeArg`（Tensor），Node 通过 `input_defs/output_defs` 间接引用数据

### 2.3 `NodeArg` / `Tensor`（类比 `llvm::Value`）

```
LLVM:   Value 是所有可被引用的东西的基类（Instruction, Argument, Constant...）
AIC:    NodeArg 是数据的基类，Tensor 是唯一子类（4D: NCHW）
        Value<ValueT> 是权重/bias/LUT 的参数存储（不参与数据流图）
```

```cpp
// include/aic/graph/node_arg.h     —— 数据的基类，核心就是名字
class NodeArg {
  string name_;    // 唯一标识，如 "conv1.output"
};

// include/aic/base/tensor.h         —— 特征图（feature map），4维张量
class Tensor : public NodeArg {
  Dimensions dim_;          // [N, C, H, W]
  DataType data_type_;      // kFp16, kInt8, ...
  Pattern pattern_;         // kNpuFmt, kNchwFmt, ...
  Acc acc_;                 // 定点位置信息 {exp, decimal, exp_bias}
  uint32_t addr_;           // 分配后的物理地址
  MemSpace mem_space_;      // kL1, kDDR, kNull
  uint32_t malloc_size_;    // 分配大小

  // 硬件相关 stride 信息
  uint32_t line_size_, line_stride_, patch_size_, patch_stride_;
};
```

- `Tensor` = 图中流动的特征图数据（类比 LLVM 中 `Instruction` 产出的 `Value`）
- `Value<ValueT>` = 静态参数（权重/bias/LUT），存储在 Operator 内部，不通过 `NodeArg` 连接

```cpp
// include/aic/base/value.h           —— 权重/参数存储
template <typename ValueT, DataType Kind>
class Value : public ValueBase {
  vector<ValueT> list_;    // 原始权重数据
};
// 别名: Fp16Value = Value<uint16_t, kFp16>
// 用法: conv_op->weight() 返回 Fp16Value，包含所有权重字节
```

### 类比总结表

| LLVM | AIC | 说明 |
|------|-----|------|
| `llvm::Module` | `aic::Module` | 顶层容器 |
| `llvm::Function` | `aic::Graph` | 图的容器 |
| `llvm::BasicBlock` | 拓扑序 `NodeIndex[]` | 执行顺序 |
| `llvm::Instruction` | `aic::Node` | 操作节点 |
| `llvm::Value` | `aic::NodeArg` / `aic::Tensor` | 数据（被 use 的东西） |
| `llvm::Use` | `Node::EdgeEnd` | 边（谁用了谁） |
| 常量 `ConstantInt` | `aic::Value<ValueT>` | 权重/参数 |
| — | `Graph::Resolve()` | 验证 + 拓扑排序 + 建立边 |
| `llvm::Pass` | `aic::ModulePass` | 优化 Pass |

---

## 3. L1 — Operator Graph（算子图，最高层抽象）

### 3.1 `Net`（类比 ONNX Graph，也是 `Graph` 的子类）

```cpp
// include/aic/ir/net.h
class Net : public Graph {
  // 添加算子
  template<class Op> Op& AddOperator(string name);    // Net 特有
  // 获取/创建 Tensor
  Tensor& GetOrCreateTensor(string name);
  // 按索引取 Operator
  Operator* GetOp(NodeIndex index);
};
```

### 3.2 `Operator`（类比 ONNX Node / 高级 `Instruction`）

```cpp
// include/aic/ir/operator.h
class Operator : public Node {
  string device_;     // "npu"（默认部署目标）

  // ★ 核心接口：输出 shape/type 推导
  virtual Status OutputInfer(const NameList& output_name) = 0;
  virtual Status MixPrecisionOutputInfer(...);          // 混合精度推导
};
```

每个具体算子继承 `Operator`，**加自己的属性结构体**：

```cpp
// include/aic/ir/operators/conv2d.h
struct Conv2dAttr {
  uint32_t input_ch, output_ch, group;
  uint32_t pad_h, pad_w, kernel_h, kernel_w;
  uint32_t stride_h, stride_w, dilation_h, dilation_w;
  // ... 30+ 字段
};

class Conv2d : public Operator {
  Conv2dAttr attr_;           // 算子参数
  ValuePtr weight_;           // 权重 (Fp16Value/Uint8Value/...)
  ValuePtr bias_;             // bias
  ValuePtr factor_scale_;    // 量化 scale

  Status OutputInfer(...) override;   // 根据 attr_ 推导输出 shape
};
```

**目前已支持的算子**（`include/aic/ir/operators/` 下有 40+ 个头文件）：

| 分类 | 算子 |
|------|------|
| 卷积类 | Conv2d, ConvTranspose2d, ConvTranspose2d2, LocalConv |
| 归一化 | LayerNorm, RmsNorm, RmsNorm2, InstanceNorm, BatchNorm |
| 激活/数学 | Activation, Eltwise, Exp, Sin, Cos, Inv, LogSoftmax, Softmax |
| 变换 | Permute, Reshape, Slice, Concat, Broadcast, Copy |
| 池化 | Pool2d, Pool2d2, GlobalPool2d |
| 矩阵乘 | Matmul, Matmul2, Fc (FullyConnected) |
| 其他 | Reduce, ReduceExt, ReduceExt2, Argmax, TopK, NMS, Interp, Yuv2rgb, PixelShuffle... |
| 量化 | GptqDequant |

---

## 4. L2 — Kernel Graph（内核图，类比 LLVM IR）

这是 **Lowering Pass** 的产出。`Operator` → `Kernel` 的映射引入硬件概念。

### 4.1 `KernelNet`（类比 LLVM Module 中所有 Function 的集合）

```cpp
// include/aic/ir/kernel_net.h
class KernelNet : public Graph {
  // 按索引取 Kernel
  Kernel* GetKernel(NodeIndex index);
  // 添加 Kernel
  template<class T> T& AddKernel(string name);
  // 获取/创建 Tensor
  Tensor& GetOrCreateTensor(string name);

  // 记录参数打包信息
  KernelNetInfoRecord kernel_net_info_;
  vector<vector<list<char>*>> packed_net_param_;
};
```

### 4.2 `Kernel`（类比 LLVM `Function`——一个独立的可执行单元）

每个 Kernel 是**一个完整的硬件操作单元**，内部包含一个 `HwGraph`（硬件子图）。

```cpp
// target/tensor_brain/include/tensor_brain/kernel.h
class Kernel : public Node {
  unique_ptr<HwGraph> hw_graph_;       // ★ 硬件子图（L2.5 层）
  RegionInfo extra_mem_region_;        // 额外空间（wino 变换等）
  RegionInfo params_mem_region_;       // 参数内存区域
  DynMemInfo kl_mem_info_;            // 动态内存信息
  VpuPipeline vpu_pipeline_;          // VPU 流水线配置
  SplitCascadeInfo split_cascade_info_; // Cascade 拆分信息

  // ★ 核心接口：每个 Kernel 子类必须实现
  virtual Status BuildHwGraphImpl(const NodeIoArgs& args) = 0;
  virtual Status PackedParams();        // 参数打包
  virtual Status AllocateMem();         // 内存分配

  // Cascade 支持
  bool IsStrCascaded();   // Store Cascade（输出级联）
  bool IsLdrCascaded();   // Load Cascade（输入级联）
};
```

**关键理解**：`Kernel` 不是单一指令，而是一个包含多个 `HwLayer` 的微型图。例如 `Conv2dKernel` 的 `HwGraph` 包含：
```
DMA_IN (加载输入) → Conv2D_Layer (计算) → Activation_Layer (融合的激活) → DMA_OUT (写出)
```

**具体 Kernel 示例**（`target/tensor_brain/include/tensor_brain/kernels/` 下）：

| Kernel | 对应 Operator | 内部 HwGraph 典型结构 |
|--------|-------------|---------------------|
| `Conv2dKernel` | Conv2d | DMA_In → Conv → (Act) → DMA_Out |
| `ConvFusionKernel` | 融合后的 Conv | DMA_In → Conv → Act → Pool → DMA_Out |
| `DMADataCopyKernel` | Copy, Reshape | DMA_In → DMA_Out |
| `ConcatKernel` | Concat | DMA_In(s) → (DummyConcat) → DMA_Out |
| `EltwiseKernel` | Eltwise | DMA_In(s) → Eltwise_Layer → DMA_Out |
| `PermuteKernel` | Permute | DMA_In → MTE_Permute → DMA_Out |

### 4.3 `HwGraph`（硬件子图，L2.5）

```cpp
// include/aic/ir/hw_graph.h
class HwGraph : public Graph {
  // 添加硬件层
  template<class Layer> Layer& AddHwLayer(string name);
  // 获取硬件层
  HwLayer* GetHwLayer(NodeIndex index);
  // 代码生成
  Status Codegen();
  // 参数打包
  Status PackedParams();
};
```

### 4.4 `HwLayer`（硬件层，类比 MachineInstruction）

```cpp
// target/tensor_brain/include/tensor_brain/hw_layer.h
class HwLayer : public Node {
  HwLayerType hw_layer_type_;          // kMpu0Layer, kMpu1Layer, kVpuLayer, kDmaLayer...
  InstSync inst_sync_;                 // 硬件同步信号 set/clr
  unique_ptr<HwLayerInfoRecord> hw_layer_info_record_; // 生成的指令
  list<char> packed_params_;           // 打包的参数（权重/bias 字节流）

  // Cascade 配置
  unordered_map<uint32_t, Cascade> cascade_ldr_mp_;
  Cascade cascade_str_;

  // ★ 核心接口
  virtual Status Codegen() = 0;             // 生成指令
  virtual Status SatisfyHardwareConstrain(); // 硬件约束检查
  virtual void CodegenSyncInst() = 0;       // 生成同步指令
  virtual bool SupportCascadeLdr/Str();      // 是否支持级联

  // In-place / Dummy / 地址
  bool IsDummy();
  virtual bool SupportInplace();
  Status InplaceAddrCheck();
};
```

**具体 HwLayer 类型**（`target/tensor_brain/include/tensor_brain/hw_layers/` 下大量子类）：

| 目录 | 包含的 HwLayer |
|------|---------------|
| `mpu/` | Conv2dLayer, Conv2dFusionLayer, EltwiseLayer, BilinearInterpLayer, Pool2d2Layer... |
| `vpu/` | EltwiseLayer, NMSLayer, ActivationLayer, SoftmaxLayer, ReduceLayer... |
| `dma/` | NPU_DMA_In, NPU_DMA_Out, NPU_DMA_For_ParamDataFetch |
| `dummy/` | DummyConcatLayer, DummySliceLayer |
| `mte/` | PermuteLayer, SliceLayer, InterpLayer |

---

## 5. L3 — Analysis Graph（分析图，类比 Schedule IR / 后端 IR）

### 5.1 `AnalyseGraph`（全局硬件执行图）

```cpp
// include/aic/ir/analyse_graph.h
class AnalyseGraph : public Graph {
  // ★ 核心：order ↔ node 的双向映射（执行顺序，不是拓扑序！）
  map<uint32_t, AnalyseNode*> order_to_node_;    // 执行序号 → 节点
  map<AnalyseNode*, uint32_t> node_to_order_;    // 节点 → 执行序号
  // 按 HwLayer 类型分组
  array<vector<AnalyseNode*>, kHwLayerTypeMax> nodes_order_of_type_;

  // 按顺序添加（不同于拓扑序，这是确定的执行顺序）
  AnalyseNode& AddAnalyseNode(string name);                // 追加到末尾
  AnalyseNode& InsertAnalyseNodeAfter(uint32_t idx, ...);  // 插入到指定位置后
  AnalyseNode& InsertAnalyseNodeBefore(uint32_t idx, ...); // 插入到指定位置前

  Status Update();  // Resolve + 分类
};
```

**关键区别**：`AnalyseGraph` 的节点顺序是**确定的执行顺序**（硬件流水线顺序），不是 Graph 的拓扑序。`BuildAnalyseGraph` Pass 负责将分散在多个 Kernel 的 `HwGraph` 拼接成这一个全局图。

### 5.2 `AnalyseNode`（分析节点，封装 HwLayer）

```cpp
// include/aic/ir/analyse_node.h
class AnalyseNode : public Node {
  HwLayer* hw_layer_;            // ★ 指向实际硬件层
  MemAllocateFlag mem_flag_;     // 内存分配标记

  // 委托给 HwLayer
  bool IsDummy();
  bool IsDummySlice();
  bool IsDummyConcat();
  bool IsIODmaInNode();
  bool IsIODmaOutNode();
  bool IsStrCascaded();
  bool IsLdrCascaded();

  // In-place
  bool SupportInplace();
};
```

**`AnalyseNode` 是对 `HwLayer` 的薄封装**，加上了执行顺序号和内存分配标记。它让 HwLayer 可以参与全局分析（同步插入、内存分配、Cascade 判断），而不修改 HwLayer 本身的代码。

---

## 6. 辅助基础设施

### 6.1 `GraphManager`

```cpp
// include/aic/graph/graph_manager.h
class GraphManager {
  // 创建图（Net, KernelNet, HwGraph, AnalyseGraph 等）
  template<class G> G* Create(string name);
  // 获取当前活跃的图
  Graph* GraphPtr();
};
```

### 6.2 `GraphViewer`（只读拓扑视图）

```cpp
// include/aic/graph/graph_viewer.h
class GraphViewer {
  const vector<NodeIndex>& GetNodesInTopologicalOrder();  // 拓扑序遍历
  GraphViewer(Graph& g);  // 构造时触发 Resolve
};
```

### 6.3 `TargetMachine`

```cpp
// include/aic/target_support/target_machine.h
class TargetMachine {
  // 指令集信息
  // 内存规格（L1 大小、DDR 带宽）
  // Op→Kernel 转换器
};
```

### 6.4 `MCInstr`（机器指令）

```cpp
// include/aic/machine_code/mcinstr.h
class MCInstr {
  // 一条硬件指令（opcode + operands）
  // HwLayer::Codegen() 产生 MCInstr
  // 最终序列化为二进制
};
```

---

## 7. 一张图总结：从 JSON 到指令的完整数据流

```
                          Module
                            │
                   ┌────────┼────────┐
                   │        │        │
              GraphManager  │   FileManager
                   │        │
          ┌────────┼────────┼────────┐
          │        │        │        │
         Net   KernelNet  HwGraph  AnalyseGraph
       (L1 IR)  (L2 IR)  (L2.5)   (L3 IR)
          │        │        │        │
          ▼        ▼        ▼        ▼
   ┌─────────┐ ┌───────┐ ┌───────┐ ┌──────────┐
   │Operator │ │Kernel │ │HwLayer│ │AnalyseNode│
   │(Node)   │ │(Node) │ │(Node) │ │(Node)     │
   │         │ │       │ │       │ │  └─HwLayer*│
   │+ attr   │ │+HwGrph│ │+Codegen│ │  └─MemFlag │
   │+ weight │ │+Cascad│ │+Sync  │ │  └─OrderNo │
   └────┬────┘ └───┬───┘ └───┬───┘ └─────┬─────┘
        │          │         │            │
   ┌────▼────┐     │         │            │
   │ Tensor  │◄────┼─────────┼────────────┘
   │(NodeArg)│     │         │
   │ NCHW    │     │         │
   └─────────┘     │         │
                   │         │
   ┌───────────┐   │         │
   │ Value<T>  │   │         │
   │ (权重/bias)│  │         │
   └───────────┘   │         │
                   │         │
                   ▼         ▼
               ┌──────────────────┐
               │    MCInstr       │
               │ (机器指令 + 操作数)│
               └──────────────────┘
                       │
                       ▼
                  .o 文件 (二进制指令)
                data.json (tensor 元信息)
```

---

## 8. 阅读建议

| 优先级 | 文件 | 内容 |
|--------|------|------|
| ⭐⭐⭐ | `include/aic/graph/graph.h` | Graph 基类（Node 容器 + 边 + Resolve） |
| ⭐⭐⭐ | `include/aic/graph/node.h` | Node 基类（input/output defs + edge 遍历） |
| ⭐⭐⭐ | `include/aic/base/tensor.h` | Tensor（4D + addr + stride） |
| ⭐⭐⭐ | `include/aic/ir/operator.h` | Operator 基类 |
| ⭐⭐ | `include/aic/ir/operators/conv2d.h` | 一个具体 Operator 的完整示例 |
| ⭐⭐ | `target/.../kernels/conv2d.h` | 一个具体 Kernel 的完整示例 |
| ⭐⭐ | `target/.../hw_layer.h` | HwLayer 基类 |
| ⭐⭐ | `include/aic/ir/analyse_graph.h` | AnalyseGraph（order-to-node 映射） |
| ⭐⭐ | `include/aic/ir/analyse_node.h` | AnalyseNode（HwLayer 的包装） |
| ⭐ | `include/aic/ir/module.h` | Module（顶层入口） |
| ⭐ | `include/aic/ir/hw_graph.h` | HwGraph（Kernel 内部的子图） |

> 建议阅读路径：**Tensor → Node → Operator(Conv2d) → Graph → Net → Kernel → HwLayer → AnalyseNode → AnalyseGraph**
