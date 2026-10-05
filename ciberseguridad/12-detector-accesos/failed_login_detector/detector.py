"""Detección de demasiados intentos fallidos dentro de una ventana de tiempo.

Regla: hay alerta cuando una misma clave (una cuenta o una IP) acumula al
menos ``threshold`` fallos cuyo primero y último están separados por como
máximo ``window`` minutos.

Algoritmo (ventana deslizante):

1. Se ordenan todos los eventos por fecha UTC. Los registros pueden venir
   desordenados (varios servidores, rotación de logs, relojes distintos).
2. Para cada clave se mantiene una cola (``deque``) con sus fallos recientes.
   Al llegar un fallo nuevo se agrega a la derecha y se sacan por la
   izquierda los que quedaron fuera de la ventana.
3. Si la cola alcanza el umbral, se abre una alerta. Mientras los fallos
   sigan llegando sin que la ráfaga se interrumpa, se amplía la MISMA
   alerta en vez de crear una por cada fallo extra.
4. Al final se busca un acceso EXITOSO de la misma clave durante la ráfaga
   o poco después, porque eso puede indicar que el ataque funcionó.

Este módulo solo detecta. No bloquea cuentas ni IPs: decidir una respuesta
requiere revisión humana (ver README).
"""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable, Sequence

from .models import LoginEvent, Outcome

RULES = ("user", "ip")
RULE_LABELS = {"user": "Cuenta", "ip": "IP"}

_KEY: dict[str, Callable[[LoginEvent], str]] = {"user": lambda e: e.user, "ip": lambda e: e.ip}
# Dato "relacionado" que se muestra en la alerta: para una cuenta, desde qué
# IPs la atacaron; para una IP, qué cuentas intentó.
_RELATED: dict[str, Callable[[LoginEvent], str]] = {"user": lambda e: e.ip, "ip": lambda e: e.user}


@dataclass(frozen=True)
class DetectionSettings:
    """Parámetros de detección ya validados.

    Attributes:
        threshold: fallos necesarios para alertar (mínimo 2).
        window: separación máxima entre el primer y el último fallo contado.
        success_after: margen tras el último fallo para buscar un acceso exitoso.
        rules: reglas activas: ``"user"``, ``"ip"`` o ambas.
        max_evidence: ubicaciones (archivo:línea) que se guardan por alerta.
    """

    threshold: int = 5
    window: timedelta = timedelta(minutes=5)
    success_after: timedelta = timedelta(minutes=15)
    rules: tuple[str, ...] = RULES
    max_evidence: int = 10

    def __post_init__(self) -> None:
        if self.threshold < 2:
            raise ValueError("el umbral debe ser al menos 2 fallos")
        if self.window <= timedelta(0):
            raise ValueError("la ventana debe ser mayor que 0")
        if self.success_after < timedelta(0):
            raise ValueError("el margen para éxito posterior no puede ser negativo")
        if not self.rules or any(rule not in RULES for rule in self.rules):
            raise ValueError(f"reglas válidas: {', '.join(RULES)}")
        if self.max_evidence < 1:
            raise ValueError("max_evidence debe ser al menos 1")


@dataclass
class Alert:
    """Una ráfaga de fallos que superó el umbral.

    Attributes:
        rule: ``"user"`` o ``"ip"``.
        key: la cuenta o la IP afectada.
        first_seen / last_seen: primer y último fallo de la ráfaga (UTC).
        failures: número de fallos en la ráfaga.
        related: IPs (regla de cuenta) o cuentas (regla de IP) involucradas.
        evidence: primeras ubicaciones ``(archivo, línea)`` de los fallos.
        success_after: primer acceso exitoso de la misma clave durante la
            ráfaga o dentro del margen posterior; ``None`` si no hubo.
    """

    rule: str
    key: str
    first_seen: datetime
    last_seen: datetime
    failures: int = 0
    related: set[str] = field(default_factory=set)
    evidence: list[tuple[str, int]] = field(default_factory=list)
    success_after: LoginEvent | None = None
    # Posición del último evento agregado; sirve para no contar dos veces.
    _last_position: int = field(default=-1, repr=False, compare=False)

    @property
    def severity(self) -> str:
        """``alta`` si hubo un acceso exitoso asociado; ``media`` en otro caso."""
        return "alta" if self.success_after is not None else "media"

    @property
    def duration(self) -> timedelta:
        return self.last_seen - self.first_seen


@dataclass
class DetectionResult:
    """Alertas y estadísticas del análisis."""

    alerts: list[Alert]
    total_events: int
    failures: int
    successes: int
    out_of_order: int


