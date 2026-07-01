# Pad OOM 修复尝试记录 — 2026-07-01

> 问题：模型 49/62 的 ReflectionPad2d 输出 [1,2,1088,1920] = 8.36MB，超过片上 4MB SRAM，MemAlloc OOM。
>
> 目标：消除 PadKernel 输出 DummyConcat 产生的全尺寸 L1 buffer。

---

## 1. 问题确认

- 模型 49：单一 `ReflectionPad2d`，输入 `[1,2,1080,1920]` ≈ 7.91MB，输出 `[1,2,1088,1920]` ≈ 7.97MB
- 模型 62：同结构
- PadKernel 在 `BuildHwGraphImpl` 中检测到 `mem_size > 2MB && single_pad()`，进入 H tiling
- H tiling 将 1080 行切成 15 个 tile，每个 ~540KB L1
- 15 个 PadLayer tile 输出 → `BuildDummyConcatLayers` → 全尺寸 L1 output `[1,2,1088,1920]` ≈ 8.36MB → OOM
- **基线（HEAD）就是坏的**

## 2. 尝试方案

### 2.1 Plan A：PadKernel 内部加 NpuDmaOut（V1）

**思路**：在 `PadKernel::GenerateHTilingHwLayers` 和 `GenerateOutChannelTilingHwLayers` 末尾，每个 tile 的 PadLayer 输出后插入 `NpuDmaOut` 层，将 L1 tile 写到 DDR，再 DummyConcat 合并 DDR tensors。

**修改**：`target/tensor_brain/kernels/pad.cpp`，~30 行。

**结果**：❌ Pass 45 `BuildAnalyseGraph` 报 `source hwlayers number is not equal to sink hwlayers number`。`NpuDmaOut` 被放入 `PadKernel`（计算 kernel）的 HwGraph，连接 source（PadKernel）和 sink（DmaOutKernel）的 compute HwLayer 数量不匹配。

**根因**：`BuildAnalyseGraph` 在连接 source/sink HwLayers 时对计算 kernel 的 HwLayer 类型有隐式约束——PadKernel 的 HwGraph 预期只包含 `PadLayer` + `DummyConcat`（compute），加入 `NpuDmaOut`（DMA）破坏了计数。

### 2.2 Plan B：SplitLargeTensor 中修改（V2 简化版）

**思路**：不在 Pass 32（BuildHwGraph）改，而在 Pass 42（SplitLargeTensor）改。照搬已有 `HeightSplitTensor` 对 `EltwiseKernel` 的模式——在 HwGraph 中插入 `NpuDmaOut` + `DummyConcat`，并用 `dma_out_kernel->MutableOutputs()[0]` 做最终输出 tensor（其在 DDR）。

**修改**：`target/tensor_brain/transforms/split_large_tensor.cpp`，~60 行。

**结果**：❌ 同样 `BuildAnalyseGraph` 报 `source hwlayers number is not equal to sink hwlayers number`。

**调试过程**：
- 确认 `SplitVpuInTensor` 被调用（Pass 42 正常运行）
- 确认 `PadKernel` 被 `dynamic_cast` 找到
- 确认 `DmaOutKernel` 作为下游存在
- 确认 15 个 `PadLayer` 被收集（tiling 激活）
- 确认 `output = dma_out_kernel->MutableOutputs()[0]` = `2FPad_1_output_0_out`，大小 8.36MB
- 代码在 `hw_graph.Resolve()` 后，到 Pass 45 时报上面错误

**尝试的子方案**：
- ❌ ReleaseNode DmaOut HwLayers（完全清空）→ 同样错误
- ❌ 仅 SetInValid DmaOut HwLayers（保留占位）→ 同样错误

## 3. 核心障碍

`BuildAnalyseGraph`（Pass 45）连接 source kernel（PadKernel）和 sink kernel（DmaOutKernel）的 HwLayers 时，要求 compute HwLayer 数量匹配。任何在 PadKernel 的 HwGraph 中加入 `NpuDmaOut` 的方案都会破坏这个匹配。

