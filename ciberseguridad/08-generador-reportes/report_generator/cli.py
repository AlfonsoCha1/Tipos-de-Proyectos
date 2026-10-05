"""Interfaz de línea de comandos del generador de reportes.

Códigos de salida: 0 = reporte generado (aunque haya filas rechazadas, que se
listan), 1 = error de entrada, de opciones o de escritura, 2 = argumentos
inválidos (argparse).
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from . import __version__
from .loader import INPUT_FORMATS, MAX_REJECTED_SHOWN, InputFormatError, load_files
from .render import render_html, render_markdown
from .timeutils import TimestampError, TimezoneError, load_timezone, parse_iso_timestamp

_NAME_RE = re.compile(r"^[A-Za-z0-9._-]{1,60}$")
EXTENSIONS = {"md": ".md", "html": ".html"}


class OptionError(Exception):
    """Una opción tiene un valor inválido."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m report_generator",
        description=(
            "Convierte eventos de seguridad (JSON, JSON Lines o CSV) en un reporte Markdown y/o HTML. "
            "Solo lee los archivos de entrada y solo escribe los reportes que le pidas."
        ),
    )
    parser.add_argument("files", nargs="+", type=Path, metavar="ARCHIVO", help="archivo(s) de eventos")
    parser.add_argument("--input-format", choices=("auto", *INPUT_FORMATS), default="auto",
                        help="formato de entrada (por defecto: según la extensión)")
    parser.add_argument("--output-format", choices=("md", "html", "both"), default="both",
                        help="formato del reporte (por defecto: both)")
    parser.add_argument("--output-dir", type=Path, default=Path("output"), metavar="CARPETA",
                        help="carpeta de salida (se crea si no existe; por defecto: output)")
    parser.add_argument("--name", default="reporte", metavar="NOMBRE",
                        help="nombre base de los archivos, sin ruta (por defecto: reporte)")
    parser.add_argument("--title", default="Reporte de eventos de seguridad", help="título del reporte")
    parser.add_argument("--top", type=int, default=5, metavar="N", help="cuántas IPs y cuentas listar (1-50)")
    parser.add_argument("--tz", default="UTC", metavar="ZONA", help="zona para fechas sin desplazamiento")
    parser.add_argument("--display-tz", default="UTC", metavar="ZONA", help="zona en la que se muestran las fechas")
    parser.add_argument("--generated-at", metavar="FECHA",
                        help="fecha de generación fija (ISO 8601); útil para obtener reportes idénticos")
    parser.add_argument("--stdout", action="store_true",
                        help="imprime el reporte Markdown en la terminal y no escribe archivos")
    parser.add_argument("--force", action="store_true", help="permite sobrescribir reportes existentes")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _plan_outputs(args: argparse.Namespace) -> dict[str, Path]:
    """Decide qué archivos se escribirán y valida que no se pisen sin ``--force``."""
    if not _NAME_RE.match(args.name):
        raise OptionError("--name solo admite letras, números, punto, guion y guion bajo (sin rutas).")
    formats = ("md", "html") if args.output_format == "both" else (args.output_format,)
    targets = {fmt: args.output_dir / f"{args.name}{EXTENSIONS[fmt]}" for fmt in formats}
    if args.output_dir.exists() and not args.output_dir.is_dir():
        raise OptionError(f"{args.output_dir} existe y no es una carpeta.")
    for path in targets.values():
        if path.exists() and not args.force:
            raise OptionError(f"{path} ya existe. Usa --force para sobrescribirlo o cambia --name.")
    return targets


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if not 1 <= args.top <= 50:
            raise OptionError("--top debe estar entre 1 y 50.")
        input_tz = load_timezone(args.tz)
        display_tz = load_timezone(args.display_tz)
        if args.generated_at:
            try:
                generated_at = parse_iso_timestamp(args.generated_at, timezone.utc)
            except TimestampError as exc:
                raise OptionError(f"--generated-at: {exc}") from exc
        else:
            generated_at = datetime.now(timezone.utc)
        targets = {} if args.stdout else _plan_outputs(args)

        loaded = load_files(args.files, args.input_format, input_tz)
        if not loaded.events:
            detail = "; ".join(f"{r.origin}: {r.reason}" for r in loaded.rejected[:5])
            raise InputFormatError("No hay eventos válidos para el reporte." + (f" Motivos: {detail}" if detail else ""))

        options = dict(
            title=args.title, files=loaded.files, rows_read=loaded.rows_read,
            display_tz=display_tz, generated_at=generated_at, top=args.top,
            max_rejected_shown=MAX_REJECTED_SHOWN,
        )
        if args.stdout:
            sys.stdout.write(render_markdown(loaded.events, loaded.rejected, **options))
        else:
            renderers = {"md": render_markdown, "html": render_html}
            args.output_dir.mkdir(parents=True, exist_ok=True)
            for fmt, path in targets.items():
                path.write_text(renderers[fmt](loaded.events, loaded.rejected, **options), encoding="utf-8", newline="\n")
                print(f"Reporte guardado en {path}")
        if loaded.rejected:
            print(f"Aviso: {len(loaded.rejected)} fila(s) rechazada(s); aparecen en el reporte.", file=sys.stderr)
        print(f"Eventos válidos: {len(loaded.events)} de {loaded.rows_read} fila(s).", file=sys.stderr if args.stdout else sys.stdout)
    except (OptionError, TimezoneError, InputFormatError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error de archivo: {exc.strerror or exc}", file=sys.stderr)
        return 1
    return 0
