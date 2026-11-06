"""Tests for Figure 22 visual-search data flow."""
from __future__ import annotations

import math

import numpy as np
import pytest

from driver_model import DriverModel
from experiment_parked import run_all_conditions, simulate_parked_trial
from task_environment import TaskEnvironment, TouchscreenEnvironment
from tasks.visual_search import VisualSearchTask


def _make_task(
    layout: str = "2x2",
    size: str = "medium",
    seed: int = 1,
) -> tuple[VisualSearchTask, DriverModel, TaskEnvironment]:
    rng = np.random.default_rng(seed)
    touchscreen = TouchscreenEnvironment.create(layout, size, rng)
    environment = TaskEnvironment(
        touchscreen=touchscreen,
        gaze_target="device",
    )
    driver = DriverModel()
    task = VisualSearchTask(environment, rng, driver.network)
    driver.register_task("visual_search", task)
    return task, driver, environment


def test_look_output_flows_into_store_without_environment_reread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    task, _driver, environment = _make_task(seed=1)
    touchscreen = environment.touchscreen
    assert touchscreen is not None
    original = touchscreen.visual_stimulus
    calls: list[int] = []

    def counted(index: int):
        calls.append(index)
        return original(index)

    monkeypatch.setattr(touchscreen, "visual_stimulus", counted)
    task.run()

    look_inputs = task.tc_entities["TC1"]
    store_inputs = task.tc_entities["TC2"]
    assert calls == [int(entity.payload["button_index"]) for entity in look_inputs]
    assert len(store_inputs) == len(look_inputs)
    for external, perceived in zip(look_inputs, store_inputs, strict=True):
        assert perceived.parent_entity_id == external.entity_id
        assert perceived.payload == external.payload


def test_stm_is_not_readable_before_store_server_completes() -> None:
    task, driver, _environment = _make_task(seed=1)
    task.start(0.0)

    driver.process_until(0.070)
    assert task._stm == {}
    driver.process_until(0.0839)
    assert task._stm == {}
    driver.process_until(0.0841)
    assert task.MEMORY_SLOT in task._stm


def test_every_tc6_activation_passes_through_server_c() -> None:
    task, _driver, _environment = _make_task(
        layout="3x5",
        size="small",
        seed=1,
    )
    task.run()
    assert task.tc_entities["TC6"]
    for entity in task.tc_entities["TC6"]:
        visits = [
            event
            for event in entity.history
            if event.operator == "VISUAL_SEARCH"
            and event.server == "C"
            and event.event == "service_started"
        ]
        assert len(visits) == 1


def test_look_at_has_no_linear_total_button_penalty() -> None:
    small_task, _driver, _environment = _make_task(layout="2x2", seed=1)
    large_task, _driver2, _environment2 = _make_task(layout="3x5", seed=1)
    small_task.run()
    large_task.run()

    def first_look_duration(task: VisualSearchTask) -> float:
        events = task.tc_entities["TC1"][0].history
        activated = next(
            event.timestamp
            for event in events
            if event.event == "operator_activated"
        )
        completed = next(
            event.timestamp
            for event in events
            if event.event == "operator_completed"
        )
        return completed - activated

    assert first_look_duration(small_task) == pytest.approx(
        first_look_duration(large_task)
    )


def test_all_nine_parked_conditions_run_without_nan() -> None:
    conditions = run_all_conditions(replications=1, base_seed=100)
    assert len(conditions) == 9
    assert all(math.isfinite(item.model_mean_s) for item in conditions)


def test_fixed_seed_reproduces_parked_trial() -> None:
    first = simulate_parked_trial("3x5", "large", 1234)
    second = simulate_parked_trial("3x5", "large", 1234)
    assert first == second
