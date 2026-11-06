# 最小 QN-MHP：视觉搜索 TC1–TC9

这是 `simple-qn-mhp` 教学分支。完整的 Driving、车辆动力学和 Performance
Monitor 实现在 `main` 分支；本分支刻意删除这些模块，只保留：

- 信息实体 `Entity`；
- 算子定义 `OperatorSpec`；
- 共享服务器 `Server`；
- 同步队列网络 `QueueNetwork`；
- Figure 22 视觉搜索 TC1–TC9；
- 一个普通输入、普通返回值的公开函数。

它的目标是先看清楚 Entity 怎样在 TC 和 Server 之间流动，不宣称已经复现论文
完整实验。

## 最简单的使用方式

```python
from qn_mhp import run_visual_search

result = run_visual_search(
    ["AM1", "FM1", "USB", "DVD", "AM2", "FM2", "MP3", "CD"],
    target_label="USB",
    seed=2,
)

print(result.completion_time_s)
print(result.clicked_index)
print(result.examined_indices)
print(result.tc_trace)
print(result.server_trace)
```

输入只有按钮标签、目标文字和随机种子。输出是一个 `TrialResult`，包含完成时间、
点击位置、检查顺序、TC 输入输出记录、全部 Entity 和服务器访问记录。

## 同步 return 风格

每个 TC 都是普通函数调用：

```python
perceived, time = model.tc1(time, parent=None)
stored, time = model.tc2(perceived, time)
retrieved, time = model.tc3(stored, time)
comparison, time = model.tc4(retrieved, time)
match, time = model.tc5(comparison, time)
```

没有 callback、Performance Monitor 或事件日历。Server 直接返回完成时间：

```text
service_start  = max(arrival_time, server_available_time)
service_finish = service_start + default_service + operator_demand
```

因此仍然保留排队等待，但使用者看到的是普通同步输入输出。

## TC1–TC9 输入输出

- TC1 `LOOK_AT`
  - 输入：`Button`
  - 路径：`1 → 2/3 → 4`
  - 输出：`perceived_button Entity`
- TC2 `STORE_TO_STM`
  - 输入：TC1 的 perceived Entity
  - 路径：`A`
  - 输出：`stored_button Entity`
- TC3 `RETRIEVE_FROM_STM`
  - 输入：TC2 的 stored Entity
  - 路径：`A`
  - 输出：`retrieved_button Entity`
- TC4 `COMPARE`
  - 输入：TC3 的 retrieved Entity
  - 路径：`C`
  - 输出：包含 `match` 的 comparison Entity
- TC5 `GOTO`
  - 输入：comparison Entity
  - 路径：空
  - 输出：`match → TC7`，`mismatch → TC6`
- TC6 `VISUAL_SEARCH`
  - 输入：comparison Entity 和内部 `examined/attention`
  - 路径：`C`
  - 输出：下一个 focus Entity
- TC7 `REACH_WITH_HAND`
  - 输入：匹配 Entity 携带的按钮位置
  - 路径：`W → Y → Z`
  - 输出：`reached_target Entity`
- TC8 `CLICK_WITH_FINGER`
  - 输入：TC7 的 reached Entity
  - 路径：`W → Y → Z`
  - 输出：`clicked_target Entity`
- TC9 `GOAL_ACCOMPLISHED`
  - 输入：TC8 的 clicked Entity
  - 路径：空
  - 输出：`done Entity`

## Entity 数据链

一次成功搜索的实体血缘可以直接通过 `parent_entity_id` 检查：

```text
visual_stimulus
→ perceived_button
→ stored_button
→ memory_request
→ retrieved_button
→ comparison
→ search_selection / reached_target
→ clicked_target
→ done
```

`result.tc_trace` 显示每个 TC 的输入/输出 Entity ID；
`result.server_trace` 显示每次服务器进入、开始、完成和等待时间。

## 命令行

```bash
python -m pip install -r requirements.txt
python run_simple.py --summary-only
python run_simple.py
python -m pytest
python -m ruff check .
```

完整 JSON 输出：

```bash
python run_simple.py \
  --labels "AM1,FM1,USB,DVD,AM2,FM2,MP3,CD" \
  --target USB \
  --seed 2
```

## 文件

- `qn_mhp.py`：全部模型代码。
- `run_simple.py`：命令行入口。
- `tests/test_simple_qn_mhp.py`：最小行为测试。

## 模型边界

- 识别容量 4 和 USB 目标来自论文。
- Server 时间、Operator demand 和固定扫视需求是透明的重建值，不是论文参数。
- 当前同步 QueueNetwork 要求同一 Server 的请求按到达时间顺序提交。
- 适合单条视觉搜索 Entity 流和基础 FIFO 演示。
- 不包含并行离散事件调度、Driving 双任务、车辆、视线切换或实验拟合。
