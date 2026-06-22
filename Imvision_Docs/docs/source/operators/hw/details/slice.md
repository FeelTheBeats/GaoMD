# Slice

## 介绍

切片操作,用来对张量在某个维度dim上进行切片操作。

## 输入

### 说明

Input size:[C0, H0, W0]

### 约束

## 输出

### 说明

Output size:[C1, H1, W1]

### 约束

Slice C:H0==H1,W0==W1<br />
Slice H:C0==C1,W0==W1<br />
Slice W:H0==H1,C0==C1

## 参数

### 说明

**param**

| name        | type | description             |
| ----------- | ---- | ----------------------- |
| dim         | int  | 1/2/3, 1:C 2:W 3:H      |
| start_index | int  | start position of slice |
| output_size | int  | output size of slice    |

### 约束

| param                    | hw/hw_acc | constrain                               |
| ------------------------ | --------- | --------------------------------------- |
| start_index, output_size | int       | Slice C: start_index + output_size <=C0 |
| start_index, output_size | int       | Slice H: start_index + output_size <=H0 |
| start_index, output_size | int       | Slice W  start_index + output_size <=W0 |

## Device

MTE

## 量化工具支持

支持fp8量化

## Reference

[Torch Slice](https://www.tensorflow.org/api_docs/python/tf/strided_slice)

## SV Interface

### f16

| name   | type   | description |
| ------ | ------ | ----------- |
| hw     | int    | 1:'f16'     |
| hw_acc | int[3] | [5,10,15]   |

**Sample**

```json
{
    "inst_name": "temp2.inc.slice_f16",
    "type_name": "Slice2",
    "bottom": ["data"],
    "top": ["800"],
    "hw": 1,
    "hw_acc": [
        5,
        10,
        15
    ],
    "param": {
        "dim": 1,
        "start_index": 2,
        "output_size": 9
    }
}
```

### f8

| name   | type   | description  |
| ------ | ------ | ------------ |
| hw     | int    | 3:'f8'       |
| hw_acc | int[3] | [4,3,7] etc. |

```json
{
    "inst_name": "temp2.inc.slice_f16",
    "type_name": "Slice2",
    "bottom": ["data"],
    "top": ["800"],
    "hw": 3,
    "hw_acc": [
        4,
        3,
        7
    ],
    "param": {
        "dim": 1,
        "start_index": 2,
        "output_size": 9
    }
}
```
