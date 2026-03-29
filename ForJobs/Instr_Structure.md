# 计算机体系与指令集

## 1.你熟悉的指令集（如 x86 或 RISCV）有哪些？
- x86(CISC)
    变长指令集
    支持复杂寻址模式：`base + index * scale + offset`
    指令语义丰富： `例如一条指令完成 load + op`
    pattern多，不好match，DAG->Match 的时候情况很多，需要有复杂的匹配逻辑。
- RISCV
    定长 32-bit 指令（基础 ISA）
    load/store 架构（运算不访问内存）
    指令格式规整（R/I/S/B/U/J）
    32个通用寄存器，且ABI明确
- 不同
    ```
        在 LLVM 中，不同 ISA 主要体现在：
            TableGen 描述指令（.td 文件）
            Instruction Selection（SelectionDAG / GlobalISel）
            Register Bank / Register Class 定义
            TargetLowering（合法化 + lowering）
    ```
总结：
    ```
    1. x86 将复杂性放在 instruction selection 和硬件 decode（µops 展开）
    2. RISC-V 将复杂性更多交给 编译器的 instruction scheduling 和指令组合
        - x86：关注 µops / port pressure / latency
        - RISC-V：关注 RAW 依赖 / load-use delay
    ```
## 2.RISCV 的基本寄存器和指令类型有哪些？
RISC-V 有 32 个通用寄存器 x0 到 x31，其中 x0 恒为 0，并有清晰的 ABI 约定，比如 a0–a7 用于参数传递。
指令类型主要包括 load/store、算术逻辑、控制流和立即数构造等，且采用严格的 load/store 架构，只有 load/store 指令可以访问内存。
同时 RISC-V 指令格式规整（R/I/S/B/U/J），没有像 x86 那样的隐式状态（如 flags），因此在编译器后端中 instruction selection 更简单，但需要更多指令并依赖调度优化性能。

寄存器数量多，Calling Convention清晰：
    **通用寄存器：x0~x31**
    浮点寄存器：f0~f31
    向量寄存器：v0~v31
    PC寄存器：pc
从编译器角度看，x86 的寄存器较少且存在 flags 等隐式状态，使得寄存器分配和指令调度更复杂；同时其指令可以直接操作内存，instruction selection 空间更大。
而 RISC-V 拥有更多通用寄存器、无隐式状态，且严格 load/store，使得 IR 到指令的映射更直接，但需要生成更多指令并依赖调度优化性能。
### 为什么 RISC-V 没有 flags？
RISC-V 去掉 flags 是为了避免隐式状态带来的依赖链，使数据依赖完全通过寄存器显式表达，从而提升指令级并行性并简化编译器和硬件实现。

### x0 = 0 对编译器有什么好处？
x0 提供了一个恒为 0 的寄存器，使编译器不需要额外生成加载常量的指令，同时减少寄存器占用，并能用来实现 move、clear、比较等操作，降低 register pressure 并简化优化。

### load-use hazard 怎么处理？
1. 插入无关指令
2. 硬件forwarding(不等待store直接拿给对应指令用)
    load结果直接从pipeline中转发
3. stall 等待 load 完成 (最坏情况)
    当一个指令依赖于 load 结果时，为了避免 pipeline 气泡，通常会插入一个 stall 指令，等待 load 完成后再继续执行。
load-use hazard 是指 load 指令的数据尚未准备好就被后续指令使用。通常通过编译器的 instruction scheduling 在中间插入无关指令，或依赖硬件 forwarding 来减少延迟，最差情况下需要插入 stall。RISC-V 更依赖编译器调度来隐藏这种 latency。
## 3.LLVM 后端如何支持新的指令集架构？
```
LLVM IR
  ↓
Instruction Selection（SelectionDAG / GlobalISel）
  ↓
MachineInstr（目标无关但接近硬件）
  ↓
Register Allocation
  ↓
Instruction Scheduling
  ↓
AsmPrinter → 汇编 / Obj
```
在 LLVM 中支持新的指令集架构，本质是实现一个新的 Target Backend。
核心包括通过 TableGen 描述寄存器、指令和 pattern，通过 TargetLowering 完成 IR 到目标操作的合法化，再通过 SelectionDAG 或 GlobalISel 完成 instruction selection，生成 MachineInstr。
随后进行寄存器分配和指令调度，最后通过 AsmPrinter 和 MC 层生成目标汇编或机器码。
整体流程就是从 IR 到 MachineInstr 再到最终目标代码的逐步 lowering 和优化。

