"""Utilidades de fechas y zonas horarias.

Copia intencional compartida por los proyectos 09 y 12. Cada proyecto del
repositorio debe funcionar por separado, así que no importan código entre sí
(ver docs/ARQUITECTURA.md en la raíz). Si cambias este archivo, revisa si el
mismo cambio aplica a la copia del otro proyecto.

Decisión central: toda fecha se convierte a UTC en cuanto se lee. Así se
pueden comparar y restar eventos que llegaron con desplazamientos distintos
(por ejemplo -06:00 y Z) sin errores sutiles.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class TimezoneError(ValueError):
    """La zona horaria indicada no existe o no se pudo cargar."""


class TimestampError(ValueError):
    """Una fecha no tiene un formato válido."""


# Subconjunto estricto de ISO 8601. Se valida con una expresión regular antes
# de llamar a datetime.fromisoformat porque esa función acepta formatos
# distintos según la versión de Python (3.11 es más permisiva que 3.10).
_ISO_RE = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2})[T ](?P<time>\d{2}:\d{2}:\d{2})"
    r"(?:\.(?P<fraction>\d{1,6}))?"
    r"(?P<offset>Z|[+-]\d{2}:\d{2})?$",
    re.IGNORECASE,
)

_OFFSET_RE = re.compile(r"^(?P<sign>[+-])(?P<hours>\d{2}):?(?P<minutes>\d{2})$")


def load_timezone(name: str) -> tzinfo:
    """Convierte un nombre de zona horaria en un objeto ``tzinfo``.

    Args:
        name: ``"UTC"``, un desplazamiento fijo como ``"-06:00"`` o un nombre
            IANA como ``"America/Mexico_City"`` (respeta mayúsculas).

    Returns:
        Objeto ``tzinfo`` listo para usar con ``datetime``.

    Raises:
        TimezoneError: si el nombre no es válido o no se encuentra. En Windows
            esto ocurre cuando falta el paquete ``tzdata``.
    """
    text = name.strip()
    if text.upper() in {"UTC", "Z"}:
        return timezone.utc

    offset = _OFFSET_RE.match(text)
    if offset:
        hours, minutes = int(offset["hours"]), int(offset["minutes"])
        if hours > 23 or minutes > 59:
            raise TimezoneError(f"Desplazamiento fuera de rango: {name!r}")
        delta = timedelta(hours=hours, minutes=minutes)
        return timezone(-delta if offset["sign"] == "-" else delta)

    try:
        return ZoneInfo(text)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise TimezoneError(
            f"Zona horaria desconocida: {name!r}. Usa 'UTC', un desplazamiento "
            "como '-06:00' o un nombre IANA exacto como 'America/Mexico_City'. "
            "En Windows, instala 'tzdata' con: pip install -r requirements.txt"
        ) from exc


def to_utc(value: datetime, default_tz: tzinfo) -> datetime:
    """Devuelve ``value`` en UTC.

    Si ``value`` no tiene zona horaria (fecha "ingenua"), se asume
    ``default_tz``. Durante un cambio de horario una hora puede repetirse;
    en ese caso Python usa la primera aparición (``fold=0``).
    """
    if value.tzinfo is None:
        value = value.replace(tzinfo=default_tz)
    return value.astimezone(timezone.utc)


def parse_iso_timestamp(text: str, default_tz: tzinfo) -> datetime:
    """Interpreta una fecha ISO 8601 y la devuelve en UTC.

    Formatos aceptados: ``2026-09-14T08:00:05``, con fracción de segundo
    opcional (hasta 6 dígitos) y desplazamiento opcional (``Z`` o ``-06:00``).

    Args:
        text: fecha tal como aparece en el registro.
        default_tz: zona que se asume si la fecha no trae desplazamiento.

    Returns:
        ``datetime`` con zona horaria UTC.

    Raises:
        TimestampError: si el texto no es una fecha válida.
    """
    match = _ISO_RE.match(text.strip())
    if not match:
        raise TimestampError(f"fecha con formato no reconocido: {text!r}")

    fraction = (match["fraction"] or "0").ljust(6, "0")
    offset = match["offset"] or ""
    if offset.upper() == "Z":
        offset = "+00:00"

    try:
        parsed = datetime.fromisoformat(f"{match['date']}T{match['time']}.{fraction}{offset}")
    except ValueError as exc:  # por ejemplo, 31 de septiembre
        raise TimestampError(f"fecha inexistente: {text!r}") from exc
    return to_utc(parsed, default_tz)


def format_timestamp(value: datetime, display_tz: tzinfo) -> str:
    """Formatea una fecha para mostrarla, por ejemplo ``2026-09-14 08:10:02-06:00``."""
    return value.astimezone(display_tz).isoformat(sep=" ", timespec="seconds")


def format_duration(delta: timedelta) -> str:
    """Convierte una duración en texto corto, por ejemplo ``3 min 28 s``."""
    total = int(delta.total_seconds())
    hours, rest = divmod(total, 3600)
    minutes, seconds = divmod(rest, 60)
    if hours:
        return f"{hours} h {minutes} min {seconds} s"
    if minutes:
        return f"{minutes} min {seconds} s"
    return f"{seconds} s"
