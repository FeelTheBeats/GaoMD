这是一个非常好的问题，而且也是**AI Compiler 从"会写 Pattern"到"会设计优化 Pass"**的分水岭。

先说结论：

> **这些 Fusion Pattern 并不是随便总结出来的固定套路，而是几十年来 Compiler（LLVM、TVM、XLA、TensorRT、MLIR、Glow、OneDNN 等）不断沉淀出来的一类"等价变换（Rewrite）"。**
>
> 新增 Fusion 的依据，不是"别人有没有写过"，而是**是否满足融合收益 > 融合代价**。

---

## 第一层：这些 Fusion 本质上属于什么？

其实几乎所有 AI Compiler 的 Fusion 都可以归纳成几类。

### 第一类：Producer-Consumer Fusion（最经典）

就是你的这些：

```
Conv
   │
Relu
```

变成

```
Conv(RelU)
```

或者

```
Conv
   │
Pool
```

变成

```
Conv(Pool)
```

或者

```
Conv
 │
BN
 │
Relu
```

变成

```
Conv(BN+Relu)
```

这种就是

> **Producer 把结果直接交给 Consumer，不落内存。**

这是所有 AI Compiler 最重要的一类 Fusion。

你的这些 Pattern 几乎全部属于这里：

```
ConvActFusion
ConvPoolFusion
ConvActPoolFusion
PoolActFusion
ActPoolFusion
```

都是 Producer-Consumer。

---

## 第二类：Elementwise Fusion

例如

```
Add
 │
Relu
```

变成

```
AddRelu
```

或者

```
Mul
 │
Sigmoid
```

变成

```
MulSigmoid
```

TensorRT 特别喜欢做这个。

例如

```
x+y
 ↓
Relu
```

GPU kernel 一起完成。

你的

```
Eltwise -> Relu
```

就是这一类。

---

## 第三类：Operator Folding

不是运行时 Fusion，而是参数折叠。

例如

```
Conv
 │
BatchNorm
```

其实

```
BN
```

可以提前算进

```
weight
bias
```

于是

```
Conv+BN
```

直接变

```
Conv(new_weight,new_bias)
```

BN 消失了。

这是推理框架最常见优化。

---

## 第四类：Layout Fusion

例如

```
Transpose
 │
Conv
```

如果 Conv 支持 NHWC

那就不用真的 transpose。

变成

```
Conv(NHWC)
```

Transpose 消失。

例如

```
Pad
 │
Conv
```

你的

```
AsymmetricalPadFusion
```

就是 Layout Fusion。

因为 Pad 本来就是 Conv 的参数。

---

## 第五类：Kernel Fusion

例如

```
MatMul
 │
Bias
 │
Relu
```

GPU 上写成一个 CUDA kernel。

不是 IR 消失。

而是

```
Launch一次
```

而不是

```
Launch三次
```

TensorRT、TorchInductor 非常喜欢。

---

## 第二层：为什么这些模式都是 Conv 开头？

因为 Conv 是 AI 芯片最贵的算子。

假设

```
Conv
```

耗时

```
100 us
```

Relu

```
2 us
```

Pool

```
5 us
```

如果不融合：

```
Conv 写DDR

Relu 读DDR

Relu 写DDR

Pool 读DDR

Pool 写DDR
```

真正浪费的是：

```
DDR
```

而不是

```
Relu
```

所以

Conv 后面的任何轻量算子，

几乎都值得融合。

这就是为什么大家最爱写

```
Conv+XXX
```

---

# 第三层：那新增 Fusion 应该依据什么？

这里就是 Compiler Engineer 最重要的思维。

不是：

> 有没有这个 Pattern？

而是：

> 为什么值得 Fusion？

一般有五条判断标准。

---

## 第一条：有没有中间 Tensor

例如

```
Conv
 │
Relu
```

产生一个

```
200MB
```

Tensor。

Relu 只是读一下。

