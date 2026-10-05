"""Pruebas de la interfaz: comandos del README sobre los datos de ejemplo."""

from pathlib import Path

import pytest

from report_generator.cli import main

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
JSON = str(SAMPLES / "eventos.json")
CSV = str(SAMPLES / "eventos.csv")
JSONL = str(SAMPLES / "eventos_hostiles.jsonl")
FIJA = "2026-10-01T12:00:00Z"


def run(capsys, *args):
    code = main([str(a) for a in args])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_genera_md_y_html(capsys, tmp_path):
    code, out, err = run(capsys, JSON, "--output-dir", tmp_path / "s", "--generated-at", FIJA)
    assert code == 0
    assert (tmp_path / "s" / "reporte.md").is_file() and (tmp_path / "s" / "reporte.html").is_file()
    assert "Eventos válidos: 9 de 14 fila(s)." in out
    assert "5 fila(s) rechazada(s)" in err


def test_un_solo_formato_y_nombre(capsys, tmp_path):
    code, out, _ = run(capsys, CSV, "--output-format", "md", "--name", "vpn", "--output-dir", tmp_path)
    assert code == 0 and [p.name for p in tmp_path.iterdir()] == ["vpn.md"]


def test_stdout_no_escribe_archivos(capsys, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    code, out, err = run(capsys, CSV, "--stdout", "--generated-at", FIJA)
    assert code == 0 and out.startswith("# Reporte de eventos de seguridad")
    assert not (tmp_path / "output").exists()
    assert "Eventos válidos: 5 de 6 fila(s)." in err


def test_no_sobrescribe_sin_force(capsys, tmp_path):
    assert run(capsys, CSV, "--output-dir", tmp_path)[0] == 0
    contenido = (tmp_path / "reporte.md").read_text(encoding="utf-8")
    (tmp_path / "reporte.md").write_text("MIO", encoding="utf-8")
    code, _, err = run(capsys, CSV, "--output-dir", tmp_path)
    assert code == 1 and "--force" in err
    assert (tmp_path / "reporte.md").read_text(encoding="utf-8") == "MIO"
    assert run(capsys, CSV, "--output-dir", tmp_path, "--force")[0] == 0
    assert (tmp_path / "reporte.md").read_text(encoding="utf-8") != "MIO" and contenido


def test_mismo_resultado_con_fecha_fija(capsys, tmp_path):
    run(capsys, JSON, CSV, "--output-dir", tmp_path / "a", "--generated-at", FIJA)
    run(capsys, JSON, CSV, "--output-dir", tmp_path / "b", "--generated-at", FIJA)
    for nombre in ("reporte.md", "reporte.html"):
        assert (tmp_path / "a" / nombre).read_bytes() == (tmp_path / "b" / nombre).read_bytes()


def test_zona_de_visualizacion(capsys):
    _, out, _ = run(capsys, CSV, "--stdout", "--generated-at", FIJA, "--display-tz=-06:00")
    assert "2026-09-16 08:00:00-06:00" in out
    _, out, _ = run(capsys, CSV, "--stdout", "--generated-at", FIJA)
    assert "2026-09-16 14:00:00+00:00" in out


def test_el_titulo_hostil_no_rompe_el_html(capsys, tmp_path):
    run(capsys, JSONL, "--output-dir", tmp_path, "--title", "<b>Hola</b>", "--force")
    html = (tmp_path / "reporte.html").read_text(encoding="utf-8")
    assert "<b>Hola</b>" not in html and "&lt;b&gt;Hola&lt;/b&gt;" in html
    assert "<script>alert" not in html and "<img src=x" not in html


@pytest.mark.parametrize("args,texto", [
    (["--top", "0"], "--top"),
    (["--top", "51"], "--top"),
    (["--name", "../escape"], "--name"),
    (["--name", "a/b"], "--name"),
    (["--tz", "Marte/Olimpo"], "Zona horaria desconocida"),
    (["--generated-at", "hoy"], "--generated-at"),
])
def test_opciones_invalidas(capsys, tmp_path, args, texto):
    code, _, err = run(capsys, CSV, "--output-dir", tmp_path, *args)
    assert code == 1 and texto in err and "Traceback" not in err
    assert list(tmp_path.iterdir()) == []


def test_salida_es_un_archivo(capsys, tmp_path):
    archivo = tmp_path / "archivo"
    archivo.write_text("x", encoding="utf-8")
    code, _, err = run(capsys, CSV, "--output-dir", archivo)
    assert code == 1 and "no es una carpeta" in err


def test_sin_eventos_validos(capsys, tmp_path):
    vacio = tmp_path / "v.json"
    vacio.write_text('[{"x": 1}]', encoding="utf-8")
    code, _, err = run(capsys, vacio, "--output-dir", tmp_path / "o")
    assert code == 1 and "No hay eventos válidos" in err and "faltan campos" in err


def test_archivo_inexistente_y_formato_desconocido(capsys, tmp_path):
    assert run(capsys, tmp_path / "no.json", "--output-dir", tmp_path)[0] == 1
    raro = tmp_path / "datos.txt"
    raro.write_text("x", encoding="utf-8")
    code, _, err = run(capsys, raro, "--output-dir", tmp_path / "o")
    assert code == 1 and "No se reconoce el formato" in err
    assert main([str(raro), "--input-format", "jsonl", "--stdout"]) == 1  # "x" no es JSON válido -> sin eventos
