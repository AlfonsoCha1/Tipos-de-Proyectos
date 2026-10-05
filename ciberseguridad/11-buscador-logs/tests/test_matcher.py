"""Pruebas de la lógica de búsqueda (criterios, IPs, fechas, contexto)."""

from datetime import datetime, timezone

import pytest

from log_search.matcher import (
    MAX_LINE_CHARS,
    QueryError,
    build_query,
    extract_timestamp,
    find_ips,
    line_matches,
    parse_date_bound,
    read_lines,
    search_file,
)
from log_search.timeutils import load_timezone

UTC = timezone.utc
MX = load_timezone("-06:00")


def write(tmp_path, text, name="a.log"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# ------------------------------ criterios ---------------------------------

def test_sin_criterios_es_error():
    with pytest.raises(QueryError):
        build_query()


@pytest.mark.parametrize("kwargs", [
    {"keywords": ["   "]},
    {"keywords": ["x" * 201]},
    {"keywords": ["a"] * 21},
    {"ips": ["999.1.1.1"]},
    {"cidrs": ["192.0.2.0/99"]},
    {"cidrs": ["no-es-rango"]},
    {"start": "ayer"},
    {"start": "2026-02-30"},
    {"start": "2026-09-15", "end": "2026-09-14"},
])
def test_criterios_invalidos(kwargs):
    with pytest.raises(QueryError):
        build_query(**kwargs)


def test_cidr_no_estricto_se_normaliza():
    query = build_query(cidrs=["192.0.2.10/24"])
    assert str(query.networks[0]) == "192.0.2.0/24"


def test_ip_se_normaliza():
    assert build_query(ips=["2001:DB8:0:0:0:0:0:1"]).ips == frozenset({"2001:db8::1"})
    assert build_query(ips=["::ffff:192.0.2.1"]).ips == frozenset({"192.0.2.1"})


def test_fecha_solo_dia_cubre_todo_el_dia_en_la_zona_indicada():
    inicio = parse_date_bound("2026-09-14", MX, is_end=False)
    fin = parse_date_bound("2026-09-14", MX, is_end=True)
    assert inicio == datetime(2026, 9, 14, 6, 0, tzinfo=UTC)
    assert fin.date().isoformat() == "2026-09-15" and fin.hour == 5 and fin.minute == 59


# --------------------------- extracción de datos ---------------------------

def test_find_ips_ignora_horas_y_fechas():
    texto = "2026-09-14T08:10:02-06:00 fallo ip=203.0.113.50 y 2001:db8::1, fin."
    assert find_ips(texto) == ["203.0.113.50", "2001:db8::1"]


def test_find_ips_no_confunde_numeros_de_version():
    assert find_ips("versión=2.4.1 build 10.20") == []


def test_extract_timestamp_iso_y_syslog():
    assert extract_timestamp("2026-09-14T08:00:00-06:00 x", UTC, 2026) == datetime(2026, 9, 14, 14, tzinfo=UTC)
    assert extract_timestamp("Sep 14 08:00:01 host", UTC, 2026) == datetime(2026, 9, 14, 8, 0, 1, tzinfo=UTC)
    assert extract_timestamp("    Traceback (most recent call last):", UTC, 2026) is None
    assert extract_timestamp("Feb 30 08:00:01 host", UTC, 2026) is None
    assert extract_timestamp("Xyz 14 08:00:01 host", UTC, 2026) is None


# ------------------------------ una línea ----------------------------------

def test_palabra_sin_distinguir_mayusculas_por_defecto():
    q = build_query(["ADMIN"])
    assert line_matches("user=admin", q, UTC, 2026) == (True, False)
    q = build_query(["ADMIN"], case_sensitive=True)
    assert line_matches("user=admin", q, UTC, 2026) == (False, False)


def test_varias_palabras_o_y_todas():
    q_any = build_query(["admin", "luis"])
    q_all = build_query(["admin", "luis"], match_all=True)
    assert line_matches("user=luis", q_any, UTC, 2026)[0] is True
    assert line_matches("user=luis", q_all, UTC, 2026)[0] is False
    assert line_matches("admin luis", q_all, UTC, 2026)[0] is True


def test_ip_exacta_no_coincide_por_prefijo():
    q = build_query(ips=["192.0.2.1"])
    assert line_matches("ip=192.0.2.10", q, UTC, 2026)[0] is False
    assert line_matches("ip=192.0.2.1 ok", q, UTC, 2026)[0] is True


def test_cidr_mezcla_ipv4_e_ipv6_sin_error():
    q = build_query(cidrs=["192.0.2.0/24", "2001:db8::/32"])
    assert line_matches("a 192.0.2.77", q, UTC, 2026)[0] is True
    assert line_matches("a 2001:db8::5", q, UTC, 2026)[0] is True
    assert line_matches("a 198.51.100.1", q, UTC, 2026)[0] is False


def test_criterios_de_distinto_tipo_se_combinan_con_y():
    q = build_query(["fallo"], cidrs=["192.0.2.0/24"])
    assert line_matches("fallo desde 192.0.2.5", q, UTC, 2026)[0] is True
    assert line_matches("fallo desde 198.51.100.5", q, UTC, 2026)[0] is False
    assert line_matches("ok desde 192.0.2.5", q, UTC, 2026)[0] is False


def test_filtro_de_fechas_limites_inclusivos_y_sin_fecha():
    q = build_query(start="2026-09-14T08:00:00", end="2026-09-14T09:00:00", tz=UTC)
    assert line_matches("2026-09-14T08:00:00Z a", q, UTC, 2026) == (True, False)
    assert line_matches("2026-09-14T09:00:00Z a", q, UTC, 2026) == (True, False)
    assert line_matches("2026-09-14T09:00:01Z a", q, UTC, 2026) == (False, False)
    assert line_matches("2026-09-14T07:59:59Z a", q, UTC, 2026) == (False, False)
    assert line_matches("sin fecha", q, UTC, 2026) == (False, True)


def test_fecha_con_desplazamiento_se_compara_en_utc():
    q = build_query(start="2026-09-14T14:00:00Z", end="2026-09-14T14:30:00Z")
    assert line_matches("2026-09-14T08:10:00-06:00 x", q, UTC, 2026)[0] is True


# --------------------------- contexto y archivos ---------------------------

def test_contexto_antes_y_despues_y_separador(tmp_path):
    texto = "\n".join(f"linea {n}" for n in range(1, 21)) + "\n"
    path = write(tmp_path, texto)
    q = build_query(["linea 5", "linea 15"])
    res = search_file(path, q, context=1)
    # "linea 5" también coincide con "linea 15"? No: son distintas cadenas, pero "linea 5" no está en "linea 15".
    numeros = [e.line_no for e in res.entries]
    assert numeros == [4, 5, 6, 14, 15, 16]
    assert [e.is_match for e in res.entries] == [False, True, False, False, True, False]


def test_contextos_solapados_no_duplican_lineas(tmp_path):
    path = write(tmp_path, "a\nX\nb\nX\nc\n")
    res = search_file(path, build_query(["x"]), context=1)
    assert [e.line_no for e in res.entries] == [1, 2, 3, 4, 5]
    assert res.matches == 2


def test_contexto_al_inicio_y_al_final_del_archivo(tmp_path):
    path = write(tmp_path, "X\nb\nc\nX\n")
    res = search_file(path, build_query(["x"]), context=3)
    assert [e.line_no for e in res.entries] == [1, 2, 3, 4]


def test_max_matches_detiene_la_busqueda(tmp_path):
    path = write(tmp_path, "X\n" * 50)
    res = search_file(path, build_query(["x"]), max_matches=5)
    assert res.matches == 5 and res.stopped_early is True
    assert res.lines_read == 6  # leyó la sexta, vio que había más y se detuvo


def test_exactamente_max_matches_no_marca_detenido(tmp_path):
    path = write(tmp_path, "X\n" * 5)
    res = search_file(path, build_query(["x"]), max_matches=5)
    assert res.matches == 5 and res.stopped_early is False


@pytest.mark.parametrize("context,max_matches", [(-1, 10), (21, 10), (0, 0), (0, 10_001)])
def test_limites_invalidos(tmp_path, context, max_matches):
    path = write(tmp_path, "x\n")
    with pytest.raises(QueryError):
        search_file(path, build_query(["x"]), context=context, max_matches=max_matches)


def test_lineas_sin_fecha_se_cuentan_con_filtro_de_fechas(tmp_path):
    path = write(tmp_path, "2026-09-14T08:00:00Z a\n  continuación\n2026-09-14T08:01:00Z b\n")
    res = search_file(path, build_query(start="2026-09-14"), default_tz=UTC)
    assert res.matches == 2 and res.undated == 1


def test_syslog_usa_el_anio_indicado(tmp_path):
    path = write(tmp_path, "Sep 14 08:00:01 host a\nSep 15 08:00:01 host b\n")
    q = build_query(start="2026-09-15")
    assert search_file(path, q, year=2026).matches == 1
    assert search_file(path, q, year=2025).matches == 0


def test_linea_larga_se_recorta_y_sigue_numerando(tmp_path):
    larga = "A" * (MAX_LINE_CHARS * 3)
    path = write(tmp_path, f"corta\n{larga}\nfinal X\n")
    lineas = list(read_lines(path))
    assert [n for n, _, _ in lineas] == [1, 2, 3]
    assert len(lineas[1][1]) == MAX_LINE_CHARS and lineas[1][2] is True
    res = search_file(path, build_query(["x"]))
    assert res.matches == 1 and res.truncated_lines == 1 and res.entries[0].line_no == 3


def test_bom_crlf_y_bytes_invalidos(tmp_path):
    path = tmp_path / "b.log"
    path.write_bytes(b"\xef\xbb\xbfprimera X\r\nsegunda \xff\xfe X\r\n")
    res = search_file(path, build_query(["x"]))
    assert res.matches == 2
    assert res.entries[0].text == "primera X"
    assert "�" in res.entries[1].text


def test_archivo_vacio(tmp_path):
    res = search_file(write(tmp_path, ""), build_query(["x"]))
    assert res.lines_read == 0 and res.matches == 0 and res.entries == []
