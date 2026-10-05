"""Interfaz de línea de comandos del buscador de logs.

Códigos de salida: 0 = búsqueda completada (haya o no coincidencias),
1 = error de entrada o criterios, 2 = argumentos inválidos (argparse).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from . import __version__
from .matcher import (
    DEFAULT_MAX_MATCHES,
    MAX_CONTEXT,
    FileResult,
    QueryError,
    build_query,
    search_file,
)
from .report import ExportError, check_output_path, export_json, render_text
from .timeutils import TimezoneError, load_timezone


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m log_search",
        description=(
            "Busca palabras, IPs, rangos de red y fechas en archivos de log, con líneas de "
            "contexto. Solo lee: no modifica ni borra ningún archivo."
        ),
    )
    parser.add_argument("files", nargs="+", type=Path, metavar="ARCHIVO", help="archivo(s) de texto donde buscar")
    parser.add_argument("-k", "--keyword", action="append", metavar="PALABRA",
                        help="palabra o frase a buscar (se puede repetir)")
    parser.add_argument("--all", action="store_true", dest="match_all",
                        help="exige TODAS las palabras (por defecto basta con una)")
    parser.add_argument("--case-sensitive", action="store_true", help="distingue mayúsculas de minúsculas")
    parser.add_argument("--ip", action="append", metavar="IP", help="IP exacta (se puede repetir)")
    parser.add_argument("--cidr", action="append", metavar="RANGO", help="rango de red, p. ej. 192.0.2.0/24")
    parser.add_argument("--from", dest="start", metavar="FECHA", help="desde AAAA-MM-DD o AAAA-MM-DDTHH:MM:SS")
    parser.add_argument("--to", dest="end", metavar="FECHA", help="hasta (inclusive), mismo formato")
    parser.add_argument("--tz", default="UTC", metavar="ZONA",
                        help="zona para fechas sin desplazamiento y para --from/--to (por defecto: UTC)")
    parser.add_argument("--year", type=int, metavar="AÑO", help="año para syslog tradicional (por defecto: año actual)")
    parser.add_argument("-C", "--context", type=int, default=0, metavar="N",
                        help=f"líneas de contexto antes y después (0-{MAX_CONTEXT})")
    parser.add_argument("--max-matches", type=int, default=DEFAULT_MAX_MATCHES, metavar="N",
                        help=f"máximo de coincidencias por archivo (por defecto {DEFAULT_MAX_MATCHES})")
    parser.add_argument("--count", action="store_true", help="solo muestra los totales, sin las líneas")
    parser.add_argument("--export-json", type=Path, metavar="RUTA", help="guarda los resultados en JSON")
    parser.add_argument("--force", action="store_true", help="permite sobrescribir el archivo de exportación")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        for path in args.files:
            if not path.is_file():
                raise QueryError(f"No existe o no es un archivo: {path}")
        tz = load_timezone(args.tz)
        query = build_query(
            args.keyword,
            match_all=args.match_all,
            case_sensitive=args.case_sensitive,
            ips=args.ip,
            cidrs=args.cidr,
            start=args.start,
            end=args.end,
            tz=tz,
        )
        if args.export_json:
            check_output_path(args.export_json, args.force)

        results: list[FileResult] = []
        for path in args.files:
            results.append(search_file(
                path, query,
                source=str(path),
                context=args.context,
                max_matches=args.max_matches,
                default_tz=tz,
                year=args.year,
            ))
        print(render_text(results, query, count_only=args.count))
        if args.export_json:
            export_json(results, query, args.export_json)
            print(f"\nResultados guardados en {args.export_json}")
    except (QueryError, TimezoneError, ExportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error al leer un archivo: {exc.strerror or exc}", file=sys.stderr)
        return 1
    return 0
