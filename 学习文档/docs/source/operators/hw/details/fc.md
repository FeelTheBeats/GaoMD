# Fully-Connected

## 介绍

每一个节点与权值做矩阵乘运算，用来把前级节点的特征综合起来。

## 输入

### 说明

- Input0：[1, 1, W]

### 约束

- 无

## 输出

### 说明

- Output：[1, 1, W]

### 约束

- 无

## 参数

### 说明

| name         | type           | description |
| ------------ | -------------- | ----------- |
| num_input    | int            | 输入数据个数      |
| num_output   | int            | 输出数据个数      |
| coef         | float16/float8 | 可学习参数权值     |
| bias         | float16/float8 | 可学习参参数偏置    |
| coef_dtype   | int            | coef 数据类型   |
| coef_acc     | int            | coef 数据精度   |
| input_dtype  | int            | 输入数据类型      |
| input_acc    | int            | 输入数据精度      |
| output_dtype | int            | 输出数据类型      |
| output_acc   | int            | 输出数据精度      |

### 约束

- 无

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
    "inst_name": "single_fc3_layer",
    "type_name": "Fc3",
    "bottom": ["data"],
    "top": ["800"],
    "hw": 1,
    "hw_acc": [5, 10, 15],
    "param": {
        "num_input": 4,
        "num_output": 3
    },
    "data": {
        "coef": [44939, 45287, 46419, 46125,
                 46628, 45384, 0,     11774,
                 12526, 44720, 44711, 12477],
        "bias": [44809, 42382, 42809],
        "coef_dtype": 1,
        "coef_acc": [5, 10, 15]
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
    "inst_name": "single_fc3_layer",
    "type_name": "Fc3",
    "bottom": ["data"],
    "top": ["800"],
    "hw": 3,
    "hw_acc": [4, 3, 7],
    "param": {
        "num_input": 4,
        "num_output": 3
    },
    "data": {
        "coef": [49, 87, 19, 25,
                 48, 84, 0, 14,
                 16, 20, 11, 77],
        "bias": [49, 82, 49],
        "coef_dtype": 3,
        "coef_acc": [4, 3, 7]
    }
}
```
