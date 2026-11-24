"""Pruebas de la interfaz de línea de comandos."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from file_validator.cli import main

PROJECT = Path(__file__).resolve().parent.parent
SAMPLES = PROJECT / "samples"


def test_samples_exit_code_and_summary(capsys):
    assert main([str(SAMPLES / "subidas")]) == 3
    out = capsys.readouterr().out
    assert "Revisados: 10 | aceptados: 5 | rechazados: 5" in out
    assert "Por qué importa" in out


def test_all_accepted_returns_zero(capsys):
    assert main([str(SAMPLES / "subidas" / "notas.txt")]) == 0


def test_name_only_mode(capsys):
    assert main(["--name", "CON.txt", "--name", "informe.pdf"]) == 3
    out = capsys.readouterr().out
    assert "(solo nombre)" in out
    assert "Nombre seguro sugerido: _CON.txt" in out


def test_no_content_flag(capsys):
    assert main([str(SAMPLES / "subidas" / "comprobante.pdf"), "--no-content"]) == 0


def test_strict_config(capsys):
    assert main([str(SAMPLES / "subidas"), "--config", str(SAMPLES / "reglas_estrictas.json")]) == 3
    assert "aceptados: 2" in capsys.readouterr().out


def test_export_json_and_force(tmp_path, capsys):
    out = tmp_path / "v.json"
    assert main([str(SAMPLES / "subidas"), "--export-json", str(out)]) == 3
    data = json.loads(out.read_text(encoding="utf-8"))
    assert sum(r["accepted"] for r in data["results"]) == 5
    assert main([str(SAMPLES / "subidas"), "--export-json", str(out)]) == 1
    assert "ya existe" in capsys.readouterr().err


def test_missing_config_is_error(tmp_path, capsys):
    assert main(["--name", "a.pdf", "--config", str(tmp_path / "no.json")]) == 1


def test_missing_path_is_reported(tmp_path, capsys):
    assert main([str(tmp_path / "no-existe.pdf")]) == 0
    assert "No revisados: 1" in capsys.readouterr().out


def test_no_arguments_is_usage_error():
    with pytest.raises(SystemExit) as info:
        main([])
    assert info.value.code == 2


def test_control_characters_are_escaped(capsys):
    main(["--name", "pago‮fdp.exe", "--name", "a\x1b[2J.txt"])
    out = capsys.readouterr().out
    assert "pago\\u202efdp.exe" in out and "\\x1b[2J" in out
    assert "‮" not in out and "\x1b" not in out


def test_run_as_module():
    completed = subprocess.run(
        [sys.executable, "-m", "file_validator", "samples/subidas", "--name", "factura.pdf.exe"],
        cwd=PROJECT, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert completed.returncode == 3
    assert "DOBLE_EXTENSION" in completed.stdout
