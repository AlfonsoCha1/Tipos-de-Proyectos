"""Interfaz de línea de comandos del validador de archivos.

Códigos de salida: 0 = todo aceptado, 3 = algún archivo o nombre rechazado,
1 = error de entrada, configuración o exportación, 2 = argumentos inválidos.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .config import ConfigError, load_rules
from .report import ExportError, check_output_path, export_json, render_text
from .rules import Validation, validate_name, validate_paths


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m file_validator",
        description=(
            "Valida archivos como lo haría el filtro de un formulario de subida: extensión permitida, "
            "tamaño, nombre seguro y contenido que coincide con la extensión. Explica cada rechazo."
        ),
    )
    parser.add_argument("paths", nargs="*", type=Path, metavar="RUTA", help="archivo(s) o carpeta(s) a validar")
    parser.add_argument("--name", action="append", default=[], metavar="NOMBRE",
                        help="valida solo un nombre, sin archivo (se puede repetir)")
    parser.add_argument("--config", type=Path, metavar="JSON", help="reglas alternativas (por defecto: config/settings.json)")
    parser.add_argument("--no-content", action="store_true", help="no revisa el contenido, solo nombre y tamaño")
    parser.add_argument("--export-json", type=Path, metavar="RUTA", help="guarda el resultado en JSON")
    parser.add_argument("--force", action="store_true", help="permite sobrescribir la exportación")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def main(argv: Sequence[str] | None = None) -> int:
    _configure_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.paths and not args.name:
        parser.error("indica al menos un archivo o carpeta, o un nombre con --name")
    try:
        rules = load_rules(args.config)
        if args.no_content:
            from dataclasses import replace

            rules = replace(rules, check_content=False)
        if args.export_json is not None:
            check_output_path(args.export_json, args.force)
        results, skipped = validate_paths(args.paths, rules)
        results += [Validation(name, None, None, validate_name(name, rules)) for name in args.name]
        print(render_text(results, skipped, rules))
        if args.export_json is not None:
            export_json(results, skipped, args.export_json)
            print(f"\nResultado exportado a JSON: {args.export_json}")
        return 0 if all(r.accepted for r in results) else 3
    except (ConfigError, ExportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error de lectura/escritura: {exc}", file=sys.stderr)
        return 1
