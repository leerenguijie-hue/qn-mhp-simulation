"""Run one minimal TC1–TC9 visual-search trial."""
from __future__ import annotations

import argparse
import json

from qn_mhp import run_visual_search


def parse_args() -> argparse.Namespace:
    """Parse command-line inputs."""
    parser = argparse.ArgumentParser(
        description="Minimal synchronous QN-MHP USB visual search"
    )
    parser.add_argument(
        "--labels",
        default="AM1,FM1,USB,DVD,AM2,FM2,MP3,CD",
        help="Comma-separated button labels; include the target exactly once.",
    )
    parser.add_argument("--target", default="USB")
    parser.add_argument("--seed", type=int, default=2)
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Omit entity and server traces.",
    )
    return parser.parse_args()


def main() -> None:
    """Print a structured JSON result."""
    args = parse_args()
    labels = [label.strip() for label in args.labels.split(",") if label.strip()]
    result = run_visual_search(
        labels,
        target_label=args.target,
        seed=args.seed,
    )
    output = result.to_dict()
    if args.summary_only:
        output = {
            "completion_time_s": result.completion_time_s,
            "clicked_index": result.clicked_index,
            "examined_indices": list(result.examined_indices),
            "tc_sequence": [record.tc for record in result.tc_trace],
        }
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
