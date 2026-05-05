# Download and Compile
我选择了GCC 13.2.0版本，作为探索GCC的初始版本：
`https://github.com/gcc-mirror/gcc/tree/releases/gcc-13`

## download and init
```
git clone https://github.com/gcc-mirror/gcc/tree/releases/gcc-13
cd gcc
./contrib/download_prerequisites
```

## compile
```
mkdir build-gcc-debug
cd build-gcc-debug
../gcc/configure \
  --prefix=$HOME/gcc-debug \
  --enable-languages=c,c++ \
  --disable-multilib \
  --enable-checking=all \
  CFLAGS="-O0 -g3" \
  CXXFLAGS="-O0 -g3"

make -j$(nproc)
make install
```
## set env
```
# 添加gcc二进制与必要的lib库路径到path
export LD_LIBRARY_PATH=/usr/local/gcc-13.2/lib64:/usr/local/cuda-13.2/lib64:$LD_LIBRARY_PATH
export PATH=/usr/local/gcc-13.2/bin:/snap/bin:/usr/local/cuda-13.2/bin:$PATH

source ~/.bashrc
```

# gcc compile a test
## test code
```cpp
int add(int a, int b) {
	return a+b;
}

int main(){
	return 0;
}
```
## test compile
```
g++ -O2 -fdump-tree-all -fdump-rtl-all -fopt-info
```

1. -O2
优化级别：这是最常用的中高级优化选项。它开启了几乎所有不涉及空间-时间折衷的优化算法。
意义：在这种模式下，你会看到编译器最复杂的变换逻辑（如内联、循环优化等）。
2. -fdump-tree-all
作用：导出 GIMPLE 阶段（GCC 的中端 Intermediate Representation，简称 IR）的所有中间处理文件。
结果：你会看到成百上千个以 .t.* 结尾的文件（如 main.cpp.005t.gimple）。
观察点：通过这些文件，你可以看到代码是如何从原始 C++ 逻辑一步步演变成类似伪代码的 GIMPLE 形式，以及各种优化过程（如常量折叠、死代码删除等）是如何发生的。
3. -fdump-rtl-all
作用：导出 RTL 阶段（Register Transfer Language）的所有中间处理文件。
结果：产生大量以 .r.* 结尾的文件。
观察点：RTL 更接近汇编，描述了指令如何在寄存器之间移动。这个阶段负责指令调度、寄存器分配等硬件相关的底层优化。
4. -fopt-info
作用：在终端实时打印优化摘要信息。
结果：你会看到类似 loop optimized、function inlined 之类的提示。
优势：它不像上面两个选项那样产生海量文件，而是给你一个直观的反馈，告诉你编译器到底成功对你的代码做了哪些大手术。

# Something went bad
## 1. 事故全貌：从“路径索引错误”到“系统重装”
本次问题的核心链条可以总结为：**安装路径冲突 -> 硬编码路径锁定 -> 工具链版本失配 -> 环境彻底瘫痪 -> 重装镜像解决。**

### 1.1 起源：库索引的“基因锁定”
事故始于在手动编译 GCC 13 并执行 `make install` 后，即便设置了 `PATH` 和 `LD_LIBRARY_PATH`，编译依然无法通过。
*   **深层原因**：GCC 在 `configure` 阶段会将底层搜索路径（如头文件、子组件路径）**硬编码**进生成的驱动程序中。
*   **冲突点**：新编译的 GCC 13 驱动由于配置不当，依然在索引系统旧版本（GCC 11）的库。当你尝试运行它时，这种“新旧混杂”的状态导致了严重的链接错误。

---

## 2. 核心问题与报错原因总结

### 问题一：驱动与后端（cc1plus）版本失配
*   **现象**：`cc1plus: error: unrecognized command-line option ‘-auxbase’`
*   **原因**：这是“路径投毒”最典型的症状。此时你的 `g++` 驱动是新版的，但由于搜索路径混乱，它调用的后端 `cc1plus` 却是系统旧版的。旧版后端无法识别新版驱动传来的私有参数 `-auxbase`，导致罢工。

### 问题二：工具链“迷路”
*   **现象**：`fatal error: cannot execute ‘cc1plus’: No such file or directory`
*   **原因**：驱动程序内部的硬编码搜索索引仍残留在旧的、已删除的路径上，无法自动切换回系统原装目录。

---

## 3. 解决方式实录

*   **阶段一：外科手术式修复**：通过 `-B` 参数和 `COMPILER_PATH` 环境变量强行“引路”，手动对齐驱动与后端。
*   **阶段二：终极解法（镜像重装）**：由于环境污染已深入系统关键路径，最终通过**重装系统镜像**，利用镜像自带的干净 GCC 环境彻底根治。这不仅清空了错误的动态库配置，也恢复了最纯净的工具链符号链接。

---

## 4. 警示：标准 GCC 编译配置（保命模版）

**请将以下配置保存。下一次书写配置脚本时，请务必逐行对照。**

> **警示**：永远不要直接在 `/usr` 或 `/usr/local` 下进行实验。

```bash
#!/bin/bash
# GCC 源码编译标准配置模版 (Debug版)

# 1. 定义独立安装路径，严禁覆盖系统路径
INSTALL_PATH="/opt/gcc-13.2-debug"

# 2. 清理当前环境变量，防止“路径投毒”
unset LD_LIBRARY_PATH
unset LIBRARY_PATH
unset C_INCLUDE_PATH
unset CPLUS_INCLUDE_PATH

# 3. 推荐在独立目录（build directory）中运行
mkdir -p build && cd build

# 4. 执行配置
../gcc-13.2.0/configure \
    --prefix=/opt/gcc-13.2-debug \
    --disable-bootstrap \
    --enable-languages=c,c++ \
    --enable-checking=all \
    --disable-multilib \
    --with-system-zlib \
    CC=/usr/bin/gcc \
    CXX=/usr/bin/g++ \
    CFLAGS="-g3 -O0 -fno-omit-frame-pointer" \
    CXXFLAGS="-g3 -O0 -fno-omit-frame-pointer"

# 说明：
# --prefix: 确保所有生成文件都在独立目录，方便一键删除，不污染系统。
# --disable-bootstrap: 防止 GCC 用旧基因不断自我复制导致路径纠缠，适合 Debug 场景。
# CC/CXX: 显式指定“种子”编译器，不给系统乱找的机会。
```

