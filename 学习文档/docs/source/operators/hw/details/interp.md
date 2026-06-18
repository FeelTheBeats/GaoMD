# Interp

## 介绍

对输入图像做两倍上采样。

### 输入

### 说明

Input size:[C0, H0, W0]

### 约束

## 输出

### 说明

Output size:[C0, 2 * H0, 2 * W0]

### 约束

## 参数

### 说明

**param**

| name   | type | description          |
| ------ | ---- | -------------------- |
| interp | int  | 0:bilinear 1:nearest |

### 约束

## Device

MTE

## 量化工具支持

支持fp8量化

## Reference

[Torch Interp](https://pytorch.org/docs/stable/generated/torch.nn.functional.interpolate.html)

## SV Interface

### f16

| name   | type   | description |
| ------ | ------ | ----------- |
| hw     | int    | 1:'f16'     |
| hw_acc | int[3] | [5,10,15]   |

**Sample**

```json
{
    "inst_name": "interp",
    "type_name": "Interp3",
    "bottom": ["data"],
    "top": ["816"],
    "hw": 1,
    "hw_acc": [5,10,15],
    "param": {
        "interp": 1
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
    "inst_name": "interp",
    "type_name": "Interp3",
    "bottom": ["data"],
    "top": ["816"],
    "hw": 3,
    "hw_acc": [4,3,7],
    "param": {
        "interp": 1
    }
}
```
