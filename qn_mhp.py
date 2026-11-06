"""A minimal, synchronous QN-MHP visual-search model."""
from __future__ import annotations

import math
import random
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

# Capacity 4 is paper-derived. All times below are reconstructed defaults.
RECOGNITION_CAPACITY = 4
DEFAULT_SERVICE_S = 0.005
SACCADE_DEMAND_S = 0.050

ROUTES = {
    "LOOK_AT": ("1", "2/3", "4"),
    "STORE_TO_STM": ("A",),
    "RETRIEVE_FROM_STM": ("A",),
    "COMPARE": ("C",),
    "GOTO": (),
    "VISUAL_SEARCH": ("C",),
    "REACH_WITH_HAND": ("W", "Y", "Z"),
    "CLICK_WITH_FINGER": ("W", "Y", "Z"),
    "GOAL_ACCOMPLISHED": (),
}

DEMANDS = {
    "LOOK_AT": {"1": 0.017, "2/3": 0.017, "4": 0.021},
    "STORE_TO_STM": {"A": 0.009},
    "RETRIEVE_FROM_STM": {"A": 0.009},
    "COMPARE": {"C": 0.017},
    "VISUAL_SEARCH": {"C": 0.017},
    "REACH_WITH_HAND": {"W": 0.005, "Y": 0.005, "Z": 0.005},
    "CLICK_WITH_FINGER": {"W": 0.005, "Y": 0.005, "Z": 0.005},
}


@dataclass(frozen=True)
class Visit:
    """One server visit."""

    entity_id: str
    operator: str
    server: str
    arrival: float
    start: float
    finish: float

    @property
    def wait(self) -> float:
        return self.start - self.arrival


@dataclass
class Entity:
    """One information entity and its lineage."""

    entity_id: str
    kind: str
    payload: dict[str, Any]
    birth_time: float
    parent_entity_id: str | None = None
    visits: list[Visit] = field(default_factory=list)


@dataclass(frozen=True)
class OperatorSpec:
    """One operator's server route and demands."""

    name: str
    route: tuple[str, ...]
    demand: dict[str, float]


