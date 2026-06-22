# Codegen 相关 Pass 走读指南

> 覆盖从 PreCodeGen 到 GenFiles 的完整代码生成链路。

---

## 1. 走读路线图

```
第1步: 基础设施         第2步: 同步与准备        第3步: 核心Codegen      第4步: 后处理与输出
HwLayerInfoRecord      InsertSync               Codegen::RunOnModule    AdjustIOOrderPass
CmdInfo                SyncAnalyse              HwLayer::Codegen()      Analyze
MCInstr                InsertIdle               HwLayer::Codegen-       GenFiles
HwLayer基类方法         PreCodeGenPass           SyncInst/Header/Tail
```

---

## 2. 第1步：基础设施（先理解"指令"是什么）

### 文件清单

| 文件 | 内容 | 优先级 |
|------|------|--------|
| `include/aic/machine_code/mcinstr.h` | `MCInstr` 类 — 一条机器指令 | ⭐⭐⭐ |
| `include/aic/machine_code/mcinstr_desc.h` | `MCInstrDesc` — 指令描述符（opcode、操作数布局） | ⭐⭐ |
| `include/aic/machine_code/mcinstr_info.h` | `MCInstrInfo` — 指令集元信息表 | ⭐ |
| `include/aic/file_out/hw_layer_info_record.h` | `CmdInfo` + `HwLayerInfoRecord` — 指令容器 | ⭐⭐⭐ |

### MCInstr — 一条机器指令

```cpp
// include/aic/machine_code/mcinstr.h
class MCInstr {
  string opc_;           // opcode 字符串，如 "DMA_IN_INFO_0", "CONV_CFG"
  MCInstrDesc desc_;     // 指令描述符：操作数名、bit位宽、bit偏移
  uint64_t bin_;         // ★ 最终编码为一个64位整数
  string asm_;           // 汇编文本表示

  // 设置操作数（按名字索引，自动编码到正确的bit位）
  void SetOperand(name, uint64_t val);           // 纯数值操作数
  void SetOperand(name, string_view val_str);    // 助记符操作数（如 "a"→0, "b"→1）
  void SetOperand(name, vector<string_view>);    // 位掩码操作数（多bit独立置位）

  uint64_t data() const { return bin_; }         // 获取编码后的64位值
  string GenAsmStr();                            // 生成汇编文本
};
```

**关键理解**：整个编译器最终产出的"指令"就是一堆 `uint64_t` 的序列。`MCInstr` 负责把语义操作数（"源地址=0x1000"）编码为硬件规定的位域格式。

### CmdInfo + HwLayerInfoRecord — 指令容器

```cpp
// include/aic/file_out/hw_layer_info_record.h
struct CmdInfo {
  string asm_str;       // 汇编文本（调试用）
  uint64_t cmd;         // 编码后的64位指令
};

class HwLayerInfoRecord {
  deque<uint64_t> cmds_;    // ★ 指令序列：一个 HwLayer 产出的所有 MCInstr
  string asms_;             // 汇编文本

  void RecordCmd(const CmdInfo&);     // 追加一条指令
  void RecordCmdToHead(...);          // 在开头插入一条指令（用于header）
  uint32_t CmdSize();                 // 指令条数
};
```

**层次关系**：
```
HwLayerInfoRecord           一个 HwLayer 的指令集合
    │
    ▼
HwGraphInfoRecord           = vector<HwLayerInfoRecordPtr>  一个 HwGraph 的指令
    │
    ▼
KernelInfoRecord            = HwGraphInfoRecord              一个 Kernel 的指令
    │
    ▼
KernelNetInfoRecord         = vector<KernelInfoRecord>       整个模型的指令
```

### HwLayer 基类的 Codegen 框架方法

```cpp
// target/tensor_brain/include/tensor_brain/hw_layer.h
class HwLayer : public Node {
  // ★ 子类必须实现
  virtual Status Codegen() = 0;
  virtual void CodegenSyncInst() = 0;           // 生成同步 set/clr 指令
  virtual void CodegenHeaderInsts(...) = 0;      // 生成模块头（cmd数、校验和）
  virtual void CodegenTailInsts(...) = 0;        // 生成模块尾（校验和）

  // 基类提供的实现（子类调用这些）
  void CodegenSyncInstImpl(opcode_header_name);         // 通用同步指令模板
  void CodegenHeaderInstsImpl(head_str, ...);            // 通用模块头模板
  void CodegenTailInstsImpl(tail_str, check_sum);       // 通用模块尾模板

  HwLayerInfoRecord* GetHwLayerInfoRecord();            // 获取指令容器
};
```

