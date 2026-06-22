# Compare

## 介绍

Compare用来对两个张量（Tensor）进行逐元素比较计算，当input0和input1对应位置的
元素满足比较运算时，输出1，否则输出0。

## 输入

### 说明

- Input0：[1, 1, W]
- Input1: [1, 1, W]

### 约束

- 无

## 输出

### 说明

- Output：[1, 1, W]

### 约束

- 无

## 参数

### 说明

| name          | type           | description         |
| ------------- | -------------- | ------------------- |
| hw            | int            | 1:’f16’, 3:’f8’     |
| hw_acc        | int[3]         | float(f16/f8):[e,m,b]  |
| operation     | int            | 0: 'gt', 1: 'lt'      |

### 约束

- 无

## Device

VPU, SPU

## 量化工具支持

- [x] 支持fp16量化
- [x] 支持fp8量化
