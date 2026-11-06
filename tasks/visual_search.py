"""Figure 22 visual-search Task Components TC1–TC9."""
from __future__ import annotations

import math
from collections.abc import Callable
from typing import Protocol

import numpy as np

from cognitive_architecture import Entity, QueueNetwork
from model_config import VisualSearchConfig
from task_environment import TaskEnvironment


class VisualSearchMonitor(Protocol):
    """Interface used by Figure 23 without coupling this module to dual_task."""

    def search_started(self, task: VisualSearchTask, at_time: float) -> None:
        """Observe the first off-road glance."""

    def before_visual_search(
        self,
        task: VisualSearchTask,
        comparison: Entity,
        at_time: float,
        resume: Callable[[float], None],
    ) -> None:
        """Continue TC6 now or pause it while a driving cycle runs."""

    def search_completed(self, task: VisualSearchTask, at_time: float) -> None:
        """Close the final off-road glance."""


def _distance(
    first: tuple[float, float],
    second: tuple[float, float],
) -> float:
    return math.hypot(first[0] - second[0], first[1] - second[1])


class VisualSearchTask:
    """Execute Figure 22 while preserving entity flow between every TC."""

    MEMORY_SLOT = "perceived_button"

    def __init__(
        self,
        environment: TaskEnvironment,
        rng: np.random.Generator,
        network: QueueNetwork,
        config: VisualSearchConfig | None = None,
        monitor: VisualSearchMonitor | None = None,
    ) -> None:
        if environment.touchscreen is None:
            raise ValueError("Visual search requires a touchscreen environment")
        self.environment = environment
        self.rng = rng
        self.network = network
        self.config = config or VisualSearchConfig()
        self.monitor = monitor

        self.trial_start = 0.0
        self.completion_at: float | None = None
        self.completion_time: float | None = None
        self.examined: set[int] = set()
        self.focus_index: int | None = None
        self.attention: list[int] = []
        self.gaze = self.config.gaze_start_px
        self.paused_tc: str | None = None
        self.is_paused = False
        self.tc_activation_log: list[tuple[str, str, float, str]] = []
        self.tc_entities: dict[str, list[Entity]] = {
            f"TC{number}": [] for number in range(1, 10)
        }
        self._stm: dict[str, Entity] = {}
        self._started = False

        # TC6 uses only internal spatial state. Labels remain external and are
        # sampled solely by TC1 through environment.visual_stimulus().
        self._geometry = {
            button.index: {
                "location": button.location,
                "width": button.width,
                "height": button.height,
            }
            for button in environment.touchscreen.buttons
        }

    @property
    def checked_button_count(self) -> int:
        """Number of distinct buttons committed as examined after TC4."""
        return len(self.examined)

    def _activate(
        self,
        tc: str,
        operator: str,
        entity: Entity,
        callback: Callable[[Entity, float], None],
        *,
        start_time: float,
        parameters: dict[str, object] | None = None,
    ) -> None:
        self.tc_activation_log.append(
            (tc, operator, float(start_time), entity.entity_id)
        )
        self.tc_entities[tc].append(entity)
        self.network.submit(
            operator,
            entity,
            callback,
            start_time=start_time,
            parameters=parameters,
        )

    def _attention_set(self, focus_index: int) -> list[int]:
        focus_location = self._geometry[focus_index]["location"]
        assert isinstance(focus_location, tuple)
        ordered = sorted(
            self._geometry,
            key=lambda index: _distance(
                self._geometry[index]["location"],  # type: ignore[arg-type]
                focus_location,
            ),
        )
        return ordered[: self.config.recognition_capacity]

    def start(self, start_time: float | None = None) -> None:
        """Initialize one trial and activate TC1."""
        if self._started:
            raise RuntimeError("A VisualSearchTask instance runs one trial")
        self._started = True
        self.trial_start = (
            self.network.time if start_time is None else float(start_time)
        )
        button_count = len(self._geometry)
        self.focus_index = int(self.rng.integers(0, button_count))
        self.attention = self._attention_set(self.focus_index)
        focus_location = self._geometry[self.focus_index]["location"]
        assert isinstance(focus_location, tuple)
        self.gaze = focus_location
        if self.monitor is not None:
            self.monitor.search_started(self, self.trial_start)
        else:
            self.environment.set_gaze("device", self.trial_start)
        self._tc1_look_at(self.trial_start)

    def run(self) -> float:
        """Run a parked trial to completion and return task completion time."""
        self.start()
        self.network.drain()
        if self.completion_time is None:
            raise RuntimeError("Visual search did not complete")
        return self.completion_time

    def _tc1_look_at(self, at_time: float) -> None:
        """TC1 activation: sample the external button and invoke LOOK_AT."""
        if self.focus_index is None:
            raise RuntimeError("Visual focus is not initialized")
        stimulus = self.environment.touchscreen.visual_stimulus(
            self.focus_index
        )
        external = Entity(
            task="visual_search",
            kind="device_visual_stimulus",
            payload={
                "button_index": stimulus.button_index,
                "label": stimulus.label,
                "location": stimulus.location,
                "width": stimulus.width,
                "height": stimulus.height,
            },
            birth_time=at_time,
        )
        self._activate(
            "TC1",
            "LOOK_AT",
            external,
            self._look_at_completed,
            start_time=at_time,
        )

    def _look_at_completed(self, external: Entity, completed_at: float) -> None:
        """TC1 completion: produce the perceived entity for TC2."""
        perceived = external.derive(
            kind="perceived_button",
            payload=external.payload,
            birth_time=completed_at,
        )
        self._tc2_store_to_stm(perceived, completed_at)

    def _tc2_store_to_stm(
        self,
        perceived: Entity,
        at_time: float,
    ) -> None:
        """TC2 activation: send TC1's output to STM server A."""
        self._activate(
            "TC2",
            "STORE_TO_STM",
            perceived,
            self._store_to_stm_completed,
            start_time=at_time,
        )

    def _store_to_stm_completed(
        self,
        perceived: Entity,
        completed_at: float,
    ) -> None:
        """TC2 completion: commit STM only after A finishes."""
        stored = perceived.derive(
            kind="stored_button",
            payload=perceived.payload,
            birth_time=completed_at,
        )
        self._stm[self.MEMORY_SLOT] = stored
        self._tc3_retrieve_from_stm(stored, completed_at)

    def _tc3_retrieve_from_stm(
        self,
        stored: Entity,
        at_time: float,
    ) -> None:
        """TC3 activation: request the slot written by TC2."""
        request = stored.derive(
            kind="memory_retrieval_request",
            payload={"memory_slot": self.MEMORY_SLOT},
            birth_time=at_time,
        )
        self._activate(
            "TC3",
            "RETRIEVE_FROM_STM",
            request,
            self._retrieve_from_stm_completed,
            start_time=at_time,
        )

    def _retrieve_from_stm_completed(
        self,
        request: Entity,
        completed_at: float,
    ) -> None:
        """TC3 completion: produce the retrieved entity."""
        slot = str(request.payload["memory_slot"])
        if slot not in self._stm:
            raise RuntimeError(f"Nothing stored in STM slot {slot!r}")
        retrieved = request.derive(
            kind="retrieved_button",
            payload=self._stm[slot].payload,
            birth_time=completed_at,
        )
        self._tc4_compare(retrieved, completed_at)

    def _tc4_compare(self, retrieved: Entity, at_time: float) -> None:
        """TC4 activation: compare retrieved text with the internal USB goal."""
        self._activate(
            "TC4",
            "COMPARE",
            retrieved,
            self._compare_completed,
            start_time=at_time,
        )

    def _compare_completed(
        self,
        retrieved: Entity,
        completed_at: float,
    ) -> None:
        """TC4 completion: commit examined state and comparison output."""
        comparison = retrieved.derive(
            kind="comparison",
            payload={
                **retrieved.payload,
                "target_label": self.config.target_label,
                "match": (
                    retrieved.payload["label"] == self.config.target_label
                ),
            },
            birth_time=completed_at,
        )
        self.examined.add(int(retrieved.payload["button_index"]))
        self._tc5_goto(comparison, completed_at)

    def _tc5_goto(self, comparison: Entity, at_time: float) -> None:
        """TC5 activation: execute the explicit empty-route GOTO operator."""
        self._activate(
            "TC5",
            "GOTO",
            comparison,
            self._goto_completed,
            start_time=at_time,
        )

    def _goto_completed(
        self,
        comparison: Entity,
        completed_at: float,
    ) -> None:
        """TC5 completion: branch only after GOTO completes."""
        if bool(comparison.payload["match"]):
            self._tc7_reach_with_hand(comparison, completed_at)
            return

        if self.monitor is None:
            self._tc6_visual_search(comparison, completed_at)
            return
        self.paused_tc = "TC6"
        self.monitor.before_visual_search(
            self,
            comparison,
            completed_at,
            lambda resume_at: self._resume_tc6(comparison, resume_at),
        )

    def _resume_tc6(self, comparison: Entity, at_time: float) -> None:
        self.paused_tc = None
        self.is_paused = False
        self._tc6_visual_search(comparison, at_time)

    def _tc6_visual_search(
        self,
        comparison: Entity,
        at_time: float,
    ) -> None:
        """TC6 activation: choose from internal search state, always through C."""
        unchecked_attention = [
            index for index in self.attention if index not in self.examined
        ]
        if unchecked_attention:
            target_index = unchecked_attention[0]
            needs_saccade = False
        else:
            remaining = [
                index
                for index in self._geometry
                if index not in self.examined
            ]
            if not remaining:
                raise RuntimeError("Search exhausted without finding target")
            target_index = remaining[
                int(self.rng.integers(0, len(remaining)))
            ]
            needs_saccade = True

        target_location = self._geometry[target_index]["location"]
        assert isinstance(target_location, tuple)
        distance = _distance(self.gaze, target_location)
        search = comparison.derive(
            kind="visual_search_selection",
            payload={
                "target_index": target_index,
                "target_location": target_location,
                "needs_saccade": needs_saccade,
            },
            birth_time=at_time,
        )
        self._activate(
            "TC6",
            "VISUAL_SEARCH",
            search,
            self._visual_search_completed,
            start_time=at_time,
            parameters={
                "needs_saccade": needs_saccade,
                "saccade_distance_px": distance,
            },
        )

    def _visual_search_completed(
        self,
        search: Entity,
        completed_at: float,
    ) -> None:
        """TC6 completion: commit focus/attention before activating TC1."""
        target_index = int(search.payload["target_index"])
        target_location = search.payload["target_location"]
        assert isinstance(target_location, tuple)
        self.focus_index = target_index
        if bool(search.payload["needs_saccade"]):
            self.gaze = target_location
            self.attention = self._attention_set(target_index)
        self._tc1_look_at(completed_at)

    def _tc7_reach_with_hand(
        self,
        comparison: Entity,
        at_time: float,
    ) -> None:
        """TC7 activation: reach using location/width carried by comparison."""
        target = comparison.payload["location"]
        width = float(comparison.payload["width"])
        assert isinstance(target, tuple)
        distance = _distance(self.config.hand_start_px, target)
        request = comparison.derive(
            kind="reach_request",
            payload={
                "button_index": comparison.payload["button_index"],
                "target_location": target,
                "width": width,
            },
            birth_time=at_time,
        )
        self._activate(
            "TC7",
            "REACH_WITH_HAND",
            request,
            self._reach_with_hand_completed,
            start_time=at_time,
            parameters={"distance_px": distance, "width_px": width},
        )

    def _reach_with_hand_completed(
        self,
        request: Entity,
        completed_at: float,
    ) -> None:
        """TC7 completion: produce a reached-target entity for TC8."""
        reached = request.derive(
            kind="reached_target",
            payload=request.payload,
            birth_time=completed_at,
        )
        self._tc8_click_with_finger(reached, completed_at)

    def _tc8_click_with_finger(
        self,
        reached: Entity,
        at_time: float,
    ) -> None:
        """TC8 activation: click the reached button without rereading it."""
        request = reached.derive(
            kind="click_request",
            payload=reached.payload,
            birth_time=at_time,
        )
        self._activate(
            "TC8",
            "CLICK_WITH_FINGER",
            request,
            self._click_with_finger_completed,
            start_time=at_time,
        )

    def _click_with_finger_completed(
        self,
        request: Entity,
        completed_at: float,
    ) -> None:
        """TC8 completion: commit the click action, then activate TC9."""
        button_index = int(request.payload["button_index"])
        if not self.environment.receive_click(button_index, completed_at):
            raise RuntimeError("Visual-search flow clicked a non-target button")
        clicked = request.derive(
            kind="clicked_target",
            payload=request.payload,
            birth_time=completed_at,
        )
        self._tc9_goal_accomplished(clicked, completed_at)

    def _tc9_goal_accomplished(
        self,
        clicked: Entity,
        at_time: float,
    ) -> None:
        """TC9 activation: report successful task completion."""
        self._activate(
            "TC9",
            "GOAL_ACCOMPLISHED",
            clicked,
            self._goal_accomplished_completed,
            start_time=at_time,
        )

    def _goal_accomplished_completed(
        self,
        _clicked: Entity,
        completed_at: float,
    ) -> None:
        """TC9 completion: finalize trial metrics."""
        self.completion_at = completed_at
        self.completion_time = completed_at - self.trial_start
        if self.monitor is not None:
            self.monitor.search_completed(self, completed_at)
