# Broadcast

## 介绍

对两个输入张量(Tensor)的shape不一致时，将小一点的张量进行扩充。

## 输入

### 说明

- Input0：[C, H, W] Input1: [1, H, W]
- Input0：[C, H, W] Input1: [C, 1, 1]
- Input0：[C, H, W] Input1: [1, 1, 1]

### 约束

- 无

## 输出

### 说明

- Output：[C, H, W]

### 约束

- 无

## 参数

### 说明

-无

### 约束

-无

## Device

VPU, SPU

## 量化工具支持

- [x] 支持fp16量化
- [x] 支持fp8量化
