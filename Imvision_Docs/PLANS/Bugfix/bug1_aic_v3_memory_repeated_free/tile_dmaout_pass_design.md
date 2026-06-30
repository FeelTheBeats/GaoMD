# TileDmaOut Pass 设计文档

> 解决问题：SplitLargeTensor 切了计算但没切输出 buffer，导致 ReflectionPad2d 等近恒等操作的输出 OOM。

---

## 1. 核心问题

### 1.1 现象

iq_model49 在 `HwLayerMemAlloc`（Pass 59）报错 `"no enough memory space for malloc"`，需要分配 8,355,840 bytes（~8MB），但片上内存池只有 4MB。

### 1.2 直接原因

SplitLargeTensor（Pass 42）将 ReflectionPad2d 的计算切为 15 个 tile，每个 tile 处理 72 行。但切完之后，15 个 tile 的输出被 **DummyConcat 拼回全尺寸 buffer**，再整体 DmaOut：

```
DmaIn → DummySlice × 15 → Pad × 15 → DummyConcat × 14 → [8.36MB buffer] → DmaOut → DDR
                                             ↑
                                       这里分配了 8.36MB 片上内存 → OOM
```

### 1.3 根因

**SplitLargeTensor 对计算做了 tiling，但没有对输出 buffer 做 tiling。** DummyConcat 作为通用拼装步骤，强制在片上还原全尺寸输出。对于 Pad 这种几乎不改变数据量级的操作，这个拼装完全多余——Pad 的输出 tile 可以直接 DmaOut 到 DDR 的正确偏移位置，不需要先在片上拼成完整的 8MB buffer。

---

## 2. 为什么 DummyConcat 在 Pad 场景下没有意义

### 2.1 Pad 不改变数据量级

```
输入: [1, 2, 1080, 1920] = 7.91 MB
输出: [1, 2, 1088, 1920] = 7.97 MB  （仅增加 8 行 padding = 60 KB）
```

Pad 的输出就是输入加上边界填充行。每个 tile 的输出尺寸是确定的，每个 tile 在最终 DDR buffer 中的偏移也是确定的。

### 2.2 DummyConcat 在这里真正做了什么

DummyConcat 的本质是"地址代数"——它不产生硬件指令，只是告诉下游"这块数据的地址是多少"。但在 SplitLargeTensor 的 tiling 场景下，DummyConcat 把 15 个独立 tile 的地址拼成一个大 buffer 的地址，**强制下游（DmaOut）看到的是一个全尺寸 tensor**。

如果去掉 DummyConcat，让每个 tile 直接挂自己的 DmaOut，DDR 上的最终排列和经过 DummyConcat 的排列**完全一样**——因为 DmaOut 写入 DDR 的地址是物理地址，tile0 写 offset 0，tile1 写 offset 552960，依次写完就是完整输出。

### 2.3 当前行为 vs 期望行为

```
当前（OOM）：
  Pad(tile0) → pad_out_0 ─┐
  Pad(tile1) → pad_out_1 ─┤
  ...                      ├→ DummyConcat → [8.36MB buffer] → DmaOut → DDR
  Pad(tile14) → pad_out_14 ┘
  片上峰值: 8.36MB ❌

期望（修复后）：
  Pad(tile0) → DmaOut → DDR offset 0         (540KB)
  Pad(tile1) → DmaOut → DDR offset 552960    (540KB)
  ...
  Pad(tile14) → DmaOut → DDR offset 7733760  (540KB)
  片上峰值: 540KB ✅
  DDR 最终排列: 15 × 540KB = 8.36MB（等价于当前）
```

---

## 3. 必要性澄清

### 3.1 这个问题不是 ReflectionPad2d 特有的

任何满足以下条件的操作都会遇到此问题：

1. 输入 tensor 很大（> 4MB 片上内存池）
2. 操作不改变或几乎不改变数据量级
3. SplitLargeTensor 对计算做了 tiling
4. tiling 后的输出被 DummyConcat 拼回全尺寸

可能受影响的同类操作：
- `ReflectionPad2d`（已确认 OOM）
- `ReplicationPad2d`（同类填充操作，同样不改变数据量级）
- `ConstantPad2d`（同上）
- 理论上，任何 SplitLargeTensor 切过且输出 > 4MB 的"近恒等"操作

### 3.2 这和 HwLayerConcatToDummy 处理的是不同问题

