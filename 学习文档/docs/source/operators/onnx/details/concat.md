# Concat

## 介绍

拼接运算,用来对两个张量再某个维度dim上进行拼接。

## 输入

### 说明

Input0 size:[C0, H0, W0]<br />
Input1 size:[C1, H1, W1]

### 约束

Concat C:H0==H1,W0==W1<br />
Concat H:C0==C1,W0==W1<br />
Concat W:H0==H1,C0==C1

## 输出

### 说明

Output size:[C2, H2, W2]

### 约束

Concat C:H0==H1==H2,W0==W1==w2<br />
Concat H:C0==C1==C2,W0==W1==w2<br />
Concat W:H0==H1==H2,C0==C1==C2

## 参数

### 说明

**param**

| name | type | description        |
| ---- | ---- | ------------------ |
| dim  | int  | 1/2/3, 1:c 2:W 3:H |

### 约束

| param    | hw/hw_acc | constrain             |
| -------- | --------- | --------------------- |
| Concat C | int       | H0==H1==H2,W0==W1==w2 |
| Concat H | int       | C0==C1==C2,W0==W1==w2 |
| Concat W | int       | H0==H1==H2,C0==C1==C2 |

## Device

MTE

## 量化工具支持

- [x] 支持fp16量化
- [x] 支持fp8量化

## Reference

[Torch Concat](https://pytorch.org/docs/stable/generated/torch.concatenate.html)
