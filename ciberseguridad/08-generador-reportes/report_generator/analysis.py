"""Estadísticas del reporte. Funciones puras: no imprimen ni escriben archivos."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, tzinfo
from typing import Sequence

from .models import SEVERITIES, SEVERITY_LABELS, Event, severity_rank


@dataclass(frozen=True)
class Summary:
    """Resumen numérico de un conjunto de eventos (no vacío)."""

    total: int
    by_severity: dict[str, int]          # incluye todas las severidades, aunque sean 0
    by_source: list[tuple[str, int]]     # de más a menos frecuente
    top_ips: list[tuple[str, int]]
    top_users: list[tuple[str, int]]
    per_day: list[tuple[date, int]]      # según la zona de visualización
    first: datetime
    last: datetime
    highlights: list[str]                # frases generadas por reglas fijas


def _ranked(counter: Counter[str], top: int) -> list[tuple[str, int]]:
    # Orden estable: más frecuente primero; empates por texto, para que el
    # reporte sea idéntico cada vez que se genera con los mismos datos.
    return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:top]


def sort_events(events: Sequence[Event]) -> list[Event]:
    """Orden del reporte: más grave primero y, dentro de cada severidad, por fecha."""
    return sorted(events, key=lambda e: (severity_rank(e.severity), e.timestamp, e.origin))


def summarize(events: Sequence[Event], display_tz: tzinfo, top: int = 5) -> Summary:
    """Calcula el resumen. ``events`` no puede estar vacío."""
    if not events:
        raise ValueError("Se necesita al menos un evento para resumir.")

    severities = Counter(e.severity for e in events)
    by_severity = {name: severities.get(name, 0) for name in SEVERITIES}
    sources = Counter(e.source or "(sin fuente)" for e in events)
    ips = Counter(e.ip for e in events if e.ip)
    users = Counter(e.user for e in events if e.user)
    days = Counter(e.timestamp.astimezone(display_tz).date() for e in events)
    moments = [e.timestamp for e in events]

    return Summary(
        total=len(events),
        by_severity=by_severity,
        by_source=_ranked(sources, 50),
        top_ips=_ranked(ips, top),
        top_users=_ranked(users, top),
        per_day=sorted(days.items()),
        first=min(moments),
        last=max(moments),
        highlights=build_highlights(events, by_severity, ips, users),
    )


def build_highlights(
    events: Sequence[Event],
    by_severity: dict[str, int],
    ips: Counter[str],
    users: Counter[str],
) -> list[str]:
    """Frases del resumen ejecutivo, generadas con reglas fijas y explicables.

    No usa IA ni puntajes: cada frase sale de un conteo que se puede verificar
    en la tabla del reporte.
    """
    lines: list[str] = []
    urgent = by_severity["critica"] + by_severity["alta"]
    if urgent:
        lines.append(
            f"Hay {urgent} evento(s) de severidad crítica o alta "
            f"({by_severity['critica']} crítica(s), {by_severity['alta']} alta(s)); revísalos primero."
        )
    else:
        lines.append("No hay eventos de severidad crítica ni alta en este conjunto de datos.")

    repeated_ips = [(ip, n) for ip, n in _ranked(ips, 50) if n >= 3]
    if repeated_ips:
        ip, n = repeated_ips[0]
        lines.append(f"La IP {ip} aparece en {n} eventos; es la más repetida.")
    repeated_users = [(user, n) for user, n in _ranked(users, 50) if n >= 3]
    if repeated_users:
        user, n = repeated_users[0]
        lines.append(f"La cuenta {user} aparece en {n} eventos; es la más repetida.")
    return lines


def severity_label(severity: str) -> str:
    return SEVERITY_LABELS[severity]
