"""Pruebas de la interfaz de línea de comandos y del reporte."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from file_inspector.cli import main
from file_inspector.report import clean_text

PROJECT = Path(__file__).resolve().parent.parent
SAMPLES = PROJECT / "samples"


def test_samples_with_iocs(capsys):
    assert main([str(SAMPLES / "archivos"), "--iocs", str(SAMPLES / "iocs_lab.txt")]) == 0
    out = capsys.readouterr().out
    assert "Archivos revisados: 6 | SOSPECHOSO: 1 | REVISAR: 1 | SIN INDICIOS: 4" in out
    assert "LAB-IOC-001" in out
    assert "línea 7 de la lista no es una huella válida" in out


def test_without_iocs_says_so(capsys):
    assert main([str(SAMPLES / "archivos")]) == 0
    assert "no se usó" in capsys.readouterr().out


def test_demo_mode_cleans_up(capsys):
    assert main(["--demo"]) == 0
    out = capsys.readouterr().out
    assert "SOSPECHOSO: 5 | REVISAR: 2 | SIN INDICIOS: 1" in out
    assert "pago\\u202efdp.exe" in out  # el truco se muestra escapado
    assert "‮" not in out


def test_all_hashes(capsys):
    assert main([str(SAMPLES / "archivos" / "notas.txt"), "--all-hashes"]) == 0
    out = capsys.readouterr().out
    assert "SHA-1:" in out and "MD5:" in out


def test_fail_on(capsys):
    args = [str(SAMPLES / "archivos"), "--iocs", str(SAMPLES / "iocs_lab.txt")]
    assert main(args + ["--fail-on", "sospechoso"]) == 3
    assert main([str(SAMPLES / "archivos" / "notas.txt"), "--fail-on", "revisar"]) == 0


def test_export_json_and_force(tmp_path, capsys):
    out = tmp_path / "r.json"
    assert main(["--demo", "--export-json", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(data["files"]) == 8
    assert {"md5", "sha1", "sha256", "findings"} <= set(data["files"][0])
    assert main(["--demo", "--export-json", str(out)]) == 1
    assert main(["--demo", "--export-json", str(out), "--force"]) == 0


def test_missing_ioc_file(tmp_path, capsys):
    assert main([str(SAMPLES / "archivos"), "--iocs", str(tmp_path / "no.txt")]) == 1
    assert "No existe la lista" in capsys.readouterr().err


def test_missing_path_is_reported(tmp_path, capsys):
    assert main([str(tmp_path / "nada.bin")]) == 0
    assert "No revisados: 1" in capsys.readouterr().out


def test_no_arguments_is_usage_error(capsys):
    try:
        main([])
    except SystemExit as exc:
        assert exc.code == 2
    else:  # pragma: no cover
        raise AssertionError("debió terminar con código 2")


def test_clean_text_escapes_controls():
    assert clean_text("a\x1b[2Jb") == "a\\x1b[2Jb"
    assert clean_text("x‮y") == "x\\u202ey"


def test_run_as_module():
    completed = subprocess.run(
        [sys.executable, "-m", "file_inspector", "--demo"],
        cwd=PROJECT, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert completed.returncode == 0
    assert "factura_noviembre.pdf.exe" in completed.stdout
