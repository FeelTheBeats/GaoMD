# LayerNorm

## 介绍

层归一化LN(Layer-Normalization Layer)是在特征(通道)维度进行归一化
(对feature map每个点在通道维度进行归一化操作)。计算公式如下：

y=  (x-E[x])/√(Var[x]+ ε)* γ+ β

其中x为输入张量中feature map特定点在channel维度的所有元素，y为输出张量中feature map特定点
在channel维度的所有元素，β和γ是可学习的仿射变换参数，用于将归一化后的数据再次缩放得到新的数据，
ε作用是防止数值计算不稳定。


## 输入

### 说明

- Input0：[C, H, W]
- eps: [1]
- beta: [C]
- gamma: [C]


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
| hw            | int            | 1:’f16’             |
| hw_acc        | int[3]         | float(f16):[e,m,b]  |
| eps           | float16        | 数值稳定参数          |
| lut_mode      | int            | 1：连续曲线函数       |
| sig_mode      | int            | 1：正常模式           |
| bin_mode      | int            | 1：64bin              |
| cal_mode      | int            | 1：插值计算时减去lutx[i] |
| mult_pre      | float16        | 1/ch, 用于在CH维度求平均 |
| coef[num_channel]    | float16     | 仿射变换参数 gamma       |
| bias[num_channel]    | float16     | 仿射变换参数 beta        |
| lut_x[64]            | float16     | LUT x coordinates       |
| lut_y[64]            | float16     | LUT y coordinates       |
| lut_k[65]            | float16     | LUT slope               |

### 约束

- 无

## Device

VPU, SPU

## 量化工具支持

- [x] 支持fp16量化
