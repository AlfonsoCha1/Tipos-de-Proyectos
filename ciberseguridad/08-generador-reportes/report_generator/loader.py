"""Lectura y validación de eventos desde JSON, JSON Lines y CSV.

Principio: ninguna fila se descarta en silencio. Lo que no cumple el esquema
se devuelve como ``RejectedRow`` con el motivo y se muestra en el reporte.

Esquema (campos de cada evento):

* obligatorios: ``timestamp`` (ISO 8601), ``severity``, ``title``
* opcionales: ``source``, ``description``, ``ip``, ``user``
"""

from __future__ import annotations

import csv
import ipaddress
import json
from dataclasses import dataclass, field
from datetime import tzinfo
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import SEVERITIES, SEVERITY_ALIASES, Event, RejectedRow
from .timeutils import TimestampError, parse_iso_timestamp

INPUT_FORMATS = ("json", "jsonl", "csv")
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_EVENTS = 50_000
MAX_REJECTED_SHOWN = 100   # el reporte no lista más filas rechazadas que esto

LIMITS = {"title": 200, "description": 2000, "source": 100, "user": 100}
REQUIRED = ("timestamp", "severity", "title")


class InputFormatError(Exception):
    """El archivo no se puede leer o no tiene una estructura utilizable."""


@dataclass
class LoadedEvents:
    """Resultado de cargar uno o más archivos."""

    events: list[Event] = field(default_factory=list)
    rejected: list[RejectedRow] = field(default_factory=list)
    rows_read: int = 0
    files: list[str] = field(default_factory=list)


def detect_format(path: Path) -> str:
    """Deduce el formato por la extensión (``.json``, ``.jsonl``/``.ndjson``, ``.csv``)."""
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "json"
    if suffix in {".jsonl", ".ndjson"}:
        return "jsonl"
    if suffix == ".csv":
        return "csv"
    raise InputFormatError(
        f"No se reconoce el formato de {path.name}: usa .json, .jsonl o .csv, o indica --input-format."
    )


def _read_text(path: Path) -> str:
    try:
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            raise InputFormatError(f"{path} pesa {size // (1024 * 1024)} MB; el máximo es {MAX_FILE_BYTES // (1024 * 1024)} MB.")
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise InputFormatError(f"{path} no está en UTF-8 válido (byte inválido en la posición {exc.start}).") from exc
    except OSError as exc:
        raise InputFormatError(f"No se pudo leer {path}: {exc.strerror or exc}") from exc


def _text_field(row: Mapping[str, Any], name: str) -> tuple[str, str | None]:
    """Devuelve ``(valor, error)`` para un campo de texto opcional u obligatorio."""
    value = row.get(name)
    if value is None:
        return "", None
    if not isinstance(value, (str, int, float)) or isinstance(value, bool):
        return "", f"el campo '{name}' debe ser texto"
    text = str(value).strip()
    limit = LIMITS.get(name)
    if limit and len(text) > limit:
        return "", f"el campo '{name}' supera {limit} caracteres"
    return text, None


