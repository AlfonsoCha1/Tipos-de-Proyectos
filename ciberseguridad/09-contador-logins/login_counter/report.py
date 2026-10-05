"""Presentación del resumen: texto para la terminal y exportación a JSON/CSV.

Los nombres de usuario vienen del registro, que es entrada no confiable.
Por eso:

* En la terminal se escapan los caracteres de control: una secuencia ANSI
  dentro de un nombre de usuario podría borrar o falsear la pantalla.
* En CSV se neutralizan celdas que empiezan con ``= + - @``: Excel o
  LibreOffice podrían interpretarlas como fórmulas (inyección CSV).
"""

from __future__ import annotations

import csv
import json
import unicodedata
from datetime import datetime, timezone, tzinfo
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .counter import LoginSummary, Tally, ranked
from .timeutils import format_timestamp

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


class ExportError(Exception):
    """No se pudo escribir un archivo de exportación."""


# --------------------------------------------------------------------------
# Limpieza de texto no confiable
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# Texto para la terminal
# --------------------------------------------------------------------------

def _table(headers: Sequence[str], rows: Sequence[Sequence[Any]], numeric_from: int) -> list[str]:
    """Construye una tabla de ancho fijo. Las columnas desde ``numeric_from`` se alinean a la derecha."""
    cells = [[clean_text(str(value)) for value in row] for row in rows]
    widths = [len(header) for header in headers]
    for row in cells:
        widths = [max(width, len(value)) for width, value in zip(widths, row)]

    def render(row: Sequence[str]) -> str:
        parts = [
            value.rjust(width) if index >= numeric_from else value.ljust(width)
            for index, (value, width) in enumerate(zip(row, widths))
        ]
        return "  ".join(parts).rstrip()

    return [render(headers), *(render(row) for row in cells)]


def _tally_section(title: str, label: str, tallies: dict[str, Tally], top: int) -> list[str]:
    rows = [(key, t.success, t.failure, t.total) for key, t in ranked(tallies, top)]
    scope = "todos" if top == 0 or top >= len(tallies) else f"top {top}"
    lines = [f"{title} ({scope}, ordenado por fallos)"]
    if not rows:
        return lines + ["  (sin datos)"]
    lines += _table((label, "EXITOSOS", "FALLIDOS", "TOTAL"), rows, numeric_from=1)
    if top and len(tallies) > top:
        lines.append(f"... {len(tallies) - top} más; usa --top 0 para ver todos.")
    return lines


