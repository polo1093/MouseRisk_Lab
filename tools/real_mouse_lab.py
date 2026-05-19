#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ctypes
import math
import random
import time
from dataclasses import dataclass
from typing import Callable, Iterable, Optional, Sequence, Tuple

import requests
from pyclick import HumanClicker


Point = Tuple[int, int]
Region = Tuple[int, int, int, int]
_VK_F12 = 0x7B
DEFAULT_CLICK_RATE_HZ = 0.7


@dataclass(frozen=True)
class RunResult:
    count: int
    scores: list[float]


def emergency_stop_requested() -> bool:
    try:
        return bool(ctypes.windll.user32.GetAsyncKeyState(_VK_F12) & 0x8000)
    except AttributeError:
        return False


def check_emergency_stop() -> None:
    if emergency_stop_requested():
        raise SystemExit("Emergency stop requested with F12")


def interruptible_sleep(seconds: float, step: float = 0.05) -> None:
    deadline = time.monotonic() + max(0.0, seconds)
    while True:
        check_emergency_stop()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(step, remaining))


def pace_click(started_at: float, rate_hz: float = DEFAULT_CLICK_RATE_HZ) -> None:
    interval = 1.0 / max(0.1, rate_hz)
    elapsed = time.monotonic() - started_at
    interruptible_sleep(max(0.0, interval - elapsed))


