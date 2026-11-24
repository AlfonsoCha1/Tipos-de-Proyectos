"""Pruebas del lector de correos y de los indicadores."""

from __future__ import annotations

from pathlib import Path

import pytest

from email_analyzer.config import load_settings
from email_analyzer.indicators import (
    analyze,
    contains_phrase,
    levenshtein,
    lookalike_of,
    registrable_domain,
)
from email_analyzer.parser import EmailFormatError, defang, host_of, load_message, parse_eml, parse_text

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
SETTINGS = load_settings()
PROTECTED = SETTINGS.protected_domains


def codes(analysis):
    return {i.code for i in analysis.indicators}


def eml(headers: str, body: str = "hola", content_type: str = "text/plain") -> bytes:
    return (f"{headers}\nMIME-Version: 1.0\nContent-Type: {content_type}; charset=utf-8\n\n{body}\n").encode()


# --- utilidades -----------------------------------------------------------

@pytest.mark.parametrize(
    "host, expected",
    [("login.bancofenix.example", "bancofenix.example"), ("www.banco.com.mx", "banco.com.mx"),
     ("sat.gob.mx", "sat.gob.mx"), ("a.b.c.example", "c.example")],
)
def test_registrable_domain(host, expected):
    assert registrable_domain(host) == expected


def test_levenshtein():
    assert levenshtein("bancofenix", "bancofenlx") == 1
    assert levenshtein("abc", "abc") == 0


@pytest.mark.parametrize(
    "host",
    ["bancofenlx.example", "bancofen1x.example", "banco-fenix.example", "bancofenix-seguridad.example",
     "bancofenix.example.otro-sitio.example", "paqueteriarapida-mx.example"],
)
def test_lookalikes_detected(host):
    assert lookalike_of(host, PROTECTED) is not None


@pytest.mark.parametrize("host", ["bancofenix.example", "www.bancofenix.example", "correo.example", "tiendademo.example"])
def test_legit_or_unrelated_hosts_are_not_lookalikes(host):
    assert lookalike_of(host, PROTECTED) is None


def test_contains_phrase_ignores_accents_and_needs_whole_words():
    assert contains_phrase("Su cuenta SERA BLOQUEADA hoy", "será bloqueada")
    assert not contains_phrase("opinión", "pin")
    assert contains_phrase("Escribe tu NIP", "nip")


def test_defang_and_host():
    assert defang("https://www.ejemplo.example/x") == "hxxps://www[.]ejemplo[.]example/x"
    assert host_of("www.ejemplo.example/ruta") == "www.ejemplo.example"
    assert host_of("http://[2001:db8::1]/x") == "2001:db8::1"


# --- lector ---------------------------------------------------------------

def test_parse_encoded_headers_and_html_links():
    parsed = load_message(SAMPLES / "02_phishing_banco.eml")
    assert parsed.from_name == "Banco Fénix Seguridad"
    assert parsed.from_address == "seguridad@bancofenlx.example"
    assert parsed.reply_to == ["soporte.bancofenix@correo-gratis.example"]
    assert parsed.auth_results == {"spf": "fail", "dkim": "none", "dmarc": "fail"}
    assert parsed.links[0].url == "http://198.51.100.77/bancofenix/login.php"
    assert parsed.links[0].text == "https://www.bancofenix.example/seguridad"


def test_attachments_are_hashed_not_saved(tmp_path):
    parsed = load_message(SAMPLES / "03_factura_con_adjunto.eml")
    names = [a.filename for a in parsed.attachments]
    assert names == ["Factura_0925.pdf.exe", "pago_en_linea.html"]
    assert all(len(a.sha256) == 64 for a in parsed.attachments)
    assert not any(SAMPLES.glob("Factura_0925*"))


def test_script_content_is_not_text():
    html = "<html><script>var a='https://oculto.example';</script><p>visible</p></html>"
    parsed = parse_eml(eml("From: a@b.example\nSubject: x", html, "text/html"), Path("x.eml"))
    assert parsed.links == []
    assert "oculto" not in parsed.text


def test_file_without_headers_is_error():
    with pytest.raises(EmailFormatError, match="no tiene encabezados"):
        load_message(SAMPLES / "06_no_es_correo.eml")


def test_text_mode():
    parsed = parse_text(b"Visita www.ejemplo.example/x, ya.", Path("m.txt"))
    assert [l.url for l in parsed.links] == ["www.ejemplo.example/x"]


# --- indicadores ----------------------------------------------------------

@pytest.mark.parametrize(
    "name, level, score",
    [
        ("01_legitimo_estado_cuenta.eml", "BAJO", 15),
        ("02_phishing_banco.eml", "ALTO", 100),
        ("03_factura_con_adjunto.eml", "ALTO", 60),
        ("04_boletin_acortador.eml", "BAJO", 5),
        ("05_sms_paqueteria.txt", "MEDIO", 55),
    ],
)
def test_samples_scores(name, level, score):
    analysis = analyze(load_message(SAMPLES / name), SETTINGS)
    assert (analysis.level, analysis.score) == (level, score)


def test_phishing_sample_indicators():
    analysis = analyze(load_message(SAMPLES / "02_phishing_banco.eml"), SETTINGS)
    assert codes(analysis) == {
        "AUTENTICACION_FALLA", "RESPONDER_A_DISTINTO", "RETURN_PATH_DISTINTO", "REMITENTE_PARECIDO",
        "NOMBRE_SUPLANTA_MARCA", "ENLACE_ENGANOSO", "ENLACE_A_IP", "URGENCIA", "PIDE_DATOS_SENSIBLES",
    }


def test_display_name_with_other_address():
    data = eml('From: "avisos@bancofenix.example" <x@otro.example>\nSubject: hola')
    analysis = analyze(parse_eml(data, Path("x.eml")), SETTINGS)
    assert "NOMBRE_CON_OTRO_CORREO" in codes(analysis)


def test_reply_to_subdomain_of_same_org_is_fine():
    data = eml("From: a@tiendademo.example\nReply-To: soporte@ayuda.tiendademo.example\nSubject: x")
    assert "RESPONDER_A_DISTINTO" not in codes(analyze(parse_eml(data, Path("x.eml")), SETTINGS))


def test_link_text_matching_destination_is_fine():
    html = '<a href="https://www.tiendademo.example/a">www.tiendademo.example</a>'
    data = eml("From: a@tiendademo.example\nSubject: x", html, "text/html")
    assert codes(analyze(parse_eml(data, Path("x.eml")), SETTINGS)) == set()


def test_risky_attachment_without_double_extension(tmp_path):
    data = (
        "From: a@b.example\nSubject: x\nMIME-Version: 1.0\nContent-Type: multipart/mixed; boundary=z\n\n"
        "--z\nContent-Type: text/plain\n\nhola\n--z\nContent-Type: application/x-msdownload\n"
        'Content-Disposition: attachment; filename="instalar.js"\n\nconsole.log(1)\n--z--\n'
    ).encode()
    assert "ADJUNTO_EJECUTABLE" in codes(analyze(parse_eml(data, Path("x.eml")), SETTINGS))


def test_score_is_capped_at_100():
    assert analyze(load_message(SAMPLES / "02_phishing_banco.eml"), SETTINGS).score == 100
