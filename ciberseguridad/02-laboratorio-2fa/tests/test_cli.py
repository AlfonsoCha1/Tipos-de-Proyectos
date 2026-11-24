"""Pruebas de la interfaz de línea de comandos."""

from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from totp_lab.cli import main, parse_time

PROJECT = Path(__file__).resolve().parent.parent
SECRET_FILE = str(PROJECT / "samples" / "secreto_demo.txt")
AT = "2026-11-24T10:00:00-06:00"


@pytest.fixture(autouse=True)
def no_env_secret(monkeypatch):
    monkeypatch.delenv("TOTP_SECRET", raising=False)


def test_code_with_fixed_time(capsys):
    assert main(["code", "--secret-file", SECRET_FILE, "--at", AT]) == 0
    out = capsys.readouterr().out
    assert "Código: 120159" in out
    assert "contador T = 59851200" in out


def test_verify_valid_and_invalid(capsys):
    assert main(["verify", "120159", "--secret-file", SECRET_FILE, "--at", "2026-11-24T10:00:25-06:00"]) == 0
    assert "VÁLIDO" in capsys.readouterr().out
    assert main(["verify", "000000", "--secret-file", SECRET_FILE, "--at", AT]) == 3
    assert "RECHAZADO" in capsys.readouterr().out


def test_verify_reuse(capsys):
    args = ["verify", "120159", "--secret-file", SECRET_FILE, "--at", AT, "--last-counter", "59851200"]
    assert main(args) == 3
    assert "posible repetición" in capsys.readouterr().out


def test_secret_from_environment(monkeypatch, capsys):
    monkeypatch.setenv("TOTP_SECRET", "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ")
    assert main(["code", "--at", AT]) == 0
    assert "120159" in capsys.readouterr().out


def test_secret_on_command_line_warns(capsys):
    assert main(["code", "--secret", "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ", "--at", AT]) == 0
    assert "historial" in capsys.readouterr().err


def test_missing_and_invalid_secret(tmp_path, capsys):
    assert main(["code"]) == 1
    assert "falta el secreto" in capsys.readouterr().err
    bad = tmp_path / "s.txt"
    bad.write_text("no-es-base32!\n", encoding="utf-8")
    assert main(["code", "--secret-file", str(bad)]) == 1
    assert "Base32" in capsys.readouterr().err


def test_explain_steps(capsys):
    assert main(["explain", "--secret-file", SECRET_FILE, "--at", AT]) == 0
    out = capsys.readouterr().out
    assert "7. 166120159 mod 10^6 = 120159" in out


def test_rfc_test_command(capsys):
    assert main(["rfc-test"]) == 0
    assert "18 de 18 vectores coinciden" in capsys.readouterr().out


def test_secret_save_and_no_overwrite(tmp_path, capsys):
    target = tmp_path / "secrets" / "demo.secret"
    assert main(["secret", "--save", str(target)]) == 0
    assert len(target.read_text(encoding="utf-8").strip()) == 32
    if os.name != "nt":
        assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert main(["secret", "--save", str(target)]) == 1
    assert main(["secret", "--save", str(target), "--force"]) == 0


def test_uri(capsys):
    assert main(["uri", "--secret-file", SECRET_FILE, "--account", "ana@empresa.example", "--issuer", "Lab"]) == 0
    assert capsys.readouterr().out.startswith("otpauth://totp/Lab:ana@empresa.example?secret=GEZDG")


@pytest.mark.parametrize(
    "text, expected",
    [("0", 0.0), ("59", 59.0), ("1970-01-01T00:01:00Z", 60.0), ("1970-01-01T00:00:00-06:00", 21600.0),
     ("1970-01-01T00:00:30", 30.0)],
)
def test_parse_time(text, expected):
    assert parse_time(text) == expected


def test_bad_time(capsys):
    assert main(["code", "--secret-file", SECRET_FILE, "--at", "mañana"]) == 1
    assert "fecha inválida" in capsys.readouterr().err


def test_run_as_module():
    completed = subprocess.run(
        [sys.executable, "-m", "totp_lab", "rfc-test"],
        cwd=PROJECT, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert completed.returncode == 0
    assert "OK" in completed.stdout
