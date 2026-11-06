"""Figure 23 Performance Monitor for the Driving dual task."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from cognitive_architecture import Entity, QueueNetwork
from model_config import PerformanceMonitorConfig
from task_environment import TaskEnvironment
from tasks.steering import SteeringTask


@dataclass(frozen=True)
class Glance:
    """One completed eyes-off-road interval."""

    start: float
    end: float

    @property
    def duration(self) -> float:
        """Return glance duration in seconds."""
        return self.end - self.start


@dataclass(frozen=True)
class SearchPause:
    """Search state captured immediately before an inserted driving cycle."""

    timestamp: float
    paused_tc: str
    examined: frozenset[int]
    attention: tuple[int, ...]
    focus_index: int | None


class PerformanceMonitor:
    """Choose gaze/task switches that resource queues alone cannot decide."""

    def __init__(
        self,
        network: QueueNetwork,
        environment: TaskEnvironment,
        steering_task: SteeringTask,
        config: PerformanceMonitorConfig | None = None,
    ) -> None:
        if steering_task.network is not network:
            raise ValueError("Performance Monitor and steering must share a network")
        self.network = network
        self.environment = environment
        self.steering_task = steering_task
        self.config = config or PerformanceMonitorConfig()
        if self.config.driving_cycles_per_check < 1:
            raise ValueError("At least one driving cycle must be inserted")

        self.current_task: str | None = None
        self.glances: list[Glance] = []
        self.search_pauses: list[SearchPause] = []
        self.inserted_driving_cycles = 0
        self._active_glance_start: float | None = None
        self._first_off_road_start: float | None = None
        self._last_off_road_end: float | None = None

    @property
    def eyes_off_road_duration(self) -> float:
        """Cumulative completed and currently active off-road time."""
        total = sum(glance.duration for glance in self.glances)
        if self._active_glance_start is not None:
            total += self.network.time - self._active_glance_start
        return total

    @property
    def glance_durations(self) -> list[float]:
        """Durations of all completed off-road glances."""
        return [glance.duration for glance in self.glances]

    @property
    def teort(self) -> float:
        """Total Eyes-Off-Road Time for the completed trial."""
        return sum(self.glance_durations)

    @property
    def task_completion_time(self) -> float | None:
        """First off-road glance start to final off-road glance end."""
        if (
            self._first_off_road_start is None
            or self._last_off_road_end is None
        ):
            return None
        return self._last_off_road_end - self._first_off_road_start

    @property
    def long_glance_count(self) -> int:
        """Count glances strictly longer than the paper's 2.0 s criterion."""
        threshold = self.config.long_glance_threshold_s
        return sum(duration > threshold for duration in self.glance_durations)

    def _open_glance(self, at_time: float) -> None:
        if self._active_glance_start is not None:
            raise RuntimeError("Cannot open an already active off-road glance")
        self.environment.set_gaze("device", at_time)
        self._active_glance_start = at_time
        if self._first_off_road_start is None:
            self._first_off_road_start = at_time

    def _close_glance(self, at_time: float) -> None:
        if self._active_glance_start is None:
            raise RuntimeError("Cannot close an inactive off-road glance")
        if at_time < self._active_glance_start:
            raise ValueError("Glance end precedes its start")
        self.glances.append(Glance(self._active_glance_start, at_time))
        self._active_glance_start = None
        self._last_off_road_end = at_time

    def search_started(self, _task: object, at_time: float) -> None:
        """Start the first device glance."""
        self.current_task = "visual_search"
        self._open_glance(at_time)

    def before_visual_search(
        self,
        task: object,
        _comparison: Entity,
        at_time: float,
        resume: Callable[[float], None],
    ) -> None:
        """Apply Figure 23's threshold before each activation of TC6."""
        if self._active_glance_start is None:
            raise RuntimeError("Visual search has no active device glance")
        elapsed = at_time - self._active_glance_start
        if elapsed < self.config.off_road_threshold_s:
            resume(at_time)
            return

        # Attribute access is intentionally structural to avoid a circular
        # import from visual_search back into this task module.
        task.is_paused = True
        self.search_pauses.append(
            SearchPause(
                timestamp=at_time,
                paused_tc="TC6",
                examined=frozenset(task.examined),
                attention=tuple(task.attention),
                focus_index=task.focus_index,
            )
        )
        self._close_glance(at_time)
        self.environment.set_gaze("road", at_time)
        self.current_task = "steering"
        road_return_not_before = at_time + self.config.minimum_road_check_s
        self._run_driving_cycles(
            remaining=self.config.driving_cycles_per_check,
            at_time=at_time,
            road_return_not_before=road_return_not_before,
            task=task,
            resume=resume,
        )

    def _run_driving_cycles(
        self,
        *,
        remaining: int,
        at_time: float,
        road_return_not_before: float,
        task: object,
        resume: Callable[[float], None],
    ) -> None:
        near_angle, far_angle = self.environment.road.stimuli()
        self.inserted_driving_cycles += 1

        def cycle_completed(completed_at: float) -> None:
            if remaining > 1:
                self._run_driving_cycles(
                    remaining=remaining - 1,
                    at_time=completed_at,
                    road_return_not_before=road_return_not_before,
                    task=task,
                    resume=resume,
                )
                return
            switch_time = max(completed_at, road_return_not_before)
            if switch_time > self.network.time:
                self.network.schedule_callback(
                    switch_time,
                    lambda: self._resume_search(task, resume, switch_time),
                )
            else:
                self._resume_search(task, resume, switch_time)

        self.steering_task.submit_visual_angles(
            near_angle,
            far_angle,
            at_time,
            on_cycle_complete=cycle_completed,
        )

    def _resume_search(
        self,
        task: object,
        resume: Callable[[float], None],
        at_time: float,
    ) -> None:
        self.current_task = "visual_search"
        self._open_glance(at_time)
        task.is_paused = False
        resume(at_time)

    def search_completed(self, _task: object, at_time: float) -> None:
        """Close the last glance when TC9 completes."""
        self._close_glance(at_time)
        self.environment.set_gaze("road", at_time)
        self.current_task = None

    def metrics(self) -> dict[str, object]:
        """Return structured Driving glance metrics."""
        completion_time = self.task_completion_time
        if completion_time is None:
            raise RuntimeError("Driving trial has not completed")
        return {
            "task_completion_time_s": completion_time,
            "teort_s": self.teort,
            "glance_count": len(self.glances),
            "glance_durations_s": self.glance_durations,
            "long_glance_count": self.long_glance_count,
            "inserted_driving_cycles": self.inserted_driving_cycles,
        }
