# Release Note

## 2024.09.06

### **New Feature**

1. 支持中间层内存管理；
2. 支持中间层结果搬入搬出功能；
3. 支持混合精度下conv co拆分多个hardlayer（coef/bias拆分）；
4. 支持1对2级联MPU->WDMA/MPU->VPU，并输出对应eda it case；
5. 支持1对2级联MTE->WDMA/MTE->VPU，并输出对应eda it case；
6. 输出1对2级联rdma->vpu/mte->vpu、rdma->vpu/mpu->vpu、 mpu->vpu/mte->vpu对应eda it case；
7. 根据最新isa适配ff fp8，lutx、lutyk不同dtype配置；
8. 混合精度下算子json parse中无output_type时，使用hw及hw_acc作为output_type及output_acc；
9. 支持npu dma模块NHWC非密排，并输出对应20个eda it case；
10. 支持RDMA交织场景1对2级联RDMA->MTE/RDMA->MPU、RDMA->MTE/RDMA->VPU、RDMA->MPU/RDMA->VPU，输出对应eda it case；
11. 支持RDMA一对二级联RDMA->MTE/RDMA->MPU、RDMA->MTE/RDMA->VPU，输出对应eda it case；
12. 支持fp8 conv/FF融合功能；
13. 更新mpu模块最新isa配置(包含mac_out_dtype/bias_dtype)；
14. 更新pool2d 和 global pool2d cmodel 定义和对应ISA 配置；
15. 更新vpu ISA 9781版本，增加chx_stride, h拆分等ISA 配置，AIS增加相关解析；
16. 更新npu dma模块i8 case转为fp8；

## 2024.08.16

### **New Feature**

1. MTE concat的优化提高了对c1/c2/c4做concat的并行度；
2. Local Conv算子支持，并输出对应eda it case；
3. 复合算子1/x的支持，并输出对应eda it case；
4. 复合算子1/sqrt_x的支持，并输出对应case；
5. 混合精度conv/wino中bias数据类型随ifm配置；

## 2024.08.09

### **New Feature**

1. TLE和data.json中按照Load顺序摆放input_tensor的信息，按照store顺序摆放 output_tensor信息；
2. MPU模块padding case_id MPU_54~56测例输出；
3. MPU interp bilinear输出拆分C8余数hardlayer，并输出相关case（20i20o）；
4. v3二合一mfnr_5i3o、v3mfnr_5i3o_big网络加入models仓库；
5. 参数替换按照eda反馈的问题进行data.json配置更新；

## 2024.08.02

### **New Feature**

1. concat 优化新方案功能支持以及对应case输出；
2. pool2d fp8支持；
3. activation fp8 wgt打包支持；
4. NPU_SCH模块8个eda it case支持；
5. conv算子fp8数据格式支持，并输出case；
6. 实现通过命令行参数传入模型参数数据在TLF中的起始地址的对齐因子的功能；
7. mpu interp blk_ch字段配置更新；

## 2024.07.26

### **New Feature**

1. EDA IT mte模块算子fp8/fp16 case支持；
2. conv+pool+relu融合，aic /ais联调通过；
3. batch_norm 混合精度支持，对应bf16->fp16/fp16->fp8/fp8->bf16/fp8->fp16 eda it测例输出；
4. mpu h拆分新方案支持，aic/ais联调通过，三个单算子case eda通过；
5. MPU interp bilinear支持；
6. mpu interp算子block划分更新；
7. DMA模块 IT case的输出（目前剩NHWC非密排的case）；
8. NPU_SCH模块DMA地址替换相关case设计与输出；
9. 修复mte->wdma/mte->rdma级联ais 模拟的精度问题；
10. 解决mfnr_v3 编译内存释放错误问题；

## 2024.07.12

### **New Feature**

1. conv h方向的拆分支持（根据硬件新方案拆分不产生concat），ais已支持以及aic/ais功能联调通过；
2. MPU/FF融合后的H拆分支持，aic/ais功能联调通过；
3. DMA模块EDA五个IT case的输出；（case_id DMA_6/DMA_14/DMA_16/DMA_61/DMA_63）
4. 六个（rdma->vpu、mpu->vpu、rmda->mte、mte->wdma、mte->vpu、mpu->wdma）级联case功能支持以及case输出；
5. MTE concat优化支持（方案更新，concat不能完全融掉，concat c4+c1+c1中最后的c1需加dma），aic已完成功能支持，已输出单算子测例同步给eda测试；

## 2024.07.05

### **New Feature**

1. MTE concat优化，消除concat，aic功能已支持，已输出单算子测例给eda同步测试；
2. conv h方向的拆分支持（根据硬件新方案），aic功能已支持，已输出单算子测例给eda同步测试；
3. aic/ais debug方案实施；
4. vpu-dmaout级联case输出；
5. batch_norm 支持权值是标量，通过配置在ISA减少DMA搬运及内存开销；
6. DMA In和Out Channel拆分功能支持；
7. 修复dummy_concat 地址从node传递到hwlayer问题；
8. 修复nchw转内部格式时的内存溢出问题；

## 2024.06.28

### **New Feature**

1. MPU/FF融合后的CO拆分支持；
2. conv co方向拆分支持；
3. MPU与FF融合支持，aic/ais联调通过；
4. 复合算子NMS ISA更新，AIC load store配置修改；
5. 复合算子NMS offset地址偏移ISA修改；
6. Reduce Ext C维度规约，WDMA 大于8且不是8的整数倍拆分成了2个Hwlayer的更新；
7. Hwlayer 输入输出内存地址检查；
8. Broadcast 算子eda IT case支持，新增i8/f8/bf16 case，同时修复数据类型检查问题；（case_id vpu_broadcast_1/2/3/4/5/6/7）
9. DMA模块eda IT case2和case49输出；（case_id DMA_2/DMA_49）
10. FF模块activation 22个IT case输出；（MPU_64~MPU_85）

