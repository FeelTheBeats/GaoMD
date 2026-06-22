# Pixelunshuffle

## 介绍

通过sub-pixel操作下采样原始图像，扩大图像倍率。

### 输入

### 说明

Input size:[C0, H0, W0]

### 约束

## 输出

### 说明

Output size:[C1, H1, W1]

### 约束

C1 = C0 * r^2
H1 = H0 * r
W1 = W0 * r

## 参数

### 说明

**param**

| name   | type | description |
| ------ | ---- | ----------- |
| factor | int  | 2,4         |

### 约束

## Device

MTE

## 量化工具支持

支持fp8量化

## Reference

[Torch Pixelunshuffle](https://pytorch.org/docs/stable/generated/torch.nn.PixelUnshuffle.html)

## SV Interface

### f16

| name   | type   | description |
| ------ | ------ | ----------- |
| hw     | int    | 1:'f16'     |
| hw_acc | int[3] | [5,10,15]   |

**Sample**

```json
{
    "inst_name": "temp2.downc0.pixelunshuffle_f16",
    "type_name": "PixelUnshuffle2",
    "bottom": ["data"],
    "top": ["789"],
    "hw": 1,
    "hw_acc": [5,10,15],
    "param": {
        "factor": 2
    }
}
```

### f8

| name   | type   | description  |
| ------ | ------ | ------------ |
| hw     | int    | 3:'f8'       |
| hw_acc | int[3] | [4,3,7] etc. |
| hw_acc | int[3] | [5,2,7] etc. |

```json
{
    "inst_name": "temp2.downc0.pixelunshuffle_f16",
    "type_name": "PixelUnshuffle2",
    "bottom": ["data"],
    "top": ["789"],
    "hw": 3,
    "hw_acc": [4,3,7],
    "param": {
        "factor": 2
    }
}
```
