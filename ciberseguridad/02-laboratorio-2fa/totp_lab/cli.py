"""Interfaz de línea de comandos del laboratorio TOTP.

Subcomandos: ``secret``, ``code``, ``verify``, ``explain``, ``uri`` y ``rfc-test``.

El secreto se lee, en este orden, de ``--secret-file``, de la variable de
entorno ``TOTP_SECRET`` o de ``--secret`` (este último queda en el historial de
la terminal, por eso se muestra un aviso).

Códigos de salida: 0 = correcto (en ``verify``: código válido), 1 = error de
entrada, 2 = argumentos inválidos, 3 = código rechazado o vector RFC fallido.
"""

from __future__ import annotations

import argparse
import os
import stat
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from . import __version__
from .totp import (
    ALGORITHMS,
    SecretError,
    TotpConfig,
    counter_at,
    decode_secret,
    explain,
    generate_secret,
    provisioning_uri,
    run_rfc_vectors,
    seconds_remaining,
    totp,
    verify,
)

ENV_VAR = "TOTP_SECRET"


class InputError(Exception):
    """Entrada inválida: secreto faltante, fecha mal escrita, archivo existente..."""


def _add_common(sub: argparse.ArgumentParser, needs_secret: bool = True) -> None:
    if needs_secret:
        sub.add_argument("--secret-file", type=Path, metavar="TXT", help="archivo con el secreto Base32 (recomendado)")
        sub.add_argument("--secret", metavar="BASE32", help=f"secreto en la línea de comandos (mejor usa --secret-file o {ENV_VAR})")
    sub.add_argument("--digits", type=int, default=6, choices=(6, 7, 8), help="dígitos del código (por defecto 6)")
    sub.add_argument("--period", type=int, default=30, metavar="SEG", help="duración de cada código (por defecto 30)")
    sub.add_argument("--algorithm", default="SHA1", choices=tuple(ALGORITHMS), help="por defecto SHA1, como las apps comunes")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m totp_lab",
        description="Laboratorio de códigos 2FA (TOTP, RFC 6238): genera, verifica y explica códigos de un solo uso.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subs = parser.add_subparsers(dest="command", required=True, metavar="COMANDO")

    s = subs.add_parser("secret", help="genera un secreto nuevo")
    s.add_argument("--bytes", type=int, default=20, help="tamaño del secreto en bytes (mínimo 16; por defecto 20)")
    s.add_argument("--save", type=Path, metavar="RUTA", help="guarda el secreto en un archivo (sin sobrescribir)")
    s.add_argument("--force", action="store_true", help="permite sobrescribir --save")

    c = subs.add_parser("code", help="muestra el código actual (o el de --at)")
    _add_common(c)
    c.add_argument("--at", metavar="FECHA", help="fecha ISO 8601 o segundos Unix; por defecto ahora")

    v = subs.add_parser("verify", help="verifica un código")
    v.add_argument("code", metavar="CÓDIGO")
    _add_common(v)
    v.add_argument("--at", metavar="FECHA", help="fecha ISO 8601 o segundos Unix; por defecto ahora")
    v.add_argument("--window", type=int, default=1, help="periodos aceptados antes y después (por defecto 1)")
    v.add_argument("--last-counter", type=int, metavar="N", help="contador del último código aceptado (rechaza repeticiones)")

    e = subs.add_parser("explain", help="muestra cada paso del cálculo")
    _add_common(e)
    e.add_argument("--at", metavar="FECHA", help="fecha ISO 8601 o segundos Unix; por defecto ahora")

    u = subs.add_parser("uri", help="URI otpauth:// para registrar el secreto en una app")
    _add_common(u)
    u.add_argument("--account", required=True, help="cuenta, p. ej. ana@empresa.example")
    u.add_argument("--issuer", required=True, help="servicio, p. ej. 'Laboratorio'")

    subs.add_parser("rfc-test", help="comprueba la implementación con los vectores oficiales del RFC 6238")
    return parser


def parse_time(text: str | None) -> float:
    """``None`` = ahora; un número = segundos Unix; si no, fecha ISO 8601 (sin zona = UTC)."""
    if text is None:
        return time.time()
    try:
        return float(text)
    except ValueError:
        pass
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise InputError(f"fecha inválida: {text!r} (usa 2026-11-24T10:00:00-06:00 o segundos Unix)") from exc
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def read_secret_text(args: argparse.Namespace) -> str:
    """Texto Base32 del secreto según la prioridad documentada."""
    if args.secret_file is not None:
        try:
            lines = args.secret_file.read_text(encoding="utf-8-sig").splitlines()
        except OSError as exc:
            raise InputError(f"no se pudo leer {args.secret_file}: {exc.strerror or exc}") from exc
        return next((line.strip() for line in lines if line.strip() and not line.lstrip().startswith("#")), "")
    if os.environ.get(ENV_VAR):
        return os.environ[ENV_VAR]
    if args.secret:
        print(f"Aviso: el secreto quedó en el historial de la terminal; usa --secret-file o {ENV_VAR}.", file=sys.stderr)
        return args.secret
    raise InputError(f"falta el secreto: usa --secret-file, la variable {ENV_VAR} o --secret")


