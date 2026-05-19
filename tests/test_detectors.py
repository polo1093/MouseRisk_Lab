from __future__ import annotations

from types import SimpleNamespace

import requests

from detectors.botd_v2 import BotdV2
from detectors.external_fe_bot_v1 import ExternalFeBotV1
from detectors.heuristic_mouse_v1 import HeuristicMouseV1


def payload(**overrides: object) -> SimpleNamespace:
    defaults = {
        "webdriver": False,
        "plugins_len": 3,
        "languages_len": 2,
        "std_dt": 20.0,
        "straightness": 0.8,
        "mean_abs_turn": 0.5,
        "max_speed": 1200.0,
        "trusted_ratio": 1.0,
        "n": 40,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_mouse_heuristic_keeps_normal_payload_low_risk() -> None:
    result = HeuristicMouseV1().score(payload())

    assert result["score"] == 0.0
    assert result["raw"]["risk"] == 0.0


def test_mouse_heuristic_scores_obvious_automation_signals() -> None:
    result = HeuristicMouseV1().score(
        payload(
            webdriver=True,
            plugins_len=0,
            languages_len=1,
            std_dt=1.0,
            straightness=0.999,
            mean_abs_turn=0.01,
            max_speed=14000.0,
            trusted_ratio=0.70,
        )
    )

    assert result["score"] == 1.0
    assert result["raw"]["risk"] > 1.0


def test_mouse_heuristic_reduces_confidence_for_small_window() -> None:
    large_window = HeuristicMouseV1().score(payload(std_dt=1.0, n=40))
    small_window = HeuristicMouseV1().score(payload(std_dt=1.0, n=10))

    assert large_window["score"] == 0.18
    assert small_window["score"] == 0.135


def test_botd_scores_detected_bot_as_high_risk() -> None:
    detector = BotdV2()

    result = detector.score(SimpleNamespace(botd_bot=True, botd_kind="webdriver"))

    assert result["score"] == 0.95
    assert result["raw"] == {"bot": True, "kind": "webdriver"}


def test_botd_scores_human_or_unknown_as_zero() -> None:
    detector = BotdV2()

    human = detector.score(SimpleNamespace(botd_bot=False, botd_kind=None))
    unknown = detector.score(SimpleNamespace(botd_bot=None, botd_kind=None))

    assert human["score"] == 0.0
    assert unknown["score"] == 0.0


def test_external_fe_bot_handles_incomplete_payload() -> None:
    detector = ExternalFeBotV1(url="http://127.0.0.1:1/predict/fe", timeout=0.01)
    incomplete = SimpleNamespace(
        session_id=None,
        duration_ms=None,
        mousemove_teleport_count=None,
        mousemove_count=None,
    )

    result = detector.score(incomplete)

    assert 0.0 <= result["score"] <= 1.0
    assert result["raw"]["status"] == "external_error"


def test_external_fe_bot_handles_unavailable_api() -> None:
    detector = ExternalFeBotV1(url="http://127.0.0.1:1/predict/fe", timeout=0.01)

    result = detector.score(
        payload(
            session_id="session-a",
            duration_ms=5320,
            mousemove_teleport_count=7,
            mousemove_count=21,
        )
    )

    assert 0.0 <= result["score"] <= 1.0
    assert result["score"] == 0.0
    assert result["raw"]["status"] == "external_error"


def test_external_fe_bot_sends_expected_payload(monkeypatch) -> None:
    captured = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "model_type": "fe",
                "label": "bot",
                "bot_score": 0.913245,
                "threshold": 0.5,
                "model_name": "XGBClassifier",
            }

    def fake_post(url: str, json: dict, timeout: float) -> FakeResponse:
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(requests, "post", fake_post)
    detector = ExternalFeBotV1(url="http://example.test/predict/fe")

    result = detector.score(
        payload(
            session_id="session_abc123",
            duration_ms=5320,
            mousemove_teleport_count=7,
            mousemove_count=21,
        )
    )

    assert captured["url"] == "http://example.test/predict/fe"
    assert captured["json"] == {
        "X-Session-Ticket": "session_abc123",
        "showScheduleId": 101,
        "duration_ms": 5320,
        "mousemove_teleport_count": 7,
        "mousemove_count": 21,
    }
    assert captured["timeout"] == 1.5
    assert result["score"] == 0.913245
    assert result["raw"]["status"] == "ok"
    assert result["raw"]["model_name"] == "XGBClassifier"
