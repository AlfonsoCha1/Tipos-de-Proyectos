"""Presentación de alertas: texto para la terminal y exportación a JSON/CSV.

Cada alerta incluye una explicación en lenguaje claro: qué regla se activó,
con qué datos, en qué intervalo y dónde está la evidencia. Así una persona
puede verificarla en el registro original.

Los nombres de usuario vienen del registro (entrada no confiable): en la
terminal se escapan caracteres de control y en CSV se neutralizan celdas que
una hoja de cálculo interpretaría como fórmula.
"""

from __future__ import annotations

import csv
import json
import unicodedata
from datetime import datetime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Any, Iterable, Sequence

from . import __version__
from .detector import RULE_LABELS, Alert, DetectionResult, DetectionSettings
from .loader import LoadedLogs
from .timeutils import format_duration, format_timestamp

FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

DISCLAIMER = (
    "Esta herramienta no bloquea cuentas ni direcciones. Las alertas son indicios para revisión "
    "humana: puede haber falsos positivos (usuarios que olvidaron su contraseña) y falsos "
    "negativos (ataques lentos o distribuidos por debajo del umbral)."
)


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


def evidence_text(evidence: Iterable[tuple[str, int]]) -> str:
    """Agrupa ubicaciones por archivo: ``a.log líneas 13, 14, 7 (x2)``.

    Una misma línea puede aparecer varias veces si syslog la resumió con
    "message repeated N times".
    """
    grouped: dict[str, dict[int, int]] = {}
    for source, line_no in evidence:
        lines = grouped.setdefault(source, {})
        lines[line_no] = lines.get(line_no, 0) + 1
    parts = []
    for source, lines in grouped.items():
        numbers = ", ".join(f"{n} (x{c})" if c > 1 else str(n) for n, c in lines.items())
        parts.append(f"{clean_text(source)} líneas {numbers}")
    return "; ".join(parts)


def minutes_text(delta: timedelta) -> str:
    """``timedelta(minutes=5)`` -> ``"5 min"``; ``timedelta(seconds=90)`` -> ``"1.5 min"``."""
    minutes = delta.total_seconds() / 60
    return f"{minutes:g} min"


# --------------------------------------------------------------------------
# Explicación de una alerta
# --------------------------------------------------------------------------

def explain(alert: Alert, settings: DetectionSettings, display_tz: tzinfo) -> list[str]:
    """Devuelve las frases que justifican una alerta, en el orden en que se leen."""
    first = format_timestamp(alert.first_seen, display_tz)
    last = format_timestamp(alert.last_seen, display_tz)
    related_label = "IPs de origen" if alert.rule == "user" else "Cuentas intentadas"
    related = ", ".join(sorted(alert.related))

    lines = [
        f"{alert.failures} intentos fallidos entre {first} y {last} ({format_duration(alert.duration)}).",
        f"Regla: {settings.threshold} o más fallos en una ventana de {minutes_text(settings.window)}.",
        f"{related_label} ({len(alert.related)}): {related}",
    ]

    success = alert.success_after
    if success is None:
        lines.append(
            "Sin acceso exitoso de la misma "
            f"{'cuenta' if alert.rule == 'user' else 'IP'} hasta "
            f"{minutes_text(settings.success_after)} después de la ráfaga."
        )
    else:
        when = format_timestamp(success.timestamp, display_tz)
        if success.timestamp <= alert.last_seen:
            moment = "durante la ráfaga"
        else:
            moment = f"{format_duration(success.timestamp - alert.last_seen)} después del último fallo"
        detail = f"desde {success.ip}" if alert.rule == "user" else f"con la cuenta {success.user}"
        lines.append(
            f"Acceso EXITOSO {moment}: {when} {detail} ({success.location}). "
            "Verifica si fue legítimo."
        )
    return [clean_text(line) for line in lines]


# --------------------------------------------------------------------------
# Texto para la terminal
# --------------------------------------------------------------------------

def _files_table(loaded: LoadedLogs) -> list[str]:
    headers = ("ARCHIVO", "FORMATO", "LÍNEAS", "EVENTOS", "IGNORADAS", "NO INTERPRETADAS")
    rows = [
        (clean_text(f.source), f.fmt, str(f.lines), str(f.events), str(f.ignored), str(f.unparsed))
        for f in loaded.files
    ]
    widths = [max(len(h), *(len(r[i]) for r in rows)) if rows else len(h) for i, h in enumerate(headers)]

    def render(row: Sequence[str]) -> str:
        cells = [v.ljust(w) if i < 2 else v.rjust(w) for i, (v, w) in enumerate(zip(row, widths))]
        return "  ".join(cells).rstrip()

    return [render(headers), *(render(row) for row in rows)]


