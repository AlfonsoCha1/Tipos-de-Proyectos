"""Banco de preguntas: lectura, validación y selección. No imprime nada.

El banco es un JSON editable. Antes de usarlo se valida pregunta por pregunta y
se reportan TODOS los errores juntos (con el id de cada pregunta), en vez de
fallar en el primero: así quien lo edita corrige todo de una vez.
"""

from __future__ import annotations

import json
import random
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

LETTERS = "ABCD"
DIFFICULTIES = ("facil", "media", "dificil")
DEFAULT_BANK = Path(__file__).resolve().parent.parent / "data" / "preguntas.json"


class BankError(Exception):
    """El banco no existe, no es JSON válido o tiene preguntas inválidas."""


@dataclass(frozen=True)
class Question:
    id: str
    category: str
    difficulty: str
    prompt: str
    options: tuple[str, ...]
    answer: int  # índice 0-3
    explanation: str


def normalize(text: str) -> str:
    """Minúsculas y sin acentos: 'Fácil' == 'facil'."""
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).lower().strip()


def validate(raw: object) -> tuple[list[Question], list[str]]:
    """Convierte el JSON en preguntas y junta todos los errores encontrados."""
    if not isinstance(raw, dict) or not isinstance(raw.get("preguntas"), list):
        return [], ["el archivo debe tener un objeto con la lista 'preguntas'"]
    questions, errors, seen = [], [], set()
    for position, item in enumerate(raw["preguntas"], start=1):
        label = f"pregunta #{position}"
        if not isinstance(item, dict):
            errors.append(f"{label}: debe ser un objeto")
            continue
        qid = item.get("id")
        label = f"pregunta '{qid}'" if isinstance(qid, str) and qid else label
        problems = []
        if not isinstance(qid, str) or not qid.strip():
            problems.append("falta 'id'")
        elif qid in seen:
            problems.append("'id' repetido")
        for key in ("categoria", "pregunta", "explicacion"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                problems.append(f"falta '{key}'")
        difficulty = normalize(str(item.get("dificultad", "")))
        if difficulty not in DIFFICULTIES:
            problems.append(f"'dificultad' debe ser {', '.join(DIFFICULTIES)}")
        options = item.get("opciones")
        if not isinstance(options, list) or len(options) != 4 or not all(isinstance(o, str) and o.strip() for o in options):
            problems.append("'opciones' debe tener exactamente 4 textos")
        elif len({normalize(o) for o in options}) != 4:
            problems.append("hay opciones repetidas")
        answer = str(item.get("respuesta", "")).strip().upper()
        if answer not in LETTERS:
            problems.append("'respuesta' debe ser A, B, C o D")
        if problems:
            errors.append(f"{label}: " + "; ".join(problems))
            continue
        seen.add(qid)
        questions.append(Question(
            qid, item["categoria"].strip(), difficulty, item["pregunta"].strip(),
            tuple(o.strip() for o in options), LETTERS.index(answer), item["explicacion"].strip(),
        ))
    return questions, errors


def load_bank(path: Path | None = None) -> list[Question]:
    bank_path = path or DEFAULT_BANK
    try:
        raw = json.loads(bank_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise BankError(f"No existe el banco de preguntas: {bank_path}") from exc
    except json.JSONDecodeError as exc:
        raise BankError(f"{bank_path} no es JSON válido (línea {exc.lineno}, columna {exc.colno}): {exc.msg}") from exc
    questions, errors = validate(raw)
    if errors:
        raise BankError("el banco tiene errores:\n  - " + "\n  - ".join(errors))
    if not questions:
        raise BankError("el banco no tiene preguntas")
    return questions


def select(
    questions: Sequence[Question],
    category: str | None = None,
    difficulty: str | None = None,
    count: int = 5,
    rng: random.Random | None = None,
) -> list[Question]:
    """Elige preguntas al azar (reproducible con una semilla) según los filtros."""
    rng = rng or random.Random()
    pool = [
        q for q in questions
        if (category is None or normalize(q.category) == normalize(category))
        and (difficulty is None or q.difficulty == normalize(difficulty))
    ]
    if count <= 0 or count >= len(pool):
        chosen = list(pool)
        rng.shuffle(chosen)
        return chosen
    return rng.sample(pool, count)


def shuffled_options(question: Question, rng: random.Random) -> tuple[list[str], int]:
    """Mezcla las opciones para que la respuesta no sea siempre la misma letra; devuelve el nuevo índice correcto."""
    order = list(range(4))
    rng.shuffle(order)
    return [question.options[i] for i in order], order.index(question.answer)
