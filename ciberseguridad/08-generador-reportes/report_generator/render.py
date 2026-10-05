"""Generación del reporte en Markdown y en HTML.

Todo texto que viene de los eventos es entrada no confiable:

* Markdown: ``md_escape`` neutraliza los caracteres con significado especial
  (enlaces, imágenes, tablas, HTML en línea).
* HTML: ``html.escape`` convierte ``<``, ``>``, ``&`` y comillas. El archivo
  no incluye JavaScript, ni recursos externos, y declara una política
  ``Content-Security-Policy`` que los bloquea aunque algo se colara.
"""

from __future__ import annotations

import html
import unicodedata
from datetime import datetime, tzinfo
from typing import Sequence

from . import __version__
from .analysis import Summary, severity_label, sort_events, summarize
from .models import SEVERITIES, Event, RejectedRow
from .timeutils import format_timestamp

DISCLAIMER = (
    "Reporte generado automáticamente a partir de los datos recibidos. No valida que los eventos "
    "sean ciertos ni completos; úsalo como apoyo para la revisión humana."
)
URGENT = ("critica", "alta")


# --------------------------------------------------------------------------
# Limpieza de texto no confiable
# --------------------------------------------------------------------------

def single_line(text: str) -> str:
    """Colapsa saltos de línea y escapa caracteres de control (p. ej. ANSI)."""
    pieces = []
    for char in text:
        if char in "\r\n\t":
            pieces.append(" ")
        elif unicodedata.category(char) == "Cc":
            pieces.append(f"\\x{ord(char):02x}")
        else:
            pieces.append(char)
    return " ".join("".join(pieces).split())


def md_escape(text: str) -> str:
    """Escapa texto para Markdown (celdas de tabla incluidas)."""
    text = single_line(text)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for char in ("\\", "`", "*", "_", "[", "]", "|", "!", "#", "~"):
        text = text.replace(char, "\\" + char)
    return text


def html_escape(text: str) -> str:
    """Escapa texto para colocarlo dentro de un elemento o atributo HTML."""
    return html.escape(single_line(text), quote=True)


# --------------------------------------------------------------------------
# Piezas comunes
# --------------------------------------------------------------------------

def _when(value: datetime, tz: tzinfo) -> str:
    return format_timestamp(value, tz)


def _location(event: Event) -> str:
    return event.origin


def _context_lines(
    events: Sequence[Event],
    rejected: Sequence[RejectedRow],
    files: Sequence[str],
    rows_read: int,
) -> list[str]:
    return [
        f"Archivos: {', '.join(files)}",
        f"Filas leídas: {rows_read} · eventos válidos: {len(events)} · filas rechazadas: {len(rejected)}",
    ]


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------

def _md_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return lines


