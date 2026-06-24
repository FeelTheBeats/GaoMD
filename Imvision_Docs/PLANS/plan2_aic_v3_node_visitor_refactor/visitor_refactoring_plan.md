# AIC Visitor 模式重构方案

> 2026-06-23，基于 aic_v3 代码仓实际数据。覆盖 Node / Operator / Kernel / AnalyseGraph（Wrapper）四层设计。

---

## 一、当前状态

### 1.1 继承树

```
Node (371行, 3个虚函数)
├── Operator (L1, 42个子类)
│   ├── Exp, Softmax, Conv2d, BatchNorm, Eltwise, ...
│   └── ...
└── Kernel   (L2, 17个子类)
    ├── Conv2dKernel, EltwiseKernel, Pool2dKernel, ...
    └── DmaKernel → DmaInKernel, DmaOutKernel
```

```
HwLayer (独立继承树, ~40个叶子类)
├── Mpu  → Conv2dLayer, Conv2dFusionLayer, MatmulLayer, ...
├── Vpu  → EltwiseLayer, ActivationLayer, ...
├── Mte  → PermuteLayer, SliceLayer, ConcatLayer, ...
├── Dma  → NpuDmaIn, NpuDmaOut, ...
└── Spu  → ...
```

```
AnalyseNode (L3, 继承 Node)
└── HwLayer* hw_layer_  (1:1 绑定)
    ├── order_ (执行序号)
    └── MemAllocateFlag
```

### 1.2 当前类型分发模式

| 层 | 匹配 | 改写 |
|----|------|------|
| L1 | `PatternMatcher(p).Match()` 或 `dynamic_cast<T*>` | `dynamic_cast<T*>` + 直接访问属性 |
| L2 | `dynamic_cast<T*>` | `dynamic_cast<T*>` + 直接访问属性 |
| L3 | 遍历 `order_to_node` | `node->GetHwLayer()` → `dynamic_cast<T*>` + 访问方法 |

**53 处** `dynamic_cast` 在 pass 代码中。

---

## 二、设计：Visitor 类体系

### 2.1 定义两个 Visitor 接口

```cpp
// ===== 图节点层 Visitor（L1 + L2） =====
class NodeVisitor {
 public:
  virtual ~NodeVisitor() = default;

  // L1 Operator 层 —— 42 个
  virtual void Visit(Exp& op)            {}
  virtual void Visit(Softmax& op)        {}
  virtual void Visit(Conv2d& op)         {}
  virtual void Visit(BatchNorm& op)      {}
  virtual void Visit(Eltwise& op)        {}
  // ... 按需添加，默认空实现
};

// ===== 硬件层 Visitor（L3） =====
class HwVisitor {
 public:
  virtual ~HwVisitor() = default;

  virtual void Visit(Conv2dLayer& l)     {}
  virtual void Visit(Conv2dFusionLayer& l) {}
  virtual void Visit(EltwiseLayer& l)    {}
  virtual void Visit(Pool2d2Layer& l)    {}
  virtual void Visit(SliceLayer& l)      {}
  virtual void Visit(Mpu& l)             {}   // 中间基类，需要时 override
  // ...
};
```

### 2.2 为什么不合并？

L1/L2 的 Node 是算子层（软件语义：拆算子、Lowering、融合），L3 的 HwLayer 是硬件层（硬件语义：Cascade、MemAlloc、Sync）。两层关心的类型集合完全不重叠。用两个 Visitor 保持接口精简，每个 pass 只实现自己关心的 `Visit` 重载。

---

## 三、逐层实现

### 3.1 Node 基类

```cpp
// node.h — 只加一行
class Node {
 public:
  virtual void Accept(NodeVisitor& v) { v.Visit(*this); }  // 新增
  // ... 现有接口不变
};
```

### 3.2 L1 Operator

每个子类加一行 override：

```cpp
// exp.h
class Exp : public Operator {
 public:
  void Accept(NodeVisitor& v) override { v.Visit(*this); }
};

// softmax.h, conv2d.h, batchnorm.h ... 42 个文件，每个加一行
```

**为什么每个类都要 override？** C++ 重载决议基于**静态类型**。如果 `Exp` 不 override `Accept`，调用 `expObj.Accept(v)` 时会调 `Operator::Accept` 或 `Node::Accept`，传给 `v.Visit()` 的是 `Node&` 而非 `Exp&`，导致 double dispatch 失败。

