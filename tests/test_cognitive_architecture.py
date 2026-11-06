"""Unit tests for the task-independent queue network."""
from __future__ import annotations

import pytest

from cognitive_architecture import Entity, OperatorSpec, QueueNetwork, ServerSpec


def _entity(task: str, kind: str = "test") -> Entity:
    return Entity(task=task, kind=kind, birth_time=0.0)


def test_entity_data_lineage_is_explicit() -> None:
    parent = _entity("visual_search", "stimulus")
    child = parent.derive(
        kind="perceived",
        payload={"label": "USB"},
        birth_time=0.1,
    )
    grandchild = child.derive(
        kind="stored",
        payload=child.payload,
        birth_time=0.2,
    )

    assert child.parent_entity_id == parent.entity_id
    assert grandchild.parent_entity_id == child.entity_id
    assert grandchild.payload == {"label": "USB"}


def test_capacity_one_server_is_fifo() -> None:
    network = QueueNetwork(
        [ServerSpec("C")],
        [OperatorSpec("WORK", ("C",), {"C": 0.1})],
    )
    entities = [_entity("task", str(index)) for index in range(3)]
    completed: list[tuple[str, float]] = []
    for entity in entities:
        network.submit(
            "WORK",
            entity,
            lambda item, time: completed.append((item.kind, time)),
        )

    assert network.servers["C"].queue_length == 2
    network.drain()
    assert [kind for kind, _ in completed] == ["0", "1", "2"]
    assert [time for _, time in completed] == pytest.approx([0.1, 0.2, 0.3])


def test_arrivals_above_service_rate_wait_in_server_queue() -> None:
    network = QueueNetwork(
        [ServerSpec("C")],
        [OperatorSpec("WORK", ("C",), {"C": 0.1})],
    )
    for start_time in (0.0, 0.02, 0.04):
        network.submit(
            "WORK",
            _entity("overload"),
            lambda _entity, _time: None,
            start_time=start_time,
        )

    network.process_until(0.04)
    assert network.servers["C"].busy
    assert network.servers["C"].queue_length == 2


def test_different_tasks_compete_on_same_server_c() -> None:
    network = QueueNetwork(
        [ServerSpec("C")],
        [
            OperatorSpec("COMPARE", ("C",), {"C": 0.1}),
            OperatorSpec("DETERMINE_STEERING", ("C",), {"C": 0.1}),
        ],
    )
    completions: list[tuple[str, float]] = []
    visual = _entity("visual_search")
    steering = _entity("steering")
    network.submit(
        "COMPARE",
        visual,
        lambda entity, time: completions.append((entity.task, time)),
    )
    network.submit(
        "DETERMINE_STEERING",
        steering,
        lambda entity, time: completions.append((entity.task, time)),
    )
    network.drain()

    assert completions == [
        ("visual_search", pytest.approx(0.1)),
        ("steering", pytest.approx(0.2)),
    ]
    steering_start = next(
        event.timestamp
        for event in steering.history
        if event.event == "service_started"
    )
    assert steering_start == pytest.approx(0.1)


def test_empty_route_goto_calls_back_immediately() -> None:
    network = QueueNetwork(
        [ServerSpec("C")],
        [OperatorSpec("GOTO", ())],
    )
    entity = _entity("visual_search")
    callbacks: list[float] = []
    network.submit(
        "GOTO",
        entity,
        lambda _entity, time: callbacks.append(time),
    )

    assert callbacks == [0.0]
    assert [event.event for event in entity.history] == [
        "operator_activated",
        "operator_completed",
    ]
    assert network.servers["C"].queue_length == 0


def test_server_four_uses_recognition_capacity_four() -> None:
    from driver_model import DriverModel

    driver = DriverModel()
    assert driver.network.servers["4"].capacity == 4
