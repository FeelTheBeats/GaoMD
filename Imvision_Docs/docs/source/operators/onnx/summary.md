# 算子概览

整体约束：

1. C > 1 and C < 4096
2. H > 1 and H < 16384
3. H > 1 and H < 16384

| Operator name                                   | Description             | Input shape                                 | Output shape               | comment |
|:-----------------------------------------------:|:-----------------------:|:-------------------------------------------:|:--------------------------:| ------- |
| [Add](./details/eltwise.md)                     | Eltwise                 | [C,H,W], [C,H,W]                            | [C,H,W]                    |         |
| [And](./details/compare.md)                     | compare                 | [C,H,W]                                     | [C,H,W]                    |         |
| [ArgMax](./details/getmaxidx.md)                | get max index           | [1,1,W]                                     | [1,1,1]                    |         |
| [ArgMin](./details/getmaxidx.md)                | get max index           | [1,1,W]                                     | [1,1,1]                    |         |
| [AveragePool](./details/pool2d.md)              | Pool2d                  | [C,H,W]                                     | [C,H',W']                  |         |
| [BatchNormalization](./details/batchnorm.md)    |                         | [C,H,W]                                     | [C,H,W]                    |         |
| [Celu](./details/activation.md)                 | Activation              | [C,H,W]                                     | [C,H,W]                    |         |
| [Concat](./details/concat.md)                   | concat                  | [C0,H0,W0]*[C1,H1,W1]                       | [C',H,'W']                 |         |
| [Conv1d](./details/conv1d.md)                   | Convolution 1d          | [C,1,W]                                     | [C',1,W']                  |         |
| [Conv2d](./details/conv2d.md)                   | Convolution 2d          | [C,H,W]                                     | [C',H',W']                 |         |
| [ConvTranspose1d](./details/deconv1d.md)        | Transposed Conv 1d      | [C,1,W]                                     | [C',1,W']                  |         |
| [ConvTranspose2d](./details/deconv2d.md)        | Transposed Conv 2d      | [C,H,W]                                     | [C',H',W']                 |         |
| [Eelu](./details/activation.md)                 | Activation              | [C,H,W]                                     | [C,H,W]                    |         |
| [Gemm_Fc](./details/fc.md)                      | Fully-Connected         | [1,1,W]                                     | [1,1,W']                   |         |
| [GlobalAveragePool](./details/global_pool2d.md) | Global Pool2d           | [C,H,W]                                     | [C,1,1]                    |         |
| [GlobalMaxPool](./details/global_pool2d.md)     | Global Pool2d           | [C,H,W]                                     | [C,1,1]                    |         |
| [HardSigmoid](./details/activation.md)          | Activation              | [C,H,W]                                     | [C,H,W]                    |         |
| [HardSwish](./details/activation.md)            | Activation              | [C,H,W]                                     | [C,H,W]                    |         |
| [LayerNormalization](./details/ln.md)           | Layer Norm              | [C,H,W]                                     | [C,H,W]                    |         |
| [LSTM](./details/lstm.md)                       | LSTM                    | [1,1,input_size],[num_layers,2,hidden_size] | [num_layers,2,hidden_size] | TBD     |
| [LeakyRelu](./details/activation.md)            | Activation              | [C,H,W]                                     | [C,H,W]                    |         |
| [Matmul](./details/matmul.md)                   | Matrix-Multiplication   | [C,H0,W0]*[C,H1,W1]                         | [C,H0,W1]                  |         |
| [Max](./details/eltwise.md)                     | Eltwise                 | 2*[C,H,W]                                   | [C,H,W]                    |         |
| [MaxPool](./details/pool2d.md)                  | Pool2d VPU              | [C,H,W]                                     | [C,H',W']                  |         |
| [Min](./details/eltwise.md)                     | Eltwise                 | 2*[C,H,W]                                   | [C,H,W]                    |         |
| [Mish](./details/activation.md)                 | Activation              | [C,H,W]                                     | [C,H,W]                    |         |
| [Mul](./details/eltwise.md)                     | Eltwise                 | 2*[C,H,W]                                   | [C,H,W]                    |         |
| [NonMaxSuppression](./details/nms.md)           | non-maximum suppression | [1,1,W],[4,1,W]                             | [1,1,W']                   |         |
| [Prelu](./details/activation.md)                | Activation              | [C,H,W]                                     | [C,H,W]                    |         |
| [ConstantPad2d](./details/constantpad.md)       | Constant pad 2d         | [C,H,W]                                     | [C,H',W']                  |         |
| [ReflectionPad2d](./details/reflectionpad.md)   | Reflection pad 2d       | [C,H,W]                                     | [C,H',W']                  |         |
| [ReplicationPad2d](./details/replicationpad.md) | Replication pad 2d      | [C,H,W]                                     | [C,H',W']                  |         |
| [ReduceMax](./details/reduce.md)                | Reduce                  | [C,H,W]                                     | [C,1,1]/[1,1,1]            |         |
| [ReduceMean](./details/reduce.md)               | Reduce                  | [C,H,W]                                     | [C,1,1]/[1,1,1]            |         |
| [ReduceMin](./details/reduce.md)                | Reduce                  | [C,H,W]                                     | [C,1,1]/[1,1,1]            |         |
| [ReduceSum](./details/reduce.md)                | Reduce                  | [C,H,W]                                     | [C,1,1]/[1,1,1]            |         |
| [Relu](./details/activation.md)                 | Activation              | [C,H,W]                                     | [C,H,W]                    |         |
| [Reshape](./details/reshape.md)                 | Flatten -> W dim        | [C,H,W]                                     | [1,1,W']/[C,1,W'']         |         |
| [Selu](./details/activation.md)                 | Activation              | [C,H,W]                                     | [C,H,W]                    |         |
| [Sigmoid](./details/activation.md)              | Activation              | [C,H,W]                                     | [C,H,W]                    |         |
| [Slice](./details/slice.md)                     | slice                   | [C0,H0,W0]*[C1,H1,W1]                       | [C',H,'W']                 |         |
| [Softmax](./details/softmax.md)                 | Softmax                 | [C,H,W]                                     | [C,H,W]                    |         |
| [Sqrt](./details/activation.md)                 | Activation              | [C,H,W]                                     | [C,H,W]                    |         |
| [Sub](./details/eltwise.md)                     | Eltwise                 | 2*[C,H,W]                                   | [C,H,W]                    |         |
| [Tanh](./details/activation.md)                 | Activation              | [C,H,W]                                     | [C,H,W]                    |         |
| [TopK](./details/topk.md)                       | top-k                   | [1,1,W]                                     | [1,1,W']                   |         |
| [Transpose](./details/permute.md)               | permute                 | [C,H,W]                                     | [C',H,'W']                 |         |
| [Upsample](./details/interp.md)                 | 2x2 interpolation       | [C,H,W]                                     | [C,2H,2W]                  |         |
| [Broadcast](./details/broadcast.md)             | broadcast               | [C,H,W],[C1,H1,W1]                          | [C,H,W]                    |         |
| [Localconv](./details/local_conv.md)            | Local Convolution       | [1,H,W]                                     | [1,H,W]                    |         |
| [PixelShuffle](./details/pixelshuffle.md)       | pixel shuffle           | [C*r*r,H,W]                                 | [C,rH,rW]                  |         |
| [PixelUnshuffle](./details/pixelunshuffle.md)   | pixel unshuffle         | [C,rH,rW]                                   | [C*r*r,H,W]                |         |
