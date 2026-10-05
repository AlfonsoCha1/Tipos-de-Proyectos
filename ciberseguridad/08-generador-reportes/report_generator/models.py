"""Modelos de datos del generador de reportes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

# De más a menos grave. El índice se usa para ordenar.
SEVERITIES = ("critica", "alta", "media", "baja", "info")

# Nombres en inglés aceptados en la entrada; se normalizan al español.
SEVERITY_ALIASES = {
    "critical": "critica", "crítica": "critica", "crítico": "critica", "critico": "critica",
    "high": "alta", "medium": "media", "med": "media", "low": "baja",
    "informational": "info", "informativa": "info",
}

SEVERITY_LABELS = {
    "critica": "Crítica", "alta": "Alta", "media": "Media", "baja": "Baja", "info": "Informativa",
}


def severity_rank(severity: str) -> int:
    """Posición de la severidad (0 = la más grave)."""
    return SEVERITIES.index(severity)


@dataclass(frozen=True, slots=True)
class Event:
    """Un evento de seguridad ya validado.

    Attributes:
        timestamp: fecha del evento en UTC.
        severity: una de ``SEVERITIES``.
        title: resumen corto.
        source: sistema que lo generó (por ejemplo ``vpn``); puede estar vacío.
        description: detalle opcional.
        ip: dirección IP normalizada o cadena vacía.
        user: cuenta afectada o cadena vacía.
        origin: ubicación en el archivo de entrada (``archivo:posición``).
    """

    timestamp: datetime
    severity: str
    title: str
    source: str
    description: str
    ip: str
    user: str
    origin: str


@dataclass(frozen=True, slots=True)
class RejectedRow:
    """Una fila de entrada que no se pudo convertir en evento."""

    origin: str
    reason: str
