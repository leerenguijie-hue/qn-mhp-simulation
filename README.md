# QN-MHP 驾驶员认知计算仿真平台

这是一个基于 Streamlit 的交互式网页原型。可以调节车辆参数、视觉采样间隔、服务器服务时间倍率和控制增益，运行 QN-MHP 风格队列网络仿真，并查看车辆轨迹、横向位置、方向盘转角和近/远观察点角度。

## 文件结构

- `app.py`：Streamlit 网页入口（第 2 章转向仿真）
- `qn_mhp_queue_network.py`：第 2 章转向队列网络
- `qn_mhp_network.py`：QN-MHP 服务器与算子路由（共用）
- `qn_mhp_visual_search_parked.py`：第 4 章 Parked 视觉搜索复现（对应第 3 章实验单任务条件）
- `requirements.txt`：运行依赖

### Parked 视觉搜索（命令行）

```bash
python qn_mhp_visual_search_parked.py
```

输出 9 种按钮布局 × 3 种尺寸下的模型平均任务完成时间，并与论文第 3 章 Table 1（Parked）人类均值对照。

## 本地运行

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 部署到 Streamlit Community Cloud

1. 在 GitHub 新建一个仓库。
2. 上传 `app.py`、`qn_mhp_queue_network.py`、`requirements.txt` 和 `README.md`。
3. 登录 Streamlit Community Cloud，选择该 GitHub 仓库及 `app.py`。
4. 点击 Deploy，等待构建完成后即可通过网页链接访问。

## 模型边界与复现说明

当前仿真核心是对论文结构的可运行重建，不等同于论文作者原始 MATLAB 实现。第 2 章转向与第 4 章 Parked 搜索的服务时间、Fitts/扫视等参数均为暂定值，需对照原文或再标定。修改模型核心时，应同步更新本 README 中的模型说明。
