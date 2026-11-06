"""Command-line Chapter 2 steering reconstruction."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass

import numpy as np

from driver_model import DriverModel
from model_config import PAPER_DERIVED, SteeringConfig, VehicleConfig
from task_environment import TaskEnvironment
from tasks.steering import SteeringTask
from vehicle_dynamics import VehicleDynamics


@dataclass(frozen=True)
class SteeringExperimentConfig:
    """Numerical settings; the time step is a reconstructed value."""

    dt_s: float = 0.01
    duration_s: float = 8.0
    initial_offsets_m: tuple[float, ...] = PAPER_DERIVED[
        "steering_initial_offsets_m"
    ].value


def simulate_steering(
    initial_lateral_position: float,
    experiment_config: SteeringExperimentConfig | None = None,
    vehicle_config: VehicleConfig | None = None,
    task_config: SteeringConfig | None = None,
) -> dict[str, np.ndarray | int]:
    """Run the standalone task with independent 50 ms stimulus arrivals."""
    experiment = experiment_config or SteeringExperimentConfig()
    vehicle = VehicleDynamics(
        initial_lateral_position,
        vehicle_config or VehicleConfig(),
    )
    environment = TaskEnvironment()
    driver = DriverModel()
    steering_task = SteeringTask(
        driver.network,
        environment,
        task_config or SteeringConfig(),
    )
    driver.register_task("steering", steering_task)

    dt = experiment.dt_s
    time = np.arange(0.0, experiment.duration_s + dt / 2.0, dt)
    lateral = np.zeros_like(time)
    forward = np.zeros_like(time)
    yaw = np.zeros_like(time)
    steering = np.zeros_like(time)
    near_angles = np.zeros_like(time)
    far_angles = np.zeros_like(time)
    lateral[0] = initial_lateral_position
    near_angle, far_angle = vehicle.visual_angles()
    environment.road.update(near_angle, far_angle, 0.0)
    near_angles[0], far_angles[0] = near_angle, far_angle

    visual_tick = max(
        1,
        round(steering_task.config.visual_interval_s / dt),
    )
    steering_task.submit_visual_angles(near_angle, far_angle, 0.0)

    for index in range(1, len(time)):
        current_time = float(time[index])
        driver.process_until(current_time)
        state = vehicle.step(steering_task.steering_angle, dt)
        environment.road.update(
            state.near_angle,
            state.far_angle,
            current_time,
        )

        lateral[index] = state.x
        forward[index] = state.z
        yaw[index] = state.yaw
        steering[index] = state.steering_angle
        near_angles[index] = state.near_angle
        far_angles[index] = state.far_angle
        if index % visual_tick == 0:
            steering_task.submit_visual_angles(
                state.near_angle,
                state.far_angle,
                current_time,
            )

    return {
        "time": time,
        "x": lateral,
        "z": forward,
        "yaw": yaw,
        "steering_angle": steering,
        "near_angle": near_angles,
        "far_angle": far_angles,
        "completed_cycles": steering_task.cycles_completed,
    }


def main() -> None:
    """Print one JSON record per initial lateral offset."""
    config = SteeringExperimentConfig()
    for offset in config.initial_offsets_m:
        result = simulate_steering(offset, config)
        record = {
            "initial_offset_m": offset,
            "final_x_m": float(result["x"][-1]),
            "final_yaw_deg": math.degrees(float(result["yaw"][-1])),
            "completed_cycles": int(result["completed_cycles"]),
            "parameter_status": "RECONSTRUCTED; not a validated replication",
        }
        print(json.dumps(record, ensure_ascii=False))


if __name__ == "__main__":
    main()
