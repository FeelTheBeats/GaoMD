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

支持fp8量化

## Reference

[Torch ConvTranspose1d](https://pytorch.org/docs/stable/generated/torch.nn.ConvTranspose1d.html)

## SV Interface

### f16

| name   | type   | description |
| ------ | ------ | ----------- |
| hw     | int    | 1:'f16'     |
| hw_acc | int[3] | [5,10,15]   |

**Sample**

```json
{
    "inst_name": "ConvTranspose1d_f16_test",
    "type_name": "ConvTranspose1d",
    "bottom": ["824_pst"],
    "top": ["827_ver1"],
    "hw": 1,
    "hw_acc": [5,10,15],
    "param": {
        "num_output": 4,
        "bias_term": 1,
        "group": 1,
        "pad": 0,
        "kernel": 3,
        "stride": 1,
        "dilation": 1,
        "num_input": 4,
        "padding_mode": 0,
        "output_pad": 0,
        "partial_sum_order":[4,0,0,0]
    },
    "data": {
        "coef": [44939, 45287, 46419, 46125, 46628, 45384, 0, 11774, 12526, 44720, 44711, 12477, 9738, 45657, 12610, 10315, 
                13727, 11868, 0, 45796, 13280, 42192, 45495, 44086, 32768, 44683, 0, 11340, 12581, 44808, 43754, 44982, 
                32768, 12511, 0, 45818, 14361, 32768, 45497, 0, 14105, 13275, 45787, 46807, 0, 45151, 14067, 13179],
        "bias": [13280, 42192, 45495, 44086],
        "factor_scale": [15360, 15360, 15360, 15360],
        "coef_dtype": 1,
        "coef_acc": [5,10,15]
        }
}
```

### f8

| name   | type   | description  |
| ------ | ------ | ------------ |
| hw     | int    | 3:'f8'       |
| hw_acc | int[3] | [4,3,7] etc. |

**Sample**

```json
{
    "inst_name": "ConvTranspose1d_f8_test",
    "type_name": "ConvTranspose1d",
    "bottom": ["824_pst"],
    "top": ["827_ver1"],
    "hw": 3,
    "hw_acc": [4,3,7],
    "param": {
        "num_output": 3,
        "bias_term": 1,
        "group": 1,
        "pad": 0,
        "kernel": 3,
        "stride": 1,
        "dilation": 1,
        "num_input": 4,
        "padding_mode": 0,
        "output_pad": 0,
        "partial_sum_order":[4,0,0,0]
    },
    "data": {
        "coef": [129,149,20,161,27,24,150,152,146,6,129,1,7,23,144,154,
                    27,166,4,142,142,129,154,143,139,162,149,154,22,35,17,19,
                    8,15,27,155],
        "bias": [146,152,150],
        "factor_scale": [15360, 15360, 15360],
        "coef_dtype": 3,
        "coef_acc": [4,3,7],
        "input_dtype": 3,
        "input_acc":[4, 3, 7]
        }
}
```

## Reference

[Torch ConvTranspose1d](https://pytorch.org/docs/stable/generated/torch.nn.ConvTranspose1d.html)
