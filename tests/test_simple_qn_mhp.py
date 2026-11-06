"""Tests for the minimal return-style QN-MHP model."""
from __future__ import annotations

import pytest

from qn_mhp import (
    Entity,
    QueueNetwork,
    Server,
    VisualSearchModel,
    run_visual_search,
)

LABELS = ["AM1", "FM1", "USB", "DVD", "AM2", "FM2", "MP3", "CD"]


def test_public_api_finds_and_clicks_usb() -> None:
    result = run_visual_search(LABELS, seed=1)

    assert result.clicked_index == LABELS.index("USB")
    assert result.tc_trace[-3].tc == "TC7"
    assert result.tc_trace[-2].tc == "TC8"
    assert result.tc_trace[-1].tc == "TC9"


def test_tc_sequence_is_tc1_to_tc6_until_match_then_tc7_to_tc9() -> None:
    result = run_visual_search(LABELS, seed=2)
    sequence = [record.tc for record in result.tc_trace]

    cursor = 0
    while sequence[cursor : cursor + 6] == [
        "TC1",
        "TC2",
        "TC3",
        "TC4",
        "TC5",
        "TC6",
    ]:
        cursor += 6
    assert sequence[cursor:] == [
        "TC1",
        "TC2",
        "TC3",
        "TC4",
        "TC5",
        "TC7",
        "TC8",
        "TC9",
    ]


def test_each_tc_output_is_the_next_entity_in_the_lineage() -> None:
    result = run_visual_search(LABELS, seed=1)
    entities = {entity.entity_id: entity for entity in result.entities}

    for record in result.tc_trace:
        if record.output_id == record.input_id:
            assert record.tc == "TC5"
        else:
            output = entities[record.output_id]
            assert output.parent_entity_id == record.input_id


def test_tc6_always_visits_server_c() -> None:
    result = run_visual_search(LABELS, seed=2)
    tc6_inputs = {
        record.input_id
        for record in result.tc_trace
        if record.tc == "TC6"
    }
    visits = {
        visit.entity_id
        for visit in result.server_trace
        if visit.operator == "VISUAL_SEARCH" and visit.server == "C"
    }

    assert tc6_inputs
    assert tc6_inputs == visits


def test_capacity_one_server_processes_equal_arrivals_fifo() -> None:
    network = QueueNetwork()
    first = network.entity("first", {}, 0.0)
    second = network.entity("second", {}, 0.0)

    first_finish = network.process("COMPARE", first, 0.0)
    second_finish = network.process("COMPARE", second, 0.0)
    second_visit = second.visits[0]

    assert second_visit.start == pytest.approx(first_finish)
    assert second_visit.wait > 0
    assert second_finish > first_finish


def test_capacity_four_server_starts_four_entities_together() -> None:
    server = Server("4", capacity=4, service_time=0.01)
    entities = [
        Entity(f"E{index}", "object", {}, 0.0)
        for index in range(5)
    ]
    finishes = [
        server.process(entity, "LOOK_AT", 0.0, 0.0)
        for entity in entities
    ]

    assert [visit.start for visit in server.visits[:4]] == [0.0] * 4
    assert server.visits[4].start == pytest.approx(0.01)
    assert finishes[4] == pytest.approx(0.02)


def test_empty_route_goto_returns_same_time() -> None:
    network = QueueNetwork()
    entity = network.entity("comparison", {"match": False}, 1.25)

    completed_at = network.process("GOTO", entity, 1.25)

    assert completed_at == 1.25
    assert entity.visits == []


def test_perfect_search_memory_has_no_duplicate_examined_indices() -> None:
    result = run_visual_search(LABELS, seed=4)

    assert len(result.examined_indices) == len(set(result.examined_indices))
    tc4_count = sum(record.tc == "TC4" for record in result.tc_trace)
    assert tc4_count == len(result.examined_indices)


def test_fixed_seed_is_fully_reproducible() -> None:
    first = run_visual_search(LABELS, seed=91).to_dict()
    second = run_visual_search(LABELS, seed=91).to_dict()

    assert first == second


def test_model_requires_exactly_one_target() -> None:
    with pytest.raises(ValueError, match="Exactly one target"):
        VisualSearchModel(["AM", "FM"], target="USB")
