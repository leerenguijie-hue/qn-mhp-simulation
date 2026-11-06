"""Task-independent discrete-event QN-MHP machinery (Figure 4d).

This module deliberately knows nothing about roads, vehicles, buttons, or task
components.  Task modules create information entities and activate registered
operators; servers own the shared FIFO queues on which those entities compete.
"""
from __future__ import annotations

import heapq
from collections import deque
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from itertools import count
from typing import Any

OperatorCallback = Callable[["Entity", float], None]
DemandRule = Callable[[str, "Entity", Mapping[str, Any]], float]

_ENTITY_IDS = count(1)


def _new_entity_id() -> str:
    return f"entity-{next(_ENTITY_IDS):08d}"


@dataclass(frozen=True)
class HistoryEvent:
    """One timestamped event in an entity's queue-network history."""

    event: str
    timestamp: float
    operator: str
    server: str | None = None


@dataclass(kw_only=True)
class Entity:
    """Information item flowing through the QN-MHP network."""

    task: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    birth_time: float = 0.0
    parent_entity_id: str | None = None
    entity_id: str = field(default_factory=_new_entity_id)
    history: list[HistoryEvent] = field(default_factory=list)

    def derive(
        self,
        *,
        kind: str,
        birth_time: float,
        payload: Mapping[str, Any] | None = None,
        task: str | None = None,
    ) -> Entity:
        """Create a child entity while preserving explicit data lineage."""
        return Entity(
            task=task or self.task,
            kind=kind,
            payload=dict(payload or {}),
            birth_time=birth_time,
            parent_entity_id=self.entity_id,
        )

    def record(
        self,
        event: str,
        timestamp: float,
        operator: str,
        server: str | None = None,
    ) -> None:
        """Append an immutable processing-history event."""
        self.history.append(
            HistoryEvent(
                event=event,
                timestamp=float(timestamp),
                operator=operator,
                server=server,
            )
        )


@dataclass(frozen=True)
class OperatorSpec:
    """Route and server-specific service demand for one QN-MHP operator."""

    name: str
    route: tuple[str, ...] | list[str]
    service_demand_by_server: Mapping[str, float] = field(default_factory=dict)
    service_demand_rule: DemandRule | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "route", tuple(self.route))
        unknown = set(self.service_demand_by_server).difference(self.route)
        if unknown:
            raise ValueError(
                f"{self.name}: service demand provided for servers outside route: "
                f"{sorted(unknown)}"
            )
        if any(value < 0 for value in self.service_demand_by_server.values()):
            raise ValueError(f"{self.name}: service demand cannot be negative")

    def service_demand(
        self,
        server_name: str,
        entity: Entity,
        parameters: Mapping[str, Any],
    ) -> float:
        """Return this operator's additional demand at one server."""
        demand = float(self.service_demand_by_server.get(server_name, 0.0))
        if self.service_demand_rule is not None:
            demand += float(
                self.service_demand_rule(server_name, entity, parameters)
            )
        if demand < 0:
            raise ValueError(
                f"{self.name}: computed negative demand for {server_name}"
            )
        return demand


@dataclass(frozen=True)
class ServerSpec:
    """Configuration for one shared QN-MHP server."""

    name: str
    capacity: int = 1
    default_service_time: float = 0.0

    def __post_init__(self) -> None:
        if self.capacity < 1:
            raise ValueError("Server capacity must be at least one")
        if self.default_service_time < 0:
            raise ValueError("Server service time cannot be negative")


@dataclass
class _ServiceRequest:
    request_id: int
    entity: Entity
    operator: OperatorSpec
    additional_demand: float
    entered_at: float
    on_complete: OperatorCallback
    schedule: Callable[[float, Callable[[], None]], None]


class Server:
    """Capacity-limited server with an explicit FIFO waiting queue."""

    def __init__(
        self,
        name: str,
        *,
        capacity: int = 1,
        default_service_time: float = 0.0,
    ) -> None:
        if capacity < 1:
            raise ValueError("Server capacity must be at least one")
        if default_service_time < 0:
            raise ValueError("Server service time cannot be negative")
        self.name = name
        self.capacity = capacity
        self.default_service_time = float(default_service_time)
        self.queue: deque[_ServiceRequest] = deque()
        self._active: dict[int, _ServiceRequest] = {}

    @property
    def busy(self) -> bool:
        """Whether at least one service slot is occupied."""
        return bool(self._active)

    @property
    def current_service(self) -> Entity | None:
        """Current entity for capacity-one inspection; first entity otherwise."""
        if not self._active:
            return None
        first_request = next(iter(self._active.values()))
        return first_request.entity

    @property
    def queue_length(self) -> int:
        """Number of entities waiting, excluding active service."""
        return len(self.queue)

    def request_service(self, request: _ServiceRequest, at_time: float) -> None:
        """Enter the FIFO and start immediately when capacity is available."""
        request.entity.record(
            "server_entered",
            at_time,
            request.operator.name,
            self.name,
        )
        if len(self._active) < self.capacity:
            self._start(request, at_time)
        else:
            self.queue.append(request)

    def _start(self, request: _ServiceRequest, at_time: float) -> None:
        self._active[request.request_id] = request
        request.entity.record(
            "service_started",
            at_time,
            request.operator.name,
            self.name,
        )
        duration = self.default_service_time + request.additional_demand
        request.schedule(
            at_time + duration,
            lambda: self._complete(request.request_id, at_time + duration),
        )

    def _complete(self, request_id: int, at_time: float) -> None:
        request = self._active.pop(request_id)
        request.entity.record(
            "service_completed",
            at_time,
            request.operator.name,
            self.name,
        )

        # Existing waiters get the newly free slot before a completion callback
        # can submit fresh work at the same timestamp.
        while self.queue and len(self._active) < self.capacity:
            self._start(self.queue.popleft(), at_time)
        request.on_complete(request.entity, at_time)


