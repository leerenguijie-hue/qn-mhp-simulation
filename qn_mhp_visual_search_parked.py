"""
QN-MHP Parked visual search (Feng dissertation Ch. 3 experiment / Ch. 4 model).

Task: find and press the USB button among distractors on a touch screen while the
vehicle is parked (single-task, eyes initially on screen center).

TC 1–9 map to QN-MHP operators via OPERATOR_ROUTES in qn_mhp_network.py.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Dict, List, Set, Tuple

import numpy as np

from qn_mhp_network import Entity, OPERATOR_ROUTES, QueueNetwork

# --- Parameter selection (provisional; calibrate against Table 1 Parked) ---
PARKED_CONFIG = {
    "replications": 10,
    "screen_w_px": 800.0,
    "screen_h_px": 480.0,
    "button_spacing_px": 4.0,
    "font_px": 20.0,
    "target_label": "USB",
    "recognition_capacity": 4,
    "recognition_penalty_s": 0.018,
    "saccade_base_s": 0.028,
    "saccade_per_px": 0.00035,
    "fitts_a_s": 0.08,
    "fitts_b_s": 0.12,
    "hand_start": (400.0, 600.0),
    "gaze_start": (400.0, 240.0),
    "service": {
        "1": 0.022,
        "2/3": 0.022,
        "4": 0.026,
        "A": 0.014,
        "C": 0.022,
        "W": 0.010,
        "Y": 0.010,
        "Z": 0.010,
    },
}

LAYOUTS = {
    "2x2": (2, 2),
    "2x4": (2, 4),
    "3x5": (3, 5),
}
BUTTON_SIZES_PX = {"small": 66.0, "medium": 108.0, "large": 150.0}
LABELS = {
    "2x2": ["AM1", "FM1", "USB", "DVD"],
    "2x4": ["AM1", "FM1", "USB", "DVD", "AM2", "FM2", "MP3", "CD"],
    "3x5": [
        "AM1", "FM1", "USB", "DVD", "AM2", "FM2", "MP3", "CD",
        "AM3", "FM3", "TV", "SD", "Tape", "AV In", "Scan",
    ],
}


@dataclass(frozen=True)
class Button:
    index: int
    label: str
    cx: float
    cy: float
    width: float
    height: float


def _grid_origin(cols: int, rows: int, btn: float, gap: float, sw: float, sh: float) -> Tuple[float, float]:
    grid_w = cols * btn + (cols - 1) * gap
    grid_h = rows * btn + (rows - 1) * gap
    return (sw - grid_w) / 2.0, (sh - grid_h) / 2.0


def build_ui(
    layout_key: str, size_key: str, cfg: dict, rng: np.random.Generator
) -> List[Button]:
    rows, cols = LAYOUTS[layout_key]
    btn = BUTTON_SIZES_PX[size_key]
    gap = cfg["button_spacing_px"]
    sw, sh = cfg["screen_w_px"], cfg["screen_h_px"]
    ox, oy = _grid_origin(cols, rows, btn, gap, sw, sh)
    labels = list(LABELS[layout_key])
    rng.shuffle(labels)
    buttons: List[Button] = []
    for r in range(rows):
        for c in range(cols):
            idx = r * cols + c
            cx = ox + c * (btn + gap) + btn / 2.0
            cy = oy + r * (btn + gap) + btn / 2.0
            buttons.append(Button(idx, labels[idx], cx, cy, btn, btn))
    return buttons


def _distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _attention_set(buttons: List[Button], focus: Button, capacity: int) -> List[Button]:
    ordered = sorted(buttons, key=lambda b: _distance((b.cx, b.cy), (focus.cx, focus.cy)))
    return ordered[:capacity]


def _fitts_time(a: float, b: float, dist: float, width: float) -> float:
    if width <= 0:
        width = 1.0
    index = math.log2(dist / width + 1.0)
    return a + b * index


def _perception_extra(n_buttons: int, cfg: dict) -> float:
    cap = cfg["recognition_capacity"]
    if n_buttons <= cap:
        return 0.0
    return (n_buttons - cap) * cfg["recognition_penalty_s"]


class ParkedVisualSearchModel:
    """
    Task controller: TC 1–9 ↔ QN-MHP operators.

    Pathway selection (Parked):
      - Fixed NGOMSL method graph; only TC 5 GOTO branches (match → TC 7, else → TC 6).
      - TC 6 chooses same-fixation item vs saccade to a new button (random among unexamined).
      - No driving-task insertion (dual-task switch is disabled here).
    """

    def __init__(self, buttons: List[Button], cfg: dict, rng: np.random.Generator):
        self.buttons = buttons
        self.cfg = cfg
        self.rng = rng
        self.network = QueueNetwork(cfg["service"])
        self.trial_start = 0.0
        self.completion_time: float | None = None

        self.examined: Set[int] = set()
        self.gaze = cfg["gaze_start"]
        self.focus: Button | None = None
        self.attention: List[Button] = []
        self._last_match = 0

    def _schedule_saccade(self, target: Button, then: Callable[[], None]) -> None:
        dist = _distance(self.gaze, (target.cx, target.cy))
        delay = self.cfg["saccade_base_s"] + self.cfg["saccade_per_px"] * dist
        ent = Entity(
            "saccade",
            {"extra_service": delay, "target_index": target.index},
            birth_time=self.network.time,
        )
        self.network.run_operator(
            "VISUAL_SEARCH",
            ent,
            OPERATOR_ROUTES["VISUAL_SEARCH"],
            lambda e, t: then(),
            start_time=self.network.time,
        )

    def _run_tc(self, tc: int) -> None:
        if tc == 1:
            self._tc_look_at()
        elif tc == 2:
            self._tc_store()
        elif tc == 3:
            self._tc_retrieve()
        elif tc == 4:
            self._tc_compare()
        elif tc == 5:
            self._tc_goto()
        elif tc == 6:
            self._tc_visual_search()
        elif tc == 7:
            self._tc_reach()
        elif tc == 8:
            self._tc_click()
        elif tc == 9:
            self._tc_goal_done()
        else:
            raise ValueError(f"Unknown TC {tc}")

    def _current_button(self) -> Button:
        assert self.focus is not None
        return self.focus

    def _tc_look_at(self) -> None:
        b = self._current_button()
        extra = _perception_extra(len(self.buttons), self.cfg)
        ent = Entity(
            "look",
            {
                "label": b.label,
                "location": (b.cx, b.cy),
                "extra_service": extra,
                "button_index": b.index,
            },
            birth_time=self.network.time,
        )
        self.network.run_operator(
            "LOOK_AT",
            ent,
            OPERATOR_ROUTES["LOOK_AT"],
            lambda e, t: self._run_tc(2),
        )

    def _tc_store(self) -> None:
        b = self._current_button()
        ent = Entity("store", {"label": b.label}, birth_time=self.network.time)
        self.network.run_operator(
            "STORE_TO_STM",
            ent,
            OPERATOR_ROUTES["STORE_TO_STM"],
            lambda e, t: self._run_tc(3),
        )

    def _tc_retrieve(self) -> None:
        b = self._current_button()
        ent = Entity("retrieve", {"label": b.label}, birth_time=self.network.time)
        self.network.run_operator(
            "RETRIEVE_FROM_STM",
            ent,
            OPERATOR_ROUTES["RETRIEVE_FROM_STM"],
            lambda e, t: self._run_tc(4),
        )

    def _tc_compare(self) -> None:
        b = self._current_button()
        match = 1 if b.label == self.cfg["target_label"] else 0
        ent = Entity("compare", {"match": match, "label": b.label}, birth_time=self.network.time)
        self.examined.add(b.index)

        def after_compare(_e: Entity, _t: float) -> None:
            self._last_match = match
            self._run_tc(5)

        self.network.run_operator(
            "COMPARE",
            ent,
            OPERATOR_ROUTES["COMPARE"],
            after_compare,
        )

    def _tc_goto(self) -> None:
        if self._last_match:
            self._run_tc(7)
        else:
            self._run_tc(6)

    def _tc_visual_search(self) -> None:
        unchecked = [b for b in self.attention if b.index not in self.examined]
        if unchecked:
            self.focus = unchecked[0]
            self._run_tc(1)
            return

        remaining = [b for b in self.buttons if b.index not in self.examined]
        if not remaining:
            raise RuntimeError("Search exhausted without finding target")
        target = remaining[int(self.rng.integers(0, len(remaining)))]

        def after_saccade() -> None:
            self.gaze = (target.cx, target.cy)
            self.focus = target
            self.attention = _attention_set(
                self.buttons, target, self.cfg["recognition_capacity"]
            )
            self._run_tc(1)

        self._schedule_saccade(target, after_saccade)

    def _tc_reach(self) -> None:
        b = self._current_button()
        hand = self.cfg["hand_start"]
        dist = _distance(hand, (b.cx, b.cy))
        fitts = _fitts_time(self.cfg["fitts_a_s"], self.cfg["fitts_b_s"], dist, b.width)
        ent = Entity(
            "reach",
            {"extra_service": fitts, "target": (b.cx, b.cy)},
            birth_time=self.network.time,
        )
        self.network.run_operator(
            "REACH_WITH_HAND",
            ent,
            OPERATOR_ROUTES["REACH_WITH_HAND"],
            lambda e, t: self._run_tc(8),
        )

    def _tc_click(self) -> None:
        ent = Entity("click", {}, birth_time=self.network.time)
        self.network.run_operator(
            "CLICK_WITH_FINGER",
            ent,
            OPERATOR_ROUTES["CLICK_WITH_FINGER"],
            lambda e, t: self._run_tc(9),
        )

    def _tc_goal_done(self) -> None:
        ent = Entity("done", {}, birth_time=self.network.time)
        self.network.run_operator(
            "GOAL_ACCOMPLISHED",
            ent,
            OPERATOR_ROUTES["GOAL_ACCOMPLISHED"],
            lambda e, t: self._finish(t),
        )

    def _finish(self, t: float) -> None:
        self.completion_time = t - self.trial_start

    def run(self) -> float:
        self.trial_start = self.network.time
        first_idx = int(self.rng.integers(0, len(self.buttons)))
        first = self.buttons[first_idx]
        self.focus = first
        self.attention = _attention_set(self.buttons, first, self.cfg["recognition_capacity"])
        self.gaze = self.cfg["gaze_start"]

        def begin_search() -> None:
            self.gaze = (first.cx, first.cy)
            self._run_tc(1)

        self._schedule_saccade(first, begin_search)
        self.network.drain()
        assert self.completion_time is not None
        return self.completion_time


def simulate_parked_trial(layout_key: str, size_key: str, seed: int) -> float:
    cfg = PARKED_CONFIG
    rng = np.random.default_rng(seed)
    buttons = build_ui(layout_key, size_key, cfg, rng)
    if not any(b.label == cfg["target_label"] for b in buttons):
        raise ValueError("Target label missing from layout")
    model = ParkedVisualSearchModel(buttons, cfg, rng)
    return model.run()


def run_all_conditions(replications: int | None = None) -> Dict[str, Dict[str, float]]:
    reps = replications or PARKED_CONFIG["replications"]
    means: Dict[str, Dict[str, float]] = {}
    for layout in LAYOUTS:
        means[layout] = {}
        for size in BUTTON_SIZES_PX:
            times = [
                simulate_parked_trial(
                    layout, size, seed=abs(hash((layout, size))) * 1000 + r
                )
                for r in range(reps)
            ]
            means[layout][size] = float(np.mean(times))
    return means


def main() -> None:
    human_parked = {
        "2x2": {"small": 1.42, "medium": 1.35, "large": 1.27},
        "2x4": {"small": 1.75, "medium": 1.72, "large": 1.65},
        "3x5": {"small": 2.49, "medium": 2.23, "large": 2.53},
    }
    model = run_all_conditions()
    print("Parked task completion time (s) — model vs Ch.3 Table 1 (human means)")
    print(f"{'Layout':<6} {'Size':<8} {'Model':>8} {'Human':>8} {'Δ':>8}")
    for layout in LAYOUTS:
        for size in BUTTON_SIZES_PX:
            m = model[layout][size]
            h = human_parked[layout][size]
            print(f"{layout:<6} {size:<8} {m:8.3f} {h:8.3f} {m - h:+8.3f}")
    print("\nNOTE: service times / Fitts / saccade constants are provisional (Ch.4).")


if __name__ == "__main__":
    main()
