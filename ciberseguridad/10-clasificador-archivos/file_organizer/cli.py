"""Interfaz de línea de comandos del clasificador de archivos.

Por defecto SOLO SIMULA. Para mover hay que pasar ``--apply`` y confirmar
escribiendo SI (o ``--yes`` en scripts). Cada aplicación deja un journal para
revertir con ``--undo``.

Códigos de salida: 0 = correcto o cancelado por el usuario, 1 = error,
2 = argumentos inválidos, 3 = algunos movimientos fallaron.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Callable, Sequence

from . import __version__
from .organizer import OrganizerError, Plan, apply_plan, apply_undo, load_undo_plan, plan_moves, tree

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = PROJECT_DIR / "config" / "settings.json"
DEMO_SOURCE = PROJECT_DIR / "samples" / "descargas_demo"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m file_organizer",
        description=(
            "Organiza los archivos de una carpeta en subcarpetas por tipo. Por defecto solo simula; "
            "con --apply mueve tras confirmar y guarda un journal para revertir con --undo."
        ),
    )
    parser.add_argument("folder", nargs="?", type=Path, metavar="CARPETA", help="carpeta a organizar")
    parser.add_argument("--apply", action="store_true", help="ejecuta los movimientos (después de confirmar)")
    parser.add_argument("--yes", action="store_true", help="no pregunta (para scripts); requiere --apply")
    parser.add_argument("--undo", type=Path, metavar="JOURNAL", help="revierte una organización anterior")
    parser.add_argument("--config", type=Path, metavar="JSON", help="categorías alternativas")
    parser.add_argument("--demo", action="store_true",
                        help="copia los ejemplos a una carpeta temporal, organiza, revierte y la borra")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def load_categories(path: Path | None) -> dict[str, list[str]]:
    config_path = path or DEFAULT_CONFIG
    try:
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise OrganizerError(f"No existe el archivo de configuración: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise OrganizerError(f"{config_path} no es JSON válido (línea {exc.lineno}): {exc.msg}") from exc
    categories = data.get("categories") if isinstance(data, dict) else None
    if not isinstance(categories, dict) or not categories:
        raise OrganizerError("la configuración debe tener un objeto 'categories' con al menos una categoría")
    for name, exts in categories.items():
        if not name or any(c in name for c in '\\/:*?"<>|') or name.startswith("."):
            raise OrganizerError(f"nombre de categoría inválido: {name!r}")
        if not isinstance(exts, list) or not all(isinstance(e, str) and e.startswith(".") for e in exts):
            raise OrganizerError(f"'{name}' debe ser una lista de extensiones que empiecen con punto")
    return categories


def _print_plan(plan: Plan) -> None:
    if not plan.moves:
        print("No hay archivos para organizar.")
    else:
        width = max(len(m.source) for m in plan.moves)
        print(f"Movimientos planeados: {len(plan.moves)}")
        for move in plan.moves:
            note = "   (renombrado: el nombre ya existía)" if move.renamed else ""
            print(f"  {move.source.ljust(width)}  ->  {move.target}{note}")
    if plan.skipped:
        print(f"\nSe quedan donde están: {len(plan.skipped)}")
        for name, reason in plan.skipped:
            print(f"  {name}  ({reason})")


def _confirm(question: str, ask: Callable[[str], str]) -> bool:
    try:
        return ask(question).strip().upper() == "SI"
    except EOFError:
        return False


def _organize(folder: Path, categories: dict, apply: bool, yes: bool, ask: Callable[[str], str]) -> int:
    plan = plan_moves(folder, categories)
    print(f"Carpeta: {folder}\n")
    _print_plan(plan)
    if not apply:
        print("\nSimulación: no se movió nada. Para aplicar agrega --apply.")
        return 0
    if not plan.moves:
        return 0
    if not yes and not _confirm(f"\nEscribe SI para mover {len(plan.moves)} archivos: ", ask):
        print("Cancelado: no se movió nada.")
        return 0
    result = apply_plan(plan)
    print(f"\nMovidos: {len(result.done)} | fallidos: {len(result.failed)}")
    for move, error in result.failed:
        print(f"  FALLÓ {move.source}: {error}")
    print(f"Journal guardado en: {result.journal}")
    print(f"Para revertir: python -m file_organizer --undo \"{result.journal}\" --apply")
    return 3 if result.failed else 0


def _undo(journal: Path, apply: bool, yes: bool, ask: Callable[[str], str]) -> int:
    plan = load_undo_plan(journal)
    print(f"Revertir según: {journal}\n")
    print(f"Movimientos a deshacer: {len(plan.moves)}")
    for move in plan.moves:
        print(f"  {move.source}  ->  {move.target}")
    for move, reason in plan.problems:
        print(f"  NO SE PUEDE {move.source}: {reason}")
    if not apply:
        print("\nSimulación: no se movió nada. Para revertir agrega --apply.")
        return 0
    if not plan.moves:
        return 3 if plan.problems else 0
    if not yes and not _confirm(f"\nEscribe SI para devolver {len(plan.moves)} archivos a su lugar: ", ask):
        print("Cancelado: no se movió nada.")
        return 0
    failures = apply_undo(plan)
    print(f"\nDevueltos: {len(plan.moves) - len(failures)} | fallidos: {len(failures)}")
    for move, error in failures:
        print(f"  FALLÓ {move.source}: {error}")
    return 3 if failures or plan.problems else 0


def _demo(categories: dict) -> int:
    with tempfile.TemporaryDirectory(prefix="file_organizer_demo_") as tmp:
        folder = Path(tmp) / "Descargas"
        shutil.copytree(DEMO_SOURCE, folder)
        print("Modo demostración: se trabaja sobre una COPIA temporal de samples/descargas_demo.\n")
        print("1) Antes:")
        print("\n".join("   " + line for line in tree(folder)))
        print("\n2) Simulación:")
        _print_plan(plan_moves(folder, categories))
        print("\n3) Aplicar (en la demo se confirma solo):")
        result = apply_plan(plan_moves(folder, categories))
        print(f"   Movidos: {len(result.done)} | fallidos: {len(result.failed)} | journal: {result.journal.name}")
        print("\n4) Después:")
        print("\n".join("   " + line for line in tree(folder)))
        print("\n5) Revertir con el journal:")
        failures = apply_undo(load_undo_plan(result.journal))
        print(f"   Devueltos: {len(result.done) - len(failures)} | fallidos: {len(failures)}")
        print("\n6) Después de revertir:")
        print("\n".join("   " + line for line in tree(folder)))
    print("\nLa carpeta temporal se borró. samples/descargas_demo no se modificó.")
    return 0


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def main(argv: Sequence[str] | None = None, ask: Callable[[str], str] = input) -> int:
    _configure_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    if sum(bool(x) for x in (args.folder, args.undo, args.demo)) != 1:
        parser.error("indica una CARPETA, o --undo JOURNAL, o --demo (solo uno)")
    if args.yes and not args.apply:
        parser.error("--yes solo tiene sentido junto con --apply")
    try:
        if args.undo:
            return _undo(args.undo, args.apply, args.yes, ask)
        categories = load_categories(args.config)
        if args.demo:
            return _demo(categories)
        return _organize(args.folder, categories, args.apply, args.yes, ask)
    except OrganizerError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error de lectura/escritura: {exc}", file=sys.stderr)
        return 1
