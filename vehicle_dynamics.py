"""Figure 4(b): Appendix A vehicle dynamics without cognitive logic."""
from __future__ import annotations

import math
from dataclasses import dataclass

from model_config import VehicleConfig


@dataclass
class VehicleState:
    """Vehicle state in the Appendix A coordinate system."""

    x: float = 0.0
    z: float = 0.0
    yaw: float = 0.0
    steering_angle: float = 0.0
    near_angle: float = 0.0
    far_angle: float = 0.0


class VehicleDynamics:
    """Advance ``VehicleState`` using the equations in Appendix A."""

    def __init__(
        self,
        initial_lateral_position: float = 0.0,
        config: VehicleConfig | None = None,
    ) -> None:
        self.config = config or VehicleConfig()
        self.state = VehicleState(x=float(initial_lateral_position))
        self._update_visual_angles()

    def step(self, steering_angle: float, dt: float) -> VehicleState:
        """Advance by ``dt`` from an absolute steering-wheel angle in radians."""
        if dt <= 0:
            raise ValueError("dt must be positive")
        config = self.config
        state = self.state
        distance = config.speed_mps * dt
        radius = (
            1_000_000.0
            if abs(steering_angle) < 1e-12
            else config.wheelbase_m / math.sin(steering_angle)
        )
        alpha = distance / radius
        # Appendix A prints 2*|R|*sin(alpha/2). Taken literally, a negative
        # radius makes the first lateral displacement positive for a left turn,
        # contradicting its own sign definition and Figure 8. A positive chord
        # magnitude preserves the stated negative-R/left-turn convention.
        chord_length = 2.0 * abs(radius) * math.sin(abs(alpha) / 2.0)
        state.x += (
            chord_length * math.sin(state.yaw + alpha / 2.0)
        )
        state.z += (
            chord_length * math.cos(state.yaw + alpha / 2.0)
        )
        state.yaw += alpha
        state.steering_angle = float(steering_angle)
        self._update_visual_angles()
        return state

    def _update_visual_angles(self) -> None:
        config = self.config
        state = self.state
        state.near_angle = (
            math.atan(state.x / config.near_distance_m) + state.yaw
        )
        state.far_angle = (
            math.atan(
                state.x
                / (config.far_time_headway_s * config.speed_mps)
            )
            + state.yaw
        )

    def visual_angles(self) -> tuple[float, float]:
        """Return the latest near and far visual angles in radians."""
        return self.state.near_angle, self.state.far_angle
