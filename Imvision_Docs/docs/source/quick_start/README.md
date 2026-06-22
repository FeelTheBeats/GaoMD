# 快速开始

请使用以下指令来编译模型，其中`input file`是需要编译的模型文件路径。

```
ts_aic <input file>
```

`input file`是需要编译的模型文件路径，也是唯一必须输入的参数。模型文件格式请参考cmodel的SV接口文档。
在没有指定输出路径的情况下，输出文件将默认放在输入文件相同的目录下。

ts_aic的通用指令格式如下所示。[options]支持一些可选输入的参数。

```
ts_aic <input file> [options]
```

显示详细使用说明：

```
ts_aic --help
```

# 可选指令参数

下面所罗列的指令是编译选项中的可选参数，非强制项。

| 选项             | 描述                                                               | 默认值               |
| -------------- | ---------------------------------------------------------------- | ----------------- |
| --io-pathway=  | 设置 I/O 通路:<br> **vbus**: 使用 Vbus 通路 (未支持)<br> **dma**: 使用 DMA 通路 | dma               |
| -o             | 指定输出文件路径                                                         | 在输入文件同路径下生成out/目录 |
| --soc-version= | 指定 soc 版本                                                        | aiisp_v3          |
| --in-pattern=  | 指定 input pattern, 可选项 stream bayer nchw nhwc npu_fmt             | bayer             |
| --out-pattern= | 指定 output pattern, 可选项 stream bayer nchw nhwc npu_fmt            | bayer             |

# 输出文件

1. xxx_ins.bin: 指令流二进制文件;
2. xxx_wgt.bin: 参数二进制文件;
3. xxx_data.json: 供EDA平台使用的配置文件;
4. xxx_model.tlf: 可由RTOS执行的编译结果。

# 开启debug开关

终端输入以下命令可以修改debug log等级，默认log等级为：2-info

```shell
export AIC_TLOG_LEVEL=4
```

其他log等级：0-Error; 1-warning; 2-info; 3-debug; 4-trace
