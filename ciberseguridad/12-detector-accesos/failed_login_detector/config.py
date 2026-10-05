"""Carga y validación de la configuración editable (``config/settings.json``).

Los argumentos de la terminal tienen prioridad sobre este archivo. Las
claves que empiezan con ``_`` se ignoran y sirven como comentarios, porque
JSON no admite comentarios.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .detector import RULES
from .timeutils import TimezoneError, load_timezone

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "settings.json"

DEFAULTS: dict[str, Any] = {
    "threshold": 5,
    "window_minutes": 5,
    "success_after_minutes": 15,
    "rules": ["user", "ip"],
    "default_timezone": "UTC",
    "display_timezone": "UTC",
    "max_evidence": 10,
    "max_unparsed_shown": 10,
    "max_unparsed_kept": 500,
}


class ConfigError(ValueError):
    """La configuración no se pudo leer o tiene valores inválidos."""


@dataclass(frozen=True)
class Settings:
    """Configuración validada (ver ``config/settings.json`` para la descripción de cada clave)."""

    threshold: int
    window_minutes: float
    success_after_minutes: float
    rules: tuple[str, ...]
    default_timezone: str
    display_timezone: str
    max_evidence: int
    max_unparsed_shown: int
    max_unparsed_kept: int


def _read_json(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        raise ConfigError(f"No existe el archivo de configuración: {path}") from None
    except json.JSONDecodeError as exc:
        raise ConfigError(f"JSON inválido en {path}, línea {exc.lineno}: {exc.msg}") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path} debe contener un objeto JSON ({{...}})")
    return data


def _int(data: dict[str, Any], key: str, minimum: int) -> int:
    value = data[key]
    # bool es subclase de int en Python; se rechaza explícitamente.
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ConfigError(f"'{key}' debe ser un entero mayor o igual a {minimum} (recibido: {value!r})")
    return value


def _minutes(data: dict[str, Any], key: str, allow_zero: bool) -> float:
    value = data[key]
    valid_type = isinstance(value, (int, float)) and not isinstance(value, bool)
    if not valid_type or value < 0 or (value == 0 and not allow_zero):
        limit = "mayor o igual a 0" if allow_zero else "mayor que 0"
        raise ConfigError(f"'{key}' debe ser un número {limit} (recibido: {value!r})")
    return float(value)


def _rules(data: dict[str, Any]) -> tuple[str, ...]:
    value = data["rules"]
    if not isinstance(value, list) or not value or any(rule not in RULES for rule in value):
        raise ConfigError(f"'rules' debe ser una lista con 'user', 'ip' o ambos (recibido: {value!r})")
    return tuple(dict.fromkeys(value))  # quita duplicados conservando el orden


def _timezone_name(data: dict[str, Any], key: str) -> str:
    value = data[key]
    if not isinstance(value, str):
        raise ConfigError(f"'{key}' debe ser texto, por ejemplo \"UTC\" o \"America/Mexico_City\"")
    try:
        load_timezone(value)
    except TimezoneError as exc:
        raise ConfigError(f"'{key}': {exc}") from None
    return value


def load_settings(path: Path | None = None) -> Settings:
    """Lee la configuración y la valida.

    Args:
        path: archivo JSON. Si es ``None`` se usa ``config/settings.json`` del
            proyecto, y si no existe se usan los valores por defecto.

    Raises:
        ConfigError: si el archivo indicado no existe, no es JSON válido,
            tiene claves desconocidas o valores fuera de rango.
    """
    data = dict(DEFAULTS)
    if path is not None:
        data.update(_read_json(path))
    elif DEFAULT_CONFIG_PATH.is_file():
        data.update(_read_json(DEFAULT_CONFIG_PATH))

    data = {key: value for key, value in data.items() if not key.startswith("_")}
    unknown = sorted(set(data) - set(DEFAULTS))
    if unknown:
        raise ConfigError(f"Claves desconocidas en la configuración: {', '.join(unknown)}")

    return Settings(
        threshold=_int(data, "threshold", 2),
        window_minutes=_minutes(data, "window_minutes", allow_zero=False),
        success_after_minutes=_minutes(data, "success_after_minutes", allow_zero=True),
        rules=_rules(data),
        default_timezone=_timezone_name(data, "default_timezone"),
        display_timezone=_timezone_name(data, "display_timezone"),
        max_evidence=_int(data, "max_evidence", 1),
        max_unparsed_shown=_int(data, "max_unparsed_shown", 0),
        max_unparsed_kept=_int(data, "max_unparsed_kept", 0),
    )
