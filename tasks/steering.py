"""Figure 6 steering Task Components TC1–TC6."""
from __future__ import annotations

import math
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

from cognitive_architecture import Entity, QueueNetwork
from model_config import SteeringConfig
from task_environment import TaskEnvironment


@dataclass(frozen=True)
class _RoadStimulusPair:
    pair_id: int
    near_angle: float
    far_angle: float
    sample_time: float
    on_cycle_complete: Callable[[float], None] | None = None


class SteeringTask:
    """Run Figure 6 independently of the 50 ms stimulus producer."""

    def __init__(
        self,
        network: QueueNetwork,
        environment: TaskEnvironment,
        config: SteeringConfig | None = None,
    ) -> None:
        self.network = network
        self.environment = environment
        self.config = config or SteeringConfig()
        self.steering_angle = 0.0
        self.previous_control: tuple[float, float, float] | None = None
        self.cycles_completed = 0
        self.tc_activation_log: list[tuple[str, str, float, str]] = []
        self.tc_entities: dict[str, list[Entity]] = {
            f"TC{number}": [] for number in range(1, 7)
        }

        self._stimuli: deque[_RoadStimulusPair] = deque()
        self._active_pair: _RoadStimulusPair | None = None
        self._next_pair_id = 1
        self._stm: dict[int, dict[str, Entity]] = {}
        self._retrieve_started: set[int] = set()

    @property
    def is_idle(self) -> bool:
        """Whether no steering cycle is active."""
        return self._active_pair is None

    @property
    def pending_stimulus_count(self) -> int:
        """Number of environmental pairs awaiting TC1."""
        return len(self._stimuli)

    def _activate(
        self,
        tc: str,
        operator: str,
        entity: Entity,
        callback: Callable[[Entity, float], None],
        at_time: float,
    ) -> None:
        self.tc_activation_log.append(
            (tc, operator, float(at_time), entity.entity_id)
        )
        self.tc_entities[tc].append(entity)
        self.network.submit(
            operator,
            entity,
            callback,
            start_time=at_time,
        )

    def submit_visual_angles(
        self,
        near_angle: float,
        far_angle: float,
        sample_time: float,
        on_cycle_complete: Callable[[float], None] | None = None,
    ) -> int:
        """Queue one external 50 ms road stimulus independently of TC6."""
        pair = _RoadStimulusPair(
            pair_id=self._next_pair_id,
            near_angle=float(near_angle),
            far_angle=float(far_angle),
            sample_time=float(sample_time),
            on_cycle_complete=on_cycle_complete,
        )
        self._next_pair_id += 1
        self._stimuli.append(pair)
        if self._active_pair is None:
            self._start_next_cycle(max(self.network.time, sample_time))
        return pair.pair_id

    def _start_next_cycle(self, at_time: float) -> None:
        if self._active_pair is not None:
            return
        if not self._stimuli:
            self._active_pair = None
            return
        pair = self._stimuli.popleft()
        self._active_pair = pair
        self._stm[pair.pair_id] = {}
        self._tc1_look_at("near", pair.near_angle, pair, at_time)
        self._tc1_look_at("far", pair.far_angle, pair, at_time)

    def _tc1_look_at(
        self,
        angle_kind: str,
        value: float,
        pair: _RoadStimulusPair,
        at_time: float,
    ) -> None:
        """TC1 activation: LOOK_AT one near/far road-angle stimulus."""
        external = Entity(
            task="steering",
            kind="road_visual_stimulus",
            payload={
                "pair_id": pair.pair_id,
                "angle_kind": angle_kind,
                "value": value,
                "sample_time": pair.sample_time,
            },
            birth_time=pair.sample_time,
        )
        self._activate(
            "TC1",
            "LOOK_AT",
            external,
            self._look_at_completed,
            at_time,
        )

    def _look_at_completed(
        self,
        external: Entity,
        completed_at: float,
    ) -> None:
        """TC1 completion: produce a perceived road-angle entity."""
        perceived = external.derive(
            kind="perceived_road_angle",
            payload=external.payload,
            birth_time=completed_at,
        )
        self._tc2_store_to_stm(perceived, completed_at)

    def _tc2_store_to_stm(
        self,
        perceived: Entity,
        at_time: float,
    ) -> None:
        """TC2 activation: send the perceived angle to A."""
        self._activate(
            "TC2",
            "STORE_TO_STM",
            perceived,
            self._store_to_stm_completed,
            at_time,
        )

    def _store_to_stm_completed(
        self,
        perceived: Entity,
        completed_at: float,
    ) -> None:
        """TC2 completion: commit and pair near/far entities at A."""
        pair_id = int(perceived.payload["pair_id"])
        angle_kind = str(perceived.payload["angle_kind"])
        stored = perceived.derive(
            kind="stored_road_angle",
            payload=perceived.payload,
            birth_time=completed_at,
        )
        self._stm[pair_id][angle_kind] = stored
        if (
            set(self._stm[pair_id]) == {"near", "far"}
            and pair_id not in self._retrieve_started
        ):
            self._retrieve_started.add(pair_id)
            self._tc3_retrieve_from_stm(pair_id, completed_at)

    def _tc3_retrieve_from_stm(
        self,
        pair_id: int,
        at_time: float,
    ) -> None:
        """TC3 activation: explicitly retrieve the paired values through A."""
        near = self._stm[pair_id]["near"]
        far = self._stm[pair_id]["far"]
        request = near.derive(
            kind="steering_memory_retrieval_request",
            payload={
                "pair_id": pair_id,
                "near_entity_id": near.entity_id,
                "far_entity_id": far.entity_id,
            },
            birth_time=at_time,
        )
        self._activate(
            "TC3",
            "RETRIEVE_FROM_STM",
            request,
            self._retrieve_from_stm_completed,
            at_time,
        )

    def _retrieve_from_stm_completed(
        self,
        request: Entity,
        completed_at: float,
    ) -> None:
        """TC3 completion: produce one retrieved near/far pair."""
        pair_id = int(request.payload["pair_id"])
        values = self._stm[pair_id]
        near = values["near"]
        far = values["far"]
        retrieved = request.derive(
            kind="retrieved_road_angle_pair",
            payload={
                "pair_id": pair_id,
                "near_angle": float(near.payload["value"]),
                "far_angle": float(far.payload["value"]),
                "sample_time": max(
                    float(near.payload["sample_time"]),
                    float(far.payload["sample_time"]),
                ),
                "source_entity_ids": (
                    near.entity_id,
                    far.entity_id,
                ),
            },
            birth_time=completed_at,
        )
        self._tc4_determine_steering(retrieved, completed_at)

    def _tc4_determine_steering(
        self,
        retrieved: Entity,
        at_time: float,
    ) -> None:
        """TC4 activation: invoke the Salvucci steering computation on C."""
        self._activate(
            "TC4",
            "DETERMINE_STEERING",
            retrieved,
            self._determine_steering_completed,
            at_time,
        )

    def _determine_steering_completed(
        self,
        retrieved: Entity,
        completed_at: float,
    ) -> None:
        """TC4 completion: calculate and emit the steering adjustment."""
        near_now = float(retrieved.payload["near_angle"])
        far_now = float(retrieved.payload["far_angle"])
        sample_time = float(retrieved.payload["sample_time"])
        if self.previous_control is None:
            near_delta = 0.0
            far_delta = 0.0
            elapsed = self.config.visual_interval_s
        else:
            previous_near, previous_far, previous_time = self.previous_control
            near_delta = near_now - previous_near
            far_delta = far_now - previous_far
            elapsed = max(
                self.config.visual_interval_s,
                sample_time - previous_time,
            )

        cap = math.radians(self.config.near_angle_cap_deg)
        # Symmetric clipping is an explicit executable interpretation; Feng
        # reports min(theta_near, theta_nmax) without a negative-side rule.
        limited_near = max(-cap, min(cap, near_now))
        adjustment = (
            self.config.k_far * far_delta
            + self.config.k_near * near_delta
            + self.config.k_integral * limited_near * elapsed
        )
        self.previous_control = (near_now, far_now, sample_time)
        determined = retrieved.derive(
            kind="steering_adjustment",
            payload={
                **retrieved.payload,
                "adjustment_angle": adjustment,
            },
            birth_time=completed_at,
        )
        self._tc5_turn_steering(determined, completed_at)

    def _tc5_turn_steering(
        self,
        determined: Entity,
        at_time: float,
    ) -> None:
        """TC5 activation: route the adjustment through W→Y→Z."""
        self._activate(
            "TC5",
            "TURN_STEERING",
            determined,
            self._turn_steering_completed,
            at_time,
        )

    def _turn_steering_completed(
        self,
        determined: Entity,
        completed_at: float,
    ) -> None:
        """TC5 completion: commit the steering action to the environment."""
        limit = math.radians(self.config.maximum_steering_angle_deg)
        requested = self.steering_angle + float(
            determined.payload["adjustment_angle"]
        )
        self.steering_angle = max(-limit, min(limit, requested))
        self.environment.receive_steering(
            self.steering_angle,
            completed_at,
        )
        executed = determined.derive(
            kind="executed_steering",
            payload={
                **determined.payload,
                "steering_angle": self.steering_angle,
            },
            birth_time=completed_at,
        )
        self._tc6_goto(executed, completed_at)

    def _tc6_goto(self, executed: Entity, at_time: float) -> None:
        """TC6 activation: explicit task-program loop control."""
        self._activate(
            "TC6",
            "GOTO",
            executed,
            self._goto_completed,
            at_time,
        )

    def _goto_completed(
        self,
        _executed: Entity,
        completed_at: float,
    ) -> None:
        """TC6 completion: finish this cycle, then consume the next stimulus."""
        pair = self._active_pair
        if pair is None:
            raise RuntimeError("TC6 completed without an active stimulus pair")
        self.cycles_completed += 1
        self._active_pair = None
        if pair.on_cycle_complete is not None:
            pair.on_cycle_complete(completed_at)
        self._start_next_cycle(completed_at)
