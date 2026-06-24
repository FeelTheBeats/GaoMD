# 芯片第一步，了解ISA
## 初步了解
### 这颗芯片是 SIMT / SIMD / VLIW / 数据流 / 张量引擎？
VLIW/SIMD 结合专有计算阵列的模式
### 有几层执行单元？（Core / Tile / Cluster / Tensor Core）
`Module/Core/Cluster`
在 AI 芯片（无论是 NVIDIA 的 GPU 架构，还是各种专有的 NPU 架构）中，**Module（模块）、Core（核心）、Cluster（集群）** 处于硬件层次结构（Hardware Hierarchy）的不同层级。

为了从底层到顶层说清楚它们的组织形式，我们按照**从微观到宏观**的顺序来梳理其具体含义和演进逻辑：

---

#### 1. Core（核心）

**Core 是处理并行计算的最小完整逻辑单元（计算节点的基石）。**

在 AI 芯片中，一个 Core 通常包含：

* **执行单元（Execution Units）：** 比如处理通用计算的标量/向量单元（ALU、Vector Units），以及 AI 芯片最核心的**矩阵乘法单元（Tensor Core / Matrix Engine）**。
* **本地寄存器堆（Register File）：** 极高性能的私有寄存器。
* **一级缓存/内部暂存器（L1 Cache / Scratchpad Memory / SRAM）：** 用于暂存当前计算所需的权重和特征图（Feature Map）。
* **控制指令单元：** 负责取指、译码并分发到内部的计算单元。

> **典型对齐：**
> * 在 NVIDIA GPU 中，可以类比为 **SM（Streaming Multiprocessor）** 内部的子核心（或者广义上将一个 SM 视为一个大 Core，内部包含 Tensor Core）。
> * 在 NPU 中，一个 Core（如 TPU 的 Matrix Unit 核心）通常可以独立运行一个算子的局部子块。
> 
> 

---

#### 2. Cluster（集群）

**Cluster 是由多个 Core 以及它们共享的局部资源组合而成的硬件复用单元。**

当芯片规模变大时，如果让成百上千个 Core 直接去对接着急的全局内存（如 HBM、DDR），会导致严重的总线拥堵（Bus Congestion）和控制混乱。因此，硬件设计采用“分而治之”的思路，将若干个 Core（例如 4个、8个或 16个）打包成一个 Cluster。

在一个 Cluster 内部，这些 Core 通常会共享：

* **二级缓存（Shared L2 Cache / SRAM）：** 用于 Core 之间进行快速的数据交换（例如 Kernel Fusion 时的时延消减，数据从 Core A 算完直接过 L2 给 Core B，不用回写到片外）。
* **网络/互连结构（Interconnect / NoC Router）：** 负责 Cluster 内部 Core 之间的点对点通信。
* **任务分发器（Work Distribution Engine）：** 负责将一个大的计算任务（如一个 Tensor 层的计算）拆分并下发给该 Cluster 内部的各个 Core。

> **典型对齐：**
> * 在 NVIDIA GPU 中，这对应 **GPC（Graphics Processing Cluster）** 或 **TPC（Texture Processing Cluster）**，它把多个 SM 聚合在一起。
> * 在很多大模型专用 NPU 架构中，一个 Cluster 往往构成一个独立的“计算阵列”，负责处理某一个空间维度的并行。
> 
> 

---

#### 3. Module（模块）

**Module 在芯片架构中通常有两种语境，分别代表“功能部件”或“最高级物理封装”。**

根据上下文，Module 的含义会有所不同：

* **语境 A：功能性子模块（微观视角）**
在讨论 Core 内部结构时，Module 指的是**专门负责某种特定计算的硬核（Hard IP）**。
> *例如：“该 NPU 核心内部集成了一个 Vector Module（向量模块）和一个 Matrix Module（矩阵模块）。”* 这里的 Module 是 Core 的**组成部分**。


* **语境 B：可扩展的硬件模块/芯片组（宏观/物理视角）**
在现代**晶片组（Chiplet）**和板卡架构中，Module 指的是**一个完整的、可插拔的或独立封装的硬件单元**。它由多个 Cluster、片上超大 L3 Cache/SRAM、内存控制器（HBM Controller）以及片间互连总线（如 NVLink 接口）共同构成。
> *例如：NVIDIA 的 SXM5 Module（SXM 模组）或者某些 AI 加速器的计算模组。* 这里的 Module 是包含了完整计算、存储和 IO 的**宏观实体**。



---

#### 总结：层级关系与编译器的视角

如果用一个经典的剥洋葱视角来看，它们在 AI 芯片中的拓扑关系如下：

$$\text{Module (芯片/模组级)} \longrightarrow \text{Cluster (集群级)} \longrightarrow \text{Core (核心级)} \longrightarrow \text{Execution Module (内部部件)}$$

