# Split Pass 合并重构 —— 2026-06-29 重构与修复总结

> 基于 `401ee6da`（ComplexOpSplit 初始实现）的后续重构，完成 `extern` 胶水代码消除、SplitVisitor 独立、死代码清理、及多个边界问题修复。

---

## 一、背景

`401ee6da` 将 10 个独立 split pass 合并为 `ComplexOpSplit`，通过 `SplitVisitor` 分发。但初始实现存在以下临时性设计：

1. **`extern` 声明**堆在 `complex_op_split.cpp` 顶部（30+ 行），跨 TU 无类型检查
2. **`SplitVisitor` 内联**在 pass 文件中，职责不分离
3. **旧 pass 类未清理**：`RunOnModule`、`PM_REGISTER_PASS`、`PASS_DEFINITION` 仍在，造成死代码
4. **`(void)` 丢弃错误返回值**：所有 impl 函数调用结果被静默忽略
5. **节点双重移除**：impl 函数内部做 `ReleaseNode + Resolve`，`SplitVisitor` 又通过 `BatchRewriter` 做一次
6. **Matmul 优化遗漏**：`MergePermuteMatmul` 未被调用

本次重构逐一修复上述问题。

---

## 二、变更总览

### 目录结构（最终态）

```
include/aic/transforms/split_op/   ← 头文件（11 个）
├── split_visitor.h                 ← SplitVisitor 类 + 所有 Visit 方法
├── complex_op_split_exp.h          ← ExpSplitImpl 声明
├── complex_op_split_inv.h          ← InvSplitImpl / InvSqrtSplitImpl 声明
├── complex_op_split_softmax.h      ← DoSplitSoftmax / SoftmaxSplitChannel / SatisfySplitC 声明
├── complex_op_lower_logsoftmax.h   ← LoweringLogSoftmax / LogSoftmaxSplitChannel / SatisfySplitC 声明
├── complex_op_split_basenorm.h     ← LayerNormImpl / RMSNormImpl / InstanNormImpl 声明
├── complex_op_split_matmul.h       ← ConvertMatmul / MergePermuteMatmul 声明
├── complex_op_split_conv_transpose2d.h   ← SplitConvTranspose2d 声明
├── complex_op_split_conv_transpose2d2.h  ← SplitConvTranspose2d2 声明
├── complex_op_split_sin_cos.h      ← ExpandSinOp / ExpandCosOp 声明
└── complex_op_split_yuv2rgb.h      ← TransformToConcatConv2d / TransformToConv2dAdd / UpdateYuv2RgbRefModel 声明

src/transforms/split_op/           ← 实现文件（11 个 .cpp，仅含 impl 函数）
├── complex_op_split.cpp            ← ComplexOpSplit pass 类 + RunOnModule
├── complex_op_split_exp.cpp
├── ...
└── complex_op_split_yuv2rgb.cpp
```

### 涉及文件统计

| 类别 | 数量 | 说明 |
|------|------|------|
| 新建头文件 | 11 | 每个 impl .cpp 一个 .h + `split_visitor.h` |
| 重写 | 1 | `complex_op_split.cpp` |
| 修改 .cpp | 10 | 移除 RunOnModule / PM_REGISTER_PASS / ReleaseNode+Resolve |
| 修改配置 | 2 | `main.cpp`（流水线合并）、`passes.h`（删除 10 行 PASS_DEFINITION） |

---

## 三、逐项变更详述

### 3.1 `extern` → `#include` 头文件

**前**：
```cpp
// complex_op_split.cpp 顶部 30+ 行
extern Status ExpSplitImpl(Net*, Exp*);
extern Status InvSplitImpl(Net*, Inv*);
// ... 共 16 个 extern 声明
```

**后**：
```cpp
// complex_op_split.cpp 只 include 需要的
#include "aic/transforms/split_op/complex_op_split_matmul.h"
#include "aic/transforms/split_op/complex_op_split_yuv2rgb.h"
#include "aic/transforms/split_op/split_visitor.h"
```

每个 impl .cpp 创建对应头文件，使用前向声明 + `common::Status`（不用 `using` 污染命名空间）：
```cpp
// complex_op_split_exp.h
#include "aic/ir/operators/exp.h"
namespace aic {
class Net;
namespace common { class Status; }
common::Status ExpSplitImpl(Net* net, Exp* exp_op);
}
```

**收益**：编译器检验签名一致性，重构不炸链接器。

---

### 3.2 SplitVisitor 独立成文件

从 `complex_op_split.cpp` 抽出 → `include/aic/transforms/split_op/split_visitor.h`

```cpp
class SplitVisitor : public NodeVisitor {
 public:
  SplitVisitor(Net* net, BatchRewriter& rewriter);

  void Visit(Exp& op) override;
  void Visit(Inv& op) override;
  // ... 11 个 Visit 重载

  bool HasError() const;
  common::Status GetFirstError() const;
  bool has_yuv2rgb_conv2dadd_ = false;
 private:
  void RecordError(...);   // 记录首个错误
  Net* net_;
  BatchRewriter& rewriter_;
  common::Status first_error_;
};
```

**收益**：dispatch 层与编排层分离。`SplitVisitor` 可被其他 pass 复用。

