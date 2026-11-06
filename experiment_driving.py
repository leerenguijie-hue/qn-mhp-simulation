"""Command-line reconstruction of Feng (2015) Experiment 1 Driving trials."""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field

import numpy as np

from driver_model import DriverModel
from model_config import (
    PAPER_DERIVED,
    RECONSTRUCTED,
    PerformanceMonitorConfig,
    SteeringConfig,
    VehicleConfig,
    VisualSearchConfig,
)
from task_environment import (
    BUTTON_SIZES_PX,
    LAYOUTS,
    TaskEnvironment,
    TouchscreenEnvironment,
)
from tasks.dual_task import PerformanceMonitor
from tasks.steering import SteeringTask
from tasks.visual_search import VisualSearchTask
from vehicle_dynamics import VehicleDynamics

HUMAN_DRIVING_TCT_MEANS = {
    "2x2": {"small": 2.00, "medium": 1.82, "large": 1.80},
    "2x4": {"small": 2.79, "medium": 2.39, "large": 2.57},
    "3x5": {"small": 3.73, "medium": 3.36, "large": 3.61},
}

HUMAN_TEORT_MEANS = {
    "2x2": {"small": 1.87, "medium": 1.71, "large": 1.70},
    "2x4": {"small": 2.43, "medium": 2.16, "large": 2.28},
    "3x5": {"small": 3.20, "medium": 2.92, "large": 3.11},
}


@dataclass(frozen=True)
class DrivingExperimentConfig:
    """Numerical controls for one dual-task simulation."""

    dt_s: float = RECONSTRUCTED["simulation_step_s"].value
    maximum_trial_time_s: float = 30.0
    initial_lateral_offset_m: float = RECONSTRUCTED[
        "driving_initial_lateral_offset_m"
    ].value


@dataclass
class DrivingTrialResult:
    """Structured dual-task trial metrics and vehicle trajectory."""

    layout: str
    size: str
    seed: int
    task_completion_time_s: float
    teort_s: float
    glance_count: int
    glance_durations_s: list[float]
    long_glance_count: int
    checked_buttons: int
    inserted_driving_cycles: int
    final_lateral_position_m: float
    final_yaw_rad: float
    final_steering_angle_rad: float
    maximum_absolute_lateral_deviation_m: float
    trajectory: dict[str, list[float]] = field(repr=False)

    def summary_record(self) -> dict[str, object]:
        """Return JSON-friendly metrics without the high-rate trajectory."""
        record = asdict(self)
        record.pop("trajectory")
        return record


@dataclass(frozen=True)
class DrivingConditionResult:
    """Aggregate output for one layout/size condition."""

    layout: str
    size: str
    replications: int
    model_tct_mean_s: float
    human_tct_mean_s: float
    model_teort_mean_s: float
    human_teort_mean_s: float
    model_glance_mean: float
    model_long_glance_mean: float
    one_glance_proportion: float
    two_glance_proportion: float
    more_than_two_glance_proportion: float
    final_lateral_position_mean_m: float
    final_yaw_mean_rad: float
    final_steering_angle_mean_rad: float
    maximum_absolute_lateral_deviation_mean_m: float


def simulate_driving_trial(
    layout_key: str,
    size_key: str,
    seed: int,
    *,
    experiment_config: DrivingExperimentConfig | None = None,
    visual_config: VisualSearchConfig | None = None,
    steering_config: SteeringConfig | None = None,
    vehicle_config: VehicleConfig | None = None,
    monitor_config: PerformanceMonitorConfig | None = None,
) -> DrivingTrialResult:
    """Run one Figure 23 dual-task trial on a single shared network."""
    experiment = experiment_config or DrivingExperimentConfig()
    visual = visual_config or VisualSearchConfig()
    steering = steering_config or SteeringConfig()
    vehicle_parameters = vehicle_config or VehicleConfig()
    monitor_parameters = monitor_config or PerformanceMonitorConfig()

    rng = np.random.default_rng(seed)
    touchscreen = TouchscreenEnvironment.create(layout_key, size_key, rng)
    environment = TaskEnvironment(touchscreen=touchscreen, gaze_target="road")
    vehicle = VehicleDynamics(
        experiment.initial_lateral_offset_m,
        vehicle_parameters,
    )
    near_angle, far_angle = vehicle.visual_angles()
    environment.road.update(near_angle, far_angle, 0.0)

    driver = DriverModel(visual_config=visual)
    steering_task = SteeringTask(driver.network, environment, steering)
    monitor = PerformanceMonitor(
        driver.network,
        environment,
        steering_task,
        monitor_parameters,
    )
    search_task = VisualSearchTask(
        environment,
        rng,
        driver.network,
        visual,
        monitor,
    )
    driver.register_task("steering", steering_task)
    driver.register_task("visual_search", search_task)
    driver.register_task("performance_monitor", monitor)

    times = [0.0]
    lateral = [vehicle.state.x]
    yaw = [vehicle.state.yaw]
    steering_angles = [vehicle.state.steering_angle]
    search_task.start(0.0)

    visual_tick = max(
        1,
        round(steering.visual_interval_s / experiment.dt_s),
    )
    step_index = 0
    while search_task.completion_at is None:
        step_index += 1
        current_time = step_index * experiment.dt_s
        if current_time > experiment.maximum_trial_time_s:
            raise RuntimeError(
                f"Driving trial exceeded {experiment.maximum_trial_time_s}s"
            )

        # Integrate first: actions completed during this interval become
        # effective on the next fixed-step interval.
        state = vehicle.step(steering_task.steering_angle, experiment.dt_s)
        if step_index % visual_tick == 0:
            # This is environmental stimulus production. TC6 remains task
            # program control and does not manufacture the 50 ms stimulus.
            environment.road.update(
                state.near_angle,
                state.far_angle,
                current_time,
            )
        driver.process_until(current_time)

        times.append(current_time)
        lateral.append(state.x)
        yaw.append(state.yaw)
        steering_angles.append(state.steering_angle)

    glance_metrics = monitor.metrics()
    return DrivingTrialResult(
        layout=layout_key,
        size=size_key,
        seed=seed,
        task_completion_time_s=float(
            glance_metrics["task_completion_time_s"]
        ),
        teort_s=float(glance_metrics["teort_s"]),
        glance_count=int(glance_metrics["glance_count"]),
        glance_durations_s=list(glance_metrics["glance_durations_s"]),
        long_glance_count=int(glance_metrics["long_glance_count"]),
        checked_buttons=search_task.checked_button_count,
        inserted_driving_cycles=int(
            glance_metrics["inserted_driving_cycles"]
        ),
        final_lateral_position_m=vehicle.state.x,
        final_yaw_rad=vehicle.state.yaw,
        final_steering_angle_rad=vehicle.state.steering_angle,
        maximum_absolute_lateral_deviation_m=max(
            abs(value) for value in lateral
        ),
        trajectory={
            "time_s": times,
            "lateral_position_m": lateral,
            "yaw_rad": yaw,
            "steering_angle_rad": steering_angles,
        },
    )


