"""Pruebas de la checklist: plantilla, avance, guardado seguro e interfaz."""

from __future__ import annotations

import csv
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

from security_checklist.cli import export_text, main
from security_checklist.store import (
    ChecklistError,
    load_checklist,
    load_template,
    mark,
    save_checklist,
)

PROJECT = Path(__file__).resolve().parent.parent


@pytest.fixture
def state(tmp_path):
    return tmp_path / "avance.json"


def test_template_is_valid():
    tasks = load_template()
    assert len(tasks) == 18
    assert len({t.id for t in tasks}) == 18


def test_first_run_everything_pending(state):
    checklist = load_checklist(None, state)
    assert checklist.counts()["pendiente"] == 18
    assert checklist.percent_done() == 0
    assert not state.exists()  # leer no crea archivos


def test_mark_save_and_reload(state):
    checklist = load_checklist(None, state)
    mark(checklist, "cuentas-01", "hecho", "con app")
    mark(checklist, "red-03", "no_aplica")
    save_checklist(checklist, state)
    reloaded = load_checklist(None, state)
    assert reloaded.get("cuentas-01").status == "hecho"
    assert reloaded.get("cuentas-01").note == "con app"
    assert reloaded.get("cuentas-01").updated
    assert reloaded.percent_done() == pytest.approx(100 / 17)  # "no aplica" no cuenta


def test_saved_file_only_keeps_changed_items(state):
    checklist = load_checklist(None, state)
    mark(checklist, "equipo-01", "hecho")
    save_checklist(checklist, state)
    data = json.loads(state.read_text(encoding="utf-8"))
    assert list(data["items"]) == ["equipo-01"]
    assert not state.with_name(state.name + ".tmp").exists()


@pytest.mark.parametrize("task_id, status, message", [("no-existe", "hecho", "no existe la tarea"), ("equipo-01", "listo", "estado inválido")])
def test_mark_errors(state, task_id, status, message):
    with pytest.raises(ChecklistError, match=message):
        mark(load_checklist(None, state), task_id, status)


def test_note_too_long(state):
    with pytest.raises(ChecklistError, match="máximo"):
        mark(load_checklist(None, state), "equipo-01", "hecho", "x" * 501)


def test_damaged_state_is_not_overwritten(state):
    state.write_text("{roto", encoding="utf-8")
    with pytest.raises(ChecklistError, match="No se sobrescribió"):
        load_checklist(None, state)
    assert main(["--file", str(state), "mark", "equipo-01", "hecho"]) == 1
    assert state.read_text(encoding="utf-8") == "{roto"


def test_invalid_status_in_state(state):
    state.write_text(json.dumps({"items": {"equipo-01": {"estado": "quizas"}}}), encoding="utf-8")
    with pytest.raises(ChecklistError, match="estado inválido"):
        load_checklist(None, state)


def test_orphan_ids_are_kept_and_reported(state, capsys):
    state.write_text(json.dumps({"items": {"vieja-01": {"estado": "hecho"}}}), encoding="utf-8")
    assert main(["--file", str(state), "progress"]) == 0
    assert "vieja-01" in capsys.readouterr().err


def test_template_errors(tmp_path):
    bad = tmp_path / "t.json"
    bad.write_text(json.dumps({"items": [{"id": "a", "categoria": "x", "tarea": "t", "por_que": "p"},
                                         {"id": "a", "categoria": "x", "tarea": "t", "por_que": "p"},
                                         {"id": "b"}]}), encoding="utf-8")
    with pytest.raises(ChecklistError) as info:
        load_template(bad)
    assert "id repetido" in str(info.value) and "falta categoria" in str(info.value)


def test_cli_flow(state, capsys):
    assert main(["--file", str(state), "mark", "equipo-02", "en_progreso", "--note", "falta la llave"]) == 0
    assert main(["--file", str(state), "list", "--status", "en_progreso"]) == 0
    out = capsys.readouterr().out
    assert "[~] equipo-02" in out and "Nota: falta la llave" in out
    assert main(["--file", str(state), "progress"]) == 0
    assert "Siguiente sugerida: cuentas-01" in capsys.readouterr().out


def test_reset_needs_yes(state, capsys):
    main(["--file", str(state), "mark", "equipo-01", "hecho"])
    assert main(["--file", str(state), "reset"]) == 0
    assert load_checklist(None, state).get("equipo-01").status == "hecho"
    assert main(["--file", str(state), "reset", "--yes"]) == 0
    assert load_checklist(None, state).get("equipo-01").status == "pendiente"


def test_export_markdown_and_csv(state, tmp_path, capsys):
    checklist = load_checklist(None, state)
    mark(checklist, "cuentas-01", "hecho", "<script>x</script>")
    mark(checklist, "cuentas-02", "en_progreso", "=HYPERLINK(1)")
    md = export_text(checklist, "md")
    assert "- [x] Activar verificación en dos pasos" in md
    assert "&lt;script&gt;" in md and "<script>" not in md
    rows = list(csv.reader(io.StringIO(export_text(checklist, "csv"))))
    assert rows[0][0] == "id" and len(rows) == 19
    assert rows[2][4] == "'=HYPERLINK(1)"
    out = tmp_path / "c.md"
    assert main(["--file", str(state), "export", "--output", str(out)]) == 0
    assert main(["--file", str(state), "export", "--output", str(out)]) == 1
    assert main(["--file", str(state), "export", "--output", str(out), "--force"]) == 0


def test_control_characters_in_notes_are_escaped(state, capsys):
    main(["--file", str(state), "mark", "equipo-01", "hecho", "--note", "a\x1b[2Jb"])
    main(["--file", str(state), "list", "--category", "equipo"])
    out = capsys.readouterr().out
    assert "\\x1b[2J" in out and "\x1b" not in out


def test_demo_does_not_touch_default_state(capsys):
    default = PROJECT / "output" / "mi_checklist.json"
    existed = default.exists()
    assert main(["demo"]) == 0
    assert "Siguiente sugerida" in capsys.readouterr().out
    assert default.exists() == existed


def test_run_as_module(tmp_path):
    completed = subprocess.run(
        [sys.executable, "-m", "security_checklist", "--file", str(tmp_path / "a.json"), "progress"],
        cwd=PROJECT, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert completed.returncode == 0
    assert "Avance:" in completed.stdout
