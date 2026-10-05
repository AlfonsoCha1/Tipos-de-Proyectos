"""Pruebas de la lógica de conteo con los datos sintéticos de samples/."""

from datetime import datetime, timezone
from pathlib import Path

from login_counter.counter import LoginCounter, Tally, analyze_files, ranked
from login_counter.models import LoginEvent, Outcome
from login_counter.parsers import ParseOptions
from login_counter.timeutils import load_timezone

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
UTC_2026 = ParseOptions(default_tz=timezone.utc, year=2026)
MEXICO_2026 = ParseOptions(default_tz=load_timezone("America/Mexico_City"), year=2026)


def test_lab_sample_totals():
    summary = analyze_files([SAMPLES / "auth_lab.log"], "auto", UTC_2026)
    [stats] = summary.files
    assert (stats.fmt, stats.lines, stats.events, stats.ignored, stats.unparsed) == ("lab", 44, 29, 10, 5)
    assert (summary.totals.success, summary.totals.failure) == (6, 23)
    assert round(summary.failure_rate, 1) == 79.3


def test_lab_sample_by_user_and_ip():
    summary = analyze_files([SAMPLES / "auth_lab.log"], "lab", UTC_2026)
    assert summary.by_user["admin"] == Tally(success=1, failure=7)
    assert summary.by_user["luis"] == Tally(success=2, failure=6)
    assert summary.by_ip["198.51.100.23"] == Tally(success=0, failure=6)
    assert summary.by_ip["2001:db8::25"] == Tally(success=1, failure=0)
    # "marco" solo aparece en una línea inválida: no debe contarse.
    assert "marco" not in summary.by_user


def test_first_and_last_seen_ignore_file_order_and_depend_on_timezone():
    # La línea de "sofia" no trae zona horaria. Si se asume UTC queda como
    # el evento más temprano; si se asume Ciudad de México, no.
    assumed_utc = analyze_files([SAMPLES / "auth_lab.log"], "lab", UTC_2026)
    assumed_mexico = analyze_files([SAMPLES / "auth_lab.log"], "lab", MEXICO_2026)
    assert assumed_utc.first_seen == datetime(2026, 9, 14, 10, 0, tzinfo=timezone.utc)
    assert assumed_mexico.first_seen == datetime(2026, 9, 14, 13, 58, 12, tzinfo=timezone.utc)
    assert assumed_mexico.last_seen == datetime(2026, 9, 14, 17, 6, 40, tzinfo=timezone.utc)


def test_syslog_sample_counts_repeats_and_invalid_users():
    summary = analyze_files([SAMPLES / "auth_syslog.log"], "auto", MEXICO_2026)
    [stats] = summary.files
    assert (stats.fmt, stats.events, stats.ignored, stats.unparsed) == ("syslog", 13, 5, 3)
    assert (summary.totals.success, summary.totals.failure) == (3, 10)
    assert summary.by_user["root"].failure == 3  # 1 línea + "message repeated 2 times"
    assert summary.invalid_user_failures == 3


def test_several_files_are_combined():
    paths = [SAMPLES / "auth_lab.log", SAMPLES / "auth_syslog.log", SAMPLES / "logins.csv"]
    summary = analyze_files(paths, "auto", MEXICO_2026)
    assert [f.fmt for f in summary.files] == ["lab", "syslog", "csv"]
    assert summary.totals.total == 29 + 13 + 5
    assert summary.unparsed_total == 5 + 3 + 2


def test_unparsed_lines_are_capped_but_still_counted():
    summary = analyze_files([SAMPLES / "auth_lab.log"], "lab", UTC_2026, max_unparsed_kept=2)
    assert summary.unparsed_total == 5
    assert len(summary.unparsed) == 2


def test_ranked_orders_by_failures_then_total_then_name():
    tallies = {"b": Tally(0, 2), "a": Tally(0, 2), "c": Tally(5, 1), "d": Tally(1, 2)}
    assert [key for key, _ in ranked(tallies)] == ["d", "a", "b", "c"]
    assert [key for key, _ in ranked(tallies, top=2)] == ["d", "a"]


def test_counter_handles_unordered_events():
    counter = LoginCounter()
    late = datetime(2026, 9, 14, 12, tzinfo=timezone.utc)
    early = datetime(2026, 9, 14, 8, tzinfo=timezone.utc)
    for moment in (late, early):
        counter.add_event(LoginEvent(moment, "ana", "192.0.2.1", Outcome.FAILURE, "x", 1))
    summary = counter.summary()
    assert (summary.first_seen, summary.last_seen) == (early, late)
    assert summary.totals == Tally(0, 2)
