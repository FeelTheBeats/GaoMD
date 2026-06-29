# Visitor 重构：类体系改动树

> 标注说明：`[新增]` = 本次重构添加，`[不变]` = 未改动，`★` = 新建文件

---

```
Node  (include/aic/graph/node.h)
├── Accept(NodeVisitor& v) { v.Visit(*this); }  [新增] 默认实现
│
├── NodeVisitor  (include/aic/transforms/node_visitor.h)  ★ 新建
│   ├── Visit(Node&)          = 0  默认 fallback
│   ├── Visit(Exp&)           = 0  } 
│   ├── Visit(Softmax&)       = 0  }
│   ├── Visit(Conv2d&)        = 0  }
│   └── ... (16 个 Visit 方法)      } L1 Operator + L2 Kernel 分发入口
│
├── HwVisitor  (include/aic/transforms/hw_visitor.h)  ★ 新建
│   ├── Visit(HwLayer&)       = 0  默认 fallback
│   ├── Visit(Conv2dLayer&)   = 0  }
│   ├── Visit(EltwiseLayer&)  = 0  }
│   ├── Visit(Mpu&)           = 0  }
│   └── ... (11 个 Visit 方法)      } L3 HwLayer 分发入口
│
├── Operator ─────────────────────────────── L1 Operator Graph
│   │  Operator 基类：不加 Accept（中间层，分发在叶子）
│   │
│   ├── Exp               Accept(NodeVisitor&) override  [新增]
│   ├── Inv               Accept(NodeVisitor&) override  [新增]
│   ├── Sin               Accept(NodeVisitor&) override  [新增]
│   ├── Cos               Accept(NodeVisitor&) override  [新增]
│   ├── Softmax           Accept(NodeVisitor&) override  [新增]
│   ├── LogSoftmax        Accept(NodeVisitor&) override  [新增]
│   ├── BaseNorm          Accept(NodeVisitor&) override  [新增]
│   │   ├── LayerNorm     Accept(NodeVisitor&) override  [新增]
│   │   ├── InstanceNorm  Accept(NodeVisitor&) override  [新增]（文件：instance_norm.h）
│   │   └── RMSNorm       Accept(NodeVisitor&) override  [新增]（文件：rms_norm.h）
│   ├── ConvTranspose2d   Accept(NodeVisitor&) override  [新增]
│   ├── ConvTranspose2d2  Accept(NodeVisitor&) override  [新增]
│   ├── Matmul            Accept(NodeVisitor&) override  [新增]
│   ├── Permute           Accept(NodeVisitor&) override  [新增]
│   ├── Reshape           Accept(NodeVisitor&) override  [新增]
│   ├── BatchNorm         Accept(NodeVisitor&) override  [新增]
│   ├── Activation        Accept(NodeVisitor&) override  [新增]
│   ├── Eltwise           Accept(NodeVisitor&) override  [新增]
│   ├── Reduce            Accept(NodeVisitor&) override  [新增]
│   ├── Slice             Accept(NodeVisitor&) override  [新增]
│   ├── Concat            Accept(NodeVisitor&) override  [新增]
│   └── ... (全部 45 个)  Accept(NodeVisitor&) override  [新增]
│
├── Kernel ────────────────────────────────── L2 Kernel Graph
│   │  Kernel 基类：不加 Accept
│   │
│   ├── Conv2dKernel         Accept(NodeVisitor&) override  [新增]
│   ├── EltwiseKernel        Accept(NodeVisitor&) override  [新增]
│   ├── Pool2dKernel         Accept(NodeVisitor&) override  [新增]
│   ├── Pool2d2Kernel        Accept(NodeVisitor&) override  [新增]
│   ├── DmaKernel            [不变] 基类，不加
│   │   ├── DmaInKernel      Accept(NodeVisitor&) override  [新增]
│   │   └── DmaOutKernel     Accept(NodeVisitor&) override  [新增]
│   ├── ActivationKernel     Accept(NodeVisitor&) override  [新增]
│   ├── BatchNormKernel      Accept(NodeVisitor&) override  [新增]
│   ├── SliceKernel          Accept(NodeVisitor&) override  [新增]
│   ├── ConcatKernel         Accept(NodeVisitor&) override  [新增]
│   └── ... (全部 17 个)     Accept(NodeVisitor&) override  [新增]
│
├── HwLayer ───────────────────────────────── L3 Analysis Graph (硬件层)
│   │  Accept(HwVisitor& v) { v.Visit(*this); }  [新增] 默认实现
│   │
│   ├── Mpu  (中间基类)  Accept(HwVisitor&) override  [新增]
│   │   ├── Conv2dLayer               Accept override  [新增]
│   │   ├── Conv2dFusionLayer         Accept override  [新增]
│   │   ├── BilinearInterpLayer       Accept override  [新增]
│   │   ├── MatmulLayer               Accept override  [新增]
│   │   └── FixFunc                   Accept override  [新增]
│   │
│   ├── Vpu  (中间基类)  Accept(HwVisitor&) override  [新增]
│   │   ├── EltwiseLayer              Accept override  [新增]
│   │   ├── Pool2dLayer               Accept override  [新增]
│   │   ├── ScaleLayer                Accept override  [新增]
│   │   ├── ReduceLayer               Accept override  [新增]
│   │   ├── BatchNormLayer            Accept override  [新增]
│   │   └── ... (共 14 个叶子类)
│   │
│   ├── Dma  (中间基类)  Accept(HwVisitor&) override  [新增]
│   │   ├── NpuDmaIn                  Accept override  [新增]
│   │   ├── NpuDmaOut                 Accept override  [新增]
│   │   └── NpuDmaForParamDataFetch   Accept override  [新增]
│   │
│   ├── Mte  (中间基类)  Accept(HwVisitor&) override  [新增]
│   │   ├── SliceLayer                Accept override  [新增]
│   │   ├── ConcatLayer               Accept override  [新增]
│   │   ├── PermuteLayer              Accept override  [新增]
│   │   ├── PadLayer                  Accept override  [新增]
│   │   ├── InterpLayer               Accept override  [新增]
│   │   └── ... (共 9 个叶子类)
│   │
│   └── Spu  (中间基类)  Accept(HwVisitor&) override  [新增]
│       ├── SpuActivationLayer        Accept override  [新增]
│       └── ...
│
└── AnalyseNode ────────────────────────────── L3 Wrapper
    │  Accept(HwVisitor& v)   [新增] 路由
    │    if (hw_layer_) hw_layer_->Accept(v);   ← 穿透
    │
    ├── SetHwLayer(HwLayer*)   [不变]
    ├── GetHwLayer()           [不变]
    ├── IsDummy()              [不变]
    └── ... (原有方法全部不变)
```

---

## 改动统计

| 层 | 基类改动 | 子类 Accept 数 | 新建接口 |
|----|---------|:---:|---------|
| Node | 1 行 (`Accept`) | — | NodeVisitor (16 Visit) |
| L1 Operator | 不加 | 45 | — |
| L2 Kernel | 不加 | 28 | — |
| L3 HwLayer | 1 行 (`Accept`) | 41 | HwVisitor (11 Visit) |
| L3 Wrapper | 3 行 (Accept 路由) | — | — |
| **合计** | **3 处基类改动** | **114 Accept** | **2 个 Visitor 接口** |

## 未改动

- 所有 pass 代码（SplitExp、Cascade、SliceFuse...）— **0 处修改**
- 所有类方法的访问方式（`e.Shift_Bn()`、`conv.GetKernelSize()`）— **0 处修改**
- 图遍历逻辑（PatternMatcher、GraphViewer）— **0 处修改**