def parse_region(value: str) -> Region:
    parts = [part.strip() for part in value.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("region must use x1,y1,x2,y2")
    x1, y1, x2, y2 = (int(part) for part in parts)
    if x2 <= x1 or y2 <= y1:
        raise argparse.ArgumentTypeError("region requires x2 > x1 and y2 > y1")
    return x1, y1, x2, y2


def center(region: Region) -> Point:
    x1, y1, x2, y2 = region
    return ((x1 + x2) // 2, (y1 + y2) // 2)


def random_point(region: Region, margin: int = 12) -> Point:
    x1, y1, x2, y2 = region
    return (
        random.randint(x1 + margin, x2 - margin),
        random.randint(y1 + margin, y2 - margin),
    )


def grid_points(region: Region, count: int) -> list[Point]:
    x1, y1, x2, y2 = region
    cols = max(2, math.ceil(math.sqrt(count)))
    rows = max(2, math.ceil(count / cols))
    points: list[Point] = []
    for row in range(rows):
        for col in range(cols):
            if len(points) >= count:
                return points
            x = int(x1 + ((col + 0.5) / cols) * (x2 - x1))
            y = int(y1 + ((row + 0.5) / rows) * (y2 - y1))
            points.append((x, y))
    return points


def health_check(base_url: str) -> None:
    response = requests.get(f"{base_url}/api/health", timeout=2)
    response.raise_for_status()
    if response.json().get("ok") is not True:
        raise SystemExit("Health check failed")


def fetch_latest_event(base_url: str, session_id: Optional[str]) -> Optional[dict]:
    params: dict[str, object] = {"limit": 1}
    if session_id:
        params["session_id"] = session_id
    response = requests.get(f"{base_url}/api/telemetry", params=params, timeout=2)
    response.raise_for_status()
    events = response.json()
    if not events:
        return None
    return events[-1]


def sleep_between(min_delay: float, max_delay: float) -> None:
    interruptible_sleep(random.uniform(min_delay, max_delay))


class RealMouseActor:
    def __init__(self) -> None:
        self.clicker = HumanClicker()

    def human_move_click(self, point: Point, min_duration: float, max_duration: float) -> None:
        check_emergency_stop()
        self.clicker.move(point, random.uniform(min_duration, max_duration))
        interruptible_sleep(random.uniform(0.04, 0.18))
        check_emergency_stop()
        self.clicker.click()

    def linear_move_click(self, point: Point, duration: float) -> None:
        check_emergency_stop()
        self.clicker.move(point, duration)
        check_emergency_stop()
        self.clicker.click()

    def teleport_click(self, point: Point) -> None:
        check_emergency_stop()
        self.clicker.move(point, 0.01)
        check_emergency_stop()
        self.clicker.click()

    def double_click(self, point: Point, duration: float) -> None:
        check_emergency_stop()
        self.clicker.move(point, duration)
        check_emergency_stop()
        self.clicker.click()
        interruptible_sleep(random.uniform(0.03, 0.08))
        check_emergency_stop()
        self.clicker.click()


def iter_points(mode: str, region: Region, count: int) -> Iterable[Point]:
    if mode == "grid":
        yield from grid_points(region, count)
        return
    if mode == "center":
        for _ in range(count):
            yield center(region)
        return
    for _ in range(count):
        yield random_point(region)


def print_event(index: int, event: Optional[dict]) -> Optional[float]:
    if not event:
        print(f"{index:02d} no telemetry yet")
        return None

    score = float(event["bot_probability"])
    signals = event.get("signals") or {}
    mouse = signals.get("mouse_heuristic_v1", {}).get("score")
    botd = signals.get("botd_v2", {}).get("score")
    mouse_text = "?" if mouse is None else f"{float(mouse):.3f}"
    botd_text = "?" if botd is None else f"{float(botd):.3f}"
    print(
        f"{index:02d} score={score:.3f} mouse={mouse_text} botd={botd_text} "
        f"reason={event.get('reason')} session={event.get('session_id')}"
    )
    return score


def run_profile(
    *,
    mode: str,
    actor: RealMouseActor,
    region: Region,
    count: int,
    base_url: str,
    session_id: Optional[str],
    min_delay: float,
    max_delay: float,
) -> RunResult:
    scores: list[float] = []
    points = list(iter_points(mode, region, count))

    for index, point in enumerate(points, start=1):
        click_started_at = time.monotonic()
        check_emergency_stop()
        if mode == "human":
            actor.human_move_click(point, min_duration=0.35, max_duration=0.9)
        elif mode == "linear":
            actor.linear_move_click(point, duration=0.35)
        elif mode == "teleport":
            actor.teleport_click(point)
        elif mode == "double":
            actor.double_click(point, duration=0.25)
        elif mode in {"grid", "center"}:
            actor.linear_move_click(point, duration=0.35)
        else:
            raise ValueError(f"unsupported mode: {mode}")

        interruptible_sleep(0.25)
        score = print_event(index, fetch_latest_event(base_url, session_id))
        if score is not None:
            scores.append(score)
        if index < len(points):
            pace_click(click_started_at)

    return RunResult(count=len(points), scores=scores)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Real screen mouse/click lab for MouseRisk Lab"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--region", required=True, type=parse_region)
    parser.add_argument(
        "--mode",
        choices=["human", "linear", "teleport", "grid", "center", "double"],
        default="human",
    )
    parser.add_argument("--count", type=int, default=12)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--focus-wait", type=float, default=4.0)
    parser.add_argument("--min-delay", type=float, default=0.25)
    parser.add_argument("--max-delay", type=float, default=0.8)
    parser.add_argument("--skip-health-check", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.count < 1:
        raise SystemExit("--count must be >= 1")

    if not args.skip_health_check:
        health_check(args.base_url)

    print(f"Mode: {args.mode}")
    print(f"Region: {args.region}")
    print(f"Focus the browser window. Starting in {args.focus_wait:.1f}s...")
    interruptible_sleep(args.focus_wait)

    result = run_profile(
        mode=args.mode,
        actor=RealMouseActor(),
        region=args.region,
        count=args.count,
        base_url=args.base_url,
        session_id=args.session_id,
        min_delay=args.min_delay,
        max_delay=args.max_delay,
    )

    if not result.scores:
        print("Summary: no score received")
        return

    avg = sum(result.scores) / len(result.scores)
    print(
        f"Summary: clicks={result.count} scores={len(result.scores)} "
        f"avg={avg:.3f} min={min(result.scores):.3f} max={max(result.scores):.3f}"
    )


if __name__ == "__main__":
    main()
