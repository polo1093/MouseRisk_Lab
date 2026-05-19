from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.real_mouse_lab import (
    DEFAULT_CLICK_RATE_HZ,
    RealMouseActor,
    grid_points,
    health_check,
    interruptible_sleep,
    pace_click,
    parse_region,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Linear mouse moves with regular clicks")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--region", required=True, type=parse_region)
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--focus-wait", type=float, default=3.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    health_check(args.base_url)
    actor = RealMouseActor()
    points = grid_points(args.region, args.count)
    print(
        "Program: linear_sweep_clicks | "
        f"clicks={len(points)} | rate={DEFAULT_CLICK_RATE_HZ:.2f}/s | region={args.region}"
    )
    if args.focus_wait:
        print(f"Starting in {args.focus_wait:.1f}s...")
        interruptible_sleep(args.focus_wait)

    for index, point in enumerate(points, start=1):
        click_started_at = time.monotonic()
        actor.linear_move_click(point, duration=0.35)
        print(f"{index:02d} linear-clicked {point}")
        if index < len(points):
            pace_click(click_started_at)


if __name__ == "__main__":
    main()
