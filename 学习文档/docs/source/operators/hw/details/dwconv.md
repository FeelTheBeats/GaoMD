# DWConv

## 介绍

Applies a 2D convolution over an input signal composed of several input planes.

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

1. kernel_h/w $\in$ [1, 15]

2. stride_h/w $\in$ [1, 2]

3. pad_h/w $\in$ [0, 7] ，并且只能是下面两种情况：
   1. pad_h/w全部为0
   2. pad_h/w = floor((dilation_w * (kernel_w - 1) + 1) / 2)

4. dilation_h/w $\in$ [1, 7]

5. dilation_h/w*(kernel_h/w-1)+1 $\in$ [1, 9]、

6. dilation_h/w*(kernel_h-1)+1 <= ifm_h/w

7. stride_h = 2或stride_w = 2时，dilation_h和dilation_w必须为1

8. 当kernel_h/w为偶数时，硬件要求h up方向pad = kernel/2, 在h down 方向pad = kernel/2 - 1
   1. 编译器内部会做拆分动作，将一个layer拆分为pad+conv2d

## Device

1. MPU

2. VPU

## 量化工具支持

- 支持fp16量化

- 支持fp8量化

## Reference

[Torch Conv2d](https://pytorch.org/docs/stable/generated/torch.nn.Conv2d.html)

## SV Interface

### fp16

| name   | type   | description |
| ------ | ------ | ----------- |
| hw     | int    | 1:'f16'     |
| hw_acc | int[3] | [5,10,15]   |

**Sample**

```json
{
    "inst_name": "Conv2d_f16_test",
    "type_name": "Conv2d",
    "bottom": ["824_pst"],
    "top": ["827_ver1"],
    "hw": 1,
    "hw_acc": [5,10,15],
    "param": {
        "num_output": 4,
        "bias_term": 1,
        "group": 1,
        "pad_h": 0,
        "pad_w": 0,
        "kernel_h": 3,
        "kernel_w": 3,
        "stride_h": 1,
        "stride_w": 1,
        "dilation_h": 1,
        "dilation_w": 1,
        "num_input": 4,
        "padding_mode": 0,
        "partial_sum_order":[4,0,0,0]
    },
    "data": {
        "coef": [44939, 45287, 46419, 46125, 46628, 45384, 0, 11774, 12526, 44720, 44711, 12477, 9738, 45657, 12610, 10315, 
                13727, 11868, 0, 45796, 13280, 42192, 45495, 44086, 32768, 44683, 0, 11340, 12581, 44808, 43754, 44982, 
                32768, 12511, 0, 45818, 14361, 32768, 45497, 0, 14105, 13275, 45787, 46807, 0, 45151, 14067, 13179,
                11868, 0, 45796, 13280, 42192, 45495, 44086, 32768, 44683, 0, 11340, 12581, 44808, 7384, 123, 112,
                0, 13280, 42192, 45495, 44086, 32768, 44683, 0, 11340, 12581, 44808, 43754, 44982, 0, 23141, 
                32768, 12511, 0, 45818, 14361, 32768, 45497, 0, 14105, 13275, 45787, 46807, 0, 45151, 14067, 13179,
                45495, 44086, 32768, 44683, 0, 11340,  0, 45818, 14361, 32768, 45497, 0, 14105, 13275, 14067, 44808,
                13727, 11868, 0, 45796, 13280, 42192, 45495, 44086, 32768, 44683, 0, 11340, 12581, 44808, 43754, 44982,
                46125, 46628, 45384, 0, 11774, 12526, 44720, 44711, 11340, 12581, 44808, 43754, 44982, 0, 23141, 1314],
        "bias": [13280, 42192, 45495, 44086],
        "coef_dtype": 1,
        "coef_acc": [5,10,15],
        "output_dtype": 3,
        "output_acc": [4,3,7],
        }
}
```

### fp8

**Sample**

```json
{
    "inst_name": "Conv2d_f8_test",
    "type_name": "Conv2d",
    "bottom": ["824_pst"],
    "top": ["827_ver1"],
    "hw": 3,
    "hw_acc": [4,3,7],
    "param": {
        "num_output": 3,
        "bias_term": 1,
        "group": 1,
        "pad_h": 0,
        "pad_w": 0,
        "kernel_h": 5,
        "kernel_w": 5,
        "stride_h": 1,
        "stride_w": 1,
        "dilation_h": 1,
        "dilation_w": 1,
        "num_input": 4,
        "padding_mode": 0,
        "partial_sum_order":[4,0,0,0]
    },
    "data": {
        "coef": [194,65,44,64,186,32,66,184,177,66,56,56,192,65,68,191,
                183,190,193,63,33,188,196,54,54,192,54,59,186,65,66,67,
                46,63,188,67,187,0,48,177,64,68,67,50,7,35,185,68,
                191,66,64,51,174,194,181,171,47,56,190,60,35,59,64,193,
                66,19,62,59,51,160,59,66,66,68,24,194,175,185,35,187,
                187,187,190,60,55,0,63,164,29,67,193,58,64,170,58,195,
                35,53,67,12,25,41,195,195,67,194,62,193,47,194,193,195,
                192,187,194,163,49,67,39,54,68,24,130,55,178,66,193,174,
                171,59,33,62,64,49,186,191,65,195,180,59,57,194,67,56,
                194,57,53,194,194,61,38,194,187,172,39,194,194,195,33,66,
                41,194,43,59,175,183,192,55,180,66,48,194,55,192,172,65,
                194,192,68,58,60,4,190,184,58,64,68,182,65,67,189,185,
                178,196,65,62,32,191,61,50,65,192,56,59,43,193,179,176,
                11,191,192,63,173,194,66,65,149,58,195,64,178,54,65,192,
                193,163,195,185,192,66,193,185,56,67,59,173,63,50,65,189,
                56,37,57,178,65,192,58,194,187,57,174,64,64,192,64,181,
                192,57,65,190,178,163,190,65,195,53,184,67,62,180,168,67,
                161,64,196,52,59,160,187,178,65,191,32,36,65,47,67,193,
                183,187,45,184,35,192,191,59,189,194,25,187],
        "bias": [55,190,58],
        "coef_dtype": 3,
        "coef_acc": [4,3,7],
        "input_dtype": 3,
        "input_acc":[4, 3, 7],
        "output_dtype": 1,
        "output_acc":[5, 10, 15]
        }
}
```
