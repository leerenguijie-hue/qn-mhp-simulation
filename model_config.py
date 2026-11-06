"""Model parameters with explicit provenance.

``PAPER_DERIVED`` contains values stated in Feng (2015).  Values needed to make
the executable reconstruction complete, but not supplied by the dissertation,
live in ``RECONSTRUCTED``.  ``CALIBRATED`` is intentionally empty until a
documented fit against human data is performed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ParameterSource(str, Enum):
    """Allowed provenance classes for model parameters."""

    PAPER_DERIVED = "PAPER_DERIVED"
    RECONSTRUCTED = "RECONSTRUCTED"
    CALIBRATED = "CALIBRATED"


@dataclass(frozen=True)
class SourcedParameter:
    """A parameter value together with its source and modeling caveat."""

    value: Any
    source: ParameterSource
    citation: str
    note: str = ""


def _paper(value: Any, citation: str, note: str = "") -> SourcedParameter:
    return SourcedParameter(
        value=value,
        source=ParameterSource.PAPER_DERIVED,
        citation=citation,
        note=note,
    )


def _reconstructed(value: Any, note: str) -> SourcedParameter:
    return SourcedParameter(
        value=value,
        source=ParameterSource.RECONSTRUCTED,
        citation="Not specified by Feng (2015)",
        note=note,
    )


PAPER_DERIVED: dict[str, SourcedParameter] = {
    "visual_stimulus_interval_s": _paper(0.050, "Chapter 2, pp. 16–17"),
    "visual_recognition_capacity": _paper(4, "Chapter 4, p. 55"),
    "long_glance_threshold_s": _paper(
        2.0,
        "Chapter 3",
        "A long glance is strictly greater than this threshold.",
    ),
    "near_distance_m": _paper(10.0, "Appendix A"),
    "far_time_headway_s": _paper(4.0, "Appendix A"),
    "screen_size_px": _paper((800.0, 480.0), "Chapter 3"),
    "button_spacing_px": _paper(4.0, "Chapter 3"),
    "font_size_px": _paper(20.0, "Chapter 3"),
    "button_sizes_px": _paper(
        {"small": 66.0, "medium": 108.0, "large": 150.0},
        "Chapter 3",
    ),
    "layout_shapes": _paper(
        {"2x2": (2, 2), "2x4": (2, 4), "3x5": (3, 5)},
        "Chapter 3",
    ),
    "target_label": _paper("USB", "Chapter 3"),
    "replications_per_condition": _paper(10, "Chapter 4, p. 52"),
    "vehicle_speed_mps": _paper(
        29.0,
        "Chapter 2, p. 17",
        "The steering validation used 65 mph (=29 m/s).",
    ),
    "steering_initial_offsets_m": _paper(
        (0.3, 0.6, 0.9, 1.2),
        "Chapter 2, p. 17",
    ),
}


RECONSTRUCTED: dict[str, SourcedParameter] = {
    "server_default_service_s": _reconstructed(
        {
            "1": 0.005,
            "2/3": 0.005,
            "4": 0.005,
            "A": 0.005,
            "C": 0.005,
            "W": 0.005,
            "Y": 0.005,
            "Z": 0.005,
        },
        "Deterministic base times retained as transparent executable defaults.",
    ),
    "operator_service_demand_s": _reconstructed(
        {
            "LOOK_AT": {"1": 0.017, "2/3": 0.017, "4": 0.021},
            "STORE_TO_STM": {"A": 0.009},
            "RETRIEVE_FROM_STM": {"A": 0.009},
            "COMPARE": {"C": 0.017},
            "VISUAL_SEARCH": {"C": 0.017},
            "DETERMINE_STEERING": {"C": 0.017},
            "TURN_STEERING": {"W": 0.005, "Y": 0.005, "Z": 0.005},
            "REACH_WITH_HAND": {"W": 0.005, "Y": 0.005, "Z": 0.005},
            "CLICK_WITH_FINGER": {"W": 0.005, "Y": 0.005, "Z": 0.005},
        },
        "The dissertation does not report operator/server service demands.",
    ),
    "server_capacities": _reconstructed(
        {"1": 1, "2/3": 1, "4": 4, "A": 1, "C": 1, "W": 1, "Y": 1, "Z": 1},
        "Server 4 uses the paper's recognition capacity. Other capacities are "
        "executable assumptions; C=1 preserves the requested shared-resource test.",
    ),
    "saccade_base_s": _reconstructed(
        0.028,
        "No quantitative gaze-shift equation is reported.",
    ),
    "saccade_seconds_per_pixel": _reconstructed(
        0.00035,
        "Pixel-distance approximation; requires calibration.",
    ),
    "fitts_intercept_s": _reconstructed(
        0.080,
        "Fitts coefficients are not reported.",
    ),
    "fitts_slope_s": _reconstructed(
        0.120,
        "Fitts coefficients are not reported.",
    ),
    "hand_start_px": _reconstructed(
        (400.0, 600.0),
        "A fixed hand origin is needed for the executable Fitts approximation.",
    ),
    "gaze_start_px": _reconstructed(
        (400.0, 240.0),
        "A fixed device gaze origin is not specified.",
    ),
    "steering_gains": _reconstructed(
        {"far": -0.2, "near": -0.2, "integral": -0.015},
        "The steering-law gains are not reported. These defaults keep the "
        "reconstructed delayed loop numerically stable; they are not a human-data fit.",
    ),
    "near_angle_cap_deg": _reconstructed(
        20.0,
        "The dissertation gives the symbol but not its numerical value.",
    ),
    "maximum_steering_angle_deg": _reconstructed(
        45.0,
        "No steering-angle limit is reported.",
    ),
    "wheelbase_m": _reconstructed(2.7, "Vehicle wheelbase is not reported."),
    "appendix_negative_turn_sign_correction": _reconstructed(
        True,
        "Appendix A prints |R|*sin(alpha/2), which moves X right for both "
        "steering signs and conflicts with its negative-R definition and Figure 8. "
        "The executable model uses a positive chord length for left turns.",
    ),
    "simulation_step_s": _reconstructed(
        0.01,
        "Numerical integration step is not reported.",
    ),
    "driving_initial_lateral_offset_m": _reconstructed(
        0.6,
        "A nonzero offset makes the reconstructed lateral-control task observable.",
    ),
    "off_road_threshold_s": _reconstructed(
        1.20,
        "Performance Monitor switch threshold is not reported; pending calibration.",
    ),
    "minimum_road_check_s": _reconstructed(
        0.25,
        "Road-check duration is not reported; pending calibration.",
    ),
    "driving_cycles_per_check": _reconstructed(
        1,
        "The number of inserted driving cycles is not reported.",
    ),
}


# No parameter has yet been fit to the Chapter 3 observations.
CALIBRATED: dict[str, SourcedParameter] = {}


@dataclass(frozen=True)
class CognitiveConfig:
    """Shared-server timing and capacity reconstruction."""

    default_service_s: dict[str, float] = field(
        default_factory=lambda: dict(
            RECONSTRUCTED["server_default_service_s"].value
        )
    )
    operator_demand_s: dict[str, dict[str, float]] = field(
        default_factory=lambda: {
            name: dict(values)
            for name, values in RECONSTRUCTED[
                "operator_service_demand_s"
            ].value.items()
        }
    )
    capacities: dict[str, int] = field(
        default_factory=lambda: dict(RECONSTRUCTED["server_capacities"].value)
    )


@dataclass(frozen=True)
class VisualSearchConfig:
    """Visual-search parameters used by TC1–TC9."""

    target_label: str = PAPER_DERIVED["target_label"].value
    recognition_capacity: int = PAPER_DERIVED[
        "visual_recognition_capacity"
    ].value
    saccade_base_s: float = RECONSTRUCTED["saccade_base_s"].value
    saccade_seconds_per_pixel: float = RECONSTRUCTED[
        "saccade_seconds_per_pixel"
    ].value
    fitts_intercept_s: float = RECONSTRUCTED["fitts_intercept_s"].value
    fitts_slope_s: float = RECONSTRUCTED["fitts_slope_s"].value
    hand_start_px: tuple[float, float] = RECONSTRUCTED["hand_start_px"].value
    gaze_start_px: tuple[float, float] = RECONSTRUCTED["gaze_start_px"].value


@dataclass(frozen=True)
class SteeringConfig:
    """Steering-task program and control-law parameters."""

    visual_interval_s: float = PAPER_DERIVED[
        "visual_stimulus_interval_s"
    ].value
    k_far: float = RECONSTRUCTED["steering_gains"].value["far"]
    k_near: float = RECONSTRUCTED["steering_gains"].value["near"]
    k_integral: float = RECONSTRUCTED["steering_gains"].value["integral"]
    near_angle_cap_deg: float = RECONSTRUCTED["near_angle_cap_deg"].value
    maximum_steering_angle_deg: float = RECONSTRUCTED[
        "maximum_steering_angle_deg"
    ].value


@dataclass(frozen=True)
class VehicleConfig:
    """Appendix A constants plus explicit reconstruction choices."""

    speed_mps: float = PAPER_DERIVED["vehicle_speed_mps"].value
    wheelbase_m: float = RECONSTRUCTED["wheelbase_m"].value
    near_distance_m: float = PAPER_DERIVED["near_distance_m"].value
    far_time_headway_s: float = PAPER_DERIVED["far_time_headway_s"].value


@dataclass(frozen=True)
class PerformanceMonitorConfig:
    """Pending-calibration controls for Figure 23 task switching."""

    off_road_threshold_s: float = RECONSTRUCTED[
        "off_road_threshold_s"
    ].value
    minimum_road_check_s: float = RECONSTRUCTED[
        "minimum_road_check_s"
    ].value
    driving_cycles_per_check: int = RECONSTRUCTED[
        "driving_cycles_per_check"
    ].value
    long_glance_threshold_s: float = PAPER_DERIVED[
        "long_glance_threshold_s"
    ].value


def parameter_manifest() -> dict[str, dict[str, dict[str, Any]]]:
    """Return a JSON-serializable provenance manifest."""
    groups = {
        ParameterSource.PAPER_DERIVED.value: PAPER_DERIVED,
        ParameterSource.RECONSTRUCTED.value: RECONSTRUCTED,
        ParameterSource.CALIBRATED.value: CALIBRATED,
    }
    return {
        group: {
            name: {
                "value": parameter.value,
                "citation": parameter.citation,
                "note": parameter.note,
            }
            for name, parameter in values.items()
        }
        for group, values in groups.items()
    }
