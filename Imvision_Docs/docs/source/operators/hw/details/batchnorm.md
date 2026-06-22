# BatchNorm

## 介绍

在batch维度进行归一化（一个批次内不同样本的相同特征计算均值和方差）。

## 输入

### 说明

- Input0：[C, H, W]

### 约束

- 无

## 输出

### 说明

- Output：[C, H, W]

### 约束

- 无

## 参数

### 说明

| name          | type           | description         |
| ------------- | -------------- | ------------------- |
| share_channel | int            | 是否各通道共享coef/bias    |
| num_channel   | int            | input/output C 通道个数 |
| bias_neg_mode | int            | 对读取到的bias是否取负号操作    |
| coef          | float16/float8 | 可学习参数权值             |
| bias          | float16/float8 | 可学习参参数偏置            |

### 约束

| name          | type           | description                |
| ------------- | -------------- | -------------------------- |
| share_channel | int            | 0: 不共享各通道的coef/bias, 1: 共享 |
| bias_neg_mode | int            | 0: 不作处理 1：取负号操作            |
| coef          | float16/float8 | 等于C维度个数                    |
| bias          | float16/float8 | 等于C维度个数                    |

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
    "inst_name": "bn_test_f16",
    "type_name": "Bn",
    "bottom": ["data"],
    "top": ["out"],
    "hw": 1,
    "hw_acc": [5, 10, 15],
    "param":{
        "num_channel": 8
    },
    "data":{
      "coef": [0, 15360, 18688, 22080, 18632, 18688, 18687, 14578],
      "bias": [47104, 0, 14578, 16968, 15360, 18688, 22080, 18632],
      "input_dtype": 1,
      "input_acc": [5, 10, 15]
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
    "inst_name": "bn_test_f8",
    "type_name": "Bn",
    "bottom": ["data"],
    "top": ["out"],
    "hw": 3,
    "hw_acc": [5, 2, 1],
    "param":{
        "num_channel": 8
    },
    "data":{
        "coef": [255, 127, 231, 220, 1, 1, 1, 1],
        "bias": [0, 15, 89, 34, 0, 33, 22, 19],
        "input_dtype": 3,
        "input_acc": [5, 2, 1]
    }
}
```