**每个 HwLayer 子类的 Codegen 职责**：
- `Codegen()` — 生成自己的计算/DMA 指令，写入 `HwLayerInfoRecord`
- `CodegenSyncInst()` — 生成与本层相关的同步 set/clr 指令（放在模块头）
- `CodegenHeaderInsts()` — 写模块头：hardlayer_num, cmd_num, cmd_id
- `CodegenTailInsts()` — 写模块尾：check_sum

---

## 3. 第2步：同步与准备（Codegen 前必须完成的工作）

### 文件清单

| 文件 | 功能 | 优先级 |
|------|------|--------|
| `target/tensor_brain/transforms/insert_sync_pass.cpp` | 在 HwLayer 间插入同步屏障 | ⭐⭐⭐ |
| `target/tensor_brain/transforms/sync_analyse.cpp` | 验证同步正确性，优化同步位置 | ⭐⭐ |
| `target/tensor_brain/transforms/insert_idle_pass.cpp` | 插入 Idle 等待周期 | ⭐⭐ |
| `target/tensor_brain/transforms/pre_codegen_pass.cpp` | 最终地址绑定、Broadcast 类型设置 | ⭐⭐ |

### InsertSync — 插入同步屏障

```cpp
// 核心逻辑（简化）
for (auto& [order, node] : graph->GetOrderToNodeMap()) {
  for (auto& pred_edge : node->GetRelationships().input_edges) {
    AnalyseNode* pred = order_to_node_[pred_edge.in_order];

    // 原则：不同硬件类型之间、有 RAW 依赖的 HwLayer 之间插入 sync
    if (NeedSync(pred, node)) {
      pred->GetHwLayer()->InstSyncSet(node->GetHwLayer());  // pred完成后发信号
      node->GetHwLayer()->InstSyncClr(pred->GetHwLayer());  // node执行前等信号
    }
  }
}
```

**关键数据结构 `InstSync`**：每个 HwLayer 有 `inst_sync_` 字段，记录它需要 set 哪些信号、clr 哪些信号。在 Codegen 阶段，`CodegenSyncInst()` 根据这些信息生成实际的 SYNC_SET/SYNC_CLR 指令。

### SyncAnalyse — 验证与优化同步

遍历 AnalyseGraph，检查所有数据依赖都有正确的同步保护。优化不必要或位置不佳的同步。

### InsertIdle — 插入等待周期

当两个硬件操作之间存在最小间隔要求时，插入 IDLE 指令。Idle 不执行任何计算，只是等待指定周期数：
```cpp
MCInstr idle("IDLE_INFO");
idle.SetOperand("idle_cnt_threshold", idle_cycle_);
hw_layer_info_record_->RecordCmd({idle.GenAsmStr(), idle.data()});
```

### PreCodeGenPass — 代码生成前最后配置

设置 VPU Broadcast 类型标记（如 `11c_to_hwc`），为 Codegen 阶段的硬件约束检查做准备。

---

## 4. 第3步：核心 Codegen

### 4.1 Codegen::RunOnModule — 总调度

**文件**: `target/tensor_brain/transforms/codegen_pass.cpp`

```cpp
Status Codegen::RunOnModule(Module &mod) {
  // 1. 获取 AnalyseGraph（通过 BuildAnalyseGraph 的 PassResult）
  auto *pr = GetModulePassResult("BuildAnalyseGraph");
  AnalyseGraph *graph = pr->graph;
  auto order_to_node = graph->GetOrderToNodeMap();

  // 2. 按执行序遍历，跳过 Dummy 层
  //    - 遇到 DMA_In → 记录输入 tensor 加载顺序
  //    - 遇到 DMA_Out → 记录输出 tensor 写出顺序
  for (auto& [order, node] : order_to_node) {
    if (node->IsDummy()) continue;
    if (node->IsIODmaInNode())  RecordAndUpdateDmaIn(...);
    if (node->IsIODmaOutNode()) RecordAndUpdateDmaOut(...);
    node_list.push_back(node);
  }

  // 3. 分组：将连续的无同步依赖的同类 HwLayer 打包为一个 Group
  auto group_list = GetHwLayerGroupList(node_list);

  // 4. 按 Group 执行 Codegen
  for (auto& group : group_list) {
    // 4a. 每个 HwLayer 生成自己的计算指令
    for (uint32_t order_id : group) {
      hw_layer_ptr->SatisfyHardwareConstrain();  // 硬件约束检查
      hw_layer_ptr->Codegen();                   // ★ 生成计算指令
    }

    // 4b. Group 头部：模块头 + 同步指令
    hw_layer_front->CodegenHeaderInsts(group.size(), cmd_num, cmd_id);
    hw_layer_front->CodegenSyncInst();

    // 4c. Group 尾部：模块尾 + Idle
    hw_layer_back->CodegenTailInsts(check_sum);
    hw_layer_back->CodegenIdleInstsIfNeeded();
  }
}
```

