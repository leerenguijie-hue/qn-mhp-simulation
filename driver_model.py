"""Figure 4 Driver Model integration boundary.

The driver owns exactly one queue network.  Steering, visual search, and the
Performance Monitor are registered against that instance, so their entities use
the same Server 1, 2/3, 4, A, C, W, Y, and Z objects.
"""
from __future__ import annotations

import math
from typing import Any

from cognitive_architecture import (
    Entity,
    OperatorSpec,
    QueueNetwork,
    ServerSpec,
)
from model_config import CognitiveConfig, VisualSearchConfig


def _visual_search_demand_rule(
    config: VisualSearchConfig,
):
    def demand(
        server_name: str,
        _entity: Entity,
        parameters: dict[str, Any],
    ) -> float:
        if server_name != "C" or not parameters.get("needs_saccade", False):
            return 0.0
        distance = float(parameters["saccade_distance_px"])
        return config.saccade_base_s + config.saccade_seconds_per_pixel * distance

    return demand


def _reach_demand_rule(
    config: VisualSearchConfig,
):
    def demand(
        server_name: str,
        _entity: Entity,
        parameters: dict[str, Any],
    ) -> float:
        if server_name != "Z":
            return 0.0
        distance = max(0.0, float(parameters["distance_px"]))
        width = max(1e-9, float(parameters["width_px"]))
        index_of_difficulty = math.log2(distance / width + 1.0)
        return config.fitts_intercept_s + (
            config.fitts_slope_s * index_of_difficulty
        )

    return demand


def build_operator_specs(
    cognitive: CognitiveConfig,
    visual: VisualSearchConfig,
) -> list[OperatorSpec]:
    """Build the explicit TC operator registry used by the driver."""
    routes = {
        "LOOK_AT": ("1", "2/3", "4"),
        # The dissertation does not uniquely identify the Chapter 4 verbal
        # memory server or a second A visit in Figure 6. These A routes are
        # explicit reconstruction choices required by the requested model.
        "STORE_TO_STM": ("A",),
        "RETRIEVE_FROM_STM": ("A",),
        "COMPARE": ("C",),
        "GOTO": (),
        "VISUAL_SEARCH": ("C",),
        "DETERMINE_STEERING": ("C",),
        "TURN_STEERING": ("W", "Y", "Z"),
        "REACH_WITH_HAND": ("W", "Y", "Z"),
        "CLICK_WITH_FINGER": ("W", "Y", "Z"),
        "GOAL_ACCOMPLISHED": (),
    }
    dynamic_rules = {
        "VISUAL_SEARCH": _visual_search_demand_rule(visual),
        "REACH_WITH_HAND": _reach_demand_rule(visual),
    }
    return [
        OperatorSpec(
            name=name,
            route=route,
            service_demand_by_server=cognitive.operator_demand_s.get(name, {}),
            service_demand_rule=dynamic_rules.get(name),
        )
        for name, route in routes.items()
    ]


class DriverModel:
    """Own and coordinate the one shared task-independent queue network."""

    def __init__(
        self,
        cognitive_config: CognitiveConfig | None = None,
        visual_config: VisualSearchConfig | None = None,
    ) -> None:
        self.cognitive_config = cognitive_config or CognitiveConfig()
        self.visual_config = visual_config or VisualSearchConfig()
        server_names = tuple(self.cognitive_config.default_service_s)
        if set(server_names) != set(self.cognitive_config.capacities):
            raise ValueError("Service-time and capacity server sets must match")
        server_specs = [
            ServerSpec(
                name=name,
                capacity=self.cognitive_config.capacities[name],
                default_service_time=self.cognitive_config.default_service_s[
                    name
                ],
            )
            for name in server_names
        ]
        self.network = QueueNetwork(
            server_specs,
            build_operator_specs(self.cognitive_config, self.visual_config),
        )
        self.tasks: dict[str, Any] = {}

    def register_task(self, name: str, task: Any) -> None:
        """Register a task that uses this driver's exact network instance."""
        if getattr(task, "network", None) is not self.network:
            raise ValueError("Task must use the DriverModel QueueNetwork instance")
        if name in self.tasks:
            raise ValueError(f"Task {name!r} is already registered")
        self.tasks[name] = task

    def task(self, name: str) -> Any:
        """Return a registered task by name."""
        return self.tasks[name]

    def process_until(self, target_time: float) -> float:
        """Advance all shared cognitive-server events to ``target_time``."""
        return self.network.process_until(target_time)

    def drain(self) -> float:
        """Complete all currently scheduled cognitive work."""
        return self.network.drain()
