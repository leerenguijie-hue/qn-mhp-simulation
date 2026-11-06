# Feng (2015) QN-MHP 复现基础

这是 Feng (2015) 论文第 2–4 章的命令行结构性重建，覆盖独立转向、
Parked 视觉搜索和实验 1 Driving 双任务。它不是作者 MATLAB/Simulink
模型的逐参数移植，也尚不能称为“复现成功”。当前重点是建立可检查的
Figure 4 模块边界、TC 数据流、共享服务器竞争、Figure 23 任务切换和实验指标。

项目不包含 Web UI、Streamlit 或绘图代码；实验输出为 JSON Lines，Python
接口同时返回结构化结果和 Driving 车辆轨迹。

## Figure 4 对应关系

- `task_environment.py` — Figure 4(a)
  - 道路场景、触摸屏、Button、随机 USB 位置、外部视觉刺激、gaze 和动作结果。
  - 不包含 QN-MHP 服务器或 TC。
- `vehicle_dynamics.py` — Figure 4(b)
  - 独立 `VehicleState` 和 Appendix A 车辆更新。
  - 输入绝对方向盘角与 `dt`，输出 `x`、`z`、`yaw`、near/far angle。
- `tasks/` — Figure 4(c)
  - `steering.py`：Figure 6 的 TC1–TC6 和 Salvucci 控制律。
  - `visual_search.py`：Figure 22 的 TC1–TC9。
  - `dual_task.py`：Figure 23 Performance Monitor、glance 和暂停/恢复。
- `cognitive_architecture.py` — Figure 4(d)
  - 仅包含 `Entity`、`OperatorSpec`、`Server`、`QueueNetwork` 和离散事件调度。
- `driver_model.py` — Figure 4 虚线框 Driver Model
  - 创建唯一 QueueNetwork 和算子注册表。
  - 所有任务共享完全相同的 `1、2/3、4、A、C、W、Y、Z` Server 实例。
- `model_config.py`
  - 参数值、来源、注释和待标定状态。

## 队列与 TC 语义

`OperatorSpec` 明确保存算子名称、服务器路径、各服务器附加服务需求和动态
参数规则。响应时间由服务器等待、服务器默认服务时间及算子服务需求共同产生。
时间参数不塞入 Entity payload。

每个 `Server` 持有自己的 FIFO 队列和当前服务实体；队列不属于算子。因此
`COMPARE`、`VISUAL_SEARCH` 与 `DETERMINE_STEERING` 使用同一个 C 队列。
Server 支持可配置容量；当前 Server 4 以容量 4 表达论文的视觉对象识别容量，
不再使用 `(N-4)×penalty` 线性罚时。

每个 TC 只激活一个论文算子。`_tc...` 方法负责激活，
`_..._completed` 方法只在服务器完成后提交状态并激活后继 TC。空路径
`GOTO` 和 `GOAL_ACCOMPLISHED` 仍进入显式算子历史，并在同一仿真时间回调。

Entity 包含任务、类型、创建时间、父 Entity ID 和完整服务器历史。视觉搜索
的数据链为：

```text
Button external stimulus
→ TC1 LOOK_AT → perceived
→ TC2 STORE_TO_STM → stored
→ TC3 RETRIEVE_FROM_STM → retrieved
→ TC4 COMPARE → comparison
→ TC5 GOTO
→ TC6 VISUAL_SEARCH 或 TC7 REACH_WITH_HAND
→ TC8 CLICK_WITH_FINGER
→ TC9 GOAL_ACCOMPLISHED
```

只有 TC1 读取按钮标签。TC7/TC8 使用 Entity 一直携带的位置与宽度，不重新读取
环境。TC6 总是经过 C，并保存 perfect search memory。

转向中 50 ms 是环境 road stimulus 的生成间隔；TC6 是任务程序的显式 GOTO。
两者独立。near/far 在 TC2 的 A 完成后配对，TC3 再显式经过 A，之后才进入 C。

## Figure 23 与 Driving 指标

