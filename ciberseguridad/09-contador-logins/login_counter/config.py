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

from .timeutils import TimezoneError, load_timezone

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "settings.json"

DEFAULTS: dict[str, Any] = {
    "default_timezone": "UTC",
    "display_timezone": "UTC",
    "top": 10,
    "max_unparsed_shown": 20,
    "max_unparsed_kept": 500,
}


class ConfigError(ValueError):
    """La configuración no se pudo leer o tiene valores inválidos."""


@dataclass(frozen=True)
class Settings:
    """Configuración validada.

    Attributes:
        default_timezone: zona que se asume para fechas sin desplazamiento.
        display_timezone: zona en la que se muestran las fechas del reporte.
        top: filas por tabla (0 = todas).
        max_unparsed_shown: líneas no interpretadas que se muestran en terminal.
        max_unparsed_kept: líneas no interpretadas que se guardan para exportar.
    """

    default_timezone: str
    display_timezone: str
    top: int
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


def _non_negative_int(data: dict[str, Any], key: str) -> int:
    value = data[key]
    # bool es subclase de int en Python; se rechaza explícitamente.
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ConfigError(f"'{key}' debe ser un entero mayor o igual a 0 (recibido: {value!r})")
    return value


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
        ConfigError: si el archivo no existe (cuando se indicó explícitamente),
            no es JSON válido, tiene claves desconocidas o valores inválidos.
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
        default_timezone=_timezone_name(data, "default_timezone"),
        display_timezone=_timezone_name(data, "display_timezone"),
        top=_non_negative_int(data, "top"),
        max_unparsed_shown=_non_negative_int(data, "max_unparsed_shown"),
        max_unparsed_kept=_non_negative_int(data, "max_unparsed_kept"),
    )