def run_all_conditions(
    replications: int | None = None,
    base_seed: int = 20_150_101,
) -> tuple[list[DrivingConditionResult], list[DrivingTrialResult]]:
    """Run all nine Driving conditions with reproducible seeds."""
    repeats = replications or int(
        PAPER_DERIVED["replications_per_condition"].value
    )
    conditions = []
    all_trials = []
    condition_index = 0
    for layout in LAYOUTS:
        for size in BUTTON_SIZES_PX:
            condition_seed = base_seed + condition_index * 10_000
            trials = [
                simulate_driving_trial(
                    layout,
                    size,
                    condition_seed + repeat,
                )
                for repeat in range(repeats)
            ]
            all_trials.extend(trials)
            tct = np.asarray(
                [trial.task_completion_time_s for trial in trials]
            )
            teort = np.asarray([trial.teort_s for trial in trials])
            glances = np.asarray([trial.glance_count for trial in trials])
            long_glances = np.asarray(
                [trial.long_glance_count for trial in trials]
            )
            deviations = np.asarray(
                [
                    trial.maximum_absolute_lateral_deviation_m
                    for trial in trials
                ]
            )
            final_lateral = np.asarray(
                [trial.final_lateral_position_m for trial in trials]
            )
            final_yaw = np.asarray(
                [trial.final_yaw_rad for trial in trials]
            )
            final_steering = np.asarray(
                [trial.final_steering_angle_rad for trial in trials]
            )
            conditions.append(
                DrivingConditionResult(
                    layout=layout,
                    size=size,
                    replications=repeats,
                    model_tct_mean_s=float(np.mean(tct)),
                    human_tct_mean_s=HUMAN_DRIVING_TCT_MEANS[layout][size],
                    model_teort_mean_s=float(np.mean(teort)),
                    human_teort_mean_s=HUMAN_TEORT_MEANS[layout][size],
                    model_glance_mean=float(np.mean(glances)),
                    model_long_glance_mean=float(np.mean(long_glances)),
                    one_glance_proportion=float(np.mean(glances == 1)),
                    two_glance_proportion=float(np.mean(glances == 2)),
                    more_than_two_glance_proportion=float(
                        np.mean(glances > 2)
                    ),
                    final_lateral_position_mean_m=float(
                        np.mean(final_lateral)
                    ),
                    final_yaw_mean_rad=float(np.mean(final_yaw)),
                    final_steering_angle_mean_rad=float(
                        np.mean(final_steering)
                    ),
                    maximum_absolute_lateral_deviation_mean_m=float(
                        np.mean(deviations)
                    ),
                )
            )
            condition_index += 1
    return conditions, all_trials


def comparison_metrics(
    conditions: list[DrivingConditionResult],
) -> dict[str, float]:
    """Compute RMSE/MAPE for Table 1 TCT and Table 2 TEORT."""

    def metrics(
        model: np.ndarray,
        human: np.ndarray,
        prefix: str,
    ) -> dict[str, float]:
        errors = model - human
        return {
            f"{prefix}_rmse_s": float(
                math.sqrt(float(np.mean(errors**2)))
            ),
            f"{prefix}_mape_percent": float(
                np.mean(np.abs(errors) / human) * 100.0
            ),
        }

    model_tct = np.asarray(
        [condition.model_tct_mean_s for condition in conditions]
    )
    human_tct = np.asarray(
        [condition.human_tct_mean_s for condition in conditions]
    )
    model_teort = np.asarray(
        [condition.model_teort_mean_s for condition in conditions]
    )
    human_teort = np.asarray(
        [condition.human_teort_mean_s for condition in conditions]
    )
    return {
        **metrics(model_tct, human_tct, "tct"),
        **metrics(model_teort, human_teort, "teort"),
    }


def main() -> None:
    """Print JSON Lines for all conditions and aggregate comparison."""
    conditions, _trials = run_all_conditions()
    for condition in conditions:
        print(json.dumps(asdict(condition), ensure_ascii=False))
    print(
        json.dumps(
            {
                **comparison_metrics(conditions),
                "parameter_status": (
                    "Performance Monitor, service, gaze, Fitts, and steering "
                    "values are RECONSTRUCTED and pending calibration"
                ),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
