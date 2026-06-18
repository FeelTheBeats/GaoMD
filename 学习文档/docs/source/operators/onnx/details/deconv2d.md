# ConvTranspose2d

## 介绍

Applies a 2D transposed convolution over an input signal composed of several input planes.

## 输入

### 说明

Input size:[C_in, H_in, W_in]

### 约束

## 输出

### 说明

Output size:[C_out, H_out, W_out]

H_out= (H_in - 1) * stride_h - 2 * pad_h + dilation_h * (kernel_h - 1) + output_pad_h + 1<br />
W_out= (W_in - 1) * stride_w - 2 * pad_w + dilation_w * (kernel_w - 1) + output_pad_w + 1

### 约束

## 参数

### 说明

**param**

| name              | type                 | description                                                                      |
| ----------------- | -------------------- | -------------------------------------------------------------------------------- |
| num_output        | int                  | output channel number                                                            |
| bias_term         | int                  | 0: no bias, 1(default) support bias                                              |
| group             | int                  | group number                                                                     |
| pad_h             | int                  | padding vertical                                                                 |
| pad_w             | int                  | padding horizontal                                                               |
| kernel_h          | int                  | kernel height                                                                    |
| kernel_w          | int                  | kernel width                                                                     |
| stride_h          | int                  | stride vertical                                                                  |
| stride_w          | int                  | stride horizontal                                                                |
| dilation_h        | int                  | dilation vertical                                                                |
| dilation_w        | int                  | dilation horizontal                                                              |
| num_input         | int                  | input channel number                                                             |
| padding_mode      | int                  | 0:zeros, 1:reflect, 2:replicate                                                  |
| output_pad_h      | int                  | controls the additional size added to bottom side of the output shape, default:0 |
| output_pad_w      | int                  | controls the additional size added to right side of the output shape, default:0  |
| partial_sum_order | int[num_input/group] | partial sum order, if gorup == num_output == num_input, fixed as [1]             |

**data**

| name              | type                                                         | description                                                                           |
| ----------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------- |
| coef              | double[num_input * (num_output/group) * kernel_h * kernel_w] | convolution filter weight                                                             |
| bias              | double[num_output]                                           | convolution bias                                                                      |
| coef_scale        | double[num_output]                                           | coef scale                                                                            |
| coef_zero_point   | double[num_output]                                           | coef zero point                                                                       |
| bias_scale        | double[num_output]                                           | bias scale                                                                            |
| bias_zero_point   | double[num_output]                                           | bias zero point                                                                       |
| input_scale       | double[num_input]                                            | input tensor scale                                                                    |
| input_zero_point  | double[num_input]                                            | input tensor zero point                                                               |
| output_scale      | double[num_output]                                           | output tensor scale                                                                   |
| output_zero_point | double[num_output]                                           | output tensor zero point                                                              |
| coef_dtype        | int                                                          | coef data type 1:'f16', 3:'f8', 5:'i8', 4:'i4'                                        |
| coef_acc          | int[3]                                                       | coef accuracy [e, m, b] for float('f16'/'f8')<br> [int, sub, sign] for int('i8'/'i4') |
| input_dtype       | string                                                       | 'f8': only for fp8 inferecne                                                          |
| input_acc         | int[3]                                                       | only for fp8 inferecne                                                                |

### 约束

- kernel_h/w $\in$ [1, 9]

- stride_h/w $\in$ [1, 2]

- pad_h/w $\in$ [0, 4] ，并且只能是下面两种情况：
  1. pad_h/w全部为0
  2. pad_h/w = floor((dilation_w * (kernel_w - 1) + 1) / 2)

- dilation_h/w $\in$ [1, 7]

- dilation_h/w*(kernel_h/w-1)+1 $\in$ [1, 9]

- dilation_h/w*(kernel_h-1)+1 <= ifm_h/w

- stride_h = stride_w

- output_pad_h/w必须小于stride_h/w或者必须小于dilation_h/w

## Device

MPU

## 量化工具支持

- [x] 支持fp16量化
- [x] 支持fp8量化

## Reference

[Torch ConvTranspose2d](https://pytorch.org/docs/stable/generated/torch.nn.ConvTranspose2d.html)
