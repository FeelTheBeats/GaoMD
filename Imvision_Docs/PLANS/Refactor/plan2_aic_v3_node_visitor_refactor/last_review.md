# Visitor 模式重构 Split Pass —— Code Review 文档

> 基于 commit `401ee6da` + `bf1baeea`，将 10 个独立 split pass 合并为 1 个 ComplexOpSplit + 1 个 SplitVisitor。

---

## 目录

- [Pre_Ques](#pre_ques)
  - [什么是 Visitor 模式？](#什么是-visitor-模式)
  - [NodeIR 为什么适配 Visitor 模式？](#nodeir-为什么适配-visitor-模式)
  - [有什么好处？](#有什么好处)
- [怎么使用 NodeIR 的 Visitor 模式？](#怎么使用-nodeir-的-visitor-模式)
  - [步骤 1：定义 Visitor](#步骤-1定义-visitor)
  - [步骤 2：在 pass 中调用](#步骤-2在-pass-中调用)
- [demo重构](#demo重构)
  - [涉及文件](#涉及文件)
  - [最终目录结构](#最终目录结构)
  - [demo-结语](#demo-结语)
- [关键设计决策](#关键设计决策)
- [是否还有优化空间](#是否还有优化空间)
- [附件](#附件)

---
## Pre_Ques
### 什么是 Visitor 模式？

Visitor 是一种行为设计模式，核心机制是 **Double Dispatch（双重分派-重载是编译期的limit）**：

1. **第一跳**：调用 `node->Accept(visitor)`，虚函数还原出子类的静态类型
2. **第二跳**：`Accept` 内部调用 `visitor.Visit(*this)`，编译器根据 `*this` 的静态类型精确匹配到对应的 `Visit` 重载

```
你的代码： op->Accept(visitor)
             │
             ▼ 虚函数表（第一跳）
  Exp::Accept(v)    →    v.Visit(Exp&)       ← 重载决议（第二跳）
  Inv::Accept(v)    →    v.Visit(Inv&)
  Softmax::Accept(v)→    v.Visit(Softmax&)
  BaseNorm::Accept(v)→   v.Visit(BaseNorm&)
```

关键是：`dynamic_cast` 从你的代码中消失了 —— 编译器替你做类型判断。

---

### NodeIR 为什么适配 Visitor 模式？

三个条件全部满足：

1. **类型层次清晰**：`Node → Operator → 45+ 具体 Op 类型`，继承树深且宽
2. **按类型分派是高频操作**：10 个 split pass 都在做 `dynamic_cast<Xxx*>(node) → 调用 impl`，这是 Visitor 最擅长消除的模式
3. **每类 Accept 只需一行代码**：`void Accept(NodeVisitor& v) override { v.Visit(*this); }`，改造成本约等于零

---

### 有什么好处？

| | 旧方式（10 个独立 pass） | Visitor 方式（1 个 pass） |
|---|---|---|
| 分派机制 | `dynamic_cast<Exp*>(node)` 手动判断 | `node->Accept(v)` → 虚函数表自动路由 |
| 未处理类型 | `if (nullptr) continue` 跳过 | 默认 `Visit(Node&)` 空操作，自动跳过 |
| 新增 split 类型成本 | 新建 .cpp + pass 类 + 注册 + main.cpp 加一行 | SplitVisitor 加一个 `Visit` 重载 + 一条 `#include` |
| 类型安全 | 运行时 `dynamic_cast`，误写类型编译不报 | 编译期：没重载 `Visit(Xxx&)` 就 fallthrough 到默认 no-op |
| 样板代码 | 每个 pass 重复：GraphViewer + for + CastNoCheck + nullptr 检查 + GetOutputEdgesCount + ReleaseNode + PM_REGISTER_PASS | 这套代码只写一次，放在 ComplexOpSplit 和 SplitVisitor 里 |
| 结构 | 匹配、分派、改写全混在 RunOnModule 里 | PatternMatcher 管匹配、Visitor 管分派、impl 函数管改写——三层分离 |
| 复用性 | impl 函数的 `static` 必须去掉才能被其他 pass 调用 | impl 函数通过 `#include` 头文件对外公开，SplitVisitor 可被其他 pass 复用 |

> **关于代码量**：impl 函数体未变，删除的是 ~300 行样板代码（10 个 RunOnModule + extern 声明 + PASS_DEFINITION + PM_REGISTER_PASS），新增 ~350 行（11 个头文件 + SplitVisitor + ComplexOpSplit 新 pass 类）。净行数变化不大。
>
> **关于图遍历**：原来 10 个 pass 各遍历一次和现在 PatternMatcher 一次遍历，检查的节点 × 类型总量相同，没有"10 倍变 1 倍"的性能提升。重构的核心收益不是性能，是结构：**类型的判断从你的手写 `dynamic_cast` 挪给了编译器的虚函数表。**

---

## 怎么使用 NodeIR 的 Visitor 模式？

### 步骤 1：定义 Visitor(头文件实现Visit分派到不同pass主流程的逻辑，.cpp只负责进行判断和visit调用)

```cpp
#include "aic/transforms/node_visitor.h"

class SplitVisitor : public NodeVisitor {
 public:
  SplitVisitor(Net* net, BatchRewriter& rewriter)
      : net_(net), rewriter_(rewriter) {}

  void Visit(Exp& op) override {
    auto s = ExpSplitImpl(net_, &op);
    if (!s.IsOK()) RecordError("Exp", op.name(), s);
    rewriter_.RemoveNode(op.Index());
  }
  // ... 每个关心的类型一个 Visit 重载

  bool HasError() const { return !first_error_.IsOK(); }
  common::Status GetFirstError() const { return first_error_; }

 private:
  Net* net_;
  BatchRewriter& rewriter_;
  common::Status first_error_;
};
```

### 步骤 2：在 pass 中调用

```cpp
Status ComplexOpSplit::RunOnModule(Module& mod) {
  Net* net = dynamic_cast<Net*>(mod.GetGraphManager()->GraphPtr());

  auto pattern = PatternBuilder("ComplexOpSplit")
      .MatchNode("op", [](const Node& n) -> bool {
          return CastNoCheck<const Exp>(&n) ||
                 CastNoCheck<const Inv>(&n) ||
                 /* ... 11 种类型 */;
      })
      .Build();

  BatchRewriter rewriter(*net);
  SplitVisitor visitor(net, rewriter);

  for (auto& match : PatternMatcher(*net).Match(pattern)) {
    auto* op = net->GetOp(match.nodes.at("op"));
    if (!op) continue;
    op->Accept(visitor);   // ← 这一行替代了 dynamic_cast + if-continue + 函数调用
    if (visitor.HasError()) break;
  }

  if (visitor.HasError()) return visitor.GetFirstError();
  return rewriter.Commit();
}
```

**多个pass变一组pass，一个Visitor，因此只有一个主入口(runOnModule)**

---

## demo重构

### 涉及文件

| 类别 | 数量 | 说明 |
|------|------|------|
| 新建头文件 | 11 | 10 个 impl 头文件 + `split_visitor.h`，位于 `include/aic/transforms/split_op/` |
| 重写 | 1 | `src/transforms/split_op/complex_op_split.cpp` |
| 修改 .cpp | 10 | 移除 RunOnModule / PM_REGISTER_PASS / ReleaseNode+Resolve |
| 修改配置 | 2 | `main.cpp`（10 行 → 1 行）、`passes.h`（删除 10 行 PASS_DEFINITION） |
| 新增独立头文件 | 1 | `include/aic/ir/operators/bn_info.h`（BNInfo 提取） |

### 最终目录结构

```
include/aic/transforms/split_op/
├── split_visitor.h                  ← SplitVisitor 类
├── complex_op_split_exp.h            ← ExpSplitImpl 声明
├── complex_op_split_inv.h            ← InvSplitImpl / InvSqrtSplitImpl 声明
├── complex_op_split_softmax.h        ← DoSplitSoftmax / SoftmaxSplitChannel 声明
├── complex_op_lower_logsoftmax.h     ← LoweringLogSoftmax / LogSoftmaxSplitChannel 声明
├── complex_op_split_basenorm.h       ← LayerNormImpl / RMSNormImpl / InstanNormImpl 声明
├── complex_op_split_matmul.h         ← ConvertMatmul / MergePermuteMatmul 声明
├── complex_op_split_conv_transpose2d.h   ← SplitConvTranspose2d 声明
├── complex_op_split_conv_transpose2d2.h  ← SplitConvTranspose2d2 声明
├── complex_op_split_sin_cos.h        ← ExpandSinOp / ExpandCosOp 声明
└── complex_op_split_yuv2rgb.h        ← TransformToConcatConv2d / TransformToConv2dAdd 声明

src/transforms/split_op/
├── complex_op_split.cpp              ← ComplexOpSplit pass 类
├── complex_op_split_exp.cpp
├── ... (10 个 impl .cpp)
└── complex_op_split_yuv2rgb.cpp
```

### demo-结语
原来项目中存在 10 个独立的 Split Pass，它们的主体流程几乎完全一致：遍历图、判断节点类型、调用对应 SplitImpl、删除节点并提交修改，只是处理的 Op 类型不同。因此我将每个 Pass 的改写逻辑保留为独立的 Impl 函数，并抽离公共流程，合并为一个 ComplexOpSplit Pass。与此同时，我删除了旧 Pass 的 RunOnModule、注册代码以及其他重复样板，将 Impl 接口声明到头文件供统一调度。

在新的架构中，ComplexOpSplit 只负责使用 PatternMatcher 筛选需要处理的节点，然后调用 op->Accept(visitor)。Accept 利用虚函数完成第一次分派，根据节点真实类型进入对应子类的 Accept；随后 Accept 内部调用 visitor.Visit(*this)，编译器依据 *this 的静态类型完成第二次分派，自动路由到对应的 Visit(Exp&)、Visit(Inv&) 等重载，由这些 Visit 再调用对应的 SplitImpl 完成改写。整个过程中，原先大量的 dynamic_cast + if 判断都由 Visitor 的双重分派机制替代，使匹配、分派和改写三个职责完全解耦。

---

## 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| Impl 函数整理策略 | extern → `#include` 头文件 | 编译期签名检查，extern 是链接期才炸 |
| SplitVisitor 放置 | 独立 `split_visitor.h` | dispatch 层与编排层分离，可复用 |
| 旧 pass 类处理 | 全部删除（PASS_DEFINITION + RunOnModule + PM_REGISTER_PASS） | 死代码是负债 |
| 错误处理 | `RecordError()` 记录首个错误，`RunOnModule` 提前退出 | 替代原来的 `(void)` 静默丢弃 |
| 节点移除策略 | impl 函数不再自行 `ReleaseNode`，统一由 `BatchRewriter::Commit()` 处理 | 消除双重移除风险 |
| 头文件位置 | `include/aic/transforms/split_op/` | 与项目现有 include 惯例一致 |
| Pipeline 注册 | 10 个独立 pass → 1 个 `ComplexOpSplit` | main.cpp 意图清晰，消除 10 次重复图遍历 |

---

## 是否还有优化空间

1. Accept 可以用宏消除手误。现在 45+ 个 Op 类型各写一行 Accept，写法完全一致。一旦有人新加 Op 忘了写 Accept，编译不报错、静默 fallthrough 到 Visit(Node&) 空操作，表现就是"这个 Op 没有被 Split 处理"，排查困难。加个宏就解决了：

```cpp
#define AIC_ACCEPT_VISITOR(ClassName) \
  void Accept(NodeVisitor& v) override { v.Visit(*this); }

class Exp : public Operator {
  AIC_ACCEPT_VISITOR(Exp)  // 一行，不会写错
};
```

这不是性能优化，是防呆——让漏写变成编译期可见（或者至少容易 grep）。

2. 10 个 impl 头文件可以再权衡一下粒度。每个头文件只声明 1~2 个函数，目前只有 split_visitor.h 引用它们。如果后续没有第二个 pass 需要单独调用 ExpSplitImpl，这些头文件的"复用价值"只是假设性的。可以考虑合并成 2~3 个更大粒度的头文件（比如 split_expr_ops.h、split_norm_ops.h），减少文件数量但不损失可定位性。

# 附件
![alt text](NodeIRVisitorproc-1.png)