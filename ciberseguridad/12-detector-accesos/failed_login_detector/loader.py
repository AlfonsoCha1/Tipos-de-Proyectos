"""Carga de eventos desde uno o varios archivos.

A diferencia del contador (proyecto 09), el detector necesita TODOS los
eventos en memoria para ordenarlos por fecha antes de aplicar la ventana.
Ese es el precio de aceptar registros desordenados (ver Limitaciones en el
README).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .models import LoginEvent, UnparsedLine
from .parsers import ParseOptions, detect_format, read_log


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
class LoadedLogs:
    """Eventos leídos, en el orden original, y diagnóstico de la lectura."""

    events: list[LoginEvent] = field(default_factory=list)
    files: list[FileStats] = field(default_factory=list)
    unparsed: list[UnparsedLine] = field(default_factory=list)
    unparsed_total: int = 0


def load_events(
    paths: Iterable[Path],
    fmt: str,
    options: ParseOptions,
    max_unparsed_kept: int = 500,
) -> LoadedLogs:
    """Lee los archivos y devuelve sus eventos junto con las estadísticas.

    Args:
        paths: archivos a leer, en orden.
        fmt: ``"auto"`` o un formato fijo (``lab``, ``syslog``, ``csv``).
        options: zona horaria por defecto y año para syslog.
        max_unparsed_kept: máximo de líneas no interpretadas que se guardan.

    Raises:
        LogFormatError: si un archivo tiene un formato desconocido.
        OSError: si un archivo no se puede leer.
    """
    loaded = LoadedLogs()
    for path in paths:
        file_format = detect_format(path) if fmt == "auto" else fmt
        stats = FileStats(source=str(path), fmt=file_format)
        loaded.files.append(stats)
        for result in read_log(path, file_format, options):
            stats.lines = max(stats.lines, result.line_no)
            if result.error is not None:
                stats.unparsed += 1
                loaded.unparsed_total += 1
                if len(loaded.unparsed) < max_unparsed_kept:
                    loaded.unparsed.append(result.error)
            elif result.ignored:
                stats.ignored += 1
            else:
                stats.events += len(result.events)
                loaded.events.extend(result.events)
    return loaded
