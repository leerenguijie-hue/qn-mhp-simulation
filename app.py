import copy
import io
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import streamlit as st
import qn_mhp_queue_network as qn

st.set_page_config(page_title="QN-MHP 驾驶员认知仿真平台", page_icon="🚗", layout="wide")

st.title("🚗 QN-MHP 驾驶员认知计算仿真平台")
st.caption("可交互调整参数、运行队列网络仿真，并观察车辆运动与视觉—认知—动作链条。")

with st.sidebar:
    st.header("仿真参数")
    st.subheader("车辆与环境")
    initial_x = st.slider("初始横向偏移 X₀（m）", 0.1, 2.0, 0.6, 0.1)
    speed = st.slider("车速（m/s）", 10.0, 35.0, 29.0, 1.0)
    wheelbase = st.slider("轴距（m）", 2.0, 3.5, 2.7, 0.1)
    near_distance = st.slider("近距离观察点（m）", 3.0, 20.0, 10.0, 0.5)
    far_thw = st.slider("远距离观察点 THW（s）", 1.0, 6.0, 4.0, 0.5)

    st.subheader("时间设置")
    duration = st.slider("仿真时长（s）", 2.0, 20.0, 8.0, 1.0)
    visual_interval = st.select_slider("视觉采样间隔", options=[0.025, 0.05, 0.075, 0.1], value=0.05,
                                       format_func=lambda x: f"{int(x*1000)} ms")

    st.subheader("认知控制参数")
    service_scale = st.slider("服务器服务时间倍率", 0.25, 3.0, 1.0, 0.05,
                              help="整体缩放各服务器的暂定服务时间；不是论文已校准参数。")
    k_far = st.slider("远点反馈系数 k_far", -2.0, 0.0, -0.8, 0.05)
    k_near = st.slider("近点反馈系数 k_near", -2.0, 0.0, -0.8, 0.05)
    k_i = st.slider("积分反馈系数 k_I", -2.0, 0.0, -0.5, 0.05)
    max_steer = st.slider("方向盘角度限制（°）", 10.0, 60.0, 45.0, 1.0)

    run = st.button("▶ 运行仿真", type="primary", use_container_width=True)

st.info("模型说明：视觉信息按固定间隔进入队列网络，依次经过处理服务器；控制结果经动作通道后影响车辆动力学。服务时间与控制增益目前包含暂定值，需结合论文原文或后续校准。")

if run or "sim_results" not in st.session_state:
    original = copy.deepcopy(qn.CONFIG)
    try:
        qn.CONFIG["duration"] = float(duration)
        qn.CONFIG["visual_interval"] = float(visual_interval)
        qn.CONFIG["speed"] = float(speed)
        qn.CONFIG["wheelbase"] = float(wheelbase)
        qn.CONFIG["near_distance"] = float(near_distance)
        qn.CONFIG["far_thw"] = float(far_thw)
        qn.CONFIG["k_far"] = float(k_far)
        qn.CONFIG["k_near"] = float(k_near)
        qn.CONFIG["k_i"] = float(k_i)
        qn.CONFIG["max_phi_deg"] = float(max_steer)
        qn.CONFIG["service"] = {k: v * service_scale for k, v in original["service"].items()}
        result = qn.simulate(float(initial_x))
        st.session_state["sim_results"] = result
        st.session_state["sim_params"] = {
            "初始横向偏移": initial_x, "车速": speed, "仿真时长": duration,
            "视觉采样间隔": visual_interval, "服务时间倍率": service_scale,
            "k_far": k_far, "k_near": k_near, "k_I": k_i
        }
    finally:
        qn.CONFIG.clear()
        qn.CONFIG.update(original)

r = st.session_state["sim_results"]
t = r["time"]

m1, m2, m3, m4 = st.columns(4)
m1.metric("最终横向位置", f"{r['x'][-1]:.3f} m")
m2.metric("最终航向角", f"{np.rad2deg(r['yaw'][-1]):.2f}°")
m3.metric("最终转向角", f"{np.rad2deg(r['phi'][-1]):.2f}°")
m4.metric("仿真采样点", f"{len(t):,}")

st.subheader("1. 车辆运动轨迹")
fig, ax = plt.subplots(figsize=(10, 4.5))
ax.plot(r["x"], r["z"], label="车辆轨迹")
ax.axvline(0, linestyle="--", linewidth=1, label="车道中心线")
ax.set_xlabel("横向位置 X（m）")
ax.set_ylabel("前进距离 Z（m）")
ax.set_title("车辆在车道坐标系中的运动轨迹")
ax.grid(alpha=0.25)
ax.legend()
ax.axis("equal")
st.pyplot(fig, use_container_width=True)
plt.close(fig)

left, right = st.columns(2)
with left:
    st.subheader("2. 横向位置与方向盘转角")
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(t, r["x"], label="横向位置 X（m）")
    ax.set_xlabel("时间（s）")
    ax.set_ylabel("横向位置（m）")
    ax.grid(alpha=0.25)
    ax.legend(loc="upper left")
    ax2 = ax.twinx()
    ax2.plot(t, np.rad2deg(r["phi"]), linestyle="--", label="方向盘转角 φ（°）")
    ax2.set_ylabel("方向盘转角（°）")
    ax2.legend(loc="upper right")
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)
with right:
    st.subheader("3. 近、远观察点角度")
    fig, ax = plt.subplots(figsize=(7, 4))
    ax.plot(t, np.rad2deg(r["theta_near"]), label="近点角度")
    ax.plot(t, np.rad2deg(r["theta_far"]), label="远点角度")
    ax.set_xlabel("时间（s）")
    ax.set_ylabel("视角（°）")
    ax.grid(alpha=0.25)
    ax.legend()
    st.pyplot(fig, use_container_width=True)
    plt.close(fig)

st.subheader("4. 认知处理链条")
st.markdown("""
`视觉采样（近点 / 远点）` → `早期视觉处理（Server 1、2/3、4）` → `视觉信息暂存（A）` → `控制计算（C）` → `动作准备与执行（W、Y、Z）` → `车辆动力学更新`

当前实现按既定路由推进实体，并用服务时间模拟处理延迟。此图展示的是代码中的处理结构，不代表每个服务器的具体生理含义都已由论文逐项验证。
""")

with st.expander("查看本次仿真参数"):
    st.json(st.session_state.get("sim_params", {}))

out = pd.DataFrame({
    "time_s": t,
    "lateral_position_m": r["x"],
    "forward_distance_m": r["z"],
    "yaw_deg": np.rad2deg(r["yaw"]),
    "steering_deg": np.rad2deg(r["phi"]),
    "near_angle_deg": np.rad2deg(r["theta_near"]),
    "far_angle_deg": np.rad2deg(r["theta_far"]),
})
st.download_button("⬇ 下载本次仿真 CSV", out.to_csv(index=False).encode("utf-8-sig"),
                   file_name="qn_mhp_simulation.csv", mime="text/csv")

st.warning("研究使用提醒：本平台是可运行的研究原型，不是论文原始 MATLAB 模型的逐项复刻。服务器服务时间、部分控制参数及个别实现细节仍需对照论文核验；不要将当前默认参数直接表述为论文实测或标定值。")
st.caption("本地运行：在项目目录执行 `pip install -r requirements.txt`，再执行 `streamlit run app.py`。")
