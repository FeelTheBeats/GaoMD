# GlobalPool2d

## 介绍

对输入数据进行2D全局池化运算。

## 输入

### 说明

- Input0：[C, H, W]

### 约束

- 无

## 输出

### 说明

- Output：[C, 1, 1]

### 约束

- 无

## 参数

### 说明

| name     | type        | description |
| -------- | ----------- | ----------- |
| pool     | int         | 池化方式        |
| mult_pre | float16/fp8 | 1/HW        |

### 约束

| name | type | description        |
| ---- | ---- | ------------------ |
| pool | int  | 0: max, 1: average |

## Device

VPU, SPU

## 量化工具支持

- [x] 支持fp16量化
- [x] 支持fp8量化
