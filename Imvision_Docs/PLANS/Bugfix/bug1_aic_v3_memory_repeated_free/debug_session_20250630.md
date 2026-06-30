# 调试会话：2025-06-30 — OOM 根因定位

## 0. 背景

[first_Q.md](first_Q.md) 中记录了问题表象：iq_model49 在 `HwLayerMemAlloc` pass 时报错 `"no enough memory space for malloc"`，tensor 大小为 `8355840` bytes。

本次会话的目标：**从 IR 链路追溯这个 8355840 大 tensor 的起源，并理解为什么编译器无法处理它。**

---

## 1. 定位 `"mem_size": 8355840` 首次出现位置

**问题**：`mem_size: 8355840` 在哪个文件第一次出现？

### 逐 pass IR 检索

```
$ grep -rl '"mem_size": 8355840' pass_ir/ | sort

007.MatmulSplit.json    ← 2 次
057.LiveTimeAnalyse.json ← 3 次
```

但继续向上追溯 pass 001~006：

| Pass | 出现次数 |
|------|---------|
| `001.ReadCfgFileInfos.json` | **1 次** |
| `002.CompressTensorShapeHandle.json` | **1 次** |
| `003.InsertCopy.json` | **2 次**（InsertCopy 增加了 Copy 输出的 edge，相同大小） |
| 之后所有 pass | **2 次** |

**结论**：这个大 tensor 在 Pass 1（`ReadCfgFileInfos`）就已经存在，是从原始模型 `iq_model49_sv.json` 直接读入的，**不是任何 pass 引入或放大的**。

### 验算

```
shape  = [1, 2, 1088, 1920]
dtype  = f16（半精度浮点，2 bytes/element）

总元素数 = 1 × 2 × 1088 × 1920 = 4,177,920
总字节数 = 4,177,920 × 2       = 8,355,840 bytes
         = 8,160.00 KB
         ≈ 7.97 MB
```

在 `iq_model49_sv.json` 中直接定义了：

```json
"output_tensor": ["2FPad_1_output_0"],
"output_shape": [{"dim": [1, 2, 1088, 1920], "dtype": "f16", ...}]
```

对应的节点：

```
节点: /Pad_1 (ReflectionPad2d)
输入: 2FConcat_output_0  → shape [1, 2, 1080, 1920] → 7.91 MB (Fp16)
输出: 2FPad_1_output_0   → shape [1, 2, 1088, 1920] → 7.97 MB (Fp16)
```

Pad 操作在 H 维度加了 8 行（1080 → 1088），输出从 7.91 MB 增加到 7.97 MB。

---

## 2. SplitLargeTensor 做了什么？没做什么？

### Pass 42 (SplitLargeTensor) 对 `/Pad_1` 的切分

SplitLargeTensor 确实对 `/Pad_1` 做了切分，将计算拆成：

```
DummySlice × 15  +  Pad × 15  +  DummyConcat × 14
```

但切分粒度：

| 层级 | 做了什么 | 未做什么 |
|------|---------|---------|
| ✅ 输入端 | DmaIn 按 72-row tile 流式加载，每个 tile 552,960 bytes (540KB) | — |
| ✅ 计算 | 15 个 Pad 各自处理一个 72-row 分片 | — |
| ❌ **输出端** | — | 14 个 DummyConcat 拼回全尺寸输出，**edges 中 `2FPad_1_output_0` 仍然是 8,355,840 bytes** |

### 核心矛盾

```
2FPad_1_output_0 单 tensor:  8.36 MB
硬件内存池总大小:             4.00 MB
空闲内存（mem_6 时刻）:       ~1.90 MB
```

**无论怎么切计算，输出 buffer 需要全尺寸分配，而单 buffer 就比整个内存池大 2 倍。**

### 输入端为什么能过？

回顾 loglog 中 `mem_0 ~ mem_6` 的内存分配记录，每次只分配 **552,960 bytes**（一个 tile slice），用的是 DmaIn 流式加载。输入端没有一次性分配 8.29MB，而是 tile by tile。

---

## 3. 横向对比：66 个模型哪里过哪里不过

检查 `/home/sevengao/bugs/001_memory_repeated_free/all_scales/tnt-5875/motionattgen_npu_a400_out/` 下所有 66 个切分后的子模型。

