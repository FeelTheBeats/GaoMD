# ScratchV 测试套件拆解

> 运行命令: `python3 -m pytest tests/ -v --tb=short`
> 统计: 348 条用例, 22 个模块, 覆盖编译器完整流水线

---

## 1. 前端 — 源码 → IR

| 模块 | 用例数 | 测什么 |
|------|--------|--------|
| `test_parser.py` | 8 | DSL 解析器: `c = a + b`、`relu(x)`、`matmul(A,B)`、`gelu(x)` 等语法能否正确生成 IR |
| `test_dsl_extended.py` | 22 | 扩展 DSL 控制流: `if (x > 0) { ... } else { ... }`、`while (i < 10) { ... }` 解析, 嵌套 if/while, label 唯一性, 非法语法拒绝 |
| `test_dsl_errors.py` | 27 | 错误诊断系统: 语法错误创建、彩色/无色格式化、`^~~` 列标记、错误收集器上限、fix hint 建议 |
| `test_ir.py` | 6 | IR Builder: 从 DSL 构建 IR 程序 (add/sub/relu/for 循环/多 basic block), 验证 IR dump 格式 |
| `test_cnn_pipeline.py` | 24 (4 skipped) | CNN 端到端: ONNX 模型加载→IR 编译→汇编生成→二进制编码→仿真执行→输出校验。skipped 是因 onnxruntime 未安装 |

## 2. 中间端 — IR 优化与分析

| 模块 | 用例数 | 测什么 |
|------|--------|--------|
| `test_ir_verifier.py` | 14 | IR 验证器: SSA 合规、def-before-use、block 终止指令、label 存在性、类型一致性、不可达代码检测 |
| `test_cfg_builder.py` | 20 | 控制流图: CFG 节点/边构建、前驱/后继、可达性分析、支配树、自然循环检测 (含嵌套)、不可达代码消除、DOT 导出 |
| `test_optimizer.py` | 5 | 基础优化: 常量折叠 (`add 2,3 → 5`)、死代码消除 |
| `test_optimizer_advanced.py` | 7 | 高级优化: IR peephole (`addi x,0` 消除, `mul x,1` 消除)、Mul-Add 融合、LICM (循环不变量外提) |

## 3. 后端 — IR → 汇编

| 模块 | 用例数 | 测什么 |
|------|--------|--------|
| `test_backend.py` | 6 | 经典后端三阶段: 指令选择 (add/relu→RISC-V)、贪心/朴素寄存器分配、汇编发射 |
| `test_inst_select_ext.py` | 14 | 扩展指令选择: neg/sub/load/store、FP64 类型检测与开关 |
| `test_regalloc_linear.py` | 16 | 线性扫描寄存器分配: 活跃区间计算与重叠检测、重命名、溢出处理、空 block 边界 |
| `test_llvm_codegen.py` | 9 | LLVM IR 对照路径: add/relu/mul/sub/gelu/div/neg/exp/for 循环 → LLVM IR |
| `test_inst_scheduler.py` | 16 | 指令调度器: 数据依赖 DAG、拓扑排序、周期估计、WAW 依赖、自定义延迟模型 |

## 4. 后端优化 — 汇编级 Pass

| 模块 | 用例数 | 测什么 |
|------|--------|--------|
| `test_asm_peephole.py` | 17 | 汇编 Peephole: addi+addi 合并、li+addi 融合、beq zero→j、冗余 mv 消除、多轮迭代 |
| `test_const_merge.py` | 15 | 常量合并: lui+addi→li 伪指令 (含负数符号扩展)、跨寄存器不合并、有中间指令不合并 |
| `test_asm_beautifier.py` | 23 | 汇编美化器: 解析标注/标签/伪指令/内存操作数、自动注释生成、section/function 头插入 |

## 5. 验证与仿真

| 模块 | 用例数 | 测什么 |
|------|--------|--------|
| `test_verification.py` | 13 | 数值正确性: Numpy 参考 vs DSL 解释器 (add/mul/relu/gelu/matmul/exp/neg/softmax) |
| `test_simulator.py` | 5 | 仿真器: 指令计数、寄存器读写、内存访问追踪、空汇编边界 |

## 6. 基础设施

| 模块 | 用例数 | 测什么 |
|------|--------|--------|
| `test_logger.py` | 18 | 日志系统: 分级、自动前缀、层级命名、文件输出、彩色开关、phase 日志 |
| `test_bench_runner.py` | 17 | 基准测试框架: 用例发现/执行、超时、HTML/JSON/MD 报告、统计汇总 |
| `test_inst_counter.py` | 20 | 指令统计: 操作码提取/分类 (ALU/Mem/Branch/Jump/Pseudo)、两文件对比、HTML 报告 |

---

## 流水线全景

```
DSL/ONNX 源码
    │
    ▼  [test_parser] [test_dsl_extended] [test_dsl_errors] [test_cnn_pipeline]
  ScratchV IR
    │
    ▼  [test_ir] [test_ir_verifier]
  验证后的 IR
    │
    ▼  [test_optimizer] [test_optimizer_advanced] [test_cfg_builder]
  优化后的 IR ──── [test_llvm_codegen] ──→ LLVM IR (对照路径)
    │
    ▼  [test_backend] [test_inst_select_ext] [test_regalloc_linear] [test_inst_scheduler]
  RISC-V 汇编
    │
    ▼  [test_asm_peephole] [test_const_merge] [test_asm_beautifier]
  优化后的汇编
    │
    ▼  [test_simulator] [test_verification] [test_inst_counter]
  执行 / 验证 / 统计
```
