# Interp

## 介绍

对输入图像做两倍上采样。

### 输入

### 说明

Input size:[C0, H0, W0]

### 约束

## 输出

### 说明

Output size:[C0, 2 * H0, 2 * W0]

### 约束

## 参数

### 说明

**param**

| name   | type | description          |
| ------ | ---- | -------------------- |
| interp | int  | 0:bilinear 1:nearest |

### 约束

## Device

MTE

## 量化工具支持

- [x] 支持fp16量化
- [x] 支持fp8量化

## Reference

[Torch Interp](https://pytorch.org/docs/stable/generated/torch.nn.functional.interpolate.html)
