# BatchNorm

## 介绍

在batch维度进行归一化（一个批次内不同样本的相同特征计算均值和方差）。

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

| name          | type           | description         |
| ------------- | -------------- | ------------------- |
| share_channel | int            | 是否各通道共享coef/bias    |
| num_channel   | int            | input/output C 通道个数 |
| bias_neg_mode | int            | 对读取到的bias是否取负号操作    |
| coef          | float16/float8 | 可学习参数权值             |
| bias          | float16/float8 | 可学习参参数偏置            |

### 约束

| name          | type           | description                |
| ------------- | -------------- | -------------------------- |
| share_channel | int            | 0: 不共享各通道的coef/bias, 1: 共享 |
| bias_neg_mode | int            | 0: 不作处理 1：取负号操作            |
| coef          | float16/float8 | 等于C维度个数                    |
| bias          | float16/float8 | 等于C维度个数                    |

## Device

VPU, SPU

## 量化工具支持

- [x] 支持fp16量化
- [x] 支持fp8量化
