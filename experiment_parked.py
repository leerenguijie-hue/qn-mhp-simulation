"""Command-line Chapter 3 Parked visual-search experiment."""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass

import numpy as np

from driver_model import DriverModel
from model_config import PAPER_DERIVED, VisualSearchConfig
from task_environment import (
    BUTTON_SIZES_PX,
    LAYOUTS,
    TaskEnvironment,
    TouchscreenEnvironment,
)
from tasks.visual_search import VisualSearchTask

HUMAN_PARKED_MEANS = {
    "2x2": {"small": 1.42, "medium": 1.35, "large": 1.27},
    "2x4": {"small": 1.75, "medium": 1.72, "large": 1.65},
    "3x5": {"small": 2.49, "medium": 2.23, "large": 2.53},
}


@dataclass(frozen=True)
class ParkedTrialResult:
    """Structured output for one Parked trial."""

    layout: str
    size: str
    seed: int
    task_completion_time_s: float
    checked_buttons: int


@dataclass(frozen=True)
class ParkedConditionResult:
    """Aggregate output for one layout/size condition."""

    layout: str
    size: str
    replications: int
    model_mean_s: float
    model_sd_s: float
    human_mean_s: float
    error_s: float


def simulate_parked_trial(
    layout_key: str,
    size_key: str,
    seed: int,
    visual_config: VisualSearchConfig | None = None,
) -> ParkedTrialResult:
    """Run one deterministic-seed Parked trial."""
    config = visual_config or VisualSearchConfig()
    rng = np.random.default_rng(seed)
    touchscreen = TouchscreenEnvironment.create(layout_key, size_key, rng)
    environment = TaskEnvironment(
        touchscreen=touchscreen,
        gaze_target="device",
    )
    driver = DriverModel(visual_config=config)
    search_task = VisualSearchTask(
        environment,
        rng,
        driver.network,
        config,
    )
    driver.register_task("visual_search", search_task)
    completion_time = search_task.run()
    return ParkedTrialResult(
        layout=layout_key,
        size=size_key,
        seed=seed,
        task_completion_time_s=completion_time,
        checked_buttons=search_task.checked_button_count,
    )


def run_all_conditions(
    replications: int | None = None,
    base_seed: int = 20_150_001,
) -> list[ParkedConditionResult]:
    """Run all nine paper conditions with reproducible trial seeds."""
    repeats = replications or int(
        PAPER_DERIVED["replications_per_condition"].value
    )
    results = []
    condition_index = 0
    for layout in LAYOUTS:
        for size in BUTTON_SIZES_PX:
            condition_seed = base_seed + condition_index * 10_000
            trials = [
                simulate_parked_trial(
                    layout,
                    size,
                    condition_seed + repeat,
                )
                for repeat in range(repeats)
            ]
            values = np.asarray(
                [trial.task_completion_time_s for trial in trials],
                dtype=float,
            )
            observed = HUMAN_PARKED_MEANS[layout][size]
            model_mean = float(np.mean(values))
            results.append(
                ParkedConditionResult(
                    layout=layout,
                    size=size,
                    replications=repeats,
                    model_mean_s=model_mean,
                    model_sd_s=float(np.std(values, ddof=0)),
                    human_mean_s=observed,
                    error_s=model_mean - observed,
                )
            )
            condition_index += 1
    return results


def error_metrics(
    conditions: list[ParkedConditionResult],
) -> dict[str, float]:
    """Compute RMSE and MAPE against Chapter 3 Table 1 means."""
    errors = np.asarray([condition.error_s for condition in conditions])
    observed = np.asarray(
        [condition.human_mean_s for condition in conditions]
    )
    return {
        "rmse_s": float(math.sqrt(float(np.mean(errors**2)))),
        "mape_percent": float(
            np.mean(np.abs(errors) / observed) * 100.0
        ),
    }


def main() -> None:
    """Print JSON Lines condition records followed by aggregate error."""
    conditions = run_all_conditions()
    for condition in conditions:
        print(json.dumps(asdict(condition), ensure_ascii=False))
    print(
        json.dumps(
            {
                **error_metrics(conditions),
                "parameter_status": (
                    "RECONSTRUCTED; comparison is diagnostic, not a "
                    "successful replication claim"
                ),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
