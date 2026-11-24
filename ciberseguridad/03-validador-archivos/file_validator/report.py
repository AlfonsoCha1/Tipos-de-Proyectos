"""Presentación: texto para la terminal y exportación a JSON.

Los nombres validados son entrada no confiable; se escapan los caracteres de
control y de dirección del texto antes de mostrarlos.
"""

from __future__ import annotations

import json
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .rules import Rules, Skipped, Validation, safe_storage_name

NAME_CODES_WITH_SUGGESTION = {
    "NOMBRE_CARACTERES_CONTROL", "NOMBRE_CON_RUTA", "NOMBRE_CARACTERES_PROHIBIDOS",
    "NOMBRE_RESERVADO", "NOMBRE_TERMINA_EN_PUNTO_O_ESPACIO", "NOMBRE_LARGO",
}


class ExportError(Exception):
    """No se pudo escribir un archivo de exportación."""


def clean_text(text: str) -> str:
    out = []
    for char in text:
        category = unicodedata.category(char)
        if category == "Cf":
            out.append(f"\\u{ord(char):04x}")
        elif category == "Cc":
            out.append(f"\\x{ord(char):02x}")
        else:
            out.append(char)
    return "".join(out)


def render_text(results: Sequence[Validation], skipped: Sequence[Skipped], rules: Rules) -> str:
    title = "Validador de archivos - Cybersecurity Python Lab"
    lines = [title, "=" * len(title), ""]
    accepted = sum(1 for r in results if r.accepted)
    lines.append(f"Revisados: {len(results)} | aceptados: {accepted} | rechazados: {len(results) - accepted}")
    lines.append(
        f"Reglas: extensiones {', '.join(sorted(rules.allowed_extensions))} | "
        f"máximo {rules.max_size_bytes} bytes | nombre de hasta {rules.max_name_length} caracteres | "
        f"revisar contenido: {'sí' if rules.check_content else 'no'}"
    )
    lines.append("")
    for result in results:
        status = "ACEPTADO " if result.accepted else "RECHAZADO"
        size = f" ({result.size} bytes)" if result.size is not None else " (solo nombre)"
        lines.append(f"[{status}] '{clean_text(result.name)}'{size}")
        for problem in result.problems:
            lines.append(f"  - {problem.code}: {clean_text(problem.message)}")
            lines.append(f"      Por qué importa: {problem.why}")
        if any(p.code in NAME_CODES_WITH_SUGGESTION for p in result.problems):
            lines.append(f"  Nombre seguro sugerido: {safe_storage_name(result.name)}")
        if result.problems:
            lines.append("")
    if skipped:
        lines.append("")
        lines.append(f"No revisados: {len(skipped)}")
        for item in skipped:
            lines.append(f"  {clean_text(str(item.path))}  {item.reason}")
    lines.append("")
    lines.append("Nota: esta herramienta no borra, mueve ni renombra nada; solo explica la decisión.")
    return "\n".join(lines)


def check_output_path(path: Path, force: bool) -> None:
    if path.exists() and not force:
        raise ExportError(f"{path} ya existe. Usa --force para sobrescribirlo.")


def export_json(results: Sequence[Validation], skipped: Sequence[Skipped], path: Path) -> None:
    data: dict[str, Any] = {
        "tool": "file_validator",
        "version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "results": [
            {
                "name": r.name,
                "path": str(r.path) if r.path else None,
                "size": r.size,
                "accepted": r.accepted,
                "problems": [{"code": p.code, "message": p.message, "why": p.why} for p in r.problems],
            }
            for r in results
        ],
        "skipped": [{"path": str(s.path), "reason": s.reason} for s in skipped],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
