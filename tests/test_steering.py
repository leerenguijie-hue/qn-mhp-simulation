"""Tests for the explicit Figure 6 steering program."""
from __future__ import annotations

import numpy as np

from driver_model import DriverModel
from task_environment import TaskEnvironment, TouchscreenEnvironment
from tasks.steering import SteeringTask
from tasks.visual_search import VisualSearchTask


def test_steering_tc3_explicitly_passes_through_a() -> None:
    environment = TaskEnvironment()
    driver = DriverModel()
    task = SteeringTask(driver.network, environment)
    driver.register_task("steering", task)
    task.submit_visual_angles(0.1, 0.05, 0.0)
    driver.drain()

    assert len(task.tc_entities["TC3"]) == 1
    tc3 = task.tc_entities["TC3"][0]
    assert any(
        event.operator == "RETRIEVE_FROM_STM"
        and event.server == "A"
        and event.event == "service_started"
        for event in tc3.history
    )
    assert task.cycles_completed == 1


def test_visual_arrivals_are_separate_from_tc6_loop_control() -> None:
    environment = TaskEnvironment()
    driver = DriverModel()
    task = SteeringTask(driver.network, environment)
    driver.register_task("steering", task)

    task.submit_visual_angles(0.1, 0.05, 0.00)
    task.submit_visual_angles(0.1, 0.05, 0.05)
    task.submit_visual_angles(0.1, 0.05, 0.10)
    assert task.pending_stimulus_count == 2
    driver.drain()

    assert task.cycles_completed == 3
    assert len(task.tc_entities["TC6"]) == 3
    assert all(
        any(
            event.operator == "GOTO"
            and event.event == "operator_completed"
            for event in entity.history
        )
        for entity in task.tc_entities["TC6"]
    )


def test_registered_tasks_share_exact_server_instances() -> None:
    rng = np.random.default_rng(7)
    environment = TaskEnvironment(
        touchscreen=TouchscreenEnvironment.create("2x2", "small", rng)
    )
    driver = DriverModel()
    steering = SteeringTask(driver.network, environment)
    search = VisualSearchTask(environment, rng, driver.network)
    driver.register_task("steering", steering)
    driver.register_task("visual_search", search)

    assert steering.network.servers["C"] is search.network.servers["C"]
    assert steering.network.servers["A"] is search.network.servers["A"]
