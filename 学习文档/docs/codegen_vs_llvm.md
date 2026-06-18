# AIC Codegen 与 LLVM Codegen 的异同

---

## 相同点

### 1. 都有 Machine IR 层

- LLVM 有 `MachineFunction` + `MachineBasicBlock` + `MachineInstr`
- AIC 有 `AnalyseGraph` + `order_to_node`（执行序）+ `AnalyseNode`（包 `HwLayer*`）
- 都在这一层之后才做最终指令发射

### 2. 都有 MC 层的指令抽象

- LLVM: `MCInst` → `MCStreamer` → object file
- AIC: `MCInstr` → `HwLayerInfoRecord`（收集 uint64_t）→ `GenFiles` 写出 .o
- 两边都是一条指令 = 一个 opcode + 一组操作数，最后编码成二进制

### 3. 代码生成和文件输出分离

- LLVM: CodeGen 生成 `MCInst`，`AsmPrinter` / `ObjectWriter` 负责写文件
- AIC: `HwLayer::Codegen()` 生成 `uint64_t` 序列，`GenFiles` Pass 负责写出 .o / .asm / .tlf

---

## 关键不同

### 1. 没有寄存器分配

这是最大的区别。AIC 是 VLIW 风格的固定功能加速器，tensor 直接用物理地址寻址：

```
LLVM:     vreg1 = load [addr]  →  regalloc  →  R4 = load [addr]
AIC:      DMA_In {src_addr=0x1000, dst_addr=0x2000, size=4096}
```

没有虚拟寄存器，没有 spill，没有 live interval 分析——这些在 AIC 里被**内存分配 Pass**（MemAlloc / HwLayerMemAlloc）替代了。地址在 codegen 之前就已经确定，codegen 只管往 MCInstr 的操作数里填地址值。

### 2. 没有指令选择（Instruction Selection）

```
LLVM:     (add i32 %a, %b)  →  Pattern Match  →  ADD32rr / ADD32ri / ...
          一条 IR 指令可能对应多条目标指令，需要选最优的

AIC:      Conv2dLayer  →  固定生成 CONV_CFG + MAC_CORE_CFG + STORE_FM_CFG + ...
          HwLayer 到 MCInstr 的映射是写死的，没有 pattern matching
```

### 3. 没有指令调度（Instruction Scheduling）

```
LLVM:     多条独立的 MachineInstr 可以重排以填满流水线

AIC:      执行顺序由 AnalyseGraph::order_to_node 确定，不可改变
          硬件是顺序执行的，没有乱序，没有超标量
```

### 4. 内存分配在 codegen 之前，而不是过程中

```
LLVM:     regalloc 是 codegen 的一个阶段（通常和其他阶段交叉）

AIC:      MemAlloc → HwLayerInplace → LiveTimeAnalyse → HwLayerMemAlloc
          ↓ 全部完成，地址已确定
          Codegen（直接用地址填操作数）
```

### 5. Group 机制 — LLVM 没有对应物

AIC 的 `Codegen::RunOnModule()` 把连续的同类无同步 HwLayer 打包成 Group，每个 Group 有 Header/Tail/Sync。这更像给硬件生成**命令列表**（command list），而不是传统意义上的指令序列。LLVM 里没有这个概念。

### 6. 单 Pass，无多阶段

```
LLVM CodeGen 管线:
  DAG → ISel → Schedule → RegAlloc → PrologEpilog → Peephole → MC

AIC Codegen 管线:
  PreCodeGenPass → Codegen（单Pass） → 完成
```

每个 HwLayer 的 `Codegen()` 一次性生成全部指令，没有迭代优化。

---

## 总结

| | LLVM | AIC |
|---|---|---|
| 核心工作 | 指令选择 + 寄存器分配 + 调度 | **填操作数**（地址/尺寸/stride → bit域） |
| 复杂度来源 | 通用 CPU 的灵活性 | 固定加速器的确定性 |
| Codegen 是 | 编译器的"后端之王"，最复杂的部分 | 相对简单：地址都有了，照模板填指令就行 |
| 真正难的 | 寄存器分配、指令调度 | **内存分配和 Cascade**（都在 codegen 之前做完了） |

本质原因：LLVM 面向通用 CPU（有寄存器文件、乱序执行、多种指令变体），AIC 面向固定功能 NPU（VLIW + 物理地址 + 确定的指令模板）。所以 AIC 把"难的部分"放在了内存分配和级联优化，codegen 本身反而简单直接。
