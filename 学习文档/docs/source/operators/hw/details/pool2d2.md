# Pool2d2

## 介绍

池化运算,包括最大池化以及平均池化。

## 输入

### 说明

Input size:[C, Hin, Win]

### 约束

## 输出

### 说明

Output size:[C, Hout, Wout]

Hout= Hin/2<br />
Wout= Win/2

### 约束

## 参数

### 说明

**param**

| name      | type | description                                                |
| --------- | ---- | ---------------------------------------------------------- |
| pool      | int  | 0/1, 0:最大池化 1: 平均池化                                        |
| ceil_mode | int  | 当剩余数据少于kernel size时，0：用floor模式计算输出shape，1：用ceil模式计算输出shape |

### 约束

| param      | hw/hw_acc | constrain                 |
| ---------- | --------- | ------------------------- |
| kernel_h/w | int       | kernel_h == kernel_w == 2 |
| stride_h/w | int       | stride_h == stride_w == 2 |
| pad_h/w    | int       | pad_h == pad_w == 0       |

## Device

MPU

## 量化工具支持

支持fp8量化

## Reference

[Torch Pooling](https://pytorch.org/docs/stable/generated/torch.nn.MaxPool2d.html)

## SV Interface

### f16

| name   | type   | description |
| ------ | ------ | ----------- |
| hw     | int    | 1:'f16'     |
| hw_acc | int[3] | [5,10,15]   |

**Sample**

```json
{
    "inst_name": "pool2d2_test",
    "type_name": "Pool2d2",
    "bottom": [
        "data"
    ],
    "top": [
        "1"
    ],
    "param": {
        "pool": 0,
        "ceil_mode": 1
    },
    "hw": 1,
    "hw_acc": [
        5,
        10,
        15
    ]
}
```

### f8

| name   | type   | description  |
| ------ | ------ | ------------ |
| hw     | int    | 3:'f8'       |
| hw_acc | int[3] | [4,3,7] etc. |

```json
{
    "inst_name": "pool2d2_test",
    "type_name": "Pool2d2",
    "bottom": [
        "data"
    ],
    "top": [
        "1"
    ],
    "param": {
        "pool": 0,
        "ceil_mode": 1
    },
    "hw": 3,
    "hw_acc": [
        4,
        3,
        7
    ]
}
```
