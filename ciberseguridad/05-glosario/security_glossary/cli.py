"""Interfaz del glosario: búsqueda, listado, término al azar y modo interactivo.

Códigos de salida: 0 = encontrado (o listado), 1 = error del glosario,
2 = argumentos inválidos, 3 = búsqueda sin resultados.
"""

from __future__ import annotations

import argparse
import random
import sys
import textwrap
from pathlib import Path
from typing import Callable, Sequence

from . import __version__
from .glossary import GlossaryError, Term, by_category, load_glossary, random_term, search, suggest

WIDTH = 88


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m security_glossary",
        description="Glosario de ciberseguridad en español. Busca sin importar mayúsculas ni acentos.",
    )
    parser.add_argument("query", nargs="*", metavar="TEXTO", help="término o palabra a buscar")
    parser.add_argument("--list", action="store_true", help="lista los términos por categoría")
    parser.add_argument("--category", metavar="CATEGORÍA", help="con --list, solo una categoría")
    parser.add_argument("--random", action="store_true", help="muestra un término al azar (para estudiar)")
    parser.add_argument("--seed", type=int, help="semilla para --random")
    parser.add_argument("--interactive", "-i", action="store_true", help="modo de consulta continua")
    parser.add_argument("--max", type=int, default=5, metavar="N", help="resultados a mostrar (por defecto 5)")
    parser.add_argument("--file", type=Path, metavar="JSON", help="otro archivo de glosario")
    parser.add_argument("--validate", action="store_true", help="valida el glosario y termina")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def render_term(term: Term) -> str:
    wrap = lambda label, text: textwrap.fill(text, WIDTH, initial_indent=label, subsequent_indent=" " * len(label))
    lines = [f"{term.name}  [{term.category}]"]
    if term.synonyms:
        lines.append(wrap("  También: ", ", ".join(term.synonyms)))
    lines.append(wrap("  Qué es: ", term.definition))
    if term.example:
        lines.append(wrap("  Ejemplo: ", term.example))
    if term.related:
        lines.append(wrap("  Ver también: ", ", ".join(term.related)))
    return "\n".join(lines)


def answer(terms: Sequence[Term], query: str, limit: int) -> tuple[str, bool]:
    results = search(terms, query)
    if not results:
        hints = suggest(terms, query)
        text = f"No encontré '{query}'."
        if hints:
            text += " ¿Quisiste decir: " + ", ".join(hints) + "?"
        return text, False
    shown = results[:limit]
    text = f"{len(results)} resultado(s) para '{query}':\n\n" + "\n\n".join(render_term(t) for t in shown)
    if len(results) > limit:
        text += f"\n\n... {len(results) - limit} más: " + ", ".join(t.name for t in results[limit:])
    return text, True


def main(argv: Sequence[str] | None = None, ask: Callable[[str], str] = input) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.max < 1:
        parser.error("--max debe ser 1 o mayor")
    try:
        terms = load_glossary(args.file)
        if args.validate:
            print(f"Glosario válido: {len(terms)} términos en {len(by_category(terms))} categorías.")
            return 0
        if args.list:
            groups = by_category(terms, args.category)
            if not groups:
                raise GlossaryError(f"no hay categoría '{args.category}'")
            for category, items in groups.items():
                print(f"{category} ({len(items)})")
                print(textwrap.fill(", ".join(t.name for t in items), WIDTH, initial_indent="  ", subsequent_indent="  "))
            print(f"\nTotal: {len(terms)} términos")
            return 0
        if args.random:
            print("Término al azar:\n\n" + render_term(random_term(terms, random.Random(args.seed))))
            return 0
        if args.interactive or not args.query:
            print("Glosario de ciberseguridad. Escribe un término (vacío o 'salir' para terminar).")
            while True:
                try:
                    query = ask("\n> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    return 0
                if query.lower() in ("", "salir", "exit", "q"):
                    return 0
                print(answer(terms, query, args.max)[0])
        text, found = answer(terms, " ".join(args.query), args.max)
        print(text)
        return 0 if found else 3
    except GlossaryError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
