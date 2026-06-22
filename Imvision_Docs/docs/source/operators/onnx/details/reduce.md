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

- [x] 支持fp16量化
- [x] 支持fp8量化
