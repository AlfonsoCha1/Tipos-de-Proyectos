"""Lectura de correos ``.eml`` y de mensajes de texto, sin abrir enlaces ni adjuntos.

Se usa el paquete ``email`` de la biblioteca estándar con ``policy.default``,
que decodifica encabezados (``=?utf-8?...?=``) y cuerpos (base64,
quoted-printable). Los adjuntos solo se miden y se les calcula SHA-256 en
memoria: nunca se guardan en disco ni se ejecutan.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parseaddr
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

MAX_BYTES = 10 * 1024 * 1024  # un correo de laboratorio no debería pesar más
URL_RE = re.compile(r"""(?i)\b((?:https?://|www\.)[^\s<>"'()\[\]]+)""")
AUTH_RE = re.compile(r"(?i)\b(spf|dkim|dmarc)\s*=\s*([a-z]+)")


class EmailFormatError(Exception):
    """El archivo no se pudo leer como correo o mensaje."""


@dataclass(frozen=True)
class Link:
    url: str
    text: str  # texto visible ("" si el enlace venía en texto plano)
    source: str  # "html" o "texto"

    @property
    def host(self) -> str:
        return host_of(self.url)


@dataclass(frozen=True)
class Attachment:
    filename: str
    content_type: str
    size: int
    sha256: str


@dataclass
class ParsedEmail:
    source: Path
    kind: str  # "eml" o "texto"
    from_name: str = ""
    from_address: str = ""
    reply_to: list[str] = field(default_factory=list)
    return_path: str = ""
    subject: str = ""
    date: str = ""
    auth_results: dict[str, str] = field(default_factory=dict)
    text: str = ""
    links: list[Link] = field(default_factory=list)
    attachments: list[Attachment] = field(default_factory=list)


def host_of(url: str) -> str:
    """Host en minúsculas de una URL (acepta 'www.ejemplo.com' sin esquema)."""
    if not re.match(r"(?i)^[a-z][a-z0-9+.-]*://", url):
        url = "http://" + url
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:
        return ""
    return host.lower().rstrip(".")


def domain_of_address(address: str) -> str:
    return address.rpartition("@")[2].lower().strip(" >").rstrip(".")


class _LinkCollector(HTMLParser):
    """Recolecta <a href> con su texto visible y el texto general del HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[Link] = []
        self.text_parts: list[str] = []
        self._href: str | None = None
        self._anchor: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag == "a":
            self._href = dict(attrs).get("href") or ""
            self._anchor = []

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1
        if tag == "a" and self._href is not None:
            href = self._href.strip()
            if href.lower().startswith(("http://", "https://")):
                self.links.append(Link(href, " ".join("".join(self._anchor).split()), "html"))
            self._href = None

    def handle_data(self, data):
        if self._skip:
            return
        self.text_parts.append(data)
        if self._href is not None:
            self._anchor.append(data)


def _text_links(text: str) -> list[Link]:
    links = []
    for match in URL_RE.finditer(text):
        url = match.group(1).rstrip(".,;:!?")
        links.append(Link(url, "", "texto"))
    return links


def _dedupe(links: list[Link]) -> list[Link]:
    seen, unique = set(), []
    for link in links:
        key = (link.url, link.text)
        if key not in seen:
            seen.add(key)
            unique.append(link)
    return unique


def parse_eml(data: bytes, source: Path) -> ParsedEmail:
    message: EmailMessage = BytesParser(policy=policy.default).parsebytes(data)  # type: ignore[assignment]
    if not message.keys():
        raise EmailFormatError(f"{source} no tiene encabezados de correo (From, Subject...). Usa --text para mensajes sueltos")
    parsed = ParsedEmail(source, "eml")
    try:
        name, address = parseaddr(str(message.get("From", "")))
        parsed.from_name, parsed.from_address = name.strip(), address.strip().lower()
        parsed.reply_to = [addr.lower() for _, addr in getaddresses([str(v) for v in message.get_all("Reply-To", [])]) if addr]
        parsed.return_path = parseaddr(str(message.get("Return-Path", "")))[1].lower()
        parsed.subject = " ".join(str(message.get("Subject", "")).split())
        parsed.date = str(message.get("Date", ""))
    except (ValueError, TypeError) as exc:  # encabezados mal formados a propósito
        raise EmailFormatError(f"{source}: encabezados inválidos ({exc})") from exc
    for header in message.get_all("Authentication-Results", []):
        for mechanism, result in AUTH_RE.findall(str(header)):
            parsed.auth_results.setdefault(mechanism.lower(), result.lower())

    texts, links = [], []
    for part in message.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        disposition = part.get_content_disposition()
        if filename or disposition == "attachment":
            payload = part.get_payload(decode=True) or b""
            parsed.attachments.append(Attachment(
                filename or "(sin nombre)", part.get_content_type(), len(payload), hashlib.sha256(payload).hexdigest(),
            ))
            continue
        try:
            content = part.get_content()
        except (LookupError, ValueError):  # charset desconocido o contenido dañado
            content = (part.get_payload(decode=True) or b"").decode("utf-8", errors="replace")
        if not isinstance(content, str):
            continue
        if part.get_content_type() == "text/html":
            collector = _LinkCollector()
            collector.feed(content)
            links += collector.links
            texts.append(" ".join("".join(collector.text_parts).split()))
        elif part.get_content_type() == "text/plain":
            texts.append(content)
            links += _text_links(content)
    parsed.text = "\n".join(texts)
    parsed.links = _dedupe(links)
    return parsed


def parse_text(data: bytes, source: Path) -> ParsedEmail:
    """Mensaje suelto (SMS, WhatsApp, cuerpo pegado): solo texto y enlaces."""
    text = data.decode("utf-8-sig", errors="replace")
    return ParsedEmail(source, "texto", text=text, links=_dedupe(_text_links(text)))


def load_message(path: Path, force_text: bool = False) -> ParsedEmail:
    size = path.stat().st_size
    if size > MAX_BYTES:
        raise EmailFormatError(f"{path} pesa {size} bytes; el límite del laboratorio es {MAX_BYTES}")
    data = path.read_bytes()
    if force_text or path.suffix.lower() != ".eml":
        return parse_text(data, path)
    return parse_eml(data, path)


def defang(url: str) -> str:
    """Vuelve un enlace no clicable para reportes: https://a.b -> hxxps://a[.]b"""
    result = re.sub(r"(?i)^http", "hxxp", url)
    host = host_of(url)
    if host:
        result = result.replace(host, host.replace(".", "[.]"), 1)
    return result
