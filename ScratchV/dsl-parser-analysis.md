# DSL Parser 分析 (`scratchv/frontend/dsl_parser.py`)

## 一句话定位

**ScratchV 的微型 DSL 前端** — 把类 Python 的数学表达式文本解析成 ScratchV IR，是脱离 ONNX 依赖的轻量测试入口。

## 为什么存在

ONNX 是面向真实模型的路径，但日常开发、调试、跑单测不能总依赖 ONNX 模型文件。DSL 提供零依赖、即时可写的 IR 生成方式，覆盖所有算子 + 控制流。

## 支持的 DSL 语法

```
# 注释
c = add(a, b)           # 加法
c = sub(a, b)           # 减法
c = mul(a, b)           # 乘法
c = div(a, b)           # 除法
y = relu(x)             # ReLU 激活
y = gelu(x)             # GELU 激活
y = softmax(x, axis:-1) # Softmax
y = exp(x)              # 指数
y = neg(x)              # 取反
c = matmul(a, b, rows:4, cols:8, inner:16)  # 矩阵乘法 (shape 参数可选)
c = dot(a, b, len:64)   # 向量点积
y = maxpool(x, kernel:2, stride:2)          # 最大池化
return x                # 返回值

for i = 0, 10           # 循环开始 (i 从 0 到 9)
    ...
endfor                  # 循环结束
```

## 核心数据结构

| 字段 | 类型 | 作用 |
|------|------|------|
| `builder` | `IRBuilder` | IR 构造器，实际生成 Program/Function/Block/Instruction |
| `_vars` | `dict[str, Value]` | 符号表 — 变量名 → IR Value 的映射 |
| `_loop_stack` | `list[str]` | 循环栈 — 追踪嵌套 for 的循环变量名，用于匹配 endfor |

## 解析流程

```
parse(text)
  │
  ├─ 1. new_function("main")       ← 创建 IR 函数
  ├─ 2. new_block("entry")         ← 创建入口基本块
  │
  ├─ 3. 逐行解析 _parse_line(line):
  │      │
  │      ├─ "for i = 0, N"  → builder.for_loop(start, end), 压入 _loop_stack
  │      ├─ "endfor"        → builder.endfor(), 弹出 _loop_stack
  │      ├─ "return x"      → _resolve(x) → builder.ret(val)
  │      ├─ "c = op(args)"  → _resolve 每个参数 → _dispatch_op → builder.op(...)
  │      └─ 其他             → 抛 DSLParseError
  │
  └─ 4. 自动补 return (如果最后一个指令不是 return 且无未闭合循环)
```

## `_resolve` — 名字解析策略

```
_resolve(name)
  ├─ 在 _vars 中? → 直接返回已存在的 Value (已定义变量)
  ├─ 能转 float?  → builder.load_const(val)   (字面常量)
  └─ 都不行       → builder.make_value(name), 记入 _vars (隐式输入参数)
```

最后一条很关键：DSL 不需要显式声明输入变量。写 `c = add(a, b)` 时，如果 `a`/`b` 第一次出现，自动创建为 input value。这让测试极简 — 不需要 preamble。

## `_dispatch_op` — 算子路由表

13 个算子通过 dict(lambda) 分发：

| DSL 算子 | IR builder 方法 | 参数处理 |
|----------|----------------|---------|
| `add` | `builder.add(a, b)` | 两个位置参数 |
| `sub` | `builder.sub(a, b)` | 同上 |
| `mul` | `builder.mul(a, b)` | 同上 |
| `div` | `builder.div(a, b)` | 同上 |
| `neg` | `builder.neg(x)` | 一个位置参数 |
| `exp` | `builder.exp(x)` | 同上 |
| `relu` | `builder.relu(x)` | 同上 |
| `gelu` | `builder.gelu(x)` | 同上 |
| `dot` | `builder.dot(a, b, len)` | kwargs: `len` 或 `length` |
| `matmul` | `builder.matmul(a, b, rows, cols, inner)` | kwargs: `rows`/`m`, `cols`/`n`, `inner`/`k` |
| `softmax` | `builder.softmax(x, axis)` | kwargs: `axis` (默认 -1) |
| `maxpool` | `builder.maxpool(x, kernel, stride)` | kwargs: `kernel` (默认 2), `stride` (默认 2) |

## kwargs 解析 (`_parse_kwargs`)

把 `"rows:4, cols:8, inner:16"` 拆成:
- `plain`: 位置参数列表 `[a, b]`
- `kwargs`: `{rows: 4, cols: 8, inner: 16}`

值自动推断类型: `int` → `float` → `str`。

## 设计要点

1. **无外部依赖** — 不引入任何解析库 (PLY/Lark/ANTLR)，纯 regex，适合 CI 快速测试
2. **与 ONNX 路径同构** — 无论 DSL 还是 ONNX，最终都调用同样的 `IRBuilder` 方法，保证 IR 一致性
3. **隐式输入** — 不需要声明变量，首次引用即创建，降低 DSL 书写负担
4. **自动补 return** — 如果没有显式 return 且不在循环内，自动插入 `ret()`，避免 IR 验证报 block 缺终止指令
5. **循环栈校验** — `endfor` 检查栈非空，防止不匹配

## 在流水线中的位置

```
DSL 文本
  │
  ▼  [DSLParser.parse()]
  IR Program
  │
  ▼  [IRVerifier] → [Optimizer] → [Backend] → 汇编
```
