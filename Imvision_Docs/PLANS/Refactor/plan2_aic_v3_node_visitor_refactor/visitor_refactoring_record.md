# Visitor 模式重构记录

> 2026-06-24，Node + Operator + Kernel 层 Visitor 基础设施实施记录。
> 仅涉及基类和类型体系的修改，不涉及具体 pass 迁移。

---

## 一、改动概览

| 类型 | 文件数 | Accept 方法数 | 新增行数 |
|------|--------|:---:|---------|
| 新建 NodeVisitor | 1 | — | 80 |
| 新建 HwVisitor | 1 | — | 55 |
| Node 基类 | 1 | 1 | 2 |
| Operator 子类 | 45 | 45 | 45 |
| Kernel 子类 | 26 | 28 | 28 |
| HwLayer 基类 | 1 | 1 | 2 |
| HwLayer 子类 | 39 | 41 | 41 |
| AnalyseNode | 1 | 1 | 3 |
| **合计** | **115** | **117** | **256** |

> 决策记录 1：最初只给 16 个被 pass 分发的类型加了 Accept，后改为全覆盖。理由：避免未来新 pass 需要分发未覆盖类型时，还要先补基础设施。
>
> 决策记录 2：L3 使用独立的 `HwVisitor`，不合并到 `NodeVisitor`。两层关心的类型集合完全不重叠（Operator vs HwLayer）。AnalyseNode 的 `Accept(HwVisitor&)` 做路由：穿透到 `hw_layer_->Accept(v)`。

---

## 二、新建文件

### `include/aic/transforms/node_visitor.h`

NodeVisitor 接口定义，包含：

- **默认 fallback**：`Visit(Node&)` — 空实现，未 override 的类型自动跳过
- **L1 Operator（13 个）**：Exp, Inv, Sin, Cos, Softmax, LogSoftmax, BaseNorm, LayerNorm, ConvTranspose2d, ConvTranspose2d2, Matmul, Permute, Reshape
- **L2 Kernel（3 个）**：Conv2dKernel, EltwiseKernel, Pool2dKernel

**设计要点**：每个 Visit 方法的默认实现委托到 `Visit(Node&)`，形成两级 fallback：

```
Visit(Exp&) override → 具体处理
Visit(Exp&) 未 override → Visit(Node&) → 空实现（跳过）
```

---

## 三、修改文件

### 3.1 Node 基类（`include/aic/graph/node.h`）

```diff
+ class NodeVisitor;  // 前置声明

  class Node {
+   virtual void Accept(NodeVisitor& v) { v.Visit(*this); }
  };
```

- 使用**默认实现**而非纯虚函数 → 不 override 的子类仍可编译
- 未 override 时走到 `v.Visit(Node&)`（默认空实现，等价于跳过）

### 3.2 Operator 子类（45 个文件，全覆盖）

所有 Operator 子类均添加 `Accept` override。通过 `sed` 脚本在 `TypeString() const override` 后插入：

```cpp
std::string TypeString() const override { return "XXX"; }
+ void Accept(NodeVisitor& v) override { v.Visit(*this); }
```

**基类未 override**：`Operator` 本身不加 Accept——它是中间层，分发粒度在叶子类。

### 3.3 Kernel 子类（26 个文件，全覆盖）

所有 Kernel 子类均添加 `Accept` override。Kernel 类没有统一的 `TypeString()`，`Accept` 加在析构函数之后：

```cpp
~XXXKernel() = default;
+ void Accept(NodeVisitor& v) override { v.Visit(*this); }
```

**特殊处理**：
- `dma.h` 含 3 个类：`DmaKernel`（基类，不加 Accept），`DmaInKernel`、`DmaOutKernel`（各加 1 行）
- `param_data_fetch_kernel.h`：析构函数前缀 `virtual`，sed 未命中，手动补

**基类未 override**：`Kernel`、`DmaKernel` 等中间基类不加 Accept——分发粒度在叶子类。

---

## 五、编译影响

