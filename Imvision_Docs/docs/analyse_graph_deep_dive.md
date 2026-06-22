# AnalyseGraph 深度解析

> AnalyseGraph 是什么？它基于什么数据结构？为什么内存和同步都建立在它之上？它和 KernelNet 是什么关系？

---

## 1. 一句话定义

**AnalyseGraph 是一个以 `map<uint32_t, AnalyseNode*>`（执行序号 → 节点）为核心索引的 `Graph` 子类，它把散落在各 Kernel 内部 `HwGraph` 中的 `HwLayer` 按硬件执行顺序拼接成一张全局图。**

---

## 2. 基于什么数据结构

### 2.1 继承链

```
Graph  ←── AnalyseGraph
  │            │
  │            ├── map<uint32_t, AnalyseNode*> order_to_node_   ★ 核心新增
  │            ├── map<AnalyseNode*, uint32_t> node_to_order_   ★ 反向索引
  │            └── array<vector<AnalyseNode*>> nodes_order_of_type_  (按 HwLayerType 分组)
  │
  ├── vector<unique_ptr<Node>> nodes_          (继承自 Graph)
  ├── unordered_map<string, NodeIndex> node_name_to_idx_  (继承)
  ├── unordered_map<string, unique_ptr<NodeArg>> node_args_  (继承)
  ├── 边关系 (继承)
  └── 拓扑序 (继承)
```

### 2.2 关键新增：`order_to_node_`

```cpp
// include/aic/ir/analyse_graph.h
class AnalyseGraph : public Graph {
 private:
  uint32_t node_cnt_ = 0;
  std::map<uint32_t, AnalyseNode *> order_to_node_;       // ★ 执行序号 → 节点
  std::map<AnalyseNode *, uint32_t> node_to_order_;       // ★ 节点 → 执行序号
  std::array<std::vector<AnalyseNode *>, kHwLayerTypeMax> nodes_order_of_type_;
};
```

**这不是拓扑序，是确定的硬件执行顺序**：

```
order_to_node_:
  0 → NPU_DMA_IN_Layer  (加载第1个Conv的输入)
  1 → Conv2d_Layer      (第1个Conv计算)
  2 → NPU_DMA_OUT_Layer (写出第1个Conv的结果)
  3 → NPU_DMA_IN_Layer  (加载第2个Conv的输入)
  4 → Conv2d_Layer      (第2个Conv计算)
  5 → Activation_Layer  (激活)
  6 → NPU_DMA_OUT_Layer (写出最终结果)
  ...
```

**为什么不能复用 Graph 的拓扑序？**

```
Graph 的拓扑序:
  DMA_In_A → Conv_A → DMA_Out_A → DMA_In_B → Conv_B → DMA_Out_B
                           ↘                            ↗
                           DMA_In_C → Conv_C → DMA_Out_C
  
  可能有多个合法拓扑序:
    A→B→C  或  A→C→B  或  B→A→C  ...

  AnalyseGraph 的执行序:
    只有一种：硬件指令的执行顺序
    order_to_node_[0], order_to_node_[1], order_to_node_[2], ...
    这个顺序决定了物理内存的分配和同步信号的时序
```

### 2.3 节点类型：AnalyseNode

```cpp
// include/aic/ir/analyse_node.h
class AnalyseNode : public Node {
  HwLayer* hw_layer_;            // ★ 指向实际的硬件层
  MemAllocateFlag mem_flag_;     // 内存分配标记（In-place/Cascade 等）
  bool del_hwlayer_manul_ = false;
  bool is_swap_out = false;

  // 所有硬件相关查询，全部委托给 HwLayer：
  bool IsDummy();
  bool IsDummySlice();
  bool IsDummyConcat();
  bool IsIODmaInNode();
  bool IsIODmaOutNode();
  bool IsStrCascaded();       // Store Cascade（输出留在 L1）
  bool IsLdrCascaded();       // Load Cascade（输入已在 L1）
  bool SupportInplace();
};
```

**AnalyseNode 是对 HwLayer 的包装**——加上了 Graph 节点能力（输入/输出 NodeArg、边关系）、执行序号和内存标记。HwLayer 本身只关心硬件指令生成，AnalyseNode 让它能参与全局图分析。

### 2.4 关键插入操作