def render_markdown(
    events: Sequence[Event],
    rejected: Sequence[RejectedRow],
    *,
    title: str,
    files: Sequence[str],
    rows_read: int,
    display_tz: tzinfo,
    generated_at: datetime,
    top: int = 5,
    max_rejected_shown: int = 100,
) -> str:
    """Devuelve el reporte completo en Markdown."""
    summary = summarize(events, display_tz, top)
    ordered = sort_events(events)
    out: list[str] = [f"# {md_escape(title)}", ""]
    out.append(f"Generado: {_when(generated_at, display_tz)} · herramienta report_generator {__version__}")
    out.append("")
    out += [f"- {md_escape(line)}" for line in _context_lines(events, rejected, files, rows_read)]
    out += ["", f"> {md_escape(DISCLAIMER)}", ""]

    out += ["## Resumen ejecutivo", ""]
    out += [f"- {md_escape(line)}" for line in summary.highlights]
    out.append(
        f"- Periodo cubierto: {_when(summary.first, display_tz)} a {_when(summary.last, display_tz)}."
    )
    out.append("")

    out += ["## Eventos por severidad", ""]
    out += _md_table(
        ["Severidad", "Eventos"],
        [[severity_label(name), str(summary.by_severity[name])] for name in SEVERITIES],
    )
    out += ["", "## Eventos por fuente", ""]
    out += _md_table(["Fuente", "Eventos"], [[md_escape(name), str(n)] for name, n in summary.by_source])
    out += ["", "## Eventos por día", ""]
    out += _md_table(["Día", "Eventos"], [[day.isoformat(), str(n)] for day, n in summary.per_day])

    out += ["", f"## IPs más frecuentes (hasta {top})", ""]
    out += _md_table(["IP", "Eventos"], [[f"`{ip}`", str(n)] for ip, n in summary.top_ips]) if summary.top_ips else ["Ningún evento trae IP."]
    out += ["", f"## Cuentas más frecuentes (hasta {top})", ""]
    out += _md_table(["Cuenta", "Eventos"], [[md_escape(u), str(n)] for u, n in summary.top_users]) if summary.top_users else ["Ningún evento trae cuenta."]

    out += ["", "## Todos los eventos (más graves primero)", ""]
    out += _md_table(
        ["Hora", "Severidad", "Fuente", "Título", "IP", "Cuenta", "Origen"],
        [
            [_when(e.timestamp, display_tz), severity_label(e.severity), md_escape(e.source),
             md_escape(e.title), f"`{e.ip}`" if e.ip else "", md_escape(e.user), md_escape(_location(e))]
            for e in ordered
        ],
    )

    detailed = [e for e in ordered if e.severity in URGENT and e.description]
    if detailed:
        out += ["", "## Detalle de eventos críticos y altos", ""]
        for event in detailed:
            out.append(f"- **{md_escape(event.title)}** ({severity_label(event.severity)}, {md_escape(_location(event))}): "
                       f"{md_escape(event.description)}")

    if rejected:
        out += ["", "## Filas rechazadas", "",
                "Estas filas no se incluyeron en las estadísticas porque no cumplen el esquema:", ""]
        out += _md_table(
            ["Origen", "Motivo"],
            [[md_escape(r.origin), md_escape(r.reason)] for r in rejected[:max_rejected_shown]],
        )
        if len(rejected) > max_rejected_shown:
            out += ["", f"(Se muestran {max_rejected_shown} de {len(rejected)} filas rechazadas.)"]
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

_CSS = """
:root{color-scheme:light dark;--bg:#fff;--fg:#1a1a1a;--muted:#555;--line:#d0d0d0;--card:#f5f6f8}
@media (prefers-color-scheme:dark){:root{--bg:#15171a;--fg:#e8e8e8;--muted:#a0a0a0;--line:#3a3d42;--card:#1f2226}}
body{font-family:system-ui,Segoe UI,Arial,sans-serif;background:var(--bg);color:var(--fg);margin:0 auto;max-width:1000px;padding:16px 16px 48px;line-height:1.5}
h1{font-size:1.6rem;margin:.4em 0}h2{font-size:1.15rem;margin-top:1.8em;border-bottom:1px solid var(--line);padding-bottom:.2em}
.meta,.note{color:var(--muted);font-size:.9rem}.note{background:var(--card);padding:8px 12px;border-radius:6px}
.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;font-size:.9rem}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}th{background:var(--card)}
code{font-family:ui-monospace,Consolas,monospace}
.sev{font-weight:700;padding:1px 8px;border-radius:10px;border:1px solid currentColor;white-space:nowrap}
.sev-critica{color:#a4001f}.sev-alta{color:#b34700}.sev-media{color:#7a6200}.sev-baja{color:#1d6b3a}.sev-info{color:#3d5a80}
@media (prefers-color-scheme:dark){.sev-critica{color:#ff7a90}.sev-alta{color:#ffa566}.sev-media{color:#e6cf5c}.sev-baja{color:#6fd391}.sev-info{color:#8fb3e6}}
""".strip()