**流程图**：
```
AnalyseGraph (order_to_node)
    │
    ├── 遍历 → 跳过 Dummy → 收集 node_list
    ├── RecordAndUpdateDmaIn/DmaOut → 标记 IO tensor 加载顺序
    │
    ├── GetHwLayerGroupList() → 分组（连续同类无sync的HwLayer打包）
    │
    └── 对每个 Group:
         ├── HwLayer[0].Codegen()  → 生成计算指令
         ├── HwLayer[1].Codegen()  → ...
         ├── HwLayer[n].Codegen()  → ...
         ├── CodegenHeaderInsts()  → 模块头
         ├── CodegenSyncInst()     → 同步信号
         ├── CodegenTailInsts()    → 校验和
         └── CodegenIdleInsts()    → Idle等待
```

### 4.2 HwLayer::Codegen() 模式

每种 HwLayer 子类实现 `Codegen()`，但都遵循相同模式：

**模式：CodegenDetailInfo() 模板**

以 `Conv2dLayer::Codegen()` 为例：

```cpp
// conv2d_layer.cpp:926
Status Conv2dLayer::Codegen() {
  if (!SatisfyHardwareConstrain().IsOK()) return FAIL;
  CodegenDetailInfo();             // ★ 实际生成指令
  return Status::OK();
}

// conv2d_layer.cpp:51
void Conv2dLayer::CodegenDetailInfo() {
  vector<CmdInfo> cmds_info;       // 临时收集本层所有指令

  // 1. 计算mac模式（MACx1/x2/x3）
  CalcMacMode();

  // 2. 各子功能模块填充指令
  ReuseConfig(cmds_info, ...);              // 内存复用配置
  LoadFmDataConfig(*in, *out, ...);         // 加载输入特征图
  LoadParamDataConfig(...);                  // 加载权重参数
  MacCoreConfig(*in, *out, ...);            // 核心 MAC 计算配置
  if (IsCropEnable()) CropInfoConfig(...);  // Wino 裁剪
  StoreFmDataConfig(*in, *out, ...);        // 写出结果特征图
  SplitHAndMacModeDataConfig(...);          // H维度拆分和MAC模式

  // 3. 写入指令容器
  this->GetHwLayerInfoRecord()->RecordCmds(cmds_info);
}
```

**数据流**：
```
Tensor (输入)                  Tensor (输出)
  │  addr, H, W, stride         │  addr, H, W, stride
  ▼                              ▼
┌─────────────────────────────────────┐
│ CodegenDetailInfo()                 │
│   用 Tensor 的地址/尺寸作为操作数    │
│   填充 MCInstr 的各个 bit 域         │
│   生成 uint64_t 指令序列             │
└─────────────────────────────────────┘
  │
  ▼
HwLayerInfoRecord::cmds_     (deque<uint64_t>)
```

**DMA 层更直观**（`NpuDmaIn::CodegenDetailInfo()`）：

```cpp
// npu_dma_in.cpp:49
void NpuDmaIn::CodegenDetailInfo() {
  vector<CmdInfo> cmds_info;

  // 逐条生成 DMA 指令
  MCInstr dma_in("DMA_IN_INFO_0");
  dma_in.SetOperand("src_addr",  tensor->addr());       // 源地址
  dma_in.SetOperand("dst_addr",  l1_addr);              // 目标地址
  dma_in.SetOperand("line_size", tensor->GetLineSize());// 行大小
  dma_in.SetOperand("h_size",    tensor->H());          // 高度
  dma_in.SetOperand("line_stride", ...);                // 行步长
  // ... 更多操作数
  cmds_info.emplace_back(dma_in.GenAsmStr(), dma_in.data());

  this->GetHwLayerInfoRecord()->RecordCmds(cmds_info);
}
```

