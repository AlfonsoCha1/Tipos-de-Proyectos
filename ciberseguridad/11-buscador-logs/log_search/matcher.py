"""Lógica de búsqueda: criterios, lectura incremental y líneas de contexto.

Este módulo no imprime ni lee la terminal: recibe archivos y criterios y
devuelve resultados, así se puede probar sin interfaz.

Cómo se combinan los criterios (documentado también en el README):

* Palabras: coincide si la línea contiene **alguna** (por defecto) o **todas**
  (``match_all``).
* IPs y rangos: coincide si la línea contiene **alguna** IP que sea igual a una
  de ``--ip`` **o** esté dentro de uno de los rangos ``--cidr``.
* Fechas: coincide si la fecha al inicio de la línea está entre ``--from`` y
  ``--to`` (ambos inclusivos).
* Entre tipos de criterio (palabras, IPs, fechas) se exige que se cumplan
  **todos** los que se hayan indicado.
"""

from __future__ import annotations

import ipaddress
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone, tzinfo
from pathlib import Path
from typing import Iterator

from .timeutils import TimestampError, parse_iso_timestamp, to_utc

MAX_LINE_CHARS = 10_000      # las líneas más largas se recortan (defensa contra archivos hostiles)
MAX_KEYWORDS = 20
MAX_KEYWORD_CHARS = 200
MAX_CONTEXT = 20
MAX_MATCHES_LIMIT = 10_000
DEFAULT_MAX_MATCHES = 200

IPNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network


class QueryError(ValueError):
    """Los criterios de búsqueda no son válidos."""


# --------------------------------------------------------------------------
# Criterios
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Query:
    """Criterios de búsqueda ya validados. Las fechas están en UTC."""

    keywords: tuple[str, ...] = ()
    match_all: bool = False
    case_sensitive: bool = False
    ips: frozenset[str] = frozenset()
    networks: tuple[IPNetwork, ...] = ()
    start: datetime | None = None
    end: datetime | None = None

    @property
    def has_ip_filter(self) -> bool:
        return bool(self.ips or self.networks)

    @property
    def has_date_filter(self) -> bool:
        return self.start is not None or self.end is not None


def normalize_ip(text: str) -> str:
    """Devuelve la IP en forma canónica (IPv6 comprimida, IPv4 mapeada → IPv4).

    Raises:
        ValueError: si ``text`` no es una IP válida.
    """
    address = ipaddress.ip_address(text.strip())
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        address = address.ipv4_mapped
    return str(address)


def parse_date_bound(text: str, tz: tzinfo, *, is_end: bool) -> datetime:
    """Interpreta ``--from`` / ``--to`` y devuelve un instante en UTC.

    Acepta ``2026-09-14`` (todo el día) o una fecha-hora ISO 8601. Con solo la
    fecha, el inicio es las 00:00:00 y el final las 23:59:59.999999 de ese día.

    Raises:
        QueryError: si el texto no es una fecha válida.
    """
    value = text.strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            day = date.fromisoformat(value)
        except ValueError as exc:
            raise QueryError(f"fecha inexistente: {text!r}") from exc
        moment = datetime.combine(day, time.max if is_end else time.min)
        return to_utc(moment, tz)
    try:
        return parse_iso_timestamp(value, tz)
    except TimestampError as exc:
        raise QueryError(f"{exc}. Usa AAAA-MM-DD o AAAA-MM-DDTHH:MM:SS") from exc