Performance Monitor 在视觉搜索 TC5 mismatch、准备进入 TC6 时检查当前
off-road glance：

- 未达到阈值：直接继续 TC6。
- 达到阈值：在 TC6 前暂停，保存 `examined/attention/focus`，切回道路，
  插入配置数量的完整 Steering TC1–TC6，满足最短 road check 后重新看设备并
  恢复同一个 TC6。

Driving 输出：

- Task Completion Time：首次 off-road glance 开始至最后一次 glance 结束。
- TEORT：所有 off-road glance 时长之和。
- glance 数和每次时长。
- long glance 数，严格使用 `duration > 2.0 s`。
- 检查按钮数、插入驾驶循环数。
- 完整 `time/x/yaw/steering angle` 轨迹、最终状态和最大绝对横向偏差。

## 参数来源

`model_config.py` 将参数严格分为：

- `PAPER_DERIVED`
  - 50 ms 视觉刺激间隔、视觉识别容量 4、按钮尺寸/间距/布局、800×480 屏幕、
    USB 目标、near distance 10 m、far THW 4 s、65 mph = 29 m/s、
    0.3/0.6/0.9/1.2 m 转向初始偏移、每条件 10 次模型重复和 long glance 2 s。
- `RECONSTRUCTED`
  - Server/Operator 时间、除 Server 4 外的容量、Fitts/扫视参数、wheelbase、
    转向增益与限幅、积分步长、Performance Monitor 阈值和 road check 时长。
  - 这些值只是透明的可运行默认值，不能引用为论文原值。
- `CALIBRATED`
  - 当前为空；尚未执行并记录对 Chapter 3 人类数据的参数拟合。

论文不能唯一确定、当前明确采用重建方案的部分：

- 第 4 章文字 STM 没有给出服务器字母；当前按任务规格使用 A。
- Figure 6 明示 TC3，但正文总路径只列一次 A；当前 TC3 显式第二次经过 A。
- 论文称 C 可并行低层操作；当前默认 C capacity=1，以实现要求中的共享 FIFO
  竞争。容量是可配置的。
- 视觉搜索的精确服务器路由、服务分布、Fitts 系数和扫视方程未给出。
- Figure 23 的切换阈值、road glance 时长和插入循环数未给出。
- Appendix A 印刷式 `|R|·sin(α/2)` 与“负 R 表示左转”及 Figure 8 的方向
  相冲突。代码使用正的弦长保持左转符号，并在参数清单中标记为重建修正。

## 安装与运行

```bash
python -m pip install -r requirements.txt
python -m pytest
python -m ruff check .
python experiment_steering.py
python experiment_parked.py
python experiment_driving.py
```

Parked 和 Driving 默认运行 4/8/15 按钮 × small/medium/large 共 9 个条件，
每条件 10 次，使用固定、可重复的种子。两个入口分别对照 Chapter 3 Table 1
和 Table 2，并报告 RMSE 与 MAPE。Driving 还输出 Figure 28 对应的
1/2/>2 glance 比例和 Figure 29 对应的 long-glance 均值。

## 当前验证结果与边界

2026-11-06 的本仓库默认参数运行结果：

- `pytest`：21 个测试全部通过。
- `ruff`：全部通过。
- 独立转向：四个论文初始偏移均能在 8 s 内向中心收敛，但轨迹与 Figure 8/9
  尚未定量数字化比较，转向增益仍是重建值。
- Parked：RMSE `0.645 s`，MAPE `34.21%`。
- Driving TCT：RMSE `1.477 s`，MAPE `55.09%`。
- Driving TEORT：RMSE `1.195 s`，MAPE `50.76%`。
- 默认批量结果没有产生 long glance，说明当前服务时间和 Performance Monitor
  参数明显偏快，不能复现 Figure 29。

这些偏差被保留并报告，没有通过隐藏结构问题或把重建值伪装成论文参数来贴合
结果。下一步需要数字化 Figure 8/9、Figure 25–29，并在固定结构与公开目标函数
下校准 `CALIBRATED` 参数。