## 2024.06.21

### **New Feature**

1. wino3x3 h方向的拆分支持；
2. MPU与FF融合支持；
3. 去除conv h拆分中的前级slice；
4. 内存管理代码结构调整，单独实现为类和注册机制；
5. 支持内存并行时hwlayer层内存使用信息log生成；
6. NMS算子ISA更新load_len配置；
7. v2 insta mfnr网络MPU/FF融合配置以及conv_split_h配置更新；
8. EDA IT验证-DMA模块部分输出14个测例（case_id DMA_1/DMA_3/DMA_12/DMA_13/DMA_17/DMA_26/DMA_27/DMA_48/DMA_50/DMA_59/DMA_60/DMA_64/DMA_73/DMA_74）；

## 2024.06.14

### **New Feature**

1. vpu模块算子输入shape相同时，设置为no_broadcast；
2. Slice算子在C8拆分时转换为DummySlice解决mfnr_0415网络内存放不下的第一个尖峰时刻问题；
3. 根据生命周期信息调整内存策略，生命周期长的tensor优先从内存块尾巴分配，解决mfnr_0415网络第二个尖峰时刻，mfnr_0415网络在2M内存可以编译通过；
4. conv h拆分支持（stride为2不支持）；
5. insta mfnr模型编译以及联调支持；
6. MPU/FF模块算子的融合支持（ais暂未完成支持）；

## 2024.06.07

### **New Feature**

1. reduce插入dim_mode无效信息的支持；
2. lut/eltwise/bn原地操作的支持；
3. asm中hardlayer name的统一；
4. 奇数分辨率的wino添加crop算子；
5. Reduce Sum Ext 修改W 拆分为H * W；
6. pad+conv融合pattern支持；

## 2024.05.31

### **New Feature**

1. 多输入输出支持不同的pattern；
2. 2个mpu并行支持；
3. 支持相同队列插入sync；
4. 算子并行内存问题处理;
5. 超夜网络(2dnr/v2 mfnr)更新：
   1）开启wino和ff pool2d2开关的支持；
   2）相同队列插入sync；
   3）2个mpu并行支持；
6. AIS更新MPU/VPU性能计算公式；
7. 已解决bn算子输入为111时ISA load2配置问题，scalar_from 来源于L1；

## 2024.05.24

### **New Feature**

1. vpu fc修改weght param打包按行32B对齐;
2. vpu fc修改store_type为11c;
3. 开启MPU wino3*3优化；
4. pool2*2根据性能最优情况选择VPU或FF;
5. 修正nms算子loop_op为2，ISA配置错误；

## 2024.05.17

### **New Feature**

1. 支持deconv1d；
2. 支持conv1d；
3. 支持group deconv1d；
4. 支持reduce mean算子C维度规约；
5. 输出部分MPU case；
6. 输出eda it rdma nhwc测试case；
7. warp算子支持；
8. vpu line_stride计算公式更新；
9. MTE模块ISA更新至版本R8755；

## 2024.05.10

### **New Feature**

1. 支持mem sync级联，以及输出VPU+WDMA的级联case；
2. 更新pool2d2 block计算公式；
3. 支持group deconv2d算子；
4. 已修复group conv通道配置问题；
5. 增加特殊group conv（ci/co除以group id是8的倍数）的支持；
6. 已完成flownet网络支持-warp算子支持，待ais支持后联调；
7. 已完成FlowNet网络-reduce sum算子支持，aic_v2与ais 联调通过；
8. 修改depth conv的line_stride计算
9. v2 mfnr网络aic与ais联调通过；

## 2024.04.26

### **New Feature**

1. reduceSum C维度规约支持，ais联调通过（case_id comp_reduce_1）；
2. warpaffine算子支持，ais暂未联调；
3. 修复nhwc紧密排列输出时patch_stride配置问题；
4. 修复支持网络多输出时发现的aic_v2 tlf中tensor_num/tensor_info配置问题；
5. 支持网络多输出功能；
6. concat/slice 增加res_ch_linestride配置;
7. 增加cmd id ISA字段支持;

## 2024.04.19

### **New Feature**

1. MPU/VPU/FF/DMA模块ISA更新至版本R8755;
2. MPU模块更新input block新增约束;
3. VPU模块修正line_stride；
4. MPU/MTE/FF/DMA/VPU eda_case_list已有用例更新case_id;

## 2024.04.12

### **New Feature**

1. group conv2d算子(group id/ci/co不大于8)功能支持以及联调；
2. aic readme增加各个算子的精度支持情况；

## 2024.04.07

### **New Feature**

1. depth conv2d算子功能支持以及联调；
2. 复合算子NMS功能支持；
3. SCH hardlayer2/4/8/16测例支持；

## 2024.03.26

### **New Feature**

1. MPU/VPU/FF/MTE/DMA模块ISA更新到R8395版本；

## 2023.11.24

### **New Feature**

1. Conv2d支持Stream格式；

## 2023.11.15

### **New Feature**

1. 支持 Eltwise 层.

### **Bug Fixed**

1. 根据硬件计算方式重排 Conv2d (4I4O, 8I8O)的权重；

## 2023.11.2

### **New Feature**

1. 支持 Conv2d 层.

## 2023.12.8

### **New Feature**

1. 支持 Matmul 层.

## 2024.1.17

### **New Feature**

1. 支持 wino2d 层.
