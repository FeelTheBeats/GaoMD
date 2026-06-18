# Pool2d

## 介绍

对输入数据进行2D池化运算。

## 输入

### 说明

- Input0：[C, H, W]

### 约束

- 无

## 输出

### 说明

- Output：[C, H, W]

### 约束

- 无

## 参数

### 说明

| name         | type        | description              |
| ------------ | ----------- | ------------------------ |
| pool         | int         | 池化方式                     |
| pad_h        | int         | 垂直对称padding个数            |
| pad_w        | int         | 水平对称padding个数            |
| kernel_h     | int         | 卷积核高（height）             |
| kernel_w     | int         | 卷积核宽（width）              |
| stride_h     | int         | 沿height方向步长              |
| stride_w     | int         | 沿width方向步长               |
| padding_mode | int         | 补pad的模式                  |
| ceil_mode    | int         | 当剩余数据少于kernel_size时，是否保留 |
| mult_pre     | float16/fp8 | 1/kernel_h * kernel_w    |

### 约束

| name         | type | description                                                          |
| ------------ | ---- | -------------------------------------------------------------------- |
| pool         | int  | 0: max, 1: average                                                   |
| kernel_h     | int  | 1 <= kernel_h <=15                                                   |
| kernel_w     | int  | 1 <= kernel_w <=15                                                   |
| stride_h     | int  | (2 <= stride_h <=6 or stride_h == kernel_h) and stride_h <= kernel_h |
| stride_w     | int  | (2 <= stride_w <=6 or stride_w == kernel_w) and stride_w <= kernel_w |
| pad_h        | int  | 0 <= pad_h <= floor(kernel_h/2)                                      |
| pad_w        | int  | 0 <= pad_w <= floor(kernel_w/2)                                      |
| padding_mode | int  | 0：min/zeros, 1: reflect, 2: replicate                                |
| ceil_mode    | int  | 0: 使用floor模式计算输出shape, 1: 使用                                         |

1. 当kernel_h/w为偶数时，硬件要求h up方向pad = kernel/2, 在h down 方向pad = kernel/2 - 1
   1. 编译器内部会做拆分动作，将一个layer拆分为pad+pool2d

## Device

VPU, SPU

## 量化工具支持

- 支持fp16量化

- 支持fp8量化

## SV Interface

### f16

| name   | type   | description |
| ------ | ------ | ----------- |
| hw     | int    | 1:'f16'     |
| hw_acc | int[3] | [5,10,15]   |

**Sample**

```json
{
    "inst_name": "pool2d_test",
    "type_name": "Pool2d",
    "bottom": ["data"],
    "top": ["827_ver1"],
    "hw": 1,
    "hw_acc": [5,10,15],
    "param": {
        "pool": 1,
        "pad_h": 0,
        "pad_w": 0,
        "kernel_h": 3,
        "kernel_w": 3,
        "stride_h": 1,
        "stride_w": 1,
        "padding_mode": 0,
        "ceil_mode": 0,
        "parallelsim": 128
    },
    "data": {
        "mult_pre": 12060
    }
}
```

### f8

| name   | type   | description  |
| ------ | ------ | ------------ |
| hw     | int    | 3:'f8'       |
| hw_acc | int[3] | [4,3,7] etc. |

**Sample**

```json
{
    "inst_name": "pool2d_test",
    "type_name": "Pool2d",
    "bottom": ["data"],
    "top": ["827_ver1"],
    "hw": 3,
    "hw_acc": [4,3,7],
    "param": {
        "pool": 1,
        "pad_h": 0,
        "pad_w": 0,
        "kernel_h": 3,
        "kernel_w": 3,
        "stride_h": 1,
        "stride_w": 1,
        "padding_mode": 0,
        "ceil_mode": 0,
        "parallelsim": 8192
    },
    "data": {
        "mult_pre": 12060
    }
}
```
