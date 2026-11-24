"""Indicadores de phishing con puntos, explicación y posible falso positivo.

La suma de puntos (tope 100) da el nivel: 0-24 BAJO, 25-59 MEDIO, 60+ ALTO.
Ningún indicador por sí solo prueba un fraude; por eso cada uno dice cuándo
podría ser legítimo. La idea es priorizar qué correo revisar primero.
"""

from __future__ import annotations

import ipaddress
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import PurePosixPath
from typing import Mapping, Sequence

from .parser import ParsedEmail, domain_of_address, host_of

COMPOUND_SLDS = {"com", "gob", "org", "edu", "net", "co"}
RISKY_ATTACHMENTS = frozenset(
    ".exe .scr .com .pif .bat .cmd .msi .js .jse .vbs .vbe .wsf .hta .ps1 .lnk .jar .iso .img .vhd "
    ".docm .xlsm .pptm .one .chm .reg".split()
)
HTML_ATTACHMENTS = frozenset({".html", ".htm", ".shtml", ".svg"})
DECOY_EXTENSIONS = frozenset(".pdf .doc .docx .xls .xlsx .jpg .jpeg .png .txt .zip".split())
LEVELS = ((60, "ALTO"), (25, "MEDIO"), (0, "BAJO"))


@dataclass(frozen=True)
class Settings:
    protected_domains: Mapping[str, Sequence[str]]
    shorteners: frozenset[str]
    urgency_phrases: tuple[str, ...]
    credential_phrases: tuple[str, ...]


@dataclass(frozen=True)
class Indicator:
    code: str
    points: int
    detail: str
    false_positive: str


@dataclass
class Analysis:
    email: ParsedEmail
    indicators: list[Indicator] = field(default_factory=list)

    @property
    def score(self) -> int:
        return min(100, sum(i.points for i in self.indicators))

    @property
    def level(self) -> str:
        return next(label for threshold, label in LEVELS if self.score >= threshold)


def registrable_domain(host: str) -> str:
    """Aproximación al dominio registrable: 'login.banco.com.mx' -> 'banco.com.mx'."""
    labels = [label for label in host.lower().split(".") if label]
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in COMPOUND_SLDS:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).lower()


def contains_phrase(text: str, phrase: str) -> bool:
    return re.search(r"(?<!\w)" + re.escape(_strip_accents(phrase)) + r"(?!\w)", _strip_accents(text)) is not None


def levenshtein(a: str, b: str) -> int:
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def _skeleton(label: str) -> str:
    """Forma 'visual' de una etiqueta: rn->m, vv->w, 0->o, 1/i->l, 3->e, 5->s, sin guiones."""
    label = label.replace("rn", "m").replace("vv", "w").replace("-", "")
    return label.translate(str.maketrans({"0": "o", "1": "l", "i": "l", "3": "e", "5": "s"}))


def lookalike_of(host: str, protected: Mapping[str, Sequence[str]]) -> tuple[str, str] | None:
    """Devuelve (marca, dominio legítimo) si ``host`` imita a un dominio protegido sin serlo."""
    if not host:
        return None
    candidate = registrable_domain(host)
    for brand, domains in protected.items():
        for legit in domains:
            legit = legit.lower()
            if candidate == legit or host.endswith("." + legit):
                return None  # es el dominio legítimo o un subdominio suyo
    for brand, domains in protected.items():
        for legit in domains:
            legit_label = registrable_domain(legit.lower()).split(".")[0]
            cand_label = candidate.split(".")[0]
            if (levenshtein(cand_label, legit_label) <= 2 and len(legit_label) >= 5) \
                    or _skeleton(cand_label) == _skeleton(legit_label) \
                    or (len(legit_label) >= 5 and _skeleton(legit_label) in _skeleton(host.replace(".", ""))):
                return brand, legit
    return None


def _is_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host.strip("[]"))
        return True
    except ValueError:
        return False


def _extensions(name: str) -> list[str]:
    return ["." + part.lower() for part in PurePosixPath(name.replace("\\", "/")).name.split(".")[1:] if part]


