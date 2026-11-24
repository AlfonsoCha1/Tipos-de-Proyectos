"""Algoritmos HOTP (RFC 4226) y TOTP (RFC 6238) con la biblioteca estándar.

Así funcionan las apps de autenticación (Google Authenticator, Microsoft
Authenticator, Authy...): el servidor y el teléfono comparten un **secreto** y
ambos calculan el mismo código a partir de la **hora**. No viaja nada por la
red: por eso el código funciona sin internet.

1. ``T = (segundos desde 1970 - T0) // periodo``           (contador de 30 s)
2. ``HMAC = HMAC-SHA1(secreto, T como 8 bytes big-endian)``
3. Truncamiento dinámico: los 4 bits finales del HMAC dicen desde qué byte
   tomar 4 bytes; se quita el bit de signo.
4. ``código = ese entero mod 10^dígitos``, con ceros a la izquierda.

Se implementa aquí para entenderlo y se valida contra los vectores oficiales del
RFC 6238 (``rfc-test``). En producción se usa una biblioteca mantenida, pero
estas mismas pruebas sirven para verificarla.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
import struct
from dataclasses import dataclass
from urllib.parse import quote, urlencode

ALGORITHMS = {"SHA1": hashlib.sha1, "SHA256": hashlib.sha256, "SHA512": hashlib.sha512}
DEFAULT_PERIOD = 30
DEFAULT_DIGITS = 6


class SecretError(ValueError):
    """El secreto no es Base32 válido o es demasiado corto."""


@dataclass(frozen=True)
class TotpConfig:
    digits: int = DEFAULT_DIGITS
    period: int = DEFAULT_PERIOD
    algorithm: str = "SHA1"
    t0: int = 0

    def __post_init__(self) -> None:
        if self.digits not in (6, 7, 8):
            raise ValueError("los dígitos deben ser 6, 7 u 8")
        if not 1 <= self.period <= 300:
            raise ValueError("el periodo debe estar entre 1 y 300 segundos")
        if self.algorithm not in ALGORITHMS:
            raise ValueError(f"algoritmo no soportado: {self.algorithm} (usa {', '.join(ALGORITHMS)})")


@dataclass(frozen=True)
class VerifyResult:
    valid: bool
    reason: str
    counter: int | None = None
    offset: int | None = None  # -1 = código del periodo anterior, 0 = actual, +1 = siguiente


def generate_secret(num_bytes: int = 20) -> str:
    """Secreto aleatorio en Base32 sin relleno. 20 bytes = 160 bits, lo que recomienda RFC 4226."""
    if num_bytes < 16:
        raise SecretError("usa al menos 16 bytes (128 bits) de secreto")
    return base64.b32encode(secrets.token_bytes(num_bytes)).decode("ascii").rstrip("=")


def decode_secret(secret_b32: str) -> bytes:
    """Convierte Base32 (como lo muestran las apps, con espacios y en minúsculas) a bytes."""
    cleaned = "".join(secret_b32.split()).replace("-", "").upper().rstrip("=")
    if not cleaned:
        raise SecretError("el secreto está vacío")
    padded = cleaned + "=" * (-len(cleaned) % 8)
    try:
        key = base64.b32decode(padded, casefold=False)
    except (binascii.Error, ValueError) as exc:
        raise SecretError("el secreto no es Base32 válido (solo letras A-Z y números 2-7)") from exc
    if len(key) < 10:
        raise SecretError(f"el secreto es demasiado corto ({len(key) * 8} bits); el mínimo razonable es 80")
    return key


def hotp(key: bytes, counter: int, digits: int = DEFAULT_DIGITS, algorithm: str = "SHA1") -> str:
    """Código HOTP para un contador (RFC 4226, sección 5.3)."""
    digest = hmac.new(key, struct.pack(">Q", counter), ALGORITHMS[algorithm]).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(binary % 10**digits).zfill(digits)


def counter_at(timestamp: float, config: TotpConfig = TotpConfig()) -> int:
    return int((int(timestamp) - config.t0) // config.period)


def totp(key: bytes, timestamp: float, config: TotpConfig = TotpConfig()) -> str:
    return hotp(key, counter_at(timestamp, config), config.digits, config.algorithm)


def seconds_remaining(timestamp: float, config: TotpConfig = TotpConfig()) -> int:
    return config.period - int((int(timestamp) - config.t0) % config.period)


def verify(
    key: bytes,
    code: str,
    timestamp: float,
    config: TotpConfig = TotpConfig(),
    window: int = 1,
    last_counter: int | None = None,
) -> VerifyResult:
    """Verifica un código aceptando ``window`` periodos antes y después (relojes desfasados).

    Con ``last_counter`` (el contador del último código aceptado para esa cuenta)
    se rechaza la reutilización: un código robado no sirve dos veces.
    """
    code = code.strip().replace(" ", "")
    if not code.isdigit() or len(code) != config.digits:
        return VerifyResult(False, f"el código debe tener exactamente {config.digits} dígitos")
    if not 0 <= window <= 10:
        raise ValueError("la ventana debe estar entre 0 y 10 periodos")
    current = counter_at(timestamp, config)
    match = None
    # Se recorren todas las posiciones aunque haya coincidencia temprana y se usa
    # compare_digest, para no revelar por el tiempo de respuesta qué tan cerca estuvo.
    for offset in range(-window, window + 1):
        candidate = hotp(key, current + offset, config.digits, config.algorithm)
        if hmac.compare_digest(candidate, code) and match is None:
            match = offset
    if match is None:
        return VerifyResult(False, "el código no coincide con ningún periodo de la ventana")
    counter = current + match
    if last_counter is not None and counter <= last_counter:
        return VerifyResult(False, "código ya usado (o anterior al último aceptado): posible repetición", counter, match)
    return VerifyResult(True, "código válido", counter, match)


def explain(key: bytes, timestamp: float, config: TotpConfig = TotpConfig()) -> dict[str, str | int]:
    """Cada paso del cálculo, para mostrarlo en la terminal."""
    counter = counter_at(timestamp, config)
    message = struct.pack(">Q", counter)
    digest = hmac.new(key, message, ALGORITHMS[config.algorithm]).digest()
    offset = digest[-1] & 0x0F
    chunk = digest[offset : offset + 4]
    binary = struct.unpack(">I", chunk)[0] & 0x7FFFFFFF
    return {
        "timestamp": int(timestamp),
        "counter": counter,
        "counter_bytes": message.hex(),
        "hmac": digest.hex(),
        "offset": offset,
        "chunk": chunk.hex(),
        "binary": binary,
        "code": str(binary % 10**config.digits).zfill(config.digits),
    }


def provisioning_uri(secret_b32: str, account: str, issuer: str, config: TotpConfig = TotpConfig()) -> str:
    """URI ``otpauth://`` que codifican los códigos QR de alta (formato de Google Authenticator)."""
    label = quote(f"{issuer}:{account}", safe="@:")
    params = {
        "secret": "".join(secret_b32.split()).upper().rstrip("="),
        "issuer": issuer,
        "algorithm": config.algorithm,
        "digits": config.digits,
        "period": config.period,
    }
    return f"otpauth://totp/{label}?{urlencode(params, quote_via=quote)}"


