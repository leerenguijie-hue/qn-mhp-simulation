"""Figure 4(a): road and touchscreen task environment.

The environment exposes external stimuli and receives actions.  It contains no
queue-network server, operator, or task-component implementation.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from model_config import PAPER_DERIVED

LAYOUTS: dict[str, tuple[int, int]] = dict(
    PAPER_DERIVED["layout_shapes"].value
)
BUTTON_SIZES_PX: dict[str, float] = dict(
    PAPER_DERIVED["button_sizes_px"].value
)
LABELS = {
    "2x2": ["AM1", "FM1", "USB", "DVD"],
    "2x4": ["AM1", "FM1", "USB", "DVD", "AM2", "FM2", "MP3", "CD"],
    "3x5": [
        "AM1",
        "FM1",
        "USB",
        "DVD",
        "AM2",
        "FM2",
        "MP3",
        "CD",
        "AM3",
        "FM3",
        "TV",
        "SD",
        "Tape",
        "AV In",
        "Scan",
    ],
}
SCREEN_WIDTH_PX, SCREEN_HEIGHT_PX = PAPER_DERIVED["screen_size_px"].value
BUTTON_SPACING_PX = PAPER_DERIVED["button_spacing_px"].value
TARGET_LABEL = PAPER_DERIVED["target_label"].value


@dataclass(frozen=True)
class Button:
    """One externally visible touchscreen object."""

    index: int
    label: str
    cx: float
    cy: float
    width: float
    height: float

    @property
    def location(self) -> tuple[float, float]:
        """Return the button center in screen pixels."""
        return self.cx, self.cy


@dataclass(frozen=True)
class DeviceVisualStimulus:
    """Immutable visual stimulus sampled from a button at one instant."""

    button_index: int
    label: str
    location: tuple[float, float]
    width: float
    height: float


@dataclass(frozen=True)
class ActionRecord:
    """Action result accepted by the external environment."""

    action: str
    timestamp: float
    payload: dict[str, float | int | str]


@dataclass
class TouchscreenEnvironment:
    """Chapter 3 touchscreen layout and target placement."""

    buttons: list[Button]
    target_label: str = TARGET_LABEL

    @classmethod
    def create(
        cls,
        layout_key: str,
        size_key: str,
        rng: np.random.Generator,
    ) -> TouchscreenEnvironment:
        """Create one randomized layout using the paper-derived geometry."""
        if layout_key not in LAYOUTS:
            raise KeyError(f"Unknown layout {layout_key!r}")
        if size_key not in BUTTON_SIZES_PX:
            raise KeyError(f"Unknown button size {size_key!r}")
        rows, cols = LAYOUTS[layout_key]
        button_size = BUTTON_SIZES_PX[size_key]
        origin_x, origin_y = _grid_origin(
            cols,
            rows,
            button_size,
            BUTTON_SPACING_PX,
            SCREEN_WIDTH_PX,
            SCREEN_HEIGHT_PX,
        )
        labels = list(LABELS[layout_key])
        rng.shuffle(labels)
        buttons = []
        for row in range(rows):
            for col in range(cols):
                index = row * cols + col
                center_x = (
                    origin_x
                    + col * (button_size + BUTTON_SPACING_PX)
                    + button_size / 2
                )
                center_y = (
                    origin_y
                    + row * (button_size + BUTTON_SPACING_PX)
                    + button_size / 2
                )
                buttons.append(
                    Button(
                        index=index,
                        label=labels[index],
                        cx=center_x,
                        cy=center_y,
                        width=button_size,
                        height=button_size,
                    )
                )
        return cls(buttons=buttons)

    def button(self, index: int) -> Button:
        """Return a button by stable layout index."""
        if index < 0 or index >= len(self.buttons):
            raise IndexError(f"Button index {index} is out of range")
        return self.buttons[index]

    def visual_stimulus(self, index: int) -> DeviceVisualStimulus:
        """Sample the external visual state for TC1 LOOK_AT."""
        button = self.button(index)
        return DeviceVisualStimulus(
            button_index=button.index,
            label=button.label,
            location=button.location,
            width=button.width,
            height=button.height,
        )

    def target(self) -> Button:
        """Return the USB target and its randomized trial position."""
        for button in self.buttons:
            if button.label == self.target_label:
                return button
        raise RuntimeError(f"Target {self.target_label!r} is absent from the device")


@dataclass
class RoadScene:
    """Latest externally available near/far road-angle stimulus."""

    near_angle: float = 0.0
    far_angle: float = 0.0
    sample_time: float = 0.0

    def update(
        self,
        near_angle: float,
        far_angle: float,
        sample_time: float = 0.0,
    ) -> None:
        """Replace the current road stimulus."""
        self.near_angle = float(near_angle)
        self.far_angle = float(far_angle)
        self.sample_time = float(sample_time)

    def stimuli(self) -> tuple[float, float]:
        """Return current near and far angles."""
        return self.near_angle, self.far_angle


@dataclass
class TaskEnvironment:
    """Shared road/device environment outside the cognitive architecture."""

    road: RoadScene = field(default_factory=RoadScene)
    touchscreen: TouchscreenEnvironment | None = None
    gaze_target: Literal["road", "device"] = "road"
    actions: list[ActionRecord] = field(default_factory=list)

    def set_gaze(
        self,
        target: Literal["road", "device"],
        timestamp: float,
    ) -> None:
        """Set gaze and record the externally observable transition."""
        if target == "device" and self.touchscreen is None:
            raise RuntimeError("No touchscreen is attached to this environment")
        if target != self.gaze_target:
            self.gaze_target = target
            self.actions.append(
                ActionRecord("gaze", float(timestamp), {"target": target})
            )

    def receive_click(self, button_index: int, timestamp: float) -> bool:
        """Accept a click and report whether it hit the USB target."""
        if self.touchscreen is None:
            raise RuntimeError("No touchscreen is attached to this environment")
        button = self.touchscreen.button(button_index)
        hit = button.label == self.touchscreen.target_label
        self.actions.append(
            ActionRecord(
                "click",
                float(timestamp),
                {
                    "button_index": button_index,
                    "label": button.label,
                    "target_hit": int(hit),
                },
            )
        )
        return hit

    def receive_steering(self, steering_angle: float, timestamp: float) -> None:
        """Accept the steering action selected by the driver task."""
        self.actions.append(
            ActionRecord(
                "steering",
                float(timestamp),
                {"steering_angle": float(steering_angle)},
            )
        )


def _grid_origin(
    cols: int,
    rows: int,
    button_size: float,
    gap: float,
    screen_width: float,
    screen_height: float,
) -> tuple[float, float]:
    grid_width = cols * button_size + (cols - 1) * gap
    grid_height = rows * button_size + (rows - 1) * gap
    return (
        (screen_width - grid_width) / 2.0,
        (screen_height - grid_height) / 2.0,
    )
