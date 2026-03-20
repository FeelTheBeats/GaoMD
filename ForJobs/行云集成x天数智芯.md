````markdown
# GPU 编译器面试题整理（行云集成电路 & 天数智芯）

---

# 🧪 一、行云集成电路（LLVM Backend 导向）

> 核心考察：是否具备“落地指令集”的编译器工程能力

---

## 🧠 第一轮：基础能力（必须稳）

### Q1
LLVM 后端整体流程是什么？从 IR 到汇编经历了哪些阶段？

---

### Q2
SelectionDAG 和 GlobalISel 的区别是什么？各自适用场景？

---

### Q3
Machine IR 是什么？为什么需要这一层？

---

### Q4
LLVM 中寄存器分配是怎么做的？说两种算法及优缺点  
**追问：**
- spill 什么时候发生？
- register pressure 怎么衡量？

---

### Q5
你做过的一个 Pass，详细讲设计 + 数据结构 + 优化效果

---

## 🔧 第二轮：工程实现（核心考察）

### Q6（高频）
如果让你支持一个新 ISA，你会怎么做？

必须包含：
- TableGen
- Instruction Selection
- RegisterInfo
- Calling Convention
- AsmPrinter

---

### Q7
TableGen 的作用是什么？你用过吗？  
**追问：**
- 为什么不用 C++ 硬写？
- `.td` 文件本质是什么？

---

### Q8
Instruction Selection 是怎么做的？

---

### Q9
LLVM 怎么做指令调度？  
**追问：**
- latency vs throughput
- list scheduling

---

## ⚙️ 第三轮：场景题（拉开差距）

### Q10
如果某个程序在你支持的 ISA 上性能很差，你如何定位问题？

```text
IR → Machine IR → 汇编 → perf → hotspot → 瓶颈分析
````

---

### Q11

如何优化寄存器使用，减少 spill？

---

### Q12

如何设计一个简单的 peephole optimization？

---

## 🧩 第四轮：发散题（看上限）

### Q13

LLVM IR 和 Machine IR 最大区别是什么？

---

### Q14

编译器优化为什么有时候会让性能变差？

---

### Q15

你怎么看 GlobalISel 的未来？

---

---

# 🚀 二、天数智芯（GPU + 编译器导向）

> 核心考察：能否将编译器能力映射到 GPU 性能优化

---

## 🧠 第一轮：GPU 基础

### Q1

GPU 和 CPU 的本质区别是什么？

---

### Q2

什么是 SIMT？和 SIMD 的区别？

---

### Q3

什么是 warp？warp divergence 会发生什么？

---

### Q4

GPU memory hierarchy 是怎样的？

至少包含：

* global memory
* shared memory
* register

---

## ⚡ 第二轮：性能理解（关键）

### Q5

什么是 memory coalescing？为什么重要？

---

### Q6

什么是 kernel fusion？为什么能提升性能？

---

### Q7

什么时候程序是 memory-bound？什么时候 compute-bound？

---

## 🔧 第三轮：编译器 + GPU（核心）

### Q8（高频）

编译器如何优化 GPU 程序？

必须包含：

* loop tiling
* fusion
* unroll
* register pressure 控制

---

### Q9

如果一个 kernel 性能很差，你怎么分析？

```text
profile → memory/compute → warp效率 → 优化策略
```

---

### Q10

为什么 GPU 更怕分支？

---

### Q11

如何减少 global memory 访问？

---

## 🧩 第四轮：MLIR（加分项）

### Q12

为什么需要 MLIR？

---

### Q13

MLIR 中 dialect 的作用是什么？

---

### Q14

从 MLIR lowering 到 LLVM IR 的大致过程？

---

## 🧠 第五轮：开放题（区分强弱）

### Q15

如果让你设计一个 GPU 编译器，你会怎么分层？

---

### Q16

如何在编译阶段决定 kernel 的 tile size？

---

### Q17

你觉得 GPU 编译器最难的点是什么？

---

---

# 🎯 使用建议

## Step 1

优先准备「行云」题目（你的强项）

## Step 2

再补「天数」题目（GPU 思维）

## Step 3

准备 3 个关键回答：

1. 一个 LLVM Pass（深入）
2. 一个性能优化案例
3. 一个 GPU 优化思路（即使没做过）

---

# 📌 总结

* 行云：考察 **LLVM Backend 深度**
* 天数：考察 **GPU + 编译器迁移能力**

👉 策略：

> 用 LLVM 打底，用 GPU 思维加分

```
```