def build_query(
    keywords: list[str] | None = None,
    *,
    match_all: bool = False,
    case_sensitive: bool = False,
    ips: list[str] | None = None,
    cidrs: list[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    tz: tzinfo = timezone.utc,
) -> Query:
    """Valida lo que escribió la persona y arma una ``Query``.

    Raises:
        QueryError: ante cualquier criterio inválido o si no hay ninguno.
    """
    words = list(keywords or [])
    if len(words) > MAX_KEYWORDS:
        raise QueryError(f"Demasiadas palabras: máximo {MAX_KEYWORDS}.")
    for word in words:
        if not word.strip():
            raise QueryError("Una palabra de búsqueda está vacía.")
        if len(word) > MAX_KEYWORD_CHARS:
            raise QueryError(f"Palabra demasiado larga (máximo {MAX_KEYWORD_CHARS} caracteres).")
    if not case_sensitive:
        words = [word.casefold() for word in words]

    exact: set[str] = set()
    for raw in ips or []:
        try:
            exact.add(normalize_ip(raw))
        except ValueError as exc:
            raise QueryError(f"IP no válida: {raw!r}") from exc

    networks: list[IPNetwork] = []
    for raw in cidrs or []:
        try:
            # strict=False acepta 192.0.2.10/24 y lo normaliza a 192.0.2.0/24.
            networks.append(ipaddress.ip_network(raw.strip(), strict=False))
        except ValueError as exc:
            raise QueryError(f"Rango no válido: {raw!r}. Ejemplo: 192.0.2.0/24") from exc

    start_utc = parse_date_bound(start, tz, is_end=False) if start else None
    end_utc = parse_date_bound(end, tz, is_end=True) if end else None
    if start_utc and end_utc and start_utc > end_utc:
        raise QueryError("--from es posterior a --to.")

    if not (words or exact or networks or start_utc or end_utc):
        raise QueryError("Indica al menos un criterio: -k, --ip, --cidr, --from o --to.")

    return Query(
        keywords=tuple(words),
        match_all=match_all,
        case_sensitive=case_sensitive,
        ips=frozenset(exact),
        networks=tuple(networks),
        start=start_utc,
        end=end_utc,
    )


# --------------------------------------------------------------------------
# Extracción de IPs y fechas de una línea
# --------------------------------------------------------------------------

_IP_TOKEN_RE = re.compile(r"[0-9A-Fa-f:.]{3,45}")
_ISO_START_RE = re.compile(
    r"^\s*(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|[+-]\d{2}:\d{2})?)",
    re.IGNORECASE,
)
_SYSLOG_START_RE = re.compile(r"^([A-Z][a-z]{2})\s+(\d{1,2})\s+(\d{2}:\d{2}:\d{2})\b")
_MONTHS = {name: number for number, name in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), start=1)}


def find_ips(text: str) -> list[str]:
    """Devuelve las IPs válidas (normalizadas) que aparecen en la línea.

    Se buscan trozos hechos solo de dígitos hexadecimales, ``:`` y ``.`` y se
    comprueba cada uno con ``ipaddress``; lo que no es una IP (``08:10:02``,
    ``2026-09-14``) simplemente se descarta.
    """
    found: list[str] = []
    for token in _IP_TOKEN_RE.findall(text):
        token = token.strip(".:")
        if not token:
            continue
        try:
            found.append(normalize_ip(token))
        except ValueError:
            continue
    return found


def extract_timestamp(text: str, default_tz: tzinfo, year: int) -> datetime | None:
    """Lee la fecha del inicio de la línea (UTC) o devuelve ``None``.

    Formatos: ISO 8601 (``2026-09-14T08:10:02-06:00``) y syslog tradicional
    (``Sep 14 08:10:02``, que no trae año: se usa ``year``).
    """
    iso = _ISO_START_RE.match(text)
    if iso:
        try:
            return parse_iso_timestamp(iso.group(1), default_tz)
        except TimestampError:
            return None
    syslog = _SYSLOG_START_RE.match(text)
    if syslog and syslog.group(1) in _MONTHS:
        hour, minute, second = (int(part) for part in syslog.group(3).split(":"))
        try:
            naive = datetime(year, _MONTHS[syslog.group(1)], int(syslog.group(2)), hour, minute, second)
        except ValueError:
            return None
        return to_utc(naive, default_tz)
    return None


# --------------------------------------------------------------------------
# Evaluación de una línea
# --------------------------------------------------------------------------

def line_matches(text: str, query: Query, default_tz: tzinfo, year: int) -> tuple[bool, bool]:
    """Decide si una línea cumple la consulta.

    Returns:
        ``(coincide, sin_fecha)``. ``sin_fecha`` es ``True`` cuando hay filtro
        de fechas y la línea no empieza con una fecha reconocible (se excluye).
    """
    if query.keywords:
        haystack = text if query.case_sensitive else text.casefold()
        hits = [word in haystack for word in query.keywords]
        if not (all(hits) if query.match_all else any(hits)):
            return False, False

    if query.has_ip_filter:
        if not any(_ip_selected(ip, query) for ip in find_ips(text)):
            return False, False

    if query.has_date_filter:
        moment = extract_timestamp(text, default_tz, year)
        if moment is None:
            return False, True
        if query.start is not None and moment < query.start:
            return False, False
        if query.end is not None and moment > query.end:
            return False, False

    return True, False


