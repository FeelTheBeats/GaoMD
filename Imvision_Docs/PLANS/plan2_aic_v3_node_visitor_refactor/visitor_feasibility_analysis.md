# AIC Visitor 模式可行性分析

> 2026-06-23，基于 aic_v3 代码仓实际数据。调研目标：评估在三层 IR（Operator/Kernel/Analyse）中为 Node 类体系添加 Visitor 模式的可行性与必要性。

---

## 一、数量基础

| | Operator (L1) | Kernel (L2) | HwLayer (L3) |
|---|---|---|---|
| 子类数 | **42** | 17 | 9 |
| Pass 中 dynamic_cast 的目标类型 | ~15 | ~10 | 很少（大多按执行序遍历，不做类型分发） |
| 遍历模式 | `graph_.Nodes()` | `graph_.Nodes()` | `order_to_node`（执行序，非拓扑序） |

---

## 二、可行性

### L1（Operator）：可行

`Node` 基类（371 行）只有 3 个虚函数，很干净。加一个 `virtual void Accept(Visitor&) = 0` 是单点改动。代价是 42 个子类都要加一行 override：

```cpp
void Exp::Accept(Visitor& v) override { v.Visit(*this); }
```

机械操作，可脚本生成。

### L2（Kernel）：可行

17 个子类，和 L1 一样的模式。`Kernel` 和 `Operator` 都继承自 `Node`，`Node::Accept` 可以同时服务两层。

### L3（AnalyseGraph）：不需要

`AnalyseNode` 包裹 `HwLayer*`（委托模式，非继承 HwLayer 体系）。L3 的 pass 不靠类型分发——遍历 `order_to_node`，操作的是执行顺序、内存分配、同步位置。仅 9 个 HwLayer 类型且很稳定，Visitor 收益可忽略。

**结论：L1 + L2 可行，L3 不需要。**

---

## 三、必要性

### 当前分发已经分成两层

```
        谁在 dynamic_cast？            还能被 Visitor 改进吗？
        ─────────────────            ────────────────────────
第 1 层  PatternMatcher（匹配）        不需要——已经声明式了
第 2 层  Impl 函数（改写）            可以——还是手写 dynamic_cast
```

### 具体例子

```cpp
// 第 1 层：匹配 —— PatternMatcher 已处理
auto matches = PatternMatcher(*net).Match(pattern);

for (auto& match : matches) {
    // 第 2 层：改写 —— 仍然 dynamic_cast
    auto* exp_op = CastNoCheck<Exp>(net->GetOp(idx));  // ← Visitor 替换这个
    exp_op->Attr()->exp_sig_mode;  // 访问 Exp 特有属性
    exp_op->GetLutAcc();           // 访问 Exp 特有方法
}
```

### Visitor 后

```cpp
node.Accept(loweringVisitor);
// → double dispatch →
// LoweringVisitor::Visit(Exp& e) { e.Attr()->exp_sig_mode; ... }
```

**Visitor 不是在取代 PatternMatcher，是在取代 Impl 函数中的 `dynamic_cast`。**

---

## 四、核心收益

| 维度 | 当前 | Visitor 后 |
|------|------|-----------|
| 匹配（找节点） | ✅ PatternMatcher 声明式 | ✅ 不变 |
| 改写（访问类型特有接口） | `CastNoCheck<T>` + 直接调方法 | `Accept → Visit(T&)` 自动路由 |
| 类型安全 | 运行时 `dynamic_cast` | 编译期重载决议 |
| 遗漏类型处理 | 静默跳过（`continue`） | 编译报错或默认 fallback（可定制） |
| 新增 Operator 的改动 | 改所有相关 pass | 新类加 1 行 `Accept` + 各 Visitor 加 1 个 `Visit` 重载 |

**"遗漏类型编译报错"是最大收益**——如果新增 `FooOp` 但忘记在相关 pass 加处理逻辑，只有在运行时遇到该 op 才会暴露（且不报错，静默跳过）。

---

## 五、三层总结

| | L1 Operator (42 子类) | L2 Kernel (17 子类) | L3 Analyse |
|---|---|---|---|
| 可行性 | ✅ 高 | ✅ 高 | ❌ 不需要 |
| 必要性 | 中等（PatternMatcher 已分担匹配，Visitor 解决改写层类型安全） | 中等偏弱（子类少，pass 少） | 低 |
| 风险 | 需改 42 个头文件加 `Accept` | 需改 17 个头文件加 `Accept` | — |
| 时机 | 适合先做（子类最多收益最大） | 跟随 L1 一起做 | 跳过 |

---

## 六、建议方案

1. 在 L1（Operator + Node）层加 Visitor 接口
2. L2（Kernel）复用同一套 `Node::Accept` 接口
3. L3 不动
4. 不是替代 PatternMatcher——是 **PatternMatcher 匹配 + Visitor 改写** 的组合模式
