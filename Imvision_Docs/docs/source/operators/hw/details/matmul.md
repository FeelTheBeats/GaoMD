# Matmul

## 介绍

Perform matrix mutiplication on two tensors.

## 输入

### 说明

- Only support two input tensors，more than 3 input tensors need to be split into multiple Matmul.

### 约束

- W0 == H1, input0[C, H0, W0], input1[C, H1, W1] .

## 输出

### 说明

Output size:[C, H0, W1]

### 约束

## 参数

### 说明

**param**

| name        | type | description                 |
| ----------- | ---- | --------------------------- |
| num_channel | int  | input/output channel number |

**data**
| name         | dim | acc  | bit-width | description                         |
| ------------ | --- | ---- | --------- | ----------------------------------- |
| input0_dtype | [1] | int  | 3         | 3:'f8', only for fp8 inferene       |
| input0_acc   | [3] | int  | 8         | [e, m, b] for float ('f16'/'f8')    |
| input1_dtype | [1] | int  | 3         | 3:'f8', only for fp8 inferene       |
| input1_acc   | [3] | int  | 8         | [e, m, b] for float ('f16'/'f8')    |

### 约束

## Device

MPU

## 量化工具支持

支持fp8量化

## Reference

[torch.matmul](https://pytorch.org/docs/stable/generated/torch.matmul.html)#

## SV Interface

### f16

| name   | type   | description |
| ------ | ------ | ----------- |
| hw     | int    | 1:'f16'     |
| hw_acc | int[3] | [5,10,15]   |

**param**

| name        | type | description                 |
| ----------- | ---- | --------------------------- |
| num_channel | int  | input/output channel number |

**Sample**

```json
{
    "name": "single_matmul_layer",
    "input_tensor": ["0", "1"],
    "input_shape": [{"dim": [1,4,272,272], "dtype": "f16", "hw_acc": [5, 10, 15], "pack": 0},
                    {"dim": [1,4,272,272], "dtype": "f16", "hw_acc": [5, 10, 15], "pack": 0}],
    "output_tensor": ["102"],
    "output_shape": [{"dtype":"f16","hw_acc":[5, 10, 15], "pack": 0}],
    "layer": [
        {
            "inst_name": "temp2.inc.matmul_f16",
            "type_name": "Matmul",
            "bottom": ["0", "1"],
            "top": ["102"],
            "hw": 1,
            "hw_acc": [5, 10, 15],
            "param":{
                "num_channel": 4
            }
        }
    ]
}
```

### fp8

| name   | type   | description                |
| ------ | ------ | -------------------------- |
| hw     | int    | 3:'f8'                     |
| hw_acc | int[3] | [4,3,b], [5,2,b], b:[0,32] |

**param**

| name        | type | description                 |
| ----------- | ---- | --------------------------- |
| num_channel | int  | input/output channel number |

**Sample**

```json
{
    "name": "single_matmul_layer",
    "input_tensor": ["0", "1"],
    "input_shape": [{"dim": [1,4,272,272], "dtype": "f8", "hw_acc": [4, 3, 7], "pack": 0},
                    {"dim": [1,4,272,272], "dtype": "f8", "hw_acc": [4, 3, 7], "pack": 0}],
    "output_tensor": ["102"],
    "output_shape": [{"dtype":"f8","hw_acc":[4, 3, 7], "pack": 0}],
    "layer": [
        {
            "inst_name": "temp2.inc.matmul_f8",
            "type_name": "Matmul",
            "bottom": ["0", "1"],
            "top": ["102"],
            "hw": 3,
            "hw_acc": [4, 3, 7],
            "param":{
                "num_channel": 4
            }
        }
    ]
}
```
