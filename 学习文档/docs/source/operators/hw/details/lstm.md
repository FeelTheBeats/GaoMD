# LSTM

## 介绍

LSTM算法是一种重要的目前使用最多的时间序列算法，是一种特殊的RNN（Recurrent Neural Network，循环神经网络），  
能够学习长期的依赖关系。主要是为了解决长序列训练过程中的梯度消失和梯度爆炸问题。

## 输入

### 说明

- Input0: [1, 1, input_size]
- Input1: [num_layers, 2, hidden_size]
Input1表示每层初始隐藏层以及细胞状态，其中[num_layers, 0, hidden_size]表示隐藏层输入,  
[num_layers, 1, hidden_size]表示细胞状态输入；

### 约束

- 无

## 输出

### 说明

- Output：[num_layers, 2, hidden_size]

### 约束

- 无

## 参数

### 说明

| name          | type           | description         |
| ------------- | -------------- | ------------------- |
| hw            | int            | 1:’f16’, 3:’f8’     |
| hw_acc        | int[3]         | float(f16/f8):[e,m,b]  |
| Input_size    | int            | 输入向量维度            |
| Hidden_size   | int            | 隐藏层维度              |
| Num_layers    | int            | Lstm堆叠层数            |
| Bias          | int            | 0/1 计算时是否需要bias参与运算 |
| Weight_ih_l0  | float16        | Lstm layer0输入矩阵运算权重    |
| Weight_hh_l0  | float16        | Lstm layer0隐藏层矩阵运算权重  |
| Bias_ih_l0    | float16        | Lstm layer0输入矩阵运算偏置    |
| Bias_hh_l0    | float16        | Lstm layer0隐藏层矩阵运算偏置   |
| Weight_ih_ln  | float16        | Lstm layer1~n输入矩阵运算权重   |
| Weight_hh_ln  | float16        | Lstm layer1~n隐藏层矩阵运算权重 |
| Bias_ih_ln    | float16        | Lstm layer1~n输入矩阵运算偏置   |
| Bias_hh_ln    | float16        | Lstm layer1~n隐藏层矩阵运算偏置 |
| Sigmoid_lut_mode   | int       | Sigmoid lut拟合参数，固定为1 |
| Sigmoid_sig_mode   | int       | Sigmoid lut拟合参数，固定为1 |
| Sigmoid_idx_mode   | int       | Sigmoid lut拟合参数，固定为0 |
| Sigmoid_cal_mode   | int       | Sigmoid lut拟合参数，固定为1 |
| Sigmoid_lut_x      | float16   | Sigmoid lutx |
| Sigmoid_lut_y      | float16   | Sigmoid luty |
| Sigmoid_lut_k      | float16   | Sigmoid lutk |
| Tanh_lut_mode      | int       | Tanh lut拟合参数，固定为1 |
| Tanh_sig_mode      | int       | Tanh lut拟合参数，固定为1 |
| Tanh_idx_mode      | int       | Tanh lut拟合参数，固定为0 |
| Tanh_cal_mode      | int       | Tanh lut拟合参数，固定为1 |
| Tanh_lut_x         | float16   | Tanh lutx |
| Tanh_lut_y         | float16   | Tanh luty |
| Tanh_lut_k         | float16   | Tanh lutk |

### 约束

| name          | type           | description         |
| ------------- | -------------- | ------------------- |
| hw            | int            | 1:’f16’, 3:’f8’     |
| hw_acc        | int[3]         | float(f16/f8):[e,m,b]  |
| Input_size    | int            | 输入向量维度            |
|
| Bias          | int            | Bias=0|| Bias=1     |
| Input_size    | int            | Input_size>=1       |
| hidden_size   | int            | hidden_size>=1      |
| num_layers    | int            | num_layers>=1       |
| Input0 Size | int |Input0与input1 size必须与LSTM设置参数相同，其中[num_layers, 0, hidden_size]表示隐藏层输入，[num_layers, 1, hidden_size]表示细胞状态输入 |
| Output Size   | int            | 与input1 Size完全相同 |

## Device

VPU, SPU

## 量化工具支持

- [x] 支持fp16量化