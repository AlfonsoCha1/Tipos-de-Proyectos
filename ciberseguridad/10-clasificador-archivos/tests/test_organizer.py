"""Pruebas de la lógica del clasificador (organizer.py)."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from file_organizer.organizer import (
    OTHER_CATEGORY,
    OrganizerError,
    apply_plan,
    apply_undo,
    build_extension_map,
    category_for,
    load_undo_plan,
    plan_moves,
)

CATEGORIES = {"Imagenes": [".jpg", ".png"], "Documentos": [".pdf", ".txt"]}
SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "descargas_demo"


def touch(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def snapshot(folder: Path) -> dict[str, str]:
    return {
        str(p.relative_to(folder)).replace(os.sep, "/"): p.read_text(encoding="utf-8")
        for p in folder.rglob("*") if p.is_file() and not p.name.startswith(".organizador_journal_")
    }


def test_extension_map_and_category():
    mapping = build_extension_map(CATEGORIES)
    assert category_for("FOTO.JPG", mapping) == "Imagenes"
    assert category_for("sin_extension", mapping) == OTHER_CATEGORY
    assert category_for("raro.xyz", mapping) == OTHER_CATEGORY


def test_extension_in_two_categories_is_error():
    with pytest.raises(OrganizerError, match="dos categorías"):
        build_extension_map({"A": [".pdf"], "B": [".PDF"]})


def test_plan_does_not_touch_disk(tmp_path):
    touch(tmp_path / "a.jpg")
    touch(tmp_path / "b.pdf")
    before = snapshot(tmp_path)
    plan = plan_moves(tmp_path, CATEGORIES)
    assert [(m.source, m.target) for m in plan.moves] == [("a.jpg", "Imagenes/a.jpg"), ("b.pdf", "Documentos/b.pdf")]
    assert snapshot(tmp_path) == before
    assert not (tmp_path / "Imagenes").exists()


def test_hidden_files_folders_and_symlinks_stay(tmp_path):
    touch(tmp_path / ".oculto.txt")
    touch(tmp_path / "carpeta" / "dentro.pdf")
    target = touch(tmp_path / "real.txt")
    try:
        (tmp_path / "enlace.txt").symlink_to(target)
        has_link = True
    except (OSError, NotImplementedError):
        has_link = False
    plan = plan_moves(tmp_path, CATEGORIES)
    assert [m.source for m in plan.moves] == ["real.txt"]
    skipped = dict(plan.skipped)
    assert "oculto" in skipped[".oculto.txt"]
    if has_link:
        assert "enlace" in skipped["enlace.txt"]


def test_name_conflicts_are_renamed_never_overwritten(tmp_path):
    touch(tmp_path / "Imagenes" / "foto.jpg", "vieja")
    touch(tmp_path / "Imagenes" / "foto (1).jpg", "otra vieja")
    touch(tmp_path / "foto.jpg", "nueva")
    plan = plan_moves(tmp_path, CATEGORIES)
    assert plan.moves[0].target == "Imagenes/foto (2).jpg"
    assert plan.moves[0].renamed
    apply_plan(plan)
    assert (tmp_path / "Imagenes" / "foto.jpg").read_text(encoding="utf-8") == "vieja"
    assert (tmp_path / "Imagenes" / "foto (2).jpg").read_text(encoding="utf-8") == "nueva"


def test_existing_category_folder_with_other_case_is_reused(tmp_path):
    touch(tmp_path / "imagenes" / "x.txt")
    touch(tmp_path / "a.png")
    plan = plan_moves(tmp_path, CATEGORIES)
    assert plan.moves[0].target == "imagenes/a.png"


def test_apply_writes_journal_and_undo_restores_everything(tmp_path):
    for name in ("a.jpg", "b.pdf", "c.zip", "d"):
        touch(tmp_path / name, name)
    before = snapshot(tmp_path)
    result = apply_plan(plan_moves(tmp_path, CATEGORIES))
    assert len(result.done) == 4 and not result.failed
    data = json.loads(result.journal.read_text(encoding="utf-8"))
    assert {m["status"] for m in data["moves"]} == {"hecho"}
    assert (tmp_path / OTHER_CATEGORY / "c.zip").exists()

    undo = load_undo_plan(result.journal)
    assert len(undo.moves) == 4 and not undo.problems
    assert apply_undo(undo) == []
    assert snapshot(tmp_path) == before
    assert not (tmp_path / "Imagenes").exists()  # carpetas vacías eliminadas
    assert result.journal.with_name(result.journal.stem + ".revertido.json").exists()


def test_undo_never_overwrites(tmp_path):
    touch(tmp_path / "a.jpg", "original")
    result = apply_plan(plan_moves(tmp_path, CATEGORIES))
    touch(tmp_path / "a.jpg", "otro archivo nuevo")
    undo = load_undo_plan(result.journal)
    assert undo.moves == []
    assert "ocupado" in undo.problems[0][1]
    assert (tmp_path / "a.jpg").read_text(encoding="utf-8") == "otro archivo nuevo"


def test_undo_reports_missing_files(tmp_path):
    touch(tmp_path / "a.jpg")
    result = apply_plan(plan_moves(tmp_path, CATEGORIES))
    (tmp_path / "Imagenes" / "a.jpg").unlink()
    assert "ya no existe" in load_undo_plan(result.journal).problems[0][1]


def test_failed_move_is_recorded(tmp_path, monkeypatch):
    touch(tmp_path / "a.jpg")
    touch(tmp_path / "b.pdf")
    real_rename = os.rename

    def flaky(src, dst):
        if Path(src).name == "b.pdf":
            raise PermissionError(13, "Permiso denegado")
        return real_rename(src, dst)

    monkeypatch.setattr(os, "rename", flaky)
    result = apply_plan(plan_moves(tmp_path, CATEGORIES))
    assert [m.source for m in result.done] == ["a.jpg"]
    assert result.failed[0][0].source == "b.pdf"
    statuses = [m["status"] for m in json.loads(result.journal.read_text(encoding="utf-8"))["moves"]]
    assert statuses[0] == "hecho" and statuses[1].startswith("fallido")


def test_damaged_journal(tmp_path):
    bad = touch(tmp_path / ".organizador_journal_x.json", "{no")
    with pytest.raises(OrganizerError, match="No se pudo leer el journal"):
        load_undo_plan(bad)


def test_not_a_folder(tmp_path):
    with pytest.raises(OrganizerError):
        plan_moves(tmp_path / "nada", CATEGORIES)


def test_samples_plan_with_default_config(tmp_path):
    from file_organizer.cli import load_categories

    copy = tmp_path / "Descargas"
    shutil.copytree(SAMPLES, copy)
    plan = plan_moves(copy, load_categories(None))
    assert len(plan.moves) == 13
    renamed = [m for m in plan.moves if m.renamed]
    assert [m.target for m in renamed] == ["Imagenes/vacaciones_playa (1).jpg"]
    assert dict(plan.skipped) == {".configuracion_oculta": "archivo oculto (no se mueve)"}