### 输出 > 4MB 的模型（共 6 个）

| 模型 | 输出大小 | 输出层类型 | 编译结果 |
|------|---------|-----------|---------|
| iq_model5 | 7.91 MB | **Slice2** | ❌ 无输出 |
| iq_model24 | 7.91 MB | **Slice2** | ❌ 无输出 |
| iq_model48 | 7.91 MB | **Concat2** | ✅ 成功（69 passes, 有 bin） |
| iq_model61 | 7.91 MB | **Concat2** | ✅ 成功（有 bin） |
| **iq_model49** | **7.97 MB** | **ReflectionPad2d** | ❌ **OOM** |
| **iq_model62** | **7.97 MB** | **ReflectionPad2d** | ❌ **OOM** |

### 所有 ReflectionPad2d 作为输出层的模型

| 模型 | pad后输出 | 编译结果 |
|------|----------|---------|
| iq_model17 | 3.98 MB | ❌ 只到 pass 45 (BuildAnalyseGraph) |
| iq_model36 | 3.98 MB | ❌ 无输出 |
| **iq_model49** | **7.97 MB** | ❌ pass 59 OOM |
| **iq_model62** | **7.97 MB** | ❌ pass 59 OOM |

**结论**：所有以 ReflectionPad2d 为输出层的模型都失败了，无论输出是否 < 4MB。而 Concat2 即使输出 > 4MB 也能成功。

---

## 4. 为什么输出层类型决定 OOM？

### 4.1 Concat2 → 能过：实际内存 trace 证据

Model 48 编译产出的 `iq_model48_sv_local_mem.log` 记录了片上实际内存分配：

```
"max_peak_size": [{"size": 4147200}]   ← 峰值只有 3.96MB！
```

而它的逻辑输出 `2FConcat_output_0` 是 [1,2,1080,1920] = **7.91MB**。7.91MB 的输出却只用了 3.96MB 片上内存，怎么做到的？

Model 48 一共 4 个 kernel，完整执行流程：

```
kernel[0]: DmaIn  input_A (2FAdd_2, [1,1,1080,1920])
           → malloc 3.96MB @ addr 0
           → 从 DDR 读到片上 buf

kernel[1]: DmaOut "copy_out_2FConcat_output_0.0"
           → 不分配新内存！复用 kernel[0] 的 buf
           → 写到 DDR offset 0
           → free 3.96MB（片上释放）

kernel[2]: DmaIn  input_B (2FSub_2, [1,1,1080,1920])
           → malloc 3.96MB @ addr 0  ← 同一块地址，复用！
           → 从 DDR 读到片上 buf

kernel[3]: DmaOut "copy_out_2FConcat_output_0.1"
           → 不分配新内存！复用 kernel[2] 的 buf
           → 写到 DDR offset 4147200
           → free 3.96MB
```

**DDR 上的最终布局**：

```
DDR:
  ┌─────────────────────────┐ offset 0
  │  input_A (channel 0)    │ 3.96MB  ← kernel[1] 写入
  ├─────────────────────────┤ offset 4147200
  │  input_B (channel 1)    │ 3.96MB  ← kernel[3] 写入
  └─────────────────────────┘
  
  逻辑上 = 2FConcat_output_0 [1,2,1080,1920] = 7.91MB
  但片上自始至终只占 3.96MB！
```

**核心原理**：Concat 的两个输入来自两个**不同上游**（2FAdd_2 和 2FSub_2），它们到达有先后。编译器利用时间差，让两块输入**串行**使用同一块 3.96MB 片上 buffer，分别 DmaOut 到 DDR 的相邻位置。Concat 本身不产生任何数据搬运——Concat 就是"两块数据在 DDR 上紧挨着放"这个摆放方式本身。

### 4.2 ReflectionPad2d → 为什么不能同样处理？

ReflectionPad2d 的输出 `2FPad_1_output_0` 也被 SplitLargeTensor 切成了 15 个 tile，每个 tile 540KB。**理论上**每个 tile 也可以独立 DmaOut 到 DDR 的正确偏移：