def _html_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """Tabla HTML. Las celdas de ``rows`` deben venir ya escapadas o construidas por el código."""
    head = "".join(f"<th>{h}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


def _sev_badge(severity: str) -> str:
    # El texto de la severidad siempre se muestra: el color nunca es la única señal.
    return f'<span class="sev sev-{severity}">{html_escape(severity_label(severity))}</span>'


def render_html(
    events: Sequence[Event],
    rejected: Sequence[RejectedRow],
    *,
    title: str,
    files: Sequence[str],
    rows_read: int,
    display_tz: tzinfo,
    generated_at: datetime,
    top: int = 5,
    max_rejected_shown: int = 100,
) -> str:
    """Devuelve el reporte como un único archivo HTML autocontenido."""
    summary = summarize(events, display_tz, top)
    ordered = sort_events(events)
    e = html_escape
    parts: list[str] = []

    parts.append(f"<h1>{e(title)}</h1>")
    parts.append(f'<p class="meta">Generado: {e(_when(generated_at, display_tz))} · report_generator {__version__}</p>')
    parts.append("<ul>" + "".join(f"<li>{e(line)}</li>" for line in _context_lines(events, rejected, files, rows_read)) + "</ul>")
    parts.append(f'<p class="note">{e(DISCLAIMER)}</p>')

    parts.append("<h2>Resumen ejecutivo</h2><ul>")
    parts += [f"<li>{e(line)}</li>" for line in summary.highlights]
    parts.append(f"<li>Periodo cubierto: {e(_when(summary.first, display_tz))} a {e(_when(summary.last, display_tz))}.</li></ul>")

    parts.append("<h2>Eventos por severidad</h2>")
    parts.append(_html_table(["Severidad", "Eventos"],
                             [[_sev_badge(name), str(summary.by_severity[name])] for name in SEVERITIES]))
    parts.append("<h2>Eventos por fuente</h2>")
    parts.append(_html_table(["Fuente", "Eventos"], [[e(name), str(n)] for name, n in summary.by_source]))
    parts.append("<h2>Eventos por día</h2>")
    parts.append(_html_table(["Día", "Eventos"], [[day.isoformat(), str(n)] for day, n in summary.per_day]))

    parts.append(f"<h2>IPs más frecuentes (hasta {top})</h2>")
    parts.append(_html_table(["IP", "Eventos"], [[f"<code>{e(ip)}</code>", str(n)] for ip, n in summary.top_ips])
                 if summary.top_ips else "<p>Ningún evento trae IP.</p>")
    parts.append(f"<h2>Cuentas más frecuentes (hasta {top})</h2>")
    parts.append(_html_table(["Cuenta", "Eventos"], [[e(u), str(n)] for u, n in summary.top_users])
                 if summary.top_users else "<p>Ningún evento trae cuenta.</p>")

    parts.append("<h2>Todos los eventos (más graves primero)</h2>")
    parts.append(_html_table(
        ["Hora", "Severidad", "Fuente", "Título", "IP", "Cuenta", "Origen"],
        [
            [e(_when(ev.timestamp, display_tz)), _sev_badge(ev.severity), e(ev.source), e(ev.title),
             f"<code>{e(ev.ip)}</code>" if ev.ip else "", e(ev.user), e(_location(ev))]
            for ev in ordered
        ],
    ))

    detailed = [ev for ev in ordered if ev.severity in URGENT and ev.description]
    if detailed:
        parts.append("<h2>Detalle de eventos críticos y altos</h2><ul>")
        parts += [
            f"<li><strong>{e(ev.title)}</strong> ({e(severity_label(ev.severity))}, {e(_location(ev))}): {e(ev.description)}</li>"
            for ev in detailed
        ]
        parts.append("</ul>")

    if rejected:
        parts.append("<h2>Filas rechazadas</h2><p>Estas filas no se incluyeron en las estadísticas porque no cumplen el esquema:</p>")
        parts.append(_html_table(["Origen", "Motivo"],
                                 [[e(r.origin), e(r.reason)] for r in rejected[:max_rejected_shown]]))
        if len(rejected) > max_rejected_shown:
            parts.append(f"<p>(Se muestran {max_rejected_shown} de {len(rejected)} filas rechazadas.)</p>")

    body = "\n".join(parts)
    return (
        "<!DOCTYPE html>\n"
        '<html lang="es">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'\">\n"
        f"<title>{e(title)}</title>\n<style>\n{_CSS}\n</style>\n</head>\n<body>\n{body}\n</body>\n</html>\n"
    )
