# Softmax

## 介绍

Softmax是将各个输出节点的输出值范围映射到[0,1]，并且约束各个输出节点的输出值的和为1的函数。Softmax的含义在于不再唯一的确定某一个最大值，而是为每个输出分类的结果都赋予一个概率值。

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
| hw            | int            | 1: ‘f16’            |
| hw_acc        | int[3]         | 固定[e,m,b]: [5,10,15] |
| mode          | int            | 0: softmax; 1: softmin |
| num_channel   | int            | Input/output tensor channel number |
| exp_lut_mode  | int            | 0/1，0:折线类函数 1：连续曲线函数    |
| exp_sig_mode  | int            | 0/1/2，0:奇函数模式 1：正常模式 2: 偶函数模式 |
| exp_bin_mode  | int            | 0/1/2，0:35bin  1：64bin  2:4bin  |
| exp_cal_mode  | int            | 0/1，0:插值计算时不减lutx[i] 1：插值计算时减去lutx[i] |
| inv_lut_Mode  | int            | 0/1，0:折线类函数 1：连续曲线函数 |
| inv_sig_mode  | int            | 0/1/2，0:奇函数模式 1：正常模式 2: 偶函数模式 |
| inv_bin_mode  | int            | 0/1/2，0:35bin  1：64bin  2:4bin |
| inv_cal_mode  | int            | 0/1，0:插值计算时不减lutx[i] 1：插值计算时减去lutx[i] |
| exp_lut_x[64]   | float16      | Exp LUT x coordinates |
| exp_lut _y[64]  | float16      | Exp LUT y coordinates |
| exp_lut _k[65]  | float16      | Exp LUT slope         |
| inv_lut _x[64]  | float16      | Inv LUT x coordinates |
| inv_lut _y[64]  | float16      | Inv LUT y coordinates |
| inv_lut _k[65]  | float16      | Inv LUT slope         |

### 约束

- 无

## Device

VPU, SPU

## 量化工具支持

- [x] 支持fp16量化
