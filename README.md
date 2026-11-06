# QN-MHP 仿真（命令行）

Feng 论文风格的 QN-MHP 队列网络重建：第 2 章车道转向与第 4 章 Parked 视觉搜索。无 Web UI、无绘图输出。

## 文件结构

- `qn_mhp_queue_network.py`：第 2 章转向队列网络
- `qn_mhp_network.py`：QN-MHP 服务器与算子路由（共用）
- `qn_mhp_visual_search_parked.py`：第 4 章 Parked 视觉搜索（第 3 章实验单任务条件）
- `requirements.txt`：运行依赖

## 本地运行

```bash
pip install -r requirements.txt
```

### 转向仿真（第 2 章）

```bash
python qn_mhp_queue_network.py
```

在终端打印各初始横向偏移下的最终车道位置与航向角。

### Parked 视觉搜索（第 4 章）

```bash
python qn_mhp_visual_search_parked.py
```

输出 9 种按钮布局 × 3 种尺寸下的模型平均任务完成时间，并与论文第 3 章 Table 1（Parked）人类均值对照。

## 模型边界与复现说明

当前仿真核心是对论文结构的可运行重建，不等同于论文作者原始 MATLAB 实现。第 2 章转向与第 4 章 Parked 搜索的服务时间、Fitts/扫视等参数均为暂定值，需对照原文或再标定。修改模型核心时，应同步更新本 README 中的模型说明。