### 4.3 CodegenSyncInst / CodegenHeaderInsts / CodegenTailInsts

这三个方法在**每个 Group 执行一次**（不是每个 HwLayer）。

- `CodegenHeaderInsts(group_size, cmd_num, cmd_id)` — 写入模块描述符：该组有多少个 HwLayer、总共多少条指令、组ID
- `CodegenSyncInst()` — 根据 `InstSync` 字段生成 SYNC_SET/SYNC_CLR 指令
- `CodegenTailInsts(check_sum)` — 写入校验和，硬件用于验证指令完整性
- `CodegenIdleInstsIfNeeded()` — 如果该 HwLayer 需要在最后插入 idle 等待

**最终每条指令的组织结构**：
```
┌────────── Group Header ──────────┐
│ Sync Set/Clear 指令（如有）       │  ← CodegenSyncInst()
│ Hardlayer Num + Cmd Num + Cmd ID │  ← CodegenHeaderInsts()
├────────── HwLayer[0] ────────────┤
│ DMA_IN_INFO_0                    │  ← Codegen() 生成
│ DMA_IN_INFO_1                    │
│ ...                              │
├────────── HwLayer[1] ────────────┤
│ CONV_CFG                         │
│ MAC_CORE_CFG                     │
│ STORE_FM_CFG                     │
│ ...                              │
├────────── Group Tail ────────────┤
│ CheckSum                         │  ← CodegenTailInsts()
│ IDLE_INFO（如有）                 │  ← CodegenIdleInstsIfNeeded()
└──────────────────────────────────┘
```

---

## 5. 第4步：后处理与输出

### 文件清单

| 文件 | 功能 | 优先级 |
|------|------|--------|
| `target/tensor_brain/transforms/adjust_io_tensor_order.cpp` | 调整 IO tensor 顺序匹配硬件 | ⭐ |
| `target/tensor_brain/transforms/analyze_pass.cpp` | 统计资源使用量 | ⭐ |
| `src/transforms/gen_files_pass.cpp` | 输出最终文件 | ⭐⭐ |

### AdjustIOOrderPass — IO 顺序调整

Codegen 执行过程中记录了 DMA_In/DMA_Out 的实际访问顺序（`in_ordered`/`out_ordered`）。这个 Pass 据此重排 KernelNet 的 inputs/outputs，使最终产物的 IO 顺序与硬件实际加载顺序一致。

### Analyze — 资源统计

统计编译结果：总指令数、总参数量、L1 内存峰值用量、DDR 带宽估算等。用于编译报告和性能评估。

### GenFiles — 最终文件输出

遍历 `KernelNet` 的 `KernelNetInfoRecord`（全部指令），生成：
- `.o` — `uint64_t` 指令流二进制
- `.asm` — 可读汇编文本
- `param.bin` — 打包的权重参数
- `data.json` — tensor 元信息
- `.tlf` — 完整模型包

---

## 6. 推荐走读顺序

```
1. include/aic/machine_code/mcinstr.h              (20min)  理解"指令"的数据结构
2. include/aic/file_out/hw_layer_info_record.h      (10min)  理解"指令容器"
3. target/tensor_brain/hw_layers/dma/npu_dma_in.cpp (30min)  看DMA Codegen（最简单直观）
   只看 CodegenDetailInfo() 函数
4. target/tensor_brain/transforms/codegen_pass.cpp  (40min)  看总调度 RunOnModule()
5. target/tensor_brain/hw_layers/mpu/conv2d_layer.cpp (40min) 看计算层Codegen（复杂）
   只看 Codegen() + CodegenDetailInfo() + LoadFmDataConfig + MacCoreConfig + StoreFmDataConfig
6. target/tensor_brain/transforms/insert_sync_pass.cpp (30min) 理解同步插入
7. target/tensor_brain/include/tensor_brain/hw_layer.h (20min) 看基类框架方法
8. target/tensor_brain/transforms/pre_codegen_pass.cpp (15min)
9. target/tensor_brain/transforms/insert_idle_pass.cpp (15min)
10. src/transforms/gen_files_pass.cpp               (15min)  看最终文件输出
```

