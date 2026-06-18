# Wino2d

## 介绍

Applies a winograd 2D convolution over an input signal composed of several input planes.

## 输入

### 说明

Input size:[C_in, H_in, W_in]

### 约束

## 输出

### 说明

Output size:[C_out, H_out, W_out]

H_out= (H_in + 2 * pad_h - dilation_h * (kernel_h - 1) - 1)/stride_h + 1

W_out= (W_in + 2 * pad_w - dilation_w * (kernel_w - 1) - 1)/stride_w + 1

### 约束

## 参数

### 说明

**param**

| name              | type                 | description                                                          |
| ----------------- | -------------------- | -------------------------------------------------------------------- |
| num_output        | int                  | output channel number                                                |
| bias_term         | int                  | 0: no bias, 1(default) support bias                                  |
| group             | int                  | group number                                                         |
| pad_h             | int                  | padding vertical                                                     |
| pad_w             | int                  | padding horizontal                                                   |
| kernel_h          | int                  | kernel height                                                        |
| kernel_w          | int                  | kernel width                                                         |
| stride_h          | int                  | stride vertical                                                      |
| stride_w          | int                  | stride horizontal                                                    |
| dilation_h        | int                  | dilation vertical                                                    |
| dilation_w        | int                  | dilation horizontal                                                  |
| num_input         | int                  | input channel number                                                 |
| padding_mode      | int                  | 0:zeros, 1:reflect, 2:replicate                                      |
| partial_sum_order | int[num_input/group] | partial sum order, if gorup == num_output == num_input, fixed as [1] |

**data**

| name         | type                                                        | description                                     | default |
| ------------ | ----------------------------------------------------------- | ----------------------------------------------- | ------- |
| coef         | double[num_ouput * (num_input/group) * kernel_h * kernel_w] | convolution filter weight                       | /       |
| bias         | double[num_output]                                          | convolution bias                                | /       |
| coef_dtype   | int/str                                                     | coef data type 1:'f16', 3:'f8'                  | hw      |
| coef_acc     | int[3]                                                      | coef accuracy [e, m, b] for float('f16'/'f8')   | hw_acc  |
| input_dtype  | int/str                                                     | input data type 1:'f16', 3:'f8'                 | hw      |
| input_acc    | int[3]                                                      | input accuracy [e, m, b] for float('f16'/'f8')  | hw_acc  |
| output_dtype | int/str                                                     | output data type 1:'f16', 3:'f8'                | hw      |
| output_acc   | int[3]                                                      | output accuracy [e, m, b] for float('f16'/'f8') | hw_acc  |

### 约束

* kernel_h== kernel_w ==1 or 3
* stride_h== stride_w ==1
* dilation_h == dilation_w == 1
* pad_h/w $\in$ [0, 7]

## Device

MPU

## 量化工具支持

- [x] 支持fp16量化
- [x] 支持fp8量化

## Reference

[Torch Conv2d](https://pytorch.org/docs/stable/generated/torch.nn.Conv2d.html)
