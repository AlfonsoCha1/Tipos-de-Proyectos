"""Pruebas del resumen y del escape en Markdown y HTML."""

import re
from datetime import datetime, timezone
from html.parser import HTMLParser

from report_generator.analysis import sort_events, summarize
from report_generator.models import Event, RejectedRow
from report_generator.render import html_escape, md_escape, render_html, render_markdown, single_line

UTC = timezone.utc
AHORA = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


def ev(n, severity="media", title="t", ip="", user="", source="s", description="", hora=0):
    return Event(datetime(2026, 9, 14, hora, n, tzinfo=UTC), severity, title, source, description, ip, user, f"x:{n}")


def opciones(**extra):
    base = dict(title="Reporte", files=["x.json"], rows_read=3, display_tz=UTC, generated_at=AHORA)
    base.update(extra)
    return base


def test_resumen_cuenta_por_severidad_incluyendo_ceros():
    eventos = [ev(1, "alta"), ev(2, "alta"), ev(3, "info")]
    resumen = summarize(eventos, UTC)
    assert resumen.by_severity == {"critica": 0, "alta": 2, "media": 0, "baja": 0, "info": 1}
    assert resumen.total == 3


def test_resumen_vacio_es_error():
    import pytest
    with pytest.raises(ValueError):
        summarize([], UTC)


def test_top_ordena_por_frecuencia_y_desempata_por_texto():
    eventos = [ev(1, ip="192.0.2.2"), ev(2, ip="192.0.2.1"), ev(3, ip="192.0.2.3"), ev(4, ip="192.0.2.3")]
    assert summarize(eventos, UTC, top=2).top_ips == [("192.0.2.3", 2), ("192.0.2.1", 1)]


def test_dias_se_agrupan_en_la_zona_de_visualizacion():
    from report_generator.timeutils import load_timezone
    eventos = [Event(datetime(2026, 9, 15, 3, 0, tzinfo=UTC), "baja", "t", "", "", "", "", "o")]
    assert summarize(eventos, load_timezone("-06:00")).per_day[0][0].isoformat() == "2026-09-14"


def test_orden_por_gravedad_y_luego_fecha():
    eventos = [ev(5, "baja"), ev(9, "critica"), ev(1, "critica")]
    assert [e.origin for e in sort_events(eventos)] == ["x:1", "x:9", "x:5"]


def test_frases_del_resumen():
    eventos = [ev(n, "alta", ip="192.0.2.9", user="ana") for n in range(3)]
    texto = " ".join(summarize(eventos, UTC).highlights)
    assert "3 evento(s) de severidad crítica o alta" in texto
    assert "192.0.2.9 aparece en 3" in texto and "cuenta ana aparece en 3" in texto
    assert "No hay eventos de severidad crítica ni alta" in summarize([ev(1, "baja")], UTC).highlights[0]


def test_reporte_es_determinista():
    eventos = [ev(1, "alta", ip="192.0.2.1"), ev(2, "baja")]
    assert render_markdown(eventos, [], **opciones()) == render_markdown(list(reversed(eventos)), [], **opciones())
    assert render_html(eventos, [], **opciones()) == render_html(list(reversed(eventos)), [], **opciones())


def test_md_escape_neutraliza_markdown_y_html():
    texto = md_escape("<b>x</b> [a](http://e) | `c` *n* _u_ ![i](u) & fin")
    assert "<" not in texto and ">" not in texto
    assert "\\[a\\]" in texto and "\\|" in texto and "\\`c\\`" in texto and "&amp;" in texto
    assert "\n" not in md_escape("uno\ndos\r\ntres")


def test_ansi_y_control_se_escapan():
    assert single_line("a\x1b[31mb\x00c") == "a\\x1b[31mb\\x00c"
    assert "\x1b" not in html_escape("\x1b[0m") and "\x1b" not in md_escape("\x1b[0m")


def test_html_escapa_comillas_y_etiquetas():
    assert html_escape('"><script>') == "&quot;&gt;&lt;script&gt;"


class _Etiquetas(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags: list[str] = []
        self.atributos: list[tuple[str, str | None]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.atributos += attrs


def test_html_hostil_no_crea_etiquetas_ni_atributos_peligrosos():
    hostil = '<script>alert(1)</script><img src=x onerror=alert(1)>"\'><svg onload=alert(1)>'
    eventos = [ev(1, "critica", title=hostil, user=hostil, source=hostil, description=hostil, ip="192.0.2.1")]
    rechazadas = [RejectedRow(hostil, hostil)]
    html = render_html(eventos, rechazadas, **opciones(title=hostil, files=[hostil]))
    parser = _Etiquetas()
    parser.feed(html)
    assert not {"script", "img", "svg", "iframe", "a", "link", "object"} & set(parser.tags)
    nombres = {nombre for nombre, _ in parser.atributos}
    assert not any(nombre.startswith("on") for nombre in nombres)
    assert "src" not in nombres and "href" not in nombres


def test_html_es_autocontenido_y_sin_javascript():
    html = render_html([ev(1)], [], **opciones())
    assert "Content-Security-Policy" in html and "default-src 'none'" in html
    assert "<script" not in html and "http://" not in html and "https://" not in html
    assert '<html lang="es">' in html and "<title>Reporte</title>" in html


def test_la_severidad_siempre_aparece_como_texto():
    html = render_html([ev(1, "critica")], [], **opciones())
    assert ">Crítica</span>" in html


def test_markdown_tabla_no_se_rompe_con_pipes():
    md = render_markdown([ev(1, title="a | b\nc")], [], **opciones())
    fila = next(linea for linea in md.splitlines() if "a \\| b c" in linea)
    # Una fila de la tabla de eventos tiene 7 columnas: 8 barras sin escapar.
    assert len(re.findall(r"(?<!\\)\|", fila)) == 8


def test_filas_rechazadas_se_listan_y_se_limitan():
    rechazadas = [RejectedRow(f"f:{n}", "motivo") for n in range(5)]
    md = render_markdown([ev(1)], rechazadas, **opciones(max_rejected_shown=2))
    assert "## Filas rechazadas" in md and "Se muestran 2 de 5" in md
    assert "## Filas rechazadas" not in render_markdown([ev(1)], [], **opciones())


def test_detalle_solo_para_criticos_y_altos_con_descripcion():
    md = render_markdown([ev(1, "alta", description="detalle uno"), ev(2, "baja", description="no aparece")], [], **opciones())
    assert "detalle uno" in md and "no aparece" not in md


def test_sin_ips_ni_cuentas():
    md = render_markdown([ev(1)], [], **opciones())
    assert "Ningún evento trae IP." in md and "Ningún evento trae cuenta." in md
    html = render_html([ev(1)], [], **opciones())
    assert "Ningún evento trae IP." in html and "Ningún evento trae cuenta." in html
