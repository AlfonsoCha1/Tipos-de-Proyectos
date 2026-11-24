"""Interfaz de la checklist: list, mark, progress, export, reset y demo.

Códigos de salida: 0 = correcto, 1 = error (plantilla, avance, id o estado
inválidos, exportación), 2 = argumentos inválidos.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Sequence

from . import __version__
from .store import STATUSES, Checklist, ChecklistError, load_checklist, mark, save_checklist

SYMBOLS = {"pendiente": "[ ]", "en_progreso": "[~]", "hecho": "[x]", "no_aplica": "[-]"}
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def clean_text(text: str) -> str:
    return "".join(f"\\x{ord(c):02x}" if unicodedata.category(c) == "Cc" else c for c in text)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m security_checklist",
        description="Checklist de seguridad personal y de un pequeño negocio, con avance guardado en tu equipo.",
    )
    parser.add_argument("--file", type=Path, metavar="JSON", help="archivo de avance (por defecto output/mi_checklist.json)")
    parser.add_argument("--template", type=Path, metavar="JSON", help="plantilla alternativa")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subs = parser.add_subparsers(dest="command", required=True, metavar="COMANDO")

    lst = subs.add_parser("list", help="muestra las tareas")
    lst.add_argument("--category", metavar="CATEGORÍA")
    lst.add_argument("--status", choices=STATUSES)
    lst.add_argument("--why", action="store_true", help="muestra por qué importa cada tarea")

    mrk = subs.add_parser("mark", help="cambia el estado de una tarea")
    mrk.add_argument("task_id", metavar="ID")
    mrk.add_argument("status", choices=STATUSES, metavar="ESTADO", help=" | ".join(STATUSES))
    mrk.add_argument("--note", metavar="TEXTO", help="nota corta (máx. 500 caracteres)")

    subs.add_parser("progress", help="avance por categoría")

    exp = subs.add_parser("export", help="exporta a Markdown o CSV")
    exp.add_argument("--format", choices=("md", "csv"), default="md")
    exp.add_argument("--output", type=Path, metavar="RUTA", help="archivo de salida (por defecto, la pantalla)")
    exp.add_argument("--force", action="store_true", help="permite sobrescribir --output")

    rst = subs.add_parser("reset", help="vuelve todo a pendiente")
    rst.add_argument("--yes", action="store_true", help="confirma el borrado del avance")

    subs.add_parser("demo", help="demostración sobre un archivo temporal (no toca tu avance)")
    return parser


def render_list(checklist: Checklist, category: str | None, status: str | None, why: bool) -> str:
    lines, current = [], None
    for task in checklist.tasks:
        progress = checklist.get(task.id)
        if category and task.category.lower() != category.lower():
            continue
        if status and progress.status != status:
            continue
        if task.category != current:
            current = task.category
            lines.append(f"\n{current}")
        lines.append(f"  {SYMBOLS[progress.status]} {task.id:<13} {task.title}")
        if progress.note:
            lines.append(f"      Nota: {clean_text(progress.note)}")
        if why:
            lines.append(f"      Por qué: {task.why}")
    return "\n".join(lines).lstrip("\n") if lines else "(no hay tareas con ese filtro)"


def render_progress(checklist: Checklist) -> str:
    counts = checklist.counts()
    width = 30
    filled = round(width * checklist.percent_done() / 100)
    lines = [f"Avance: [{'#' * filled}{'.' * (width - filled)}] {checklist.percent_done():.0f} %  "
             f"(hecho {counts['hecho']}, en progreso {counts['en_progreso']}, pendiente {counts['pendiente']}, "
             f"no aplica {counts['no_aplica']})", ""]
    categories: dict[str, list[str]] = {}
    for task in checklist.tasks:
        categories.setdefault(task.category, []).append(checklist.get(task.id).status)
    name_width = max(len(c) for c in categories)
    for category, statuses in categories.items():
        applicable = [s for s in statuses if s != "no_aplica"]
        done = sum(1 for s in applicable if s == "hecho")
        lines.append(f"  {category.ljust(name_width)}  {done}/{len(applicable)}")
    pending = [t for t in checklist.tasks if checklist.get(t.id).status in ("pendiente", "en_progreso")]
    if pending:
        lines.append(f"\nSiguiente sugerida: {pending[0].id} - {pending[0].title}")
    return "\n".join(lines)


def export_text(checklist: Checklist, fmt: str) -> str:
    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerow(["id", "categoria", "tarea", "estado", "nota", "actualizado"])
        for task in checklist.tasks:
            p = checklist.get(task.id)
            safe = lambda v: "'" + v if v.startswith(FORMULA_PREFIXES) else v
            writer.writerow([task.id, task.category, task.title, p.status, safe(p.note), p.updated])
        return buffer.getvalue()
    lines = ["# Checklist de seguridad", "", f"Avance: {checklist.percent_done():.0f} %"]
    current = None
    for task in checklist.tasks:
        p = checklist.get(task.id)
        if task.category != current:
            current = task.category
            lines += ["", f"## {current}", ""]
        box = "x" if p.status == "hecho" else " "
        suffix = {"en_progreso": " *(en progreso)*", "no_aplica": " *(no aplica)*"}.get(p.status, "")
        # La nota es texto libre: se neutraliza HTML para que no se interprete al ver el Markdown.
        note = f" — {p.note.replace('<', '&lt;').replace('>', '&gt;')}" if p.note else ""
        lines.append(f"- [{box}] {task.title}{suffix}{note}")
    return "\n".join(lines) + "\n"


def run_demo(template: Path | None) -> int:
    with tempfile.TemporaryDirectory(prefix="checklist_demo_") as tmp:
        state = Path(tmp) / "avance.json"
        print("Modo demostración: se usa un archivo temporal; tu avance real no se toca.\n")
        checklist = load_checklist(template, state)
        steps = [("cuentas-01", "hecho", "MFA con app de autenticación"), ("equipo-01", "hecho", None),
                 ("equipo-02", "en_progreso", "falta guardar la llave de recuperación"),
                 ("red-03", "no_aplica", "no tengo dispositivos IoT"), ("respaldo-01", "hecho", "disco externo + nube")]
        for task_id, status, note in steps:
            mark(checklist, task_id, status, note)
            print(f"$ python -m security_checklist mark {task_id} {status}" + (f' --note "{note}"' if note else ""))
        save_checklist(checklist, state)
        reloaded = load_checklist(template, state)
        print("\n$ python -m security_checklist progress")
        print(render_progress(reloaded))
        print("\n$ python -m security_checklist list --category Equipo")
        print(render_list(reloaded, "Equipo", None, False))
        print("\n$ python -m security_checklist export --format md  (primeras líneas)")
        print("\n".join(export_text(reloaded, "md").splitlines()[:9]))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    try:
        if args.command == "demo":
            return run_demo(args.template)
        checklist = load_checklist(args.template, args.file)
        for orphan in checklist.orphans:
            print(f"Aviso: tu avance tiene la tarea '{orphan}', que ya no está en la plantilla (se conserva).", file=sys.stderr)
        if args.command == "list":
            print(render_list(checklist, args.category, args.status, args.why))
        elif args.command == "mark":
            task = mark(checklist, args.task_id, args.status, args.note)
            path = save_checklist(checklist, args.file)
            print(f"{SYMBOLS[args.status]} {task.id}: {task.title}  -> {args.status} (guardado en {path})")
            print(f"Avance: {checklist.percent_done():.0f} %")
        elif args.command == "progress":
            print(render_progress(checklist))
        elif args.command == "export":
            text = export_text(checklist, args.format)
            if args.output is None:
                print(text)
            else:
                if args.output.exists() and not args.force:
                    raise ChecklistError(f"{args.output} ya existe. Usa --force para sobrescribirlo.")
                args.output.parent.mkdir(parents=True, exist_ok=True)
                args.output.write_text(text, encoding="utf-8-sig" if args.format == "csv" else "utf-8")
                print(f"Exportado a {args.output}")
        elif args.command == "reset":
            if not args.yes:
                print("Esto vuelve todas las tareas a 'pendiente' y borra las notas. Repite con --yes para confirmar.")
                return 0
            checklist.progress.clear()
            print(f"Avance reiniciado ({save_checklist(checklist, args.file)}).")
        return 0
    except ChecklistError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error de lectura/escritura: {exc}", file=sys.stderr)
        return 1