`HeightSplitTensor` 对 `EltwiseKernel` 的同样模式能工作——它在 EltwiseKernel 的 HwGraph 中加 `NpuDmaOut` 并 invalidate DmaOutKernel 的 HwLayers。但将其直接移植到 PadKernel 行不通。差异需要深入 `BuildAnalyseGraph` 的源码理解。

## 4. 可用的线索

- **Alan 的方向**："node tiling 的问题"（截图中提到 `BuildHwGraphImpl`）
- **55f6e40 patch**：eloisezhang 的 PadKernel C+H tiling 改进，但仅解决计算 tiling 粒度，不解决输出 buffer
- **EltwiseKernel 对比**：在 `HeightSplitTensor` 中 NpuDmaOut + DummyConcat + DmaOutKernel invalidate 能工作——需要理解为什么 PadKernel 不能复用相同模式

## 5. 突破：框架已有解决方案，只是入口被卡住了

### 5.1 关键发现

读 `BuildAnalyseGraph` 的 source/sink HwLayer 配对逻辑时，发现了一个名为 `KernelMovDummyConcatAfterDMAOutPattern` 的 pattern（line 1063-1267）。

**这个 pattern 的功能正是我们需要的**：将 source kernel（如 PadKernel）内部的 DummyConcat "移到 DmaOut 之后"——把 tile 在 L1 侧合并再 DmaOut 的流程，改写为每个 tile 独立 DmaOut 后在 DDR 侧合并。

```
原来：PadLayer×N → DummyConcat(L1全尺寸) → DmaOut → DDR
改写：PadLayer×N → NpuDmaOut×N → DummyConcat(DDR) → DDR输出
```

`PadKernel` 已在支持的 kernel 列表中（line 1076）：

```cpp
const bool is_supported_src = Isa<Conv2dKernel, ConvFusionKernel, ActivationKernel,
    InterpKernel, PadKernel, Pool2d2Kernel, PermuteKernel, Pool2dKernel,
    BatchNormKernel>(source_kernel);
```

### 5.2 为什么它不匹配

逐条件追踪 `KernelMovDummyConcatAfterDMAOutPattern::Match`：

| 条件 | 结果 | 说明 |
|------|------|------|
| `split_cascade_opt != kDefault` | ✅ 通过 | 模型 49 不设此 flag |
| `io_pathway == kVbus \|\| frame2patch` | ✅ 通过 | 不触发 |
| source kernel 是 PadKernel | ✅ 通过 | 在支持列表 |
| sink kernel 是 DmaOutKernel | ✅ 通过 | model 49 是 DmaIn→Pad→DmaOut |
| `commonPatternMatch` | ✅ 通过 | PadKernel 总内存 15.88MB > 4MB，且 `HwSplitHMode=false` |
| `GetDstMemSpace() != local_mem` | ✅ 通过 | DmaOut 写 DDR |
| `source_hw.NumberOfNodes() > 1` | ✅ 通过 | 15 PadLayer + 15 DummySlice + 14 DummyConcat |
| `isKHeightDummyConcat()` | ✅ 通过 | H tiling 使用 height 模式 DummyConcat |
| **`allSplitedPartEqual(Height)`** | ❌ **失败** | ReflectionPad 首尾 tile 高度不等 |

`allSplitedPartEqual`（line 1101-1177）检查所有 tile 输出是否等分。ReflectionPad 的 H tiling 中：
- 第一个 tile：`pad_size_h_up` 保留，`pad_size_h_down = 0`
- 中间 tile：上下 padding 均为 0
- 最后一个 tile：`pad_size_h_up = 0`，`pad_size_h_down` 保留

三个区域的 PadLayer 输出高度不同 → `size_of_parts.size() > 1` → 检查失败。

### 5.3 框架已有的跳过机制

`allSplitedPartEqual` 中有一段**专门为 H-tiling PadLayer 设计的跳过逻辑**（line 1121-1126）：

```cpp
if (Isa<PadLayer>(hw_layer)) {
    auto pad_hw = CastNoCheck<PadLayer>(hw_layer);
    if (pad_hw->hsplit_en) {
        continue;  // 跳过 hsplit 模式的 PadLayer，不参与等分检查
    }
}
```

