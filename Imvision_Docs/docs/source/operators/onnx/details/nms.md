# NMS

## 介绍

NMS算子可以完成非极大值抑制算法，以目标检测为例，可以消除冗余的检测框
input0表示输入N个检测框置信度，input1表示输入N个检测框的坐标值，output表示经过NMS处理后保留检测框idx（input0，input1必须按照置信度降序排序）

## 输入

### 说明

input0 size: [1,1,N]
input1 size:[4,1,N]

* input1存储检测框坐标以(x1,y1,x2,y2)形式存储，且0<=x1<x2,0<=y1<y2

### 约束

## 输出

### 说明

output size: [1,1,M]

### 约束

* 输出的size为1x1xk，k与配置参数相同

## 参数

### 说明

**param**

| name       | type | description |
| ---------- | ---- | ----------- |
| iou        | f16  | 置信度阈值       |
| max_output | int  | 输出最大检测框数量   |

### 约束

| name       | type | description     |
| ---------- | ---- | --------------- |
| iou        | f16  | 浮点数上: 0<=iou<=1 |
| max_output | int  | max_output = M  |

* sv只支持f16精度
* output dtype只支持为u16

## Device

VPU

## 量化工具支持

- [x] 支持fp16量化
- [] 支持fp8量化

## Reference