def render_text(
    summary: LoginSummary,
    *,
    display_tz: tzinfo,
    display_tz_name: str,
    top: int,
    max_unparsed_shown: int,
    assumed_year: int | None = None,
) -> str:
    """Genera el reporte legible para la terminal.

    Args:
        summary: resultado de ``analyze_files``.
        display_tz: zona en la que se muestran las fechas.
        display_tz_name: nombre de esa zona, para indicarlo en el reporte.
        top: filas por tabla (0 = todas).
        max_unparsed_shown: cuántas líneas no interpretadas se listan.
        assumed_year: año asumido para syslog sin año; se menciona si no es ``None``.

    Returns:
        Texto con saltos de línea, sin colores ni símbolos especiales para
        que funcione igual en Linux y en la consola de Windows.
    """
    title = "Contador de intentos de login - Cybersecurity Python Lab"
    lines = [title, "=" * len(title), "", "Archivos analizados"]
    lines += _table(
        ("ARCHIVO", "FORMATO", "LÍNEAS", "EVENTOS", "IGNORADAS", "NO INTERPRETADAS"),
        [(f.source, f.fmt, f.lines, f.events, f.ignored, f.unparsed) for f in summary.files],
        numeric_from=2,
    )

    totals = summary.totals
    rate = "sin intentos" if summary.failure_rate is None else f"{summary.failure_rate:.1f} % de fallos"
    lines += [
        "",
        "Resumen",
        f"  Intentos: {totals.total} | exitosos: {totals.success} | fallidos: {totals.failure} ({rate})",
        f"  Fallos con usuario inexistente (solo syslog): {summary.invalid_user_failures}",
    ]
    if summary.first_seen and summary.last_seen:
        lines.append(f"  Primer evento: {format_timestamp(summary.first_seen, display_tz)}")
        lines.append(f"  Último evento: {format_timestamp(summary.last_seen, display_tz)}")
    lines.append(f"  Zona horaria del reporte: {display_tz_name}")
    if assumed_year is not None:
        lines.append(f"  Año asumido para syslog sin año: {assumed_year} (cámbialo con --year)")

    lines += ["", *_tally_section("Por usuario", "USUARIO", summary.by_user, top)]
    lines += ["", *_tally_section("Por IP", "IP", summary.by_ip, top)]

    lines += ["", f"Líneas no interpretadas: {summary.unparsed_total}"]
    shown = summary.unparsed[:max_unparsed_shown]
    for item in shown:
        lines.append(f"  {clean_text(item.source)}:{item.line_no}  {item.reason}")
        lines.append(f"      {clean_text(item.text)}")
    if summary.unparsed_total > len(shown):
        lines.append(
            f"  ... {summary.unparsed_total - len(shown)} más (exporta a JSON para ver hasta "
            "el límite configurado en max_unparsed_kept)."
        )

    lines += [
        "",
        "Nota: los conteos describen lo que dice el registro; no prueban por sí solos un ataque.",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Exportación
# --------------------------------------------------------------------------

def _iso_utc(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(timezone.utc).isoformat(timespec="seconds")


def check_output_path(path: Path, force: bool) -> None:
    """Verifica que se pueda escribir ``path`` sin destruir datos.

    Raises:
        ExportError: si el archivo ya existe y no se usó ``--force``, o si la
            ruta es una carpeta.
    """
    if path.is_dir():
        raise ExportError(f"{path} es una carpeta; indica un nombre de archivo.")
    if path.exists() and not force:
        raise ExportError(f"{path} ya existe. Usa --force para sobrescribirlo o elige otro nombre.")


def summary_to_dict(summary: LoginSummary) -> dict[str, Any]:
    """Convierte el resumen en una estructura serializable (fechas en UTC)."""

    def rows(tallies: dict[str, Tally], key_name: str) -> list[dict[str, Any]]:
        return [
            {key_name: key, "success": t.success, "failure": t.failure, "total": t.total}
            for key, t in ranked(tallies)
        ]

    return {
        "tool": "login_counter",
        "version": __version__,
        "generated_at_utc": _iso_utc(datetime.now(timezone.utc)),
        "files": [
            {
                "source": f.source,
                "format": f.fmt,
                "lines": f.lines,
                "events": f.events,
                "ignored": f.ignored,
                "unparsed": f.unparsed,
            }
            for f in summary.files
        ],
        "totals": {
            "success": summary.totals.success,
            "failure": summary.totals.failure,
            "total": summary.totals.total,
        },
        "invalid_user_failures": summary.invalid_user_failures,
        "first_seen_utc": _iso_utc(summary.first_seen),
        "last_seen_utc": _iso_utc(summary.last_seen),
        "by_user": rows(summary.by_user, "user"),
        "by_ip": rows(summary.by_ip, "ip"),
        "unparsed_total": summary.unparsed_total,
        "unparsed": [
            {"source": u.source, "line": u.line_no, "reason": u.reason, "text": u.text}
            for u in summary.unparsed
        ],
    }


def export_json(summary: LoginSummary, path: Path) -> None:
    """Escribe el resumen completo en JSON (UTF-8)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(summary_to_dict(summary), handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def export_csv(summary: LoginSummary, path: Path) -> None:
    """Escribe los conteos por usuario y por IP en un CSV.

    Se usa ``utf-8-sig`` para que Excel en Windows muestre bien los acentos.
    Columnas: ``dimension`` (user/ip), ``key``, ``success``, ``failure``, ``total``.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(("dimension", "key", "success", "failure", "total"))
        for dimension, tallies in (("user", summary.by_user), ("ip", summary.by_ip)):
            for key, t in ranked(tallies):
                writer.writerow((dimension, safe_csv_cell(key), t.success, t.failure, t.total))
