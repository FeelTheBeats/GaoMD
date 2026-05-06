# 观测一个简单的优化例子
## a small testcase
```cpp
int foo() {
    int a = 3 * 4;
    int b = a + 0;
    if (0) {
        return b;
    }
    return a;
}

int main() {
    int a = foo();
    return 0;
}
```

## compile and see opt info
```
g++ -O2 -fdump-tree-all -fdump-rtl-all -fopt-info
```

## focus on opt
GIMPLE（tree 层优化）

优先关注：
*.gimple（初始 IR）
*.optimized
*.ccp（常量传播）
*.dce（死代码消除）

👉 看这些问题：
3 * 4 是在哪一步变成 12 的？
if (0) 是在哪一步被删掉的？
b = a + 0 是在哪一步被优化掉的？

最后：
再看：
*.expand
*.combine
*.cse

👉 看：
指令是怎么被简化的
是否生成冗余 mov

## useful info
gcc/tree-ssa-ccp.cc
gcc/tree-ssa-dce.cc
gcc/passes.cc

简历mapping
```
代码变化（dump）
    ↓
某个 pass 名字
    ↓
源码文件
    ↓
核心函数
```