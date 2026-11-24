"""Pruebas del glosario: validación, búsqueda, sugerencias e interfaz."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from security_glossary.cli import main
from security_glossary.glossary import (
    GlossaryError,
    by_category,
    load_glossary,
    normalize,
    search,
    suggest,
    validate,
)

PROJECT = Path(__file__).resolve().parent.parent
TERMS = load_glossary()


def entry(**changes):
    item = {"termino": "Hash", "categoria": "Cripto", "definicion": "x", "sinonimos": [], "relacionados": []}
    item.update(changes)
    return item


def names(results):
    return [t.name for t in results]


def test_default_glossary_is_valid():
    assert len(TERMS) == 43
    assert len(by_category(TERMS)) == 9


@pytest.mark.parametrize(
    "query, first",
    [("mfa", "MFA"), ("2FA", "MFA"), ("doble factor", "MFA"), ("CONTENCION", "Contención"),
     ("contención", "Contención"), ("indicador de compromiso", "IOC"), ("cortafuegos", "Firewall"),
     ("  phishing  ", "Phishing")],
)
def test_exact_and_synonym_matches_come_first(query, first):
    assert names(search(TERMS, query))[0] == first


def test_partial_match_in_name():
    assert names(search(TERMS, "spray")) == ["Password spraying"]


def test_match_in_definition_comes_after_names():
    results = names(search(TERMS, "phishing"))
    assert results[0] == "Phishing"
    assert "Spear phishing" in results  # parcial en el nombre
    assert results.index("Threat intelligence") > results.index("Spear phishing")  # solo en su ejemplo


def test_empty_query():
    assert search(TERMS, "   ") == []


@pytest.mark.parametrize("typo, expected", [("fishing", "Phishing"), ("ransonware", "Ransomware"), ("firwall", "Firewall")])
def test_suggestions(typo, expected):
    assert search(TERMS, typo) == []
    assert expected in suggest(TERMS, typo)


def test_normalize():
    assert normalize("  Ingeniería   Social ") == "ingenieria social"


def test_validation_errors():
    _, errors = validate({"terminos": [entry(), entry(termino="HASH")]})
    assert "repetido" in errors[0]
    _, errors = validate({"terminos": [entry(relacionados=["No existe"])]})
    assert "no existen" in errors[0]
    _, errors = validate({"terminos": [entry(definicion="")]})
    assert "falta 'definicion'" in errors[0]
    _, errors = validate({"terminos": [entry(sinonimos="texto")]})
    assert "lista de textos" in errors[0]
    _, errors = validate([])
    assert "lista 'terminos'" in errors[0]


def test_load_errors(tmp_path):
    with pytest.raises(GlossaryError, match="No existe"):
        load_glossary(tmp_path / "no.json")
    bad = tmp_path / "g.json"
    bad.write_text("[", encoding="utf-8")
    with pytest.raises(GlossaryError, match="no es JSON válido"):
        load_glossary(bad)


def test_cli_found_and_not_found(capsys):
    assert main(["ingeniería", "social"]) == 0
    assert "Ingeniería social  [Ataques]" in capsys.readouterr().out
    assert main(["fishing"]) == 3
    assert "¿Quisiste decir: Phishing?" in capsys.readouterr().out


def test_cli_max(capsys):
    assert main(["seguridad", "--max", "1"]) == 0
    assert "más:" in capsys.readouterr().out


def test_cli_list_random_validate(capsys):
    assert main(["--list", "--category", "correo"]) == 0
    out = capsys.readouterr().out
    assert "DKIM, DMARC, SPF" in out
    assert main(["--list", "--category", "astronomía"]) == 1
    assert main(["--random", "--seed", "1"]) == 0
    assert "Término al azar" in capsys.readouterr().out
    assert main(["--validate"]) == 0


def test_interactive_mode(capsys):
    replies = iter(["dmarc", "xyzxyz", "salir"])
    assert main(["-i"], ask=lambda prompt: next(replies)) == 0
    out = capsys.readouterr().out
    assert "DMARC  [Correo]" in out and "No encontré 'xyzxyz'" in out


def test_interactive_end_of_input(capsys):
    def eof(prompt):
        raise EOFError

    assert main([], ask=eof) == 0


def test_run_as_module():
    completed = subprocess.run(
        [sys.executable, "-m", "security_glossary", "siem"],
        cwd=PROJECT, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert completed.returncode == 0
    assert "SIEM  [Operaciones de seguridad]" in completed.stdout
