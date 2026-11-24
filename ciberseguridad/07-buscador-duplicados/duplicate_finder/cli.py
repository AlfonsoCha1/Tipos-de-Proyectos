"""Interfaz de línea de comandos del buscador de duplicados.

Códigos de salida: 0 = correcto (haya o no duplicados), 1 = error de entrada,
configuración o exportación, 2 = argumentos inválidos (lo decide argparse).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .config import ConfigError, load_settings
from .report import ExportError, check_output_path, export_csv, export_json, render_text
from .scanner import ScanOptions, find_duplicates


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m duplicate_finder",
        description=(
            "Agrupa archivos idénticos por tamaño y SHA-256. Solo lee: nunca borra, mueve ni modifica nada."
        ),
    )
    parser.add_argument("roots", nargs="+", type=Path, metavar="CARPETA", help="carpeta(s) o archivo(s) a revisar")
    parser.add_argument("--min-size", type=int, metavar="BYTES", help="ignora archivos más pequeños (por defecto: 1)")
    parser.add_argument("--include-hidden", action="store_true", default=None, help="incluye archivos y carpetas ocultos")
    parser.add_argument("--top", type=int, metavar="N", help="grupos a mostrar; 0 = todos")
    parser.add_argument("--config", type=Path, metavar="JSON", help="archivo de configuración alternativo")
    parser.add_argument("--export-json", type=Path, metavar="RUTA", help="guarda el resultado completo en JSON")
    parser.add_argument("--export-csv", type=Path, metavar="RUTA", help="guarda una fila por archivo duplicado en CSV")
    parser.add_argument("--force", action="store_true", help="permite sobrescribir archivos de exportación")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def main(argv: Sequence[str] | None = None) -> int:
    _configure_output()
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(args.config)
        min_size = settings.min_size if args.min_size is None else args.min_size
        top = settings.top if args.top is None else args.top
        if min_size < 0 or top < 0:
            raise ConfigError("--min-size y --top deben ser 0 o mayores")
        include_hidden = settings.include_hidden if args.include_hidden is None else True
        for root in args.roots:
            if not root.exists():
                raise ConfigError(f"No existe: {root}")
        for output in (args.export_json, args.export_csv):
            if output is not None:
                check_output_path(output, args.force)

        options = ScanOptions(min_size=min_size, include_hidden=include_hidden, block_size=settings.block_size)
        result = find_duplicates(args.roots, options)
        print(render_text(result, args.roots, top, min_size))

        if args.export_json is not None:
            export_json(result, args.export_json)
            print(f"\nResultado exportado a JSON: {args.export_json}")
        if args.export_csv is not None:
            export_csv(result, args.export_csv)
            print(f"Duplicados exportados a CSV: {args.export_csv}")
        return 0
    except (ConfigError, ExportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error de lectura/escritura: {exc}", file=sys.stderr)
        return 1
