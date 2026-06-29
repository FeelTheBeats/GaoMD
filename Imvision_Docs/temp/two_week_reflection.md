# 两周回顾：从 PatternMatcher 到 Visitor 模式

> 入职 7~12 个工作日。停下来，看一看走过的路。

---

## 干了什么

五件有形的产出：

1. **PatternMatcher 重构（11 个 pass）**——把 L1 层所有 split/lowering pass 从手写 `for + dynamic_cast` 改成声明式 PatternBuilder。这是第一次接触 AIC 的 pass 结构、图遍历、类型体系。

2. **BatchRewriter 概念澄清**——理解它只是一个"批量删除 + 单次 Resolve"的封装，不是事务。等 Alan 定型后再跟进。

3. **Visitor 模式基础设施（115 个文件）**——给所有 Node 子类（Operator 45、Kernel 24、HwLayer 39）加 `Accept` 方法，创建 `NodeVisitor` 和 `HwVisitor` 两个接口，`AnalyseNode` 做 Wrapper 路由。**纯增量，零 pass 修改。**

4. **Split Pass 合并试点（10→1）**——用 extern 策略把 10 个独立 split pass 合并为 `ComplexOpSplit`，通过 `SplitVisitor` 分发。验证了 Visitor 在真实场景下的可行性。

5. **文档体系**——SPEC、重构记录、学习日记、FAQ。每一份都是你自己的积累，不依赖我。

---

## 每个阶段学了什么

### PatternMatcher 重构 → 理解"图怎么遍历"

- `GraphViewer` 拿拓扑序、`graph_.Nodes()` 遍历、`dynamic_cast` 做类型筛选
- 三层 IR 的边界：L1（Operator/Net）、L2（Kernel/KernelNet）、L3（AnalyseGraph/HwLayer）
- Pass 注册机制：`PM_REGISTER_PASS` 怎么把 pass 挂到编译流水线

**重点**：不需要记住每个 pass 的细节。需要记住的是"所有 lowering pass 都遵循同一个模式"——找节点 → 创建替代算子 → 删旧节点。

### BatchRewriter 讨论 → 理解"图怎么修改"

- `ReleaseNode` 标记删除，`Resolve` 全图校验
- 攒着删比立即删好——O(N) 次 Resolve vs O(1) 次
- 图修改的正确性边界：tensor 连接是独立的，删旧节点不影响新节点

**重点**：`Resolve()` 是重操作。以后写 pass 时，清理逻辑统一用 BatchRewriter（或手写的话，攒完一次 Resolve）。

### Visitor 落地 → 理解"类型怎么分发"

- C++ 的 `dynamic_cast` 工作原理、前置声明 vs 完整定义
- Double dispatch：`Accept → Visit` 的虚函数路由链
- 头文件依赖管理：何时用 `#include`，何时用前置声明
- L3 的 `AnalyseNode` 是壳，`HwLayer*` 才是肉

**重点**：Visitor 不替代 PatternMatcher。PatternMatcher 找节点，Visitor 处理节点。单节点场景 Visitor 更优，多节点场景需要两者配合。

### Split 合并 → 理解"重构怎么收放"

- extern 策略：旧文件去 `static`，新文件 `extern` 转发。零搬运风险
- 旧文件"能不改就不改"原则
- BNInfo 冲突是原代码缺陷（同名 struct 定义在多个 header），不是我们引入的 bug
- commit message 规范、codecheck 规则、Gerrit push 流程

**重点**：重构的边界感——知道什么该动、什么不该动，比写出漂亮的代码更难。

---

## 优缺点

### 做得好的

1. **追问到根**。`MatchNode` 的第一个参数是干什么的、"conv_transpose2d2" 这个字符串从哪来的——你从不接受表面解释。这在编译器领域是核心能力，因为很多 bug 就是因为"我以为这个东西是 A，其实是 B"。

2. **主动质疑设计**。单节点 PatternMatcher 没收益→找 Alan 确认意图→理解这是架构决策。Visior 合并 pass 前先评估可行性。你不是在执行任务，你是在理解任务。

3. **对"能不改就不改"的坚持**。这是工程素养。新人容易一腔热血把所有东西都改一遍，你知道边界在哪。

4. **文档习惯**。日记、SPEC、重构记录——两周积累了 15+ 份文档。三个月后你再回头看这些代码，这些文档比任何代码注释都有用。

### 需要补的

1. **编译流程和测试流程**——你改了 100+ 个文件，但从没自己跑过完整的 CI pipeline，没调试过一个 core dump。这让你对"改错了怎么办"缺乏直觉。

2. **硬件层理解**——你知道 DmaIn 是 DDR→L1 的搬运，Conv2d 跑在 MPU 上，但这是概念层面的。你还没 trace 过一个 pass 的完整链路：JSON 输入 → Parser → Operator → Lowering → Kernel → HwLayer → Codegen → 指令输出。

3. **先 grep 再判断**——SplitBaseNorm "channel-split 有拓扑序依赖"那次，如果 5 秒 grep 一下 `graph_viewer` 的次数，当时就能发现只有一处而不是两处。教训："看起来复杂"不等于"实际复杂"。

---

## 下一步学什么

建议按这个顺序，每个 ~半天：

1. **端到端 trace**：挑 SplitExp，从 JSON 输入到 codegen 输出，用 `TLOG_D` 打 log 跟踪一个 Expp 节点在整个编译流水线中的演变。目标：理解一层的输出怎么变成下一层的输入。

2. **硬件 PE 文档**：你已经有 `docs/source/hw_pes/` 下的四个文件。带着"我改的 pass 最终会生成什么指令"的问题去读。不需要读微架构，读指令集和内存层次。

3. **跑一次完整 CI**：找 mentor 要 onboarding 文档，本地跑一个 case，学会看 log、抓 core dump。这是"安全感"的来源——你知道改错了会怎样、怎么修。

4. **总结你自己的文档**：把两周积累的日记和 SPEC 通读一遍，标记你觉得"还不太懂"的部分。这些就是你下一步的深入点。

---

## 最后

这两周你的学习曲线不是"我从零开始学编译器"——你是从一个 LLVM 工程师的视角去理解另一个编译器，然后在 6 个工作日内完成了一个通常需要 2~3 周的重构任务。你不需要比别人快，你需要的是不要比别人累。

今天下午，看看文档，喝杯咖啡。不急。
