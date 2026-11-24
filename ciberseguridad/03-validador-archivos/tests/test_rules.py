"""Pruebas de las reglas de validación (rules.py y config.py)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from file_validator.config import ConfigError, load_rules
from file_validator.rules import Rules, safe_storage_name, validate_file, validate_name, validate_paths

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
RULES = Rules()


def codes_for(name: str, rules: Rules = RULES) -> list[str]:
    return [p.code for p in validate_name(name, rules)]


@pytest.mark.parametrize("name", ["informe.pdf", "foto_2026.JPG", "datos-clientes.csv", "carta.docx"])
def test_valid_names(name):
    assert codes_for(name) == []


@pytest.mark.parametrize(
    "name, code",
    [
        ("", "NOMBRE_VACIO"),
        ("   ", "NOMBRE_VACIO"),
        ("../../etc/passwd.txt", "NOMBRE_CON_RUTA"),
        ("..\\windows\\win.ini.txt", "NOMBRE_CON_RUTA"),
        ("reporte<1>.pdf", "NOMBRE_CARACTERES_PROHIBIDOS"),
        ("CON.txt", "NOMBRE_RESERVADO"),
        ("com1.pdf", "NOMBRE_RESERVADO"),
        ("nul", "NOMBRE_RESERVADO"),
        ("informe.pdf.", "NOMBRE_TERMINA_EN_PUNTO_O_ESPACIO"),
        ("informe.pdf ", "NOMBRE_TERMINA_EN_PUNTO_O_ESPACIO"),
        ("a" * 101 + ".pdf", "NOMBRE_LARGO"),
        (".env", "NOMBRE_OCULTO"),
        ("factura.pdf.exe", "DOBLE_EXTENSION"),
        ("foto.jpg.js", "DOBLE_EXTENSION"),
        ("LEEME", "SIN_EXTENSION"),
        ("script.ps1", "EXTENSION_NO_PERMITIDA"),
        ("pago‮fdp.exe", "NOMBRE_CARACTERES_CONTROL"),
        ("linea\nnueva.txt", "NOMBRE_CARACTERES_CONTROL"),
    ],
)
def test_invalid_names(name, code):
    assert code in codes_for(name)


def test_reserved_name_only_matches_whole_stem():
    assert "NOMBRE_RESERVADO" not in codes_for("console.txt")
    assert "NOMBRE_RESERVADO" not in codes_for("auxiliar.pdf")


def test_double_extension_needs_executable_at_the_end():
    assert "DOBLE_EXTENSION" not in codes_for("respaldo.tar.gz")


def test_allow_hidden_option():
    assert "NOMBRE_OCULTO" not in codes_for(".notas.txt", Rules(allow_hidden=True))


def write(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


def file_codes(path: Path, rules: Rules = RULES) -> list[str]:
    return [p.code for p in validate_file(path, rules).problems]


def test_real_png_is_accepted(tmp_path):
    assert file_codes(write(tmp_path, "a.png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 20)) == []


def test_pdf_that_is_text_is_rejected(tmp_path):
    assert file_codes(write(tmp_path, "a.pdf", b"no soy un pdf")) == ["CONTENIDO_NO_COINCIDE"]


def test_executable_renamed_as_document(tmp_path):
    assert file_codes(write(tmp_path, "a.pdf", b"MZ\x90\x00")) == ["CONTENIDO_EJECUTABLE"]


def test_binary_renamed_as_text(tmp_path):
    assert file_codes(write(tmp_path, "a.txt", b"hola\x00\x01")) == ["CONTENIDO_NO_COINCIDE"]


def test_content_check_can_be_disabled(tmp_path):
    assert file_codes(write(tmp_path, "a.pdf", b"texto"), Rules(check_content=False)) == []


def test_empty_and_too_big(tmp_path):
    assert file_codes(write(tmp_path, "a.txt", b"")) == ["ARCHIVO_VACIO"]
    assert file_codes(write(tmp_path, "b.txt", b"x" * 11), Rules(max_size_bytes=10)) == ["DEMASIADO_GRANDE"]


def test_samples_expected_result():
    results, skipped = validate_paths([SAMPLES / "subidas"], RULES)
    accepted = sorted(r.name for r in results if r.accepted)
    assert accepted == ["clientes.csv", "contrato_firmado.pdf", "foto_perfil.png", "manual_usuario.txt", "notas.txt"]
    assert len(results) == 10 and skipped == []


def test_strict_rules_sample():
    rules = load_rules(SAMPLES / "reglas_estrictas.json")
    results, _ = validate_paths([SAMPLES / "subidas"], rules)
    accepted = sorted(r.name for r in results if r.accepted)
    assert accepted == ["contrato_firmado.pdf", "foto_perfil.png"]
    manual = next(r for r in results if r.name == "manual_usuario.txt")
    assert {"EXTENSION_NO_PERMITIDA", "DEMASIADO_GRANDE"} <= {p.code for p in manual.problems}


@pytest.mark.parametrize(
    "data, message",
    [
        ('{"allowed_extensions": ["pdf"]}', "empiecen con punto"),
        ('{"max_size_bytes": 0}', "entero positivo"),
        ('{"check_content": "si"}', "true o false"),
        ("[1, 2]", "objeto JSON"),
        ("{roto", "no es JSON válido"),
    ],
)
def test_invalid_config(tmp_path, data, message):
    path = tmp_path / "c.json"
    path.write_text(data, encoding="utf-8")
    with pytest.raises(ConfigError, match=message):
        load_rules(path)


def test_default_config_matches_dataclass_defaults():
    data = json.loads((SAMPLES.parent / "config" / "settings.json").read_text(encoding="utf-8"))
    assert frozenset(data["allowed_extensions"]) == Rules().allowed_extensions


@pytest.mark.parametrize(
    "name, safe",
    [
        ("reporte final .pdf.", "reporte_final.pdf"),
        ("CON.txt", "_CON.txt"),
        ("../../config.txt", "config.txt"),
        ("Fáctura Nº 5.PDF", "Factura_No_5.pdf"),
        ("...", "archivo"),
    ],
)
def test_safe_storage_name(name, safe):
    assert safe_storage_name(name) == safe
    assert codes_for(safe_storage_name(name), Rules(allowed_extensions=frozenset({".pdf", ".txt"}))) in ([], ["SIN_EXTENSION"])