# Vectores de prueba del RFC 6238, apéndice B (8 dígitos, periodo de 30 s).
RFC6238_KEYS = {
    "SHA1": b"12345678901234567890",
    "SHA256": b"12345678901234567890123456789012",
    "SHA512": b"1234567890123456789012345678901234567890123456789012345678901234",
}
RFC6238_VECTORS = (
    (59, "SHA1", "94287082"), (59, "SHA256", "46119246"), (59, "SHA512", "90693936"),
    (1111111109, "SHA1", "07081804"), (1111111109, "SHA256", "68084774"), (1111111109, "SHA512", "25091201"),
    (1111111111, "SHA1", "14050471"), (1111111111, "SHA256", "67062674"), (1111111111, "SHA512", "99943326"),
    (1234567890, "SHA1", "89005924"), (1234567890, "SHA256", "91819424"), (1234567890, "SHA512", "93441116"),
    (2000000000, "SHA1", "69279037"), (2000000000, "SHA256", "90698825"), (2000000000, "SHA512", "38618901"),
    (20000000000, "SHA1", "65353130"), (20000000000, "SHA256", "77737706"), (20000000000, "SHA512", "47863826"),
)


def run_rfc_vectors() -> list[tuple[int, str, str, str, bool]]:
    """(tiempo, algoritmo, esperado, obtenido, ¿coincide?) para cada vector oficial."""
    results = []
    for timestamp, algorithm, expected in RFC6238_VECTORS:
        got = totp(RFC6238_KEYS[algorithm], timestamp, TotpConfig(digits=8, algorithm=algorithm))
        results.append((timestamp, algorithm, expected, got, got == expected))
    return results
