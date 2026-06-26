# AIC 学习日记 — 2026-06-25

> Split 合并重构落地：10 个 pass → 1 个 ComplexOpSplit。extern 策略、ConvTranspose 提取、BNInfo 冲突修复、Visit 方法转发。

---

## Split Pass 合并重构

### Q1: extern 策略 vs 搬运策略怎么选？

搬运策略（复制函数体）导致 complex_op_split.cpp 1500+ 行、容易漏代码、命名冲突。改动为 extern 策略：旧文件去掉 `static`，新文件 `extern` 声明后一行转发。新文件缩到 ~250 行，零搬运风险。

**关键收益**：旧文件 Impl 函数一行不动，review 只需看转发调用是否正确。

### Q2: ConvTranspose2d 为什么特殊？

其他 8 个 pass 都有独立的 `XxxImpl` 函数，去 `static` 就能 extern。ConvTranspose2d 和 ConvTranspose2d2 的改写逻辑 inline 在 RunOnModule 循环体里，没有独立 Impl。需要先提取为 `SplitConvTranspose2d` / `SplitConvTranspose2d2` 函数。

### Q3: 提取函数后 RunOnModule 是否还保留原始逻辑？

用户指出：提取函数后 RunOnModule 和 SplitConvTranspose2d 有两份相同的 100 行代码。修复：让 RunOnModule 的循环体直接调用 `SplitConvTranspose2d`，消除重复。**原始代码一行不动的前提下，函数变为胶水层。**

同样的逻辑供三处使用：原始 RunOnModule、ComplexOpSplit Visitor、回退备用。

### Q4: 格式改动到底能不能做？

用户强调"能不改就不改"原则。第一次提取 ConvTranspose2d 时我把注释和换行压缩了。用户严厉指正。**教训**：新函数也必须用原文件精确格式（sed 提取原行，一字不改）。

### Q5: BNInfo 重复定义怎么解决？

6 个 operator 头文件各自定义了同名 `struct BNInfo`，合并到 complex_op_split.cpp 后编译器报 redefinition。分析发现 softmax.h 和 base_norm.h 是命名空间级定义（会冲突），其余 4 个是类内嵌套（`Exp::BNInfo` 等，天然不冲突）。修复：给 base_norm.h 和 softmax.h 加 `#ifndef AIC_BNINFO_DEFINED` guard，每文件 3 行。

### Q6: nodiscard Status 返回值怎么处理？

Visitor 的 Visit 方法是 void，但调用的 extern Impl 函数返回 `[[nodiscard]] Status`。`-Werror` 报错。修复：每个调用前加 `(void)` 显式忽略，格式要求 `(void)FuncCall()` 紧贴函数名。

### Q7: RmsNorm2Type 哪来的？

我在 NormType map 中手误写了 `NormType::RmsNorm2Type`。这是一个不存在的枚举值。原 complex_op_split_basenorm.cpp 的 map 只有 3 个条目（LayerNorm、InstanceNorm、RmsNorm）。修复：删除该条目。

### Q8: Yuv2rgb 有什么特殊处理？

Yuv2rgb 有后处理步骤 `UpdateYuv2RgbRefModel`——需要根据是否使用了 Conv2dAdd 路径在遍历结束后调用。修复：在 SplitVisitor 中加 `has_yuv2rgb_conv2dadd_` 标志位，RunOnModule 循环结束后检查并调用。

### Q9: CI bot 的三个建议要不要改？

1. `[LowerLogSoftmax]` 是 pass 名，不是内部代号 → 不改
2. `CastNoCheck` 换成 `Cast` → 建议合理，但旧文件遵循"能不改就不改"
3. `Commit()` 未显式调 `Resolve()` → bot 没看到 Commit 内部已包含 Resolve → 不改
4. Dead Attr `(void)n; return true;` → 用户发现了，已在 permute_replace_reshape.cpp 删掉

### Q10: 编译警告的来源？

用户发现编译有两类警告，确认是 Split 重构（不是 Visitor 重构）导致的：BNInfo 重定义 + nodiscard。都已在最新 commit 中修复，编译零 warning。

---

## 提问评价与建议

### 这次特别好的

1. **对格式的严格把关（Q4）**：你发现我压缩了原始代码的注释和换行，立即叫停。这不是挑刺——编译器不管格式，但 code review 的人在乎。改别人的代码，哪怕只是搬运，也得保持原样。这是工程素养。

2. **主动追问函数定位（Q3）**："SplitConvTranspose2d 为什么那么特殊不能动"——你精准抓住了核心问题：如果提取的函数和 RunOnModule 有重复逻辑，那就不是胶水层，是冗余。这直接推动了去重方案落地。

3. **CI bot 建议的独立判断（Q9）**：三个 bot 建议你都逐条分析并给结论，不是无条件接受也不是无脑拒绝。尤其是 dead Attr 那条——bot 没发现，你自己发现了，说明你对代码的理解已经比静态检查工具更深。

### 可改进的

1. **"能不改就不改"可以作为显式原则记录下来**：这是你第二次强调，说明这是你和团队的共识。建议在 SPEC 或工作笔记里写一行："重构原则：旧文件能不动的尽量不动，改动集中在新建文件中"。

2. **extern 策略可以更早定下来**：搬运策略（1500 行新文件）浪费了一些时间。如果一开始就评估"新文件越大越难 review"，extern 的优势会更早显现。**教训**：不要先动手再反思，先规划再执行。
