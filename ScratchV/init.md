# ScratchV 项目初始化文档 — 代码架构全览

> **生成日期**: 2026-06-28 | **版本**: 0.3.0
>
> 本文档是 ScratchV 代码仓的结构化索引，对照 LLVM 编译器架构分层介绍，作为后续所有学习和提问的基础。

---

## 目录

1. [项目身份](#1-项目身份)
2. [对照 LLVM 架构分层](#2-对照-llvm-架构分层)
3. [完整编译管线](#3-完整编译管线)
4. [分层代码详解](#4-分层代码详解)
5. [关键设计决策](#5-关键设计决策)
6. [性能版图与优化方向](#6-性能版图与优化方向)
7. [模块速查表](#7-模块速查表)
8. [关键命令](#8-关键命令)

---

## 1. 项目身份

**ScratchV** 是一个 Python 实现的 AI 编译器，使命是：

> 将 ONNX 深度学习模型编译为 RISC-V 机器码，性能**超越 LLVM**。

核心关键词：
- **源语言**: ONNX (Open Neural Network Exchange) 模型
- **目标架构**: RISC-V RV32IM (整数) / RV64FD (浮点)
- **实现语言**: Python 3.12+（约 38,000 行核心代码）
- **零外部依赖**: 核心编译器路径只用 Python 标准库
- **教育属性**: 所有源码可读、可改、可验证，配套 30 个 topic 模块文档

### 当前性能差距 (cnn.onnx)

| 指标 | LLVM (RV64FD float32) | ScratchV (RV32IM Q16.16) | 差距 |
|------|----------------------|--------------------------|------|
| 静态指令 | 1,059 | 785 | ScratchV 少 26% |
| **动态指令** | **18.5 亿** | **77.7 亿** | **4.2x** |
| 静态指令少但动态多，问题在循环嵌套效率 | | | |

---

## 2. 对照 LLVM 架构分层

ScratchV 的架构设计与 LLVM 经典三段式编译器高度对应：

```
        LLVM                               ScratchV
  ═══════════════                  ═══════════════════

  Clang / 前端语言               ONNX 模型 (.onnx) / DSL (.dsl)
       │                                │
       ▼                                ▼
  ┌──────────────┐            ┌──────────────────────┐
  │  Frontend    │            │  frontend/           │
  │  (C/C++→IR)  │            │  onnx_parser.py      │ ← ONNX→IR
  │              │            │  dsl_parser.py       │ ← DSL→IR
  └──────┬───────┘            │  dsl_extended.py     │ ← 扩展DSL
         │                    └──────────┬───────────┘
         ▼                               ▼
  ┌──────────────┐            ┌──────────────────────┐
  │  LLVM IR     │            │  ir/                 │
  │  (SSA,类型系统)│            │  types.py            │ ← OpCode, Value, DataType
  │              │            │  builder.py          │ ← IRBuilder (构造器)
  └──────┬───────┘            │  printer.py          │ ← IRPrinter (输出)
         │                    └──────────┬───────────┘
         ▼                               ▼
  ┌──────────────┐            ┌──────────────────────┐
  │  Optimizer   │            │  optimizer/          │
  │  (Pass Manager)           │  constant_folding.py │ ← 常量折叠
  │  -mem2reg     │            │  dead_code.py        │ ← 死代码消除
  │  -instcombine │            │  peephole.py         │ ← IR窥孔优化
  │  -licm        │            │  muladd_fusion.py    │ ← 乘加融合
  │  -loop-unroll │            │  licm.py             │ ← 循环不变量外提
  └──────┬───────┘            └──────────┬───────────┘
         ▼                               ▼
  ┌──────────────┐            ┌──────────────────────┐
  │  Backend     │            │  backend/            │
  │  -isel       │            │  instruction_select  │ ← IR→机器指令
  │  -regalloc   │            │  register_alloc.py   │ ← 寄存器分配
  │  -machine-cse│            │  asm_emit.py         │ ← 汇编输出
  │  -asm-printer│            │  riscv_encoder.py    │ ← 机器码编码
  │              │            │  asm_peephole.py     │ ← 汇编窥孔
  │              │            │  inst_scheduler.py   │ ← 指令调度
  │              │            │  cycle_estimator.py  │ ← 5级流水线模拟
  │              │            │  llvm_codegen.py     │ ← LLVM IR 后端
  └──────┬───────┘            └──────────┬───────────┘
         ▼                               ▼
  ┌──────────────┐            ┌──────────────────────┐
  │  Machine     │            │  standalone/         │
  │  Code        │            │  onnx_to_riscv_      │
  │  (x86/ARM..) │            │    standalone.py     │ ← 零依赖全流程
  │              │            │  onnx_to_llvm_       │
  │              │            │    standalone.py     │ ← LLVM IR 生成
  └──────────────┘            └──────────────────────┘
```

**关键差异**:
- LLVM 的 IR 是无类型限制的通用 SSA，ScratchV 的 IR 面向神经网络算子（Conv, Gemm, ReLU 等是一等公民）
- LLVM 有完整的 loop 变换 pass（unrolling, vectorization, interchange），ScratchV 尚无
- LLVM 后端支持数十种架构，ScratchV 专耕 RISC-V

---

## 3. 完整编译管线

ScratchV 有**两条编译路径**共享同一个 IR 前端，在后端分叉：

### 路径 A: ScratchV 原生路径 (Q16.16 定点 → RV32IM)

```
ONNX(.onnx) → ONNXParser → IR(Program) → InstructionSelector
→ RegisterAllocator → AsmEmitter → RISC-V assembly(.s)
                                           │
                                    riscv_encoder.py
                                           │
                                    RV32IM flat binary(.bin)
```

### 路径 B: LLVM 路径 (float32 → LLVM IR → RV64FD)

```
ONNX(.onnx) → ONNXParser → IR(Program) → LLVMCodegen → LLVM IR(.ll)
                                                           │
                                                    外部 llc -O3
                                                           │
                                                    RV64FD assembly(.s)
```

### Pass 执行顺序 (CompilerDriver)

```
1. Parse (onnx / dsl)
2. Verify IR (optional)
3. Optimize:
   basic: constant_folding → dead_code_elim
   all:   + ir_peephole → muladd_fusion → licm
4. Codegen (riscv / llvm)
5. Post-codegen:
   asm_peephole → const_merge → schedule → beautify → count_instr
6. Cycle estimation (optional, 5-stage pipeline simulation)
7. Write output
```

---

## 4. 分层代码详解

### 4.1 Frontend (前端) — `scratchv/frontend/`

对标 LLVM 的 Clang，负责将输入格式翻译为 IR。

| 文件 | 行数 | 职责 |
|------|------|------|
| `onnx_parser.py` | ~256 | ONNX 模型解析。用 `onnx` 库加载 protobuf，逐算子翻译到 IR。支持的算子: Add, Mul, Sub, Div, ReLU, MatMul, GELU, Softmax, MaxPool, Neg, Exp, Conv, Gemm, Sigmoid, Reshape |
| `dsl_parser.py` | - | 自定义 DSL 解析。无 ONNX 依赖时的替代前端 |
| `dsl_extended.py` | - | 扩展 DSL，支持 if/while 控制流 |
| `dsl_errors.py` | - | DSL 语法错误提示 |

**ONNXParser 核心方法**: 按 `op_type` 反射到 `_handle_{op_type}` 方法，逐个翻译节点，同时做输入端的常量折叠。

### 4.2 IR (中间表示) — `scratchv/ir/`

对标 LLVM IR，采用**三地址码 (Three-Address Code) + SSA 风格**。

| 文件 | 职责 |
|------|------|
| `types.py` | IR 类型系统核心。`OpCode`(35 个枚举: 算术/访存/控制流/NN算子), `DataType`(f32/i32/f64/i64), `Value`(SSA值), `Instruction`(三地址码), `BasicBlock`, `Function`, `Program` |
| `builder.py` | `IRBuilder` 类。提供 `add/sub/mul/div/conv/gemm/relu/softmax` 等工厂方法，自动维护 `current_func` 和 `current_block` |
| `printer.py` | `IRPrinter` 类。将 Program dump 为人类可读文本，用于 `--dump-ir` |

**关键设计**: OpCode 直接包含神经网络算子 (CONV, GEMM, RELU, SOFTMAX, GELU, SIGMOID, MAXPOOL, MATMUL, DOT)，而非展开为标量运算。这使得 IR 层级更高，但也要求每个后端都理解这些"高阶"指令。

### 4.3 Optimizer (优化器) — `scratchv/optimizer/`

对标 LLVM 的 Pass Manager，5 个 pass 全部实现为原地修改 Program 的独立类。

| 文件 | 对标 LLVM Pass | 职责 |
|------|---------------|------|
| `constant_folding.py` | `-constprop` | 编译期求值常量运算 (ADD/SUB/MUL/DIV)，替换为 LOAD_CONST |
| `dead_code.py` | `-dce` | 删除结果未被使用的指令，保留有副作用的 (STORE/RETURN/BR 等) |
| `peephole.py` | `-instcombine` | IR 级别的窥孔优化 (模式匹配 + 替换) |
| `muladd_fusion.py` | `-madd` | 识别 `tmp=mul(a,b); sum=add(tmp,acc)` 模式，融合为单条 |
| `licm.py` | `-licm` | 循环不变量外提。分析 FOR/ENDFOR 间的代码，将不变计算移到循环前 |

**当前缺失的 Pass** (vs LLVM -O3):
- 循环展开 (Loop Unrolling): 减少分支、增加指令级并行
- 循环交换 (Loop Interchange): 改善 cache 局部性
- 循环融合 (Loop Fusion): 减少中间 tensor 的 store/load
- 向量化 (Vectorization): 利用 SIMD
- GVN (Global Value Numbering): 消除冗余计算
- 内联 (Inlining): scratchv 的函数粒度较粗

### 4.4 Backend (后端) — `scratchv/backend/`

对标 LLVM 的 CodeGen 层，完成 IR→汇编的全流程。

#### 4.4.1 指令选择 — `instruction_select.py`

对标 LLVM 的 `SelectionDAG` / `GlobalISel`。IR 的每个 OpCode 由专门的 `_select_{opcode}` 方法处理：

- **算术**: ADD→add, SUB→sub, MUL→mul, DIV→div, NEG→sub rd,x0,rs
- **NN 算子**: ReLU→max rd,rs,x0, Conv→bias+MAC(MUL+ADD), GEMM→bias+MAC, Sigmoid→SLT+分支 clamp, MaxPool→SLT+分支 max
- **控制流**: FOR→LI+标签+BGE, ENDFOR→ADDI+J, BR→J, BR_IF→BNEZ+J, RETURN→MV a0+JALR

#### 4.4.2 寄存器分配 — `register_alloc.py`

两种策略:
- **Naive**: 所有虚拟寄存器 spill 到栈，每次计算都 load/store
- **Greedy**: 简单贪心分配。优先使用 caller-saved temp 寄存器 (t0-t6)，满则 LRU spill 最早分配的

`regalloc_linear.py` 提供线性扫描分配器 (更接近 LLVM 的 regalloc)。

#### 4.4.3 汇编输出 — `asm_emit.py`

将 `MachineInstr` 列表转为 GAS 语法汇编文本。支持 ~60 种 RISC-V 指令的文本化输出。

#### 4.4.4 LLVM 后端 — `llvm_codegen.py`

ScratchV IR → LLVM IR 的翻译器。生成标准 LLVM IR 文本 (.ll)，可接 llc/opt/lli 使用。

#### 4.4.5 Post-Codegen Passes

| 文件 | 职责 |
|------|------|
| `asm_peephole.py` | 汇编级窥孔优化 (相邻指令合并/删除) |
| `const_merge.py` | 相邻常量加载合并 (li+li → 单条 li) |
| `inst_scheduler.py` | 指令调度 (构建 DAG + 拓扑排序) |
| `asm_beautifier.py` | 汇编格式化输出 |
| `inst_counter.py` | 指令分类统计 (ALU/MEM/BRANCH/FP) |
| `cycle_estimator.py` | 5 级流水线周期估算 (IF/ID/EX/MEM/WB) |
| `riscv_encoder.py` | 汇编→32-bit 机器码编码 |

### 4.5 Standalone (独立编译器) — `scratchv/standalone/`

**零外部依赖**的完整编译器实现。不走 IR→backend 的常规管线，而是直接从 ONNX protobuf 生成内联 RISC-V 循环。

| 文件 | 行数 | 职责 |
|------|------|------|
| `onnx_to_riscv_standalone.py` | ~1500+ | **核心**。手工 protobuf 解析 → Q16.16 定点转换 → 内存规划 → 逐算子内联循环 → flat binary 输出 |
| `onnx_to_llvm_standalone.py` | ~800+ | 复用 standalone 的 ONNX 解析，生成 float32 LLVM IR |
| `benchmark.py` | ~400+ | RV32IM 仿真器 + 动态指令计数器 |
| `cache_model.py` | - | Set-associative cache 模型 (Hit/Miss 模拟) |
| `spike_sim.py` | ~767 | Spike (官方 RISC-V 仿真器) 包装 |
| `run_spike_bench.py` | ~817 | 带 cache 模型的完整 Spike 仿真 |
| `llvm_cache_compare.py` | - | LLVM vs ScratchV 的 cache 行为对比分析 |
| `tinyfive_compare.py` | ~930 | TinyFive (Python RISC-V 仿真器) 静态对比 |
| `rv32_bench.py` | ~429 | RV32 全量 Benchmark 编排器 |
| `bench_report.py` | - | HTML/JSON/MD 多格式报告生成 |

### 4.6 CI / Dashboard — `scratchv/ci/`

| 文件 | 职责 |
|------|------|
| `ci_benchmark.py` | CI 基准测试编排器 (模型注册→编译→仿真→对比) |
| `dashboard.py` | 性能对比仪表盘生成器 (纯静态 HTML，零外部可视化依赖) |
| `history_page.py` | 优化历史页面 (各版本性能变化趋势) |
| `test_page.py` | CI 产物验证页面 |

### 4.7 Simulator (仿真器) — `scratchv/simulator/`

| 文件 | 职责 |
|------|------|
| `rv32_emulator.py` | RV32IM 全功能仿真器，含完整的 RISC-V 解码器 + NN runtime hooks |
| `tinyfive.py` | TinyFive 仿真器适配器，提供 cycle-accurate 的 RV32IM 仿真 |

### 4.8 Verification (验证) — `scratchv/verification/`

| 文件 | 职责 |
|------|------|
| `verifier.py` | ONNX Runtime / numpy 数值验证。编译结果与参考实现逐元素对比 |

### 4.9 Analysis (分析) — `scratchv/analysis/`

| 文件 | 职责 |
|------|------|
| `cfg_builder.py` | 控制流图 (CFG) 构建 |
| `ir_verifier.py` | IR 结构合法性验证 |

### 4.10 scratchv_dag (DAG 指令选择) — `scratchv_dag/`

实验性 DAG-based 指令选择器 (对标 LLVM 的 SelectionDAG):

| 文件 | 职责 |
|------|------|
| `sdnode.py` | SDNode 定义 (DAG 节点) |
| `selection_dag.py` | DAG 构建、DAG 合并、DAG 调度 |
| `allocator.py` | 寄存器分配器适配 |
| `cache.py` | DAG 节点缓存 |

---

## 5. 关键设计决策

### 5.1 Q16.16 定点运算

```
float32 → int(float × 65536) & 0xFFFFFFFF

32-bit 整数:
  [31:16] 整数部分 (范围 -32768 ~ 32767)
  [15:0]  小数部分 (精度 1/65536 ≈ 1.5e-5)

乘法: MUL a, b → 64-bit → SRAI 16 截断 (a×b×2^32 → (a×b)×2^16)
加法: ADD a, b  直接加 (小数点对齐)

代价: 每个 MAC (乘累加) 需 ~30 条 RV32IM 指令
收益: 可在无 FPU 的 RV32IM 核上运行深度推理
```

### 5.2 双路径设计

| 维度 | 原生路径 | LLVM 路径 |
|------|---------|-----------|
| 数值 | Q16.16 int32 | float32 |
| 目标 | RV32IM | RV64FD |
| 指令/MAC | ~30 条 | ~2 条 |
| 输出 | flat binary | LLVM IR → llc |
| 依赖 | Python stdlib | llvmlite / llc |

### 5.3 Zero-Dependency 策略

Standalone 编译器的 ONNX 解析是**手工实现 protobuf wire-format 解析器**，不依赖 `onnx` Python 包。这确保:
- 可在任何能运行 Python 3.8+ 的环境编译
- 生成的 flat binary 可在 bare-metal RISC-V 核上直接执行
- 权重嵌入二进制，无需外部文件

---

## 6. 性能版图与优化方向

### 当前数据 (cnn.onnx: 3×Conv + 3×MaxPool + 2×FC, @28×28 输入)

| 指标 | LLVM (baseline) | ScratchV | ScratchV 优化前 |
|------|----------------|----------|----------------|
| 动态指令 | 18.5 亿 | 32.2 亿 | 77.7 亿 |
| 动态 ALU | 5.25 亿 (28.4%) | - | 46.6 亿 (60%) |
| 动态 Load | 5.27 亿 (28.6%) | - | 15.6 亿 (20.1%) |
| 动态 Store | 0.03 亿 (0.2%) | - | 5.19 亿 (6.7%) |
| D$ 命中率 | 88.75% | 88.75% | 88.75% |

**优化历史**: 从 77.7 亿 → 32.2 亿 (已减 58.7%)

### 根因分析 (为什么 ScratchV 仍慢 1.74x)

1. **Q16.16 定点开销** — 每条 MAC ~15 条整数指令，LLVM float32 只需 `fmul+fadd` ≈ 2 条
2. **无循环变换** — LLVM -O3 自动 loop unrolling/interchange/vectorization，ScratchV 无
3. **地址计算开销** — 无 GEP，手动 MUL+ADD 链 ~5 条/次
4. **中间 Store 过多** — ScratchV 每个输出元素都需要 SW 写回

### 超越路线

1. 算子融合 (Conv+ReLU/MaxPool 端到端)
2. 循环变换 (unrolling, interchange, tiling 改善 cache)
3. 内存布局优化 (CHW→HWC)
4. 如果硬件支持 SIMD，定制向量指令

---

## 7. 模块速查表

```
scratchv/                     ← 编译器核心 (~38K 行)
├── compiler.py               ← CompilerDriver + PassManager (515行)
├── main.py                   ← CLI 入口 (272行)
├── pass_interface.py         ← CompilerPass / PassResult 基础接口
├── frontend/                 ← [Layer 1] 前端
│   ├── onnx_parser.py        ← ONNX → IR (256行)
│   ├── dsl_parser.py         ← DSL → IR
│   ├── dsl_extended.py       ← 扩展 DSL (if/while)
│   └── dsl_errors.py         ← 错误提示
├── ir/                       ← [Layer 2] 中间表示
│   ├── types.py              ← OpCode(35), Value, Instruction, BasicBlock, Program (207行)
│   ├── builder.py            ← IRBuilder 工厂类 (210行)
│   └── printer.py            ← IR 文本输出
├── optimizer/                ← [Layer 3] 优化器 (5 pass)
│   ├── constant_folding.py   ← 常量折叠 (82行)
│   ├── dead_code.py          ← 死代码消除 (71行)
│   ├── peephole.py           ← IR 窥孔
│   ├── muladd_fusion.py      ← 乘加融合 (77行)
│   └── licm.py               ← 循环不变量外提 (125行)
├── backend/                  ← [Layer 4] 后端
│   ├── machine_types.py      ← MachineOp(63种), MachineOperand, MachineInstr (177行)
│   ├── instruction_select.py ← IR→RISC-V 指令选择 (368行)
│   ├── inst_select_ext.py    ← 扩展指令选择 (fp64/sqrt/min/max/abs)
│   ├── register_alloc.py     ← 寄存器分配 (naive/greedy, 227行)
│   ├── regalloc_linear.py    ← 线性扫描分配器
│   ├── asm_emit.py           ← 汇编发射器 (160行)
│   ├── llvm_codegen.py       ← LLVM IR 后端 (570行)
│   ├── asm_peephole.py       ← 汇编窥孔优化
│   ├── const_merge.py        ← 常量加载合并
│   ├── inst_scheduler.py     ← 指令调度
│   ├── cycle_estimator.py    ← 5级流水线模拟
│   ├── riscv_encoder.py      ← 汇编→32-bit 机器码
│   ├── asm_beautifier.py     ← 汇编格式化
│   └── inst_counter.py       ← 指令统计
├── standalone/               ← [Layer 5] 零依赖独立编译器
│   ├── onnx_to_riscv_standalone.py  ← 主编译器 (~1500+行)
│   ├── onnx_to_llvm_standalone.py   ← LLVM IR 生成 (~800+行)
│   ├── benchmark.py          ← RV32IM 仿真器
│   ├── cache_model.py        ← Cache 模型
│   ├── spike_sim.py          ← Spike 包装
│   ├── run_spike_bench.py    ← 完整仿真
│   ├── llvm_cache_compare.py ← LLVM vs ScratchV cache 对比
│   ├── tinyfive_compare.py   ← TinyFive 静态对比
│   ├── compare_codegen.py    ← 代码生成质量对比
│   ├── rv32_bench.py         ← RV32 全量 Benchmark
│   └── bench_report.py       ← 多格式报告生成
├── ci/                       ← CI 编排 + Dashboard
│   ├── ci_benchmark.py       ← CI 基准测试
│   ├── dashboard.py          ← 性能仪表盘
│   ├── history_page.py       ← 优化历史
│   └── test_page.py          ← 测试页面
├── simulator/                ← RISC-V 仿真器
│   ├── rv32_emulator.py      ← RV32IM 全功能仿真
│   └── tinyfive.py           ← TinyFive 适配器
├── verification/             ← 验证
│   └── verifier.py           ← ONNX Runtime/numpy 验证
├── analysis/                 ← 分析
│   ├── cfg_builder.py        ← CFG 构建
│   └── ir_verifier.py        ← IR 验证
├── codegen/                  ← (占位)
└── memory/                   ← (占位)

scratchv_dag/                 ← 实验性 DAG 指令选择
├── sdnode.py
├── selection_dag.py
├── allocator.py
└── cache.py

benchmarks/                   ← 23 个 DSL 基准用例
tests/                        ← 单元测试 (面向主要模块)
docs/                         ← 30 个 topic 模块文档 + 5 篇入门指南
models/                       ← 测试用 ONNX 模型
```

---

## 8. 关键命令

```bash
# 环境
make quick-start       # 打印新手引导
pip install -e .       # 安装 scratchv

# 测试
make test              # 运行全部 pytest

# CNN 编译 (原生路径)
python scratchv/standalone/onnx_to_riscv_standalone.py models/graph/cnn.onnx \
    -o output.bin --asm output.s --estimate --report

# CNN 编译 (LLVM 路径)
python scratchv/standalone/onnx_to_llvm_standalone.py models/graph/cnn.onnx \
    -o output.ll --compare

# CI 全量对比 (LLVM vs ScratchV → HTML dashboard)
make bench-ci

# 命令行快速编译
scratchv model.onnx -o output.s --optimize all --beautify --peephole-asm --count-instr

# LLVM vs ScratchV 缓存对比
python scratchv/standalone/llvm_cache_compare.py

# TinyFive 仿真验证
python scratchv/standalone/tinyfive_compare.py

# Dashboard 生成
python scratchv/ci/dashboard.py --run -o dashboard.html

# Harness 验证
python .claude/harness/verify/run.py --level L2
```

---

> **文档说明**: 本文档基于 2026-06-28 对 ScratchV 代码仓的完整扫描生成。每个模块的文件行数、类名、方法名均来自实际源码。后续所有对话将以本文档为项目认知基础，涉及具体代码细节时回溯相关源文件验证。