@dataclass
class Server:
    """A capacity-limited server that returns a completion time."""

    name: str
    capacity: int = 1
    service_time: float = DEFAULT_SERVICE_S
    visits: list[Visit] = field(default_factory=list)
    _available: list[float] = field(init=False, repr=False)
    _last_arrival: float = field(default=-math.inf, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.capacity < 1:
            raise ValueError("capacity must be >= 1")
        self._available = [0.0] * self.capacity

    def process(
        self,
        entity: Entity,
        operator: str,
        arrival: float,
        demand: float,
    ) -> float:
        """Return finish time; equal-time arrivals are FIFO by call order."""
        if arrival < self._last_arrival:
            raise ValueError("submit arrivals chronologically")
        self._last_arrival = arrival
        slot = min(
            range(self.capacity),
            key=lambda index: (self._available[index], index),
        )
        start = max(arrival, self._available[slot])
        finish = start + self.service_time + demand
        self._available[slot] = finish
        visit = Visit(entity.entity_id, operator, self.name, arrival, start, finish)
        self.visits.append(visit)
        entity.visits.append(visit)
        return finish


class QueueNetwork:
    """Shared servers with a synchronous ``process`` method."""

    def __init__(self) -> None:
        self.servers = {
            name: Server(
                name,
                capacity=RECOGNITION_CAPACITY if name == "4" else 1,
            )
            for name in ("1", "2/3", "4", "A", "C", "W", "Y", "Z")
        }
        self.operators = {
            name: OperatorSpec(name, route, DEMANDS.get(name, {}))
            for name, route in ROUTES.items()
        }
        self.entities: list[Entity] = []
        self.server_trace: list[Visit] = []
        self.time = 0.0
        self._next_id = 1

    def entity(
        self,
        kind: str,
        payload: dict[str, Any],
        time: float,
        parent: Entity | None = None,
    ) -> Entity:
        entity = Entity(
            entity_id=f"E{self._next_id:03d}",
            parent_entity_id=parent.entity_id if parent else None,
            kind=kind,
            payload=dict(payload),
            birth_time=time,
        )
        self._next_id += 1
        self.entities.append(entity)
        return entity

    def process(
        self,
        operator_name: str,
        entity: Entity,
        time: float,
        extra: dict[str, float] | None = None,
    ) -> float:
        """Run the route now and return its simulated completion time."""
        spec = self.operators[operator_name]
        current = time
        for server_name in spec.route:
            server = self.servers[server_name]
            current = server.process(
                entity,
                spec.name,
                current,
                spec.demand.get(server_name, 0.0)
                + (extra or {}).get(server_name, 0.0),
            )
            self.server_trace.append(server.visits[-1])
        self.time = max(self.time, current)
        return current


@dataclass(frozen=True)
class TCRecord:
    tc: str
    operator: str
    input_id: str
    output_id: str
    start: float
    finish: float
    result: str = ""


@dataclass(frozen=True)
class TrialResult:
    completion_time_s: float
    clicked_index: int
    examined_indices: tuple[int, ...]
    tc_trace: tuple[TCRecord, ...]
    entities: tuple[Entity, ...]
    server_trace: tuple[Visit, ...]

    def to_dict(self) -> dict[str, Any]:
        """Return JSON-ready results."""
        return {
            "completion_time_s": self.completion_time_s,
            "clicked_index": self.clicked_index,
            "examined_indices": list(self.examined_indices),
            "tc_trace": [asdict(item) for item in self.tc_trace],
            "entities": [
                {
                    "entity_id": item.entity_id,
                    "parent_entity_id": item.parent_entity_id,
                    "kind": item.kind,
                    "payload": item.payload,
                    "birth_time": item.birth_time,
                }
                for item in self.entities
            ],
            "server_trace": [
                {**asdict(item), "wait": item.wait}
                for item in self.server_trace
            ],
        }


class VisualSearchModel:
    """TC1–TC9 with ordinary arguments and return values."""

    def __init__(
        self,
        labels: Sequence[str],
        target: str = "USB",
        seed: int = 2,
    ) -> None:
        if sum(label == target for label in labels) != 1:
            raise ValueError("Exactly one target button is required")
        columns = math.ceil(math.sqrt(len(labels)))
        self.buttons = [
            {
                "button_index": index,
                "label": label,
                "location": ((index % columns) * 110.0, (index // columns) * 110.0),
                "width": 100.0,
            }
            for index, label in enumerate(labels)
        ]
        self.target = target
        self.rng = random.Random(seed)
        self.qn = QueueNetwork()
        self.examined: set[int] = set()
        self.attention: list[int] = []
        self.focus = 0
        self.stm: Entity | None = None
        self.trace: list[TCRecord] = []

    def _output(
        self,
        tc: str,
        operator: str,
        input_entity: Entity,
        output_kind: str,
        output_payload: dict[str, Any],
        time: float,
        *,
        result: str = "",
        extra: dict[str, float] | None = None,
    ) -> tuple[Entity, float]:
        finish = self.qn.process(operator, input_entity, time, extra)
        output = self.qn.entity(
            output_kind,
            output_payload,
            finish,
            parent=input_entity,
        )
        self.trace.append(
            TCRecord(
                tc,
                operator,
                input_entity.entity_id,
                output.entity_id,
                time,
                finish,
                result,
            )
        )
        return output, finish

    def _attention(self, focus: int) -> list[int]:
        x, y = self.buttons[focus]["location"]
        ordered = sorted(
            self.buttons,
            key=lambda item: (
                math.hypot(item["location"][0] - x, item["location"][1] - y),
                item["button_index"],
            ),
        )
        return [
            int(item["button_index"])
            for item in ordered[:RECOGNITION_CAPACITY]
        ]

    def tc1(
        self,
        time: float,
        parent: Entity | None,
    ) -> tuple[Entity, float]:
        stimulus = self.qn.entity(
            "visual_stimulus",
            self.buttons[self.focus],
            time,
            parent,
        )
        return self._output(
            "TC1", "LOOK_AT", stimulus, "perceived_button", stimulus.payload, time
        )

    def tc2(self, perceived: Entity, time: float) -> tuple[Entity, float]:
        stored, finish = self._output(
            "TC2",
            "STORE_TO_STM",
            perceived,
            "stored_button",
            perceived.payload,
            time,
        )
        self.stm = stored
        return stored, finish

    def tc3(self, stored: Entity, time: float) -> tuple[Entity, float]:
        request = self.qn.entity("memory_request", {"slot": "button"}, time, stored)
        if self.stm is None:
            raise RuntimeError("STM is empty")
        return self._output(
            "TC3",
            "RETRIEVE_FROM_STM",
            request,
            "retrieved_button",
            self.stm.payload,
            time,
        )

    def tc4(self, retrieved: Entity, time: float) -> tuple[Entity, float]:
        match = retrieved.payload["label"] == self.target
        comparison, finish = self._output(
            "TC4",
            "COMPARE",
            retrieved,
            "comparison",
            {**retrieved.payload, "match": match},
            time,
            result="match" if match else "mismatch",
        )
        self.examined.add(int(retrieved.payload["button_index"]))
        return comparison, finish

    def tc5(self, comparison: Entity, time: float) -> tuple[bool, float]:
        finish = self.qn.process("GOTO", comparison, time)
        match = bool(comparison.payload["match"])
        self.trace.append(
            TCRecord(
                "TC5",
                "GOTO",
                comparison.entity_id,
                comparison.entity_id,
                time,
                finish,
                "TC7" if match else "TC6",
            )
        )
        return match, finish

    def tc6(self, comparison: Entity, time: float) -> tuple[Entity, float]:
        local = [index for index in self.attention if index not in self.examined]
        if local:
            next_focus, saccade = local[0], False
        else:
            remaining = [
                int(item["button_index"])
                for item in self.buttons
                if item["button_index"] not in self.examined
            ]
            next_focus, saccade = self.rng.choice(remaining), True
        selection = self.qn.entity(
            "search_selection",
            {"button_index": next_focus, "needs_saccade": saccade},
            time,
            comparison,
        )
        focus, finish = self._output(
            "TC6",
            "VISUAL_SEARCH",
            selection,
            "focus",
            selection.payload,
            time,
            result=f"focus={next_focus}",
            extra={"C": SACCADE_DEMAND_S} if saccade else None,
        )
        self.focus = next_focus
        if saccade:
            self.attention = self._attention(next_focus)
        return focus, finish

    def tc7(self, comparison: Entity, time: float) -> tuple[Entity, float]:
        return self._output(
            "TC7",
            "REACH_WITH_HAND",
            comparison,
            "reached_target",
            comparison.payload,
            time,
        )

    def tc8(self, reached: Entity, time: float) -> tuple[Entity, float]:
        return self._output(
            "TC8",
            "CLICK_WITH_FINGER",
            reached,
            "clicked_target",
            reached.payload,
            time,
        )

    def tc9(self, clicked: Entity, time: float) -> tuple[Entity, float]:
        return self._output(
            "TC9",
            "GOAL_ACCOMPLISHED",
            clicked,
            "done",
            {"clicked_index": clicked.payload["button_index"]},
            time,
        )

    def run(self) -> TrialResult:
        time = 0.0
        self.focus = self.rng.randrange(len(self.buttons))
        self.attention = self._attention(self.focus)
        focus_entity: Entity | None = None

        while True:
            perceived, time = self.tc1(time, focus_entity)
            stored, time = self.tc2(perceived, time)
            retrieved, time = self.tc3(stored, time)
            comparison, time = self.tc4(retrieved, time)
            match, time = self.tc5(comparison, time)
            if not match:
                focus_entity, time = self.tc6(comparison, time)
                continue
            reached, time = self.tc7(comparison, time)
            clicked, time = self.tc8(reached, time)
            done, time = self.tc9(clicked, time)
            return TrialResult(
                time,
                int(done.payload["clicked_index"]),
                tuple(sorted(self.examined)),
                tuple(self.trace),
                tuple(self.qn.entities),
                tuple(self.qn.server_trace),
            )


def run_visual_search(
    labels: Sequence[str],
    target_label: str = "USB",
    seed: int = 2,
) -> TrialResult:
    """Public API: button labels in, complete TC1–TC9 result out."""
    return VisualSearchModel(labels, target_label, seed).run()
