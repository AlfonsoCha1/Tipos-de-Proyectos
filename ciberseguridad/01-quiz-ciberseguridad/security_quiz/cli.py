"""Interfaz del quiz: modo interactivo, respuestas por argumento, listado y validación.

Códigos de salida: 0 = correcto, 1 = error del banco de preguntas o filtros sin
resultados, 2 = argumentos inválidos.
"""

from __future__ import annotations

import argparse
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable, Sequence

from . import __version__
from .bank import DIFFICULTIES, LETTERS, BankError, Question, load_bank, normalize, select, shuffled_options


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m security_quiz",
        description="Quiz de ciberseguridad con explicación de cada respuesta. Las preguntas están en data/preguntas.json.",
    )
    parser.add_argument("--category", metavar="CATEGORÍA", help="solo una categoría (ver --list)")
    parser.add_argument("--difficulty", choices=DIFFICULTIES, help="solo una dificultad")
    parser.add_argument("--count", type=int, default=5, metavar="N", help="número de preguntas; 0 = todas (por defecto 5)")
    parser.add_argument("--seed", type=int, metavar="N", help="semilla para repetir la misma selección y orden")
    parser.add_argument("--answers", metavar="A,B,...", help="respuestas sin preguntar (S = saltar), útil para demos y pruebas")
    parser.add_argument("--no-shuffle", action="store_true", help="no mezcla el orden de las opciones")
    parser.add_argument("--bank", type=Path, metavar="JSON", help="otro banco de preguntas")
    parser.add_argument("--list", action="store_true", help="muestra categorías y número de preguntas")
    parser.add_argument("--validate", action="store_true", help="valida el banco de preguntas y termina")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _list(questions: Sequence[Question]) -> None:
    by_category: dict[str, Counter] = defaultdict(Counter)
    for q in questions:
        by_category[q.category][q.difficulty] += 1
    print(f"{'CATEGORÍA':<18} {'FÁCIL':>5} {'MEDIA':>5} {'DIFÍCIL':>7} {'TOTAL':>5}")
    for category in sorted(by_category):
        c = by_category[category]
        print(f"{category:<18} {c['facil']:>5} {c['media']:>5} {c['dificil']:>7} {sum(c.values()):>5}")
    print(f"{'Total':<18} {'':>5} {'':>5} {'':>7} {len(questions):>5}")


def _parse_answers(text: str | None) -> list[str] | None:
    if text is None:
        return None
    answers = [a.strip().upper() for a in text.split(",")]
    bad = [a for a in answers if a not in (*LETTERS, "S")]
    if bad:
        raise BankError(f"respuestas inválidas en --answers: {', '.join(bad)} (usa A, B, C, D o S)")
    return answers


def run_quiz(
    questions: Sequence[Question],
    rng: random.Random,
    shuffle: bool,
    answers: list[str] | None,
    ask: Callable[[str], str],
) -> list[tuple[Question, bool | None]]:
    """Aplica el quiz y devuelve (pregunta, acierto) donde None = saltada."""
    results: list[tuple[Question, bool | None]] = []
    for number, question in enumerate(questions, start=1):
        options, correct = shuffled_options(question, rng) if shuffle else (list(question.options), question.answer)
        print(f"\nPregunta {number}/{len(questions)}  [{question.category} · {question.difficulty}]")
        print(question.prompt)
        for letter, option in zip(LETTERS, options):
            print(f"  {letter}) {option}")
        if answers is not None:
            reply = answers[number - 1] if number - 1 < len(answers) else "S"
            print(f"Tu respuesta: {reply}")
        else:
            reply = ""
            while reply not in (*LETTERS, "S"):
                try:
                    reply = ask("Tu respuesta (A-D, o S para saltar): ").strip().upper()
                except EOFError:
                    reply = "S"
        if reply == "S":
            print(f"Saltada. La respuesta era {LETTERS[correct]}) {options[correct]}")
            results.append((question, None))
        elif LETTERS.index(reply) == correct:
            print("Correcto.")
            results.append((question, True))
        else:
            print(f"Incorrecto. La respuesta era {LETTERS[correct]}) {options[correct]}")
            results.append((question, False))
        print(f"Por qué: {question.explanation}")
    return results


def summarize(results: Sequence[tuple[Question, bool | None]]) -> str:
    total = len(results)
    right = sum(1 for _, ok in results if ok)
    skipped = sum(1 for _, ok in results if ok is None)
    lines = ["", "Resultado", "=========",
             f"Aciertos: {right} de {total} ({100 * right / total:.0f} %) | saltadas: {skipped}"]
    per_category: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for question, ok in results:
        per_category[question.category][1] += 1
        per_category[question.category][0] += 1 if ok else 0
    for category, (good, count) in sorted(per_category.items()):
        lines.append(f"  {category:<18} {good}/{count}")
    weak = sorted(c for c, (good, count) in per_category.items() if good / count < 0.7)
    lines.append("Repasa: " + ", ".join(weak) if weak else "¡Bien! Ninguna categoría por debajo del 70 %.")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None, ask: Callable[[str], str] = input) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    try:
        questions = load_bank(args.bank)
        if args.validate:
            print(f"Banco válido: {len(questions)} preguntas.")
            return 0
        if args.list:
            _list(questions)
            return 0
        if args.category and normalize(args.category) not in {normalize(q.category) for q in questions}:
            raise BankError(f"no hay categoría '{args.category}'. Usa --list para verlas.")
        rng = random.Random(args.seed)
        chosen = select(questions, args.category, args.difficulty, args.count, rng)
        if not chosen:
            raise BankError("ninguna pregunta coincide con esos filtros")
        answers = _parse_answers(args.answers)
        title = "Quiz de ciberseguridad - Cybersecurity Python Lab"
        print(title + "\n" + "=" * len(title))
        results = run_quiz(chosen, rng, not args.no_shuffle, answers, ask)
        print(summarize(results))
        return 0
    except BankError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nQuiz interrumpido.")
        return 0
