# LLVM 中后端与编译器基础

## 1.LLVM IR 的基本组成和数据结构有哪些？
- Module
顶级容器、对应一个编译单元
包含：GV、Function、Symbol Table、DataLayout、Metadata
- Function
执行单元
结构：`define i32 @main(xxx)`
包含：Arg、Returntype、BB
特点：强类型签名、支持external/intrinsic
- BB
CFG的节点，之包含一段顺序执行的指令。
一定以一个`terminator`结束：
```
br/ret/switch/invoke
```
- Instruction
Every line is Instruction!
包含：Type/Operand/SSA-value
```
alloca/load/store
br/ret/phi
call/invoke
```
- Value
Every can be used is a `Value`!!!!!
```
Instruction/Arg/Constant/GV
```
可以使用USE-DEF链

- Metadata
调试信息，一些数据结构可以携带 metadata！
## 2.LLVM 中 Pass 的分类和执行顺序如何？
- 作用范围
1. ModulePass
全局优化/跨函数分析
如：`Inline/GlobalOpt/Dead Global Elimination`
2. Call Graph SCC Pass
是基于调用图的-强连通分量(SCC)
意义：处理递归函数，保证调用图稳定
用于：函数内联，函数属性推导
3. FunctionPass
作用域单个函数（大部分优化都在这）
如：InstCombine/GVN(全局值编号)/SROA/SimplifyCFG
这里不关心其他函数，是优化的主战场，因为粒度适中，相对独立！
4. LoopPass
作用于循环
如：LoopUnroll/LICM(Loop Invarient Code Motion)/LoopVectorize
依赖于：LoopInfo/DominatorTree
- 功能
1. Analysis Pass
DominatorTree/LoopInfo/AliasAnalysis/ScalarEvolution
2. Transformation Pass
InstCombine/GVN/DCE/Inline
3. Utility Pass (辅助)
VerifierPass/PrintModulePass

```
ModulePassManager
 ├── ModulePass
 └── CGSCCPassManager
      └── FunctionPassManager
           └── LoopPassManager
```
- 优化流水线
```
SimplifyCFG
SROA
EarlyCSE
Inline
GVN
LICM
LoopUnroll
Vectorize
DCE
```
分段执行，反复清理IR

- 重复执行
一个优化会暴露新的优化机会
`InstCombine → GVN → InstCombine`
## 3.解释从 AST 到 LLVM IR 再到目标指令的整体流程。
```
Source Code
   ↓
Lexer + Preprocessor
   ↓
Parser
   ↓
AST（语法 + 语义）
   ↓
CodeGen（AST → LLVM IR）
   ↓
LLVM IR（SSA）
   ↓
Optimization Pipeline（Passes）
   ↓
Optimized IR
   ↓
Instruction Selection（IR → Machine IR）
   ↓
Machine IR（Target-dependent）
   ↓
Register Allocation
   ↓
Assembly / Object Code
```
## 4.LLVM 后端如何进行寄存器分配？常见算法有哪些？
```
LLVM IR
  ↓
Instruction Selection
  ↓
Machine IR（含 vreg）
  ↓
Register Allocation   ← 这里
  ↓
Prolog/Epilog 插入
  ↓
Assembly
```
同时活跃的变量不能分配到同一寄存器/寄存器数量有限
**本质是图着色问题**
```
1. Live Range
2. Interference Graph
3. Register Classes
    不同类型寄存器：
        GPR（通用寄存器）
        FPR（浮点寄存器）
        Vector 寄存器
            👉 每个 vreg 只能分配到对应 class
4. Spill Slot(vreg → stack slot)
```
- 主流的寄存器分配算法
1. Greedy Register Allocator(`Live Interval + 贪心 + 分裂（split）`)
```
1. Live Range Splitting
2. Spill Heuristic(谁被spill)
3. Eviction(驱逐)
```
2. Linear Scan Register Allocation(`按时间顺序扫描 live interval`)
超级快，扫描完就分配，不够就spill，太贪心了。但是质量没有图着色好。
3. Graph Coloring
速度不够快，理论最优。
4. PBQP（Partitioned Boolean Quadratic Programming）
复杂寄存器约束

### 下面这些知识必须掌握
```
第一阶段（必须掌握）

LiveIntervals

liveness analysis

interference 判断

第二阶段（核心能力）

RegAllocGreedy.cpp

spill heuristic

live range splitting

这些了解：
coalescing

rematerialization

target-specific constraints
```
## 5.解释 LLVM 如何做指令选择（Instruction Selection）。


如何实现一个简单的优化 Pass？举例说明。

LLVM 中循环优化（Loop Unroll、Loop Vectorize）是如何实现的？

LLVM 如何处理函数内联（Function Inlining）？优化前后有什么变化？

解释死代码消除（DCE）在 LLVM 中的实现原理。

LLVM 如何进行全局值编号（GVN）优化？