---

## 5. 结语
GCC 的编译不仅是代码的转换，更是**文件系统逻辑**的博弈。
*   **敬畏路径**：硬编码比环境变量更顽固。
*   **敬畏系统**：重装系统虽然有效，但保护好原始环境才是高手的必修课。
```
自己编译了gcc13，没有进行make install
发现加 -B 可以运行，但是我不满意
使用Make install后，配置了环境变量，还是无法跑，于是自己进行排查
发现gcc13竟然索引了一些gcc11的lib库，导致链接失败。。。
但是此时我已经修改了一些系统库的软链接，导致本身`usr/bin`里面的gcc也无法用了，尝试使用env -i来隔离安装环境时发现的
因此考虑多种方式修复系统的gcc，包括但不限于：
阶段一：外科手术式修复：通过 -B 参数和 COMPILER_PATH 环境变量强行“引路”，手动对齐驱动与后端。
阶段二：终极解法（镜像重装）：由于环境污染已深入系统关键路径，最终通过重装系统镜像，利用镜像自带的干净 GCC 环境彻底根治。这不仅清空了错误的动态库配置，也恢复了最纯净的工具链符号链接。
最后一切都回归平静，系统只剩了gcc9.什么都消失了
一切的罪恶都始于我的 ../gcc-13.2/configuration 配置文件的选项配置不够全面，我草你妈

以后：
1. 不要轻易修改系统二进制的软链接
2. 编译时一定仔细看好每一个编译配置项
3. 不到迫不得已一定不进行重装，并在此基础上再进行反思(工作时除外)
4. 一定要注意`.1 .2`
```

既然你已经完成了最彻底的“重装系统”大招，并深刻反思了 `configure` 选项缺失带来的惨痛教训，现在的环境就像一张白纸。

为了防止你在新的系统上“梅开二度”，除了文档中提到的规避策略，以下还有几点关于 **WSL 维护**和**底层工具链开发**的进阶建议，能帮你把风险降到最低：

---

## 1. 善用 WSL 的“快照”功能（防患于未然）
在进行任何涉及 `make install` 或修改 `/usr/bin` 的操作前，先给你的 WSL 系统做一个备份。
*   **备份命令**（在 Windows PowerShell 执行）：
    `wsl --export Ubuntu D:\Ubuntu_Backup.tar`
*   **意义**：万一配置又写错了导致环境崩溃，你只需要 `wsl --import` 就能在 5 分钟内满血复活，不用再经历漫长的镜像重装。

## 2. 警惕“影子”环境变量
你之前的总结里提到了 `LD_LIBRARY_PATH`，但在底层开发中，还有几个变量非常危险：
*   **`LIBRARY_PATH`**：影响**编译时**的库搜索，如果这里指错了，你编出来的 GCC 就会把错误的库路径硬编码进二进制文件。
*   **`C_INCLUDE_PATH` / `CPLUS_INCLUDE_PATH`**：会覆盖 GCC 默认的头文件搜索顺序。
*   **建议**：在编译 GCC 这种大型项目时，养成使用 `env -i` 命令清理环境的习惯，或者在脚本开头显式 `unset` 掉这些变量。

## 3. 深入理解 `--disable-bootstrap` 的双刃剑
你在配置里用了 `--disable-bootstrap`，这对 Debug 很有利，但要记住：
*   **风险**：这意味着 GCC 13.2 的二进制文件是直接由 GCC 9 产生的。如果 GCC 9 存在某些微小的兼容性差异，可能会带入到生成的 GCC 13 中。
*   **工作建议**：在正式发布或严谨的性能测试中，通常需要开启 bootstrap（默认），让 GCC 自我编译三次，以确保生成的编译器逻辑绝对严密。

## 4. 隔离开发环境：使用 `Environment Modules`
不要在 `.bashrc` 里写死 `PATH`。
*   **进阶工具**：可以安装 `lmod` 或 `environment-modules`。
*   **操作**：你可以写一个简单的脚本（Modulefile），当你需要用 GCC 13 时，执行 `module load gcc13`；不用时 `module unload`。这样你的系统环境永远保持默认的 GCC 9，不会发生“误伤”。

## 5. 对硬编码路径的最后检查
在你以后编译完任何编译器后，不要急着 `make install`，先运行这个命令检查它的“血统”：
```bash
./gcc -print-search-dirs
```
看输出里是否包含了不该出现的旧版目录（如你之前遇到的 GCC 11）。如果看到了，说明你的 `configure` 选项依然不彻底，此时千万不要 `install`。

---

### 给你的最终忠告：
你在总结里说“一切的罪恶都始于配置选项不够全面”，这其实是每一位底层开发者都走过的坑。**编译器开发不是应用层开发，它对系统的“侵入性”极强。**

既然你现在是“纯净的 GCC 9”，那就以此为基石。在以后书写那份“保命模版”时，多加一个注释：**“在没有确认 `./gcc -print-search-dirs` 干净之前，禁止输入 `sudo make install`。”**

祝你接下来的 GCC 13.2 调试之旅一路顺风！