```
理论上可以（但编译器没做）：
  Pad tile0 → DmaOut → DDR offset 0        (540KB)
  Pad tile1 → DmaOut → DDR offset 552960    (540KB)
  ...
  Pad tile14 → DmaOut → DDR offset 7733760  (540KB)
  
  片上峰值: 540KB（只需一个 tile buffer）
  DDR 最终: 15 × 540KB = 8.36MB 完整输出
```

**但实际编译器的行为**：

```
实际做的：
  Pad tile0 → pad_out_0 (540KB)
  Pad tile1 → pad_out_1 (540KB)
  ...
  Pad tile14 → pad_out_14 (540KB)
                    ↓
  DummyConcat → 把 15 个 tile 拼成一个 8.36MB 片上 buffer
                    ↓
  DmaOut → DDR
  
  片上峰值: 8.36MB → OOM！
```

**DummyConcat 在 Pad 场景下帮了倒忙**：它把分散的 tile 输出"聚合"成一个全尺寸 buffer 再 DmaOut，而不是让每个 tile 独立 DmaOut。

### 4.3 为什么同样的 DummyConcat，在 Concat 场景是优化，在 Pad 场景是灾难？

| | Concat2（model 48） | ReflectionPad2d（model 49） |
|---|---|---|
| 输入来源 | 两个**独立**上游，时间错开 | 15 个 tile 来自**同一个** Pad 计算 |
| 输入之间的时间差 | ✅ 有（不同上游计算完的时间不同） | ❌ 无（同一个 Pad 连续产出 tile） |
| DummyConcat 做了什么 | **消除**——Concat 变成两个独立的 DmaIn→DmaOut 对，各自串行 | **聚合**——把 15 个 tile 拼成一个 buffer |
| 片上峰值 | 3.96MB（单个输入） | **8.36MB（全尺寸输出）** |
| 编译器优化管线 | KernelConcatEliminate → HwlayerConcatEliminate → HwLayerConcatToDummy | SplitLargeTensor 切了计算但没有匹配的"输出 tile 化"pass |

### 4.4 类比

- **Concat2**：快递公司有两个包裹要送到同一个地址。第一个到了放下就走，第二个到了放第一个旁边。不需要先把两个包裹拼成一个大箱子再送——放在一起就是"拼接"。
- **ReflectionPad2d（当前）**：工厂 15 条生产线各自产出一个小零件。但仓库要求先把 15 个零件拼成一辆完整的车再入库——需要一个能放整辆车的仓库。而仓库只有 4 平米，车要 8 平米，爆仓。
- **ReflectionPad2d（理想）**：每个零件生产出来直接入库，放到指定位置。仓库只需要放一个零件（540KB），而不是整辆车（8.36MB）。

---

## 5. 结论与修复方向

### 根因

**SplitLargeTensor 切了计算但没有切输出 buffer**，而 ReflectionPad2d 缺少类似 Concat 的消除/虚拟化优化。DummyConcat 把所有分片拼回全尺寸输出 buffer，导致分配 8.36MB → 超出 4MB 内存池 → OOM。

### 可能的修复方向

1. **编译器增加 buffer tile 化 pass**：让 Pad 的每个分片直接 DmaOut 到 DDR 的不同偏移位置，避免在片上分配全尺寸输出 buffer
2. **前端规避**：在模型切分时确保 ReflectionPad2d 的输出尺寸 ≤ 4MB，或把 Pad 和下游的 Downsample（如 model 50 的 Pool2d）合并在同一个子模型内
3. **增大内存池**：检查 4MB 是否硬件硬限制，是否可通过配置扩大

---

## 附录：关键文件路径

| 文件 | 路径 |
|------|------|
| 原始模型 | `/home/sevengao/bugs/001_memory_repeated_free/ques/iq_model49/iq_model49_sv.json` |
| 编译日志 | `/home/sevengao/bugs/001_memory_repeated_free/ques/iq_model49/loglog` |
| Pass IR 目录 | `/home/sevengao/bugs/001_memory_repeated_free/ques/iq_model49/fixfix/pass_ir/` |
| 所有子模型 | `/home/sevengao/bugs/001_memory_repeated_free/all_scales/tnt-5875/motionattgen_npu_a400_out/` |
| Pass 列表（从 loglog 提取） | 见下方 |

### 完整 Pass 列表（59 个）

