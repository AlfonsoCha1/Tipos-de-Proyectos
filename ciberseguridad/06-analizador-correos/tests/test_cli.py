"""Pruebas de la interfaz de línea de comandos y del reporte."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from email_analyzer.cli import main

PROJECT = Path(__file__).resolve().parent.parent
SAMPLES = PROJECT / "samples"


def test_folder_summary_and_error(capsys):
    assert main([str(SAMPLES)]) == 0
    out = capsys.readouterr().out
    assert "Resumen" in out
    assert "02_phishing_banco.eml          100/100  ALTO" in out
    assert "No analizado:" in out and "06_no_es_correo.eml" in out


def test_links_are_defanged(capsys):
    main([str(SAMPLES / "02_phishing_banco.eml")])
    out = capsys.readouterr().out
    assert "hxxp://198[.]51[.]100[.]77" in out
    assert "http://198.51.100.77" not in out


def test_text_flag_reads_eml_as_text(capsys):
    assert main([str(SAMPLES / "06_no_es_correo.eml"), "--text"]) == 0
    assert "mensaje de texto" in capsys.readouterr().out


def test_fail_on(capsys):
    assert main([str(SAMPLES / "02_phishing_banco.eml"), "--fail-on", "alto"]) == 3
    assert main([str(SAMPLES / "04_boletin_acortador.eml"), "--fail-on", "medio"]) == 0


def test_export_json_iocs(tmp_path, capsys):
    out = tmp_path / "iocs.json"
    assert main([str(SAMPLES / "02_phishing_banco.eml"), str(SAMPLES / "03_factura_con_adjunto.eml"),
                 "--export-json", str(out)]) == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    first, second = data["messages"]
    assert first["domains"] == ["198.51.100.77"]
    assert len(second["attachments"][0]["sha256"]) == 64
    assert main([str(SAMPLES / "02_phishing_banco.eml"), "--export-json", str(out)]) == 1


def test_only_errors_returns_one(tmp_path, capsys):
    assert main([str(tmp_path / "nada.eml")]) == 1
    assert "no existe" in capsys.readouterr().out


def test_bad_config(tmp_path, capsys):
    bad = tmp_path / "c.json"
    bad.write_text('{"protected_domains": {"X": ["sin-punto"]}}', encoding="utf-8")
    assert main([str(SAMPLES / "01_legitimo_estado_cuenta.eml"), "--config", str(bad)]) == 1
    assert "protected_domains" in capsys.readouterr().err


def test_control_characters_in_subject_are_escaped(tmp_path, capsys):
    path = tmp_path / "m.eml"
    path.write_bytes(b"From: a@b.example\nSubject: =?utf-8?q?hola=1B=5B2J?=\n\ncuerpo\n")
    main([str(path)])
    out = capsys.readouterr().out
    assert "\\x1b[2J" in out and "\x1b" not in out


def test_run_as_module():
    completed = subprocess.run(
        [sys.executable, "-m", "email_analyzer", "samples"],
        cwd=PROJECT, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert completed.returncode == 0
    assert "riesgo ALTO" in completed.stdout
