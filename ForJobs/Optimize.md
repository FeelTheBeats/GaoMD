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
在分析 IR 时我发现，对于 struct/array 类型的字段访问，编译器在某些情况下不会自动做完全的冗余 load 消除，尤其是在：
    ```
    通过 getelementptr (GEP) 多次计算相同地址
    或者经过轻微变形（不同 GEP 但语义相同）
    ```
    对于这种情况GVN很容易出现不命中的情况，导致同一个内存位置被多次 load
实现：
    我对同一个 basic block 内的 load 指令做扫描，通过对其地址表达式（GEP）进行规范化（canonicalization），识别出指向相同 base + offset 的内存访问，然后将后续的 load 替换为前面的结果。
注意点：
    中间必须没有store(值没有改变)
为什么要做这个优化：
    区别于LLVM的 GVN/EarlyCSE 的通用优化，我激进地优化了GEP被使用的场景：
        - 激进的GEP等价识别
        - offset的归一化
    特别适用于：
        - Array of Struct（结构体数组）
        - 深层嵌套的GEP
完整回复：
    ```
        我之前做过一个针对 LLVM IR 的中端优化，是一个基于 memory range 的冗余 load 消除。

    一开始我是做 (base, offset) 级别的 load CSE，但后来发现对于 array/struct 类型，这种方式不够，因为很多访问其实是“子区间关系”，而不是完全相同的地址。

    所以我把内存访问建模成 (base pointer, [start, end)) 的区间形式，并在 basic block 内维护一个已加载区间的集合。

    当遇到新的 load 时，如果它的访问区间被已有区间完全覆盖，我就通过 extract 或类似方式从已有 value 中构造子值，从而避免新的内存访问。

    在实现上，我做了保守的正确性控制，比如：

    遇到 store 时，如果与已有区间重叠就会 invalidate
    遇到 call / volatile / atomic 会作为 barrier
    alias 分析只在 base pointer 完全一致时生效

    这个优化在 struct/array 密集访问的场景下效果比较明显，相比普通的 load CSE 能进一步减少子字段访问带来的冗余 load，在一些 case 中 load 数量下降可以达到 30% 以上。
    ```
这段代码本质是一个“区间版的 MemCSE + store invalidation”，是 LLVM Memory 优化的一个简化模型。    
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