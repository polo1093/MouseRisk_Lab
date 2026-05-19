from __future__ import annotations

import mouse_programs.adaptive_spiral_human_plus as plus


def test_click_point_uses_requested_mouse_button(monkeypatch) -> None:
    clicks: list[str] = []

    monkeypatch.setattr(plus.pyautogui, "position", lambda: (10, 10))
    monkeypatch.setattr(plus.pyautogui, "moveTo", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(plus.pyautogui, "click", lambda *, button: clicks.append(button))
    monkeypatch.setattr(plus, "interruptible_sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(plus, "check_emergency_stop", lambda: None)

    delayed = plus.click_point(
        (80, 80),
        button="right",
        region=(0, 0, 100, 100),
        min_duration=0.01,
        max_duration=0.01,
    )

    assert delayed is False
    assert clicks == ["right"]


def test_click_zone_clicks_inside_active_zone(monkeypatch) -> None:
    events: list[tuple[str, object]] = []

    monkeypatch.setattr(plus.pyautogui, "position", lambda: (0, 0))
    monkeypatch.setattr(plus.pyautogui, "moveTo", lambda x, y, **_kwargs: events.append(("move", (x, y))))
    monkeypatch.setattr(plus.pyautogui, "mouseDown", lambda *, button: events.append(("down", button)))
    monkeypatch.setattr(plus.pyautogui, "mouseUp", lambda *, button: events.append(("up", button)))
    boxes = iter([(0, 0, 100, 100), (40, 40, 60, 60)])
    monkeypatch.setattr(plus, "random_inner_box", lambda _region, _scale: next(boxes))
    monkeypatch.setattr(plus, "path_to_target", lambda *_args, **_kwargs: [(10, 10), (45, 45), (55, 55)])
    monkeypatch.setattr(plus, "interruptible_sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(plus, "check_emergency_stop", lambda: None)

    result = plus.click_zone(
        region=(0, 0, 100, 100),
        target_point=(50, 50),
        button="left",
        inner_box_scale=1.0,
        click_box_scale=0.40,
        min_duration=0.01,
        max_duration=0.01,
    )

    assert result.movement_region == (0, 0, 100, 100)
    assert result.click_region == (40, 40, 60, 60)
    assert result.target == (50, 50)
    assert result.button == "left"
    assert result.clicked is True
    assert result.click_point == (45, 45)
    assert result.delayed is False
    assert events == [
        ("move", (10, 10)),
        ("move", (45, 45)),
        ("down", "left"),
        ("up", "left"),
    ]


def test_move_to_alias_uses_humanized_move(monkeypatch) -> None:
    calls: list[tuple[object, ...]] = []

    def fake_move_to_point(*args: object, **kwargs: object) -> plus.Point:
        calls.append((*args, kwargs))
        return (80, 90)

    monkeypatch.setattr(plus, "move_to_point", fake_move_to_point)

    result = plus.moveTo(
        (80, 90),
        region=(0, 0, 100, 100),
        min_duration=0.02,
        max_duration=0.03,
        spiral_radius=5.0,
    )

    assert result == (80, 90)
    assert calls == [
        (
            (80, 90),
            {
                "region": (0, 0, 100, 100),
                "min_duration": 0.02,
                "max_duration": 0.03,
                "spiral_radius": 5.0,
            },
        )
    ]


def test_move_to_zone_stops_at_random_point(monkeypatch) -> None:
    calls: list[tuple[object, ...]] = []

    monkeypatch.setattr(plus, "random_target", lambda region: (region[0] + 10, region[1] + 20))

    def fake_move_to_point(*args: object, **kwargs: object) -> plus.Point:
        calls.append((*args, kwargs))
        return (20, 40)

    monkeypatch.setattr(plus, "move_to_point", fake_move_to_point)

    result = plus.moveTozone(
        (10, 20, 110, 120),
        min_duration=0.04,
        max_duration=0.08,
        spiral_radius=7.0,
    )

    assert result == (20, 40)
    assert calls == [
        (
            (20, 40),
            {
                "region": (10, 20, 110, 120),
                "min_duration": 0.04,
                "max_duration": 0.08,
                "spiral_radius": 7.0,
            },
        )
    ]


def test_random_inner_box_stays_inside_region() -> None:
    plus.random.seed(3)

    box = plus.random_inner_box((10, 20, 110, 220), 0.35)

    assert box[0] >= 10
    assert box[1] >= 20
    assert box[2] <= 110
    assert box[3] <= 220
    assert box[2] - box[0] == 35
    assert box[3] - box[1] == 70
