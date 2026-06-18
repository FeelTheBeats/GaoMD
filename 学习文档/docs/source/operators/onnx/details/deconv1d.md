# ConvTranspose1d

## 介绍

Applies a 1D transposed convolution over an input signal composed of several input planes.

## 输入

### 说明

Input size:[C_in, 1, L_in]

### 约束

## 输出

### 说明

Output size:[C_out, 1, L_out]

L_out= (L_in - 1) * stride - 2 * pad + dilation * (kernel - 1) + output_pad + 1

### 约束

## 参数

### 说明

**param**
| name              | type                 | description                                                                   |
| ----------------- | -------------------- | ----------------------------------------------------------------------------- |
| num_output        | int                  | output channel number                                                         |
| bias_term         | int                  | 0: no bias, 1(default) support bias                                           |
| group             | int                  | group number                                                                  |
| pad               | int                  | padding                                                                       |
| kernel            | int                  | kernel size                                                                   |
| stride            | int                  | stride                                                                        |
| dilation          | int                  | dilation                                                                      |
| num_input         | int                  | input channel number                                                          |
| padding_mode      | int                  | 0:zeros                                                                       |
| output_pad        | int                  | controls the additional size added to one side of the output shape, default:0 |
| partial_sum_order | int[num_input/group] | partial sum order, if gorup == num_output == num_input, fixed as [1]          |

### 约束

* kernel $\in$ [1, 9]
* stride $\in$ [1, 2]
* pad(dilation*(kernel-1) - pad _ output_pad) $\in$ [0, 4]
* dilation $\in$ [1, 7]

## Device

MPU

## 量化工具支持

- [x] 支持fp16量化
- [x] 支持fp8量化

## Reference

[Torch ConvTranspose1d](https://pytorch.org/docs/stable/generated/torch.nn.ConvTranspose1d.html)
