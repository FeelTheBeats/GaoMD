# Constantpad

## 介绍

对输入feature map的边缘扩展pad值，可在fm的上下左右四个边缘部分扩展。

### 输入

### 说明

Input size:[C0, H0, W0]

### 约束

## 输出

### 说明

Output size:[C0, H1, W1]

### 约束

H1 = H0 + pad_top + pad_bottom

W1 = W0 + pad_left + pad_right

## 参数

### 说明

**param**

| name  | type  | description |
| ----- | ----- | ----------- |
| pad_l | int   | 左侧pad个数     |
| pad_r | int   | 右侧pad个数     |
| pad_t | int   | 上边pad个数     |
| pad_b | int   | 下边pad个数     |
| value | float | 扩展的数值       |

### 约束

| param       | hw/hw_acc | constrain     |
| ----------- | --------- | ------------- |
| pad_l/r/t/b | int       | 0<=kernel<=15 |

## Device

MTE

## 量化工具支持

- [x] 支持fp16量化
- [x] 支持fp8量化

## Reference

[Torch Pad](https://pytorch.org/docs/stable/generated/torch.nn.functional.pad.html)
