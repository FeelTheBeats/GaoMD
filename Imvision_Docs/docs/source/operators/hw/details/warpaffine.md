# Warpaffine

## 介绍

对输入图像中的像素通过grid矩阵或者affine矩阵进行变换。

### 输入

### 说明

Input0 size:[C0, H0, W0]<br />
Input1 size:[2, H0, W0]

### 约束

## 输出

### 说明

Output size:[C0, H0, W0]

### 约束

## 参数

### 说明

**param**

| name             | type | description                  |
| ---------------- | ---- | ---------------------------- |
| interp           | int  | 0:bilinear 1:nearest         |
| mode             | int  | 0:warp 1:affine              |
| align_corners    | int  | 0:false 1:true               |
| border_mode      | int  | 0:固定数值padding, 1:边界数值padding |
| border_value     | int  | 默认值为0                        |
| affn_store_hsize | int  | output width                 |
| affn_store_vsize | int  | output height                |
| affn_x_offset_w  | int  | matrix0                      |
| affn_x_offset_h  | int  | matrix1                      |
| affn_y_offset_w  | int  | matrix3                      |
| affn_y_offset_h  | int  | matrix4                      |
| affn_start_x     | int  | input tensor startx坐标        |
| affn_start_y     | int  | input tensor startx坐标        |
| warp_coef_w      | int  | (width-1)/2                  |
| warp_coef_h      | int  | (height-1)/2                 |

### 约束

| param         | hw/hw_acc | constrain              |
| ------------- | --------- | ---------------------- |
| mode          | int       | mode = 1时必须为两输入        |
| border_mode   | int       | border_mode = 0        |
| warp_coef_w/h | int       | warp_coef_w/h <= 16384 |

dtype只支持fp16，不支持fp8

## Device

MTE

## 量化工具支持

dtype只支持fp16，不支持fp8

## Reference

## SV Interface

### f16

| name   | type   | description |
| ------ | ------ | ----------- |
| hw     | int    | 1:'f16'     |
| hw_acc | int[3] | [5,10,15]   |

**Sample**

```json
{
    "inst_name": "warpaffine_test",
    "type_name": "Warpaffine",
    "bottom": [
        "101",
        "102"
    ],
    "top": [
        "103"
    ],
    "hw": 1,
    "hw_acc": [
        5,
        10,
        15
    ],
    "param": {
        "mode": 0,
        "interp": 0,
        "align_corners": 1,
        "border_mode": 0,
        "border_value": 0,
        "affn_store_hsize": 272,
        "affn_store_vsize": 272,
        "affn_x_offset_w": 4096,
        "affn_x_offset_h": 0,
        "affn_y_offset_w": 0,
        "affn_y_offset_h": 4096,
        "affn_start_x": 0,
        "affn_start_y": 0
    },
    "data": {
        "warp_coef_w": 271,
        "warp_coef_h": 271
    }
}
```