def _ip_selected(ip: str, query: Query) -> bool:
    if ip in query.ips:
        return True
    address = ipaddress.ip_address(ip)
    return any(address.version == net.version and address in net for net in query.networks)


# --------------------------------------------------------------------------
# Lectura incremental y búsqueda con contexto
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Entry:
    """Una línea mostrada: coincidencia o contexto."""

    line_no: int
    text: str
    is_match: bool


@dataclass
class FileResult:
    """Resultado de buscar en un archivo."""

    source: str
    lines_read: int = 0
    matches: int = 0
    undated: int = 0           # líneas sin fecha excluidas por el filtro de fechas
    truncated_lines: int = 0   # líneas recortadas por ser demasiado largas
    stopped_early: bool = False  # se alcanzó --max-matches
    entries: list[Entry] = field(default_factory=list)


def read_lines(path: Path) -> Iterator[tuple[int, str, bool]]:
    """Lee un archivo línea por línea sin cargarlo completo en memoria.

    Yields:
        ``(número de línea, texto sin salto de línea, fue_recortada)``. Una
        línea de más de ``MAX_LINE_CHARS`` caracteres se recorta. El archivo
        se decodifica como UTF-8 (con o sin BOM); los bytes inválidos se
        sustituyen por ``�`` en vez de fallar.
    """
    with path.open("r", encoding="utf-8-sig", errors="replace", newline=None) as handle:
        number = 0
        while True:
            chunk = handle.readline(MAX_LINE_CHARS + 1)
            if chunk == "":
                return
            number += 1
            truncated = False
            if len(chunk) > MAX_LINE_CHARS and not chunk.endswith("\n"):
                truncated = True
                chunk = chunk[:MAX_LINE_CHARS]
                # Descarta el resto de la línea sin acumularlo.
                while True:
                    rest = handle.readline(65536)
                    if rest == "" or rest.endswith("\n"):
                        break
            yield number, chunk.rstrip("\n"), truncated


def search_file(
    path: Path,
    query: Query,
    *,
    source: str | None = None,
    context: int = 0,
    max_matches: int = DEFAULT_MAX_MATCHES,
    default_tz: tzinfo = timezone.utc,
    year: int | None = None,
) -> FileResult:
    """Busca en un archivo y devuelve coincidencias con su contexto.

    Memoria: solo se guardan las coincidencias (hasta ``max_matches``) y sus
    líneas de contexto; el resto del archivo se descarta a medida que se lee.

    Raises:
        OSError: si el archivo no se puede abrir.
    """
    if not 0 <= context <= MAX_CONTEXT:
        raise QueryError(f"El contexto debe estar entre 0 y {MAX_CONTEXT}.")
    if not 1 <= max_matches <= MAX_MATCHES_LIMIT:
        raise QueryError(f"--max-matches debe estar entre 1 y {MAX_MATCHES_LIMIT}.")

    use_year = year if year is not None else datetime.now(timezone.utc).year
    result = FileResult(source=source if source is not None else str(path))
    before: deque[Entry] = deque(maxlen=context) if context else deque(maxlen=0)
    after_left = 0

    for number, text, was_truncated in read_lines(path):
        result.lines_read += 1
        if was_truncated:
            result.truncated_lines += 1
        matched, undated = line_matches(text, query, default_tz, use_year)
        if undated:
            result.undated += 1

        if matched:
            if result.matches >= max_matches:
                result.stopped_early = True
                break
            result.entries.extend(before)
            before.clear()
            result.entries.append(Entry(number, text, True))
            result.matches += 1
            after_left = context
        elif after_left > 0:
            result.entries.append(Entry(number, text, False))
            after_left -= 1
        else:
            before.append(Entry(number, text, False))

    return result

