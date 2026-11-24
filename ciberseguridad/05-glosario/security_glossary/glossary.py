"""Glosario: lectura, validación y búsqueda sin distinguir mayúsculas ni acentos.

Orden de los resultados de ``search``:

1. Coincidencia exacta con el término o un sinónimo ("mfa" -> MFA, "2fa" -> MFA).
2. El texto buscado aparece dentro del término o de un sinónimo ("spray" -> Password spraying).
3. Aparece en la definición o el ejemplo.

Si no hay nada, ``suggest`` propone términos parecidos con ``difflib``
("fishing" -> Phishing).
"""

from __future__ import annotations

import difflib
import json
import random
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

DEFAULT_GLOSSARY = Path(__file__).resolve().parent.parent / "data" / "glosario.json"


class GlossaryError(Exception):
    """El glosario no existe, no es JSON válido o tiene entradas inválidas."""


@dataclass(frozen=True)
class Term:
    name: str
    category: str
    synonyms: tuple[str, ...]
    definition: str
    example: str
    related: tuple[str, ...]


def normalize(text: str) -> str:
    """'Contención ' -> 'contencion' (minúsculas, sin acentos, espacios simples)."""
    stripped = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return " ".join(stripped.lower().split())


def validate(raw: object) -> tuple[list[Term], list[str]]:
    if not isinstance(raw, dict) or not isinstance(raw.get("terminos"), list):
        return [], ["el archivo debe tener un objeto con la lista 'terminos'"]
    terms, errors, names = [], [], {}
    for position, item in enumerate(raw["terminos"], start=1):
        if not isinstance(item, dict):
            errors.append(f"entrada #{position}: debe ser un objeto")
            continue
        label = f"'{item.get('termino')}'" if item.get("termino") else f"entrada #{position}"
        problems = [f"falta '{k}'" for k in ("termino", "categoria", "definicion") if not str(item.get(k, "")).strip()]
        lists = {k: item.get(k, []) for k in ("sinonimos", "relacionados")}
        for key, value in lists.items():
            if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                problems.append(f"'{key}' debe ser una lista de textos")
        if not problems and normalize(item["termino"]) in names:
            problems.append("término repetido")
        if problems:
            errors.append(f"{label}: " + "; ".join(problems))
            continue
        names[normalize(item["termino"])] = item["termino"]
        terms.append(Term(item["termino"].strip(), item["categoria"].strip(), tuple(lists["sinonimos"]),
                          item["definicion"].strip(), str(item.get("ejemplo", "")).strip(), tuple(lists["relacionados"])))
    for term in terms:
        missing = [r for r in term.related if normalize(r) not in names]
        if missing:
            errors.append(f"'{term.name}': relacionados que no existen en el glosario: {', '.join(missing)}")
    return terms, errors


def load_glossary(path: Path | None = None) -> list[Term]:
    glossary_path = path or DEFAULT_GLOSSARY
    try:
        raw = json.loads(glossary_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise GlossaryError(f"No existe el glosario: {glossary_path}") from exc
    except json.JSONDecodeError as exc:
        raise GlossaryError(f"{glossary_path} no es JSON válido (línea {exc.lineno}, columna {exc.colno}): {exc.msg}") from exc
    terms, errors = validate(raw)
    if errors:
        raise GlossaryError("el glosario tiene errores:\n  - " + "\n  - ".join(errors))
    return sorted(terms, key=lambda t: normalize(t.name))


def search(terms: Sequence[Term], query: str) -> list[Term]:
    q = normalize(query)
    if not q:
        return []
    exact, partial, in_text = [], [], []
    for term in terms:
        names = [normalize(term.name), *(normalize(s) for s in term.synonyms)]
        if q in names:
            exact.append(term)
        elif any(q in name for name in names):
            partial.append(term)
        elif q in normalize(term.definition) or q in normalize(term.example):
            in_text.append(term)
    return exact + partial + in_text


def suggest(terms: Sequence[Term], query: str, limit: int = 3) -> list[str]:
    options: dict[str, str] = {}
    for term in terms:
        for name in (term.name, *term.synonyms):
            options.setdefault(normalize(name), term.name)
    matches = difflib.get_close_matches(normalize(query), list(options), n=limit * 2, cutoff=0.6)
    unique: list[str] = []
    for match in matches:
        if options[match] not in unique:
            unique.append(options[match])
    return unique[:limit]


def by_category(terms: Sequence[Term], category: str | None = None) -> dict[str, list[Term]]:
    groups: dict[str, list[Term]] = {}
    for term in terms:
        if category is None or normalize(term.category) == normalize(category):
            groups.setdefault(term.category, []).append(term)
    return dict(sorted(groups.items()))


def random_term(terms: Sequence[Term], rng: random.Random | None = None) -> Term:
    return (rng or random.Random()).choice(list(terms))