- **无 ABI 断裂**：`Accept` 是新增虚函数，添加在已有虚函数表末尾，不影响已有函数偏移
- **无行为变化**：所有现有代码不调用 `Accept`，行为完全不变
- **头文件依赖**：`node_visitor.h` 只做前置声明 + 虚方法声明，不引入新的编译依赖

---

## 六、设计意图：不只替代 dynamic_cast

Visitor 常被简化为"避免手写 dynamic_cast"——这只是一个副作用。**真正的价值是在不修改类的前提下添加新操作。**

### 当前现状

每加一个 pass，就是在新的 `.cpp` 文件里写 `dynamic_cast<Exp*>` 链。Exp 类不需要改，但类型分发逻辑分散在全仓，没有编译期检查"哪个类型被遗漏了"。

### Visitor 后

```cpp
// 新 pass = 一个 Visitor 子类，不会修改 Exp.h
class CompressLutVisitor : public NodeVisitor {
  void Visit(Exp& e) override {
    e.Shift_Bn();  // 直接调 Exp 公开方法，和 dynamic_cast 后一样
  }
  // 其他 41 个类型 → 默认 fallback 跳过，不需要写 else if
};
```

- **Exp 类不知道有这个 pass 存在**
- **每个新的优化操作 = 一个独立的 Visitor 子类**
- **类体系稳定（42 个 Operator 几年不变），但 pass 数量可以无限增长**

这就是 "add operations without modifying classes"——类体系和操作集合的演进解耦。

### Visitor 换了什么、没换什么

| 换了 | 没换 |
|------|------|
| `dynamic_cast<T*>` 拿引用 | 类方法调用方式（`e.Shift_Bn()` 不变） |
| 遗漏类型的静默跳过 → 可选的编译报错 | 类本身的公开接口 |
| 类型分发位置（从 pass 分散 → Visitor 接口集中） | 图遍历方式（PatternMatcher 继续用） |

---

## 七、下一步

当前改动是**纯基础设施**——铺好了轨道但没有火车。下一步是：

1. **试点 pass 迁移**：选 SplitExp 验证 `NodeVisitor` 链路
2. **L3 Wrapper**：`HwVisitor` + `HwLayer::Accept` + `AnalyseNode::Accept(HwVisitor&)`（Alan 说的 wrapper）
3. **渐进推广**：新 pass 强制用 Visitor，旧 pass 按需迁移

---

## 八、编译问题踩坑

### 坑 1：`static_cast` 到基类需要完整类型定义

`node_visitor.h` 中 Kernel 类型的默认实现最初为：

```cpp
virtual void Visit(Conv2dKernel& k) { Visit(static_cast<Node&>(k)); }
```

编译失败：`invalid static_cast from 'Conv2dKernel' to 'Node&'`，`Conv2dKernel` 是 incomplete type。

**原因**：`node_visitor.h` 只有 `class Conv2dKernel;` 前置声明。`static_cast` 做继承链类型转换时，编译器必须看到两个类型的完整定义来验证转换合法性。

**修复**：默认实现改为空 `{}`。语义正确：不 override 就应该什么都不做。

**教训**：头文件中只有前置声明的类型，inline 方法体只能是 `{}`——不能做 `static_cast`、方法调用、`sizeof` 等依赖完整类型的操作。

### 坑 2：inline 方法调用外部类方法需要完整定义

`node.h` 中 `Accept` 是 inline 的，调用了 `v.Visit(*this)`。但 `node.h` 只有 `class NodeVisitor;` 前置声明。任何 include `node.h` 但不经过 operator 头文件的 `.cpp`（如 `parallel_base_on_type.cpp`）都会因看不到 `NodeVisitor::Visit()` 声明而编译失败。

**修复**：`node.h` 直接 `#include "aic/transforms/node_visitor.h"`。`node_visitor.h` 只做前置声明不 include `node.h`，无循环依赖。

**教训**：`A.h` 的 inline 方法调 `B.h` 的类 → `A.h` 必须 include `B.h`。前置声明不够。被调用方可以用前置声明做反向引用。
