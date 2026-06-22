# Permute

## 介绍

用来对输入张量维度进行不同顺序的排列，得到一个新的张量。

## 输入

### 说明

Input size:[C0, H0, W0]

### 约束

## 输出

### 说明

Output size:[C1, H1, W1]

### 约束

Mode = 0,WHC: C1==W0,H1==H0,W1==C0<br />
Mode = 1,CWH: C1==C0,H1==W0,W1==H0<br />
Mode = 2,HWC: C1==H0,H1==W0,W1==C0<br />
Mode = 3,WCH: C1==W0,H1==C0,W1==H0<br />
Mode = 4,HCW: C1==H0,H1==C0,W1==W0

## 参数

### 说明

**param**

| name | type | description                       |
| ---- | ---- | --------------------------------- |
| mode | int  | 0:WHC, 1:CWH, 2:HWC, 3:WCH, 4:HCW |

### 约束

## Device

MTE

## 量化工具支持

支持fp8量化

## Reference

[Torch Permute](https://pytorch.org/docs/stable/generated/torch.permute.html)

## SV Interface

### f16

| name   | type   | description |
| ------ | ------ | ----------- |
| hw     | int    | 1:'f16'     |
| hw_acc | int[3] | [5,10,15]   |

**Sample**

```json
{
    "inst_name": "temp2.inc.permute_f16",
    "type_name": "Permute2",
    "bottom": ["data"],
    "top": ["800"],
    "hw": 1,
    "hw_acc": [5,10,15],
    "param": {
        "mode": 4
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
    "inst_name": "temp2.inc.permute_f16",
    "type_name": "Permute2",
    "bottom": ["data"],
    "top": ["800"],
    "hw": 3,
    "hw_acc": [4,3,7],
    "param": {
        "mode": 4
    }
}
```
