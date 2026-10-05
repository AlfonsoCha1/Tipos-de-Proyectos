"""Interfaz de línea de comandos del detector de múltiples intentos fallidos.

Solo coordina: lee argumentos y configuración, carga eventos (``loader``),
ejecuta la detección (``detector``) y muestra o exporta (``report``).

Códigos de salida: 0 = análisis completado (haya o no alertas),
1 = error de entrada o configuración, 2 = argumentos inválidos (argparse).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Sequence

from . import __version__
from .config import ConfigError, Settings, load_settings
from .detector import RULES, DetectionSettings, detect
from .loader import load_events
from .parsers import SUPPORTED_FORMATS, LogFormatError, ParseOptions
from .report import ExportError, check_output_path, export_csv, export_json, render_text
from .timeutils import TimezoneError, load_timezone


class InputError(Exception):
    """Un archivo de entrada no existe o no es un archivo."""


def build_parser() -> argparse.ArgumentParser:
    """Define los argumentos aceptados por la herramienta."""
    parser = argparse.ArgumentParser(
        prog="python -m failed_login_detector",
        description=(
            "Detecta cuentas o IPs con demasiados intentos fallidos en poco tiempo. "
            "Solo genera alertas explicables: no bloquea nada ni se conecta a ningún servicio."
        ),
    )
    parser.add_argument("files", nargs="+", type=Path, metavar="ARCHIVO", help="registro(s) a analizar")
    parser.add_argument("--format", choices=("auto", *SUPPORTED_FORMATS), default="auto",
                        help="formato de los archivos (por defecto: auto)")
    parser.add_argument("--threshold", type=int, metavar="N", help="fallos necesarios para alertar (mínimo 2)")
    parser.add_argument("--window", type=float, metavar="MIN", help="ventana de tiempo en minutos")
    parser.add_argument("--success-after", type=float, metavar="MIN",
                        help="minutos tras la ráfaga en los que se busca un acceso exitoso")
    parser.add_argument("--by", choices=(*RULES, "both"),
                        help="agrupar por cuenta (user), por IP (ip) o ambas (both). Por defecto: config")
    parser.add_argument("--tz", metavar="ZONA", help="zona para fechas sin desplazamiento, p. ej. America/Mexico_City")
    parser.add_argument("--display-tz", metavar="ZONA", help="zona en la que se muestran las fechas")
    parser.add_argument("--year", type=int, metavar="AÑO", help="año para syslog tradicional (por defecto: año actual)")
    parser.add_argument("--config", type=Path, metavar="JSON", help="archivo de configuración alternativo")
    parser.add_argument("--export-json", type=Path, metavar="RUTA", help="guarda alertas y estadísticas en JSON")
    parser.add_argument("--export-csv", type=Path, metavar="RUTA", help="guarda una fila por alerta en CSV")
    parser.add_argument("--force", action="store_true", help="permite sobrescribir archivos de exportación")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def detection_settings(args: argparse.Namespace, settings: Settings) -> DetectionSettings:
    """Combina configuración y argumentos (los argumentos ganan) y valida el resultado.

    Raises:
        ConfigError: si algún valor está fuera de rango.
    """
    window = settings.window_minutes if args.window is None else args.window
    success_after = settings.success_after_minutes if args.success_after is None else args.success_after
    if window <= 0:
        raise ConfigError("--window debe ser mayor que 0 minutos")
    if success_after < 0:
        raise ConfigError("--success-after no puede ser negativo")
    if args.by is None:
        rules = settings.rules
    else:
        rules = RULES if args.by == "both" else (args.by,)
    try:
        return DetectionSettings(
            threshold=settings.threshold if args.threshold is None else args.threshold,
            window=timedelta(minutes=window),
            success_after=timedelta(minutes=success_after),
            rules=rules,
            max_evidence=settings.max_evidence,
        )
    except ValueError as exc:
        raise ConfigError(str(exc)) from None


def _check_inputs(paths: Sequence[Path]) -> None:
    for path in paths:
        if not path.exists():
            raise InputError(f"No existe el archivo: {path}")
        if not path.is_file():
            raise InputError(f"No es un archivo: {path}")


def _configure_output() -> None:
    # Evita UnicodeEncodeError en consolas que no soportan algún carácter.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")


def main(argv: Sequence[str] | None = None) -> int:
    """Punto de entrada. Devuelve el código de salida en lugar de terminar el proceso."""
    _configure_output()
    args = build_parser().parse_args(argv)

    try:
        settings = load_settings(args.config)
        detection = detection_settings(args, settings)
        default_tz = load_timezone(args.tz or settings.default_timezone)
        display_tz_name = args.display_tz or settings.display_timezone
        display_tz = load_timezone(display_tz_name)
        year = args.year or date.today().year
        if not 1970 <= year <= 9999:
            raise ConfigError("--year debe estar entre 1970 y 9999")

        _check_inputs(args.files)
        for output in (args.export_json, args.export_csv):
            if output is not None:
                check_output_path(output, args.force)

        loaded = load_events(args.files, args.format, ParseOptions(default_tz, year), settings.max_unparsed_kept)
        result = detect(loaded.events, detection)
        uses_syslog = any(f.fmt == "syslog" for f in loaded.files)
        print(
            render_text(
                result,
                loaded,
                detection,
                display_tz=display_tz,
                display_tz_name=display_tz_name,
                max_unparsed_shown=settings.max_unparsed_shown,
                assumed_year=year if uses_syslog else None,
            )
        )

        if args.export_json is not None:
            export_json(result, loaded, detection, args.export_json)
            print(f"\nAlertas exportadas a JSON: {args.export_json}")
        if args.export_csv is not None:
            export_csv(result, args.export_csv)
            print(f"Alertas exportadas a CSV: {args.export_csv}")
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
