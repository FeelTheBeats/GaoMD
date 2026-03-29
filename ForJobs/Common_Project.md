# 5️⃣ 项目经验与团队协作
## 遇到过哪些难点，你是如何解决的？
1. XDK
    StringHash的Bugfix
        - IR级别：被其他优化Pass删除了必要的metadata（GDB-debug找到所有删除点进行单独筛选）
                在GEP的内容替换时，没有考虑入参为phi的情况。最后实现为递归替换。
        - 链接器：和用户没有沟通好生成`hash-string`对的文件头与文件结构与具体编码方式，返工了两次
        - section的对齐错误：在IRPass添加了对齐属性
    **寄存器Spill失败：**
        现象为二进制运行报错，用rcd抓取pc值，发现了某pc死锁，通过反汇编查看对应pc的指令，定位到某函数。
2. 仓颉
    - PowerOf2结构match失败，对目标IR不明确，最后参考了InstCombine的实现
    - IR变化导致的用例性能劣化，通过比对某patch前后的IR，发现IR的不一致导致了LoopUnroll展开后的IR没有Inline时候更优。询问前端团队是因为加了某句打印导致IR生成时某Function到达了ThreadsHoud。找PL重新设计了Inline策略。
3. 
## 你如何向团队成员解释复杂的优化策略？
设计文档：总体原理/实现优化的前后关系/具体实现/结果验证
视频讲述
CodeReview

## 如果需要快速上手一个新架构（如 RISCV），你的学习思路是什么？
```
可以用分层的方法快速上手一个新架构。
首先从 ISA 入手，理解指令分类、寄存器模型以及基本汇编生成；
然后补 ABI，掌握函数调用约定和栈布局；
接着结合微架构分析 pipeline、latency 和 hazard，从性能角度理解指令行为；
在此基础上，我会直接进入 LLVM backend，重点看 TableGen 的指令定义、指令选择和调度模型；
最后通过实现一个小的优化 pass（如 peephole 或 load forwarding）来验证理解并形成工程闭环。
```
ABI 定义了程序在二进制层面的运行规则，包括函数调用、寄存器使用、栈布局和数据表示，是连接 ISA 和操作系统/编译器的关键桥梁。
ABI 不决定“用什么指令”（pattern），但决定“这些指令必须如何使用寄存器和栈才能正确运行”。

```
ABI
├── Calling Convention
├── Register Usage
├── Stack Frame Layout
├── Data Layout
├── Object File Format (ELF)
├── System Call Interface
├── (Optional)
│   ├── Exception Handling
│   ├── Floating-point / Vector ABI
│   ├── TLS
│   └── Dynamic Linking
```
## 在团队协作中，你如何处理代码冲突和优化策略的分歧？