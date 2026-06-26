# FusedOp Pass 分析

> Kernel 层最重要的算子融合优化 pass。904 行，9 种融合模式，操作对象是 KernelNet（L2 IR）。

---

## 功能

将相邻的 Kernel 合并为一个融合 Kernel（`ConvFusionKernel`），消除中间 tensor 的 DDR 读写。

**举例**：`Conv2d → Activation` 两个 Kernel 各需要 DDR→L1→DDR 的搬运。融合后 DMA 只搬一次输入，计算在 L1 内连续完成，最后只写一次输出。省了一次 DDR 往返。

---

## 9 种融合模式

| 方法 | 融合模式 | 说明 |
|------|---------|------|
| `ConvActFusionPattern` | Conv2d → Activation | 最常见的融合，Conv + ReLU/Sigmoid 等 |
| `ConvPoolFusionPattern` | Conv2d → Pool2d | 卷积后直接池化 |
| `ConvActPoolFusionPattern` | Conv2d → Activation → Pool2d | 三层连续融合 |
| `ConvPoolActFusionPattern` | Conv2d → Pool2d → Activation | 同上，顺序不同 |
| `BiInterpActFusionPattern` | BilinearInterp → Activation | 双线性插值 + 激活 |
| `ReluFusionPattern` | Eltwise → Activation(ReLU) | VPU 层的激活融合 |
| `ActPoolFusionPattern` | Activation → Pool2d | 无卷积的激活+池化 |
| `PoolActFusionPattern` | Pool2d → Activation | 池化后激活 |
| `AsymmetricalPadFusionPattern` | Pad → Conv2d | 非对称填充融合进卷积 |

---

## 调用顺序

```
FusedOp::RunOnModule
  ├── AsymmetricalPadFusionPattern   // Pad → Conv
  ├── ReluFusionPattern              // Eltwise → Act
  ├── ConvActFusionPattern           // Conv → Act
  ├── ConvActPoolFusionPattern       // Conv → Act → Pool
  ├── ConvPoolFusionPattern          // Conv → Pool
  ├── ConvPoolActFusionPattern       // Conv → Pool → Act
  ├── BiInterpActFusionPattern       // Interp → Act
  ├── ActPoolFusionPattern           // Act → Pool
  └── PoolActFusionPattern           // Pool → Act
```

**9 个方法有序执行**。前一个融合的结果可能成为后一个融合的输入（例如 Conv→Act 融合后的 `ConvFusionKernel` 可能被 ConvActPoolFusionPattern 再次融合）。因此**顺序不可换**。

---

## 通用融合流程

以 `ConvActFusionPattern` 为例，每种融合遵循相同步骤：

```
1. 遍历 KernelNet 拓扑序
2. CastNoCheck<Conv2dKernel> 匹配种子节点
3. 检查约束（output edge count、dtype、bin_mode）
4. OutputNodesBegin() 遍历下游，匹配 ActivationKernel
5. 创建 ConvFusionKernel（复制 Conv + Act 的属性）
6. 连接：fusion_kernel.SetInputs(conv.input)
           fusion_kernel.SetOutputs(act.output)
7. 更新 ref_model.json（记录融合信息供后续验证）
8. kernel_net->ReleaseNode(conv) + ReleaseNode(act)
9. kernel_net->Resolve()
```

---

## 关键数据结构

```cpp
class ConvFusionKernel : public Kernel {
  Conv2dAttr     conv_attr;     // 卷积参数
  ActivationAttr act_attr;      // 激活参数
  Pool2d2Attr    pool_attr;     // 池化参数（可选）
  bool           is_act;        // 是否包含激活
  bool           is_pool;       // 是否包含池化
  bool           order;         // Act 在 Pool 前还是后
};
```

融合后的 Kernel 内部 HwGraph 会把多个操作串成一条硬件指令链：

```
ConvFusionKernel.HwGraph:
  DMA_In → Conv_Layer → Act_Layer → Pool_Layer → DMA_Out
```

全部在 L1 内完成，不写回 DDR。

---

## 与 PatternMatcher 的关系

这是 PatternMatcher 最有价值的应用场景：**多节点子图匹配 + 约束检查**。

当前 FusedOp 的每个 FusionPattern 都是手写遍历 + 指针追踪：

```cpp
// 当前：手写
for (auto index : graph_viewer.GetNodesInTopologicalOrder()) {
    Conv2dKernel *conv = CastNoCheck<Conv2dKernel>(node);
    if (!conv || conv->GetOutputEdgesCount() > 1) continue;
    auto *act = CastNoCheck<ActivationKernel>(&*conv->OutputNodesBegin());
    if (!act || act->attr_ref().bin_mode == 1) continue;
    // ...
}
```

如果用 PatternMatcher：

```cpp
// 重构后：声明式
auto pattern = PatternBuilder("ConvActFusion")
    .MatchNode("conv", NodeType<Conv2dKernel>())
    .MatchNode("act",  NodeType<ActivationKernel>())
    .Chain("conv", "act")
    .SingleUse("conv")
    .Attr("act", [](const Node& n) {
        return CastNoCheck<const ActivationKernel>(&n)->attr_ref().bin_mode != 1;
    })
    .Build();
```

**收益**：消除嵌套指针追踪、约束 check 集中在 Attr 中、匹配和改写解耦。

---

## 使用方式

```cpp
// 编译时自动调用，无需手动配置
// main.cpp → RegisterPasses() → FusedOp 被 PM_REGISTER_PASS 自动注册
// 关闭方式：命令行参数 --disable-fused-op-opt
```
