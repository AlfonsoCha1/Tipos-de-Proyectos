"""Interfaz de línea de comandos del contador de intentos de login.

Solo hace tres cosas: leer argumentos, llamar a la lógica (``counter``) y
mostrar o exportar el resultado (``report``). Los errores esperados se
convierten en mensajes claros y en un código de salida distinto de 0.

Códigos de salida: 0 = correcto, 1 = error de entrada o configuración,
2 = argumentos inválidos (lo decide argparse).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from typing import Sequence

from . import __version__
from .config import ConfigError, load_settings
from .counter import analyze_files
from .parsers import SUPPORTED_FORMATS, LogFormatError, ParseOptions
from .report import ExportError, check_output_path, export_csv, export_json, render_text
from .timeutils import TimezoneError, load_timezone


class InputError(Exception):
    """Un archivo de entrada no existe o no es un archivo."""


def build_parser() -> argparse.ArgumentParser:
    """Define los argumentos aceptados por la herramienta."""
    parser = argparse.ArgumentParser(
        prog="python -m login_counter",
        description=(
            "Cuenta intentos de login exitosos y fallidos por usuario e IP. "
            "Herramienta de laboratorio: analiza archivos locales, no se conecta a ningún servicio."
        ),
    )
    parser.add_argument("files", nargs="+", type=Path, metavar="ARCHIVO", help="registro(s) a analizar")
    parser.add_argument(
        "--format",
        choices=("auto", *SUPPORTED_FORMATS),
        default="auto",
        help="formato de los archivos (por defecto: auto, detecta cada archivo)",
    )
    parser.add_argument(
        "--tz",
        metavar="ZONA",
        help="zona para fechas sin desplazamiento, p. ej. America/Mexico_City (por defecto: config)",
    )
    parser.add_argument("--display-tz", metavar="ZONA", help="zona en la que se muestran las fechas")
    parser.add_argument(
        "--year",
        type=int,
        metavar="AÑO",
        help="año para syslog tradicional, que no lo incluye (por defecto: año actual)",
    )
    parser.add_argument("--top", type=int, metavar="N", help="filas por tabla; 0 = todas")
    parser.add_argument("--config", type=Path, metavar="JSON", help="archivo de configuración alternativo")
    parser.add_argument("--export-json", type=Path, metavar="RUTA", help="guarda el resumen completo en JSON")
    parser.add_argument("--export-csv", type=Path, metavar="RUTA", help="guarda los conteos en CSV")
    parser.add_argument("--force", action="store_true", help="permite sobrescribir archivos de exportación")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _check_inputs(paths: Sequence[Path]) -> None:
    for path in paths:
        if not path.exists():
            raise InputError(f"No existe el archivo: {path}")
        if not path.is_file():
            raise InputError(f"No es un archivo: {path}")


def _configure_output() -> None:
    # Si la consola no puede mostrar un carácter, se reemplaza en vez de
    # detener el programa con UnicodeEncodeError (posible en Windows al
    # redirigir la salida a un archivo).
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada. Devuelve el código de salida en lugar de terminar el proceso."""
    _configure_output()
    args = build_parser().parse_args(argv)

    try:
        settings = load_settings(args.config)
        default_tz_name = args.tz or settings.default_timezone
        display_tz_name = args.display_tz or settings.display_timezone
        default_tz = load_timezone(default_tz_name)
        display_tz = load_timezone(display_tz_name)
        top = settings.top if args.top is None else args.top
        if top < 0:
            raise ConfigError("--top debe ser 0 o mayor")
        year = args.year or date.today().year
        if not 1970 <= year <= 9999:
            raise ConfigError("--year debe estar entre 1970 y 9999")

        _check_inputs(args.files)
        # Se valida antes de analizar para no perder tiempo si la exportación fallará.
        for output in (args.export_json, args.export_csv):
            if output is not None:
                check_output_path(output, args.force)

        summary = analyze_files(
            args.files, args.format, ParseOptions(default_tz, year), settings.max_unparsed_kept
        )
        uses_syslog = any(f.fmt == "syslog" for f in summary.files)
        print(
            render_text(
                summary,
                display_tz=display_tz,
                display_tz_name=display_tz_name,
                top=top,
                max_unparsed_shown=settings.max_unparsed_shown,
                assumed_year=year if uses_syslog else None,
            )
        )

        if args.export_json is not None:
            export_json(summary, args.export_json)
            print(f"\nResumen exportado a JSON: {args.export_json}")
        if args.export_csv is not None:
            export_csv(summary, args.export_csv)
            print(f"Conteos exportados a CSV: {args.export_csv}")
        return 0

    except (ConfigError, TimezoneError, LogFormatError, InputError, ExportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except PermissionError as exc:
        print(
            f"Error: sin permiso para acceder a {exc.filename}. No ejecutes esta herramienta "
            "como administrador; trabaja con una copia o con los datos de ejemplo.",
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        print(f"Error de lectura/escritura: {exc}", file=sys.stderr)
        return 1
