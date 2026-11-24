"""Presentación: reporte de triaje para la terminal y exportación JSON de indicadores.

Los enlaces se muestran "desactivados" (``hxxps://dominio[.]com``) para que nadie
los abra por accidente al copiar el reporte, como se hace en los reportes de
un SOC. El texto del correo es entrada no confiable: se escapan caracteres de
control y de dirección del texto.
"""

from __future__ import annotations

import json
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

from . import __version__
from .indicators import Analysis
from .parser import defang

RECOMMENDATIONS = {
    "ALTO": "No hagas clic ni abras adjuntos. Reporta el correo al equipo de seguridad y bloquea el remitente y los enlaces.",
    "MEDIO": "Confirma con el remitente por otro medio (teléfono o sitio oficial escrito por ti) antes de actuar.",
    "BAJO": "Sin indicios fuertes. Aun así, no compartas contraseñas ni códigos por correo.",
}


class ExportError(Exception):
    """No se pudo escribir un archivo de exportación."""


def clean_text(text: str) -> str:
    out = []
    for char in text:
        category = unicodedata.category(char)
        if category == "Cf":
            out.append(f"\\u{ord(char):04x}")
        elif category == "Cc" and char not in "\n\t":
            out.append(f"\\x{ord(char):02x}")
        else:
            out.append(char)
    return "".join(out)


def _one_line(text: str, limit: int = 90) -> str:
    text = clean_text(" ".join(text.split()))
    return text if len(text) <= limit else text[: limit - 3] + "..."


def render_analysis(analysis: Analysis) -> list[str]:
    email = analysis.email
    lines = [f"Archivo: {clean_text(str(email.source))}  ({'correo .eml' if email.kind == 'eml' else 'mensaje de texto'})"]
    if email.kind == "eml":
        sender = f"{email.from_name} <{email.from_address}>" if email.from_name else email.from_address
        lines.append(f"  De:         {_one_line(sender)}")
        if email.reply_to:
            lines.append(f"  Responder a: {_one_line(', '.join(email.reply_to))}")
        lines.append(f"  Asunto:     {_one_line(email.subject)}")
        if email.auth_results:
            lines.append("  Autenticación: " + ", ".join(f"{k}={v}" for k, v in sorted(email.auth_results.items())))
        else:
            lines.append("  Autenticación: sin encabezado Authentication-Results")
    if email.links:
        lines.append(f"  Enlaces ({len(email.links)}, desactivados):")
        for link in email.links:
            visible = f"texto '{_one_line(link.text, 45)}' -> " if link.text else ""
            lines.append(f"    - {visible}{clean_text(defang(link.url))}")
    if email.attachments:
        lines.append(f"  Adjuntos ({len(email.attachments)}, no se guardan ni se abren):")
        for item in email.attachments:
            lines.append(f"    - {clean_text(item.filename)}  {item.content_type}  {item.size} B  SHA-256 {item.sha256[:16]}...")
    lines.append(f"  Indicadores ({len(analysis.indicators)}):")
    if not analysis.indicators:
        lines.append("    (ninguno)")
    for indicator in analysis.indicators:
        lines.append(f"    +{indicator.points:<3} {indicator.code}: {clean_text(indicator.detail)}")
        lines.append(f"         Posible falso positivo: {indicator.false_positive}")
    lines.append(f"  Puntuación: {analysis.score}/100 -> riesgo {analysis.level}")
    lines.append(f"  Recomendación: {RECOMMENDATIONS[analysis.level]}")
    return lines


def render_text(analyses: Sequence[Analysis], errors: Sequence[tuple[Path, str]]) -> str:
    title = "Analizador de correos - Cybersecurity Python Lab"
    lines = [title, "=" * len(title), ""]
    for analysis in analyses:
        lines += render_analysis(analysis)
        lines.append("")
    if len(analyses) > 1:
        lines.append("Resumen")
        width = max(len(str(a.email.source.name)) for a in analyses)
        for analysis in sorted(analyses, key=lambda a: -a.score):
            lines.append(f"  {clean_text(analysis.email.source.name).ljust(width)}  {analysis.score:>3}/100  {analysis.level}")
        lines.append("")
    for path, message in errors:
        lines.append(f"No analizado: {clean_text(str(path))}  {clean_text(message)}")
    if errors:
        lines.append("")
    lines.append("Nota: la herramienta no abre enlaces ni adjuntos. La puntuación prioriza; no prueba un fraude.")
    return "\n".join(lines)


def check_output_path(path: Path, force: bool) -> None:
    if path.exists() and not force:
        raise ExportError(f"{path} ya existe. Usa --force para sobrescribirlo.")


def export_json(analyses: Sequence[Analysis], path: Path) -> None:
    """Exporta indicadores de compromiso (dominios, URLs, hashes) listos para otra herramienta."""
    def item(a: Analysis) -> dict[str, Any]:
        e = a.email
        return {
            "source": str(e.source),
            "score": a.score,
            "level": a.level,
            "from": e.from_address,
            "reply_to": e.reply_to,
            "subject": e.subject,
            "auth_results": e.auth_results,
            "urls": [link.url for link in e.links],
            "domains": sorted({link.host for link in e.links if link.host}),
            "attachments": [
                {"filename": x.filename, "content_type": x.content_type, "size": x.size, "sha256": x.sha256}
                for x in e.attachments
            ],
            "indicators": [
                {"code": i.code, "points": i.points, "detail": i.detail, "false_positive": i.false_positive}
                for i in a.indicators
            ],
        }

    data = {
        "tool": "email_analyzer",
        "version": __version__,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "messages": [item(a) for a in analyses],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
