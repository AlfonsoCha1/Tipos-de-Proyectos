"""Pruebas de la interfaz de línea de comandos (cli.py y report.py)."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

from duplicate_finder.cli import main
from duplicate_finder.report import clean_text, safe_csv_cell

PROJECT = Path(__file__).resolve().parent.parent
SAMPLES = PROJECT / "samples" / "carpeta_demo"


def test_samples_output(capsys):
    assert main([str(SAMPLES)]) == 0
    out = capsys.readouterr().out
    assert "Grupos de duplicados: 2 | copias sobrantes: 3" in out
    assert "copia de reporte_q3.txt" in out
    assert "no borra nada" in out


def test_top_limits_groups(capsys):
    assert main([str(SAMPLES), "--top", "1"]) == 0
    out = capsys.readouterr().out
    assert "Grupo 2:" not in out
    assert "1 grupos más" in out


def test_exports_and_force(tmp_path, capsys):
    json_out = tmp_path / "r.json"
    csv_out = tmp_path / "r.csv"
    assert main([str(SAMPLES), "--export-json", str(json_out), "--export-csv", str(csv_out)]) == 0
    data = json.loads(json_out.read_text(encoding="utf-8"))
    assert data["duplicate_files"] == 3 and len(data["groups"]) == 2
    rows = list(csv.reader(csv_out.open(encoding="utf-8-sig")))
    assert rows[0] == ["grupo", "sha256", "tamano_bytes", "ruta"]
    assert len(rows) == 1 + 5
    # Sin --force no se sobrescribe
    assert main([str(SAMPLES), "--export-json", str(json_out)]) == 1
    assert "ya existe" in capsys.readouterr().err
    assert main([str(SAMPLES), "--export-json", str(json_out), "--force"]) == 0


def test_missing_folder_is_error(tmp_path, capsys):
    assert main([str(tmp_path / "nada")]) == 1
    assert "No existe" in capsys.readouterr().err


def test_negative_min_size_is_error(capsys):
    assert main([str(SAMPLES), "--min-size", "-1"]) == 1


def test_bad_config(tmp_path, capsys):
    bad = tmp_path / "c.json"
    bad.write_text("{no json", encoding="utf-8")
    assert main([str(SAMPLES), "--config", str(bad)]) == 1
    assert "no es JSON válido" in capsys.readouterr().err


def test_malicious_file_name_is_neutralized_in_csv(tmp_path, monkeypatch, capsys):
    (tmp_path / "=HYPERLINK(1).txt").write_bytes(b"igual")
    (tmp_path / "normal.txt").write_bytes(b"igual")
    monkeypatch.chdir(tmp_path)  # rutas relativas: la celda empieza con "="
    assert main([".", "--export-csv", "salida/d.csv"]) == 0
    rows = list(csv.reader((tmp_path / "salida" / "d.csv").open(encoding="utf-8-sig")))
    assert "'=HYPERLINK(1).txt" in [row[3] for row in rows]


def test_text_cleaning_helpers():
    assert clean_text("a\x1b[31mb") == "a\\x1b[31mb"
    assert safe_csv_cell("=1+1") == "'=1+1"
    assert safe_csv_cell("normal") == "normal"


def test_run_as_module():
    completed = subprocess.run(
        [sys.executable, "-m", "duplicate_finder", "samples/carpeta_demo"],
        cwd=PROJECT, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert completed.returncode == 0
    assert "Grupos de duplicados: 2" in completed.stdout
