from __future__ import annotations

import time
from typing import Callable, Optional, TypeVar

from tools.real_mouse_lab import (
    DEFAULT_POST_CLICK_WAIT,
    fetch_latest_event,
    health_check,
    interruptible_sleep,
    pace_click,
    print_event,
)


T = TypeVar("T")


def run_click_protocol(
    *,
    count: int,
    base_url: str,
    session_id: Optional[str],
    focus_wait: float,
    click_once: Callable[[int], T],
    format_result: Optional[Callable[[int, T], str]] = None,
    fetch_telemetry_each_click: bool = True,
) -> None:
    """Protocole standard: focus, clics, pacing et lecture telemetrie."""

    health_check(base_url)
    if focus_wait:
        print(f"Starting in {focus_wait:.1f}s...")
        interruptible_sleep(focus_wait)

    for index in range(1, count + 1):
        click_started_at = time.monotonic()
        result = click_once(index)
        interruptible_sleep(DEFAULT_POST_CLICK_WAIT)
        if fetch_telemetry_each_click:
            event = fetch_latest_event(base_url, session_id)
            print_event(index, event)
        if format_result is not None:
            print(format_result(index, result))
        if index < count:
            pace_click(click_started_at)
