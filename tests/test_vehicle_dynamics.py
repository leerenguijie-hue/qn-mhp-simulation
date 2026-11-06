"""Checks for the isolated Appendix A vehicle module."""
from __future__ import annotations

import math

import pytest

from vehicle_dynamics import VehicleDynamics


def test_zero_steering_advances_straight() -> None:
    vehicle = VehicleDynamics(initial_lateral_position=0.6)
    state = vehicle.step(0.0, 0.1)

    # Appendix A uses R=1,000,000 rather than mathematical infinity.
    assert state.x == pytest.approx(0.6, abs=1e-5)
    assert state.z == pytest.approx(2.9, rel=1e-5)
    assert state.yaw == pytest.approx(0.0, abs=3e-6)


def test_negative_steering_moves_toward_lane_center() -> None:
    vehicle = VehicleDynamics(initial_lateral_position=0.6)
    state = vehicle.step(math.radians(-1.0), 0.1)

    assert state.x < 0.6
    assert state.yaw < 0.0
    assert math.isfinite(state.near_angle)
    assert math.isfinite(state.far_angle)
