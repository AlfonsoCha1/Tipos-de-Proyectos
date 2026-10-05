"""Pruebas de los lectores de registros (lab, syslog y csv)."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from login_counter.models import Outcome
from login_counter.parsers import (
    MAX_REPEAT,
    LineParseError,
    LogFormatError,
    ParseOptions,
    detect_format,
    normalize_ip,
    parse_lab_line,
    parse_syslog_line,
    read_log,
)
from login_counter.timeutils import load_timezone

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
UTC_2026 = ParseOptions(default_tz=timezone.utc, year=2026)
MEXICO_2026 = ParseOptions(default_tz=load_timezone("America/Mexico_City"), year=2026)


def lab(text, options=UTC_2026):
    return parse_lab_line(text, "prueba.log", 7, options)


def syslog(text, options=MEXICO_2026):
    return parse_syslog_line(text, "auth.log", 3, options)


# ---------------------------------------------------------------- lab


def test_lab_line_produces_event_in_utc():
    [event] = lab("2026-09-14T08:10:02-06:00 LOGIN_FAILURE user=admin ip=203.0.113.50 method=password")
    assert event.timestamp == datetime(2026, 9, 14, 14, 10, 2, tzinfo=timezone.utc)
    assert (event.user, event.ip, event.outcome) == ("admin", "203.0.113.50", Outcome.FAILURE)
    assert event.location == "prueba.log:7"


@pytest.mark.parametrize("text", ["", "   ", "# comentario", "  # comentario con espacios"])
def test_lab_comments_and_blank_lines_are_ignored(text):
    assert lab(text) == []


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("2026-09-14T08:00:00Z LOGIN_FAILURE user=marco", "ip="),
        ("2026-09-14T08:00:00Z LOGIN_SUCCESS user=ana ip=999.1.1.1", "IP inválida"),
        ("2026-09-31T08:00:00Z LOGIN_SUCCESS user=ana ip=192.0.2.1", "fecha inexistente"),
        ("2026-09-14T08:00:00Z LOGIN_LOCKED user=ana ip=192.0.2.1", "evento desconocido"),
        ("2026-09-14T08:00:00Z LOGIN_SUCCESS user=ana ip", "clave=valor"),
        ("texto libre", "no sigue el formato lab"),
    ],
)
def test_lab_invalid_lines_explain_the_reason(text, reason):
    with pytest.raises(LineParseError, match=reason):
        lab(text)


# ------------------------------------------------------------- syslog


def test_syslog_traditional_header_uses_year_and_timezone():
    [event] = syslog(
        "Sep 14 08:20:32 lab-server sshd[2301]: Failed password for invalid user oracle "
        "from 198.51.100.23 port 40122 ssh2"
    )
    # 08:20:32 en Ciudad de México = 14:20:32 UTC.
    assert event.timestamp == datetime(2026, 9, 14, 14, 20, 32, tzinfo=timezone.utc)
    assert (event.user, event.ip, event.outcome, event.invalid_user) == (
        "oracle", "198.51.100.23", Outcome.FAILURE, True
    )


def test_syslog_single_digit_day_with_double_space():
    [event] = syslog("Sep  4 08:00:00 srv sshd[1]: Accepted password for ana from 192.0.2.10 port 1 ssh2")
    assert event.timestamp.day == 4
    assert event.outcome is Outcome.SUCCESS


def test_syslog_iso_header():
    [event] = syslog(
        "2026-09-14T08:15:02.123456-06:00 srv sshd[9]: Accepted publickey for ana from 192.0.2.10 port 50122 ssh2"
    )
    assert event.timestamp.hour == 14


def test_syslog_accepts_sshd_session_process():
    [event] = syslog("Sep 14 09:45:00 srv sshd-session[2500]: Failed password for admin from 203.0.113.50 port 55000 ssh2")
    assert event.user == "admin"


def test_syslog_expands_message_repeated():
    events = syslog(
        "Sep 14 08:20:44 srv sshd[2305]: message repeated 3 times: "
        "[ Failed password for root from 198.51.100.23 port 40130 ssh2]"
    )
    assert len(events) == 3
    assert {e.user for e in events} == {"root"}


def test_syslog_rejects_absurd_repeat_counts():
    with pytest.raises(LineParseError, match="repetición"):
        syslog(
            f"Sep 14 08:20:44 srv sshd[1]: message repeated {MAX_REPEAT + 1} times: "
            "[ Failed password for root from 198.51.100.23 port 1 ssh2]"
        )


@pytest.mark.parametrize(
    "text",
    [
        # "Invalid user" precede al "Failed password for invalid user": contarlo duplicaría el intento.
        "Sep 14 08:20:30 srv sshd[2301]: Invalid user oracle from 198.51.100.23 port 40122",
        "Sep 14 08:21:31 srv sshd[2311]: Connection closed by invalid user guest 198.51.100.23 port 40150 [preauth]",
        "Sep 14 08:00:01 srv CRON[2101]: pam_unix(cron:session): session opened for user root(uid=0) by root(uid=0)",
        "Sep 14 09:46:00 srv sudo:      ana : TTY=pts/0 ; COMMAND=/usr/bin/apt update",
        "Sep 14 09:46:00 srv sshd[1]: Accepted key ED25519 SHA256:abc found at /home/ana/.ssh/authorized_keys:1",
    ],
)
def test_syslog_non_login_lines_are_ignored(text):
    assert syslog(text) == []


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("Sep 14 09:51:00 srv sshd[1]: Accepted password for", "incompleto"),
        ("Sep 14 09:50:00 srv sshd[1]: Failed password for root from host.example port 22 ssh2", "IP inválida"),
        ("Feb 30 09:50:00 srv sshd[1]: Failed password for root from 192.0.2.1 port 22 ssh2", "fecha inexistente"),
        ("Foo 14 09:50:00 srv sshd[1]: Failed password for root from 192.0.2.1 port 22 ssh2", "mes desconocido"),
        ("línea sin cabecera", "cabecera syslog"),
    ],
)
def test_syslog_invalid_lines_explain_the_reason(text, reason):
    with pytest.raises(LineParseError, match=reason):
        syslog(text)


# ----------------------------------------------------------------- IPs


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("192.0.2.10", "192.0.2.10"),
        ("2001:0db8:0000:0000:0000:0000:0000:0025", "2001:db8::25"),
        ("::ffff:192.0.2.1", "192.0.2.1"),
        ("[2001:db8::1]", "2001:db8::1"),
    ],
)
def test_normalize_ip(raw, expected):
    assert normalize_ip(raw) == expected


# ----------------------------------------------------- archivos y CSV


def test_detect_format_of_samples():
    assert detect_format(SAMPLES / "auth_lab.log") == "lab"
    assert detect_format(SAMPLES / "auth_syslog.log") == "syslog"
    assert detect_format(SAMPLES / "logins.csv") == "csv"


def test_detect_format_rejects_unknown_or_empty_files(tmp_path):
    unknown = tmp_path / "raro.log"
    unknown.write_text("hola\nmundo\n", encoding="utf-8")
    empty = tmp_path / "vacio.log"
    empty.write_text("", encoding="utf-8")
    for path in (unknown, empty):
        with pytest.raises(LogFormatError, match="--format"):
            detect_format(path)


def test_read_log_reports_line_numbers_of_errors():
    results = list(read_log(SAMPLES / "auth_lab.log", "lab", UTC_2026))
    errors = [r.error for r in results if r.error]
    assert [e.line_no for e in errors] == [40, 41, 42, 43, 44]
    assert all(e.source.endswith("auth_lab.log") for e in errors)


def test_csv_with_bom_crlf_and_extra_columns(tmp_path):
    path = tmp_path / "con_bom.csv"
    path.write_bytes(
        "﻿Timestamp, User ,IP,Result,Extra\r\n"
        "2026-09-14T08:00:00Z,ana,192.0.2.10,SUCCESS,x\r\n"
        "2026-09-14T08:01:00Z,ana,192.0.2.10,failure,y\r\n".encode("utf-8")
    )
    results = list(read_log(path, "csv", UTC_2026))
    assert [r.events[0].outcome for r in results] == [Outcome.SUCCESS, Outcome.FAILURE]
    assert [r.line_no for r in results] == [2, 3]


def test_csv_without_required_columns_fails_fast(tmp_path):
    path = tmp_path / "malo.csv"
    path.write_text("fecha,usuario\n2026-09-14T08:00:00Z,ana\n", encoding="utf-8")
    with pytest.raises(LogFormatError, match="faltan columnas"):
        list(read_log(path, "csv", UTC_2026))


def test_csv_empty_file_fails_fast(tmp_path):
    path = tmp_path / "vacio.csv"
    path.write_text("", encoding="utf-8")
    with pytest.raises(LogFormatError, match="vacío"):
        list(read_log(path, "csv", UTC_2026))


def test_invalid_bytes_do_not_stop_the_analysis(tmp_path):
    path = tmp_path / "bytes.log"
    path.write_bytes(
        b"2026-09-14T08:00:00Z LOGIN_SUCCESS user=ana ip=192.0.2.10\n"
        b"\xff\xfe basura binaria\n"
        b"2026-09-14T08:01:00Z LOGIN_FAILURE user=ana ip=192.0.2.10\n"
    )
    results = list(read_log(path, "lab", UTC_2026))
    assert sum(len(r.events) for r in results) == 2
    assert results[1].error is not None


def test_unknown_format_name_is_rejected():
    with pytest.raises(LogFormatError):
        list(read_log(SAMPLES / "auth_lab.log", "xml", UTC_2026))