**核心文件（必读）**: 1 → 3 → 4 → 5

## 我的问题
### Dummy 层 是什么
Dummy 层是"不需要实际硬件操作，但需要在图中占位以维持数据流正确"的虚拟 HwLayer。

---
是什么

Dummy 层继承自普通 HwLayer，构造函数里直接调 SetDummy()：

class DummyConcatLayer : public ConcatLayer {
  DummyConcatLayer(...) : ConcatLayer(...) { SetDummy(); }  // 标记为虚拟
  bool IsDummyConcat() override { return true; }
  // 不支持 Cascade，不支持 Sync
  bool SupportCascadeLdr() override { return false; }
  int InstSyncSet(HwLayer*) override { return -EINVAL; }   // 禁止设同步
};

在流水线中的处理：

// Codegen::RunOnModule()
for (auto& [order, node] : order_to_node) {
    if (node->IsDummy()) continue;   // ← Dummy 层直接跳过，不生成任何指令
    // ...
}

// MemAlloc / LiveTimeAnalyse 中
// Dummy 层参与生命周期分析和内存分配，但不分配自己的 buffer

---
为什么需要

核心原因：两个 tensor 在物理上连续存放时，Concat/Slice 操作不需要硬件搬数据，只需要"重新解释"地址范围。但分析图需要一个节点来表达这种数据流关系。

场景一 — DummyConcat

Conv_A 输出 → L1 地址 0x1000, 大小 256B
Conv_B 输出 → L1 地址 0x1100, 大小 256B
                  ↓
        地址恰好连续：0x1000~0x1200 就是拼接后的结果
                  ↓
      DummyConcat: 输入是 [0x1000, 256B] + [0x1100, 256B]
                   输出是 [0x1000, 512B]  ← 只改描述符，不搬数据
                  ↓
      下游 Conv_C 的 DMA_In 直接读 0x1000~0x1200

如果不引入 DummyConcat，下游 Conv_C 不知道去哪找拼接后的完整数据。引入后，只是把输出的 start_addr 设为第一个输入的地址，size 设为两者之和——零硬件指令，零延时。

场景二 — DummySlice

Conv 输出 → [C0~C15, H, W]，共16个通道
       ↓
  只需要 C8~C15 → DummySlice: 输入 [C0~C15]，输出 [C8~C15]（调整地址偏移）
       ↓                              ↓
  地址偏移 = C8 × H × W × element_size，零搬运

---
和真层的区别

┌────────────────────┬──────────────────────────────┬────────────────────────────┐
│                    │ 真 HwLayer（Conv2dLayer 等） │          Dummy 层          │
├────────────────────┼──────────────────────────────┼────────────────────────────┤
│ Codegen()          │ 生成 uint64_t 指令序列       │ 不调用（IsDummy() 被跳过） │
├────────────────────┼──────────────────────────────┼────────────────────────────┤
│ 同步信号           │ 可以 Set/Clr                 │ 禁止（调用就报错）         │
├────────────────────┼──────────────────────────────┼────────────────────────────┤
│ Cascade            │ 可以参与                     │ 不支持                     │
├────────────────────┼──────────────────────────────┼────────────────────────────┤
│ 硬件延时           │ 有                           │ 零                         │
├────────────────────┼──────────────────────────────┼────────────────────────────┤
│ 内存分配           │ 分配自己的 buffer            │ 不分配，输出复用输入的地址 │
├────────────────────┼──────────────────────────────┼────────────────────────────┤
│ 在 AnalyseGraph 中 │ 参与执行序                   │ 参与，但仅用于数据流分析   │
└────────────────────┴──────────────────────────────┴────────────────────────────┘

---
一句话

Dummy 层是地址代数的占位符：当数据已经在物理上连续排列时，Concat/Slice 退化为纯地址计算，不需要硬件操作。Dummy 层把这个地址计算表达在图中，让下游节点能正确获取数据的地址和大小。

✻ Cooked for 35s

❯ 所以我可不可以理解为，这个思路类似于LLVM中由于target没有i64寄存器，所以pattern就用两个i32去
---
一句话

Dummy 层是地址代数的占位符：当数据已经在物理上连续排列时，Concat/Slice 退化为纯地址计算，不需要硬件操作。Dummy 层把这个地址计算表达在图中，让下游节点能正确获取数据的地址和大小。