```
+-------------------------------------------------------------+
| Module (例如: 整个 AI 加速芯片/Chiplet)                       |
|   +-----------------------------------------------------+   |
|   | Cluster 0 (共享 L2 Cache / NoC)                     |   |
|   |   +-------------------+     +-------------------+   |   |
|   |   | Core 0 (L1/SRAM)  |     | Core 1 (L1/SRAM)  |   |   |
|   |   |  - Matrix Module  |     |  - Matrix Module  |   |   |
|   |   |  - Vector Module  |     |  - Vector Module  |   |   |
|   |   +-------------------+     +-------------------+   |   |
|   +-----------------------------------------------------+   |
|   +-----------------------------------------------------+   |
|   | Cluster 1                                           |   |
|   +-----------------------------------------------------+   |
+-------------------------------------------------------------+

```

对于AI 编译器（如 MLIR, TVM）的开发者来说，区分这三者至关重要：

* **Core 级别**决定了你做 **Tiling（算子平铺）** 时，切分出的最小 Data Block 能不能塞进 L1 Scratchpad，以及如何优化寄存器级别的循环展开（Loop Unrolling）。
* **Cluster 级别**决定了数据如何在不同的 Core 之间进行 **Pipeline（流水线化）** 复用，以及如何利用共享 L2 减少对全局 HBM 的带宽压榨。
* **Module 级别**则决定了更高级别的任务并行策略（如张量并行 Tensor Parallelism 或流水线并行 Pipeline Parallelism）如何在不同的芯片硬件实体间做切分。

#### 自问自答
- 啥是 sync info
定义：sync info 在 Layout 上，通常对应的是硬件级别的同步屏障单元（Hardware Barrier / Semaphore）或者相关的控制寄存器
管“大家怎么排队配合”的

- 怎么进行同步的
SyncSet/SyncClr(用于放依赖的和被依赖的队列)
/SyncID/Reserved

- 啥是 core func
定义：在现代 AI 芯片（尤其是 DSA 架构）的 Core 里面，为了追求极致的面积功耗比，一个 Core 内部往往塞了好几个功能各异的硬件微模块（比如有专门拉矩阵乘法的 Matrix Module，有搞各种 ReLU/Sigmoid 的 Vector Module，甚至还有管地址生成的 AGU）。
**功能选通与配置、指令译码与分发控制、状态机（FSM）**
管“逻辑门现在该干啥活”

- 啥是 CMD group
定义：CMD group 就是把一堆有关联的、需要打包一起发给硬件执行的底层微指令（Commands），捆绑在一起形成的“指令大礼包”。
组内容：
    - Config CMD（配置/上下文指令）： 告诉硬件接下来这波计算的基地址（Base Address）、张量的形状（Shape, Stride）、数据格式（FP16 还是 INT8）、以及各种选通信号。
    - Move CMD（数据搬运指令）： 指挥底层的 DMA 控制器，赶紧把刚才配置好的权重（Weights）和特征图（Feature Map）从片外 HBM/DDR 给我搬到片上的 SRAM 缓存里。
    - Exec CMD（核心计算指令）： 这才是真正的计算，比如命令矩阵引擎（Matrix Engine）启动，去算刚才运进来的那两块矩阵。
意义：软件流水线（Ping-Pong Buffer）的完美载体
    1. CMD Num（指令总数）
    2. Hard Layer Num（硬件流水线图层数 / 硬件层数）
    3. Hard Layer CMD Num（单层硬件指令数）
    4. CheckSum (组指令自检)

- 啥是pingpong buffer
定义：这是一种通过在空间上开辟两块等大、独立的存储缓冲区（分别称为 Ping 和 Pong），并由硬件或软件控制流对其读写权限进行轮流交替切换，从而实现“数据搬运（I/O）”与“核心计算（Compute）”在时间上完全异步并行（Overlap）的微架构缓冲区管理技术。
特点：
    空间上： 一分为二，一块写，一块读。
    时间上： 角色对调，搬运隐藏在计算里。
### memory 是统一还是分层？（HBM / SRAM / scratchpad）
统一L1，所有模块与内存的交互都直接向DDR申请，与L1直接接触。

### 执行是 显式调度还是硬件调度？
显式调度，指令流水由编译器决定

## 看ISA设计
### ISA about
- Multi Core/Cluster/Module 
在软件层面，硬件的表现形式是 Group，和信道的信源异曲同工，有head和tail，前面几层是关键信息：sync\header等
- ISA 字段
SyncSet/SyncCl- 依赖队列标记
SyncID-debug用
CMD Num 命令标记，一个group的Header和tail段间的标记
Hard Layer Num 用于约束，不同 Hard Layer之间的命令无sync指令，理解为分组用，体现在三个计算单元在不同的layer上
Hard Layer CMD Num 同一级硬件上的命令如果function不同，则 CMD Num不同
CheckSum group的组指令自检用

### MTE
存储：0 Load Info
计算、存储、控制流、同步
### MPU
计算、存储、控制流、同步
### VPU
计算、存储、控制流、同步
## ISA——>Compiler IR

## 找“ISA 的设计意图”

## 用 compiler 视角重新“读 ISA 文档的方法”