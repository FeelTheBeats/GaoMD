最近准备离职，有了自己的时间，突然想到有两年的LLVM生涯，也没有略读过整个LLVM的重要部分代码。很好奇从执行`clang main.c`开始，LLVM到底施了什么魔法，把他从C代码变成了可执行文件。要想对整个流程有个把控，也必须从前端入手，我最薄弱的地方。
# 1 从C代码到AST
## 1-1 从OS到LLVM-driver
当手动执行`clang test.c -o test`时，系统会执行一些列动作：
- SHELL 解析命令行
   ```
   command = clang
   args = [main.c]
   ```
- SHELL 寻找clang可执行文件（按顺序检查，找到的第一个clang）
   ```
   echo $PATH
   ```
- SHELL 拉起新进程
   ```
   shell
  │
  ├─ fork()
  │
  └─ child process
        │
        └─ execve("/usr/bin/clang", ["clang","main.c"])
   ```
- WIN内核加载clang可执行文件
   ```
   execve("/usr/bin/clang")
   1️⃣ 打开文件
   2️⃣ 检查文件类型（ELF）
   3️⃣ 创建进程地址空间
   4️⃣ 加载程序段
   ```
- 动态链接器加载依赖库
   ```
   libLLVM.so
   libstdc++.so
   libc.so
   ......

   ELF头会指定dynamic加载器，并执行动态加载，进行：
   加载共享库
   符号重定位
   初始化
   ```
## 1-2 从driver开始的编译器生活(from sourcecode to AST)
从真正构建 `FrontAction` 前，Driver将System将clang联系起来，做了各种重要的初始化工作与数据准备，给语法分析做足了准备。
### 1-2-1 万恶之源 clang_main
对应文件：`clang/tools/driver/driver.cpp`
对应函数：`int clang_main(int Argc, char **Argv, const llvm::ToolContext &ToolContext)`
```shell
clang_main
   │
   ├─ 初始化 LLVM
   │
   ├─ 处理命令行参数
   │
   ├─ 如果是 -cc1
   │     └─ ExecuteCC1Tool()
   │
   ├─ 创建 Diagnostics
   │
   ├─ 创建 Driver
   │
   ├─ Driver.BuildCompilation()
   │     │
   │     ├─ 解析参数
   │     ├─ 构建 Action DAG
   │     └─ 生成 JobList
   │
   ├─ Driver.ExecuteCompilation()
   │     │
   │     ├─ 执行 cc1
   │     ├─ 执行 assembler
   │     └─ 执行 linker
   │
   └─ 返回结果
```
- -cc1 参数的判断
   在给clang添加了`cc1`参数的情况下，不会走默认的编译流程，而是直接跳到`cc1_main`直接开始编译阶段，后面会提到。总之，`cc1`给了用户跳过前叙流程的可能。
- Compilation
   将整个编译流程解耦，从前端的编译，到后端汇编器、链接器任务的调度分开来，我们暂时只专注于前端。
### 1-2-2 Compilation的创建
`BuildCompilation`
对应文件：`clang/lib/Driver/Driver.cpp`
对应函数：`Compilation *Driver::BuildCompilation(ArrayRef<const char *> ArgList)`
编译器把用户命令行转换成一组可执行的编译 Job（cc1 / as / ld）：
```shell
BuildCompilation
 ├─ ParseArgStrings
 ├─ BuildInputs
 ├─ BuildActions
 └─ BuildJobs
 ```
 ### 1-2-3 Compilation的工作
 #### 1-2-3-1 构建 Action DAG
 对应函数：`void Driver::BuildActions(Compilation &C)`
 干了什么：
 ```shell
InputAction
   │
PreprocessJobAction
   │
CompileJobAction
   │
BackendJobAction
   │
AssembleJobAction
   │
LinkJobAction
 ```
#### 1-2-3-2 生成具体编译命令
- 对应函数：`void Driver::BuildJobs(Compilation &C)`
- 干了什么：将 Action DAG 中的每个 Job 转换为具体的编译命令
如：
```shell
clang -cc1 test.c -o test.o
as test.o -o test.o
ld test.o -o test
- 核心逻辑：
```shell
BuildJobs
  ↓
ToolChain::SelectTool
  ↓
