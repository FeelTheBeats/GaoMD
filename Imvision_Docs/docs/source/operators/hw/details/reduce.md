# Reduce

## 介绍

对输入Tensor进行规约。

## 输入

### 说明

- Input0：[C, H, W]

### 约束

- 无

## 输出

### 说明

- Output：[C, 1, 1] or [1, 1, 1]

### 约束

- 无

## 参数

### 说明

| name     | type | description     |
| -------- | ---- | --------------- |
| func     | int  | 运算类型            |
| keep_dim | int  | 控制通道是否分开channel |

### 约束

| name     | type | description                 |
| -------- | ---- | --------------------------- |
| func     | int  | 3：'min', 4: 'max', 5:'sum'  |
| keep_dim | int  | 0: 输出[1, 1,1] 1：输出[C, 1, 1] |

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
    "inst_name": "reduce_test_f16",
    "type_name": "Reduce",
    "bottom": ["101"],
    "top": ["102"],
    "hw": 1,
    "hw_acc": [5, 10, 15],
    "param":{
        "func": 4,
        "keep_dim": 0
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
    "inst_name": "reduce_test_f8",
    "type_name": "Reduce",
    "bottom": ["101"],
    "top": ["102"],
    "hw": 3,
    "hw_acc": [4, 3, 7],
    "param":{
        "func": 4,
        "keep_dim": 0
    }
}
```
