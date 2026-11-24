"""Interfaz de línea de comandos del analizador de correos.

Códigos de salida: 0 = correcto, 1 = error de entrada, configuración o
exportación, 2 = argumentos inválidos. Con ``--fail-on medio|alto`` devuelve 3
si algún mensaje alcanza ese nivel.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .config import ConfigError, load_settings
from .indicators import analyze
from .parser import EmailFormatError, load_message
from .report import ExportError, check_output_path, export_json, render_text

FAIL_LEVELS = {"medio": 25, "alto": 60}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m email_analyzer",
        description=(
            "Señala indicadores de phishing en correos .eml o mensajes de texto, con puntuación, "
            "explicación y posibles falsos positivos. No abre enlaces ni adjuntos."
        ),
    )
    parser.add_argument("paths", nargs="+", type=Path, metavar="ARCHIVO", help=".eml, .txt o carpeta con ellos")
    parser.add_argument("--text", action="store_true", help="trata todos los archivos como texto (SMS, WhatsApp, cuerpo pegado)")
    parser.add_argument("--config", type=Path, metavar="JSON", help="marcas protegidas y frases alternativas")
    parser.add_argument("--fail-on", choices=tuple(FAIL_LEVELS), help="devuelve 3 si algún mensaje alcanza ese nivel")
    parser.add_argument("--export-json", type=Path, metavar="RUTA", help="guarda indicadores (URLs, dominios, hashes) en JSON")
    parser.add_argument("--force", action="store_true", help="permite sobrescribir la exportación")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _expand(paths: Sequence[Path]) -> list[Path]:
    files = []
    for path in paths:
        if path.is_dir():
            files += sorted(p for p in path.iterdir() if p.is_file() and p.suffix.lower() in (".eml", ".txt"))
        else:
            files.append(path)
    return files


def _configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def main(argv: Sequence[str] | None = None) -> int:
    _configure_output()
    args = build_parser().parse_args(argv)
    try:
        settings = load_settings(args.config)
        if args.export_json is not None:
            check_output_path(args.export_json, args.force)
        analyses, errors = [], []
        for path in _expand(args.paths):
            try:
                analyses.append(analyze(load_message(path, args.text), settings))
            except FileNotFoundError:
                errors.append((path, "no existe"))
            except (EmailFormatError, OSError) as exc:
                errors.append((path, str(exc)))
        print(render_text(analyses, errors))
        if args.export_json is not None:
            export_json(analyses, args.export_json)
            print(f"\nIndicadores exportados a JSON: {args.export_json}")
        if not analyses:
            return 1
        if args.fail_on and any(a.score >= FAIL_LEVELS[args.fail_on] for a in analyses):
            return 3
        return 0
    except (ConfigError, ExportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
