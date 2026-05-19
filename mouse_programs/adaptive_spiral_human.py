from __future__ import annotations

import argparse
import math
import random
import sys
import time
from pathlib import Path
from typing import Iterable, Optional, Tuple

import pyautogui

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.real_mouse_lab import (
    DEFAULT_POST_CLICK_WAIT,
    check_emergency_stop,
    fetch_latest_event,
    health_check,
    interruptible_sleep,
    pace_click,
    parse_region,
    print_event,
)


Point = Tuple[int, int]
Region = Tuple[int, int, int, int]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Human-like adversarial mouse program with curved and spiral paths"
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--region", required=True, type=parse_region)
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--focus-wait", type=float, default=3.0)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--min-duration", type=float, default=0.12)
    parser.add_argument("--max-duration", type=float, default=0.28)
    parser.add_argument("--spiral-radius", type=float, default=28.0)
    parser.add_argument("--jitter", type=float, default=4.0)
    return parser.parse_args()


def clamp_point(point: tuple[float, float], region: Region, margin: int = 8) -> Point:
    x1, y1, x2, y2 = region
    x = min(max(point[0], x1 + margin), x2 - margin)
    y = min(max(point[1], y1 + margin), y2 - margin)
    return round(x), round(y)


def random_target(region: Region) -> Point:
    x1, y1, x2, y2 = region
    width = x2 - x1
    height = y2 - y1
    # Avoid only uniform randomness: people tend to click useful zones, not edges.
    if random.random() < 0.65:
        cx = random.uniform(x1 + width * 0.22, x2 - width * 0.22)
        cy = random.uniform(y1 + height * 0.22, y2 - height * 0.22)
    else:
        cx = random.uniform(x1 + 24, x2 - 24)
        cy = random.uniform(y1 + 24, y2 - 24)
    return round(cx), round(cy)


def cubic_bezier(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> tuple[float, float]:
    u = 1.0 - t
    x = (u**3 * p0[0]) + (3 * u**2 * t * p1[0]) + (3 * u * t**2 * p2[0]) + (t**3 * p3[0])
    y = (u**3 * p0[1]) + (3 * u**2 * t * p1[1]) + (3 * u * t**2 * p2[1]) + (t**3 * p3[1])
    return x, y


def ease_in_out(t: float) -> float:
    return 0.5 - (math.cos(math.pi * t) / 2.0)


def control_points(start: Point, end: Point, region: Region) -> tuple[Point, Point]:
    sx, sy = start
    ex, ey = end
    dx = ex - sx
    dy = ey - sy
    distance = max(1.0, math.hypot(dx, dy))
    nx = -dy / distance
    ny = dx / distance
    bend = random.uniform(-0.28, 0.28) * distance
    p1 = (sx + dx * random.uniform(0.25, 0.45) + nx * bend, sy + dy * random.uniform(0.15, 0.35) + ny * bend)
    p2 = (sx + dx * random.uniform(0.58, 0.82) - nx * bend * 0.55, sy + dy * random.uniform(0.62, 0.90) - ny * bend * 0.55)
    return clamp_point(p1, region), clamp_point(p2, region)


def path_to_target(start: Point, end: Point, region: Region, duration: float, spiral_radius: float) -> Iterable[Point]:
    p1, p2 = control_points(start, end, region)
    steps = max(32, int(duration * random.uniform(58, 86)))
    previous: Optional[Point] = None
    spiral_turns = random.uniform(8.0, 11.0)
    noise_phase = random.uniform(0.0, math.tau)
    noise_amplitude = random.uniform(0.02, 0.12)

    for index in range(steps):
        progress = index / max(1, steps - 1)
        eased = ease_in_out(progress)
        point = cubic_bezier(start, p1, p2, end, eased)

        if progress > 0.82:
            settle = min(1.0, max(0.0, (progress - 0.82) / 0.18))
            radius = spiral_radius * (1.0 - settle) ** 1.45
            angle = settle * spiral_turns * math.pi
            point = (
                point[0] + math.cos(angle) * radius,
                point[1] + math.sin(angle) * radius * 0.72,
            )

        noise = (1.0 - progress) * math.sin((progress * math.tau) + noise_phase) * noise_amplitude
        candidate = clamp_point((point[0] + noise, point[1] - noise * 0.6), region)
        if candidate != previous:
            previous = candidate
            yield candidate


def move_path(points: Iterable[Point], duration: float) -> None:
    points = list(points)
    if not points:
        return
    base_sleep = duration / len(points)
    for point in points:
        check_emergency_stop()
        pyautogui.moveTo(point[0], point[1], duration=max(0.004, base_sleep * 0.65))
        interruptible_sleep(max(0.001, base_sleep * random.uniform(0.10, 0.45)), step=0.01)


def settle_and_click(target: Point, region: Region, jitter: float) -> None:
    loops = random.randint(1, 3)
    for _ in range(loops):
        check_emergency_stop()
        jx = random.uniform(-jitter, jitter) * 0.45
        jy = random.uniform(-jitter, jitter) * 0.45
        point = clamp_point((target[0] + jx, target[1] + jy), region)
        pyautogui.moveTo(point[0], point[1], duration=random.uniform(0.035, 0.09))
        interruptible_sleep(random.uniform(0.02, 0.075), step=0.01)
    check_emergency_stop()
    pyautogui.click()


def run(args: argparse.Namespace) -> None:
    if args.seed is not None:
        random.seed(args.seed)

    pyautogui.PAUSE = 0
    pyautogui.FAILSAFE = True
    health_check(args.base_url)
    print(
        "Program: adaptive_spiral_human | "
        f"clicks={args.count} | region={args.region} | failsafe=screen-corner"
    )
    if args.focus_wait:
        print(f"Starting in {args.focus_wait:.1f}s...")
        interruptible_sleep(args.focus_wait)

    for index in range(1, args.count + 1):
        click_started_at = time.monotonic()
        check_emergency_stop()
        start = pyautogui.position()
        target = random_target(args.region)
        duration = random.uniform(args.min_duration, args.max_duration)
        move_path(
            path_to_target(start, target, args.region, duration, args.spiral_radius),
            duration,
        )
        settle_and_click(target, args.region, args.jitter)
        interruptible_sleep(DEFAULT_POST_CLICK_WAIT)
        event = fetch_latest_event(args.base_url, args.session_id)
        print_event(index, event)
        if index < args.count:
            pace_click(click_started_at)


def main() -> None:
    args = parse_args()
    if args.count < 1:
        raise SystemExit("--count must be >= 1")
    if args.min_duration <= 0 or args.max_duration < args.min_duration:
        raise SystemExit("duration range is invalid")
    run(args)


if __name__ == "__main__":
    main()
