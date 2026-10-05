"""Pruebas de la interfaz: comandos del README sobre los datos de ejemplo."""

import json
from pathlib import Path

import pytest

from log_search.cli import main

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
LAB = str(SAMPLES / "auth_lab.log")
APP = str(SAMPLES / "app_mixed.log")
SYSLOG = str(SAMPLES / "auth_syslog.log")


def run(capsys, *args):
    code = main([str(a) for a in args])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_busqueda_de_palabra_en_muestra(capsys):
    code, out, _ = run(capsys, LAB, "-k", "admin")
    assert code == 0
    assert "Total: 8 coincidencia(s) en 1 archivo(s)." in out


def test_rango_cidr_cuenta(capsys):
    code, out, _ = run(capsys, LAB, "--cidr", "198.51.100.0/24", "--count")
    assert code == 0 and "7 coincidencia(s)" in out
    assert "==" not in out  # --count no muestra líneas


def test_contexto_marca_coincidencias_y_contexto(capsys):
    _, out, _ = run(capsys, APP, "-k", "reintento", "-C", "1")
    assert ": 2026-09-14T09:12:31-06:00 INFO  app: reintento 1 de 3" in out
    assert "TimeoutError" in out  # línea de contexto anterior


def test_separador_entre_bloques(capsys):
    _, out, _ = run(capsys, APP, "-k", "ana", "-C", "0")
    assert "   --" in out


def test_ipv6_en_cidr(capsys):
    _, out, _ = run(capsys, APP, "--cidr", "2001:db8::/32")
    assert "ip=2001:db8::50" in out and "Total: 1 " in out


def test_filtro_de_fechas_con_zona(capsys):
    _, out, _ = run(capsys, APP, "--from", "2026-09-15", "--to", "2026-09-15", "--tz=-06:00")
    assert "Total: 3 coincidencia(s)" in out
    assert "2026-09-14" not in out.split("Resumen")[0].split("==")[-1]


def test_lineas_sin_fecha_aparecen_en_el_resumen(capsys):
    _, out, _ = run(capsys, APP, "--from", "2026-09-14")
    assert "sin fecha reconocible" in out


def test_syslog_con_anio(capsys):
    _, out, _ = run(capsys, SYSLOG, "--year", "2026", "--from", "2026-09-14T08:20:00", "--to", "2026-09-14T08:21:59")
    assert "Total: 7 coincidencia(s)" in out


def test_secuencia_ansi_se_escapa(capsys):
    _, out, _ = run(capsys, APP, "-k", "rojo")
    assert "\x1b" not in out
    assert "\\x1b[31mROJO" in out


def test_distingue_mayusculas_si_se_pide(capsys):
    _, out, _ = run(capsys, APP, "-k", "ADMIN", "--case-sensitive", "--count")
    assert "1 coincidencia(s)" in out


def test_sin_coincidencias_no_es_error(capsys):
    code, out, _ = run(capsys, LAB, "-k", "palabra-que-no-existe")
    assert code == 0 and "Sin coincidencias" in out


@pytest.mark.parametrize("args", [
    ["-k", "x", "--tz", "Marte/Olimpo"],
    ["--ip", "999.9.9.9"],
    ["--cidr", "10.0.0.0/40"],
    ["--from", "ayer"],
    [],
    ["-k", "x", "-C", "99"],
])
def test_errores_de_criterios_devuelven_1_sin_traceback(capsys, args):
    code, out, err = run(capsys, LAB, *args)
    assert code == 1 and err.startswith("Error: ") and "Traceback" not in err


def test_archivo_inexistente(capsys, tmp_path):
    code, _, err = run(capsys, tmp_path / "no_existe.log", "-k", "x")
    assert code == 1 and "No existe" in err


def test_carpeta_en_lugar_de_archivo(capsys, tmp_path):
    code, _, err = run(capsys, tmp_path, "-k", "x")
    assert code == 1 and "No existe o no es un archivo" in err


def test_varios_archivos(capsys):
    _, out, _ = run(capsys, LAB, SYSLOG, "--ip", "198.51.100.23", "--count")
    assert "Total: 13 coincidencia(s) en 2 archivo(s)." in out


def test_exportar_json_no_sobrescribe_sin_force(capsys, tmp_path):
    destino = tmp_path / "salida.json"
    assert run(capsys, LAB, "-k", "admin", "-C", "1", "--export-json", destino)[0] == 0
    datos = json.loads(destino.read_text(encoding="utf-8"))
    assert datos["archivos"][0]["coincidencias"] == 8
    assert any(not linea["coincide"] for linea in datos["archivos"][0]["lineas"])

    code, _, err = run(capsys, LAB, "-k", "admin", "--export-json", destino)
    assert code == 1 and "--force" in err
    assert run(capsys, LAB, "-k", "admin", "--export-json", destino, "--force")[0] == 0


def test_exportar_crea_la_carpeta_de_salida(capsys, tmp_path):
    destino = tmp_path / "nueva" / "o.json"
    assert run(capsys, LAB, "-k", "x", "--export-json", destino)[0] == 0
    assert destino.is_file()


def test_exportar_a_una_carpeta_es_error(capsys, tmp_path):
    code, _, err = run(capsys, LAB, "-k", "x", "--export-json", tmp_path)
    assert code == 1 and "es una carpeta" in err