```
 1. ReadCfgFileInfos          21. GenIOInfo                 41. InitialLoadParams
 2. CompressTensorShapeHandle 22. FusedOp                   42. SplitLargeTensor
 3. InsertCopy                23. CompressWeight            43. MultloadTilingMove
 4. Yuv2rgbSplit              24. SplitOp                   44. HwLayerConcatToDummy
 5. NormTiling                25. KernelConcatEliminate     45. BuildAnalyseGraph
 6. NormSplit                 26. DeleteConcatBeforeConv    46. InsertDataLayout
 7. MatmulSplit               27. ParamsReplace             47. DumpAnalysisGraphPass
 8. ChannelLimitSplitPermute  28. BroadcastImplement        48. VbusIOMemManager
 9. ConvTranspose2d2Split     29. TwoVpuPipeline            49. MultiMpuParallelism
10. ConvTranspose2dSplit      30. SplitCascadeOp            50. SetVpuHwTypePass
11. SoftmaxSplit              31. ConcatTreeFuse            51. HandCfgHwTypePass
12. SinCosTiling              32. BuildHwGraph              52. InsertSync
13. SinCosSplit               33. SliceFuse                 53. Cascade
14. ExpSplit                  34. SliceTilingMove           54. InvalidCascadeEliminate
15. InvSplit                  35. DumpKernelGraphPass       55. MemAlloc
16. LowerLogSoftmax           36. MidResultsTransfer        56. HwLayerInplace
17. PermuteReplaceReshape     37. PackParamDatas            57. LiveTimeAnalyse
18. DumpOperatorGraphPass     38. HwlayerConcatEliminate    58. DumpAnalysisGraphPass
19. Lowering                  39. HwLayerSliceToDummy       59. HwLayerMemAlloc ← OOM
20. DumpKernelGraphPass       40. InsertParamDataFetch
```

---

## 6. Model 49 内部流程：逐步拆解

### 6.1 Model 49 只有一步

澄清：之前讨论中提到的 "Concat" 发生在 model 48，跟 model 49 的 bug 无关。Model 49 输入叫 `2FConcat_output_0` 只是因为上游 model 48 用 Concat 产出了它——换成任何其他方式产出的 7.91MB 输入，model 49 都会在同一个地方炸。

Model 49 本身极其简单：

```
输入: 2FConcat_output_0 [1,2,1080,1920] = 7.91MB
        │
        ▼
  /Pad_1 (ReflectionPad2d)
        │
        ▼
输出: 2FPad_1_output_0 [1,2,1088,1920] = 7.97MB (8355840 bytes)
```

### 6.2 编译器处理后（Pass 42 SplitLargeTensor）

编译器在 Pass 42 将唯一的一层 Pad 扩展为 44 个 hw_layers：

| HW Layer 类型 | 数量 | 作用 |
|--------------|------|------|
| DummySliceLayer | 15 | 把输入切成 15 个 tile，每个 72 行 |
| PadLayer | 15 | 对每个 tile 做镜像填充 |
| DummyConcatLayer | 14 | 把 15 个 tile 拼回完整输出 |

### 6.3 Edges 揭示了问题

Pass 42 的 IR 中，edges 只有 4 个全尺寸 tensor：

```
2FConcat_output_0_out     [1,2,1080,1920] = 7.91MB  (输入 copy)
2FConcat_output_0         [1,2,1080,1920] = 7.91MB  (输入)
2FPad_1_output_0          [1,2,1088,1920] = 7.97MB  (Pad 输出)
2FPad_1_output_0_out      [1,2,1088,1920] = 7.97MB  (输出 copy)
```

中间 15 个 Pad tile 的计算结果（每个 540KB）没有作为独立 edge 出现——它们被 DummyConcat 内部消耗了，拼回了全尺寸 `2FPad_1_output_0`。

到 Pass 57 (LiveTimeAnalyse)，全尺寸 tensor 增加到 3 个（多了 `2FPad_1_output_0_layout_in`），小 tensor（552960B = 540KB）有 59 个——输入侧已经全部 tile 化，但输出侧仍然是全尺寸。

### 6.4 为什么输入没事、输出炸了

同一个 8MB 量级的数据，输入和输出的处理方式完全不同：

