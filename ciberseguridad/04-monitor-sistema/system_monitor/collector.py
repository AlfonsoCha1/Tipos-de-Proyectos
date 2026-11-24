"""Toma de mediciones (CPU, memoria y discos) y evaluación contra umbrales.

La lectura del sistema se hace a través de un "lector" con la misma interfaz
que ``psutil``. Así las pruebas y el modo ``--demo`` usan un lector simulado y
el resto del código no cambia: la lógica de umbrales se prueba sin depender de
cuánto CPU esté usando la máquina en ese momento.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, Sequence

LEVELS = ("OK", "AVISO", "ALERTA")
SKIP_FSTYPES = {"squashfs", "tmpfs", "devtmpfs", "overlay", "iso9660", "udf", "proc", "sysfs"}


class Reader(Protocol):
    """Lo que se necesita de psutil (o de un lector simulado)."""

    def cpu_percent(self, interval: float | None = ...) -> float: ...
    def virtual_memory(self) -> Any: ...
    def disk_partitions(self, all: bool = ...) -> Sequence[Any]: ...
    def disk_usage(self, path: str) -> Any: ...


@dataclass(frozen=True)
class Thresholds:
    warning: float
    critical: float

    def __post_init__(self) -> None:
        if not 0 < self.warning < self.critical <= 100:
            raise ValueError("los umbrales deben cumplir 0 < aviso < alerta <= 100")

    def level(self, percent: float) -> str:
        if percent >= self.critical:
            return "ALERTA"
        if percent >= self.warning:
            return "AVISO"
        return "OK"


@dataclass(frozen=True)
class Measurement:
    name: str  # "CPU", "Memoria" o "Disco /"
    percent: float
    used: int | None
    total: int | None
    level: str


@dataclass
class Snapshot:
    taken_at: datetime
    measurements: list[Measurement] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def worst(self) -> str:
        return max((m.level for m in self.measurements), key=LEVELS.index, default="OK")


def _disks(reader: Reader) -> tuple[list[tuple[str, Any]], list[str]]:
    """Particiones reales, sin duplicar el mismo dispositivo ni sistemas de archivos virtuales."""
    disks, notes, seen = [], [], set()
    for part in reader.disk_partitions(all=False):
        if part.fstype.lower() in SKIP_FSTYPES or part.device in seen or "cdrom" in (part.opts or ""):
            continue
        try:
            usage = reader.disk_usage(part.mountpoint)
        except (PermissionError, OSError) as exc:  # unidad de CD vacía, disco desmontado...
            notes.append(f"No se pudo leer {part.mountpoint}: {exc}")
            continue
        seen.add(part.device)
        disks.append((part.mountpoint, usage))
    return disks, notes


def take_snapshot(reader: Reader, limits: dict[str, Thresholds], cpu_interval: float = 1.0) -> Snapshot:
    """Una medición completa. ``cpu_interval`` es el tiempo que se observa la CPU (en segundos)."""
    snapshot = Snapshot(datetime.now(timezone.utc))
    cpu = float(reader.cpu_percent(interval=cpu_interval))
    snapshot.measurements.append(Measurement("CPU", cpu, None, None, limits["cpu"].level(cpu)))
    memory = reader.virtual_memory()
    snapshot.measurements.append(Measurement(
        "Memoria", float(memory.percent), int(memory.total - memory.available), int(memory.total),
        limits["memory"].level(float(memory.percent)),
    ))
    disks, notes = _disks(reader)
    snapshot.notes += notes
    for mountpoint, usage in disks:
        snapshot.measurements.append(Measurement(
            f"Disco {mountpoint}", float(usage.percent), int(usage.used), int(usage.total),
            limits["disk"].level(float(usage.percent)),
        ))
    return snapshot


def format_bytes(num: int | None) -> str:
    if num is None:
        return "-"
    value = float(num)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TiB"  # pragma: no cover


class SimulatedReader:
    """Lector con valores fijos que cambian en cada muestra (modo --demo y pruebas)."""

    def __init__(self, cpu: Sequence[float] = (35.0, 82.0, 97.5), memory: Sequence[float] = (61.0, 64.0, 91.0),
                 disks: Sequence[tuple[str, float]] = (("/", 72.0), ("/datos", 93.0))) -> None:
        self._cpu, self._memory, self._disks = list(cpu), list(memory), list(disks)
        self._sample = 0

    def _pick(self, values: list[float]) -> float:
        return values[min(self._sample, len(values) - 1)]

    def cpu_percent(self, interval: float | None = None) -> float:
        value = self._pick(self._cpu)
        return value

    def virtual_memory(self) -> Any:
        percent = self._pick(self._memory)
        total = 16 * 1024**3
        return _Obj(percent=percent, total=total, available=int(total * (100 - percent) / 100))

    def disk_partitions(self, all: bool = False) -> list[Any]:
        return [_Obj(device=f"/dev/sim{i}", mountpoint=mount, fstype="ext4", opts="rw")
                for i, (mount, _) in enumerate(self._disks)]

    def disk_usage(self, path: str) -> Any:
        percent = dict(self._disks)[path]
        total = 500 * 1024**3
        self_used = int(total * percent / 100)
        return _Obj(percent=percent, total=total, used=self_used)

    def advance(self) -> None:
        self._sample += 1


class _Obj:
    def __init__(self, **values: Any) -> None:
        self.__dict__.update(values)
