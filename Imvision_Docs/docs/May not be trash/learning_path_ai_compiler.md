# AI 编译器学习路径

> 2026-06-22，基于当前 aic_v3 PatternMatcher 重构工作中的知识盲区整理。

---

## 一、硬件单元（4 个 PE）

优先读完 `Imvision_Docs/docs/source/hw_pes/` 下的四个文件：

| PE | 文件 | 核心功能 |
|----|------|---------|
| DMA | `dma.md` | DDR ↔ L1 数据搬运（RDMA x2 + WDMA x1），最吃带宽 |
| MTE | `mte.md` | 向量转置引擎，Slice/Concat/Permute/Reshape 最终映射到这 |
| MPU | `mpu.md` | 矩阵乘加单元，Conv2d/FC/Matmul 的主力算力 |
| VPU | `vpu.md` | 逐元素向量单元，Eltwise/Activation/Reduce/BatchNorm |

理解目标：知道每个 PE 接受什么指令格式、输出什么格式、有什么限制（C 上限、LUT 大小、32B 对齐等）。你重构的每个 pass 本质上都在做"上层算子 → 硬件基本指令序列"的翻译。

---

## 二、图操作代价模型

核心直觉：**`Graph::Resolve()` 不是廉价操作**。

```cpp
// 坏模式（旧代码常见）：每匹配一个算子就 Resolve 一次
for (...) {
    net->ReleaseNode(op->Index());
    net->Resolve();   // O(N+E) 全图拓扑排序 + shape 推导
}

// 好模式（BatchRewriter）：攒到最后一次 Resolve
for (...) {
    rewriter.RemoveNode(op->Index());
}
rewriter.Commit();    // 只调一次 Resolve
```

`Resolve()` 内部做的事情（`include/aic/graph/graph.h`）：
- 重建邻接表（`BuildAdjacency`）
- 全局拓扑排序（`TopologicalSort`）
- 每个 tensor 的 shape/dtype/pattern 推导（`ShapeInfer`）
- 死节点回收

如果图有 500 个节点、N 个匹配，旧代码调 N 次 Resolve = O(N²E)。BatchRewriter 调 1 次 = O(E)。

---

## 三、三层 IR 与 Pass 分层

你的 `aic_v2_structure.md` 已经写得很好。关键要点：

| 层 | 图类型 | 节点类型 | 能做的优化 |
|----|--------|---------|----------|
| L1 | `Net` | `Operator`（硬件无关） | **Lowering**：复杂算子拆成基本算子 |
| L2 | `KernelNet` | `Kernel`（感知 L1 大小） | **融合 + 消冗**：FusedOp, SliceFuse, ConcatEliminate |
| L3 | `AnalyseGraph` | `AnalyseNode`（感知地址） | **Cascade + In-place + 同步**：真正决定性能 |

**判断一个 pass 属于哪层**：
- 在 `src/transforms/` → L1（声明式，硬件无关）
- 在 `target/tensor_brain/transforms/` → L2/L3（自包含式，硬件强相关）

---

## 四、AI 编译器通用概念

### 必读文章

1. **Glow: Graph Lowering Compiler for Neural Networks** (Facebook, 2019)
   - 讲为什么编译器需要分层 lowering
   - Glow 的分层设计和 AIC 的三层 IR 思路一致
   - 理解"lowering ≠ 优化"的核心概念

2. **MLIR: Pattern Rewrite Infrastructure**
   - `PatternMatcher` / `PatternBuilder` / `BatchRewriter` 的概念来源
   - 声明式匹配 vs 命令式遍历的优劣
   - 理解为什么 `PatternBuilder.Chain("A","B").Attr("A", lambda)` 比手写 for 循环好

### 可选参考

3. **TVM: Bring Your Own Codegen** — 讲了算子编译器（codegen）和计算图编译器的区别
4. **XLA: Operation Semantics** — HLO 的算子拆分逻辑，和 AIC 的 complex_op_split_* 类似
5. **Triton: Introduction** — 如果未来想理解"为什么有些算子不能 tiling"

---

## 五、AI 芯片设计文档怎么用

只读两章：**指令集** 和 **内存层次**。不看微架构（PE 内部怎么实现浮点乘加）。

你需要知道的不是"VPU 内部有几个 ALU"，而是：
- 一条 Conv2d 指令接受什么输入布局（NCHW? NHWC?）、权重格式、输出格式
- L1 buffer 多大、几个 bank、对齐要求
- Cascade 模式下的数据路径（L1 驻留 vs DDR 写回）

这直接决定了：
- 为什么 `PermuteReplaceReshape` 有 32B 对齐检查
- 为什么 `TilingSinCos` 要计算 `total_footprint` 和 `safe_local_mem_limit`
- 为什么 `ConvTranspose2dSplit` 要逐字段拷贝 `conv_attr.xxx = cur_op->attr().xxx`

---

## 六、当前工作速查

| 想看什么 | 去哪看 |
|---------|--------|
| 三层 IR 全景 | `aic_v2_structure.md` |
| PatternMatcher 走读 | `PLANS/plan1_aic_v3_pattern_match_restructure/PATTERN_MATCHER_CODE_REVIEW.md` |
| SliceFuse 重构 | `PLANS/plan1_aic_v3_pattern_match_restructure/SLICE_FUSE_REFACTOR_ANALYSIS.md` |
| PermuteReplaceReshape 重构 | `PLANS/plan1_aic_v3_pattern_match_restructure/PERMUTE_REPLACE_RESHAPE_REFACTOR.md` |
| 2026-06-17 学习日记 | `diary/learning_journal_20260617.md` |
| 各算子硬件文档 | `docs/source/operators/hw/details/*.md` |
| 硬件 PE 文档 | `docs/source/hw_pes/*.md` |