```
输入 7.91MB（DDR 上）:
  DmaIn → DummySlice 切成 15 个 tile
  每次只搬 540KB 到片上
  片上峰值: 540KB ✅

输出 7.97MB:
  Pad 算完 15 个 tile（每个 540KB）
   DummyConcat 在片上拼成 8.36MB
   再 DmaOut 到 DDR
   片上峰值: 8.36MB ❌ → OOM
```

**输入能过是因为 DmaIn 自带 tile 能力（一次只搬一块），输出炸是因为 DummyConcat 强制在片上拼成全尺寸再出。**

---

## 7. Slice2 与 Concat2 的结构差异

Slice2 和 Concat2 是完全相反的操作：

```
Concat2:                         Slice2:
  [A] [B]  ──拼起来──→  [A B]     [A B C D]  ──切一块──→  [B C]
  两块 → 一块                    一块 → 取其一部分
```

| | Concat2 | Slice2 |
|---|---|---|
| 输入数量 | **2 个**独立输入 | **1 个**输入 |
| 能否时间错开？ | ✅ 两个输入来自不同上游，到达有先后 | ❌ 只有一个输入 |
| 编译器优化 | DummyConcat 消除，两个 DmaIn→DmaOut 串行复用 buffer | 零拷贝视图，无数据搬运，但输出 > 4MB 时仍然失败 |
| 能过的条件 | 输出任意大（因为从不分配全尺寸） | 输出必须 ≤ 4MB |

**Concat 能过不是因为"把 8MB 切成两个 4MB"，而是因为 Concat 本来就有两块独立来源，编译器利用时间差，让它们串行复用同一块片上 buffer。Slice2 只有一块来源，不具备这个条件。**

---

## 8. 子模型序号 = 执行顺序

`iq_model0` → `iq_model1` → ... → `iq_model65` 就是整个推理图的执行流水线。每个子模型是原始大图的一个 split subgraph，按序号串行执行，上一个的输出是下一个的输入：

```
model 0 (Slice)   → 2FSlice_output_0    → model 1 (Bn)
model 1 (Bn)      → 2FMul_output_0       → model 2 (Clip)
...
model 48 (Concat) → 2FConcat_output_0    → model 49 (Pad)
model 49 (Pad)    → 2FPad_1_output_0     → model 50 (Pool)  ← 炸在这里
model 50 (Pool)   → 544×960 缩小输出    → model 51 (Bn)
...
model 61 (Concat) → 2FConcat_1_output_0  → model 62 (Pad)
model 62 (Pad)    → 2FPad_3_output_0     → model 63 (Pool)  ← 同样炸
```

---

## 9. 修复方向（细化）

### 9.1 问题本质

ReflectionPad2d 不会改变数据量级——输入 7.91MB，输出 7.97MB，只多了 60KB 的 padding 边。问题从来不是"Pad 把数据变大了"，而是：

> **同一个 8MB 量级的数据，输入端能 tile 着读，输出端非要一次性分配。**

### 9.2 具体改法

让 Pass 42（SplitLargeTensor）切完计算后，不要用 DummyConcat 在片上拼全尺寸输出，而是给每个 Pad tile 直接挂 DmaOut：

```
现在:
  Pad(tile0) → pad_out_0
  Pad(tile1) → pad_out_1
  ...
  Pad(tile14) → pad_out_14
    → DummyConcat 拼成 8.36MB → DmaOut → DDR
  片上峰值: 8.36MB ❌

改后:
  Pad(tile0) → DmaOut → DDR offset 0         (540KB)
  Pad(tile1) → DmaOut → DDR offset 552960    (540KB)
  ...
  Pad(tile14) → DmaOut → DDR offset 7733760  (540KB)

  片上峰值: 540KB ✅
  DDR 最终: 完整的 8.36MB 输出（15 个 tile 相邻排列）
```

DDR 上最终该是 8.36MB 就是 8.36MB——那是 DDR 的事，DDR 容量远大于 4MB。问题从来不在 DDR，在于**片上内存**装不下这个一次性全尺寸分配。

这和 model 48 的 Concat 串行 DmaOut 是同一个思路：Concat 的 DummyConcat 被消除后，两个输入各自独立 DmaOut 到 DDR 相邻位置。Pad 的 DummyConcat 也应该被消除，让 15 个 tile 各自独立 DmaOut。

---

*记录时间：2025-06-30*
*后续问答继续追加到此文档*
