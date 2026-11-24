"""Pruebas de la interfaz: simulación por defecto, confirmación, --undo y --demo."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from file_organizer.cli import main

PROJECT = Path(__file__).resolve().parent.parent
SAMPLES = PROJECT / "samples" / "descargas_demo"


@pytest.fixture
def downloads(tmp_path):
    copy = tmp_path / "Descargas"
    shutil.copytree(SAMPLES, copy)
    return copy


def files_in(folder: Path) -> set[str]:
    return {p.name for p in folder.iterdir()}


def test_default_is_simulation(downloads, capsys):
    before = files_in(downloads)
    assert main([str(downloads)]) == 0
    assert "Simulación: no se movió nada" in capsys.readouterr().out
    assert files_in(downloads) == before


def test_apply_requires_typing_si(downloads, capsys):
    before = files_in(downloads)
    assert main([str(downloads), "--apply"], ask=lambda q: "no") == 0
    assert "Cancelado" in capsys.readouterr().out
    assert files_in(downloads) == before


def test_eof_on_confirmation_cancels(downloads, capsys):
    def no_input(question):
        raise EOFError

    assert main([str(downloads), "--apply"], ask=no_input) == 0
    assert "Cancelado" in capsys.readouterr().out


def test_apply_and_undo_round_trip(downloads, capsys):
    before = {p.relative_to(downloads) for p in downloads.rglob("*")}
    assert main([str(downloads), "--apply"], ask=lambda q: "si") == 0
    out = capsys.readouterr().out
    assert "Movidos: 13 | fallidos: 0" in out
    journal = next(downloads.glob(".organizador_journal_*.json"))

    assert main(["--undo", str(journal)]) == 0  # simulación del undo
    assert "Simulación" in capsys.readouterr().out
    assert main(["--undo", str(journal), "--apply", "--yes"]) == 0
    assert "Devueltos: 13 | fallidos: 0" in capsys.readouterr().out
    after = {p.relative_to(downloads) for p in downloads.rglob("*") if not p.name.startswith(".organizador_journal_")}
    assert after == before


def test_yes_without_apply_is_usage_error(downloads):
    with pytest.raises(SystemExit) as info:
        main([str(downloads), "--yes"])
    assert info.value.code == 2


def test_needs_exactly_one_mode(downloads):
    with pytest.raises(SystemExit):
        main([])
    with pytest.raises(SystemExit):
        main([str(downloads), "--demo"])


def test_bad_config(tmp_path, downloads, capsys):
    bad = tmp_path / "c.json"
    bad.write_text('{"categories": {"Docs": ["pdf"]}}', encoding="utf-8")
    assert main([str(downloads), "--config", str(bad)]) == 1
    assert "empiecen con punto" in capsys.readouterr().err


def test_missing_folder(tmp_path, capsys):
    assert main([str(tmp_path / "nada")]) == 1


def test_demo_leaves_samples_untouched(capsys):
    before = {p.relative_to(SAMPLES) for p in SAMPLES.rglob("*")}
    assert main(["--demo"]) == 0
    out = capsys.readouterr().out
    assert "Movidos: 13 | fallidos: 0" in out and "Devueltos: 13 | fallidos: 0" in out
    assert {p.relative_to(SAMPLES) for p in SAMPLES.rglob("*")} == before


def test_run_as_module():
    completed = subprocess.run(
        [sys.executable, "-m", "file_organizer", "samples/descargas_demo"],
        cwd=PROJECT, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert completed.returncode == 0
    assert "Movimientos planeados: 13" in completed.stdout
