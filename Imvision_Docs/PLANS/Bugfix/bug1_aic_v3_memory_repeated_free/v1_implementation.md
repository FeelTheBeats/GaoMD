# V1 实现方案：Pad Tile-DmaOut 修复

> 实现日期：2026-07-01
> 
> 修改文件：`target/tensor_brain/kernels/pad.cpp`
> 
> 编译状态：✅ `[100%] Built target ts_aic`

---

## 1. 问题

`PadKernel::GenerateHTilingHwLayers` 和 `GenerateOutChannelTilingHwLayers` 在 tiling 计算后，调用 `BuildDummyConcatLayers` 将所有 tile 输出合并为一个全尺寸 L1 buffer。当输出 > 4MB 时导致 MemAlloc OOM。

## 2. 修改点

在两个 tiling 函数末尾，tile 的 PadLayer 输出与 DummyConcat 合并之间，插入 NpuDmaOut 层，将每个 tile 先写到 DDR：

```
修改前：PadLayer(tile) → [L1 540KB] → DummyConcat → [L1 8.36MB] → OOM
修改后：PadLayer(tile) → [L1 540KB] → NpuDmaOut → [DDR 540KB] → DummyConcat → [DDR 8.36MB]
```

## 3. 具体改动

### 3.1 新增 include

```cpp
#include "tensor_brain/hw_layers/dma/npu_dma_out.h"
```

### 3.2 GenerateHTilingHwLayers（H 方向 tiling）

```cpp
// 替换原来的：
// return BuildDummyConcatLayers(split_outs, out, ...);

// 改为：每个 tile 先 NpuDmaOut → DDR，再 DummyConcat 合并
for (size_t i = 0; i < split_outs.size(); i++) {
    Tensor &ddr_out = hw_graph_->GetOrCreateTensor(...);
    ddr_out.Init(split_outs[i]->dim(), out->data_type(), out->pattern());
    ddr_out.SetMemSpace(MemSpace::kDDR);

    NpuDmaOut &dma_out_layer = hw_graph_->AddHwLayer<NpuDmaOut>(...);
    dma_out_layer.SetInputs({split_outs[i]}).SetOutputs({&ddr_out});
    dma_out_layer.SetInoutAttrs(split_outs[i], &ddr_out);
    split_outs[i] = &ddr_out;
}
out->SetMemSpace(MemSpace::kDDR);
return BuildDummyConcatLayers(split_outs, out, ..., "height", name());
```

### 3.3 GenerateOutChannelTilingHwLayers（C 方向 tiling）

同上逻辑，在 `BuildDummyConcatLayers1` 调用前插入 tile-DmaOut。

## 4. 改动规模

- 文件变更：1 个（`pad.cpp`）
- 新增代码：~25 行
- 插入位置：2 处（两个 tiling 函数的末尾）

## 5. 适用范围

所有转换为 `PadKernel` 的操作类型自动受益：
- `ReflectionPad2d`
- `ReplicationPad2d`
- `ConstantPad2d`

触发条件：
- `mem_size > 2 * SZ_1M`（tensor 总内存 > 2MB）
- `single_pad() == true`（DmaIn → Pad → DmaOut 直连模式）
- C >= 8 → 走 C tiling；C < 8 → 走 H tiling

## 6. 下游兼容性

DummyConcat 的输出 `out` 设置为 `MemSpace::kDDR`。下游 `DmaOutKernel` 的 `NpuDmaOut` 将进行 DDR→DDR 传输（硬件支持），功能正确，性能略有冗余（可后续 V2 优化消除双写）。

## 7. 未改动部分

- `PadKernel::BuildHwGraphImpl` 的 tiling 决策逻辑不变
- 非 tiling 路径（`mem_size <= 2 * SZ_1M` 或非 single_pad）不受影响——创建单 `PadLayer`，输出在 L1，行为不变
- `SplitLargeTensor` 无需修改（PadKernel 自主处理 tiling）
