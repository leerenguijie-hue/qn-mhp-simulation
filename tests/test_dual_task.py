"""Tests for Figure 23 gaze switching and Driving metrics."""
from __future__ import annotations

import pytest

from driver_model import DriverModel
from experiment_driving import simulate_driving_trial
from model_config import PerformanceMonitorConfig
from task_environment import TaskEnvironment
from tasks.dual_task import Glance, PerformanceMonitor
from tasks.steering import SteeringTask


def test_dual_task_can_produce_one_and_multiple_glances() -> None:
    one_glance = simulate_driving_trial(
        "3x5",
        "small",
        1,
        monitor_config=PerformanceMonitorConfig(
            off_road_threshold_s=100.0,
            minimum_road_check_s=0.0,
            driving_cycles_per_check=1,
        ),
    )
    multiple_glances = simulate_driving_trial(
        "3x5",
        "small",
        1,
        monitor_config=PerformanceMonitorConfig(
            off_road_threshold_s=0.01,
            minimum_road_check_s=0.0,
            driving_cycles_per_check=1,
        ),
    )

    assert one_glance.glance_count == 1
    assert multiple_glances.glance_count > 1
    assert multiple_glances.inserted_driving_cycles > 0


def test_teort_equals_sum_of_off_road_glances() -> None:
    result = simulate_driving_trial("3x5", "medium", 3)
    assert result.teort_s == pytest.approx(sum(result.glance_durations_s))


def test_long_glance_criterion_is_strictly_greater_than_two_seconds() -> None:
    environment = TaskEnvironment()
    driver = DriverModel()
    steering = SteeringTask(driver.network, environment)
    monitor = PerformanceMonitor(driver.network, environment, steering)
    monitor.glances = [
        Glance(0.0, 2.0),
        Glance(3.0, 5.000001),
    ]

    assert monitor.long_glance_count == 1


def test_fixed_seed_reproduces_driving_result() -> None:
    first = simulate_driving_trial("2x4", "large", 987)
    second = simulate_driving_trial("2x4", "large", 987)

    assert first.summary_record() == second.summary_record()
    assert first.trajectory == second.trajectory
