"""Pruebas de la ventana deslizante con eventos construidos a mano.

Cada prueba documenta un caso que hay que saber explicar en una entrevista:
umbral exacto, límite de la ventana, desorden, zonas horarias, ráfagas
separadas, reglas por cuenta y por IP, y acceso exitoso posterior.
"""

import random
from datetime import datetime, timedelta, timezone

import pytest

from failed_login_detector.detector import DetectionSettings, count_out_of_order, detect
from failed_login_detector.models import LoginEvent, Outcome

START = datetime(2026, 9, 14, 14, 0, tzinfo=timezone.utc)
DEFAULT = DetectionSettings(threshold=5, window=timedelta(minutes=5), success_after=timedelta(minutes=15))


def event(minute, user="admin", ip="203.0.113.50", outcome=Outcome.FAILURE, line=1):
    return LoginEvent(START + timedelta(minutes=minute), user, ip, outcome, "prueba.log", line)


def failures(minutes, **kwargs):
    return [event(m, line=i + 1, **kwargs) for i, m in enumerate(minutes)]


def user_alerts(result):
    return [a for a in result.alerts if a.rule == "user"]


def test_below_threshold_does_not_alert():
    assert detect(failures([0, 1, 2, 3]), DEFAULT).alerts == []


def test_exactly_threshold_alerts():
    [alert] = user_alerts(detect(failures([0, 1, 2, 3, 4]), DEFAULT))
    assert (alert.key, alert.failures, alert.severity) == ("admin", 5, "media")
    assert alert.duration == timedelta(minutes=4)


def test_window_limit_is_inclusive():
    # Primer y último fallo separados exactamente 5 min: cuenta.
    assert user_alerts(detect(failures([0, 1, 2, 3, 5]), DEFAULT))
    # Separados 5 min y 1 s: no cuenta.
    events = failures([0, 1, 2, 3]) + [event(5 + 1 / 60)]
    assert user_alerts(detect(events, DEFAULT)) == []


def test_continuous_burst_produces_a_single_alert():
    # 12 fallos, uno por minuto: la ráfaga nunca se interrumpe.
    [alert] = user_alerts(detect(failures(range(12)), DEFAULT))
    assert alert.failures == 12
    assert alert.first_seen == START
    assert alert.last_seen == START + timedelta(minutes=11)


def test_separate_bursts_produce_separate_alerts():
    events = failures([0, 1, 2, 3, 4]) + failures([60, 61, 62, 63, 64])
    alerts = user_alerts(detect(events, DEFAULT))
    assert [a.failures for a in alerts] == [5, 5]


def test_failures_below_threshold_inside_a_burst_are_not_lost():
    # Ventana de 5 min: el fallo del minuto 0 sale antes de que se complete
    # la ráfaga; los minutos 3..7 forman la alerta y el 8 la amplía.
    [alert] = user_alerts(detect(failures([0, 3, 4, 5, 6, 7, 8]), DEFAULT))
    assert alert.failures == 6
    assert alert.first_seen == START + timedelta(minutes=3)


def test_unordered_input_gives_same_result_as_ordered():
    ordered = failures([0, 1, 2, 3, 4, 30, 31])
    shuffled = ordered[:]
    random.Random(7).shuffle(shuffled)
    expected = [(a.key, a.failures, a.first_seen) for a in detect(ordered, DEFAULT).alerts]
    actual = [(a.key, a.failures, a.first_seen) for a in detect(shuffled, DEFAULT).alerts]
    assert actual == expected
    assert count_out_of_order(ordered) == 0
    assert count_out_of_order(shuffled) > 0


def test_mixed_timezones_are_compared_in_utc():
    mexico = timezone(timedelta(hours=-6))
    # Mismo instante expresado de dos formas: 08:00-06:00 == 14:00Z.
    events = [
        LoginEvent(datetime(2026, 9, 14, 8, minute, tzinfo=mexico).astimezone(timezone.utc),
                   "admin", "203.0.113.50", Outcome.FAILURE, "a.log", minute)
        for minute in (0, 1, 2)
    ] + [
        LoginEvent(datetime(2026, 9, 14, 14, minute, tzinfo=timezone.utc),
                   "admin", "203.0.113.50", Outcome.FAILURE, "b.log", minute)
        for minute in (3, 4)
    ]
    [alert] = user_alerts(detect(events, DEFAULT))
    assert alert.failures == 5
    assert {source for source, _ in alert.evidence} == {"a.log", "b.log"}


def test_user_rule_catches_attack_rotating_ips():
    events = [event(m, ip=f"203.0.113.{50 + m}") for m in range(5)]
    result = detect(events, DEFAULT)
    assert [a.rule for a in result.alerts] == ["user"]
    assert len(result.alerts[0].related) == 5


def test_ip_rule_catches_password_spraying():
    events = [event(m, user=f"cuenta{m}", ip="198.51.100.23") for m in range(6)]
    result = detect(events, DEFAULT)
    assert [(a.rule, a.key, a.failures) for a in result.alerts] == [("ip", "198.51.100.23", 6)]
    assert result.alerts[0].related == {f"cuenta{m}" for m in range(6)}


def test_rules_can_be_limited():
    events = failures(range(5))
    only_ip = DetectionSettings(rules=("ip",))
    assert [a.rule for a in detect(events, only_ip).alerts] == ["ip"]


def test_success_after_burst_raises_severity():
    events = failures(range(5)) + [event(10, ip="203.0.113.99", outcome=Outcome.SUCCESS, line=99)]
    [alert] = user_alerts(detect(events, DEFAULT))
    assert alert.severity == "alta"
    assert alert.success_after.location == "prueba.log:99"


def test_success_during_burst_is_detected():
    # El éxito ocurre antes de que exista la alerta (entre el fallo 2 y el 3).
    events = failures(range(5)) + [event(2.5, outcome=Outcome.SUCCESS)]
    [alert] = user_alerts(detect(events, DEFAULT))
    assert alert.success_after is not None


def test_success_too_late_or_before_is_not_linked():
    events = (
        [event(-1, outcome=Outcome.SUCCESS)]  # antes de la ráfaga
        + failures(range(5))
        + [event(4 + 16, outcome=Outcome.SUCCESS)]  # 16 min después del último fallo
    )
    [alert] = user_alerts(detect(events, DEFAULT))
    assert alert.success_after is None


def test_evidence_is_capped():
    settings = DetectionSettings(max_evidence=3)
    [alert] = user_alerts(detect(failures(range(8)), settings))
    assert alert.failures == 8
    assert len(alert.evidence) == 3


@pytest.mark.parametrize(
    "kwargs",
    [
        {"threshold": 1},
        {"window": timedelta(0)},
        {"success_after": timedelta(minutes=-1)},
        {"rules": ()},
        {"rules": ("mac",)},
        {"max_evidence": 0},
    ],
)
def test_invalid_settings_are_rejected(kwargs):
    with pytest.raises(ValueError):
        DetectionSettings(**kwargs)


def test_statistics():
    events = failures([0, 1]) + [event(3, outcome=Outcome.SUCCESS)]
    result = detect(events, DEFAULT)
    assert (result.total_events, result.failures, result.successes) == (3, 2, 1)
