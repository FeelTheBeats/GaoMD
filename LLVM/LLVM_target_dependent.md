# LLVM Target Dependent
## IR OPT
但注意一个工程细节：
有些 pass 会“参考 target 信息”，但仍运行在 IR 上
例如：
`TargetTransformInfo（TTI）`
告诉你：某种指令在目标机器上“贵不贵”

## Instruction Selection（关键分水岭）
常见实现：
```
SelectionDAG（经典）
GlobalISel（新框架）
FastISel（快速但弱）
```
✅ IR 被“降级”为目标指令
✅ 引入寄存器概念（虚拟寄存器）
✅ 明确目标架构（x86 / ARM / RISC-V）