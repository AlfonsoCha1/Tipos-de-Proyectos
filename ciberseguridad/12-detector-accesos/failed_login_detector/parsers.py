"""Lectura de registros de login en tres formatos: ``lab``, ``syslog`` y ``csv``.

Copia intencional compartida por los proyectos 09 y 12 (ver
docs/ARQUITECTURA.md en la raíz del repositorio).

Cada línea del archivo termina en una de tres categorías:

* **eventos**: intentos de login interpretados (``LoginEvent``).
* **ignorada**: línea válida pero sin relación con un login (comentarios,
  líneas vacías, mensajes de otros procesos, "session opened", etc.).
* **no interpretada**: la línea parece relevante o no respeta el formato
  esperado. Se reporta con número de línea y motivo, nunca se descarta en
  silencio.

Los registros son entrada NO confiable: pueden traer IPs falsas, fechas
imposibles o conteos exagerados. Por eso todo se valida antes de usarse.
"""

from __future__ import annotations

import csv
import ipaddress
import re
from dataclasses import dataclass, field
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Callable, Iterator, TextIO

from .models import LoginEvent, Outcome, UnparsedLine
from .timeutils import TimestampError, parse_iso_timestamp, to_utc

SUPPORTED_FORMATS = ("lab", "syslog", "csv")

# OpenSSH 9.8+ separó el proceso por sesión en "sshd-session"; las versiones
# anteriores registran todo como "sshd". Se aceptan ambos.
SSH_PROCESSES = frozenset({"sshd", "sshd-session"})

# Límite defensivo para "message repeated N times": un registro manipulado
# podría pedir millones de repeticiones y agotar la memoria.
MAX_REPEAT = 10_000

# Longitud máxima del texto de una línea guardado en los reportes.
MAX_TEXT_LENGTH = 200

REQUIRED_CSV_COLUMNS = ("timestamp", "user", "ip", "result")


class LineParseError(ValueError):
    """Una línea no se pudo interpretar. El mensaje explica el motivo."""


class LogFormatError(ValueError):
    """El archivo completo no se puede procesar (formato desconocido, CSV sin columnas...)."""


@dataclass(frozen=True, slots=True)
class ParseOptions:
    """Opciones que afectan la interpretación de fechas.

    Attributes:
        default_tz: zona horaria que se asume para fechas sin desplazamiento.
        year: año que se asume en syslog tradicional ("Sep 14 08:00:01" no trae año).
    """

    default_tz: tzinfo
    year: int


@dataclass(slots=True)
class LineResult:
    """Resultado de procesar una línea (o una fila de CSV)."""

    line_no: int
    events: list[LoginEvent] = field(default_factory=list)
    error: UnparsedLine | None = None

    @property
    def ignored(self) -> bool:
        """``True`` si la línea no aportó eventos ni errores."""
        return not self.events and self.error is None


# --------------------------------------------------------------------------
# Utilidades comunes
# --------------------------------------------------------------------------

def normalize_ip(raw: str) -> str:
    """Valida una IP y la devuelve en forma canónica.

    Una expresión regular aceptaría ``999.1.1.1``; el módulo ``ipaddress``
    no. Además comprime IPv6 (``2001:0db8::0025`` -> ``2001:db8::25``) y
    convierte IPv4 mapeadas en IPv6 (``::ffff:192.0.2.1``) a su IPv4, para
    que la misma máquina no cuente como dos IPs distintas.

    Raises:
        LineParseError: si ``raw`` no es una IP (por ejemplo, un nombre de host).
    """
    candidate = raw.strip().strip("[]")
    try:
        address = ipaddress.ip_address(candidate)
    except ValueError:
        raise LineParseError(f"IP inválida: {raw!r}") from None
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return str(address.ipv4_mapped)
    return str(address)


def _short(text: str) -> str:
    text = text.rstrip("\r\n")
    return text if len(text) <= MAX_TEXT_LENGTH else text[:MAX_TEXT_LENGTH] + "..."


def _iso_timestamp(text: str, default_tz: tzinfo) -> datetime:
    try:
        return parse_iso_timestamp(text, default_tz)
    except TimestampError as exc:
        raise LineParseError(str(exc)) from None


# --------------------------------------------------------------------------
# Formato "lab" (formato propio y documentado para los datos sintéticos)
#   2026-09-14T08:10:02-06:00 LOGIN_FAILURE user=admin ip=203.0.113.50 method=password
# --------------------------------------------------------------------------

