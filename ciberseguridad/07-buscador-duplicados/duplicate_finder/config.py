"""Lee y valida ``config/settings.json``. Los argumentos de la terminal tienen prioridad."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "settings.json"


class ConfigError(Exception):
    """La configuración no existe, no es JSON válido o tiene valores inválidos."""


@dataclass(frozen=True)
class Settings:
    min_size: int = 1
    include_hidden: bool = False
    block_size: int = 1024 * 1024
    top: int = 20


def _int(data: dict, key: str, default: int, minimum: int) -> int:
    value = data.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ConfigError(f"'{key}' debe ser un entero mayor o igual a {minimum}")
    return value


def load_settings(path: Path | None = None) -> Settings:
    config_path = path or DEFAULT_CONFIG
    if not config_path.is_file():
        if path is None:
            return Settings()
        raise ConfigError(f"No existe el archivo de configuración: {config_path}")
    try:
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{config_path} no es JSON válido (línea {exc.lineno}): {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{config_path} debe contener un objeto JSON")
    include_hidden = data.get("include_hidden", False)
    if not isinstance(include_hidden, bool):
        raise ConfigError("'include_hidden' debe ser true o false")
    return Settings(
        min_size=_int(data, "min_size", 1, 0),
        include_hidden=include_hidden,
        block_size=_int(data, "block_size", 1024 * 1024, 4096),
        top=_int(data, "top", 20, 0),
    )