def validate_row(row: Any, origin: str, default_tz: tzinfo) -> Event | RejectedRow:
    """Convierte un diccionario en ``Event`` o explica por qué no se pudo."""
    if not isinstance(row, Mapping):
        return RejectedRow(origin, "la fila no es un objeto con campos")

    missing = [name for name in REQUIRED if row.get(name) in (None, "")]
    if missing:
        return RejectedRow(origin, "faltan campos obligatorios: " + ", ".join(missing))

    values: dict[str, str] = {}
    for name in ("title", "source", "description", "user"):
        text, error = _text_field(row, name)
        if error:
            return RejectedRow(origin, error)
        values[name] = text
    if not values["title"]:
        return RejectedRow(origin, "el título está vacío")

    raw_severity = row.get("severity")
    if not isinstance(raw_severity, str):
        return RejectedRow(origin, "severity debe ser texto")
    severity = raw_severity.strip().lower()
    severity = SEVERITY_ALIASES.get(severity, severity)
    if severity not in SEVERITIES:
        return RejectedRow(origin, f"severidad desconocida: {raw_severity!r} (usa {', '.join(SEVERITIES)})")

    raw_ts = row.get("timestamp")
    if not isinstance(raw_ts, str):
        return RejectedRow(origin, "timestamp debe ser texto ISO 8601")
    try:
        timestamp = parse_iso_timestamp(raw_ts, default_tz)
    except TimestampError as exc:
        return RejectedRow(origin, str(exc))

    ip = ""
    raw_ip = row.get("ip")
    if raw_ip not in (None, ""):
        try:
            address = ipaddress.ip_address(str(raw_ip).strip())
        except ValueError:
            return RejectedRow(origin, f"IP no válida: {str(raw_ip)[:60]!r}")
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
            address = address.ipv4_mapped
        ip = str(address)

    return Event(timestamp, severity, values["title"], values["source"],
                 values["description"], ip, values["user"], origin)


def _iter_rows(path: Path, fmt: str) -> Iterable[tuple[str, Any]]:
    """Genera ``(posición, fila)``; las filas mal formadas llegan como ``_BadRow``."""
    text = _read_text(path)
    if fmt == "json":
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise InputFormatError(f"{path} no es JSON válido: {exc.msg} (línea {exc.lineno}, columna {exc.colno}).") from exc
        if isinstance(data, Mapping) and isinstance(data.get("events"), list):
            data = data["events"]
        if not isinstance(data, list):
            raise InputFormatError(f"{path}: se esperaba una lista de eventos o un objeto con la clave 'events'.")
        for index, row in enumerate(data, start=1):
            yield f"{path.name}[{index}]", row
    elif fmt == "jsonl":
        for number, line in enumerate(text.splitlines(), start=1):
            if not line.strip():
                continue
            try:
                yield f"{path.name}:{number}", json.loads(line)
            except json.JSONDecodeError as exc:
                yield f"{path.name}:{number}", _BadRow(f"JSON inválido: {exc.msg}")
    else:
        reader = csv.DictReader(text.splitlines(), restkey="_extra")
        header = reader.fieldnames or []
        absent = [name for name in REQUIRED if name not in header]
        if absent:
            raise InputFormatError(f"{path}: al CSV le faltan las columnas {', '.join(absent)}.")
        for row in reader:
            origin = f"{path.name}:{reader.line_num}"
            if any(value is None for key, value in row.items() if key != "_extra"):
                yield origin, _BadRow("la fila tiene menos columnas que el encabezado")
            else:
                row.pop("_extra", None)
                yield origin, row


class _BadRow:
    """Marca una fila que ni siquiera se pudo leer (para reportar el motivo)."""

    def __init__(self, reason: str) -> None:
        self.reason = reason


def load_files(paths: Iterable[Path], input_format: str, default_tz: tzinfo) -> LoadedEvents:
    """Carga y valida todos los archivos.

    Raises:
        InputFormatError: si un archivo no existe, es demasiado grande, no
            está en UTF-8 o su estructura general no es válida.
    """
    loaded = LoadedEvents()
    for path in paths:
        if not path.is_file():
            raise InputFormatError(f"No existe o no es un archivo: {path}")
        fmt = detect_format(path) if input_format == "auto" else input_format
        loaded.files.append(path.name)
        for origin, row in _iter_rows(path, fmt):
            loaded.rows_read += 1
            if loaded.rows_read > MAX_EVENTS:
                raise InputFormatError(f"Más de {MAX_EVENTS} filas: divide el archivo en partes.")
            if isinstance(row, _BadRow):
                loaded.rejected.append(RejectedRow(origin, row.reason))
                continue
            result = validate_row(row, origin, default_tz)
            if isinstance(result, Event):
                loaded.events.append(result)
            else:
                loaded.rejected.append(result)
    return loaded
