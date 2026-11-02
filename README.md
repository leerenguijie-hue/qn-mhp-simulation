# QN-MHP 驾驶员认知计算仿真平台

这是一个基于 Streamlit 的交互式网页原型。可以调节车辆参数、视觉采样间隔、服务器服务时间倍率和控制增益，运行 QN-MHP 风格队列网络仿真，并查看车辆轨迹、横向位置、方向盘转角和近/远观察点角度。

## 文件结构

- `app.py`：Streamlit 网页入口
- `qn_mhp_queue_network.py`：仿真核心逻辑
- `requirements.txt`：运行依赖

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

当前仿真核心是对论文结构的可运行重建，不等同于论文作者原始 MATLAB 实现。现有核心代码中服务器服务时间、控制增益等参数属于暂定值，部署前后都应在论文核验后再用于正式实验或论文结论。修改模型核心时，应同步更新本 README 中的模型说明。
