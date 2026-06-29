# ComplexOpSplit 简单设计说明

> 将 10 个独立 split pass 合并为 1 个，基于 NodeVisitor 类型分发。

---

## 问题

10 个 lowering pass 各自独立注册、各自遍历图、各自做 `dynamic_cast`。结构重复，新增 split 类型需新建文件并注册。

## 解法

1 个 `ComplexOpSplit` pass，内含 `SplitVisitor : public NodeVisitor`。一次图遍历，通过 `node->Accept(visitor)` 自动路由到对应类型的 `Visit` 方法。

## 关键设计决策

| 决策 | 选择 | 理由 |
|------|------|------|
| Impl 函数搬运策略 | extern 转发 | 不复写函数体，零搬运风险，review 只看转发调用 |
| 旧文件保留 | 是 | 保留 RunOnModule 和 Impl 函数，仅注释 PM_REGISTER_PASS，方便回退 |
| ConvTranspose2d 处理 | 提取独立函数 | 原无 Impl 函数，从 RunOnModule 循环体提取 |
| nodiscard Status | `(void)` 抑制 | Visitor 的 Visit 是 void，暂时无法传播错误 |
| BNInfo 冲突 | `#ifndef` guard | 6 个 header 同名 struct，修复原代码缺陷 |

## 调用链

```
ComplexOpSplit::RunOnModule
  ├── PatternMatcher 一次匹配 10 种 Operator 类型
  └── for each match:
        node->Accept(visitor)
          ├── Visit(Exp&)     → ExpSplitImpl        (extern)
          ├── Visit(Inv&)     → InvSplitImpl         (extern)
          ├── Visit(Softmax&) → DoSplitSoftmax        (extern)
          ├── Visit(BaseNorm&)→ NormType map → Impl   (extern)
          └── ... (共 10 个 Visit)
        rewriter.RemoveNode(...)
  └── rewriter.Commit()
```

## 改动量

- 新建 1 个文件（~250 行）
- 10 个旧文件各去 `static`（~15 个函数）+ 注释 PM_REGISTER_PASS
- 2 个旧文件新增独立函数（ConvTranspose2d x2）
- 2 个旧文件加 `#ifndef` guard（BNInfo 修复）
