# Broadcast

## 介绍

对两个输入张量(Tensor)的shape不一致时，将小一点的张量进行扩充。

## 输入

### 说明

- Input0：[C, H, W] Input1: [1, H, W]
- Input0：[C, H, W] Input1: [C, 1, 1]
- Input0：[C, H, W] Input1: [1, 1, 1]

### 约束

- 无

## 输出

### 说明

- Output：[C, H, W]

### 约束

- 无

## 参数

### 说明

-无

### 约束

-无

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
    "inst_name": "broadcast_test_f16",
    "type_name": "Broadcast2",
    "bottom": ["0", "789"],
    "top": ["800"],
    "hw": "f64",
    "hw_acc": [11,52,1023]
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
    "inst_name": "broadcast_test_f8",
    "type_name": "Broadcast2",
    "bottom": ["0", "789"],
    "top": ["800"],
    "hw": 3,
    "hw_acc": [4, 3, 7]
}
```
