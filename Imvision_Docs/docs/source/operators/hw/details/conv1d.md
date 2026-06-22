# Conv1d

## 介绍

Applies a 1D convolution over an input signal composed of several input planes.

## 输入

### 说明

Input size:[C_in, 1, L_in]

### 约束

## 输出

### 说明

Output size:[C_out, 1, L_out]

L_out= (L_in + 2 * pad - dilation * (kernel - 1) - 1)/stride + 1

### 约束

## 参数

### 说明

**param**

| name         | type | description                                 |
| ------------ | ---- | ------------------------------------------- |
| num_output   | int  | output channel number                       |
| bias_term    | int  | 0: no bias, 1(default) support bias         |
| group        | int  | group number                                |
| pad          | int  | padding                                     |
| kernel       | int  | kernel size                                 |
| stride       | int  | stride                                      |
| dilation     | int  | dilation                                    |
| num_input    | int  | input channel number                        |
| padding_mode | int  | 0:zeros, 1:reflect, 2:replicate, 3:circular |
| partial_sum_order | int[num_input/group] | partial sum order, if gorup == num_output == num_input, fixed as [1] |

**data**

| name         | dim                                                   | acc                                         | bit-width | description                                                                           |
| ------------ | ----------------------------------------------------- | ------------------------------------------- | --------- | ------------------------------------------------------------------------------------- |
| coef         | [num_ouput * (num_input/group) * kernel_h * kernel_w] | bfloat16<br>float16<br>ffp8<br>int8<br>int4 | 16        | standard binary form of bfloat16/float16/ffp8/int8/int4                               |
| bias         | [num_output]                                          | float16                                     | 16        | standard binary form of float16                                                       |
| factor_scale | [num_output]                                          | float16                                     | 16        | standard binary form of float16                                                       |
| coef_dtype   | [1]                                                   | U3.0                                        | 3         | coef data type 1:'f16', 3:'f8', 5:'i8', 4:'i4'                                        |
| coef_acc     | [3]                                                   | U7.0                                        | 7         | coef accuracy [e, m, b] for float('f16'/'f8')<br> [int, sub, sign] for int('i8'/'i4') |

### 约束

1. kernel $\in$ [1, 9]
2. stride $\in$ [1, 2]
3. pad $\in$ [0, 4] (0 or floor((dilation_w * (kernel_w - 1) + 1) / 2))
4. dilation $\in$ [1, 7]
5. dilation*(kernel-1)+1 in [1, 9]
6. stride = 2时，dilation必须为1
7. 当kernel为偶数时，硬件要求h up方向pad = kernel/2, 在h down 方向pad = kernel/2 - 1
   1. 编译器内部会做拆分动作，将一个layer拆分为pad+conv1d

## Device

MPU

## 量化工具支持

- 支持fp16量化

- 支持fp8量化

## Reference

[Torch Conv2d](https://pytorch.org/docs/stable/generated/torch.nn.Conv2d.html)

## SV Interface

### f16

**Sample**

```json
{
    "inst_name": "Conv1d_f16_test",
    "type_name": "Conv1d",
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

**Sample**

```json
{
    "inst_name": "Conv1d_f8_test",
    "type_name": "Conv1d",
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
        "partial_sum_order":[4,0,0,0]
    },
    "data": {
        "coef": [20,149,129,144,23,7,149,162,139,24,27,161,166,27,154,35,
                22,154,146,152,150,142,142,4,8,19,17,1,129,6,143,154,
                129,155,27,15],
        "factor_scale": [146,152,150],
        "coef_dtype": 3,
        "coef_acc": [4,3,7],
        "input_dtype": 3,
        "input_acc":[4, 3, 7]
        }
}
```