### 👉 “TableGen 是怎么生成 matcher 的？”
TableGen 会把 .td 中定义的指令 pattern 编译成一个 DAG matcher，本质是一个模式匹配自动机。在 SelectionDAG 阶段，这个 matcher 会遍历 DAG 节点，根据 opcode、操作数类型和约束进行匹配，并生成对应的 MachineInstr。
### 👉 “SelectionDAG 和 GlobalISel 区别？”
SelectionDAG 会将 IR 转换为 DAG 结构并在其上进行模式匹配，而 GlobalISel 直接在 Machine IR 上逐步进行 legalize 和 instruction selection。相比之下，GlobalISel 更模块化、易扩展，是 LLVM 新一代的指令选择框架。
### 👉 “TargetLowering 什么时候会介入？”
TargetLowering 主要在 legalization 阶段介入，包括类型合法化和操作合法化，同时也可以通过 custom lowering 将某些 IR 操作映射为目标特定的指令序列或模式，是 IR 向目标指令过渡的关键组件。
Type/Operand/CustomLowering
    1. TypeLowering：负责将 LLVM IR 中的类型（如 i32/f32）转换为目标 ISA 中的寄存器类型（如 GPR/FPR）。
    2. OperandLowering：负责将操作数（如寄存器、内存地址、立即数）转换为目标 ISA 中的具体表示（如寄存器编号、内存偏移量、立即数值）。
    3. CustomLowering：一些复杂操作（如 vector 指令、浮点运算等）需要自定义 lowering，TargetLowering 会调用相应的函数进行转换。
### 👉 “寄存器分配和 ISA（Instruction Set Architecture） 有什么关系？”
ISA 决定了寄存器的数量、类型以及使用约束，比如 x86 的寄存器较少且有特殊用途，而 RISC-V 有更多通用寄存器且约束较少。这些都会直接影响寄存器分配的复杂度、spill 频率以及最终生成代码的性能。
## 4 什么是指令调度（Instruction Scheduling），为什么重要？
指令调度是根据指令之间的依赖关系和目标架构的资源约束，对指令执行顺序进行重排，以减少流水线停顿并提高指令级并行性。
做了什么：
    建立依赖图（Dependency Graph）
    分析 latency
    指令重排
为什么重要：
    避免stall
    提高ILP
    利用硬件资源
```
指令调度是根据指令之间的依赖关系以及目标架构的资源约束，对指令执行顺序进行重排，以减少流水线停顿并提高指令级并行性。
它的核心目标是隐藏指令延迟，比如在 load 和其使用之间插入独立指令，从而避免 load-use stall。
在 LLVM 中，调度既可以发生在寄存器分配之前，也可以发生在之后，前者主要优化并行度，后者更多考虑寄存器约束和 spill。
因此指令调度对性能非常关键，它直接影响 pipeline 的利用率和 stall 频率。
```
## 5 CPU 流水线与编译器优化有什么关系？
CPU 流水线通过让多条指令在不同阶段重叠执行来提高吞吐，但会受到数据依赖、资源冲突和分支等因素的影响，从而产生 stall。
编译器优化的目标之一就是减少这些 stall，比如通过指令调度重排指令顺序来隐藏延迟，通过寄存器分配减少内存访问，通过循环展开和向量化提高指令级并行性。
本质上，编译器是在静态阶段优化代码，使其更好地适配 CPU 流水线，从而提高执行效率。

### 👉 “scoreboard / Tomasulo 和编译器调度的关系？” 
Scoreboard 和 Tomasulo 是硬件层面的动态调度机制，在运行时根据数据依赖和资源状态决定指令执行顺序；而编译器调度是在编译期根据依赖和目标架构模型对指令进行重排。两者解决的是同一类问题，但信息来源不同，编译器是静态预测，硬件是动态决策，因此它们是互补关系。
### 👉 “为什么 OoO(Out-of-Order Execution（乱序执行）) CPU 仍然需要编译器调度？”
虽然 OoO CPU 可以在运行时动态重排指令，但它的窗口是有限的，而且硬件成本较高，只能做局部优化。而编译器在编译期拥有全局信息，可以通过指令调度、循环优化等手段生成更有利于并行执行的指令序列，从而提高 OoO 的利用效率。因此两者是互补关系。