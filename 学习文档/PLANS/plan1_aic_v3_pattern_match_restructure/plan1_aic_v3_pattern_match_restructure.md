claude 大哥的经验  Write(.claude/projects/-home-sevengao-ai-repo-aic-v3/memory/refactoring-playbook.md)

# aic_v3 图IR 中指定顺序操作的pattern match重构

功能源码：https://gerrit.imv.local/c/aic_v2/+/73736

![alt text](企业微信截图_17816782662835.png)

## 任务列表
![alt text](企业微信截图_17816784783074.png)

## 源码走读

### graph_rewriter.h
只负责删node，别的不管

### pattern_matcher.h

#### MatchResult
NodeIndex是什么？

#### PatternGraph
一个图数据结构，内有node与edge，定义了`NodeDef`的结构，确定了查找pattern的方式。

#### PatternBuilder
- 构建pattern
- 构建PatternGraph

#### PatternMatcher