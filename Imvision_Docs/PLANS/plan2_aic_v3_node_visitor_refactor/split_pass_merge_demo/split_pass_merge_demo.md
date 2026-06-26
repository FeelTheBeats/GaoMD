# Split Pass 合并重构记录

> 基于 Visitor 基础设施的试点应用。将 10 个独立 split pass 合并为 1 个 `ComplexOpSplit`。

---

## 最终策略：extern 转发

**不复写 Impl 函数体**——保持原文件函数不变，只去掉 `static` 让符号可外部引用。新文件 `extern` 声明后一行转发。

---

## 改动文件

| 文件 | 改动 | 说明 |
|------|------|------|
| `complex_op_split.cpp` | 新建 | SplitVisitor + ComplexOpSplit::RunOnModule |
| `complex_op_split_exp.cpp` | `static` → 无 | `ExpSplitImpl` |
| `complex_op_split_inv.cpp` | `static` → 无 | `InvSplitImpl`、`InvSqrtSplitImpl` |
| `complex_op_split_softmax.cpp` | `static` → 无 | `DoSplitSoftmax`、`SoftmaxSplitChannel` |
| `complex_op_split_basenorm.cpp` | `static` → 无 | `LayerNormImpl`、`RMSNormImpl`、`InstanNormImpl` 等 |
| `complex_op_lower_logsoftmax.cpp` | `static` → 无 | `LoweringLogSoftmax`、`LogSoftmaxSplitChannel` |
| `complex_op_split_matmul.cpp` | `static` → 无 | `ConvertMatmul`、`MergePermuteMatmul` |
| `complex_op_split_sin_cos.cpp` | `static` → 无 | `ExpandSinOp`、`ExpandCosOp` |
| `complex_op_split_yuv2rgb.cpp` | `static` → 无 | `TransformToConcatConv2d`、`TransformToConv2dAdd`、`UpdateYuv2RgbRefModel` |
| `complex_op_split_conv_transpose2d.cpp` | 新增 `SplitConvTranspose2d` 函数 | 从 RunOnModule 循环体提取，原格式保留 |
| `complex_op_split_conv_transpose2d2.cpp` | 新增 `SplitConvTranspose2d2` 函数 | 同上 |

所有旧文件的 `PM_REGISTER_PASS` 注释掉，统一由 `ComplexOpSplit` 注册。

---

## 最终文件结构

```
complex_op_split.cpp (~250 行)
  ├── includes (11 个 operator 类型头文件)
  ├── extern 声明 (10 个 pass × 1~5 个 Impl)
  ├── SplitVisitor : public NodeVisitor
  │   ├── Visit(Exp&)          → ExpSplitImpl
  │   ├── Visit(Inv&)          → mode 分派 InvSplit / InvSqrtSplit
  │   ├── Visit(Softmax&)      → SatisfySplitC → DoSplitSoftmax / SoftmaxSplitChannel
  │   ├── Visit(LogSoftmax&)   → SatisfySplitC → LoweringLogSoftmax / LogSoftmaxSplitChannel
  │   ├── Visit(BaseNorm&)     → NormType map → LayerNorm / RMSNorm / InstanNorm
  │   ├── Visit(Sin&)          → ExpandSinOp
  │   ├── Visit(Cos&)          → ExpandCosOp
  │   ├── Visit(Yuv2rgb&)      → tensor size → Conv2dAdd / ConcatConv2d
  │   ├── Visit(Matmul&)       → ConvertMatmul
  │   ├── Visit(ConvTranspose2d&) → SplitConvTranspose2d
  │   └── Visit(ConvTranspose2d2&)→ SplitConvTranspose2d2
  ├── RunOnModule (PatternMatcher + BatchRewriter)
  └── PM_REGISTER_PASS(ComplexOpSplit)
```

---

## 踩坑记录

### 坑 1：BNInfo 重复定义

**现象**：6 个 operator 头文件（`softmax.h`、`base_norm.h`、`cos.h`、`exp.h`、`sin.h`、`inv.h`）各自定义了同名 `struct BNInfo`。以前分属不同编译单元相安无事，合并到 `complex_op_split.cpp` 后编译器报 `redefinition of 'struct aic::BNInfo'`。

**分析**：`softmax.h` 和 `base_norm.h` 是在命名空间 `aic` 下直接定义 `struct BNInfo`，导致冲突。其余 4 个是在类内部定义（`Exp::BNInfo` 等），天然不冲突。

**修复**：给 `base_norm.h` 和 `softmax.h` 的 `struct BNInfo` 加 `#ifndef AIC_BNINFO_DEFINED` guard。改动量：每个文件 3 行，纯 bug fix。

### 坑 2：nodiscard Status 返回值被忽略

**现象**：`Visit` 方法是 `void`，但调用的 extern Impl 函数返回 `[[nodiscard]] Status`。`-Werror=unused-result` 报错。

**修复**：每个调用前加 `(void)` 显式忽略返回值。长期方案可考虑在 SplitVisitor 中加 `Status last_error_` 字段做错误传播。

### 坑 3：ConvTranspose2d 无独立 Impl 函数

**现象**：其他 8 个 pass 都有独立的 `XxxImpl` 函数，去掉 `static` 就能 extern 调用。`ConvTranspose2d` 和 `ConvTranspose2d2` 的改写逻辑直接 inline 在 `RunOnModule` 的循环体里。

**修复**：从 RunOnModule 循环体提取 per-node 逻辑为独立函数 `SplitConvTranspose2d` / `SplitConvTranspose2d2`，保持原格式（注释、空格、换行不变）。RunOnModule 改为调用该函数。ComplexOpSplit 通过 extern 调用同一函数，消除代码重复。

### 坑 4：RmsNorm2Type 枚举值不存在

**现象**：我在 `ComplexOpSplit` 的 NormType map 中手误写了 `NormType::RmsNorm2Type`，该枚举值不存在。

**修复**：删除该条目。原 `complex_op_split_basenorm.cpp` 的 map 也只有 3 个条目（LayerNorm、InstanceNorm、RmsNorm），无 RmsNorm2。

---

## 编译状态

✅ 零 warning 零 error（包括 `-Werror=unused-result`、`-Werror=overloaded-virtual`）
