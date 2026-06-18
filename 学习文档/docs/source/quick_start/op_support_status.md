# 各模块ISA版本情况

| 模块名称    | ISA版本信息 | 备注  |
| ------- | ------- | --- |
| MPU     | R8755   |     |
| FF      | R8755   |     |
| VPU     | R9781   |     |
| VPU-nms | R9401   |     |
| MTE     | R8755   |     |
| DMA     | R8755   |     |

# 算子支持状态

**状态说明：**

- **not support**：aic/ais都暂未支持此算子；

- **aic ok**：aic已支持此算子，ais暂未支持，aic/ais暂未联调；

- **ais ok**：aic已支持此算子，ais也已支持，aic/ais已联调通过；

- **eda ok**：aic/ais都已支持此算子，aic/ais内部已联调通过，且eda验证正常；

| 算子名称                                     | FP16状态      | INT8状态      | FP8状态       | BF16状态      | 备注        |
| ---------------------------------------- | ----------- | ----------- | ----------- | ----------- | --------- |
| conv1d                                   | eda ok      | not support | not support | not support |           |
| depth conv1d                             | eda ok      | not support | not support | not support |           |
| group conv1d                             | eda ok      | not support | not support | not support |           |
| [conv2d](../operators/details/conv2d.md) | eda ok      | not support | not support | ais ok      | 算子支持范围见约束 |
| dilated conv2d                           | eda ok      | not support | not support | not support |           |
| depth conv2d(MPU)                        | eda ok      | not support | not support | not support |           |
| depth conv2d(VPU)                        | not support | not support | not support | not support |           |
| group conv2d                             | eda ok      | not support | not support | not support |           |
| conv3d                                   | not support | not support | not support | not support |           |
| deconv1d                                 | ais ok      | not support | not support | not support |           |
| group deconv1d                           | ais ok      | not support | not support | not support |           |
| deconv2d                                 | ais ok      | not support | not support | not support |           |
| group deconv2d                           | ais ok      | not support | not support | not support |           |
| deconv3d                                 | not support | not support | not support | not support |           |
| wino2d                                   | eda ok      | not support | not support | not support | 算子支持范围见约束 |
| matmul                                   | ais ok      | not support | not support | not support | 算子支持范围见约束 |
| FC                                       | ais ok      | not support | not support | not support | 算子支持范围见约束 |
| activation4                              | ais ok      | not support | not support | not support | 算子支持范围见约束 |
| Softmax                                  | not support | not support | not support | not support |           |
| Softmin                                  | not support | not support | not support | not support |           |
| eltwise add/sub/mul/max/min              | eda ok      | ais ok      | ais ok      | ais ok      | 算子支持范围见约束 |
| maxpool2d/avgpool2d(stride=2)            | eda ok      | ais ok      | ais ok      | ais ok      |           |
| maxpool2d/avgpool2d                      | eda ok      | ais ok      | not support | not support | 算子支持范围见约束 |
| global max/avg pool2d                    | eda ok      | ais ok      | not support | not support | 算子支持范围见约束 |
| concat                                   | eda ok      | ais ok      | not support | not support | 算子支持范围见约束 |
| slice                                    | eda ok      | ais ok      | not support | not support | 算子支持范围见约束 |
| permute                                  | eda ok      | ais ok      | not support | not support |           |
| pixelshuffle                             | eda ok      | ais ok      | not support | not support |           |
| pixelunshuffle                           | eda ok      | ais ok      | not support | not support |           |
| batchnorm                                | ais ok      | ais ok      | not support | not support | 算子支持范围见约束 |
| LayerNorm                                | not support | not support | not support | not support |           |
| interp                                   | aic ok      | ais ok      | not support | not support | 算子支持范围见约束 |
| warpaffine                               | aic ok      | not support | not support | not support |           |
| constant pad 2d                          | eda ok      | not support | not support | not support | 算子支持范围见约束 |
| reflection pad 2d                        | eda ok      | not support | not support | not support | 算子支持范围见约束 |
| replication pad 2d                       | eda ok      | not support | not support | not support | 算子支持范围见约束 |
| reduce max/min/sum                       | ais ok      | ais ok      | not support | not support | 算子支持范围见约束 |
| localconv                                | not support | not support | not support | not support |           |
| broadcast                                | aic ok      | aic ok      | not support | not support |           |
| 1/x (activation4)                        | not support | not support | not support | not support |           |
| RMSNorm                                  | not support | not support | not support | not support |           |
| topk                                     | aic ok      | not support | not support | not support | 算子支持范围见约束 |
| nms                                      | aic ok      | not support | not support | not support | 算子支持范围见约束 |
| Getmaxidx                                | ais ok      | not support | not support | not support | 算子支持范围见约束 |
| lstm                                     | not support | not support | not support | not support |           |
| yuv_to_rgb                               | not support | not support | not support | not support |           |
