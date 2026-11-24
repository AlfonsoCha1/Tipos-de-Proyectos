"""Presentación: texto para la terminal y exportación a JSON.

El nombre de un archivo sospechoso lo eligió quien lo creó: puede traer
caracteres de control o bidireccionales. ``clean_text`` los muestra escapados
(``\\u202e``) para que el reporte enseñe el truco en vez de caer en él.
"""

from __future__ import annotations

import json
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .inspector import Inspection, Skipped
from .iocs import IocList
from .signatures import BIDI_CONTROLS


class ExportError(Exception):
    """No se pudo escribir un archivo de exportación."""


def clean_text(text: str) -> str:
    """Escapa caracteres de control (``\\x1b``) y de dirección del texto (``\\u202e``)."""
    out = []
    for char in text:
        if char in BIDI_CONTROLS or unicodedata.category(char) == "Cf":
            out.append(f"\\u{ord(char):04x}")
        elif unicodedata.category(char) == "Cc":
            out.append(f"\\x{ord(char):02x}")
        else:
            out.append(char)
    return "".join(out)


def _display(path: Path, base: Path | None) -> str:
    if base is not None:
        try:
            return clean_text(str(path.relative_to(base)))
        except ValueError:
            pass
    return clean_text(str(path))


def format_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"  # pragma: no cover


def render_text(
    results: Sequence[Inspection],
    skipped: Sequence[Skipped],
    iocs: IocList | None,
    base: Path | None = None,
    show_hashes: str = "sha256",
) -> str:
    title = "Verificador de archivos sospechosos - Cybersecurity Python Lab"
    lines = [title, "=" * len(title), ""]
    counts = Counter(r.verdict for r in results)
    lines.append(
        f"Archivos revisados: {len(results)} | SOSPECHOSO: {counts['SOSPECHOSO']} | "
        f"REVISAR: {counts['REVISAR']} | SIN INDICIOS: {counts['SIN INDICIOS']}"
    )
    if iocs is not None:
        source = _display(iocs.source, Path.cwd()) if iocs.source else "(en memoria)"
        lines.append(f"Lista de indicadores: {source} ({len(iocs.entries)} huellas)")
        for number, raw in iocs.invalid_lines:
            lines.append(f"  Aviso: línea {number} de la lista no es una huella válida: {clean_text(raw)}")
    else:
        lines.append("Lista de indicadores: no se usó (agrega --iocs ARCHIVO)")
    lines.append("")

    for result in results:
        lines.append(f"[{result.verdict}] {_display(result.path, base)}")
        lines.append(
            f"  Tamaño: {format_size(result.size)} | tipo real: {result.detected.label} | "
            f"extensión: {result.extension or '(ninguna)'}"
        )
        lines.append(f"  SHA-256: {result.sha256}")
        if show_hashes == "all":
            lines.append(f"  SHA-1:   {result.sha1}")
            lines.append(f"  MD5:     {result.md5}")
        for finding in result.findings:
            lines.append(f"  - {finding.severity:<5} {finding.code}: {clean_text(finding.message)}")
            if finding.advice:
                lines.append(f"          Qué hacer: {clean_text(finding.advice)}")
        lines.append("")

    if skipped:
        lines.append(f"No revisados: {len(skipped)}")
        for item in skipped:
            lines.append(f"  {_display(item.path, base)}  {clean_text(item.reason)}")
        lines.append("")
    lines.append(
        "Nota: SIN INDICIOS no significa seguro. La herramienta nunca ejecuta, abre ni extrae los archivos."
    )
    return "\n".join(lines)


def check_output_path(path: Path, force: bool) -> None:
    if path.exists() and not force:
        raise ExportError(f"{path} ya existe. Usa --force para sobrescribirlo.")


def as_dict(results: Sequence[Inspection], skipped: Sequence[Skipped]) -> dict[str, Any]:
    return {
        "tool": "file_inspector",
        "version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": [
            {
                "path": str(r.path),
                "verdict": r.verdict,
                "size": r.size,
                "extension": r.extension,
                "detected_type": r.detected.key,
                "md5": r.md5,
                "sha1": r.sha1,
                "sha256": r.sha256,
                "findings": [
                    {"severity": f.severity, "code": f.code, "message": f.message, "advice": f.advice}
                    for f in r.findings
                ],
            }
            for r in results
        ],
        "skipped": [{"path": str(s.path), "reason": s.reason} for s in skipped],
    }


def export_json(results: Sequence[Inspection], skipped: Sequence[Skipped], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(as_dict(results, skipped), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