```cpp
// 追加到末尾（常规添加）
AnalyseNode& AddAnalyseNode(string name);

// 插入到指定序号之后（用于 DMA_In 在消费者之前、DMA_Out 在生产者之后）
AnalyseNode& InsertAnalyseNodeAfter(uint32_t idx, string name);

// 插入到指定序号之前
AnalyseNode& InsertAnalyseNodeBefore(uint32_t idx, string name);
```

这些插入操作会**自动维护 order_to_node_ 和 node_to_order_ 的一致性**。

---

## 3. AnalyseGraph 是怎么构建的——和 KernelNet 的关系

### 3.1 构建前的状态

```
KernelNet (按拓扑序排列):
  ┌─────────────────────┐
  │ Conv2dKernel        │  Kernel[0]
  │  └─ HwGraph:        │
  │     DMA_In ──→ Conv2d_Layer ──→ DMA_Out
  ├─────────────────────┤
  │ ActivationKernel    │  Kernel[1]  ← 消费 Kernel[0] 的输出
  │  └─ HwGraph:        │
  │     DMA_In ──→ Act_Layer ──→ DMA_Out
  ├─────────────────────┤
  │ EltwiseKernel       │  Kernel[2]  ← 消费 Kernel[0] 和 Kernel[1] 的输出
  │  └─ HwGraph:        │
  │     DMA_In ──→ DMA_In ──→ Eltwise_Layer ──→ DMA_Out
  └─────────────────────┘

每个 Kernel 有自己的 HwGraph（独立的微型图）
HwGraph 之间彼此不知道对方的存在
```

### 3.2 构建过程

```cpp
// build_analyse_graph_pass.cpp:916
Status BuildAnalyseGraph::RunOnModule(Module &mod) {
  KernelNet *net = dynamic_cast<KernelNet *>(mod.GetGraphManager()->GraphPtr());

  auto analyse_graph = pass_result_.graph;

  // 1. 按 KernelNet 的拓扑序遍历每个 Kernel
  auto kernel_order = GraphViewer(*net).GetNodesInTopologicalOrder();

  for (auto idx : kernel_order) {
    Kernel *source_kernel = net->GetKernel(idx);

    // 2. 尝试用预设的 Pattern 匹配（如 Conv+Act 融合模式、Cascade 模式）
    //    如果匹配成功，按 Pattern 的方式插入 HwLayer
    if (ApplyAnalysePatternOnce(source_kernel, ...).IsOK()) continue;

    // 3. Pattern 不匹配：逐个插入 Kernel 的 HwGraph 中的 HwLayer
    HwGraph &hw_graph = source_kernel->HwGraphRef();
    for (auto hw_idx : hw_graph 拓扑序) {
      HwLayer *hw_layer = hw_graph.GetHwLayer(hw_idx);

      // 特殊处理：根据 HwLayer 类型决定插入位置
      if (IsDummySliceLayer || IsDMA_In):
        InsertHwLayerBeforeFirstUse(...)   // 插入到消费者之前
      else if (IsDMA_Out || IsDummyConcat):
        InsertHwLayerAfterLastInput(...)   // 插入到生产者之后
      else:
        InsertHwLayer(...)                 // 直接追加到末尾
    }
  }

  // 4. 最终 Resolve：验证 DAG、建立边、更新 order_to_node_
  analyse_graph->Update();
}
```

### 3.3 构建后的状态

```
AnalyseGraph (按硬件执行序排列):
  order_to_node_:
    0 → NPU_DMA_IN_Layer    ← 加载 input_image 到 L1
    1 → Conv2d_Layer        ← 卷积计算（来自 Kernel[0].HwGraph）
    2 → NPU_DMA_OUT_Layer   ← 写回 DDR（来自 Kernel[0].HwGraph）
    3 → NPU_DMA_IN_Layer    ← 加载 conv_out 到 L1（来自 Kernel[1].HwGraph）
    4 → Activation_Layer    ← 激活计算（来自 Kernel[1].HwGraph）
    5 → NPU_DMA_OUT_Layer   ← 写回 DDR（来自 Kernel[1].HwGraph）
    6 → NPU_DMA_IN_Layer    ← 加载 conv_out（来自 Kernel[2].HwGraph 第一个输入）
    7 → NPU_DMA_IN_Layer    ← 加载 act_out（来自 Kernel[2].HwGraph 第二个输入）
    8 → Eltwise_Layer       ← 逐元素相加（来自 Kernel[2].HwGraph）
    9 → NPU_DMA_OUT_Layer   ← 写回 DDR（来自 Kernel[2].HwGraph）

全局边:
  0→1→2
  2→3 (conv_out 的 DMA_Out 连到下一个 DMA_In)
  3→4→5
  5→6 (act_out 的 DMA_Out 连到 Eltwise 的第一个 DMA_In)
  5→7 (act_out 也连到 Eltwise 的第二个 DMA_In)
  6→8, 7→8→9
```

