# Topk

## 介绍

Topk算子可以返回输入向量中k个最大或最小值

## 输入

### 说明

Input size:[C, H, W]

### 约束

* 只支持1x1xn的输入size,n<=65535

## 输出

### 说明

Output size:[C, H, W]

### 约束

* 输出的size为1x1xk，k与配置参数相同

## 参数

### 说明

**param**

| name    | type | description                      |
| ------- | ---- | -------------------------------- |
| k       | int  | topk中的k                          |
| Largest | int  | 0: 取k个最小数的index; 1: 取k个最大数的index |

### 约束

| name      | acc | constrain |
| Largest   | int | 0: 取k个最小数的index; 1: 取k个最大数的index |
| k         | int | 0 < K <= N |

* 可以配置Largest 为0或1选择最小的k个数或最大的k个数输出
* sv只支持f16精度
* output dtype只支持为u16

## Device

VPU

## 量化工具支持

支持fp16量化

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
  "inst_name": "test_topk",
  "type_name": "Topk",
  "bottom": ["data"],
  "top": ["816"],
  "hw":"f16",
  "hw_acc": [5,10,15],
  "param": {
    "k": 10,
    "largest":1
  },
  "data":{
    "output_dtype":"u16",
    "output_acc":[16,0,0]
  }
}
```
