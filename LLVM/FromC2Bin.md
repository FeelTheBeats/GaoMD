# 从C代码到二进制可执行文件
## Clang的使用
`clang test.c -o test`
对应文件：`clang/tools/driver/driver.cpp`
对应函数：`int clang_main(int Argc, char **Argv, const llvm::ToolContext &ToolContext)`
### 从clang到driver

## 构建器的创建与工作

### 构建器的创建
`BuildCompilation`
对应文件：`clang/lib/Driver/Driver.cpp`
对应函数：`Compilation *Driver::BuildCompilation(ArrayRef<const char *> ArgList)`
干了什么：
```shell
BuildCompilation
 ├─ ParseArgStrings
 ├─ BuildInputs
 ├─ BuildActions
 └─ BuildJobs
 ```
 ### 构建器的工作
 #### 构建编译 Action DAG
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
#### 生成具体编译命令
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

 ## bool Success = Clang->ExecuteAction(*Act);