"""Presentación del resultado: texto para la terminal y exportación a JSON/CSV.

Los nombres de archivo son entrada no confiable: alguien puede crear un archivo
cuyo nombre tenga secuencias ANSI o empiece con ``=``. Por eso se escapan los
caracteres de control en la terminal y se neutralizan fórmulas en el CSV.
"""

from __future__ import annotations

import csv
import json
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .scanner import ScanResult, format_size

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


class ExportError(Exception):
    """No se pudo escribir un archivo de exportación."""


def clean_text(text: str) -> str:
    """Reemplaza caracteres de control por su forma escapada (``\\x1b``)."""
    return "".join(
        f"\\x{ord(char):02x}" if unicodedata.category(char) == "Cc" else char for char in text
    )


def safe_csv_cell(value: Any) -> Any:
    """Antepone ``'`` a textos que una hoja de cálculo ejecutaría como fórmula."""
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return "'" + value
    return value


def render_text(result: ScanResult, roots: Sequence[Path], top: int, min_size: int) -> str:
    title = "Buscador de archivos duplicados - Cybersecurity Python Lab"
    lines = [title, "=" * len(title), ""]
    lines.append("Carpetas revisadas: " + ", ".join(clean_text(str(r)) for r in roots))
    lines.append(
        f"Archivos considerados: {result.files_seen} ({format_size(result.bytes_seen)}) | "
        f"tamaño mínimo: {format_size(min_size)}"
    )
    lines.append(f"Archivos con tamaño repetido, comparados por SHA-256: {result.files_hashed}")
    lines.append(
        f"Grupos de duplicados: {len(result.groups)} | copias sobrantes: {result.duplicate_files} | "
        f"espacio recuperable: {format_size(result.wasted_bytes)}"
    )
    lines.append("")

    if not result.groups:
        lines.append("No se encontraron archivos duplicados.")
    shown = result.groups if top == 0 else result.groups[:top]
    for number, group in enumerate(shown, start=1):
        lines.append(
            f"Grupo {number}: {len(group.paths)} archivos de {format_size(group.size)} "
            f"(sobran {format_size(group.wasted_bytes)})"
        )
        lines.append(f"  SHA-256: {group.sha256}")
        for path in group.paths:
            lines.append(f"  - {clean_text(str(path))}")
        lines.append("")
    if top and len(result.groups) > top:
        lines.append(f"... {len(result.groups) - top} grupos más; usa --top 0 para verlos todos.")
        lines.append("")

    if result.skipped:
        lines.append(f"No revisados: {len(result.skipped)}")
        for item in result.skipped:
            lines.append(f"  {clean_text(str(item.path))}  {clean_text(item.reason)}")
        lines.append("")

    lines.append(
        "Nota: esta herramienta no borra nada. Revisa cada grupo y decide tú qué copia conservar."
    )
    return "\n".join(lines)


def check_output_path(path: Path, force: bool) -> None:
    if path.exists() and not force:
        raise ExportError(f"{path} ya existe. Usa --force para sobrescribirlo.")
    if path.exists() and path.is_dir():
        raise ExportError(f"{path} es una carpeta, no un archivo.")


def _as_dict(result: ScanResult) -> dict[str, Any]:
    return {
        "tool": "duplicate_finder",
        "version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files_seen": result.files_seen,
        "bytes_seen": result.bytes_seen,
        "files_hashed": result.files_hashed,
        "duplicate_files": result.duplicate_files,
        "wasted_bytes": result.wasted_bytes,
        "groups": [
            {"sha256": g.sha256, "size": g.size, "wasted_bytes": g.wasted_bytes, "paths": [str(p) for p in g.paths]}
            for g in result.groups
        ],
        "skipped": [{"path": str(s.path), "reason": s.reason} for s in result.skipped],
    }


def export_json(result: ScanResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_as_dict(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def export_csv(result: ScanResult, path: Path) -> None:
    """Una fila por archivo duplicado, con el número de grupo para filtrar en la hoja de cálculo."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["grupo", "sha256", "tamano_bytes", "ruta"])
        for number, group in enumerate(result.groups, start=1):
            for file_path in group.paths:
                writer.writerow([number, group.sha256, group.size, safe_csv_cell(str(file_path))])
