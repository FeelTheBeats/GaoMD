# GPU编译链路
## 编译方式
- 代码仓：https://github.com/llvm/llvm-project
- 编译命令：
    - make：
        ```make
        cmake -G Ninja ../llvm \
        -DLLVM_ENABLE_PROJECTS="mlir;clang" \
        -DCMAKE_BUILD_TYPE=Release \
        -DLLVM_ENABLE_ASSERTIONS=ON \
        -DLLVM_TARGETS_TO_BUILD="X86;NVPTX" \
        -DCMAKE_EXPORT_COMPILE_COMMANDS=ON
        ```
    - ninja：
        ```ninja
        ninja -j16
        ```
## 编译流程
### linalg to loops
- source mlir
```mlir
module {
  func.func @main() {
    %c4 = arith.constant 4 : index
    %c0f = arith.constant 0.0 : f32

    %A = memref.alloc() : memref<4x4xf32>
    %B = memref.alloc() : memref<4x4xf32>
    %C = memref.alloc() : memref<4x4xf32>

    // 初始化 A 和 B
    linalg.fill ins(%c0f : f32) outs(%A : memref<4x4xf32>)
    linalg.fill ins(%c0f : f32) outs(%B : memref<4x4xf32>)
    linalg.fill ins(%c0f : f32) outs(%C : memref<4x4xf32>)

    call @matmul(%A, %B, %C) :
      (memref<4x4xf32>, memref<4x4xf32>, memref<4x4xf32>) -> ()

    return
  }

  func.func @matmul(%A: memref<4x4xf32>,
                    %B: memref<4x4xf32>,
                    %C: memref<4x4xf32>) {

    linalg.matmul
      ins(%A, %B : memref<4x4xf32>, memref<4x4xf32>)
      outs(%C : memref<4x4xf32>)

    return
  }
}
```
- 执行代码
`mlir-opt test.mlir -convert-linalg-to-loops`

- aim mlir
```mlir
module {
  func.func @main() {
    %c1 = arith.constant 1 : index
    %c4 = arith.constant 4 : index
    %c0 = arith.constant 0 : index
    %cst = arith.constant 0.000000e+00 : f32
    %alloc = memref.alloc() : memref<4x4xf32>
    %alloc_0 = memref.alloc() : memref<4x4xf32>
    %alloc_1 = memref.alloc() : memref<4x4xf32>
    scf.for %arg0 = %c0 to %c4 step %c1 {
      scf.for %arg1 = %c0 to %c4 step %c1 {
        memref.store %cst, %alloc[%arg0, %arg1] : memref<4x4xf32>
      }
    }
    scf.for %arg0 = %c0 to %c4 step %c1 {
      scf.for %arg1 = %c0 to %c4 step %c1 {
        memref.store %cst, %alloc_0[%arg0, %arg1] : memref<4x4xf32>
      }
    }
    scf.for %arg0 = %c0 to %c4 step %c1 {
      scf.for %arg1 = %c0 to %c4 step %c1 {
        memref.store %cst, %alloc_1[%arg0, %arg1] : memref<4x4xf32>
      }
    }
    call @matmul(%alloc, %alloc_0, %alloc_1) : (memref<4x4xf32>, memref<4x4xf32>, memref<4x4xf32>) -> ()
    return
  }
  func.func @matmul(%arg0: memref<4x4xf32>, %arg1: memref<4x4xf32>, %arg2: memref<4x4xf32>) {
    %c0 = arith.constant 0 : index
    %c4 = arith.constant 4 : index
    %c1 = arith.constant 1 : index
    scf.for %arg3 = %c0 to %c4 step %c1 {
      scf.for %arg4 = %c0 to %c4 step %c1 {
        scf.for %arg5 = %c0 to %c4 step %c1 {
          %0 = memref.load %arg0[%arg3, %arg5] : memref<4x4xf32>
          %1 = memref.load %arg1[%arg5, %arg4] : memref<4x4xf32>
          %2 = memref.load %arg2[%arg3, %arg4] : memref<4x4xf32>
          %3 = arith.mulf %0, %1 : f32
          %4 = arith.addf %2, %3 : f32
          memref.store %4, %arg2[%arg3, %arg4] : memref<4x4xf32>
        }
      }
    }
    return
  }
}
```

#### 理解
- Q1：为什么空矩阵会被 linalg to loops 初始化成全0矩阵
    答：编译器行为恕不解释
- Q2：为什么简单的矩阵乘法会被打散成点积形式？
    答：因为计算机没有`width * height`的概念，打成三层循环的形式不但利于后续的优化，也是让IR更好被计算机认识的第一步.但是linalg并不对三层循环强依赖，只是他能很好地表示代数运算，让
    编译器可以很好地进行`tileing\fusion\vectorize`
