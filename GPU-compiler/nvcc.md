# NVCC - Nvidia CUDA Compiler
## A Complete Compile Process
### 1. nvcc 前端拆分（host / device 分离）
- 功能：将 CUDA C/C++ 代码拆分成 host 代码和 device 代码
- 过程：
  - 解析 CUDA 扩展语法（如 `__global__`、`__device__` 等）
  - 生成 host 代码（CPU 执行的部分）
  - 生成 device 代码（GPU 执行的部分）
- 例：
    ```c++
    // ==========================================
    // 1. DEVICE 部分 (GPU 执行)
    // 特征：__global__ 关键字，处理并行逻辑
    // ==========================================
    __global__ void kernalFunc(int *res) {
        *res = 1 + 1; // GPU 内部的小计算
    }

    // ==========================================
    // 2. HOST 部分 (CPU 执行)
    // 特征：main 函数，负责管理内存和启动 GPU
    // ==========================================
    int main() {
        int *d_res;
        cudaMalloc(&d_res, sizeof(int)); // 在 GPU 上挖块地

        // --- 核心粘合点 ---
        // 用 <<< >>> 启动 GPU 任务，这是 nvcc 拆分代码的关键标志
        kernalFunc<<<1, 1>>>(d_res); 

        cudaFree(d_res); // 清理
        return 0;
    }
    ```
- .cu文件中不是只有cuda原代码么，为什么会有将cuda C++代码拆分成host和device代码的过程
    .cu 文件本质上是一个容器。拆分过程就像是在翻译一本中英双语手册：
    - 把中文部分撕下来交给中国翻译（C++ 编译器处理 Host 代码）。
    - 把英文部分撕下来交给英国翻译（NVIDIA 工具处理 Device 代码）。
    - 最后通过一个索引（CUDA Runtime）把两边关联起来。
### 2. NVVM IR（LLVM-like 中间表示）
from `.gpu` to `NVVM IR`
CUDA device code 会先变成：`LLVM IR (NVVM dialect)`
这一层类似：
```
LLVM IR for GPU
SSA 形式
target-independent
```
### 3. PTX（CUDA 的“虚拟 ISA”）
然后变成`PTX assembly`
如：`add.s32 %r1, %r2, %r3;`
它不是 GPU 真指令，而是“可移植 GPU 汇编”

### 4. SASS（真实 GPU 指令）
再由 ptxas 或 driver JIT 编译 PTX 为 GPU 可执行代码（SASS）。

### 5. GPU 执行（warp scheduler）
warp（32 threads）
SIMT 执行模型
register file + shared memory

### 关键问题
- 那计算结果如何返回呢？我理解cpu作为leader，会等待GPU的结果，依赖这些结果推进逻辑运算，这样会不会造成逻辑结构的阻塞？
    1. 计算结果如何返回？
        核心指令： cudaMemcpy(..., cudaMemcpyDeviceToHost)
        动作： 这一行代码就像一个“关卡”。CPU 执行到这里时会停下，伸出手去 GPU 那里接数据，直到数据全部传输完成，CPU 才会继续跑下一行代码。
    2. 会造成逻辑阻塞吗？
        会，但也不完全会。 这里的关键在于 CUDA 的设计哲学：同步阻塞、异步非阻塞（Stream）
    3. 阻塞其实是双刃剑：
        - 优点：确保数据安全，避免 race condition
        - 缺点：占用 GPU 资源，影响并行效率