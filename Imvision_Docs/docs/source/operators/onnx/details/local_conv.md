# LocalConv

## 介绍

LocalConv与Conv2d的区别在于一个feature map上的局部区域内参数是共享的，而在不同区域是不同的。

## 输入

### 说明

- Input0：[1, H, W]

### 约束

- 无

## 输出

### 说明

- Output：[1, H, W]

### 约束

- 无

## 参数

### 说明

| name         | type | description   |
| ------------ | ---- | ------------- |
| num_channel  | int  | 输入/输出C维度个数    |
| pad_h        | int  | 垂直对称padding个数 |
| pad_w        | int  | 水平对称padding个数 |
| kernel_h     | int  | 卷积核高（height）  |
| kernel_w     | int  | 卷积核宽（width）   |
| stride_h     | int  | 沿height方向步长   |
| stride_w     | int  | 沿width方向步长    |
| padding_mode | int  | 补pad的模式       |
| dilation_h   | int  | 沿height方向空洞数  |
| dilation_w   | int  | 沿width方向空洞数   |

### 约束

| name         | type | description                       |
| ------------ | ---- | --------------------------------- |
| kernel_h     | int  | 3                                 |
| kernel_w     | int  | 3                                 |
| stride_h     | int  | 1                                 |
| stride_w     | int  | 1                                 |
| pad_h        | int  | pad_h == dilation_h               |
| pad_w        | int  | pad_w == dilation_w               |
| padding_mode | int  | 0：zeros, 1: reflect, 2: replicate |
| dilation_h   | int  | 1 or 2                            |
| dilation_w   | int  | 1 or 2                            |

## Device

VPU, SPU

## 量化工具支持

- [x] 支持fp16量化
- [] 支持fp8量化
