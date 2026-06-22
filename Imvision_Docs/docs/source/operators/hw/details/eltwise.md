# Eltwise

## 介绍

对两个张量(Tensor) 进行逐点计算。

## 输入

### 说明

- Input0：[C, H, W]
- Input1：[C, H, W]

### 约束

- 无

## 输出

### 说明

- Output：[C, H, W]

### 约束

- 无

## 参数

### 说明

| name        | type | description  |
| ----------- | ---- | ------------ |
| operation   | int  | 运算类型         |
| num_channel | int  | 输入/输出channel |

### 约束

| name      | type | description                                  |
| --------- | ---- | -------------------------------------------- |
| operation | int  | 0：'add', 1: 'sub', 2:'mul', 3:'min', 4:'max' |

## Device

VPU, SPU

## 量化工具支持

支持fp8量化

## SV Interface

### f16

| name   | type   | description |
| ------ | ------ | ----------- |
| hw     | int    | 1:'f16'     |
| hw_acc | int[3] | [5,10,15]   |

**Sample**

```json
{
    "inst_name": "add_0_f16",
    "type_name": "Eltwise3",
    "bottom": ["101", "102"],
    "top": ["103"],
    "hw": 1,
    "hw_acc": [5,10,15],
    "param": {
        "operation": 0,
        "num_channel": 8
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
    "inst_name": "add_0_f8",
    "type_name": "Eltwise3",
    "bottom": ["101", "102"],
    "top": ["103"],
    "hw": 3,
    "hw_acc": [4,3,7],
    "param": {
        "operation": 0,
        "num_channel": 8
    }
}
```
