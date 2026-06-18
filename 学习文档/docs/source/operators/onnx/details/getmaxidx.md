# GetMaxIdx

## 介绍

Getmaxidx算子可以得到输入tensor中最大值所在位置的index信息。

## 输入

### 说明

- Input0：[1, 1, W]

### 约束

- 无

## 输出

### 说明

- Output：[1, 1, 1]

### 约束

- 无

## 参数

### 说明

| name          | type           | description         |
| ------------- | -------------- | ------------------- |
| hw            | int            | 1:’f16’             |
| hw_acc        | int[3]         | float(f16):[e,m,b]  |
| output_dtype  | int            | 8:‘u16’             |
| output_acc    | int[3]         | [16,0,0]            |

### 约束

| name          | type           | description         |
| ------------- | -------------- | ------------------- |
| Input Size: [1, 1, N]    | int    |  要求输入向量维度，N<=65535 |

## Device

VPU, SPU

## 量化工具支持

- [x] 支持fp16量化