def render_text(
    result: DetectionResult,
    loaded: LoadedLogs,
    settings: DetectionSettings,
    *,
    display_tz: tzinfo,
    display_tz_name: str,
    max_unparsed_shown: int,
    assumed_year: int | None = None,
) -> str:
    """Genera el reporte legible para la terminal (sin colores ni símbolos especiales)."""
    title = "Detector de múltiples intentos fallidos - Cybersecurity Python Lab"
    rules = ", ".join(RULE_LABELS[rule] for rule in settings.rules)
    lines = [title, "=" * len(title), "", "Archivos analizados", *_files_table(loaded), ""]
    lines += [
        "Resumen",
        f"  Eventos: {result.total_events} (fallidos: {result.failures}, exitosos: {result.successes})",
        f"  Eventos fuera de orden en los archivos: {result.out_of_order} (se ordenan antes de analizar)",
        f"  Configuración: umbral {settings.threshold} fallos | ventana {minutes_text(settings.window)} | "
        f"éxito posterior: {minutes_text(settings.success_after)} | reglas: {rules}",
        f"  Zona horaria del reporte: {display_tz_name}",
    ]
    if assumed_year is not None:
        lines.append(f"  Año asumido para syslog sin año: {assumed_year} (cámbialo con --year)")

    lines += ["", f"Alertas: {len(result.alerts)}"]
    for number, alert in enumerate(result.alerts, start=1):
        label = f"{RULE_LABELS[alert.rule]} '{clean_text(alert.key)}'"
        lines += ["", f"[{number}] Severidad {alert.severity.upper()} - {label}"]
        lines += [f"    {sentence}" for sentence in explain(alert, settings, display_tz)]
        extra = alert.failures - len(alert.evidence)
        lines.append(f"    Evidencia: {evidence_text(alert.evidence)}" + (f" (+{extra} más)" if extra > 0 else ""))
    if not result.alerts:
        lines.append("  Ninguna cuenta ni IP superó el umbral con la configuración actual.")

    if loaded.unparsed_total:
        lines += ["", f"Líneas no interpretadas: {loaded.unparsed_total} (no participan en la detección)"]
        for item in loaded.unparsed[:max_unparsed_shown]:
            lines.append(f"  {clean_text(item.source)}:{item.line_no}  {item.reason}")
        hidden = loaded.unparsed_total - min(len(loaded.unparsed), max_unparsed_shown)
        if hidden > 0:
            lines.append(f"  ... {hidden} más (usa --export-json o el proyecto 09 para verlas).")

    lines += ["", f"Nota: {DISCLAIMER}"]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Exportación
# --------------------------------------------------------------------------

def _iso_utc(value: datetime | None) -> str | None:
    return None if value is None else value.astimezone(timezone.utc).isoformat(timespec="seconds")


def check_output_path(path: Path, force: bool) -> None:
    """Evita sobrescribir archivos existentes sin ``--force``.

    Raises:
        ExportError: si la ruta es una carpeta o el archivo ya existe sin ``force``.
    """
    if path.is_dir():
        raise ExportError(f"{path} es una carpeta; indica un nombre de archivo.")
    if path.exists() and not force:
        raise ExportError(f"{path} ya existe. Usa --force para sobrescribirlo o elige otro nombre.")


def alert_to_dict(alert: Alert, settings: DetectionSettings) -> dict[str, Any]:
    """Convierte una alerta en un diccionario serializable (fechas en UTC)."""
    success = alert.success_after
    return {
        "rule": alert.rule,
        "key": alert.key,
        "severity": alert.severity,
        "failures": alert.failures,
        "first_seen_utc": _iso_utc(alert.first_seen),
        "last_seen_utc": _iso_utc(alert.last_seen),
        "duration_seconds": int(alert.duration.total_seconds()),
        "related": sorted(alert.related),
        "evidence": [f"{source}:{line_no}" for source, line_no in alert.evidence],
        "success_after": None
        if success is None
        else {
            "timestamp_utc": _iso_utc(success.timestamp),
            "user": success.user,
            "ip": success.ip,
            "location": success.location,
        },
        "explanation": explain(alert, settings, timezone.utc),
    }


def export_json(result: DetectionResult, loaded: LoadedLogs, settings: DetectionSettings, path: Path) -> None:
    """Escribe configuración, estadísticas y alertas en JSON (UTF-8)."""
    data = {
        "tool": "failed_login_detector",
        "version": __version__,
        "generated_at_utc": _iso_utc(datetime.now(timezone.utc)),
        "settings": {
            "threshold": settings.threshold,
            "window_minutes": settings.window.total_seconds() / 60,
            "success_after_minutes": settings.success_after.total_seconds() / 60,
            "rules": list(settings.rules),
        },
        "files": [
            {"source": f.source, "format": f.fmt, "lines": f.lines, "events": f.events,
             "ignored": f.ignored, "unparsed": f.unparsed}
            for f in loaded.files
        ],
        "stats": {
            "events": result.total_events,
            "failures": result.failures,
            "successes": result.successes,
            "out_of_order": result.out_of_order,
            "unparsed": loaded.unparsed_total,
        },
        "alerts": [alert_to_dict(alert, settings) for alert in result.alerts],
        "unparsed": [
            {"source": u.source, "line": u.line_no, "reason": u.reason, "text": u.text}
            for u in loaded.unparsed
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def export_csv(result: DetectionResult, path: Path) -> None:
    """Escribe una fila por alerta. ``utf-8-sig`` para que Excel muestre bien los acentos."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ("rule", "key", "severity", "failures", "first_seen_utc", "last_seen_utc",
             "duration_seconds", "related", "success_after_utc", "success_after_location", "evidence")
        )
        for alert in result.alerts:
            success = alert.success_after
            writer.writerow(
                (
                    alert.rule,
                    safe_csv_cell(alert.key),
                    alert.severity,
                    alert.failures,
                    _iso_utc(alert.first_seen),
                    _iso_utc(alert.last_seen),
                    int(alert.duration.total_seconds()),
                    safe_csv_cell(" ".join(sorted(alert.related))),
                    _iso_utc(success.timestamp) if success else "",
                    safe_csv_cell(success.location) if success else "",
                    safe_csv_cell(" ".join(f"{source}:{line_no}" for source, line_no in alert.evidence)),
                )
            )
