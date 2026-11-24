"""Interfaz de línea de comandos del verificador de archivos sospechosos.

Códigos de salida: 0 = correcto (aunque haya archivos sospechosos), 1 = error
de entrada o exportación, 2 = argumentos inválidos (argparse).
Con ``--fail-on sospechoso|revisar`` devuelve 3 si algún archivo alcanza ese
nivel, útil para usarla dentro de un script.
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path
from typing import Sequence

from . import __version__
from .demo import create_demo
from .inspector import inspect_paths
from .iocs import IocError, load_iocs
from .report import ExportError, check_output_path, export_json, render_text

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_IOCS = PROJECT_DIR / "samples" / "iocs_lab.txt"
FAIL_LEVELS = {"sospechoso": 3, "revisar": 2}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m file_inspector",
        description=(
            "Revisa archivos sin ejecutarlos: huellas MD5/SHA-1/SHA-256, tipo real por firma, "
            "doble extensión, nombres engañosos, PDF con contenido activo, ZIP con ejecutables "
            "y coincidencias con una lista local de indicadores."
        ),
    )
    parser.add_argument("paths", nargs="*", type=Path, metavar="RUTA", help="archivo(s) o carpeta(s)")
    parser.add_argument("-r", "--recursive", action="store_true", help="revisa también subcarpetas")
    parser.add_argument("--iocs", type=Path, metavar="TXT", help="lista de huellas conocidas (una por línea)")
    parser.add_argument("--all-hashes", action="store_true", help="muestra también SHA-1 y MD5")
    parser.add_argument("--demo", action="store_true",
                        help="crea archivos sintéticos en una carpeta temporal, los analiza y los borra")
    parser.add_argument("--fail-on", choices=tuple(FAIL_LEVELS), help="devuelve 3 si algún archivo alcanza ese nivel")
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
    if not args.paths and not args.demo:
        parser.error("indica al menos un archivo o carpeta, o usa --demo")
    try:
        iocs_path = args.iocs or (DEFAULT_IOCS if args.demo else None)
        iocs = load_iocs(iocs_path) if iocs_path is not None else None
        if args.export_json is not None:
            check_output_path(args.export_json, args.force)

        if args.demo:
            with tempfile.TemporaryDirectory(prefix="file_inspector_demo_") as tmp:
                folder = Path(tmp)
                create_demo(folder)
                print("Modo demostración: archivos sintéticos creados en una carpeta temporal (se borran al terminar).\n")
                results, skipped = inspect_paths([folder], iocs)
                print(render_text(results, skipped, iocs, base=folder,
                                  show_hashes="all" if args.all_hashes else "sha256"))
                if args.export_json is not None:
                    export_json(results, skipped, args.export_json)
        else:
            results, skipped = inspect_paths(args.paths, iocs, recursive=args.recursive)
            print(render_text(results, skipped, iocs, show_hashes="all" if args.all_hashes else "sha256"))
            if args.export_json is not None:
                export_json(results, skipped, args.export_json)
        if args.export_json is not None:
            print(f"\nResultado exportado a JSON: {args.export_json}")

        if args.fail_on and any(r.level >= FAIL_LEVELS[args.fail_on] for r in results):
            return 3
        return 0
    except (IocError, ExportError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except OSError as exc:
        print(f"Error de lectura/escritura: {exc}", file=sys.stderr)
        return 1
