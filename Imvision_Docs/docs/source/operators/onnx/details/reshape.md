# Reshape

## 介绍

Reshape用于改变输入Tensor的形状，不会改变其大小。

## 输入

### 说明

- Input：[C, H, W]

### 约束

- 无

## 输出

### 说明

- Output：[C, H, W]

### 约束

- 持三种mode, mode=0用于将数据flatten到W维度；mode=1用于将数据H和W维度融合在W维度上；  
  mode=2则为一般模式，只需保证C*H*W=C’*H’*W’即可。

## 参数

### 说明

| name        | type | description  |
| ----------- | ---- | ------------ |
| hw          | int  | 1: ‘f16’ 3:‘f8‘  |
| hw_acc      | int[3] | [e,m,b]        |
| mode        | int    | 0: flatten CHW维度到W; 1: flatten HW维度到W; 2: 一般模式（需要同时配置shape属性）|
| shape       | int[3] | 目标shape，与mode=2同时使用 |

### 约束

- 无

## Device

VPU, SPU

## 量化工具支持

- [x] 支持fp16量化
- [x] 支持fp8量化