| | HwLayerConcatToDummy | TileDmaOut（本 pass） |
|---|---|---|
| 处理对象 | ConcatKernel（真正的 concat 操作） | SplitLargeTensor 产生的 DummyConcat |
| 输入来源 | 两个**独立**上游 Kernel | 多个 tile 来自**同一**计算 |
| 时间错开？ | ✅ 有（不同上游计算完的时间不同） | ❌ 无（同一操作连续产出 tile） |
| 优化方式 | Concat 变为两个独立 DmaIn→DmaOut 对 | DummyConcat 消除，每个 tile 独立 DmaOut |
| 已有处理？ | ✅ Pass 44 已处理 | ❌ 目前没有 |

### 3.3 为什么不能复用 HwLayerConcatToDummy

HwLayerConcatToDummy 的 `isCanMatch` 要求 concat 的输入来自**不同的上游 Kernel**（每个输入 Kernel 只有 1 个 HwLayer，且是 DmaIn）。而 SplitLargeTensor 的 tiling 场景下，所有 tile 来自**同一个 Pad Kernel** 的多个 PadLayer。这两个场景的拓扑结构完全不同，不能共用一个匹配条件。应该独立为新的 pass。

---

## 4. Pass 设计

### 4.1 放置位置

```
Pass 42: SplitLargeTensor      ← 产生 "tile → DummyConcat → DmaOut"
Pass 43: MultloadTilingMove
Pass 44: HwLayerConcatToDummy
Pass 45: BuildAnalyseGraph
```

**建议插入点**：Pass 43 之后、Pass 44 之前（与 HwLayerConcatToDummy 相邻，同属 HwLayer 层面的图优化），命名为 `TileDmaOut`。

### 4.2 匹配条件

遍历 HwGraph 中的 DummyConcatLayer，对每个 DummyConcat 检查：

| 条件 | 检查方式 | 说明 |
|------|---------|------|
| DummyConcat 的所有输入来自同一 Kernel | 追溯每个 input layer 的父 Kernel，判断是否全部相同 | 区别于 Concat2（输入来自不同上游） |
| DummyConcat 的输出只有一个消费者 | `GetOutputEdgesCount() == 1` | 确保下游可控 |
| 输出消费者是 DmaOut | `CastNoCheck<DmaOutLayer>(下游)` | 确保输出直接写 DDR |
| 每个输入 tile 的尺寸对齐 | `tile_size % dma_alignment == 0` | DMA 有对齐要求 |
| （可选）原始操作是"近恒等"类型 | 检查 Kernel 类型（ReflectionPad2d / ReplicationPad2d / ConstantPad2d） | 第一阶段可以只处理确认受益的类型，避免意外 |

### 4.3 改写逻辑

对匹配到的每个 DummyConcat：

```
对于每个输入 tile_i（i = 0..N-1）：
  1. 计算该 tile 在 DDR 输出中的偏移：
     offset_i = i × tile_output_size

  2. 创建新的 DmaOutLayer，连接到 tile_i 的输出
     设置 DmaOut 的 DDR 写入地址为：dst_base + offset_i

  3. 调整 HwLayer 拓扑：
     断开 tile_i ↔ DummyConcat 的边
     建立 tile_i → DmaOutLayer 的边

完成后：
  4. 移除原来的 DummyConcat 和旧的 DmaOut
  5. Resolve() 更新图拓扑
```

### 4.4 DDR 偏移计算

```
tile_output_size = (output_height / num_tiles) × output_width × bytes_per_element

对于 model 49 的 Pad：
  output = [1, 2, 1088, 1920] × fp16(2B) = 8,355,840 bytes
  num_tiles = 15（SplitLargeTensor 产生）
  tile_output_size = (1088 / 15) × 1920 × 2 = ?
```

注意：1088 不能被 15 整除，最后一个 tile 的高度可能不同。SplitLargeTensor 已经处理了不均匀切分——需要从 DummyConcat 的 input layers 各自取出实际尺寸来计算偏移。

### 4.5 不需要处理的情况

以下情况**不应该**被此 pass 处理，保持原有的 DummyConcat 行为：

- DummyConcat 的输入来自不同 Kernel（这是真正的多输入 concat，tiling 场景不适用）
- DummyConcat 的输出消费者不是 DmaOut（可能是另一个计算的输入，需要全尺寸 buffer）
- 每个 tile 的尺寸 < 对齐阈值时（可能不值得拆分，但可以保守处理——即使小 tile 拆分也不会有坏处）

---

## 5. 实现策略

### 第一阶段（最小可行）

