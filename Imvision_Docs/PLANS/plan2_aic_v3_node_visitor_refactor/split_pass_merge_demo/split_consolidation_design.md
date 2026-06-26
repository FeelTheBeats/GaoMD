# Split Pass 合并重构设计

> Visitor 模式试点应用。将分散的 `complex_op_split_*.cpp` 合并为一个 `ComplexOpSplit` pass，通过 Visitor 动态分发。

---

## 一、目标

将以下 8 个独立 pass 合并为 1 个：

| 当前文件 | 当前类 | 分发类型 |
|---------|--------|---------|
| `complex_op_split_exp.cpp` | ExpSplit | Exp |
| `complex_op_split_inv.cpp` | InvSplit | Inv（含 InvSqrt） |
| `complex_op_split_softmax.cpp` | SoftmaxSplit | Softmax |
| `complex_op_split_basenorm.cpp` | NormSplit | BaseNorm（LayerNorm/RMSNorm/InstanceNorm） |
| `complex_op_lower_logsoftmax.cpp` | LowerLogSoftmax | LogSoftmax |
| `complex_op_split_matmul.cpp` | MatmulSplit | Matmul |
| `complex_op_split_conv_transpose2d.cpp` | ConvTranspose2dSplit | ConvTranspose2d |
| `complex_op_split_conv_transpose2d2.cpp` | ConvTranspose2d2Split | ConvTranspose2d2 |

---

## 二、新文件与类

**文件**：`src/transforms/complex_op_split.cpp`

**类**：`ComplexOpSplit : public ModulePass`

**Visitor**：`SplitVisitor : public NodeVisitor`

---

## 三、代码结构

### 3.1 类骨架

```cpp
// src/transforms/complex_op_split.cpp

class ComplexOpSplit : public ModulePass {
 public:
  void Show() const override { TLOG_I("using %s Pass!\n", "ComplexOpSplit"); }
  common::Status RunOnModule(Module& mod) override;
};

// ===== Visitor：将类型分发到不同的拆分函数 =====
class SplitVisitor : public NodeVisitor {
 public:
  SplitVisitor(Net* net, BatchRewriter& rewriter)
      : net_(net), rewriter_(rewriter) {}

  void Visit(Exp& op) override              { ExpSplitImpl(net_, &op); }
  void Visit(Inv& op) override;             // 按 mode 分派 InvSplit 或 InvSqrtSplit
  void Visit(Softmax& op) override;         // 按 SatisfySplitC 分派 channel-split 或标准
  void Visit(BaseNorm& op) override;        // 按 NormType 分派 LayerNorm/InstanceNorm/RMSNorm
  void Visit(LogSoftmax& op) override;      // 按 SatisfySplitC 分派
  void Visit(Matmul& op) override;          // ConvertMatmul
  void Visit(ConvTranspose2d& op) override;
  void Visit(ConvTranspose2d2& op) override;

 private:
  Net* net_;
  BatchRewriter& rewriter_;
};
```

### 3.2 RunOnModule

```cpp
Status ComplexOpSplit::RunOnModule(Module& mod) {
  Net* net = dynamic_cast<Net*>(mod.GetGraphManager()->GraphPtr());
  if (!net) { return FAIL; }

  auto pattern = PatternBuilder("ComplexOpSplit")
      .MatchNode("op", [](const Node& n) {
          return CastNoCheck<const Exp>(&n) ||
                 CastNoCheck<const Inv>(&n) ||
                 CastNoCheck<const Softmax>(&n) ||
                 CastNoCheck<const BaseNorm>(&n) ||
                 CastNoCheck<const LogSoftmax>(&n) ||
                 CastNoCheck<const Matmul>(&n) ||
                 CastNoCheck<const ConvTranspose2d>(&n) ||
                 CastNoCheck<const ConvTranspose2d2>(&n);
      })
      .Build();

  BatchRewriter rewriter(*net);
  SplitVisitor visitor(net, rewriter);

  for (auto& match : PatternMatcher(*net).Match(pattern)) {
    auto* op = net->GetOp(match.nodes.at("op"));
    if (!op) continue;
    op->Accept(visitor);  // double dispatch → 自动路由到正确的 Visit 重载
    rewriter.RemoveNode(op->Index());
  }

  return rewriter.Commit();
}
```

---

## 四、迁移方式

### 4.1 Impl 函数：挪过来，不改逻辑

每个原有 pass 的 Impl 函数（如 `ExpSplitImpl`、`DoSplitSoftmax`、`LoweringLogSoftmax`）**整体搬入** `complex_op_split.cpp`，作为静态函数或 SplitVisitor 的私有方法。函数体一行不改。

### 4.2 MatmulSplit 特殊处理

`MergePermuteMatmul` 阶段是子图匹配（`Permute→Matmul`），与 Split 分发无关，**单独保留在 `complex_op_split_matmul.cpp`**，不作为 `ComplexOpSplit` 的一部分。

### 4.3 旧的 pass 注册删除

8 个 `PM_REGISTER_PASS` 删除，替换为 1 个：

```cpp
PM_REGISTER_PASS(ModulePassRegistry, ComplexOpSplit, "ComplexOpSplit");
```

原文件名保留不动（避免破坏 git 历史），内容清空或留注释。

---

## 五、收益

| 维度 | 旧 | 新 |
|------|----|------|
| 文件数 | 8 | 1（+ 1 个 Matmul 残余） |
| PM_REGISTER 数 | 8 | 1 |
| 类型分发方式 | 各自手写 `for + dynamic_cast` | 统一 `node->Accept(visitor)` |
| 新加 Split 类型 | 新建文件 + 注册 | 在 `SplitVisitor` 加一个 `Visit` + 在 `MatchNode` lambda 加一行类型 |
| 公共 helper 复用 | 各自 include `common_func.h` | 同一文件内可直接复用 |
