from __future__ import annotations

import argparse
import random
import sys
import time
from pathlib import Path
from typing import Callable

import pyautogui

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.real_mouse_lab import (
    check_emergency_stop,
    health_check,
    interruptible_sleep,
    pace_click,
    parse_region,
    random_point,
)


Tween = Callable[[float], float]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simple PyAutoGUI moveTo tween with explicit left mouse down/up"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--region", required=True, type=parse_region)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--focus-wait", type=float, default=3.0)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--min-duration", type=float, default=0.18)
    parser.add_argument("--max-duration", type=float, default=0.42)
    parser.add_argument("--hold-min", type=float, default=0.035)
    parser.add_argument("--hold-max", type=float, default=0.095)
    parser.add_argument(
        "--tween",
        choices=("ease-in-out-quad", "ease-out-quad", "linear"),
        default="ease-in-out-quad",
    )
    return parser.parse_args()


def select_tween(name: str) -> Tween:
    if name == "ease-out-quad":
        return pyautogui.easeOutQuad
    if name == "linear":
        return pyautogui.linear
    return pyautogui.easeInOutQuad


def left_down_up(hold_seconds: float) -> None:
    check_emergency_stop()
    pyautogui.mouseDown(button="left")
    interruptible_sleep(hold_seconds, step=0.01)
    check_emergency_stop()
    pyautogui.mouseUp(button="left")


def run(args: argparse.Namespace) -> None:
    if args.seed is not None:
        random.seed(args.seed)
    if args.count < 1:
        raise SystemExit("--count must be >= 1")
    if args.min_duration <= 0 or args.max_duration < args.min_duration:
        raise SystemExit("duration range is invalid")
    if args.hold_min < 0 or args.hold_max < args.hold_min:
        raise SystemExit("hold range is invalid")

    pyautogui.PAUSE = 0
    pyautogui.FAILSAFE = True
    tween = select_tween(args.tween)
    health_check(args.base_url)

    print(
        "Program: pyautogui_moveto_down_up | "
        f"clicks={args.count} | region={args.region} | tween={args.tween}"
    )
    if args.focus_wait:
        print(f"Starting in {args.focus_wait:.1f}s...")
        interruptible_sleep(args.focus_wait)

    for index in range(1, args.count + 1):
        click_started_at = time.monotonic()
        check_emergency_stop()
        point = random_point(args.region, margin=18)
        duration = random.uniform(args.min_duration, args.max_duration)
        hold_seconds = random.uniform(args.hold_min, args.hold_max)

        pyautogui.moveTo(point[0], point[1], duration=duration, tween=tween)
        left_down_up(hold_seconds)
        print(
            f"{index:02d} moveTo {point} duration={duration:.3f}s "
            f"hold={hold_seconds:.3f}s"
        )

        if index < args.count:
            pace_click(click_started_at)


def main() -> None:
    run(parse_args())


if __name__ == "__main__":
    main()
