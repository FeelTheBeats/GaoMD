# Reflectionpad

## 介绍

根据输入feature map的边缘数据对fm进行对称扩展。

### 输入

### 说明

Input size:[C0, H0, W0]

### 约束

## 输出

### 说明

Output size:[C0, H1, W1]

### 约束

H1 = H0 + pad_top + pad_bottom<br />
W1 = W0 + pad_left + pad_right

## 参数

### 说明

**param**

| name  | type | description              |
| ----- | ---- | ------------------------ |
| pad_l | int  | 左侧pad个数                  |
| pad_r | int  | 右侧pad个数                  |
| pad_t | int  | 上边pad个数                  |
| pad_b | int  | 下边pad个数                  |
| mode  | int  | 0:symmetric,1:reflection |

### 约束

| param       | hw/hw_acc | constrain                      |
| ----------- | --------- | ------------------------------ |
| pad_l/r/t/b | int       | 0<=kernel<=15 and < input_size |

## Device

MTE

## 量化工具支持

支持fp8量化

## Reference

[Torch Pad](https://pytorch.org/docs/stable/generated/torch.nn.functional.pad.html)

## SV Interface

### f16

| name   | type   | description |
| ------ | ------ | ----------- |
| hw     | int    | 1:'f16'     |
| hw_acc | int[3] | [5,10,15]   |

**Sample**

```json
{
"inst_name": "ConstantPad2d_0",
"type_name": "ConstantPad2d",
"hw": 1,
"hw_acc": [5,10,15],
"bottom": ["data"],
"top": ["data_pst"],
"param":
    {
        "pad_l": 1,
        "pad_r": 0,
        "pad_t": 1,
        "pad_b": 0,
        "mode": 1
    },
}
```

### f8

| name   | type   | description  |
| ------ | ------ | ------------ |
| hw     | int    | 3:'f8'       |
| hw_acc | int[3] | [4,3,7] etc. |

```json
{
"inst_name": "ConstantPad2d_0",
"type_name": "ConstantPad2d",
"hw": 3,
"hw_acc": [4,3,7],
"bottom": ["data"],
"top": ["data_pst"],
"param":
    {
        "pad_l": 1,
        "pad_r": 0,
        "pad_t": 1,
        "pad_b": 0,
        "mode": 1
    },
}
```
