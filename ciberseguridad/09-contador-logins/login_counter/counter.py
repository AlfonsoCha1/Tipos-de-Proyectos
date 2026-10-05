"""Lógica de conteo: acumula intentos exitosos y fallidos por usuario e IP.

Este módulo no imprime nada ni lee argumentos de terminal; solo transforma
eventos en un resumen. Eso permite probarlo sin pasar por la interfaz.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable

from .models import LoginEvent, Outcome, UnparsedLine
from .parsers import LineResult, ParseOptions, detect_format, read_log


@dataclass
class Tally:
    """Contador de éxitos y fallos para una clave (usuario, IP o total)."""

    success: int = 0
    failure: int = 0

    @property
    def total(self) -> int:
        return self.success + self.failure

    def add(self, outcome: Outcome) -> None:
        if outcome is Outcome.SUCCESS:
            self.success += 1
        else:
            self.failure += 1


@dataclass
class FileStats:
    """Estadísticas de lectura de un archivo."""

    source: str
    fmt: str
    lines: int = 0
    events: int = 0
    ignored: int = 0
    unparsed: int = 0


@dataclass
class LoginSummary:
    """Resultado final del análisis, listo para mostrarse o exportarse."""

    files: list[FileStats]
    totals: Tally
    by_user: dict[str, Tally]
    by_ip: dict[str, Tally]
    invalid_user_failures: int
    first_seen: datetime | None
    last_seen: datetime | None
    unparsed: list[UnparsedLine]
    unparsed_total: int

    @property
    def failure_rate(self) -> float | None:
        """Porcentaje de intentos fallidos, o ``None`` si no hubo intentos."""
        if not self.totals.total:
            return None
        return 100 * self.totals.failure / self.totals.total


@dataclass
class LoginCounter:
    """Acumula eventos sin guardarlos.

    La memoria usada crece con el número de usuarios e IPs distintos, no con
    el tamaño del archivo. Solo se conservan las primeras
    ``max_unparsed_kept`` líneas no interpretadas (el total sí se cuenta).
    """

    max_unparsed_kept: int = 500
    files: list[FileStats] = field(default_factory=list)
    totals: Tally = field(default_factory=Tally)
    by_user: defaultdict[str, Tally] = field(default_factory=lambda: defaultdict(Tally))
    by_ip: defaultdict[str, Tally] = field(default_factory=lambda: defaultdict(Tally))
    invalid_user_failures: int = 0
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    unparsed: list[UnparsedLine] = field(default_factory=list)
    unparsed_total: int = 0

    def add_event(self, event: LoginEvent) -> None:
        """Suma un evento a los contadores total, por usuario y por IP."""
        self.totals.add(event.outcome)
        self.by_user[event.user].add(event.outcome)
        self.by_ip[event.ip].add(event.outcome)
        if event.invalid_user and event.outcome is Outcome.FAILURE:
            self.invalid_user_failures += 1
        # Los registros pueden venir desordenados: se compara cada fecha.
        if self.first_seen is None or event.timestamp < self.first_seen:
            self.first_seen = event.timestamp
        if self.last_seen is None or event.timestamp > self.last_seen:
            self.last_seen = event.timestamp

    def add_line(self, result: LineResult, stats: FileStats) -> None:
        """Clasifica el resultado de una línea y actualiza las estadísticas del archivo."""
        stats.lines = max(stats.lines, result.line_no)
        if result.error is not None:
            stats.unparsed += 1
            self.unparsed_total += 1
            if len(self.unparsed) < self.max_unparsed_kept:
                self.unparsed.append(result.error)
        elif result.ignored:
            stats.ignored += 1
        else:
            for event in result.events:
                stats.events += 1
                self.add_event(event)

    def summary(self) -> LoginSummary:
        """Devuelve una copia del estado actual para que el contador pueda seguir usándose."""
        return LoginSummary(
            files=list(self.files),
            totals=Tally(self.totals.success, self.totals.failure),
            by_user=dict(self.by_user),
            by_ip=dict(self.by_ip),
            invalid_user_failures=self.invalid_user_failures,
            first_seen=self.first_seen,
            last_seen=self.last_seen,
            unparsed=list(self.unparsed),
            unparsed_total=self.unparsed_total,
        )


def analyze_files(
    paths: Iterable[Path],
    fmt: str,
    options: ParseOptions,
    max_unparsed_kept: int = 500,
) -> LoginSummary:
    """Lee uno o varios archivos y devuelve el resumen combinado.

    Args:
        paths: archivos a analizar.
        fmt: ``"auto"`` para detectar el formato de cada archivo, o uno fijo.
        options: zona horaria por defecto y año para syslog.
        max_unparsed_kept: máximo de líneas no interpretadas que se guardan.

    Raises:
        LogFormatError: si un archivo tiene un formato desconocido.
        OSError: si un archivo no se puede leer.
    """
    counter = LoginCounter(max_unparsed_kept=max_unparsed_kept)
    for path in paths:
        file_format = detect_format(path) if fmt == "auto" else fmt
        stats = FileStats(source=str(path), fmt=file_format)
        counter.files.append(stats)
        for result in read_log(path, file_format, options):
            counter.add_line(result, stats)
    return counter.summary()


def ranked(tallies: dict[str, Tally], top: int = 0) -> list[tuple[str, Tally]]:
    """Ordena por fallos (desc), luego total (desc) y luego nombre.

    Args:
        tallies: contadores por clave.
        top: cuántos devolver; ``0`` significa todos.
    """
    ordered = sorted(tallies.items(), key=lambda item: (-item[1].failure, -item[1].total, item[0]))
    return ordered[:top] if top > 0 else ordered
