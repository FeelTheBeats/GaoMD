# Visitor 重构 — 可能被提问的问题（FAQ）

> 附属于 `v3_node_visitor_SPEC.md`，供会议答疑使用。

---

### Q1: 为什么分两个 Visitor（NodeVisitor + HwVisitor）而不是合并？

两层关心的类型集合不重叠——NodeVisitor 处理 Operator/Kernel（软件算子语义），HwVisitor 处理 HwLayer（硬件指令语义）。合并后接口有 27 个 Visit 方法，其中一半对每个 pass 都是死代码。且 L3 的 AnalyseNode 需要不同的路由逻辑（穿透到 hw_layer_），与 L1/L2 的直调模式不一致。

### Q2: NodeVisitor 为什么只有 16 个 Visit 方法？42 个 Operator 只覆盖了一小半。

Visit 方法只列当前被 pass 实际分发的类型（基于全仓 `dynamic_cast` 统计）。未列的类型（BatchNorm、Activation、Eltwise 等）不需要从 Node* 恢复类型——它们总是在创建后通过具体类引用直接使用。将来有分发需求时，加一行 `virtual void Visit(FooOp&) {}` 即可，对应子类的 Accept 已有全覆盖。

### Q3: 是否替代 PatternMatcher？

不替代。PatternMatcher 解决"在图里找到匹配的子图"（子图同构搜索），Visitor 解决"对已找到的节点执行类型特定的操作"（类型分发）。多节点场景（如 SliceFuse）需要两者配合：PatternMatcher 匹配 → Visitor 改写。

### Q4: 虚函数调用有性能损失吗？

Accept 增加一次虚函数间接跳转。但在 pass 场景下可忽略：pass 是离线编译器，每个节点在编译期间只被遍历 1~2 次，非推理热路径。

### Q5: `Node::Accept` 为什么不用纯虚函数（`= 0`）？

纯虚函数强制所有子类必须 override，导致全量一次性迁移（62 个类必须全改完才能编译）。默认实现允许渐进迁移——未 override 的子类走 `v.Visit(Node&)`（空 fallback），编译正常。当前已主动加上所有子类的 override，默认实现是防御底线。

### Q6: 会影响现有 pass 吗？需要改旧代码吗？

零影响。所有 114 个 Accept 方法是**纯增量**——新加了方法但没有一行调用代码。已有 pass 继续使用 `dynamic_cast`，行为完全不变。迁移到 Visitor 是可选的、渐进的。

### Q7: 为什么 HwLayer 子类的 Accept 覆盖了中间基类（Mpu/Vpu/Dma/Mte/Spu）？

因为 pass 可能按不同粒度分发。例如 Cascade pass 对 MPU 类型统一处理（不区分 Conv2d vs ConvFusion），可只 override `Visit(Mpu&)`；而 SyncAnalyse 可能需要区分 `Conv2dLayer` 和 `EltwiseLayer`，可 override 具体类型的 Visit。中间基类的 Visit 提供了灵活的**粒度选择**。

### Q8: 新增一个 Operator 类型的标准流程是什么？

1. `foo_op.h`：定义类 `FooOp : public Operator`，加一行 `void Accept(NodeVisitor& v) override { v.Visit(*this); }`
2. `node_visitor.h`：加一行 `virtual void Visit(FooOp&) {}`
3. 需要处理 FooOp 的 pass：override `Visit(FooOp&)`，写入业务逻辑

不关心 FooOp 的 pass：不改，默认 fallback 跳过。

### Q9: 编译依赖会增加吗？头文件循环依赖怎么解决的？

`node_visitor.h` 只做前置声明 + 空 `{}` 方法体，**不 include 任何 Node 子类头文件**。`node.h` include `node_visitor.h`（因为 Accept 是 inline 的），`node_visitor.h` 只前置声明 `Node`（因为 `Visit(Node&)` 只用引用），无循环依赖。

### Q10: 实施状态？什么时候可以用？

基础设施已完成：115 个文件修改、2 个 Visitor 接口、114 个 Accept 方法。**旧 pass 行为不变，随时可用**。试点迁移建议从 SplitExp（L1 单类型）和 Cascade（L3 多类型）开始。

### Q11: 为什么所有子类都加了 Accept override 而不是只加有分发需求的那 16 个？

最初方案确实是只覆盖 16 个被分发的类型，后改为全覆盖（45 个 Operator + 全部 Kernel + 全部 HwLayer）。理由：未来新 pass 需要分发未覆盖的类型时，不需要先补基础设施——子类的 Accept 已就位，只需在 Visitor 接口中加一行 `Visit` 声明。

### Q12: 为什么 Operator/Kernel 基类本身不加 Accept override？

`Operator` 和 `Kernel` 是中间层，没有 pass 对它们做类型分发——pass 关心的粒度是叶子类（Exp、Softmax、Conv2dKernel）。如果在基类加 override，叶子类不 override 时路由会走到 `v.Visit(Operator&)` 而不是 `v.Visit(Exp&)`，丢失了具体类型的信息。分发必须在最具体的叶子类完成。

### Q13: 编译时遇到 `static_cast` 错误是怎么回事？默认实现为什么不能写成 `static_cast<Node&>(op)` 然后 fallback 到 `Visit(Node&)`？

最初 `node_visitor.h` 中 Kernel 类型的默认实现为 `{ Visit(static_cast<Node&>(k)); }`，意图是自动 fallback 到基类。编译失败因为 `node_visitor.h` 只有前置声明——`static_cast` 做继承链类型转换时必须看到两个类型的完整定义，前置声明不包含继承关系信息。

修复：默认实现改为空 `{}`。语义等价且更安全：不 override 的 pass 本来就应该什么都不做，不需要"fallback 到基类"的中间步骤。前置声明下，inline 方法的安全子集只有 `{}`。

### Q14: `node.h` 为什么必须 include `node_visitor.h` 而不是只做前置声明？

因为 `Node::Accept` 是 inline 方法，方法体中调用了 `v.Visit(*this)`——需要 `NodeVisitor` 的完整定义来看 `Visit()` 的声明。前置声明只告诉编译器"这个类存在"，不告诉它类里有什么方法。如果某个 `.cpp` include 了 `node.h` 但没有经过 operator 头文件（例如 `parallel_base_on_type.cpp`），就会编译失败。

修复：`node.h` 直接 include `node_visitor.h`。反向无循环依赖——`node_visitor.h` 只用 `class Node;` 前置声明（`Visit(Node&)` 只取引用，不需要完整类型）。
