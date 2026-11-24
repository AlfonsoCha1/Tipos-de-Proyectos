"""Lógica del clasificador: planear, aplicar y revertir. No imprime nada.

Principio central: **primero se simula**. ``plan_moves`` solo calcula qué haría
y no toca el disco. ``apply_plan`` mueve archivos únicamente cuando la interfaz
ya pidió confirmación, y antes de mover nada escribe un *journal* (bitácora)
con cada movimiento. Con ese journal, ``undo`` devuelve todo a su lugar.

Garantías:

* Nunca sobrescribe: si el destino existe, usa ``nombre (1).ext``.
* Solo toca archivos regulares del primer nivel de la carpeta elegida.
* No sigue enlaces simbólicos ni mueve archivos ocultos.
* Comparación de nombres sin distinguir mayúsculas, como Windows y macOS.
"""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence

JOURNAL_PREFIX = ".organizador_journal_"
OTHER_CATEGORY = "Otros"


class OrganizerError(Exception):
    """Error esperado: carpeta inválida, journal dañado, etc."""


@dataclass(frozen=True)
class Move:
    source: str  # rutas relativas a la carpeta organizada
    target: str
    category: str
    renamed: bool = False


@dataclass
class Plan:
    folder: Path
    moves: list[Move] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)  # (nombre, motivo)


@dataclass
class ApplyResult:
    journal: Path
    done: list[Move]
    failed: list[tuple[Move, str]]


def build_extension_map(categories: Mapping[str, Sequence[str]]) -> dict[str, str]:
    """Invierte {categoría: [extensiones]} a {extensión: categoría} y detecta repetidas."""
    mapping: dict[str, str] = {}
    for category, extensions in categories.items():
        for ext in extensions:
            key = ext.lower()
            if key in mapping and mapping[key] != category:
                raise OrganizerError(f"la extensión {ext} está en dos categorías: {mapping[key]} y {category}")
            mapping[key] = category
    return mapping


def category_for(name: str, ext_map: Mapping[str, str]) -> str:
    suffix = Path(name).suffix.lower()
    return ext_map.get(suffix, OTHER_CATEGORY)


def _unique_target(category: str, name: str, taken: set[str]) -> tuple[str, bool]:
    """Devuelve ``categoría/nombre`` libre; si está ocupado, agrega ``(1)``, ``(2)``..."""
    stem, suffix = Path(name).stem, Path(name).suffix
    candidate = f"{category}/{name}"
    counter = 0
    while candidate.casefold() in taken:
        counter += 1
        candidate = f"{category}/{stem} ({counter}){suffix}"
    taken.add(candidate.casefold())
    return candidate, counter > 0


def plan_moves(folder: Path, categories: Mapping[str, Sequence[str]]) -> Plan:
    """Calcula los movimientos sin tocar el disco."""
    if not folder.is_dir():
        raise OrganizerError(f"No es una carpeta: {folder}")
    ext_map = build_extension_map(categories)
    category_names = {name.casefold() for name in [*categories, OTHER_CATEGORY]}
    plan = Plan(folder)

    # Carpetas que ya existen (para reutilizarlas aunque cambie la capitalización)
    # y nombres ya ocupados dentro de las que son de categoría.
    existing_dirs: dict[str, str] = {}
    taken: set[str] = set()
    for entry in folder.iterdir():
        if entry.is_dir() and not entry.is_symlink():
            existing_dirs[entry.name.casefold()] = entry.name
            if entry.name.casefold() in category_names:
                for child in entry.iterdir():
                    taken.add(f"{entry.name}/{child.name}".casefold())

    for entry in sorted(folder.iterdir(), key=lambda p: p.name.casefold()):
        name = entry.name
        try:
            st = entry.lstat()
        except OSError as exc:
            plan.skipped.append((name, f"no se pudo consultar: {exc.strerror or exc}"))
            continue
        if stat.S_ISLNK(st.st_mode):
            plan.skipped.append((name, "enlace simbólico (no se mueve)"))
        elif stat.S_ISDIR(st.st_mode):
            continue  # las carpetas se quedan donde están
        elif not stat.S_ISREG(st.st_mode):
            plan.skipped.append((name, "no es un archivo regular"))
        elif name.startswith("."):
            plan.skipped.append((name, "archivo oculto (no se mueve)"))
        else:
            category = category_for(name, ext_map)
            # Si ya hay una carpeta con el nombre de la categoría pero distinta capitalización, se reutiliza.
            existing = existing_dirs.get(category.casefold(), category)
            target, renamed = _unique_target(existing, name, taken)
            plan.moves.append(Move(name, target, existing, renamed))
    return plan


