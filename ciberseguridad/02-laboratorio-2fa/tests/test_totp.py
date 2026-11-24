"""Pruebas del algoritmo (totp.py), incluidos los vectores oficiales de RFC 4226 y RFC 6238."""

from __future__ import annotations

import base64
from urllib.parse import parse_qs, urlsplit

import pytest

from totp_lab.totp import (
    RFC6238_KEYS,
    RFC6238_VECTORS,
    SecretError,
    TotpConfig,
    counter_at,
    decode_secret,
    explain,
    generate_secret,
    hotp,
    provisioning_uri,
    seconds_remaining,
    totp,
    verify,
)

RFC_KEY = b"12345678901234567890"
NOW = 1_795_536_000  # 2026-11-24 16:00:00 UTC


# RFC 4226, apéndice D: HOTP con el mismo secreto, contadores 0 a 9.
@pytest.mark.parametrize(
    "counter, code",
    list(enumerate(["755224", "287082", "359152", "969429", "338314", "254676", "287922", "162583", "399871", "520489"])),
)
def test_rfc4226_hotp_vectors(counter, code):
    assert hotp(RFC_KEY, counter) == code


@pytest.mark.parametrize("timestamp, algorithm, code", RFC6238_VECTORS)
def test_rfc6238_totp_vectors(timestamp, algorithm, code):
    assert totp(RFC6238_KEYS[algorithm], timestamp, TotpConfig(digits=8, algorithm=algorithm)) == code


def test_generate_secret_is_random_base32_of_160_bits():
    a, b = generate_secret(), generate_secret()
    assert a != b
    assert len(decode_secret(a)) == 20
    with pytest.raises(SecretError):
        generate_secret(8)


def test_decode_secret_accepts_spaces_lowercase_and_padding():
    pretty = "gezd gnbv gy3t qojq gezd gnbv gy3t qojq"
    assert decode_secret(pretty) == RFC_KEY
    assert decode_secret("GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ====") == RFC_KEY


@pytest.mark.parametrize("bad", ["", "   ", "ABC1!", "GEZDGNBV"])
def test_decode_secret_rejects_invalid_or_short(bad):
    with pytest.raises(SecretError):
        decode_secret(bad)


def test_counter_and_remaining_seconds():
    config = TotpConfig()
    assert counter_at(NOW, config) == NOW // 30
    assert seconds_remaining(NOW, config) == 30
    assert seconds_remaining(NOW + 29, config) == 1


def test_verify_current_and_window():
    code = totp(RFC_KEY, NOW)
    assert verify(RFC_KEY, code, NOW).offset == 0
    assert verify(RFC_KEY, code, NOW + 30).offset == -1  # el reloj del teléfono va 30 s atrasado
    assert not verify(RFC_KEY, code, NOW + 30, window=0).valid
    assert not verify(RFC_KEY, code, NOW + 90).valid


def test_verify_rejects_reuse_with_last_counter():
    code = totp(RFC_KEY, NOW)
    first = verify(RFC_KEY, code, NOW)
    again = verify(RFC_KEY, code, NOW + 5, last_counter=first.counter)
    assert first.valid and not again.valid
    assert "repetición" in again.reason


@pytest.mark.parametrize("bad", ["12345", "1234567", "12a456", ""])
def test_verify_format(bad):
    assert "dígitos" in verify(RFC_KEY, bad, NOW).reason


def test_verify_accepts_spaces_inside_code():
    code = totp(RFC_KEY, NOW)
    assert verify(RFC_KEY, f"{code[:3]} {code[3:]}", NOW).valid


def test_config_validation():
    with pytest.raises(ValueError):
        TotpConfig(digits=5)
    with pytest.raises(ValueError):
        TotpConfig(period=0)
    with pytest.raises(ValueError):
        TotpConfig(algorithm="MD5")


def test_explain_matches_totp():
    steps = explain(RFC_KEY, NOW)
    assert steps["code"] == totp(RFC_KEY, NOW)
    assert steps["counter_bytes"] == (NOW // 30).to_bytes(8, "big").hex()
    assert 0 <= steps["offset"] <= 15


def test_provisioning_uri():
    secret = base64.b32encode(RFC_KEY).decode()
    uri = provisioning_uri(secret, "ana@empresa.example", "Laboratorio 2FA")
    parts = urlsplit(uri)
    assert parts.scheme == "otpauth" and parts.netloc == "totp"
    assert parts.path == "/Laboratorio%202FA:ana@empresa.example"
    query = parse_qs(parts.query)
    assert query["secret"] == [secret] and query["digits"] == ["6"] and query["issuer"] == ["Laboratorio 2FA"]