def count_out_of_order(events: Sequence[LoginEvent]) -> int:
    """Cuenta eventos cuya fecha es anterior a la de algún evento leído antes.

    Es un dato informativo: muestra cuánto se habría equivocado un detector
    que asumiera que el archivo viene ordenado.
    """
    count = 0
    latest: datetime | None = None
    for event in events:
        if latest is not None and event.timestamp < latest:
            count += 1
        else:
            latest = event.timestamp
    return count


def _add_to_alert(alert: Alert, position: int, event: LoginEvent, rule: str, max_evidence: int) -> None:
    alert.failures += 1
    alert.last_seen = event.timestamp
    alert.related.add(_RELATED[rule](event))
    if len(alert.evidence) < max_evidence:
        alert.evidence.append((event.source, event.line_no))
    alert._last_position = position


def _detect_rule(ordered: Sequence[LoginEvent], rule: str, settings: DetectionSettings) -> list[Alert]:
    """Aplica la ventana deslizante para una regla (cuenta o IP)."""
    key_of = _KEY[rule]
    windows: defaultdict[str, deque[tuple[int, LoginEvent]]] = defaultdict(deque)
    active: dict[str, Alert] = {}
    alerts: list[Alert] = []

    for position, event in enumerate(ordered):
        if event.outcome is not Outcome.FAILURE:
            continue
        key = key_of(event)
        window = windows[key]
        window.append((position, event))

        cutoff = event.timestamp - settings.window
        while window[0][1].timestamp < cutoff:
            window.popleft()
        if len(window) < settings.threshold:
            continue

        alert = active.get(key)
        if alert is not None and alert.last_seen >= cutoff:
            # La ráfaga sigue: se agregan solo los fallos que la alerta aún no tiene.
            for queued_position, queued in window:
                if queued_position > alert._last_position:
                    _add_to_alert(alert, queued_position, queued, rule, settings.max_evidence)
        else:
            first = window[0][1]
            alert = Alert(rule=rule, key=key, first_seen=first.timestamp, last_seen=first.timestamp)
            for queued_position, queued in window:
                _add_to_alert(alert, queued_position, queued, rule, settings.max_evidence)
            active[key] = alert
            alerts.append(alert)
    return alerts


def _attach_successes(alerts: list[Alert], ordered: Sequence[LoginEvent], settings: DetectionSettings) -> None:
    """Asocia a cada alerta el primer éxito de la misma clave durante o después de la ráfaga.

    Se hace en una segunda pasada porque un éxito puede ocurrir en medio de
    la ráfaga, antes de que la alerta exista.
    """
    successes: dict[str, defaultdict[str, list[LoginEvent]]] = {rule: defaultdict(list) for rule in RULES}
    times: dict[str, defaultdict[str, list[datetime]]] = {rule: defaultdict(list) for rule in RULES}
    for event in ordered:  # ya ordenados: cada lista queda ordenada por fecha
        if event.outcome is Outcome.SUCCESS:
            for rule in RULES:
                key = _KEY[rule](event)
                successes[rule][key].append(event)
                times[rule][key].append(event.timestamp)

    for alert in alerts:
        candidates = successes[alert.rule].get(alert.key, [])
        # Búsqueda binaria: primer éxito con fecha >= inicio de la ráfaga.
        index = bisect_left(times[alert.rule].get(alert.key, []), alert.first_seen)
        if index < len(candidates) and candidates[index].timestamp <= alert.last_seen + settings.success_after:
            alert.success_after = candidates[index]


def sort_events(events: Sequence[LoginEvent]) -> list[LoginEvent]:
    """Ordena por fecha UTC; a igual fecha conserva el orden de lectura (orden estable)."""
    return sorted(events, key=lambda event: event.timestamp)


def detect(events: Sequence[LoginEvent], settings: DetectionSettings) -> DetectionResult:
    """Busca ráfagas de intentos fallidos según ``settings``.

    Args:
        events: eventos en el orden en que se leyeron (pueden estar desordenados).
        settings: umbral, ventana, reglas y márgenes.

    Returns:
        Alertas ordenadas por fecha de inicio, más estadísticas generales.
    """
    ordered = sort_events(events)
    alerts: list[Alert] = []
    for rule in settings.rules:
        alerts.extend(_detect_rule(ordered, rule, settings))
    _attach_successes(alerts, ordered, settings)
    alerts.sort(key=lambda alert: (alert.first_seen, alert.rule, alert.key))

    failures = sum(1 for event in events if event.outcome is Outcome.FAILURE)
    return DetectionResult(
        alerts=alerts,
        total_events=len(events),
        failures=failures,
        successes=len(events) - failures,
        out_of_order=count_out_of_order(events),
    )
