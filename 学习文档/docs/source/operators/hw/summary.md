# 算子概览

| Operator name                                   | Description                       | Input shape                                 | Output shape               |
|:-----------------------------------------------:|:---------------------------------:|:-------------------------------------------:|:--------------------------:|
| [Activation](./details/activation.md)           | Activation                        | [C,H,W]                                     | [C,H,W]                    |
| [Astype](./details/astype.md)                   | astype                            | [C,H,W]                                     | [C,H,W]                    |
| [Bn](./details/batchnorm.md)                    | Batch Norm                        | [C,H,W]                                     | [C,H,W]                    |
| [Broadcast](./details/broadcast.md)             | broadcast                         | [C,H,W],[C1,H1,W1]                          | [C,H,W]                    |
| [Compare](./details/compare.md)                 | compare                           | [C,H,W]                                     | [C,H,W]                    |
| [Conv1d](./details/conv1d.md)                   | Convolution 1d                    | [C,1,W]                                     | [C',1,W']                  |
| [Conv2d](./details/conv2d.md)                   | Convolution 2d                    | [C,H,W]                                     | [C',H',W']                 |
| [ConvTranspose1d](./details/deconv1d.md)        | Transposed Conv 1d                | [C,1,W]                                     | [C',1,W']                  |
| [ConvTranspose2d](./details/deconv2d.md)        | Transposed Conv 2d                | [C,H,W]                                     | [C',H',W']                 |
| [ConstantPad2d](./details/constantpad.md)       | Constant pad 2d                   | [C,H,W]                                     | [C,H',W']                  |
| [Concat](./details/concat.md)                   | concat                            | [C0,H0,W0]*[C1,H1,W1]                       | [C',H,'W']                 |
| [Eltwise](./details/eltwise.md)                 | Eltwise                           | 2*[C,H,W]                                   | [C,H,W]                    |
| [Fc](./details/fc.md)                           | Fully-Connected                   | [1,1,W]                                     | [1,1,W']                   |
| [Getmaxidx](./details/getmaxidx.md)             | get max index                     | [1,1,W]                                     | [1,1,1]                    |
| [GlobalPool2d](./details/global_pool2d.md)      | Global Pool2d VPU                 | [C,H,W]                                     | [C,1,1]                    |
| [Interp](./details/interp.md)                   | 2x2 interpolation                 | [C,H,W]                                     | [C,2H,2W]                  |
| [Invsqrt](./details/invsqrt.md)                 | 1/x,1/sqrt(x)                     | [C,H,W]                                     | [C,H,W]                    |
| [Ln](./details/ln.md)                           | Layer Norm                        | [C,H,W]                                     | [C,H,W]                    |
| [Localconv](./details/local_conv.md)            | Local Convolution                 | [1,H,W]                                     | [1,H,W]                    |
| [LSTM](./details/lstm.md)                       | LSTM                              | [1,1,input_size],[num_layers,2,hidden_size] | [num_layers,2,hidden_size] |
| [Matmul](./details/matmul.md)                   | Matrix-Multiplication             | [C,H0,W0]*[C,H1,W1]                         | [C,H0,W1]                  |
| [MultAcc](./details/multacc.md)                 | Mult-Acc                          | 2*[C,H,W]                                   | [C,1,1]/[1,1,1]            |
| [MultAdd](./details/multadd.md)                 | Mult-Add                          | 3*[C,H,W]                                   | [C,H,W]                    |
| [NMS](./details/nms.md)                         | non-maximum suppression           | [1,1,W],[4,1,W]                             | [1,1,W']                   |
| [Permute](./details/permute.md)                 | permute                           | [C,H,W]                                     | [C',H,'W']                 |
| [PixelShuffle](./details/pixelshuffle.md)       | pixel shuffle                     | [C*r*r,H,W]                                 | [C,rH,rW]                  |
| [PixelUnshuffle](./details/pixelunshuffle.md)   | pixel unshuffle                   | [C,rH,rW]                                   | [C*r*r,H,W]                |
| [Pool2d](./details/pool2d.md)                   | Pool2d VPU                        | [C,H,W]                                     | [C,H',W']                  |
| [Pool2d2](./details/pool2d2.md)                 | Pool2d MPU                        | [C,H,W]                                     | [C,H',W']                  |
| [ReflectionPad2d](./details/reflectionpad.md)   | Reflection pad 2d                 | [C,H,W]                                     | [C,H',W']                  |
| [ReplicationPad2d](./details/replicationpad.md) | Replication pad 2d                | [C,H,W]                                     | [C,H',W']                  |
| [Reduce](./details/reduce.md)                   | Reduce                            | [C,H,W]                                     | [C,1,1]/[1,1,1]            |
| [ReduceExt](./details/reduceext.md)             | ReduceExt                         | [C,H,W]                                     | [1,H,W]                    |
| [Reshape3](./details/reshape.md)                | Flatten -> W dim                  | [C,H,W]                                     | [1,1,W']/[C,1,W'']         |
| [Slice](./details/slice.md)                     | slice                             | [C0,H0,W0]*[C1,H1,W1]                       | [C',H,'W']                 |
| [Softmax](./details/softmax.md)                 | Softmax                           | [C,H,W]                                     | [C,H,W]                    |
| [TopK](./details/topk.md)                       | top-k                             | [1,1,W]                                     | [1,1,W']                   |
| [ver_mix_op](./details/ver_mix_op.md)           | for verification of common mix_op | [C,H,W]                                     | [C,H,W]/[1,1,1]            |
| [Warpaffine](./details/warpaffine.md)           | warp & affine                     | [C,H,W], [2,H,W]                            | [C,H,W]                    |
| [Wino2d](./details/wino2d.md)                   | Winograd conv 3x3                 | [C,H,W]                                     | [C',H',W']                 |
| [yuv2rgb](./details/yuv2rgb.md)                 | yuv420 -> rgb                     | [1,H,W]*[2,H/2,W/2]                         | [3,H,W]                    |