### 3.3 L2 Kernel

同 L1：

```cpp
// conv2d_kernel.h
class Conv2dKernel : public Kernel {
 public:
  void Accept(NodeVisitor& v) override { v.Visit(*this); }
};
// 17 个文件，每个加一行
```

### 3.4 L3 AnalyseGraph（Wrapper）

这是 Alan 说的核心设计点。**AnalyseNode 不做类型分发，只做路由。**

```cpp
// ===== HwLayer 基类加 Accept =====
class HwLayer {
 public:
  virtual void Accept(HwVisitor& v) { v.Visit(*this); }
};

// ===== 各 HwLayer 子类 override =====
class Conv2dLayer : public HwLayer {
 public:
  void Accept(HwVisitor& v) override { v.Visit(*this); }
};
// EltwiseLayer, Pool2d2Layer, SliceLayer... L3 实际用到的类型

// ===== AnalyseNode 做路由（Wrapper 核心） =====
class AnalyseNode : public Node {
  HwLayer* hw_layer_ = nullptr;
 public:
  void Accept(HwVisitor& v) {
    if (hw_layer_) hw_layer_->Accept(v);  // ← 穿透！不调 v.Visit(AnalyseNode&)
  }
};
```

**路由链条**：

```
pass: for (auto& [order, node] : order_to_node)
        node->Accept(hwVisitor)                     // node 是 AnalyseNode*
          ↓
AnalyseNode::Accept(HwVisitor& v)
          ↓
hw_layer_->Accept(v)                                // 穿透 AnalyseNode
          ↓
Conv2dLayer::Accept(HwVisitor& v)                   // 具体 HwLayer 子类
          ↓
v.Visit(static_cast<Conv2dLayer&>(*this))            // double dispatch
          ↓
CascadeVisitor::Visit(Conv2dLayer& conv) { ... }    // 业务逻辑
```

**AnalyseNode 不参与 `NodeVisitor`**——它走的是 `HwVisitor`。如果需要把 L3 也纳入统一的 `NodeVisitor`，可以加一个 `Accept(NodeVisitor&)` 的重载，但那会混合两层语义。建议保持分离。

---

## 四、pass 改写示例

### 4.1 L1 当前写法 vs Visitor

```cpp
// 当前
for (auto idx : order) {
    auto* op = net->GetOp(idx);
    if (auto* exp = dynamic_cast<Exp*>(op)) {
        ExpSplitImpl(net, exp);
    } else if (auto* softmax = dynamic_cast<Softmax*>(op)) {
        SoftmaxSplitImpl(net, softmax);
    }
    // ...
}

// Visitor 后
ExpSplitVisitor visitor(net);
for (auto idx : order) {
    net->GetOp(idx)->Accept(visitor);  // 一行，自动路由
}
```

### 4.2 L3 当前写法 vs Visitor（Wrapper）

```cpp
// 当前
for (auto& [order, node] : order_to_node) {
    auto* hw = node->GetHwLayer();
    if (auto* conv = dynamic_cast<Conv2dLayer*>(hw)) {
        // 级联分析...
    } else if (auto* elt = dynamic_cast<EltwiseLayer*>(hw)) {
        // 级联分析...
    }
}

// Visitor 后
CascadeVisitor visitor;
for (auto& [order, node] : order_to_node) {
    node->Accept(visitor);  // AnalyseNode::Accept → HwLayer::Accept → Visit(Conv2dLayer&)
}
```

---

## 五、可行性分析

### 5.1 技术可行性

| 维度 | 评估 | 说明 |
|------|------|------|
| Node::Accept | ✅ 可行 | 基类加一个纯虚函数，影响所有子类但改动极小 |
| Operator 42 个子类 | ✅ 可行 | 每个加一行 override，机械操作 |
| Kernel 17 个子类 | ✅ 可行 | 同上 |
| HwLayer Accept 体系 | ✅ 可行 | 独立于 Node，互不干扰 |
| AnalyseNode Wrapper | ✅ 可行 | 不改变现有 1:1 绑定关系，只在运行时多一层函数调用 |
| 与 PatternMatcher 兼容 | ✅ 不冲突 | Visitor 替代改写层的 dynamic_cast，PatternMatcher 继续做匹配 |
| 现有 pass 兼容 | ✅ 渐进式 | 旧 pass 不改也能继续用 dynamic_cast，新 pass 逐步迁移 |