---

### 3.3 清理死代码

| 位置 | 删除内容 | 数量 |
|------|---------|------|
| 10 个 impl .cpp | `XXXSplit::RunOnModule()` 方法体 | 10 |
| 10 个 impl .cpp | `PM_REGISTER_PASS(ModulePassRegistry, ...)` | 10 |
| 10 个 impl .cpp | `#include "aic/pm/passes.h"` | 10 |
| `passes.h` | `PASS_DEFINITION(Yuv2rgbSplit/.../InvSplit, ...)` | 10 行 |
| `main.cpp` | `options.enable_pass.push_back("Yuv2rgbSplit")` 等 | 10 行 → 1 行 |

`main.cpp` 最终：
```cpp
options.enable_pass.push_back("ComplexOpSplit");  // 替换原 10 个独立 split pass
```

---

### 3.4 错误处理修复（`(void)` → RecoveryStatus）

**前**：所有 impl 返回值被 `(void)` 丢弃，即使是 `Resolve` 失败也静默继续。

**后**：`SplitVisitor` 在每个 `Visit` 中检查返回值，通过 `RecordError()` 记录首个错误：

```cpp
void Visit(Exp& op) override {
    auto s = ExpSplitImpl(net_, &op);
    if (!s.IsOK()) RecordError("Exp", op.name(), s);
    rewriter_.RemoveNode(op.Index());
}
```

`RunOnModule` 循环中检查 `visitor.HasError()`，遇到错误立即 break 并返回错误 Status。

---

### 3.5 节点双重移除修复

**问题**：7 个 impl 函数（Exp/Inv/Softmax/LogSoftmax/BaseNorm/Yuv2rgb）内部调用 `net->ReleaseNode() + net->Resolve()`，但 `SplitVisitor` 又通过 `rewriter_.RemoveNode()` + `Commit()` 对同一 index 再次 `ReleaseNode`。如果 index 在 impl 的 `Resolve` 后被新节点复用，`Commit()` 会误删新节点。

**修复**：从 7 个 impl 函数中移除内部 `ReleaseNode` + `Resolve`，统一由 `BatchRewriter::Commit()` 管理。

```
ExpSplitImpl:    net->ReleaseNode → return net->Resolve()  →  return Status::OK()
InvSplitImpl:    net->ReleaseNode → return net->Resolve()  →  return Status::OK()
... (共 12 处修改)
```

`Commit()` 在最后一次性释放所有节点 + 一次 `Resolve()`，顺序可预测。

---

### 3.6 Matmul 优化遗漏修复

**问题**：原始 `MatmulSplit::RunOnModule` 调用两个步骤：
1. `MergePermuteMatmul(net)` — 全局合并 permute 到 matmul
2. `PerformMatmulConverison(net)` — 逐个 lowering

但 `SplitVisitor::Visit(Matmul&)` 只调了 `ConvertMatmul`，丢了步骤 1。

**修复**：在 `ComplexOpSplit::RunOnModule` 中 PatternMatcher 循环之前添加：
```cpp
auto merge_status = MergePermuteMatmul(net);
if (!merge_status.IsOK()) { ... return merge_status; }
```

---

### 3.7 Include 路径修正

文件从 `src/transforms/` 移入 `src/transforms/split_op/` 后，相对路径变化：

| 修正 | 文件数 |
|------|--------|
| `"common_func.h"` → `"../common_func.h"` | 5 |
| 补充 `#include "aic/ir/net.h"`（之前由 passes.h 间接引入） | 9 |
| 补充 `#include "aic/graph/graph_cast.h"`（Cast 模板） | 9 |
| 补充 `#include "aic/utils/tlog.h"`（TLOG_E） | 2 |
| 补充 `#include "aic/graph/graph_viewer.h"` | 2 |

---

## 四、调用链（最终态）

```
ComplexOpSplit::RunOnModule(Module& mod)
  │
  ├── MergePermuteMatmul(net)               ← 全局 permute-matmul 合并
  │
  ├── PatternBuilder("ComplexOpSplit")
  │     .MatchNode("op", [](const Node& n)  ← 11 种 Op 类型
  │
  ├── for each match:
  │     op->Accept(visitor)                  ← double-dispatch
  │       └── SplitVisitor::Visit(Xxx& op)
  │             ├── XxxImpl(net_, &op)       ← 调用 impl（头文件声明）
  │             ├── RecordError()            ← 错误追踪
  │             └── rewriter_.RemoveNode()   ← 标记删除
  │
  ├── if visitor.HasError() → return error
  ├── if has_yuv2rgb_conv2dadd_ → UpdateYuv2RgbRefModel(*net)
  └── rewriter.Commit()                      ← 批量 ReleaseNode + 单次 Resolve
```

---

## 五、编译验证

```bash
build.sh -bt Release --no-gtest
[100%] Built target ts_aic    ✅
```

---

## 六、相关 Commit

| Commit | 说明 |
|--------|------|
| `8088fe70` | Visitor 模式基础设施（NodeVisitor 类） |
| `401ee6da` | ComplexOpSplit 初始实现（extern 方式） |
| 本次重构 | extern→include、SplitVisitor 独立、死代码清理、3 项 bug 修复 |
