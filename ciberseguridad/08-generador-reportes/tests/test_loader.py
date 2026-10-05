"""Pruebas de lectura y validación de eventos."""

import json
from datetime import timezone

import pytest

from report_generator.loader import InputFormatError, detect_format, load_files, validate_row
from report_generator.models import Event, RejectedRow
from report_generator.timeutils import load_timezone

UTC = timezone.utc
BASE = {"timestamp": "2026-09-14T08:00:00Z", "severity": "alta", "title": "Prueba"}


def ok(**cambios):
    return validate_row({**BASE, **cambios}, "t:1", UTC)


def test_evento_minimo_valido():
    ev = ok()
    assert isinstance(ev, Event)
    assert ev.severity == "alta" and ev.ip == "" and ev.source == ""


def test_severidad_en_ingles_y_mayusculas_se_normaliza():
    assert ok(severity="HIGH").severity == "alta"
    assert ok(severity=" Critical ").severity == "critica"


@pytest.mark.parametrize("cambios,texto", [
    ({"severity": "urgente"}, "severidad desconocida"),
    ({"severity": 3}, "severity debe ser texto"),
    ({"timestamp": "ayer"}, "formato no reconocido"),
    ({"timestamp": "2026-02-30T00:00:00Z"}, "inexistente"),
    ({"timestamp": 12345}, "timestamp debe ser texto"),
    ({"title": ""}, "faltan campos obligatorios"),
    ({"title": "   "}, "título está vacío"),
    ({"title": "x" * 201}, "supera 200"),
    ({"title": ["lista"]}, "debe ser texto"),
    ({"ip": "192.0.2.999"}, "IP no válida"),
    ({"description": "d" * 2001}, "supera 2000"),
])
def test_filas_invalidas_explican_el_motivo(cambios, texto):
    resultado = ok(**cambios)
    assert isinstance(resultado, RejectedRow) and texto in resultado.reason


def test_campo_obligatorio_ausente():
    fila = dict(BASE)
    del fila["severity"]
    assert "severity" in validate_row(fila, "t:1", UTC).reason


def test_fila_que_no_es_objeto():
    assert "no es un objeto" in validate_row("texto", "t:1", UTC).reason
    assert "no es un objeto" in validate_row([1, 2], "t:1", UTC).reason


def test_ip_mapeada_se_normaliza_a_ipv4_e_ipv6_se_comprime():
    assert ok(ip="::ffff:192.0.2.1").ip == "192.0.2.1"
    assert ok(ip="2001:0DB8:0:0:0:0:0:1").ip == "2001:db8::1"


def test_fecha_sin_zona_usa_tz_de_entrada():
    ev = validate_row({**BASE, "timestamp": "2026-09-14T08:00:00"}, "t:1", load_timezone("-06:00"))
    assert ev.timestamp.hour == 14


def test_formato_por_extension(tmp_path):
    assert detect_format(tmp_path / "a.JSON") == "json"
    assert detect_format(tmp_path / "a.ndjson") == "jsonl"
    assert detect_format(tmp_path / "a.csv") == "csv"
    with pytest.raises(InputFormatError):
        detect_format(tmp_path / "a.txt")


def test_json_lista_y_objeto_con_events(tmp_path):
    lista = tmp_path / "l.json"
    lista.write_text(json.dumps([BASE, BASE]), encoding="utf-8")
    objeto = tmp_path / "o.json"
    objeto.write_text(json.dumps({"events": [BASE]}), encoding="utf-8")
    assert len(load_files([lista], "auto", UTC).events) == 2
    assert len(load_files([objeto], "auto", UTC).events) == 1


def test_json_con_estructura_incorrecta(tmp_path):
    ruta = tmp_path / "x.json"
    ruta.write_text('{"otra": 1}', encoding="utf-8")
    with pytest.raises(InputFormatError, match="lista de eventos"):
        load_files([ruta], "auto", UTC)
    ruta.write_text("{no es json", encoding="utf-8")
    with pytest.raises(InputFormatError, match="no es JSON válido"):
        load_files([ruta], "auto", UTC)


def test_jsonl_reporta_linea_mala_y_salta_vacias(tmp_path):
    ruta = tmp_path / "e.jsonl"
    ruta.write_text(json.dumps(BASE) + "\n\n{roto\n" + json.dumps(BASE) + "\n", encoding="utf-8")
    cargado = load_files([ruta], "auto", UTC)
    assert len(cargado.events) == 2 and len(cargado.rejected) == 1
    assert cargado.rejected[0].origin == "e.jsonl:3"


def test_csv_con_bom_crlf_y_comillas(tmp_path):
    ruta = tmp_path / "e.csv"
    ruta.write_bytes(
        "timestamp,severity,title\r\n2026-09-14T08:00:00Z,alta,\"Con, coma\"\r\n".encode("utf-8-sig")
    )
    cargado = load_files([ruta], "auto", UTC)
    assert cargado.events[0].title == "Con, coma"


def test_csv_sin_columnas_obligatorias(tmp_path):
    ruta = tmp_path / "e.csv"
    ruta.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(InputFormatError, match="faltan las columnas"):
        load_files([ruta], "auto", UTC)


def test_csv_fila_corta_se_rechaza_y_columnas_extra_se_ignoran(tmp_path):
    ruta = tmp_path / "e.csv"
    ruta.write_text("timestamp,severity,title\n2026-09-14T08:00:00Z,alta\n2026-09-14T08:00:00Z,alta,ok,sobra\n", encoding="utf-8")
    cargado = load_files([ruta], "auto", UTC)
    assert len(cargado.events) == 1
    assert cargado.rejected[0].origin == "e.csv:2" and "menos columnas" in cargado.rejected[0].reason


def test_archivo_inexistente_no_utf8_y_demasiado_grande(tmp_path, monkeypatch):
    with pytest.raises(InputFormatError, match="No existe"):
        load_files([tmp_path / "nada.json"], "auto", UTC)
    malo = tmp_path / "m.json"
    malo.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(InputFormatError, match="UTF-8"):
        load_files([malo], "auto", UTC)
    import report_generator.loader as loader
    monkeypatch.setattr(loader, "MAX_FILE_BYTES", 5)
    grande = tmp_path / "g.json"
    grande.write_text("[]" * 10, encoding="utf-8")
    with pytest.raises(InputFormatError, match="MB"):
        load_files([grande], "auto", UTC)


def test_limite_de_filas(tmp_path, monkeypatch):
    import report_generator.loader as loader
    monkeypatch.setattr(loader, "MAX_EVENTS", 2)
    ruta = tmp_path / "e.json"
    ruta.write_text(json.dumps([BASE] * 3), encoding="utf-8")
    with pytest.raises(InputFormatError, match="Más de 2 filas"):
        load_files([ruta], "auto", UTC)
