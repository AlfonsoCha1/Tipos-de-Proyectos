"""Pruebas del monitor con un lector simulado (no dependen de la carga real del equipo)."""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

import pytest

from system_monitor.cli import load_limits, main
from system_monitor.collector import SimulatedReader, Thresholds, format_bytes, take_snapshot, _Obj

PROJECT = Path(__file__).resolve().parent.parent
LIMITS = {"cpu": Thresholds(75, 90), "memory": Thresholds(80, 90), "disk": Thresholds(80, 90)}


@pytest.mark.parametrize("percent, level", [(0, "OK"), (74.9, "OK"), (75, "AVISO"), (89.9, "AVISO"), (90, "ALERTA"), (100, "ALERTA")])
def test_threshold_levels(percent, level):
    assert Thresholds(75, 90).level(percent) == level


@pytest.mark.parametrize("warning, critical", [(0, 50), (90, 80), (50, 50), (80, 101)])
def test_invalid_thresholds(warning, critical):
    with pytest.raises(ValueError):
        Thresholds(warning, critical)


def test_snapshot_with_simulated_reader():
    snapshot = take_snapshot(SimulatedReader(), LIMITS, cpu_interval=0)
    names = [m.name for m in snapshot.measurements]
    assert names == ["CPU", "Memoria", "Disco /", "Disco /datos"]
    assert snapshot.worst == "ALERTA"  # /datos al 93 %
    memory = snapshot.measurements[1]
    assert memory.total == 16 * 1024**3 and memory.level == "OK"


class TrickyReader(SimulatedReader):
    """Discos repetidos, virtuales y uno que no se puede leer, como pasa en Linux y Windows reales."""

    def disk_partitions(self, all=False):
        return [
            _Obj(device="/dev/sda1", mountpoint="/", fstype="ext4", opts="rw"),
            _Obj(device="/dev/sda1", mountpoint="/home", fstype="ext4", opts="rw"),  # mismo dispositivo
            _Obj(device="/dev/loop0", mountpoint="/snap/app", fstype="squashfs", opts="ro"),
            _Obj(device="D:\\", mountpoint="D:\\", fstype="", opts="cdrom"),
            _Obj(device="/dev/sdb1", mountpoint="/mnt/usb", fstype="vfat", opts="rw"),
        ]

    def disk_usage(self, path):
        if path == "/mnt/usb":
            raise PermissionError(13, "Permiso denegado")
        return _Obj(percent=50.0, total=100, used=50)


def test_disk_filtering_and_unreadable_disks():
    snapshot = take_snapshot(TrickyReader(), LIMITS, cpu_interval=0)
    disks = [m.name for m in snapshot.measurements if m.name.startswith("Disco")]
    assert disks == ["Disco /"]
    assert any("/mnt/usb" in note for note in snapshot.notes)


@pytest.mark.parametrize("num, text", [(None, "-"), (512, "512 B"), (2048, "2.0 KiB"), (3 * 1024**3, "3.0 GiB")])
def test_format_bytes(num, text):
    assert format_bytes(num) == text


def test_default_config_is_valid():
    limits = load_limits(None)
    assert limits["cpu"].critical == 90


def test_demo_output_and_fail_on(capsys):
    assert main(["--demo"]) == 0
    out = capsys.readouterr().out
    assert "valores SIMULADOS" in out
    assert "Muestra 3/3" in out and "CPU al 97.5 %" in out
    assert main(["--demo", "--fail-on", "alerta"]) == 3


def test_real_mode_uses_injected_reader_and_sleep(capsys):
    waits = []
    assert main(["--samples", "2", "--interval", "3"], sleep=waits.append, reader=SimulatedReader(cpu=(10, 10))) == 0
    assert waits == [2.0]  # 3 s entre muestras menos 1 s observando la CPU
    assert "Muestra 2/2" in capsys.readouterr().out


def test_export_csv_and_force(tmp_path, capsys):
    out = tmp_path / "m.csv"
    assert main(["--demo", "--export-csv", str(out)]) == 0
    rows = list(csv.reader(out.open(encoding="utf-8-sig")))
    assert rows[0][:3] == ["fecha_utc", "metrica", "porcentaje"]
    assert len(rows) == 1 + 3 * 4
    assert main(["--demo", "--export-csv", str(out)]) == 1
    assert main(["--demo", "--export-csv", str(out), "--force"]) == 0


@pytest.mark.parametrize(
    "config, message",
    [({"cpu": {"aviso": 75, "alerta": 90}}, "falta 'memoria'"),
     ({"cpu": {"aviso": 95, "alerta": 90}, "memoria": {"aviso": 1, "alerta": 2}, "disco": {"aviso": 1, "alerta": 2}}, "0 < aviso"),
     ({"cpu": {"aviso": "x", "alerta": 90}, "memoria": {"aviso": 1, "alerta": 2}, "disco": {"aviso": 1, "alerta": 2}}, "cpu")],
)
def test_invalid_config(tmp_path, capsys, config, message):
    path = tmp_path / "c.json"
    path.write_text(json.dumps(config), encoding="utf-8")
    assert main(["--demo", "--config", str(path)]) == 1
    assert message in capsys.readouterr().err


def test_invalid_arguments():
    with pytest.raises(SystemExit):
        main(["--samples", "0"])
    with pytest.raises(SystemExit):
        main(["--interval", "-1"])


def test_ctrl_c_keeps_what_was_measured(capsys):
    def interrupt(seconds):
        raise KeyboardInterrupt

    assert main(["--samples", "5", "--interval", "2"], sleep=interrupt, reader=SimulatedReader()) == 0
    out = capsys.readouterr().out
    assert "Detenido por el usuario" in out and "Resumen de 1 muestra(s)" in out


def test_real_psutil_reading():
    pytest.importorskip("psutil")
    completed = subprocess.run(
        [sys.executable, "-m", "system_monitor", "--samples", "1"],
        cwd=PROJECT, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert completed.returncode == 0
    assert "CPU" in completed.stdout and "Memoria" in completed.stdout
