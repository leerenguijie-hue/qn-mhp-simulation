"""
Shared QN-MHP queue-network primitives (Feng dissertation, Ch. 2 & 4).

Servers are single-server queues with deterministic service times. Operators from the
NGOMSL task analysis route information entities through ordered server chains.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional
import heapq


@dataclass
class Entity:
    """Information entity flowing through the queuing network."""

    kind: str
    payload: Dict[str, Any] = field(default_factory=dict)
    birth_time: float = 0.0


@dataclass
class _ScheduledCompletion:
    finish_time: float
    seq: int
    server_name: str
    entity: Entity
    on_complete: Callable[[Entity, float], None]


class Server:
    """Single-server queue; one entity in service at a time."""

    def __init__(self, name: str, base_service: float):
        self.name = name
        self.base_service = base_service
        self.queue: deque = deque()
        self.busy_until = 0.0
        self._in_service: Optional[Entity] = None

    def extra_service(self, entity: Entity) -> float:
        """Hook for entity-dependent service (e.g. recognition load)."""
        return float(entity.payload.get("extra_service", 0.0))

    def request_service(
        self,
        entity: Entity,
        at_time: float,
        on_complete: Callable[[Entity, float], None],
        schedule: Callable[[_ScheduledCompletion], None],
        seq: int,
    ) -> None:
        start = max(at_time, self.busy_until)
        duration = self.base_service + self.extra_service(entity)
        finish = start + duration
        self.busy_until = finish
        self._in_service = entity
        schedule(
            _ScheduledCompletion(
                finish_time=finish,
                seq=seq,
                server_name=self.name,
                entity=entity,
                on_complete=on_complete,
            )
        )


class QueueNetwork:
    """
    Discrete-event executor for operator → server chains.

    Parallelism: different servers can hold work in overlapping time windows once
    scheduled; Parked visual search activates one operator chain at a time (serial TCs).
    """

    def __init__(self, service_times: Dict[str, float]):
        self.servers = {n: Server(n, t) for n, t in service_times.items()}
        self.time = 0.0
        self._event_heap: List[tuple] = []
        self._seq = 0

    def _push_event(self, completion: _ScheduledCompletion) -> None:
        heapq.heappush(
            self._event_heap,
            (completion.finish_time, completion.seq, completion),
        )

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def run_operator(
        self,
        operator: str,
        entity: Entity,
        route: List[str],
        on_done: Callable[[Entity, float], None],
        *,
        start_time: Optional[float] = None,
    ) -> None:
        """Send one entity through the server list for a QN-MHP operator."""
        if start_time is None:
            start_time = self.time

        if not route:
            on_done(entity, start_time)
            return

        def enter_server(index: int, ent: Entity, t_in: float) -> None:
            if index >= len(route):
                on_done(ent, t_in)
                return
            srv_name = route[index]
            srv = self.servers[srv_name]

            def after_server(completed: Entity, t_out: float) -> None:
                self.time = max(self.time, t_out)
                enter_server(index + 1, completed, t_out)

            srv.request_service(
                ent,
                t_in,
                after_server,
                self._push_event,
                self._next_seq(),
            )

        enter_server(0, entity, start_time)

    def drain(self) -> float:
        """Process all scheduled completions; return final simulation time."""
        while self._event_heap:
            finish, _, comp = heapq.heappop(self._event_heap)
            self.time = max(self.time, finish)
            comp.on_complete(comp.entity, finish)
        return self.time


# NGOMSL operator → ordered servers (dissertation Ch. 2 steering + Ch. 4 search).
# Procedural operators (GOTO, GOAL_ACCOMPLISHED) have empty routes = zero service time.
OPERATOR_ROUTES: Dict[str, List[str]] = {
    "LOOK_AT": ["1", "2/3", "4"],
    "STORE_TO_STM": ["A"],
    "RETRIEVE_FROM_STM": ["A"],
    "COMPARE": ["C"],
    "GOTO": [],
    "VISUAL_SEARCH": ["C"],
    "REACH_WITH_HAND": ["W", "Y", "Z"],
    "CLICK_WITH_FINGER": ["W", "Y", "Z"],
    "GOAL_ACCOMPLISHED": [],
}
