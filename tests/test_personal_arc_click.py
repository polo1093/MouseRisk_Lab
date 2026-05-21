from __future__ import annotations

import mouse_programs.personal_arc_click as arc


def test_click_point_overshoots_then_returns_and_clicks(monkeypatch) -> None:
    moves: list[arc.Point] = []
    clicks: list[str] = []
    arc_calls: list[tuple[arc.Point, arc.Point, float, int | None]] = []

    monkeypatch.setattr(arc.pyautogui, "position", lambda: (10, 50))
    monkeypatch.setattr(arc.pyautogui, "moveTo", lambda x, y, **_kwargs: moves.append((x, y)))
    monkeypatch.setattr(arc.pyautogui, "click", lambda *, button: clicks.append(button))
    monkeypatch.setattr(arc, "interruptible_sleep", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(arc, "check_emergency_stop", lambda: None)
    monkeypatch.setattr(
        arc,
        "choose_overshoot_point",
        lambda *_args, **_kwargs: (130, 50),
    )

    def fake_arc_points(
        start: arc.Point,
        end: arc.Point,
        _region: arc.Region,
        *,
        duration: float,
        arc_scale: float,
        side: int | None = None,
    ) -> list[arc.Point]:
        arc_calls.append((start, end, arc_scale, side))
        return [end]

    monkeypatch.setattr(arc, "arc_points", fake_arc_points)

    result = arc.click_point(
        (100, 50),
        button="right",
        region=(0, 0, 200, 100),
        min_duration=0.01,
        max_duration=0.01,
        settle_min=0.0,
        settle_max=0.0,
    )

    assert result.start == (10, 50)
    assert result.target == (100, 50)
    assert result.overshoot == (130, 50)
    assert result.clicked is True
    assert moves == [(130, 50), (100, 50)]
    assert clicks == ["right"]
    assert arc_calls[0][0:2] == ((10, 50), (130, 50))
    assert arc_calls[1][0:2] == ((130, 50), (100, 50))
    assert arc_calls[1][3] == -arc_calls[0][3]


def test_click_zone_chooses_point_and_calls_click_point(monkeypatch) -> None:
    calls: list[tuple[object, ...]] = []
    expected = arc.ArcClickResult(
        start=(1, 1),
        target=(55, 65),
        overshoot=(70, 70),
        movement_region=(10, 20, 110, 120),
        button="left",
        clicked=True,
    )

    monkeypatch.setattr(arc, "random_target", lambda region: (region[0] + 45, region[1] + 45))

    def fake_click_point(*args: object, **kwargs: object) -> arc.ArcClickResult:
        calls.append((*args, kwargs))
        return expected

    monkeypatch.setattr(arc, "click_point", fake_click_point)

    result = arc.click_zone(
        region=(10, 20, 110, 120),
        button="left",
        min_duration=0.02,
        max_duration=0.03,
        arc_scale=1.4,
        return_arc_scale=0.8,
        overshoot_min=15.0,
        overshoot_max=40.0,
        settle_min=0.0,
        settle_max=0.0,
    )

    assert result == expected
    assert calls == [
        (
            (55, 65),
            {
                "button": "left",
                "region": (10, 20, 110, 120),
                "min_duration": 0.02,
                "max_duration": 0.03,
                "arc_scale": 1.4,
                "return_arc_scale": 0.8,
                "overshoot_min": 15.0,
                "overshoot_max": 40.0,
                "settle_min": 0.0,
                "settle_max": 0.0,
            },
        )
    ]


def test_moveTo_uses_arc_move_without_clicking(monkeypatch) -> None:
    calls: list[tuple[object, ...]] = []

    def fake_move_to_point(*args: object, **kwargs: object) -> tuple[arc.Point, arc.Point, arc.Point]:
        calls.append((*args, kwargs))
        return (10, 10), (80, 90), (100, 100)

    monkeypatch.setattr(arc, "move_to_point", fake_move_to_point)

    result = arc.moveTo(
        (80, 90),
        region=(0, 0, 120, 120),
        min_duration=0.02,
        max_duration=0.03,
        arc_scale=1.4,
        return_arc_scale=0.7,
        overshoot_min=18.0,
        overshoot_max=45.0,
    )

    assert result == (80, 90)
    assert calls == [
        (
            (80, 90),
            {
                "region": (0, 0, 120, 120),
                "min_duration": 0.02,
                "max_duration": 0.03,
                "arc_scale": 1.4,
                "return_arc_scale": 0.7,
                "overshoot_min": 18.0,
                "overshoot_max": 45.0,
            },
        )
    ]


def test_choose_overshoot_point_goes_beyond_target() -> None:
    arc.random.seed(4)

    overshoot = arc.choose_overshoot_point(
        (10, 50),
        (100, 50),
        (0, 0, 220, 120),
        overshoot_min=25.0,
        overshoot_max=25.0,
    )

    assert overshoot[0] > 100
    assert abs(overshoot[1] - 50) <= 5


def test_arc_points_end_on_target() -> None:
    arc.random.seed(7)

    points = list(
        arc.arc_points(
            (10, 40),
            (140, 85),
            (0, 0, 200, 120),
            duration=0.08,
            arc_scale=1.25,
            side=1,
        )
    )

    assert points
    assert points[-1] == (140, 85)
