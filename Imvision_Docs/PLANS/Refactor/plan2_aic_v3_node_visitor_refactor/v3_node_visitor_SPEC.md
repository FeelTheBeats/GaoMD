> — Seven Gao

# v3 编译器多层 IR 的 Node 访问者模式重构

---

## 目录
  - [1. 问题场景](#1-问题场景)
  - [2. 意义](#2-意义)
  - [3. 整体设计](#3-整体设计)
    - [3.1. 设计思想（痛点 + 解决思路）](#31-设计思想)
    - [3.2. 支持场景](#32-支持场景)
    - [3.3. 整体流程](#33-整体流程)
    - [3.4. 子模块列表](#34-子模块列表)
  - [4. 数据结构](#4-数据结构)
    - [4.1. Node 基类](#41-node-基类新增)
    - [4.2. NodeVisitor 接口](#42-nodevisitor-接口新建)
    - [4.3. HwVisitor 接口](#43-hwvisitor-接口新建)
    - [4.4. HwLayer 基类](#44-hwlayer-基类新增)
    - [4.5. AnalyseNode Wrapper](#45-analysenode-wrapper新增)
  - [5. 子模块设计](#5-子模块设计)
  - [6. 新 Pass 开发方式](#6-新-pass-开发方式)
  - [7. 向后兼容策略](#7-向后兼容策略)
  - [8. 验证](#8-验证)

---

## 1. 问题场景

### 1.1. 场景整理

AIC 编译器有三层 IR（Operator / Kernel / AnalyseGraph），每个 pass 都需要遍历图节点，对特定类型的节点做处理。当前类型分发模式：

```cpp
// 模式 1：GraphViewer + dynamic_cast（L1/L2 pass 通用模式）
for (auto idx : graph_viewer.GetNodesInTopologicalOrder()) {
    auto* op = net->GetOp(idx);
    if (auto* exp = dynamic_cast<Exp*>(op)) { /* 处理 Exp */ }
    else if (auto* softmax = dynamic_cast<Softmax*>(op)) { /* 处理 Softmax */ }
    else if (...) { }
}

// 模式 2：order_to_node + GetHwLayer + dynamic_cast（L3 pass 通用模式）
for (auto& [order, node] : order_to_node) {
    auto* hw = node->GetHwLayer();
    if (auto* conv = dynamic_cast<Conv2dLayer*>(hw)) { /* Cascade 分析 */ }
    else if (auto* elt = dynamic_cast<EltwiseLayer*>(hw)) { /* Cascade 分析 */ }
}
```

全仓统计：
- 32 个 Operator + Kernel pass 中有 **53 处** `dynamic_cast`
- 42 个 Operator 子类中，~15 个被 pass 分发
- 17 个 Kernel 子类中，~6 个被 pass 分发
- 40 个 HwLayer 子类中，~5 个被 L3 pass 分发

**核心问题**：类型分发逻辑分散在全仓，新增 Operator 类型时无法在编译期发现哪些 pass 遗漏了处理。

---

## 2. 意义

- **类型分发与业务逻辑解耦**：`Node` 子类不再感知自身被哪些 pass 处理——每个子类只需实现一次 `Accept` 路由，所有 pass 通过 Visitor 接口以 `Visit(T&)` 重载的形式集中管理对同一类型的处理逻辑。类型分发从分散在 53 处 `dynamic_cast` 收敛到 `NodeVisitor::Visit` 的 16 个重载声明中。

- **类型安全访问**：以 `node->Accept(visitor)` 的编译期重载决议替代运行时的 `dynamic_cast`。调用方不再需要手动恢复 `Node*` 的具体类型，路由由虚函数自动完成。

- **操作可无限扩展**：类体系（42 个 Operator、17 个 Kernel、40 个 HwLayer）保持稳定，新增 pass 只需创建新的 Visitor 子类并 override 关心的 `Visit` 方法，无需修改任何 Node 子类的代码。

---

## 3. 整体设计

### 3.1. 设计思想

#### 痛点问题

1. **类型安全缺失**：`dynamic_cast` 失败静默跳过——如果 pass 忘记处理某个类型，不会编译报错，只在运行时暴露（且可能表现为静默错误行为）
2. **分发逻辑分散**：53 处 `dynamic_cast` 写在各自的 `.cpp` 中，无集中管理和统一入口。每个 pass 都在重复"遍历图 → 恢复类型 → 分发"的样板代码
3. **L3 分发穿透**：`AnalyseNode` 包裹 `HwLayer*`，pass 需要先取 `GetHwLayer()` 再 `dynamic_cast`，两步类型恢复

#### 解决思路

**双层 Visitor + AnalyseNode Wrapper**：`NodeVisitor` 覆盖 L1+L2（16 个 Visit），`HwVisitor` 覆盖 L3（11 个 Visit）。`AnalyseNode` 通过 `Accept(HwVisitor&)` 路由穿透到内部的 `HwLayer*`。

**与 PatternMatcher 的关系**：PatternMatcher 负责"在图里找到目标模式"（子图匹配），Visitor 负责"对找到的节点执行操作"（类型分发）。两者互补，不是替代。

### 3.2. 支持场景

| 场景 | 旧方案 | 新方案 |
|------|--------|--------|
| 单节点类型分发 | `dynamic_cast<T*>` 链 | `node->Accept(visitor)` 自动路由 |
| 多节点子图匹配 | PatternMatcher | PatternMatcher（不变） |
| L3 HwLayer 分发 | `node->GetHwLayer()` + `dynamic_cast` | `node->Accept(hwVisitor)` 自动穿透 |
| 新类型默认行为 | 静默跳过（不报错） | `Visit(Node&)` fallback（可定制编译报错） |
| 新增 Operator 子类 | 改 pass 的 if/else 链 | 补一行 `Accept` override + 各 Visitor 加 `Visit` 重载 |

### 3.3. 整体流程

**L1/L2（NodeVisitor）**：

```
node->Accept(nodeVisitor)
  ├─ Exp::Accept(v) override             → v.Visit(Exp&) ——→ Pass 处理
  ├─ Conv2dKernel::Accept(v) override    → v.Visit(Conv2dKernel&) ——→ Pass 处理
  └─ BatchNorm::Accept(v)  (未 override) → Node::Accept(v) → v.Visit(Node&) → 跳过
```

**L3（HwVisitor + Wrapper）**：

```
node->Accept(hwVisitor)                  // node 是 AnalyseNode*
  → AnalyseNode::Accept(hwVisitor)       // Wrapper，不调 v.Visit(AnalyseNode&)
    → hw_layer_->Accept(hwVisitor)       // 穿透到 HwLayer
      → Conv2dLayer::Accept(v) override  → v.Visit(Conv2dLayer&) ——→ Pass 处理
      → EltwiseLayer::Accept(v) override → v.Visit(EltwiseLayer&) ——→ Pass 处理
```

### 3.4. 子模块列表

| 模块 | 文件 | 说明 |
|------|------|------|
| Node 基类 | `include/aic/graph/node.h` | 新增 `Accept(NodeVisitor&)` |
| NodeVisitor 接口 | `include/aic/transforms/node_visitor.h` | 新建，16 个 Visit 方法 |
| HwVisitor 接口 | `include/aic/transforms/hw_visitor.h` | 新建，11 个 Visit 方法 |
| L1 Operator | `include/aic/ir/operators/*.h` (45 个文件) | 每个子类加 `Accept` override |
| L2 Kernel | `target/.../kernels/*.h` (26 个文件) | 每个子类加 `Accept` override |
| L3 HwLayer 基类 | `target/.../hw_layer.h` | 新增 `Accept(HwVisitor&)` |
| L3 HwLayer 子类 | `target/.../hw_layers/*/*.h` (39 个文件) | 每个子类加 `Accept` override |
| L3 Wrapper | `include/aic/ir/analyse_node.h` | 新增 `Accept(HwVisitor&)` 路由方法 |

---

## 4. 数据结构

### 4.1. Node 基类（新增）

```cpp
// node.h
class NodeVisitor;  // 前置声明，避免循环依赖

class Node {
 public:
  /** Visitor pattern: accept a visitor and dispatch to the correct Visit() overload. */
  virtual void Accept(NodeVisitor& v) { v.Visit(*this); }  // 默认实现，非纯虚
};
```

**设计决策**：使用默认实现而非纯虚函数（`= 0`）。理由：
- 纯虚函数 → 所有 Operator/Kernel 子类**必须**全部 override，否则编译失败，强制一次性迁移
- 默认实现 → 未 override 的子类可编译，走到 `v.Visit(Node&)`（空实现 fallback），支持渐进迁移

**编译依赖**：因 `Accept` 是 inline 方法且调用了 `v.Visit(*this)`，`node.h` 必须 include `node_visitor.h`，不能仅用前置声明。反向则只需前置声明（`node_visitor.h` 中 `Visit(Node&)` 只用引用，无需 `node.h` 完整定义），避免了循环依赖。

### 4.2. NodeVisitor 接口（新建）

```cpp
// node_visitor.h
class NodeVisitor {
 public:
  virtual ~NodeVisitor() = default;

  /** 默认 fallback：未处理的类型静默跳过。 */
  virtual void Visit(Node& n) {}

  // === L1 Operator（13 个） ===
  virtual void Visit(Exp& op)              {}
  virtual void Visit(Inv& op)              {}
  virtual void Visit(Sin& op)              {}
  virtual void Visit(Cos& op)              {}
  virtual void Visit(Softmax& op)          {}
  virtual void Visit(LogSoftmax& op)       {}
  virtual void Visit(BaseNorm& op)         {}
  virtual void Visit(LayerNorm& op)        {}
  virtual void Visit(ConvTranspose2d& op)  {}
  virtual void Visit(ConvTranspose2d2& op) {}
  virtual void Visit(Matmul& op)           {}
  virtual void Visit(Permute& op)          {}
  virtual void Visit(Reshape& op)          {}

  // === L2 Kernel（3 个） ===
  virtual void Visit(Conv2dKernel& k)      {}
  virtual void Visit(EltwiseKernel& k)     {}
  virtual void Visit(Pool2dKernel& k)      {}
};
```

**设计决策**：只包含当前被 pass 实际分发的 16 个类型。
- 未列入的类型（BatchNorm、Activation、Eltwise、Slice、Concat 等）不需要从 `Node*` 恢复具体类型——它们总是在创建后立即使用，调用方手持的是具体类引用。
- 新增分发需求时，只需在 `NodeVisitor` 中加一行 `virtual void Visit(FooOp&) {}`，对应子类的 `Accept` 已事先覆盖。

**编译依赖**：所有方法默认实现为空 `{}`，无需包含具体类型的头文件，仅需前置声明。不能使用 `static_cast<Node&>(op)` 等需要完整类型定义的表达式——前置声明下 `static_cast` 无法验证继承链。

### 4.3. HwVisitor 接口（新建）

```cpp
// hw_visitor.h
class HwVisitor {
 public:
  virtual ~HwVisitor() = default;

  virtual void Visit(HwLayer& l) {}

  // === 叶子类型 ===
  virtual void Visit(Conv2dLayer& l)       {}
  virtual void Visit(Conv2dFusionLayer& l) {}
  virtual void Visit(EltwiseLayer& l)      {}
  virtual void Visit(Pool2d2Layer& l)      {}
  virtual void Visit(SliceLayer& l)        {}

  // === 中间基类（pass 可按粒度选择 override） ===
  virtual void Visit(Mpu& l)               {}
  virtual void Visit(Vpu& l)               {}
  virtual void Visit(Dma& l)               {}
  virtual void Visit(Mte& l)               {}
  virtual void Visit(Spu& l)               {}
};
```

**设计决策**：**与 NodeVisitor 分离**，不合一。两层关心的类型集合完全不重叠（Operator vs HwLayer）。合并会让接口臃肿。

**中间基类 Visit**：支持 pass 按粒度选择——如果 pass 只关心"这是 MPU 操作"而不区分 Conv2d vs ConvFusion，可只 override `Visit(Mpu&)`。

### 4.4. HwLayer 基类（新增）

```cpp
// hw_layer.h
class HwVisitor;  // 前置声明

class HwLayer : public Node {
 public:
  /** Visitor for L3 passes. Separate overload from Node::Accept(NodeVisitor&). */
  virtual void Accept(HwVisitor& v) { v.Visit(*this); }
};
```

**设计决策**：`Accept(HwVisitor&)` 是新的重载方法，不与 `Node::Accept(NodeVisitor&)` 冲突。C++ 根据 visitor 类型自动选择。

### 4.5. AnalyseNode Wrapper（新增）

```cpp
// analyse_node.h
class AnalyseNode : public Node {
  HwLayer* hw_layer_ = nullptr;
 public:
  /** Wrapper: route HwVisitor to the underlying HwLayer. */
  void Accept(HwVisitor& v) {
    if (hw_layer_) hw_layer_->Accept(v);
    // 穿透！不调 v.Visit(AnalyseNode&)
  }
};
```

**设计决策**：`AnalyseNode` 不做类型分发，只做**路由**。因为真正的多态行为在 `HwLayer*` 上。路由链条：

```
AnalyseNode::Accept(hwVisitor)
  → hw_layer_->Accept(hwVisitor)
    → Conv2dLayer::Accept(hwVisitor)
      → hwVisitor.Visit(Conv2dLayer&)
```

`hw_layer_` 在 `BuildAnalyseGraph` pass 中初始化，早于所有 L3 pass，因此运行时不为空。

---

## 5. 子模块设计

### Operator 子类（45 个文件）

每个子类加一行 override，**覆盖全部 45 个**（含 BatchNorm、Activation 等未分发类型）：

```cpp
class Exp : public Operator {
 public:
  void Accept(NodeVisitor& v) override { v.Visit(*this); }
};
```

**为什么全覆盖而非仅 16 个**：未来新 pass 需要分发未覆盖类型时，无需先补基础设施。

### Kernel 子类（26 个文件）

模式同 Operator。`DmaKernel` 基类不加，仅其叶子类 `DmaInKernel`、`DmaOutKernel` 加。

### HwLayer 子类（39 个文件）

模式同 Operator/Node。中间基类（Mpu、Vpu、Dma、Mte、Spu）也加，支持 pass 按基类粒度分发。

---

## 6. 新 Pass 开发方式

### 旧方式（deprecated，仅保留兼容）

```cpp
class NewPass : public ModulePass {
  Status RunOnModule(Module& mod) override {
    for (auto idx : order) {
      auto* op = net->GetOp(idx);
      if (auto* exp = dynamic_cast<Exp*>(op))       { /* 处理 Exp */ }
      else if (auto* softmax = dynamic_cast<Softmax*>(op)) { /* 处理 Softmax */ }
      else if (...) { }
    }
  }
};
```

### 新方式（Visitor，推荐）

**Step 1**：确认目标类型已在 `NodeVisitor`（或 `HwVisitor`）中声明。如果没有，加一行 `virtual void Visit(FooOp&) {}`。

**Step 2**：创建 Visitor 子类，只 override 关心的类型：

```cpp
class NewPassVisitor : public NodeVisitor {
  Net* net_;
  BatchRewriter& rewriter_;
 public:
  explicit NewPassVisitor(Net* net, BatchRewriter& r)
      : net_(net), rewriter_(r) {}

  void Visit(Exp& e) override {
    // 改写逻辑
    rewriter_.RemoveNode(e.Index());
  }

  void Visit(Softmax& s) override {
    // 改写逻辑
    rewriter_.RemoveNode(s.Index());
  }

  // 其他 40 个类型 → 不 override → 自动 fallback 到 Visit(Node&) → 跳过
};
```

**Step 3**：`RunOnModule` 中遍历图并调用 `Accept`：

```cpp
Status NewPass::RunOnModule(Module& mod) {
  Net* net = dynamic_cast<Net*>(mod.GetGraphManager()->GraphPtr());
  BatchRewriter rewriter(*net);
  NewPassVisitor visitor(net, rewriter);

  for (auto& node : net->Nodes()) {
    node->Accept(visitor);  // 一行，自动路由到正确的 Visit 重载
  }
  return rewriter.Commit();
}
```

### 与旧方式的区别

| | 旧方式 | 新方式 |
|------|--------|--------|
| 类型分发 | 手写 `dynamic_cast` 链 | `Accept` 自动路由 |
| 遗漏类型 | 静默跳过 | `Visit(Node&)` fallback（可定制编译报错） |
| 新增 Operator 类型 | 改所有相关 pass 的 if/else | 加 1 行 Visit 声明 + 各 pass 加 1 个 Visit 重载 |
| 样板代码 | `for + dynamic_cast + if/else` 每个 pass 重复 | `for + Accept` 一行 |

---

## 7. 向后兼容策略

### 渐进迁移

```
Phase 1: 基础设施（已完成）
  → 所有 Accept 方法添加完毕
  → 所有旧 pass 继续用 dynamic_cast，不受影响

Phase 2: 试点迁移
  → SplitExp（L1 单类型）+ Cascade（L3 多类型）
  → 验证两条链路：NodeVisitor + HwVisitor

Phase 3: 渐进推广
  → 新 pass 强制用 Visitor
  → 旧 pass 按需迁移（每次改 pass 时顺手改）
```

### 新旧并存

同一代码仓中以下两种写法可同时存在且互不冲突：

```cpp
// 旧写法（不改的 pass）——继续工作
auto* exp = dynamic_cast<Exp*>(net->GetOp(idx));
if (exp) { ExpSplitImpl(net, exp); }

// 新写法（已迁移的 pass）——新增路径
ExpSplitVisitor visitor(net, rewriter);
net->GetOp(idx)->Accept(visitor);
```

### Accept 默认实现 vs 纯虚函数

使用**默认实现**（非纯虚）：
- 不 override 的子类可编译
- 未 override 时走到 `v.Visit(Node&)`（空实现，等价于跳过）
- 支持渐进迁移（不强制一次性改完）

---

## 8. 验证

- 门禁测试（CI pipeline）
- 编译验证（所有头文件可独立 include，无循环依赖）
- 已修改文件：115 个，新增行数 ~256 行
- 已有 pass 行为不变：所有动态类型分发逻辑未改动