### linalg to affine loops
- 执行代码
`mlir-opt test.mlir -convert-linalg-to-affine-loops`

- aim code
```mlir
module {
  func.func @main() {
    %cst = arith.constant 0.000000e+00 : f32
    %alloc = memref.alloc() : memref<4x4xf32>
    %alloc_0 = memref.alloc() : memref<4x4xf32>
    %alloc_1 = memref.alloc() : memref<4x4xf32>
    affine.for %arg0 = 0 to 4 {
      affine.for %arg1 = 0 to 4 {
        affine.store %cst, %alloc[%arg0, %arg1] : memref<4x4xf32>
      }
    }
    affine.for %arg0 = 0 to 4 {
      affine.for %arg1 = 0 to 4 {
        affine.store %cst, %alloc_0[%arg0, %arg1] : memref<4x4xf32>
      }
    }
    affine.for %arg0 = 0 to 4 {
      affine.for %arg1 = 0 to 4 {
        affine.store %cst, %alloc_1[%arg0, %arg1] : memref<4x4xf32>
      }
    }
    call @matmul(%alloc, %alloc_0, %alloc_1) : (memref<4x4xf32>, memref<4x4xf32>, memref<4x4xf32>) -> ()
    return
  }
  func.func @matmul(%arg0: memref<4x4xf32>, %arg1: memref<4x4xf32>, %arg2: memref<4x4xf32>) {
    affine.for %arg3 = 0 to 4 {
      affine.for %arg4 = 0 to 4 {
        affine.for %arg5 = 0 to 4 {
          %0 = affine.load %arg0[%arg3, %arg5] : memref<4x4xf32>
          %1 = affine.load %arg1[%arg5, %arg4] : memref<4x4xf32>
          %2 = affine.load %arg2[%arg3, %arg4] : memref<4x4xf32>
          %3 = arith.mulf %0, %1 : f32
          %4 = arith.addf %2, %3 : f32
          affine.store %4, %arg2[%arg3, %arg4] : memref<4x4xf32>
        }
      }
    }
    return
  }
}
```
#### 理解
- 其实不管是`linalg`还是`affine`都是不同的dialect，实际上大家的等级都一样，只是擅长的东西不一样，不过尽管如此，也是有lowering的先后关系。
  `linalg`->`affine/SCF`->`LLVMIR`
- 不同的ai编译器前端可能第一个dialect是不一样的
  | 编译器 / 框架                            | 第一层 MLIR Dialect                   | 特点                                                                   |
  | ----------------------------------- | ---------------------------------- | -------------------------------------------------------------------- |
  | **CUDA C/C++ → MLIR** (`cuda-mlir`) | `gpu` Dialect + Affine / SCF loops | 核心 kernel 循环和线程索引是第一层，矩阵乘法通常是 Affine/SCF 级别的循环，带 GPU block/thread 信息 |
  | **Triton → MLIR**                   | `triton` Dialect                   | 高层 kernel 表示矩阵块操作，保留线程块映射，类似高层 tensor math + GPU mapping             |
  | **ROCm/HIP**                        | `gpu` Dialect + SCF                | 类似 CUDA MLIR，循环展开后结合 GPU block/thread launch                         |

#### Linalg对应到AI编译器流程中属于哪一层？是 Graph IR么？
| MLIR Dialect     | 类比 DL IR 层级            | 说明                                |
| ---------------- | ---------------------- | --------------------------------- |
| **Linalg**       | Tensor IR              | 高层数学语义，矩阵、卷积算子，类似 HLO / Tensor IR |
| **Affine**       | Kernel IR（CPU/GPU）     | 循环和内存访问显式化，可做循环优化、vectorization   |
| **SCF**          | Kernel IR（动态循环）        | 通用循环、条件，支持 runtime variable 循环    |
| **LLVM dialect** | Kernel IR / Lowered IR | 最底层，机器可编译指令，映射到 CPU/GPU           |
所以答案是：
Linalg 并不是 Graph IR，而是 Tensor IR 层
Graph IR 层通常存在在 MLIR 之外，或者在 MLIR 中用 tf / torch dialect 表示
MLIR 的设计就是把 Tensor IR → Kernel IR → LLVM IR 分层清晰化

#### kernal IR是哪一层？
高层模型 / 算子
    │
    ▼
Linalg / Tensor IR          // 高层数学语义
    │
    ▼ convert-linalg-to-loops
Affine / SCF loops           // 显式循环展开
    │
    ▼ map loops to threads
GPU dialect (gpu.launch + gpu.thread_id/block_id)  // 插入线程映射
    │
    ▼ convert to LLVM GPU dialect
LLVM IR (PTX / ROCm)        // 可执行 GPU code
如你所见，是gpu dialect