@dataclass(order=True)
class _ScheduledEvent:
    timestamp: float
    sequence: int
    callback: Callable[[], None] = field(compare=False)


class QueueNetwork:
    """Discrete-event executor with queues owned by shared server instances."""

    def __init__(
        self,
        server_specs: Iterable[ServerSpec],
        operator_specs: Iterable[OperatorSpec] = (),
    ) -> None:
        specs = list(server_specs)
        if len({spec.name for spec in specs}) != len(specs):
            raise ValueError("Server names must be unique")
        self.servers = {
            spec.name: Server(
                spec.name,
                capacity=spec.capacity,
                default_service_time=spec.default_service_time,
            )
            for spec in specs
        }
        self.operators: dict[str, OperatorSpec] = {}
        for spec in operator_specs:
            self.register_operator(spec)
        self.time = 0.0
        self.entities: dict[str, Entity] = {}
        self._event_heap: list[_ScheduledEvent] = []
        self._sequence = 0

    @property
    def has_pending_events(self) -> bool:
        """Whether the event calendar contains unprocessed work."""
        return bool(self._event_heap)

    def register_operator(self, spec: OperatorSpec) -> None:
        """Register one operator after validating its server route."""
        if spec.name in self.operators:
            raise ValueError(f"Operator {spec.name!r} is already registered")
        missing = set(spec.route).difference(self.servers)
        if missing:
            raise KeyError(
                f"{spec.name}: route references unknown servers {sorted(missing)}"
            )
        self.operators[spec.name] = spec

    def schedule_callback(
        self,
        timestamp: float,
        callback: Callable[[], None],
    ) -> None:
        """Schedule a task-independent callback on the event calendar."""
        if timestamp < self.time:
            raise ValueError("Cannot schedule an event in the past")
        self._sequence += 1
        heapq.heappush(
            self._event_heap,
            _ScheduledEvent(float(timestamp), self._sequence, callback),
        )

    def submit(
        self,
        operator: str | OperatorSpec,
        entity: Entity,
        on_complete: OperatorCallback,
        *,
        start_time: float | None = None,
        parameters: Mapping[str, Any] | None = None,
    ) -> None:
        """Activate an operator and route its entity through shared servers."""
        spec = self.operators[operator] if isinstance(operator, str) else operator
        if isinstance(operator, OperatorSpec) and operator.name not in self.operators:
            raise KeyError(f"Operator {operator.name!r} is not registered")
        at_time = self.time if start_time is None else float(start_time)
        if at_time < self.time:
            raise ValueError("Operator cannot start before network time")
        parameter_values = dict(parameters or {})
        self.entities[entity.entity_id] = entity

        def activate() -> None:
            entity.record("operator_activated", at_time, spec.name)
            self._enter_route(
                spec,
                entity,
                0,
                at_time,
                parameter_values,
                on_complete,
            )

        if at_time == self.time:
            activate()
        else:
            self.schedule_callback(at_time, activate)

    def _enter_route(
        self,
        spec: OperatorSpec,
        entity: Entity,
        route_index: int,
        at_time: float,
        parameters: Mapping[str, Any],
        on_complete: OperatorCallback,
    ) -> None:
        if route_index >= len(spec.route):
            entity.record("operator_completed", at_time, spec.name)
            on_complete(entity, at_time)
            return

        server_name = spec.route[route_index]
        server = self.servers[server_name]
        self._sequence += 1
        request = _ServiceRequest(
            request_id=self._sequence,
            entity=entity,
            operator=spec,
            additional_demand=spec.service_demand(
                server_name,
                entity,
                parameters,
            ),
            entered_at=at_time,
            on_complete=lambda completed, completed_at: self._enter_route(
                spec,
                completed,
                route_index + 1,
                completed_at,
                parameters,
                on_complete,
            ),
            schedule=self.schedule_callback,
        )
        server.request_service(request, at_time)

    def process_until(self, target_time: float) -> float:
        """Process every event due at or before ``target_time``."""
        if target_time < self.time:
            raise ValueError("target_time cannot be earlier than network time")
        while self._event_heap and self._event_heap[0].timestamp <= target_time:
            event = heapq.heappop(self._event_heap)
            self.time = event.timestamp
            event.callback()
        self.time = float(target_time)
        return self.time

    def drain(self) -> float:
        """Process events until the event calendar is empty."""
        while self._event_heap:
            event = heapq.heappop(self._event_heap)
            self.time = event.timestamp
            event.callback()
        return self.time
