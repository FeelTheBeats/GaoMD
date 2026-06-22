# Eltwise

## 介绍

对两个张量(Tensor) 进行逐点计算。

## 输入

### 说明

- Input0：[C, H, W]
- Input1：[C, H, W]

### 约束

- 无

## 输出

### 说明

- Output：[C, H, W]

### 约束

- 无

## 参数

### 说明

| name        | type | description  |
| ----------- | ---- | ------------ |
| operation   | int  | 运算类型         |
| num_channel | int  | 输入/输出channel |

### 约束

| name      | type | description                                  |
| --------- | ---- | -------------------------------------------- |
| operation | int  | 0：'add', 1: 'sub', 2:'mul', 3:'min', 4:'max' |

## Device

VPU, SPU

## 量化工具支持

- [x] 支持fp16量化
- [x] 支持fp8量化