---

## 4. 为什么内存和同步基于 AnalyseGraph

### 4.1 内存分配需要什么？

```
MemAlloc / HwLayerMemAlloc / LiveTimeAnalyse 的核心问题：

  问题1: tensor_A 和 tensor_B 能否复用同一块 L1？
    → 需要知道它们各自的"生"时刻和"死"时刻
    → 只有执行序（order_to_node_）能精确回答

  问题2: tensor 应该分配在 L1 还是 DDR？
    → 需要知道 Cascade 状态
    → Cascade Pass 操作的就是 AnalyseGraph

  问题3: DMA_Out 的源 tensor 是否还能被复用？
    → 需要遍历所有消费者
    → AnalyseGraph 的边关系给出了完整的消费链
```

**举例：生命周期分析**

```cpp
// livetime_analyse.cpp 核心逻辑（简化）
for (auto& [order, node] : graph->GetOrderToNodeMap()) {
  for (auto* in_tensor : node->Inputs()) {
    // ★ 用 order 标记这个 tensor 的最后一次被使用时刻
    in_tensor->GetLiveTime().UpdateEnd(order);  // "死亡时刻" = 当前执行序号
  }
  for (auto* out_tensor : node->Outputs()) {
    // ★ 用 order 标记这个 tensor 的产生时刻
    out_tensor->GetLiveTime().SetBirth(order);  // "出生时刻" = 当前执行序号
  }
}

// 然后：两个 tensor 生命周期不重叠 → 可以复用同一块内存
// tensor_A.LiveTime: birth=2, end=5
// tensor_B.LiveTime: birth=6, end=9
// → 不重叠，B 可以复用 A 的内存
```

如果只有拓扑序，`order` 是不确定的，生命周期分析就不可靠。

### 4.2 同步插入需要什么？

```cpp
// insert_sync_pass.cpp 核心逻辑（简化）
for (auto& [order, node] : graph->GetOrderToNodeMap()) {
  HwLayer* cur = node->GetHwLayer();

  // 检查当前 HwLayer 和前序 HwLayer 的依赖关系
  for (auto& pred_edge : node->GetRelationships().input_edges) {
    AnalyseNode* pred = order_to_node_[pred_edge.in_order];

    // ★ 关键判断：前驱是 MPU 计算层，当前是 VPU 向量层？
    //    需要插入 sync set（前驱完成时发信号）
    //              sync clr（当前层执行前等信号）
    if (pred->GetHwLayerType() == kMpu0Layer &&
        cur->GetHwLayerType() == kVpuLayer) {
      pred->GetHwLayer()->InstSyncSet(cur->GetHwLayer());
      cur->GetHwLayer()->InstSyncClr(pred->GetHwLayer());
    }
  }
}
```

同步插入需要精确知道**前后两个 HwLayer 的硬件类型和执行顺序**。这只有 AnalyseGraph 能提供。

### 4.3 Cascade 需要什么？

```cpp
// cascade_pass.cpp 核心逻辑（简化）
for (auto& [order, node] : graph->GetOrderToNodeMap()) {
  // 遍历连续的 HwLayer
  // 判断条件：前驱的输出只有当前一个消费者？
  //           前驱输出的大小 ≤ L1 剩余空间？
  //           前后两层硬件兼容 Cascade？
  if (CanCascade(prev_node, cur_node)) {
    // ★ 级联：prev 的 DMA_Out 变成写 L1，cur 的 DMA_In 变成读 L1
    prev_node->CascadeStrSet({.is_cascade = true});
    cur_node->GetHwLayer()->AddCascadeLdrInfo(0, {.is_cascade = true});
  }
}
```

Cascade 需要在**连续的 HwLayer 之间**判断级联条件。这个"连续"就是 `order_to_node_` 中相邻的节点。

---

## 5. KernelNet 与 AnalyseGraph 的关系

### 5.1 对比

