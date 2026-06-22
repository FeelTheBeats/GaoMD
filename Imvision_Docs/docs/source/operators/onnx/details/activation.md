# Activation

## 介绍

激活函数（Activation Function）是神经网络中每个神经元的重要组成部分。它决定了输入信号经过神经元后的输出结果，并赋予神经网络非线性建模能力。没有激活函数的神经网络只是一层线性变换，无法处理复杂的非线性问题。

## 输入

### 说明

Input size:[C, H, W]

### 约束

## 输出

### 说明

Output size:[C, H, W]

### 约束

## 参数

### 说明

**param**

| name     | type | description                             |
| -------- | ---- | --------------------------------------- |
| sig_mode | int  | 0/1/2, 0:奇函数模式 1: 正常模式 2:偶函数模式          |
| bin_mode | int  | 0/1/2, 0:35bin 1: 64bin 2:4bin          |
| cal_mode | int  | 0/1, 0:插值计算时不减lutx[i] 1: 插值计算时减去lutx[i] |

**data**

| name                         | bit-width         | description       |
| ---------------------------- | ----------------- | ----------------- |
| lut_x[64]/lut_x[35]/lut_x[4] | float16<br>float8 | LUT x coordinates |
| lut_y[64]/lut_y[35]/lut_y[4] | float16<br>float8 | LUT y coordinates |
| lut_x[64]/lut_x[35]/lut_x[4] | float16<br>float8 | LUT k coordinates |
| input_dtype                  | float16<br>float8 |                   |
| input_acc                    | float16<br>float8 |                   |
| output_dtype                 | float16<br>float8 |                   |
| output_acc                   | float16<br>float8 |                   |

### 约束

1. Lut_x需要满足：Lut_x[i] <= Lut_x[i+1]

| input_dtype/acc       | hw/hw_acc             | output_dtype/acc      |
| --------------------- | --------------------- | --------------------- |
| 1.f16/[5,10,15]       | 1.f16/[5,10,15]       | 1.f16/[5,10,15]       |
|                       |                       | 2.f8/[4,3,b],b:[0,29] |
|                       |                       | 3.f8/[5,2,b],b:[0,29] |
| 1.f8/[4,3,b],b:[0,29] | 1.f8/[4,3,b],b:[0,29] | 1.f16/[5,10,15]       |
| 2.f8/[5,2,b],b:[0,29] | 2.f8/[5,2,b],b:[0,29] | 2.f8/[4,3,b],b:[0,29] |
|                       |                       | 3.f8/[5,2,b],b:[0,29] |

## Device

MPU

## 量化工具支持

- [x] 支持fp16量化
- [x] 支持fp8量化

## Reference

[Torch Activation](https://pytorch.org/docs/stable/generated/torch.nn.ReLU.html)
