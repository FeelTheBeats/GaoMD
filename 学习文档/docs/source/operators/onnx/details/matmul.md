# Matmul

## 介绍

Perform matrix mutiplication on two tensors.

## 输入

### 说明

- Only support two input tensors，more than 3 input tensors need to be split into multiple Matmul.

### 约束

- W0 == H1, input0[C, H0, W0], input1[C, H1, W1] .

## 输出

### 说明

Output size:[C, H0, W1]

### 约束

## 参数

### 说明

**param**

| name        | type | description                 |
| ----------- | ---- | --------------------------- |
| num_channel | int  | input/output channel number |

**data**
| name         | dim | acc  | bit-width | description                         |
| ------------ | --- | ---- | --------- | ----------------------------------- |
| input0_dtype | [1] | int  | 3         | 3:'f8', only for fp8 inferene       |
| input0_acc   | [3] | int  | 8         | [e, m, b] for float ('f16'/'f8')    |
| input1_dtype | [1] | int  | 3         | 3:'f8', only for fp8 inferene       |
| input1_acc   | [3] | int  | 8         | [e, m, b] for float ('f16'/'f8')    |

### 约束

## Device

MPU

## 量化工具支持

- [x] 支持fp16量化
- [x] 支持fp8量化

## Reference

[torch.matmul](https://pytorch.org/docs/stable/generated/torch.matmul.html)#
