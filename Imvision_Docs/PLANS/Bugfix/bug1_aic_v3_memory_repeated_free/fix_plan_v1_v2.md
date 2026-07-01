# Pad OOM 修复方案对比：V1 快速修复 vs V2 通用 Pass

> 问题：SplitLargeTensor 对 ReflectionPad2d 切了计算但没切输出 buffer，DummyConcat 在片上拼装全尺寸输出导致 OOM。

---

## V1：SplitLargeTensor 内后处理（快速修复）

### 思路

在 SplitLargeTensor 末尾，tiling 完成后，对 Pad 类操作不生成 DummyConcat，改为每个 tile 直接挂 DmaOut。

### 改动范围

- 文件：仅 `SplitLargeTensor`（1 个文件）
- 代码量：~30 行
- 不新建 pass，不改 main.cpp

### 伪代码

```
在 SplitLargeTensor 的 tiling 循环完成后：

for each tiled_kernel in tiled_kernels:
    if (kernel_type != ReflectionPad2d
        && kernel_type != ReplicationPad2d
        && kernel_type != ConstantPad2d):
        continue  // 只处理 Pad 类操作

    // 为每个 tile 创建独立 DmaOut，替代 DummyConcat + 单 DmaOut
    for (i = 0; i < num_tiles; i++):
        offset = 计算 tile_i 在 DDR 输出中的偏移
        创建 DmaOutLayer，连接到 tile_i 输出
        设置 DmaOut 写入地址 = dst_base + offset

    移除 DummyConcat 和旧 DmaOut
```

### 优点

- 改动集中，一个文件解决问题
- 直接修复 model 49/62
- 回归风险低——只影响 Pad 类操作的后处理逻辑

### 缺点

- 硬编码操作类型判断（`if (kernel_type == ReflectionPad2d || ...)`）
- 不通用——未来新的"近恒等"操作需要手动加到这里
- SplitLargeTensor 职责膨胀——它本来是切分，现在还要管输出 buffer 消除

---

## V2：TileDmaOut Pass（通用消除 Pass）

### 思路

在 SplitLargeTensor 之后、MemAlloc 之前，加一个独立 pass。通过 **pattern 匹配**而非操作类型判断，识别"同 kernel 多 tile → DummyConcat → DmaOut"，改写为每个 tile 独立 DmaOut。

### 放置位置

```
Pass 42: SplitLargeTensor
Pass 43: TileDmaOut          ← 新增
Pass 44: MultloadTilingMove  （原 43）
...
```

### 匹配条件

| 条件 | 说明 |
|------|------|
| DummyConcat 所有输入来自同一 Kernel | 通过追溯 input layer 的父 Kernel 判断 |
| DummyConcat 输出只有一个消费者 | GetOutputEdgesCount == 1 |
| 消费者是 DmaOut | 确保下游直接写 DDR |
| 每个 tile 满足 DMA 对齐 | tile_size % alignment == 0 |
| 输出 tensor 无自定义 stride | 避免复杂偏移计算 |

### 改写逻辑

```
for each matched DummyConcat:
    for (i = 0; i < num_input_tiles; i++):
        offset = 实际 tile 尺寸累加（非简单 i * tile_size，处理不均分）
        创建 DmaOutLayer → tile_i
        设置 DmaOut 写入地址 = dst_base + offset

    移除原 DummyConcat 和旧 DmaOut
    Commit()
```

### 伪代码

```cpp
Status TileDmaOut::RunOnModule(Module& mod) {
  auto* kernel_net = dynamic_cast<KernelNet*>(mod.GetGraphManager()->GraphPtr());

  for (auto index : graph_viewer.GetNodesInTopologicalOrder()) {
    auto* concat = CastNoCheck<DummyConcatLayer>(node);
    if (!concat) continue;

    // 条件 1: 所有输入来自同一个 Kernel
    Kernel* owner = nullptr;
    for (auto* input : concat->InputLayers()) {
      auto* k = input->GetOwnerKernel();
      if (!owner) owner = k;
      else if (k != owner) { owner = nullptr; break; }
    }
    if (!owner) continue;

    // 条件 2-5: 单消费者 + DmaOut + 对齐 + 无自定义 stride
    if (concat->GetOutputEdgesCount() != 1) continue;
    auto* dmaout = CastNoCheck<DmaOutLayer>(concat->OutputNodesBegin());
    if (!dmaout) continue;
    // ... 对齐和 stride 检查 ...

    // 改写: 每个 tile → DmaOut
    uint32_t offset = 0;
    for (auto* tile_input : concat->InputLayers()) {
      auto* new_dmaout = CreateDmaOut(...);
      new_dmaout->SetDstAddr(dst_base + offset);
      ConnectDmaOutToTileInput(new_dmaout, tile_input);
      offset += GetActualTileOutputSize(tile_input);
    }

    RemoveNode(concat);
    RemoveNode(old_dmaout);
    Commit();
  }
}
```

### 优点

- 通用——任何被 SplitLargeTensor 切的"近恒等"操作自动受益
- 架构对称——和 `HwLayerConcatToDummy`（消除 Concat2 的 DummyConcat）职责对应
- 易扩展——新受益类型无需改代码，匹配条件自动覆盖
- SplitLargeTensor 职责不变

### 缺点

- 新建 pass，需要注册到 main.cpp
- 更多的代码量（~80 行）

---

## 对比总结

| | V1（SplitLargeTensor 内后处理） | V2（TileDmaOut pass） |
|---|---|---|
| 文件变更 | 1 个 | 2 个（新 pass + main.cpp） |
| 代码量 | ~30 行 | ~80 行 |
| 匹配方式 | 硬编码操作类型 | Pattern 匹配（更通用） |
| 适用范围 | Pad 类操作 | 任何"多 tile → DummyConcat → DmaOut" |
| 新增受益类型成本 | 手动加 if 分支 | 零改动 |
| SplitLargeTensor 职责 | 膨胀 | 不变 |
| 与 HwLayerConcatToDummy 关系 | 无 | 对称 |
| 回归风险 | 低 | 中（新 pass 需要充分测试） |

---

## 推荐路径

1. **V1 先上**：解决 model 49/62 的紧急 OOM，改动小、风险低
2. **V2 后上**：在 V1 验证通过后，把 SplitLargeTensor 内的后处理逻辑抽出来，泛化为独立 TileDmaOut pass，纳入常规优化管线
3. V1 的硬编码操作类型判断在 V2 中被 pattern 匹配替代，不产生技术债

---

*文档时间：2026-07-01*
