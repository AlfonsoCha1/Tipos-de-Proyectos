"""Pruebas del banco de preguntas y del quiz."""

from __future__ import annotations

import json
import random
import subprocess
import sys
from pathlib import Path

import pytest

from security_quiz.bank import BankError, load_bank, normalize, select, shuffled_options, validate
from security_quiz.cli import main

PROJECT = Path(__file__).resolve().parent.parent


def good_item(**changes):
    item = {"id": "x-1", "categoria": "Redes", "dificultad": "facil", "pregunta": "¿?",
            "opciones": ["a", "b", "c", "d"], "respuesta": "B", "explicacion": "porque"}
    item.update(changes)
    return item


def test_default_bank_is_valid_and_has_every_category():
    questions = load_bank()
    assert len(questions) == 24
    assert {q.category for q in questions} == {
        "Redes", "Autenticación", "Phishing", "Malware", "SOC y registros", "Criptografía"}
    assert len({q.id for q in questions}) == len(questions)


def test_answers_are_spread_over_letters():
    """Si la respuesta fuera casi siempre la misma letra, el quiz se podría adivinar sin leer."""
    raw = json.loads((PROJECT / "data" / "preguntas.json").read_text(encoding="utf-8"))
    letters = {item["respuesta"] for item in raw["preguntas"]}
    assert len(letters) >= 3


@pytest.mark.parametrize(
    "changes, message",
    [
        ({"id": ""}, "falta 'id'"),
        ({"dificultad": "extrema"}, "'dificultad'"),
        ({"opciones": ["a", "b", "c"]}, "exactamente 4"),
        ({"opciones": ["a", "A", "c", "d"]}, "repetidas"),
        ({"respuesta": "E"}, "A, B, C o D"),
        ({"explicacion": " "}, "falta 'explicacion'"),
    ],
)
def test_validation_errors(changes, message):
    _, errors = validate({"preguntas": [good_item(**changes)]})
    assert len(errors) == 1 and message in errors[0]


def test_validation_reports_all_errors_and_duplicates():
    _, errors = validate({"preguntas": [good_item(), good_item(), good_item(id="y", respuesta="Z")]})
    assert len(errors) == 2
    assert "repetido" in errors[0] and "'y'" in errors[1]


def test_difficulty_accepts_accents():
    questions, errors = validate({"preguntas": [good_item(dificultad="Fácil")]})
    assert not errors and questions[0].difficulty == "facil"


def test_load_bank_errors(tmp_path):
    with pytest.raises(BankError, match="No existe"):
        load_bank(tmp_path / "no.json")
    bad = tmp_path / "b.json"
    bad.write_text("{roto", encoding="utf-8")
    with pytest.raises(BankError, match="no es JSON válido"):
        load_bank(bad)


def test_select_filters_and_is_reproducible():
    questions = load_bank()
    a = select(questions, "soc y registros", None, 3, random.Random(1))
    b = select(questions, "SOC Y REGISTROS", None, 3, random.Random(1))
    assert [q.id for q in a] == [q.id for q in b]
    assert all(q.category == "SOC y registros" for q in a)
    assert len(select(questions, None, "dificil", 0, random.Random(1))) == 6


def test_shuffled_options_keep_correct_answer():
    question = load_bank()[0]
    for seed in range(20):
        options, correct = shuffled_options(question, random.Random(seed))
        assert sorted(options) == sorted(question.options)
        assert options[correct] == question.options[question.answer]


def test_normalize():
    assert normalize("  Criptografía ") == "criptografia"


def correct_letters(seed: int, count: int, category: str | None = None) -> str:
    """Calcula las letras correctas reproduciendo la selección y el barajado del quiz."""
    rng = random.Random(seed)
    chosen = select(load_bank(), category, None, count, rng)
    return ",".join("ABCD"[shuffled_options(q, rng)[1]] for q in chosen)


def test_all_correct_answers(capsys):
    answers = correct_letters(42, 5)
    assert main(["--count", "5", "--seed", "42", "--answers", answers]) == 0
    out = capsys.readouterr().out
    assert "Aciertos: 5 de 5 (100 %)" in out
    assert "Ninguna categoría por debajo del 70 %" in out


def test_skips_and_review_list(capsys):
    assert main(["--category", "Redes", "--count", "2", "--seed", "3", "--answers", "S,S"]) == 0
    out = capsys.readouterr().out
    assert "saltadas: 2" in out and "Repasa: Redes" in out


def test_interactive_mode_retries_invalid_input(capsys):
    replies = iter(["x", "", "a"])
    assert main(["--count", "1", "--seed", "1"], ask=lambda q: next(replies)) == 0
    assert "Tu respuesta" not in capsys.readouterr().out  # en modo interactivo no se repite la respuesta


def test_end_of_input_skips(capsys):
    def eof(question):
        raise EOFError

    assert main(["--count", "2", "--seed", "1"], ask=eof) == 0
    assert "saltadas: 2" in capsys.readouterr().out


def test_list_validate_and_errors(capsys):
    assert main(["--list"]) == 0
    assert "SOC y registros" in capsys.readouterr().out
    assert main(["--validate"]) == 0
    assert main(["--category", "Astronomía"]) == 1
    assert "Usa --list" in capsys.readouterr().err
    assert main(["--answers", "A,X"]) == 1


def test_run_as_module():
    completed = subprocess.run(
        [sys.executable, "-m", "security_quiz", "--count", "2", "--seed", "5", "--answers", "A,B"],
        cwd=PROJECT, capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert completed.returncode == 0
    assert "Resultado" in completed.stdout
