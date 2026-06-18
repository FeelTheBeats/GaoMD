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

- 支持fp16量化

- 支持fp8量化

## Reference

[Torch Conv2d](https://pytorch.org/docs/stable/generated/torch.nn.Conv2d.html)

## SV Interface

### f16

**Sample**

```json
{
    "inst_name": "wino2d_f16_test",
    "type_name": "Wino2d",
    "bottom": ["824_pst"],
    "top": ["827_ver1"],
    "hw": 1,
    "hw_acc": [5,10,15],
    "param": {
        "num_output": 3,
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
        "coef": [12789,11824,10948,43183,13274,11648,13034,11071,44810,44751,44933,44874,43647,44927,10714,42315,
                11296,6043,44379,45231,7111,42317,45381,45581,13149,11727,10265,44766,12652,11357,43587,45262,
                7522,4280,45244,45282,45330,45896,45035,45612,11518,44535,7762,45384,44412,46372,10183,45714,
                12392,11848,12478,12018,41686,12289,10967,12837,44163,44374,41499,42588,45847,43830,44755,11136,
                43554,45277,13349,12533,10947,42358,11484,5920,45908,45682,43606,42393,45083,44168,45937,45466,
                10626,13205,38044,12843,43425,12571,45222,11126,12045,12882,40571,11567,9708,12207,45264,43737,
                9475,12826,12467,13590,11600,12443,13184,13498,11856,12425,12011,12502,12591,11795,12867,12318,
                11388,45065,10952,45206,46149,46653,45470,46278,11790,45178,44858,46479,46018,46709,46454,47109,
                44649,44186,44110,43262,45625,45216,42925,9503,10810,44721,10998,44626,43481,45483,11742,43287,
                45471,45637,42943,43639,44568,9025,10950,12594,12298,43560,12120,43935,12957,12591,12885,12520,
                45787,11979,11391,13888,45240,7628,12256,13419,44121,11879,10118,12881,37982,36668,11587,11597,
                10063,10371,10900,11119,43597,10462,7272,11740,5784,6172,8878,8930,44256,7400,43099,10754],
        "bias": [13280, 42192, 45495, 44086]
        }
}
```

### f8

**Sample**

```json
{
    "inst_name": "wino2d_f8_test",
    "type_name": "Wino2d",
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
        "coef": [36,28,22,145,40,27,38,22,158,158,159,159,149,159,20,139,
                    24,1,155,161,2,139,163,164,39,28,16,158,35,25,149,162,
                    3,0,161,162,162,167,160,164,26,156,3,163,155,170,16,165,
                    33,29,33,30,135,32,22,36,153,155,134,141,166,150,158,23,
                    148,162,40,34,22,139,26,1,167,165,149,139,160,153,167,163,
                    19,39,129,36,147,34,161,23,30,37,131,26,12,31,162,150,
                    10,36,33,42,27,33,39,41,29,33,30,34,34,28,37,32,
                    25,160,22,161,169,172,163,170,28,161,158,171,168,173,171,176,
                    157,153,153,146,164,161,143,10,20,157,22,157,148,163,28,146,
                    163,165,143,149,156,7,22,34,32,148,31,151,37,34,37,34,
                    166,30,25,45,161,3,32,41,153,29,15,37,129,0,27,27,
                    15,17,21,23,149,18,2,28,1,1,7,7,154,2,145,20],
        "bias": [146,152,150],
        "coef_dtype": 3,
        "coef_acc":[4,3,7],
        "input_dtype": 3,
        "input_acc":[4, 3, 7]
        }
}
```
