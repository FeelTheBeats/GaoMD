# GlobalPool2d

## 介绍

对输入数据进行2D全局池化运算。

## 输入

### 说明

- Input0：[C, H, W]

### 约束

- 无

## 输出

### 说明

- Output：[C, 1, 1]

### 约束

- 无

## 参数

### 说明

| name     | type        | description |
| -------- | ----------- | ----------- |
| pool     | int         | 池化方式        |
| mult_pre | float16/fp8 | 1/HW        |

### 约束

| name | type | description        |
| ---- | ---- | ------------------ |
| pool | int  | 0: max, 1: average |

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
    "inst_name": "fp16_test",
    "type_name": "GlobalPool2d",
    "bottom": ["data"],
    "top": ["800"],
    "hw": 1,
    "hw_acc": [5, 10, 15],
    "param": {
        "pool": 1
    },
    "data": {
        "mult_pre": 8072
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
    "inst_name": "fp16_test",
    "type_name": "GlobalPool2d",
    "bottom": ["data"],
    "top": ["800"],
    "hw": 3,
    "hw_acc": [4, 3, 7],
    "param": {
        "pool": 1
    },
    "data": {
        "mult_pre": 15
    }
}
```
