"""Pruebas de la interfaz de terminal y de las exportaciones."""

import csv
import json
import subprocess
import sys
from pathlib import Path

from login_counter.cli import main
from login_counter.report import clean_text, safe_csv_cell

PROJECT = Path(__file__).resolve().parent.parent
SAMPLES = PROJECT / "samples"
LAB = str(SAMPLES / "auth_lab.log")


def test_main_prints_summary(capsys):
    assert main([LAB]) == 0
    output = capsys.readouterr().out
    assert "Intentos: 29 | exitosos: 6 | fallidos: 23 (79.3 % de fallos)" in output
    assert "Líneas no interpretadas: 5" in output


def test_top_limits_rows(capsys):
    assert main([LAB, "--top", "2"]) == 0
    output = capsys.readouterr().out
    assert "Por usuario (top 2" in output
    assert "usa --top 0 para ver todos" in output


def test_exports_json_and_csv(tmp_path, capsys):
    json_path = tmp_path / "salida" / "resumen.json"
    csv_path = tmp_path / "salida" / "conteos.csv"
    args = [str(SAMPLES / "logins.csv"), "--export-json", str(json_path), "--export-csv", str(csv_path)]
    assert main(args) == 0

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["totals"] == {"success": 2, "failure": 3, "total": 5}
    assert data["unparsed_total"] == 2
    assert data["first_seen_utc"] == "2026-09-14T14:00:00+00:00"

    with csv_path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    keys = {row["key"] for row in rows if row["dimension"] == "user"}
    # El usuario malicioso "=HYPERLINK(1)" se exporta neutralizado.
    assert "'=HYPERLINK(1)" in keys
    assert "=HYPERLINK(1)" not in keys


def test_exports_do_not_overwrite_without_force(tmp_path, capsys):
    target = tmp_path / "resumen.json"
    target.write_text("datos previos", encoding="utf-8")
    assert main([LAB, "--export-json", str(target)]) == 1
    assert "--force" in capsys.readouterr().err
    assert target.read_text(encoding="utf-8") == "datos previos"

    assert main([LAB, "--export-json", str(target), "--force"]) == 0
    assert json.loads(target.read_text(encoding="utf-8"))["totals"]["total"] == 29


def test_missing_file_returns_error(tmp_path, capsys):
    assert main([str(tmp_path / "no_existe.log")]) == 1
    assert "No existe el archivo" in capsys.readouterr().err


def test_invalid_timezone_returns_error(capsys):
    assert main([LAB, "--tz", "Marte/Olympus"]) == 1
    assert "Zona horaria desconocida" in capsys.readouterr().err


def test_invalid_config_returns_error(tmp_path, capsys):
    config = tmp_path / "config.json"
    config.write_text('{"top": -1}', encoding="utf-8")
    assert main([LAB, "--config", str(config)]) == 1
    assert "'top'" in capsys.readouterr().err

    config.write_text('{"topp": 3}', encoding="utf-8")
    assert main([LAB, "--config", str(config)]) == 1
    assert "Claves desconocidas" in capsys.readouterr().err


def test_untrusted_text_is_neutralized():
    assert clean_text("admin\x1b[2J") == "admin\\x1b[2J"
    assert safe_csv_cell("=1+1") == "'=1+1"
    assert safe_csv_cell("ana") == "ana"
    assert safe_csv_cell(5) == 5


def test_module_runs_as_script():
    # Comprueba el punto de entrada real: python -m login_counter
    completed = subprocess.run(
        [sys.executable, "-m", "login_counter", "--help"],
        cwd=PROJECT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    assert completed.returncode == 0
    assert "--export-json" in completed.stdout
