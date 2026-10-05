"""Pruebas de extremo a extremo con los datos sintéticos de samples/."""

import csv
import json
import subprocess
import sys
from pathlib import Path

from failed_login_detector.cli import main
from failed_login_detector.report import clean_text, safe_csv_cell

PROJECT = Path(__file__).resolve().parent.parent
SAMPLES = PROJECT / "samples"
LAB = str(SAMPLES / "auth_lab.log")


def test_lab_sample_default_settings(capsys):
    assert main([LAB, "--display-tz", "America/Mexico_City"]) == 0
    output = capsys.readouterr().out
    assert "Alertas: 2" in output
    assert "[1] Severidad ALTA - Cuenta 'admin'" in output
    assert "7 intentos fallidos entre 2026-09-14 08:10:02-06:00 y 2026-09-14 08:13:30-06:00" in output
    assert "IPs de origen (2): 203.0.113.50, 203.0.113.51" in output
    assert "[2] Severidad MEDIA - IP '198.51.100.23'" in output
    assert "no bloquea" in output


def test_wider_window_finds_slower_burst(capsys):
    # Los 5 fallos de "luis" duran 6 minutos: solo aparecen con una ventana mayor.
    assert main([LAB, "--window", "10"]) == 0
    output = capsys.readouterr().out
    assert "Alertas: 4" in output
    assert "Cuenta 'luis'" in output


def test_rules_and_threshold_from_command_line(capsys):
    assert main([LAB, "--by", "ip"]) == 0
    output = capsys.readouterr().out
    assert "Alertas: 1" in output
    assert "Cuenta 'admin'" not in output

    assert main([LAB, "--threshold", "8"]) == 0
    assert "Alertas: 0" in capsys.readouterr().out


def test_syslog_sample(capsys):
    assert main([str(SAMPLES / "auth_syslog.log"), "--year", "2026", "--tz", "America/Mexico_City"]) == 0
    output = capsys.readouterr().out
    assert "Alertas: 1" in output
    assert "IP '198.51.100.23'" in output
    assert "líneas 5, 6, 7 (x2), 8, 9" in output


def test_multi_source_correlation_across_timezones(capsys):
    # servidor_web.log (-06:00) tiene 3 fallos de "elena" y vpn.csv (UTC, ya en
    # el día siguiente) tiene 2. Por separado no alertan; juntos sí.
    web = str(SAMPLES / "multi_fuente" / "servidor_web.log")
    vpn = str(SAMPLES / "multi_fuente" / "vpn.csv")
    for single in (web, vpn):
        assert main([single]) == 0
        assert "Alertas: 0" in capsys.readouterr().out

    assert main([web, vpn, "--display-tz", "America/Mexico_City"]) == 0
    output = capsys.readouterr().out
    assert "Alertas: 1" in output
    assert "[1] Severidad ALTA - Cuenta 'elena'" in output
    assert "5 intentos fallidos entre 2026-09-15 22:01:10-06:00 y 2026-09-15 22:04:05-06:00" in output
    assert "Acceso EXITOSO 1 min 25 s después del último fallo" in output


def test_normal_activity_has_no_alerts(capsys):
    assert main([str(SAMPLES / "normal_activity.log")]) == 0
    assert "Alertas: 0" in capsys.readouterr().out


def test_exports(tmp_path, capsys):
    json_path = tmp_path / "salida" / "alertas.json"
    csv_path = tmp_path / "salida" / "alertas.csv"
    assert main([LAB, "--export-json", str(json_path), "--export-csv", str(csv_path)]) == 0

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["settings"]["threshold"] == 5
    assert data["stats"]["events"] == 29
    first = data["alerts"][0]
    assert (first["rule"], first["key"], first["severity"], first["failures"]) == ("user", "admin", "alta", 7)
    assert first["first_seen_utc"] == "2026-09-14T14:10:02+00:00"
    assert first["success_after"]["ip"] == "203.0.113.51"
    assert first["explanation"]

    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert [row["key"] for row in rows] == ["admin", "198.51.100.23"]


def test_exports_do_not_overwrite_without_force(tmp_path, capsys):
    target = tmp_path / "alertas.json"
    target.write_text("previo", encoding="utf-8")
    assert main([LAB, "--export-json", str(target)]) == 1
    assert target.read_text(encoding="utf-8") == "previo"
    assert main([LAB, "--export-json", str(target), "--force"]) == 0


def test_invalid_parameters_return_error(capsys):
    assert main([LAB, "--threshold", "1"]) == 1
    assert "umbral" in capsys.readouterr().err
    assert main([LAB, "--window", "0"]) == 1
    assert main([LAB, "--tz", "Marte/Olympus"]) == 1


def test_invalid_config_returns_error(tmp_path, capsys):
    config = tmp_path / "config.json"
    config.write_text('{"rules": ["mac"]}', encoding="utf-8")
    assert main([LAB, "--config", str(config)]) == 1
    assert "'rules'" in capsys.readouterr().err


def test_missing_file_returns_error(tmp_path, capsys):
    assert main([str(tmp_path / "no_existe.log")]) == 1
    assert "No existe el archivo" in capsys.readouterr().err


def test_untrusted_text_is_neutralized(tmp_path, capsys):
    log = tmp_path / "malicioso.log"
    lines = [f"2026-09-14T08:0{m}:00Z LOGIN_FAILURE user=\x1b[2J=cmd ip=192.0.2.9" for m in range(5)]
    log.write_text("\n".join(lines) + "\n", encoding="utf-8")
    csv_path = tmp_path / "a.csv"
    assert main([str(log), "--export-csv", str(csv_path)]) == 0
    assert "\x1b" not in capsys.readouterr().out
    assert clean_text("a\x1bb") == "a\\x1bb"
    assert safe_csv_cell("=cmd") == "'=cmd"


def test_module_runs_as_script():
    completed = subprocess.run(
        [sys.executable, "-m", "failed_login_detector", "--help"],
        cwd=PROJECT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0
    assert "--window" in completed.stdout
