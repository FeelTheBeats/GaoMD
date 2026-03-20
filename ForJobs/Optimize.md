# 2️⃣ 性能分析与优化

## 1.你如何定位程序性能瓶颈？有哪些工具和方法？
分层定位（系统 → 程序 → IR → 指令）
### 宏观层：系统级 Profiling
使用 perf / VTune / perfetto
关注：
    CPU cycles
    cache miss（L1/L2/L3）
    branch miss
判断是：
    计算瓶颈（CPU bound）
    内存瓶颈（memory bound）
我会先用 perf 确认热点函数和瓶颈类型，比如是否是 cache miss 或 branch miss 导致。
### 函数/源码级分析
perf report / flame graph
定位：
    热点函数（hotspot）
    高频循环
找“时间花在哪”，而不是盲目优化
### 编译器 IR 层分析
分析：
    是否存在冗余 load/store
    是否有多余分支
    是否 missed optimization（比如没 vectorize）
使用：
    -Rpass=loop-vectorize
    -fsave-optimization-record
我会结合 IR 看是否有优化机会，比如 GVN、LICM 是否生效。

### 汇编 / 微架构级
`objdump / llvm-mca`
看：
    指令依赖链（dependency chain）
    pipeline stall
    ILP（指令级并行）
如果 IR 看起来合理，我会进一步分析汇编是否存在 pipeline stall 或调度不佳。
## 2.举例说明一次中后端优化带来的性能提升。
todo


## 3.解释软硬件联合优化策略（如缓存对齐、流水线优化）的实现思路。
### 缓存对齐（Cache Alignment）
问题：
    未对齐访问 → cache line split → 多次访存
编译器做法：
    数据结构对齐（padding）
    loop tiling / blocking：将循环体分为多个 block，每个 block 大小为 cache line 大小，从而减少 cache miss。
### 流水线优化 （Pipeline Optimization）
问题：
    指令依赖 → pipeline stall
编译器策略：
    Instruction Scheduling
    Loop unrolling（增加 ILP）
    Software pipelining
编译器会通过数据布局优化（如对齐）减少 cache miss，通过指令调度和 loop unroll 提高 ILP，从而更好匹配 CPU pipeline。

## 4.在编译器中如何减少分支预测失败对性能的影响？
**分支预测失败会导致 pipeline stall，从而降低整体执行吞吐。**
Enless Branch：if-conversion -> select 进而避免 morebranch 指令。
Opt Branch Layout：hot branch 放到前面，cold branch 放到后面，从而减少分支预测失败的概率。(PGO)
循环优化：减少循环次数，例如循环展开、循环合并、向量化等。


## 5.解释寄存器调度（Register Scheduling）对性能的作用。
本质上是为了减少指令之间的依赖，提高指令并行度，从而减少 pipeline stall 时间。
指令层面要对指令进行重新排序，使得指令之间的依赖更少。
从寄存器层面来看，要尽量使用不同的寄存器存储不同的变量，避免寄存器冲突，减少Spill 次数。
**Register Scheduling 的核心是通过指令重排减少数据依赖带来的 stall，同时结合寄存器分配减少 spill，从而提升整体执行吞吐。**

## 6.每个阶段产物的命令
```shell
clang -Xclang -ast-dump -fsyntax-only test.c
clang -S -emit-llvm test.c -o test.ll
opt -print-after-all test.ll
llc -stop-after=isel test.ll -o test.mir
llc -print-after-all test.ll
```