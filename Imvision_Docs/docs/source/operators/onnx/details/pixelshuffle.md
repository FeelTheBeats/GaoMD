# Pixelshuffle

## 介绍

通过sub-pixel操作上采样原始图像，扩大图像倍率。

### 输入

### 说明

Input size:[C0, H0, W0]

### 约束

## 输出

### 说明

Output size:[C1, H1, W1]

### 约束

C0 = C1 * r^2
H0 = H1 * r
W0 = W1 * r

## 参数

### 说明

**param**

| name   | type | description |
| ------ | ---- | ----------- |
| factor | int  | 2,4         |

### 约束

## Device

MTE

## 量化工具支持

- [x] 支持fp16量化
- [x] 支持fp8量化

## Reference

[Torch Pixelshuffle](https://pytorch.org/docs/stable/generated/torch.nn.PixelShuffle.html)