Tool::ConstructJob
```

#### 执行编译命令
- 对应函数：`int Compilation::ExecuteJobs()`
- 干了什么：执行 Action DAG 中的每个 Job 对应的编译命令

### 总结
```
Driver::ExecuteCompilation → 
Compilation::ExecuteJobs →
Command::Execute →
llvm::sys::ExecuteAndWait
```
## clang -cc1
### 编译的起始
入口：`llvm::sys::ExecuteAndWait(...)`
文件：`llvm/lib/Support/Program.cpp`
执行命令：
```shell
clang -cc1 test.c -o test.o
```
#### clang -cc1 干了什么
这个 cc1_main 函数是 Clang 编译器的 “前端核心”（Frontend）。当 Clang 驱动器（Driver）完成参数解析和工具链选择后，它会通过 sys::ExecuteAndWait 启动一个新的进程来运行 clang -cc1，此时程序的控制权就会交到这个函数手中。
简单来说，main 函数是 Clang 命令行工具的入口，而 cc1_main 函数是 Clang 真正开始编译代码 的入口。

所在文件：`clang/tools/driver/cc1_main.cpp`
流程：
```shell
cc1_main
  ↓
ExecuteCompilerInvocation
```
- 核心编译执行
```
// 核心调用：执行编译动作
// 这里会根据 Invocation 中的配置，决定是做语法分析、生成 IR 还是生成目标文件
Success = ExecuteCompilerInvocation(Clang.get());
```

## ExecuteCompilerInvocation
对应文件：`clang/lib/Frontend/CompilerInvocation.cpp`
对应函数：`bool ExecuteCompilerInvocation(CompilerInvocation *Invocation, CompilerInstance *Clang)`
干了什么：
```shell
1. 处理 -help
2. 处理 -version
3. 加载插件与处理底层参数
4. 错误检查（短路逻辑）
5. 执行核心编译动作（高潮部分）
- 创建前端动作（FrontendAction）：
- 执行前端动作 here is the vital part of the compilation
- 内存管理（针对调试模式）：
- 返回结果
 ```
### llvm::BuryPointer(std::move(Act));的设计哲学
编译期间一些对象过大，析构过于消耗cpu资源，llvm通过保留指向无用对象指针的方式，来防止此类对象使用析构去通过回溯方式删除其对象体。
- 是否这个优化过于激进，进而会导致内存不够用了？
并不会，因为编译对象直到整个编译结束前都不会被释放，所以我们优化的只是编译结束后"释放内存的时间"。
 ## bool Success = Clang->ExecuteAction(*Act);
 对应文件：`clang/lib/Frontend/CompilerInstance.cpp`
 对应函数：`bool CompilerInstance::ExecuteAction(FrontendAction &Act)`

```shell
ExecuteAction
 ├─ 前置环境检查
 ├─ Frontend初始化
 ├─ Target与编译选项准备
 ├─ 对每个输入文件执行FrontendAction -- vital
 └─ 输出统计信息并返回编译结果
 ```

 ## llvm::Error Err = Act.Execute()
 对应文件：`clang/lib/Frontend/FrontendAction.cpp`
 对应函数：`llvm::Error FrontendAction::Execute()`

```shell
Execute()
 ├─ ExecuteAction()
 └─ rebuild global module index
```

 ## ExecuteAction()
 对应文件：`clang/lib/Frontend/FrontendAction.cpp`
 对应函数：`void ASTFrontendAction::ExecuteAction()`
 
 ```shell
根据Action类型动态绑定的动作，对于 FrontendAction 这里调用的就是 void ASTFrontendAction::ExecuteAction()

Source file
     ↓
Preprocessor
     ↓
Lexer
     ↓
Parser
     ↓
Sema
     ↓
AST

exm：
Lexer
 → int add ( int a , int b ) { ... }

Parser
 → FunctionDecl

Sema
 → 类型检查
 → 构建 AST

ASTContext
 → 保存 FunctionDecl
 ```

 - 真正的编译流程真的如此么？
 教科书中写的`预处理-词法分析-语法分析-语义分析-AST生成`只是一个数据流的体现，真正的流程应该是`Parser 通过 Preprocessor 获取已经完成预处理的 Token。`

 ### 