def read_secret(args: argparse.Namespace) -> bytes:
    return decode_secret(read_secret_text(args))


def _config(args: argparse.Namespace) -> TotpConfig:
    try:
        return TotpConfig(digits=args.digits, period=args.period, algorithm=args.algorithm)
    except ValueError as exc:
        raise InputError(str(exc)) from exc


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(int(timestamp), tz=timezone.utc).isoformat()


def cmd_secret(args: argparse.Namespace) -> int:
    secret = generate_secret(args.bytes)
    if args.save is not None:
        if args.save.exists() and not args.force:
            raise InputError(f"{args.save} ya existe. Usa --force para sobrescribirlo.")
        args.save.parent.mkdir(parents=True, exist_ok=True)
        args.save.write_text(secret + "\n", encoding="utf-8")
        if os.name != "nt":
            args.save.chmod(stat.S_IRUSR | stat.S_IWUSR)  # solo tu usuario puede leerlo
        print(f"Secreto guardado en {args.save} (no lo subas a Git; .gitignore ignora *.secret y secrets/).")
    else:
        print(secret)
    print("Trátalo como una contraseña: quien lo tenga puede generar tus códigos.", file=sys.stderr)
    return 0


def cmd_code(args: argparse.Namespace) -> int:
    key, config, moment = read_secret(args), _config(args), parse_time(args.at)
    print(f"Código: {totp(key, moment, config)}")
    print(f"Válido por: {seconds_remaining(moment, config)} s más | contador T = {counter_at(moment, config)} | hora UTC: {_iso(moment)}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    key, config, moment = read_secret(args), _config(args), parse_time(args.at)
    try:
        result = verify(key, args.code, moment, config, args.window, args.last_counter)
    except ValueError as exc:
        raise InputError(str(exc)) from exc
    if result.valid:
        when = {-1: "del periodo anterior", 0: "del periodo actual", 1: "del periodo siguiente"}.get(
            result.offset or 0, f"de {result.offset:+d} periodos")
        print(f"VÁLIDO: {result.reason} ({when}; contador T = {result.counter}).")
        print(f"Guarda el contador {result.counter} y pásalo como --last-counter para rechazar que se repita.")
        return 0
    print(f"RECHAZADO: {result.reason}.")
    return 3


def cmd_explain(args: argparse.Namespace) -> int:
    key, config, moment = read_secret(args), _config(args), parse_time(args.at)
    steps = explain(key, moment, config)
    print(f"1. Hora: {steps['timestamp']} s desde 1970 ({_iso(moment)})")
    print(f"2. Contador T = ({steps['timestamp']} - {config.t0}) // {config.period} = {steps['counter']}")
    print(f"3. T en 8 bytes big-endian: {steps['counter_bytes']}")
    print(f"4. HMAC-{config.algorithm}(secreto, T) = {steps['hmac']}")
    print(f"5. Último medio byte = {steps['offset']} -> se toman 4 bytes desde la posición {steps['offset']}: {steps['chunk']}")
    print(f"6. Sin el bit de signo: {steps['binary']}")
    print(f"7. {steps['binary']} mod 10^{config.digits} = {steps['code']}  <- código")
    return 0


def cmd_uri(args: argparse.Namespace) -> int:
    secret = read_secret_text(args)
    decode_secret(secret)  # valida antes de construir la URI
    print(provisioning_uri(secret, args.account, args.issuer, _config(args)))
    print("Contiene el secreto: compártelo solo con la app de autenticación (normalmente como código QR).", file=sys.stderr)
    return 0


def cmd_rfc_test(args: argparse.Namespace) -> int:
    results = run_rfc_vectors()
    print("Vectores de prueba del RFC 6238 (apéndice B, 8 dígitos, periodo 30 s)")
    print(f"{'TIEMPO':>12}  {'ALGORITMO':<9}  {'ESPERADO':<8}  {'OBTENIDO':<8}  RESULTADO")
    for timestamp, algorithm, expected, got, ok in results:
        print(f"{timestamp:>12}  {algorithm:<9}  {expected:<8}  {got:<8}  {'OK' if ok else 'FALLA'}")
    passed = sum(1 for r in results if r[4])
    print(f"\n{passed} de {len(results)} vectores coinciden.")
    return 0 if passed == len(results) else 3


COMMANDS = {
    "secret": cmd_secret, "code": cmd_code, "verify": cmd_verify,
    "explain": cmd_explain, "uri": cmd_uri, "rfc-test": cmd_rfc_test,
}


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except (InputError, SecretError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