def journal_path_for(folder: Path, now: datetime | None = None) -> Path:
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    path = folder / f"{JOURNAL_PREFIX}{stamp}.json"
    counter = 1
    while path.exists():
        path = folder / f"{JOURNAL_PREFIX}{stamp}-{counter}.json"
        counter += 1
    return path


def _write_journal(path: Path, data: dict) -> None:
    """Escritura atómica: se escribe un temporal y se reemplaza, para no dejar un journal a medias."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def apply_plan(plan: Plan, journal: Path | None = None) -> ApplyResult:
    """Ejecuta el plan. Escribe el journal ANTES de mover y lo actualiza después de cada movimiento."""
    folder = plan.folder
    journal = journal or journal_path_for(folder)
    data = {
        "tool": "file_organizer",
        "folder": str(folder.resolve()),
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "moves": [{"source": m.source, "target": m.target, "status": "pendiente"} for m in plan.moves],
    }
    _write_journal(journal, data)

    done: list[Move] = []
    failed: list[tuple[Move, str]] = []
    for index, move in enumerate(plan.moves):
        source, target = folder / move.source, folder / move.target
        try:
            if target.exists():
                raise FileExistsError(f"el destino apareció mientras se trabajaba: {move.target}")
            target.parent.mkdir(exist_ok=True)
            os.rename(source, target)  # misma carpeta raíz: no copia datos, solo cambia el nombre
        except OSError as exc:
            failed.append((move, str(exc)))
            data["moves"][index]["status"] = f"fallido: {exc}"
        else:
            done.append(move)
            data["moves"][index]["status"] = "hecho"
        _write_journal(journal, data)
    return ApplyResult(journal, done, failed)


@dataclass
class UndoPlan:
    folder: Path
    journal: Path
    moves: list[Move]  # en orden inverso
    problems: list[tuple[Move, str]]


def load_undo_plan(journal: Path) -> UndoPlan:
    try:
        data = json.loads(journal.read_text(encoding="utf-8"))
        folder = journal.resolve().parent
        entries = data["moves"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise OrganizerError(f"No se pudo leer el journal {journal}: {exc}") from exc

    moves: list[Move] = []
    problems: list[tuple[Move, str]] = []
    for entry in reversed(entries):
        if entry.get("status") != "hecho":
            continue
        move = Move(entry["target"], entry["source"], "", False)  # al revés
        source, target = folder / move.source, folder / move.target
        if not source.exists():
            problems.append((move, "ya no existe en el destino (¿se movió o borró después?)"))
        elif target.exists():
            problems.append((move, "el lugar original está ocupado por otro archivo"))
        else:
            moves.append(move)
    return UndoPlan(folder, journal, moves, problems)


def apply_undo(plan: UndoPlan) -> list[tuple[Move, str]]:
    """Revierte los movimientos posibles; borra las carpetas de categoría que queden vacías."""
    failures: list[tuple[Move, str]] = []
    touched: set[Path] = set()
    for move in plan.moves:
        source, target = plan.folder / move.source, plan.folder / move.target
        try:
            if target.exists():
                raise FileExistsError(f"ocupado: {move.target}")
            os.rename(source, target)
            touched.add(source.parent)
        except OSError as exc:
            failures.append((move, str(exc)))
    for directory in touched:
        try:
            directory.rmdir()  # solo funciona si está vacía: nunca borra archivos
        except OSError:
            pass
    if not failures and not plan.problems:
        plan.journal.replace(plan.journal.with_name(plan.journal.stem + ".revertido.json"))
    return failures


def tree(folder: Path, max_entries: int = 60) -> list[str]:
    """Lista breve de la carpeta (dos niveles) para mostrar antes y después."""
    lines: list[str] = []
    for entry in sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.casefold())):
        if entry.name.startswith(JOURNAL_PREFIX):
            note = "journal ya usado" if entry.name.endswith(".revertido.json") else "journal para revertir"
            lines.append(f"{entry.name}   <- {note}")
        elif entry.is_dir() and not entry.is_symlink():
            lines.append(f"{entry.name}/")
            for child in sorted(entry.iterdir(), key=lambda p: p.name.casefold()):
                lines.append(f"    {child.name}")
        else:
            lines.append(entry.name)
        if len(lines) >= max_entries:
            lines.append("...")
            break
    return lines