_LAB_RE = re.compile(r"^(?P<ts>\S+)\s+(?P<event>LOGIN_[A-Z_]+)(?P<fields>(?:\s+\S+)*)\s*$")
_LAB_EVENTS = {"LOGIN_SUCCESS": Outcome.SUCCESS, "LOGIN_FAILURE": Outcome.FAILURE}


def _parse_key_values(text: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for token in text.split():
        key, separator, value = token.partition("=")
        if not separator or not key:
            raise LineParseError(f"campo sin formato clave=valor: {token!r}")
        fields[key.lower()] = value
    return fields


def parse_lab_line(text: str, source: str, line_no: int, options: ParseOptions) -> list[LoginEvent]:
    """Interpreta una línea del formato ``lab``.

    Args:
        text: línea completa.
        source: nombre del archivo, para ubicar el evento.
        line_no: número de línea.
        options: zona horaria por defecto.

    Returns:
        Lista con un evento, o lista vacía si la línea es un comentario (``#``)
        o está vacía.

    Raises:
        LineParseError: si la línea no respeta el formato o tiene datos inválidos.
    """
    stripped = text.strip()
    if not stripped or stripped.startswith("#"):
        return []

    match = _LAB_RE.match(stripped)
    if not match:
        raise LineParseError(
            "no sigue el formato lab: '<fecha> LOGIN_SUCCESS|LOGIN_FAILURE user=<u> ip=<ip>'"
        )

    outcome = _LAB_EVENTS.get(match["event"])
    if outcome is None:
        raise LineParseError(
            f"evento desconocido {match['event']!r} (se esperaba LOGIN_SUCCESS o LOGIN_FAILURE)"
        )

    fields = _parse_key_values(match["fields"])
    missing = [name for name in ("user", "ip") if not fields.get(name)]
    if missing:
        raise LineParseError("faltan campos obligatorios: " + ", ".join(f"{name}=" for name in missing))

    return [
        LoginEvent(
            timestamp=_iso_timestamp(match["ts"], options.default_tz),
            user=fields["user"],
            ip=normalize_ip(fields["ip"]),
            outcome=outcome,
            source=source,
            line_no=line_no,
        )
    ]


# --------------------------------------------------------------------------
# Formato "syslog" (auth.log de OpenSSH en Linux)
#   Sep 14 08:20:32 lab-server sshd[2301]: Failed password for invalid user oracle from 198.51.100.23 port 40122 ssh2
#   2026-09-14T08:20:32.000000-06:00 lab-server sshd[2301]: Failed password for ...
# --------------------------------------------------------------------------

_MONTHS = {
    "Jan": 1, "Feb": 2, "Mar": 3, "Apr": 4, "May": 5, "Jun": 6,
    "Jul": 7, "Aug": 8, "Sep": 9, "Oct": 10, "Nov": 11, "Dec": 12,
}

_SYSLOG_TRADITIONAL_RE = re.compile(
    r"^(?P<month>[A-Z][a-z]{2})\s+(?P<day>\d{1,2})\s+(?P<time>\d{2}:\d{2}:\d{2})\s+(?P<host>\S+)\s+(?P<rest>.*)$"
)
_SYSLOG_ISO_RE = re.compile(r"^(?P<ts>\d{4}-\d{2}-\d{2}T\S+)\s+(?P<host>\S+)\s+(?P<rest>.*)$")
_PROCESS_RE = re.compile(r"^(?P<process>[^\s\[:]+)(?:\[(?P<pid>\d+)\])?:\s*(?P<message>.*)$")
_REPEATED_RE = re.compile(r"^message repeated (?P<count>\d+) times: \[\s*(?P<inner>.*?)\s*\]$")

# Solo estas dos frases de OpenSSH representan el RESULTADO de un intento.
# "Invalid user X from IP" es un aviso previo al "Failed password for invalid
# user X"; contarlo produciría intentos duplicados.
_LOGIN_LIKE_RE = re.compile(r"^(?:Accepted|Failed) \S+ for\b")
_ACCEPTED_RE = re.compile(r"^Accepted (?P<method>\S+) for (?P<user>\S+) from (?P<ip>\S+) port \d+")
_FAILED_RE = re.compile(
    r"^Failed (?P<method>\S+) for (?P<invalid>invalid user )?(?P<user>\S*) from (?P<ip>\S+) port \d+"
)


def _syslog_header(text: str, options: ParseOptions) -> tuple[datetime, str]:
    """Separa la fecha del resto de la línea syslog y la convierte a UTC."""
    iso = _SYSLOG_ISO_RE.match(text)
    if iso:
        return _iso_timestamp(iso["ts"], options.default_tz), iso["rest"]

    traditional = _SYSLOG_TRADITIONAL_RE.match(text)
    if not traditional:
        raise LineParseError("no tiene cabecera syslog (fecha, equipo y mensaje)")

    month = _MONTHS.get(traditional["month"])
    if month is None:
        raise LineParseError(f"mes desconocido: {traditional['month']!r}")
    hour, minute, second = (int(part) for part in traditional["time"].split(":"))
    try:
        naive = datetime(options.year, month, int(traditional["day"]), hour, minute, second)
    except ValueError:
        raise LineParseError(
            f"fecha inexistente: {traditional['month']} {traditional['day']} {traditional['time']} "
            f"(año asumido {options.year})"
        ) from None
    return to_utc(naive, options.default_tz), traditional["rest"]


def _ssh_login(message: str) -> tuple[Outcome, str, str, bool] | None:
    """Extrae (resultado, usuario, ip, cuenta_inexistente) de un mensaje de sshd.

    Returns:
        ``None`` si el mensaje no es el resultado de un intento de login.

    Raises:
        LineParseError: si el mensaje empieza como un login pero está incompleto.
    """
    if not _LOGIN_LIKE_RE.match(message):
        return None

    accepted = _ACCEPTED_RE.match(message)
    if accepted:
        return Outcome.SUCCESS, accepted["user"], accepted["ip"], False

    failed = _FAILED_RE.match(message)
    if failed:
        return Outcome.FAILURE, failed["user"] or "(vacío)", failed["ip"], bool(failed["invalid"])

    raise LineParseError("mensaje de login de sshd incompleto o con un formato inesperado")


def parse_syslog_line(text: str, source: str, line_no: int, options: ParseOptions) -> list[LoginEvent]:
    """Interpreta una línea de ``auth.log`` generada por OpenSSH.

    Acepta la cabecera tradicional (``Sep 14 08:00:01``, sin año ni zona) y
    la cabecera ISO 8601 de rsyslog. Expande ``message repeated N times`` en
    N eventos, porque rsyslog resume así fallos idénticos consecutivos.

    Returns:
        Lista de eventos (vacía si la línea no es un resultado de login).

    Raises:
        LineParseError: si la línea no tiene cabecera syslog o el mensaje de
            login está dañado.
    """
    stripped = text.strip()
    if not stripped:
        return []

    timestamp, rest = _syslog_header(stripped, options)

    process = _PROCESS_RE.match(rest)
    if not process or process["process"] not in SSH_PROCESSES:
        return []

    message, repeat = process["message"], 1
    repeated = _REPEATED_RE.match(message)
    if repeated:
        message, repeat = repeated["inner"], int(repeated["count"])
        if not 1 <= repeat <= MAX_REPEAT:
            raise LineParseError(f"conteo de repetición fuera de rango: {repeat} (máximo {MAX_REPEAT})")

    login = _ssh_login(message)
    if login is None:
        return []

    outcome, user, raw_ip, invalid_user = login
    ip = normalize_ip(raw_ip)
    return [
        LoginEvent(timestamp, user, ip, outcome, source, line_no, invalid_user)
        for _ in range(repeat)
    ]


# --------------------------------------------------------------------------
# Formato "csv"
#   timestamp,user,ip,result[,otras columnas que se ignoran]
# --------------------------------------------------------------------------

_CSV_RESULTS = {"success": Outcome.SUCCESS, "failure": Outcome.FAILURE}


def _csv_event(values: dict[str, str], source: str, line_no: int, options: ParseOptions) -> LoginEvent:
    missing = [column for column in REQUIRED_CSV_COLUMNS if not values[column]]
    if missing:
        raise LineParseError("columnas vacías: " + ", ".join(missing))

    outcome = _CSV_RESULTS.get(values["result"].lower())
    if outcome is None:
        raise LineParseError(f"resultado desconocido {values['result']!r} (se esperaba success o failure)")

    return LoginEvent(
        timestamp=_iso_timestamp(values["timestamp"], options.default_tz),
        user=values["user"],
        ip=normalize_ip(values["ip"]),
        outcome=outcome,
        source=source,
        line_no=line_no,
    )


def _iter_csv(handle: TextIO, source: str, options: ParseOptions) -> Iterator[LineResult]:
    reader = csv.DictReader(handle)
    if reader.fieldnames is None:
        raise LogFormatError(f"{source}: el CSV está vacío o no tiene encabezado")

    # Se aceptan encabezados con mayúsculas o espacios ("User ", "IP").
    columns = {name.strip().lower(): name for name in reader.fieldnames if name}
    missing = [column for column in REQUIRED_CSV_COLUMNS if column not in columns]
    if missing:
        raise LogFormatError(
            f"{source}: faltan columnas obligatorias en el CSV: {', '.join(missing)} "
            f"(se requieren: {', '.join(REQUIRED_CSV_COLUMNS)})"
        )

    for row in reader:
        # line_num es la línea física, incluso si un campo entre comillas ocupa varias.
        line_no = reader.line_num
        values = {column: (row.get(columns[column]) or "").strip() for column in REQUIRED_CSV_COLUMNS}
        try:
            event = _csv_event(values, source, line_no, options)
        except LineParseError as exc:
            raw = ",".join(value for value in row.values() if isinstance(value, str))
            yield LineResult(line_no, error=UnparsedLine(source, line_no, str(exc), _short(raw)))
            continue
        yield LineResult(line_no, events=[event])


# --------------------------------------------------------------------------
# Detección de formato y lectura de archivos completos
# --------------------------------------------------------------------------

_LINE_PARSERS: dict[str, Callable[[str, str, int, ParseOptions], list[LoginEvent]]] = {
    "lab": parse_lab_line,
    "syslog": parse_syslog_line,
}


def _open_text(path: Path, for_csv: bool = False) -> TextIO:
    # utf-8-sig elimina el BOM que agregan algunos editores de Windows.
    # errors="replace" evita que un byte inválido detenga todo el análisis.
    return path.open("r", encoding="utf-8-sig", errors="replace", newline="" if for_csv else None)


def detect_format(path: Path, max_lines: int = 50) -> str:
    """Adivina el formato de un archivo de registro.

    Usa la extensión ``.csv`` o examina las primeras líneas con contenido.

    Returns:
        ``"lab"``, ``"syslog"`` o ``"csv"``.

    Raises:
        LogFormatError: si ninguna de las primeras líneas coincide con un
            formato conocido.
    """
    if path.suffix.lower() == ".csv":
        return "csv"

    with _open_text(path) as handle:
        for _, raw in zip(range(max_lines), handle):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            # El formato lab se prueba primero: una línea lab también
            # parecería syslog ISO ("fecha equipo mensaje").
            if _LAB_RE.match(line):
                return "lab"
            if _SYSLOG_ISO_RE.match(line) or _SYSLOG_TRADITIONAL_RE.match(line):
                return "syslog"

    raise LogFormatError(
        f"No se reconoce el formato de {path} (o está vacío). Indica --format lab, syslog o csv."
    )


def read_log(path: Path, fmt: str, options: ParseOptions) -> Iterator[LineResult]:
    """Lee un archivo línea por línea y produce un ``LineResult`` por línea.

    Es un generador: nunca carga el archivo completo en memoria, así que
    funciona con registros de varios GB.

    Args:
        path: archivo a leer.
        fmt: uno de ``SUPPORTED_FORMATS``.
        options: opciones de fechas.

    Raises:
        LogFormatError: si el formato no existe o el CSV no tiene las columnas necesarias.
        OSError: si el archivo no se puede abrir (permisos, no existe...).
    """
    if fmt not in SUPPORTED_FORMATS:
        raise LogFormatError(f"Formato no soportado: {fmt!r}. Opciones: {', '.join(SUPPORTED_FORMATS)}")

    source = str(path)
    with _open_text(path, for_csv=fmt == "csv") as handle:
        if fmt == "csv":
            yield from _iter_csv(handle, source, options)
            return

        parse_line = _LINE_PARSERS[fmt]
        for line_no, raw in enumerate(handle, start=1):
            try:
                events = parse_line(raw, source, line_no, options)
            except LineParseError as exc:
                yield LineResult(line_no, error=UnparsedLine(source, line_no, str(exc), _short(raw)))
                continue
            yield LineResult(line_no, events=events)
