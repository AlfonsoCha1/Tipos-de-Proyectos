"""Interfaz de línea de comandos del monitor básico del sistema.

Códigos de salida: 0 = correcto, 1 = error de configuración, exportación o
falta de psutil, 2 = argumentos inválidos, 3 = se alcanzó el nivel de ``--fail-on``.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Callable, Sequence

from . import __version__
from .collector import LEVELS, SimulatedReader, Snapshot, Thresholds, format_bytes, take_snapshot

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "settings.json"
CONFIG_KEYS = {"cpu": "cpu", "memoria": "memory", "disco": "disk"}


class MonitorError(Exception):
    """Error esperado de configuración, exportación o dependencias."""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m system_monitor",
        description="Mide CPU, memoria y discos, y los compara con umbrales de AVISO y ALERTA. Solo lee; no cambia nada.",
    )
    parser.add_argument("--samples", type=int, default=1, metavar="N", help="número de mediciones (por defecto 1)")
    parser.add_argument("--interval", type=float, default=2.0, metavar="SEG", help="segundos entre mediciones (por defecto 2)")
    parser.add_argument("--config", type=Path, metavar="JSON", help="umbrales alternativos")
    parser.add_argument("--export-csv", type=Path, metavar="RUTA", help="guarda todas las mediciones en CSV")
    parser.add_argument("--force", action="store_true", help="permite sobrescribir el CSV")
    parser.add_argument("--fail-on", choices=("aviso", "alerta"), help="devuelve 3 si alguna medición alcanza ese nivel")
    parser.add_argument("--demo", action="store_true", help="usa valores simulados (3 muestras con avisos y alertas)")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def load_limits(path: Path | None) -> dict[str, Thresholds]:
    config_path = path or DEFAULT_CONFIG
    try:
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise MonitorError(f"No existe el archivo de configuración: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise MonitorError(f"{config_path} no es JSON válido (línea {exc.lineno}): {exc.msg}") from exc
    limits = {}
    for key, internal in CONFIG_KEYS.items():
        entry = data.get(key) if isinstance(data, dict) else None
        if not isinstance(entry, dict):
            raise MonitorError(f"falta '{key}' con 'aviso' y 'alerta' en {config_path}")
        try:
            limits[internal] = Thresholds(float(entry["aviso"]), float(entry["alerta"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise MonitorError(f"'{key}': {exc}") from exc
    return limits


def render_snapshot(snapshot: Snapshot, number: int, total: int) -> str:
    rows = [(m.name, f"{m.percent:.1f} %", format_bytes(m.used), format_bytes(m.total), m.level)
            for m in snapshot.measurements]
    headers = ("MÉTRICA", "USO", "USADO", "TOTAL", "ESTADO")
    widths = [max(len(h), *(len(r[i]) for r in rows)) for i, h in enumerate(headers)]
    lines = [f"Muestra {number}/{total}  {snapshot.taken_at:%Y-%m-%d %H:%M:%S} UTC"]
    for row in (headers, *rows):
        lines.append("  ".join(v.rjust(w) if i in (1, 2, 3) else v.ljust(w) for i, (v, w) in enumerate(zip(row, widths))).rstrip())
    lines += [f"Nota: {note}" for note in snapshot.notes]
    return "\n".join(lines)


def render_summary(snapshots: Sequence[Snapshot]) -> str:
    peaks: dict[str, tuple[float, str]] = {}
    for snapshot in snapshots:
        for m in snapshot.measurements:
            if m.name not in peaks or m.percent > peaks[m.name][0]:
                peaks[m.name] = (m.percent, m.level)
    lines = [f"Resumen de {len(snapshots)} muestra(s): máximo por métrica"]
    width = max(len(name) for name in peaks)
    for name, (percent, level) in peaks.items():
        lines.append(f"  {name.ljust(width)}  {percent:5.1f} %  {level}")
    alerts = [(s, m) for s in snapshots for m in s.measurements if m.level != "OK"]
    if alerts:
        lines.append(f"Eventos fuera de lo normal: {len(alerts)}")
        for snapshot, m in alerts:
            lines.append(f"  {snapshot.taken_at:%H:%M:%S} UTC  {m.level:<6} {m.name} al {m.percent:.1f} %")
    else:
        lines.append("Todo dentro de los umbrales.")
    return "\n".join(lines)


def export_csv(snapshots: Sequence[Snapshot], path: Path, force: bool) -> None:
    if path.exists() and not force:
        raise MonitorError(f"{path} ya existe. Usa --force para sobrescribirlo.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["fecha_utc", "metrica", "porcentaje", "usado_bytes", "total_bytes", "estado"])
        for snapshot in snapshots:
            for m in snapshot.measurements:
                writer.writerow([snapshot.taken_at.isoformat(timespec="seconds"), m.name, f"{m.percent:.1f}",
                                 "" if m.used is None else m.used, "" if m.total is None else m.total, m.level])


def _real_reader():
    try:
        import psutil  # importación tardía: el modo --demo y las pruebas no la necesitan
    except ImportError as exc:
        raise MonitorError("falta psutil. Instálalo con: python -m pip install -r requirements.txt") from exc
    return psutil


def main(argv: Sequence[str] | None = None, sleep: Callable[[float], None] = time.sleep, reader=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    if not 1 <= args.samples <= 10_000:
        parser.error("--samples debe estar entre 1 y 10000")
    if args.interval < 0:
        parser.error("--interval no puede ser negativo")
    try:
        limits = load_limits(args.config)
        if args.export_csv is not None and args.export_csv.exists() and not args.force:
            raise MonitorError(f"{args.export_csv} ya existe. Usa --force para sobrescribirlo.")
        if args.demo:
            reader = SimulatedReader()
            samples, cpu_interval, wait = 3, 0.0, 0.0
            print("Modo demostración: valores SIMULADOS (no son de este equipo).\n")
        else:
            reader = reader or _real_reader()
            samples, cpu_interval, wait = args.samples, 1.0, max(0.0, args.interval - 1.0)

        title = "Monitor básico del sistema - Cybersecurity Python Lab"
        print(title + "\n" + "=" * len(title))
        print("Umbrales (aviso / alerta): " + ", ".join(
            f"{name} {limits[key].warning:g}/{limits[key].critical:g} %" for name, key in CONFIG_KEYS.items()) + "\n")
        snapshots: list[Snapshot] = []
        try:
            for number in range(1, samples + 1):
                snapshots.append(take_snapshot(reader, limits, cpu_interval))
                if args.demo:  # horas simuladas: una muestra cada 2 segundos
                    snapshots[-1].taken_at = snapshots[0].taken_at + timedelta(seconds=2 * (number - 1))
                print(render_snapshot(snapshots[-1], number, samples) + "\n")
                if hasattr(reader, "advance"):
                    reader.advance()
                if number < samples and wait:
                    sleep(wait)
        except KeyboardInterrupt:
            print("\nDetenido por el usuario (Ctrl+C).\n")
        if snapshots:
            print(render_summary(snapshots))
        if args.export_csv is not None and snapshots:
            export_csv(snapshots, args.export_csv, args.force)
            print(f"\nMediciones exportadas a CSV: {args.export_csv}")
        if args.fail_on:
            threshold = LEVELS.index(args.fail_on.upper())
            if any(LEVELS.index(s.worst) >= threshold for s in snapshots):
                return 3
        return 0
    except MonitorError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
