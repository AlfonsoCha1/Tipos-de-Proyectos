"""Modelos de datos de los registros de login.

Copia intencional compartida por los proyectos 09 y 12 (ver
docs/ARQUITECTURA.md en la raíz del repositorio).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Outcome(Enum):
    """Resultado de un intento de inicio de sesión."""

    SUCCESS = "success"
    FAILURE = "failure"


@dataclass(frozen=True, slots=True)
class LoginEvent:
    """Un intento de login ya interpretado.

    Attributes:
        timestamp: fecha del intento, siempre en UTC.
        user: cuenta tal como aparece en el registro (distingue mayúsculas).
        ip: dirección IP normalizada (por ejemplo, IPv6 comprimida).
        outcome: éxito o fallo.
        source: archivo de origen, tal como lo escribió quien ejecutó la herramienta.
        line_no: número de línea en ``source`` (empieza en 1).
        invalid_user: ``True`` si el registro indica que la cuenta no existe
            (solo disponible en el formato syslog de OpenSSH).
    """

    timestamp: datetime
    user: str
    ip: str
    outcome: Outcome
    source: str
    line_no: int
    invalid_user: bool = False

    @property
    def location(self) -> str:
        """Ubicación legible del evento, por ejemplo ``samples/auth_lab.log:12``."""
        return f"{self.source}:{self.line_no}"


@dataclass(frozen=True, slots=True)
class UnparsedLine:
    """Una línea que parecía relevante pero no se pudo interpretar.

    Attributes:
        source: archivo de origen.
        line_no: número de línea.
        reason: explicación en español de por qué se rechazó.
        text: contenido de la línea, recortado para no inflar los reportes.
    """

    source: str
    line_no: int
    reason: str
    text: str