### 5.2 不可行/风险点

| 风险 | 应对 |
|------|------|
| HwLayer 中间基类多（Mpu/Vpu/Dma/Mte/Spu） | Visit 方法可接受基类引用；pass 可只 override 基类的 Visit |
| 部分 pass 不按类型分发（如内存分配器按执行序处理） | 不强制改，Visitor 不影响这些 pass |
| `Accept` 调用增加一次虚函数间接跳转 | 热路径影响可忽略（pass 运行在编译期，非推理时） |

---

## 六、工作量估算

### 6.1 改动文件数

| 改动 | 文件数 | 每文件改动量 | 总代码量 |
|------|--------|------------|---------|
| `node.h` 加 `Accept` | 1 | 1 行 | 1 行 |
| `NodeVisitor` 接口定义 | 1（新建） | ~50 行 | 50 行 |
| `HwVisitor` 接口定义 | 1（新建） | ~20 行 | 20 行 |
| L1 Operator 子类加 `Accept` | 42 | 每文件 1 行 | 42 行 |
| L2 Kernel 子类加 `Accept` | 17 | 每文件 1 行 | 17 行 |
| L3 `HwLayer` + 关键子类加 `Accept` | ~10 | 每文件 1 行 | 10 行 |
| `AnalyseNode` 加 `Accept(HwVisitor&)` | 1 | 5 行 | 5 行 |
| **合计** | **~73 文件** | | **~145 行** |

### 6.2 人力估算

| 阶段 | 耗时 | 说明 |
|------|------|------|
| NodeVisitor / HwVisitor 接口设计 + review | 0.5 天 | 确定 Visit 方法覆盖哪些类型 |
| Node::Accept + 子类 override（脚本批量） | 0.5 天 | 脚本生成 + 逐个验证编译 |
| HwLayer::Accept + AnalyseNode wrapper | 0.5 天 | 手动实现 |
| 选 2~3 个 pass 试点迁移 | 1 天 | 验证方案可行性 |
| 全量 pass 迁移（可选） | 按需 | 可并行、可渐进 |

**总计：2~3 天核心实现 + 按需渐进迁移。**

---

## 七、收益评估

### 7.1 核心收益

| 收益 | 说明 |
|------|------|
| **类型安全** | `dynamic_cast` 失败静默跳过 → 编译期保证所有类型都处理 |
| **新增 Operator 可发现性** | 新增类型忘记改 pass → 当前不报错 → Visitor 后：如果不覆盖默认空实现，至少不会 crash；如果设计为纯虚函数，直接编译报错 |
| **代码一致性** | 消除 53 处手写 `dynamic_cast` 链，统一为 `node->Accept(visitor)` |
| **关注点分离** | 匹配（PatternMatcher）+ 改写（Visitor）两层解耦，各自演进 |

### 7.2 不做什么

- **不替代 PatternMatcher**：匹配逻辑继续用 PatternBuilder DSL
- **不强制迁移旧 pass**：旧代码可以继续用 `dynamic_cast`，和 Visitor 并存
- **不改 L3 不需要类型分发的 pass**：MemAlloc、SyncAnalyse 等不需要 Visitor 的 pass 保持原样

### 7.3 长期价值

Visitor 是编译器基础设施中的"标准配置"——LLVM、MLIR、TVM 都有类似机制。在 AIC 当前阶段（Operator 从 42 个可能继续增长），提前铺好 Visitor 可以避免未来 pass 数量膨胀时 `dynamic_cast` 链失控。

---

## 八、建议实施顺序

```
Phase 1: 基础设施
  1. NodeVisitor 接口定义 + Node::Accept
  2. HwVisitor 接口定义 + HwLayer::Accept + AnalyseNode wrapper
  3. 脚本批量生成 42 Operator + 17 Kernel 的 Accept override

Phase 2: 试点验证
  4. 选 SplitExp（简单单类型）迁移到 Visitor
  5. 选 Cascade（L3 多类型分发）迁移到 Visitor
  6. 编译 + 跑现有测试确认无回归

Phase 3: 渐进推广
  7. 新 pass 强制用 Visitor
  8. 旧 pass 按需迁移（每次改 pass 时顺手改）
```