融合后

```
Tensor 根本不用写。
```

收益巨大。

所以：

> **中间 Tensor 越大，Fusion 越值。**

---

## 第二条：Producer 是否支持这个功能

例如 Conv 本来就支持：

```
activation_type

padding

stride

dilation
```

那

```
Pad
Relu
Bias
```

当然可以融合。

但是如果 Conv 根本没有

```
Softmax
```

那

```
Conv+Softmax
```

基本不能融合。

所以第二条就是：

> **硬件是否支持。**

---

## 第三条：数据依赖是否简单

例如

```
Conv
 │
Relu
```

只有一个消费者。

很好融合。

但是

```
      Conv
     /   \
 Relu    Add
```

Conv 有两个用户。

融合之后

```
Add
```

怎么办？

很多 Compiler 就不会融合。

因此：

> 单消费者最好。

---

## 第四条：有没有数学等价

例如

```
Pad
 │
Conv
```

等价于

```
Conv(padding)
```

数学完全一样。

再例如

```
BN
```

可以折进 Weight。

也是数学等价。

没有数学等价，

Compiler 一般不会做。

---

## 第五条：硬件收益够不够

例如

```
Exp
 │
Log
```

理论可以融合。

但是

```
ExpLog
```

没有任何收益。

没人写。

所以

Fusion 永远是：

```
收益 > 开发成本
```

---

# 第四层：真正设计 Fusion 时，一般怎么想？

很多公司的 Compiler 都会画一张类似这样的表：

| Pattern      | Memory ↓ | Kernel ↓ | Hardware Support | 值得写吗 |
| ------------ | -------- | -------- | ---------------- | ---- |
| Conv→Relu    | ⭐⭐⭐⭐     | ⭐⭐       | ✅                | 必写   |
| Conv→BN      | ⭐⭐⭐⭐     | ⭐⭐⭐      | ✅                | 必写   |
| Conv→Pool    | ⭐⭐⭐      | ⭐⭐       | ✅                | 必写   |
| Add→Relu     | ⭐⭐       | ⭐⭐       | ✅                | 推荐   |
| Relu→Clip    | ⭐        | ⭐        | 部分支持             | 看情况  |
| Exp→Log      | ⭐        | ⭐        | ❌                | 不写   |
| Softmax→TopK | ⭐        | ⭐        | 很少支持             | 很少写  |

所以，一个新的 Fusion Pattern 是否值得加入，通常可以按下面的思路评估：

1. **先证明正确性**：融合前后语义是否完全一致？是否有数值精度、边界条件或广播规则等问题？
2. **看硬件能力**：目标 NPU/GPU 是否已经支持对应的融合指令、融合算子或可配置参数？如果硬件无法执行，IR 层融合可能反而限制后续优化。
3. **分析性能收益**：能否减少中间 Tensor 的读写、减少 Kernel Launch、降低 DMA 次数、提高片上缓存利用率或流水线效率？
4. **评估适用范围**：这是一个只在少数模型出现的特殊模式，还是 ResNet、YOLO、Transformer 等大量模型都会命中？命中率越高，投入价值越大。
5. **控制复杂度**：新的 Pattern 是否会与已有 Pattern 冲突，是否需要复杂的优先级和合法性判断，维护成本是否可接受？

---

如果你以后做的是 **AI Compiler Backend（尤其是 NPU Compiler）**，我建议逐步建立一种更偏硬件的思维方式：

> **看到一个计算图，不是先想"能不能融合"，而是先问："这里为什么要把结果写回 DDR？如果我就是这颗 NPU 的架构师，我会不会愿意在硬件里增加一个控制位、一个寄存器字段或一条微指令，让这个中间结果根本不落内存？"**

当你开始从**硬件执行代价**而不是**图匹配模式**来思考时，你设计出来的 Fusion 往往会更加合理，也更符合实际 AI 编译器后端的发展方向。