| 维度 | KernelNet | AnalyseGraph |
|------|-----------|--------------|
| **节点类型** | Kernel（内核） | AnalyseNode（包装 HwLayer*） |
| **粒度** | 粗：一个 Kernel ≈ 3-5 个 HwLayer | 细：一个 AnalyseNode = 一个 HwLayer |
| **节点数量** | 几十到几百个 Kernel | 几百到上千个 HwLayer |
| **顺序含义** | 拓扑序（计算依赖） | 执行序（硬件指令发射顺序） |
| **构建方式** | Lowering Pass 逐个创建 | BuildAnalyseGraph 从每个 Kernel.HwGraph 中提取并拼接 |
| **内部结构** | 每个 Kernel 内含一个 HwGraph | 不含子图，是扁平全局图 |
| **用于** | 融合/消冗/权重压缩等 Kernel 级优化 | 内存分配/同步/Cascade/Codegen 等硬件级操作 |

### 5.2 关系

```
KernelNet                     AnalyseGraph
  │                              │
  ├─ Kernel[0]                   │
  │   └─ HwGraph                 │
  │       ├─ DMA_In   ─────────────→ AnalyseNode[0]
  │       ├─ Conv_Layer ───────────→ AnalyseNode[1]
  │       └─ DMA_Out  ─────────────→ AnalyseNode[2]
  │                              │
  ├─ Kernel[1]                   │
  │   └─ HwGraph                 │
  │       ├─ DMA_In   ─────────────→ AnalyseNode[3]
  │       ├─ Act_Layer ────────────→ AnalyseNode[4]
  │       └─ DMA_Out  ─────────────→ AnalyseNode[5]
  │                              │
  └─ Kernel[2]                   │
      └─ HwGraph                 │
          ├─ DMA_In   ─────────────→ AnalyseNode[6]
          ├─ DMA_In   ─────────────→ AnalyseNode[7]
          ├─ Eltwise  ─────────────→ AnalyseNode[8]
          └─ DMA_Out  ─────────────→ AnalyseNode[9]
                                 │
                HwLayer* 指针指向同一对象(不拷贝)
```

**关键点**：

1. **AnalyseNode 不拷贝 HwLayer**，而是持有指针 `HwLayer* hw_layer_`。同一个 HwLayer 对象同时存在于 Kernel 的 HwGraph 和 AnalyseGraph 中。

2. **BuildAnalyseGraph 是 "展开 + 拼接"**：把每个 Kernel 内部的 HwGraph 展开为 HwLayer 序列，然后按拓扑序 + 特殊规则（DMA_In 插入消费者之前，DMA_Out 插入生产者之后）拼成全局执行序。

3. **AnalyseGraph 建立跨 Kernel 的边**：KernelNet 只有 Kernel 之间的边（粗粒度），AnalyseGraph 建立 HwLayer 之间的边（细粒度）。比如 Kernel[0] 的 DMA_Out 输出 → Kernel[1] 的 DMA_In 输入，这条边在 AnalyseGraph 中才被显式建立。

---

## 6. 总结：为什么需要 AnalyseGraph？

```
问题：为什么不直接在 KernelNet 上做内存分配和同步？

答案：因为 KernelNet 的信息粒度不够。

┌─────────────────────────────────────────────────────────┐
│  需要的信息              KernelNet 有吗?   AnalyseGraph 有吗? │
├─────────────────────────────────────────────────────────┤
│  全局硬件执行顺序          ❌ 只有拓扑序     ✅ order_to_node │
│  HwLayer 级粒度           ❌ 粒度是 Kernel   ✅ 粒度是 HwLayer │
│  HwLayer 间跨 Kernel 边   ❌ 只有 Kernel 边 ✅ 细粒度全局边    │
│  每条指令的执行序号        ❌               ✅ node_to_order  │
│  硬件单元类型 (MPU/VPU)    ❌               ✅ HwLayerType    │
│  Cascade 状态 (L1/DDR)    ❌ (只有标记)     ✅ 全局级联判断    │
│  In-place 可行性          ❌ 粒度太粗       ✅ HwLayer 级复用  │
│  tensor 精确生命周期      ❌               ✅ 基于执行序号    │
└─────────────────────────────────────────────────────────┘
```

**一句话**：KernelNet 告诉你"要算什么"，AnalyseGraph 告诉你"每条指令的精确执行顺序和硬件单元分配"。内存分配、同步插入、Cascade 优化都需要第二个信息。