这段代码存在于框架中，说明框架设计时**已经考虑了 PadLayer H-tiling 的不等分问题**。但 `PadKernel::GenerateHTilingHwLayers`（旧代码）没有设置 `hsplit_en = true`。

**55f6e40 patch 的新函数 `GenerateOutChannelHeightTilingHwLayers` 设了**（line 520 有 `split_pad_layer.hsplit_en = true`），但老函数没有。

### 5.4 一行修复

在 `PadKernel::GenerateHTilingHwLayers` 中，PadLayer 创建后加一行：

```cpp
pad.hsplit_en = true;
```

文件：`target/tensor_brain/kernels/pad.cpp`

改动：1 行。

### 5.5 修复后的流程

```
PadKernel::BuildHwGraphImpl
  → GenerateHTilingHwLayers（H tiling，每个 PadLayer 标记 hsplit_en=true）
  → BuildDummyConcatLayers（L1 侧合并 tile）

SplitLargeTensor（Pass 42）— 不处理 PadKernel

BuildAnalyseGraph（Pass 45）
  → KernelMovDummyConcatAfterDMAOutPattern::Match
    → allSplitedPartEqual: 遇到 hsplit_en 的 PadLayer → 跳过
    → 匹配成功！
  → KernelMovDummyConcatAfterDMAOutPattern::Rewrite
    → 将 DummyConcat 从 L1 移到 DDR
    → 每个 tile 独立 DmaOut → DDR → DummyConcat 合并
  → L1 峰值：单个 tile（~540KB），不是 8.36MB ✅
```

### 5.6 验证结果

| 模型 | 修复前 | 修复后 |
|------|--------|--------|
| iq_model49 | ❌ Malloc Error 8.36MB OOM | ✅ Done |
| iq_model62 | ❌ Malloc Error 8.36MB OOM | ✅ Done |

## 6. 经验总结

### 6.1 逻辑链路

```
现象：ReflectionPad2d 模型 OOM（8.36MB 输出 > 4MB L1）
  ↓
根因：PadKernel H tiling 后 DummyConcat 在 L1 侧拼装全尺寸输出
  ↓
Plan A 失败：在 PadKernel::BuildHwGraphImpl 加 NpuDmaOut
  → BuildAnalyseGraph 报 "source hwlayers != sink hwlayers"
  ↓
Plan B 失败：在 SplitLargeTensor 加 NpuDmaOut（照搬 HeightSplitTensor 模式）
  → 同样错误（改的不是时机，是对象——都在 PadKernel HwGraph 塞 DMA 层）
  ↓
关键转向：读 BuildAnalyseGraph 源码
  → 发现 KernelMovDummyConcatAfterDMAOutPattern 已实现所需逻辑
  → 逐条件追踪，定位到 allSplitedPartEqual 是卡点
  → 发现 hsplit_en 跳过机制已存在但未被设置
  ↓
一行修复：pad.hsplit_en = true
```

### 6.2 关键教训

1. **框架可能已经有答案**：在写新 pass 之前，先读框架里已有的 pattern 和优化逻辑。`KernelMovDummyConcatAfterDMAOutPattern` 的设计目标就是解决"tile 后 DummyConcat 占用 L1"的问题，PadKernel 已在支持列表中。

2. **标志位比新逻辑更优先考虑**：很多时候不是"框架缺功能"，而是"没把标志位设对"。`hsplit_en` 这个字段在 PadLayer 中定义、在 `allSplitedPartEqual` 中被检查、在 55f6e40 的新函数中被设置——说明框架设计者是知道这个场景的。

3. **"为什么 Eltwise 可以而 Pad 不行"比"Pad 为什么报错"更有价值**：EltwiseKernel 能过 HeightSplitTensor，不是因为 Eltwise 特殊，而是因为 Eltwise 的 tile 天然等分（加减乘除不改变 shape）。Pad 的 tile 不等分是因为 padding 在边界不对称——这是操作语义差异，不是框架偏袒。

4. **失败的尝试不是浪费**：六小时试了两个方案、读了四个文件、追踪了一个 pattern 的全部匹配条件——最终落在了一行代码上。这六小时的价值不在于那一行，而在于"下次不会再从写新 pass 开始想"。
