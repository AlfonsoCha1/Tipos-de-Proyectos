"""Presentación de resultados: texto para la terminal y exportación a JSON.

El contenido de las líneas viene de archivos analizados (entrada no
confiable): antes de mostrarlas se escapan los caracteres de control, por
ejemplo las secuencias ANSI (``\\x1b[31m``) que podrían alterar la terminal.
"""

from __future__ import annotations

import json
import unicodedata
from pathlib import Path
from typing import Sequence

from . import __version__
from .matcher import FileResult, Query


class ExportError(Exception):
    """No se pudo escribir un archivo de exportación."""


def clean_text(text: str) -> str:
    """Reemplaza caracteres de control por su forma escapada (``\\x1b``)."""
    return "".join(
        f"\\x{ord(char):02x}" if unicodedata.category(char) == "Cc" else char for char in text
    )


def describe_query(query: Query) -> list[str]:
    """Resume los criterios en lenguaje claro, una línea por criterio."""
    lines: list[str] = []
    if query.keywords:
        joiner = " Y " if query.match_all else " O "
        case = "distingue mayúsculas" if query.case_sensitive else "sin distinguir mayúsculas"
        lines.append(f"palabras ({case}): " + joiner.join(repr(word) for word in query.keywords))
    if query.has_ip_filter:
        parts = sorted(query.ips) + [str(net) for net in query.networks]
        lines.append("IPs o rangos: " + ", ".join(parts))
    if query.start is not None or query.end is not None:
        start = query.start.isoformat(timespec="seconds") if query.start else "(sin límite)"
        end = query.end.isoformat(timespec="seconds") if query.end else "(sin límite)"
        lines.append(f"fechas (UTC): desde {start} hasta {end}")
    return lines


def render_text(results: Sequence[FileResult], query: Query, *, count_only: bool = False) -> str:
    """Construye la salida de terminal.

    Formato por línea: ``  12: texto`` es una coincidencia y ``  11- texto``
    es una línea de contexto (igual que ``grep``). ``--`` separa bloques.
    """
    out = ["Criterios (todos deben cumplirse):"]
    out += [f"  - {line}" for line in describe_query(query)]
    out.append("")

    total = 0
    for result in results:
        total += result.matches
        if not count_only:
            out.append(f"== {clean_text(result.source)} ==")
            previous = None
            for entry in result.entries:
                if previous is not None and entry.line_no != previous + 1:
                    out.append("   --")
                mark = ":" if entry.is_match else "-"
                out.append(f"{entry.line_no:>5}{mark} {clean_text(entry.text)}")
                previous = entry.line_no
            if not result.entries:
                out.append("   (sin coincidencias)")
            out.append("")

    out.append("Resumen")
    for result in results:
        extras = []
        if result.undated:
            extras.append(f"{result.undated} sin fecha reconocible (excluidas por el filtro de fechas)")
        if result.truncated_lines:
            extras.append(f"{result.truncated_lines} línea(s) recortada(s) por ser muy largas")
        if result.stopped_early:
            extras.append("búsqueda detenida: se alcanzó --max-matches")
        note = f"  [{'; '.join(extras)}]" if extras else ""
        out.append(
            f"  {clean_text(result.source)}: {result.matches} coincidencia(s) "
            f"en {result.lines_read} línea(s) leída(s){note}"
        )
    out.append(f"Total: {total} coincidencia(s) en {len(results)} archivo(s).")
    if total == 0:
        out.append("Sin coincidencias. Revisa las palabras, el rango de fechas o la zona horaria (--tz).")
    return "\n".join(out)


def check_output_path(path: Path, force: bool) -> None:
    """Valida el destino de una exportación (nunca sobrescribe sin ``--force``)."""
    if path.exists() and path.is_dir():
        raise ExportError(f"{path} es una carpeta; indica un nombre de archivo.")
    if path.exists() and not force:
        raise ExportError(f"{path} ya existe. Usa --force para sobrescribirlo.")


def export_json(results: Sequence[FileResult], query: Query, path: Path) -> None:
    """Guarda coincidencias y contexto en un archivo JSON (UTF-8)."""
    payload = {
        "herramienta": f"log_search {__version__}",
        "criterios": describe_query(query),
        "archivos": [
            {
                "archivo": result.source,
                "lineas_leidas": result.lines_read,
                "coincidencias": result.matches,
                "sin_fecha": result.undated,
                "detenido_por_limite": result.stopped_early,
                "lineas": [
                    {"linea": e.line_no, "coincide": e.is_match, "texto": e.text}
                    for e in result.entries
                ],
            }
            for result in results
        ],
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except OSError as exc:
        raise ExportError(f"No se pudo escribir {path}: {exc.strerror or exc}") from exc
