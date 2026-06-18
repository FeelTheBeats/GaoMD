# Fully-Connected

## 介绍

每一个节点与权值做矩阵乘运算，用来把前级节点的特征综合起来。

## 输入

### 说明

- Input0：[1, 1, W]

### 约束

- 无

## 输出

### 说明

- Output：[1, 1, W]

### 约束

- 无

## 参数

### 说明

| name         | type           | description |
| ------------ | -------------- | ----------- |
| num_input    | int            | 输入数据个数      |
| num_output   | int            | 输出数据个数      |
| coef         | float16/float8 | 可学习参数权值     |
| bias         | float16/float8 | 可学习参参数偏置    |
| coef_dtype   | int            | coef 数据类型   |
| coef_acc     | int            | coef 数据精度   |
| input_dtype  | int            | 输入数据类型      |
| input_acc    | int            | 输入数据精度      |
| output_dtype | int            | 输出数据类型      |
| output_acc   | int            | 输出数据精度      |

### 约束

- 无

## Device

VPU, SPU

## 量化工具支持

- [x] 支持fp16量化
- [x] 支持fp8量化