只处理 `"同一 Kernel 的多个 PadLayer → DummyConcat → DmaOut"` 这个精确 pattern。这是 model 49 / model 62 的 OOM 的直接修复。

### 第二阶段（扩展）

将匹配条件从 PadLayer 推广到任意 Layer 类型——只要满足"同一 Kernel 的多个 tile → DummyConcat → DmaOut"，就做消除。这是更通用的方案，但需要更多测试覆盖。

### 风险控制

- **保守匹配**：只匹配输入全部来自同一 Kernel 的 DummyConcat，避免误伤真正的多输入 concat
- **对齐检查**：每个 tile 的 DDR offset 必须满足 DMA 对齐要求
- **Phase 控制**：可以加一个 `opt::enable_tile_dmaout` 开关，出问题可以关闭

---

## 6. 预期效果

| | 修复前 | 修复后 |
|---|---|---|
| model 49 编译 | ❌ Pass 59 OOM | ✅ 通过 |
| model 62 编译 | ❌ Pass 59 OOM | ✅ 通过 |
| 片上峰值内存（Pad 输出） | 8.36 MB | 540 KB |
| 已有正常模型（< 4MB 输出） | 不变 | 不变 |
| Concat2 模型（已由 HwLayerConcatToDummy 处理） | 不变 | 不变 |

---

## 7. 下游读取正确性

### 7.1 为什么下游不受影响

切换写入方式不会改变下游读取到的数据。DmaIn 通过 tensor descriptor 寻址：

```
tensor descriptor: shape=[1,2,1088,1920], dtype=fp16, stride=default
```

无论 DDR 上的 8.36MB 数据是一次 DmaOut 写入还是 15 次分片写入，只要最终的字节序列完全相同，DmaIn 读到的东西就不变。

```
当前：DmaOut(全尺寸) → DDR[0..8355839] = tile0 + tile1 + ... + tile14
修复：DmaOut(tile0) → DDR[0..552959] +
      DmaOut(tile1) → DDR[552960..1105919] +
      ...
      DmaOut(tile14) → DDR[7733760..8355839]
```

两次写入的 DDR 地址范围完全重叠，顺序一致（tile0 最低地址 → tile14 最高地址）。同一地址上的字节完全相同。下游 DmaIn 的 view 不变。

类比：`fwrite(buf, 8MB, 1, fp)` 和 `for (i=0; i<15; i++) fwrite(&buf[i*540KB], 540KB, 1, fp)` 写入同一个文件。后续 `fread` 感知不到差别。

### 7.2 边界：非默认 stride 的情况

如果输出 tensor 有自定义 line stride 或 patch stride（即 DDR 上不是紧密排列，而是行列之间有填充空隙），tile 的 offset 计算必须基于 stride 而非简单线性偏移。

```
紧密排列（默认 stride）：
  row0 | row1 | row2 | ... → offset = i × tile_size  ✅

自定义 stride（line stride > row_size）：
  row0 | [gap] | row1 | [gap] | row2 | ... → offset ≠ i × tile_size  ❌
```

对于有自定义 stride 的 tensor，tile-DmaOut 需要额外计算每个 tile 的首行在 stride 布局下的真实偏移。第一阶段可以**保守跳过**——如果 tensor 有非默认 line stride 或 patch stride，不匹配此 pattern，保持原有的 DummyConcat → DmaOut 路径。Model 49 的输出 tensor 使用默认 stride，不触发此限制。

### 7.3 这一点在匹配条件中的体现

在 4.2 节的匹配条件中增加一条：

| 条件 | 检查方式 | 说明 |
|------|---------|------|
| 输出 tensor 无自定义 stride | `!tensor->GetDstLineStrideEnFromJson() && !tensor->GetDstPatchStrideEnFromJson()` | 保证 DDR 紧密排列，tile offset 可直接线性计算 |

---

## 8. 切分上限

切分没有上限。只要满足**每个 tile 自身能装入片上 SRAM**，总输出可以是任意大小（50MB、100MB 均可）。因为 tile-DmaOut 的核心机制是每个 tile 独立写入 DDR 后立即释放片上 buffer，片上永远只保留一个 tile。

这跟 model 48 的 Concat2 原理完全相同——Concat2 输出 7.91MB，但片上峰值只有 3.96MB，因为输入 A 和输入 B 串行复用同一块 buffer。DDR 容量远大于 SRAM，瓶颈永远是片上内存的单次分配大小，不是总输出大小。

---

*文档时间：2026-06-30*