def analyze(email: ParsedEmail, settings: Settings) -> Analysis:
    analysis = Analysis(email)
    add = analysis.indicators.append
    from_domain = domain_of_address(email.from_address) if email.from_address else ""

    # --- Autenticación del remitente (solo .eml) ---
    failed = sorted(m for m, r in email.auth_results.items() if r in ("fail", "softfail", "none", "permerror"))
    if failed:
        add(Indicator(
            "AUTENTICACION_FALLA", 10 * len(failed),
            "el servidor receptor registró " + ", ".join(f"{m}={email.auth_results[m]}" for m in failed),
            "reenvíos y listas de correo rompen SPF o DKIM; DMARC=pass compensa",
        ))

    # --- Remitente ---
    if from_domain:
        for reply in email.reply_to:
            if registrable_domain(domain_of_address(reply)) != registrable_domain(from_domain):
                add(Indicator(
                    "RESPONDER_A_DISTINTO", 15,
                    f"las respuestas irían a {reply}, no al dominio del remitente ({from_domain})",
                    "algunas empresas usan un sistema de soporte con otro dominio",
                ))
                break
        if email.return_path and registrable_domain(domain_of_address(email.return_path)) != registrable_domain(from_domain):
            add(Indicator(
                "RETURN_PATH_DISTINTO", 5,
                f"el sobre (Return-Path) es {email.return_path}",
                "los servicios de envío masivo usan su propio dominio en el Return-Path",
            ))
        look = lookalike_of(from_domain, settings.protected_domains)
        if look:
            add(Indicator(
                "REMITENTE_PARECIDO", 30,
                f"el dominio {from_domain} se parece a {look[1]} ({look[0]}) pero no es el mismo",
                "una marca puede registrar dominios parecidos para campañas; confirma en su sitio oficial",
            ))
        if "@" in email.from_name and domain_of_address(email.from_name) != from_domain:
            add(Indicator(
                "NOMBRE_CON_OTRO_CORREO", 20,
                f"el nombre visible muestra '{email.from_name}' pero el correo real es {email.from_address}",
                "poco común en correos legítimos",
            ))
        else:
            for brand, domains in settings.protected_domains.items():
                if contains_phrase(email.from_name, brand) and registrable_domain(from_domain) not in {d.lower() for d in domains}:
                    add(Indicator(
                        "NOMBRE_SUPLANTA_MARCA", 20,
                        f"el nombre visible dice '{email.from_name}' pero el dominio {from_domain} no es de {brand}",
                        "un proveedor autorizado podría escribir a nombre de la marca",
                    ))
                    break

    # --- Enlaces ---
    seen_codes: set[tuple[str, str]] = set()

    def add_once(indicator: Indicator, key: str) -> None:
        if (indicator.code, key) not in seen_codes:
            seen_codes.add((indicator.code, key))
            add(indicator)

    for link in email.links:
        host = link.host
        shown = re.search(r"(?i)\b((?:https?://)?(?:[a-z0-9-]+\.)+[a-z]{2,})\b", link.text or "")
        if shown:
            shown_host = host_of(shown.group(1))
            if shown_host and registrable_domain(shown_host) != registrable_domain(host):
                add_once(Indicator(
                    "ENLACE_ENGANOSO", 30,
                    f"el texto muestra {shown_host} pero el enlace lleva a {host}",
                    "algunos boletines usan un dominio de rastreo de clics",
                ), host)
        if _is_ip(host):
            add_once(Indicator("ENLACE_A_IP", 20, f"el enlace usa una dirección IP en vez de un dominio: {host}",
                               "raro en correos legítimos dirigidos a clientes"), host)
        if host.startswith("xn--") or ".xn--" in host:
            add_once(Indicator("ENLACE_PUNYCODE", 15, f"dominio internacionalizado (punycode): {host}",
                               "legítimo en dominios con ñ o acentos, pero también se usa para imitar letras"), host)
        if registrable_domain(host) in settings.shorteners:
            add_once(Indicator("ENLACE_ACORTADO", 5, f"enlace acortado ({host}): no se ve el destino real",
                               "muy común en boletines y redes sociales"), host)
        look = lookalike_of(host, settings.protected_domains)
        if look:
            add_once(Indicator("ENLACE_PARECIDO", 25, f"{host} imita a {look[1]} ({look[0]})",
                               "confirma escribiendo tú la dirección oficial"), host)
        if link.url.lower().startswith("http://") and not _is_ip(host):
            add_once(Indicator("ENLACE_SIN_HTTPS", 5, f"enlace sin cifrado (http://) a {host}",
                               "sitios viejos o de rastreo todavía usan http"), host)

    # --- Contenido ---
    full_text = f"{email.subject}\n{email.text}"

    def found(phrases: Sequence[str]) -> list[str]:
        """Frases presentes, sin repetir variantes con y sin acento ('será' y 'sera')."""
        hits, seen = [], set()
        for phrase in phrases:
            key = _strip_accents(phrase)
            if key not in seen and contains_phrase(full_text, phrase):
                seen.add(key)
                hits.append(phrase)
        return hits

    urgent = found(settings.urgency_phrases)
    if urgent:
        add(Indicator("URGENCIA", 10, "lenguaje de presión: " + ", ".join(f"'{p}'" for p in urgent[:4]),
                      "avisos reales de vencimiento también usan fechas límite"))
    credentials = found(settings.credential_phrases)
    if credentials:
        add(Indicator("PIDE_DATOS_SENSIBLES", 15, "menciona datos sensibles: " + ", ".join(f"'{p}'" for p in credentials[:4]),
                      "un correo legítimo puede recordarte NO compartirlos; lee el contexto"))

    # --- Adjuntos ---
    for attachment in email.attachments:
        exts = _extensions(attachment.filename)
        last = exts[-1] if exts else ""
        if len(exts) >= 2 and last in RISKY_ATTACHMENTS and exts[-2] in DECOY_EXTENSIONS:
            add(Indicator("ADJUNTO_DOBLE_EXTENSION", 35, f"'{attachment.filename}' aparenta '{exts[-2]}' pero es '{last}'",
                          "prácticamente nunca es legítimo"))
        elif last in RISKY_ATTACHMENTS:
            add(Indicator("ADJUNTO_EJECUTABLE", 25, f"'{attachment.filename}' es un tipo que se ejecuta o trae macros",
                          "un área de TI interna podría enviar instaladores; confírmalo por otro medio"))
        elif last in HTML_ATTACHMENTS:
            add(Indicator("ADJUNTO_HTML", 15, f"'{attachment.filename}' es una página web adjunta (suele imitar un inicio de sesión)",
                          "algunos sistemas envían recibos en HTML"))
    return analysis
