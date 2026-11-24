"""Lee y valida las reglas de ``config/settings.json`` (o de otro archivo con ``--config``)."""

from __future__ import annotations

import json
from pathlib import Path

from .rules import Rules

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "settings.json"


class ConfigError(Exception):
    """La configuración no existe, no es JSON válido o tiene valores inválidos."""


def load_rules(path: Path | None = None) -> Rules:
    config_path = path or DEFAULT_CONFIG
    if not config_path.is_file():
        if path is None:
            return Rules()
        raise ConfigError(f"No existe el archivo de configuración: {config_path}")
    try:
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{config_path} no es JSON válido (línea {exc.lineno}): {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{config_path} debe contener un objeto JSON")

    defaults = Rules()
    exts = data.get("allowed_extensions", sorted(defaults.allowed_extensions))
    if not isinstance(exts, list) or not all(isinstance(e, str) and e.startswith(".") and len(e) > 1 for e in exts):
        raise ConfigError("'allowed_extensions' debe ser una lista de extensiones que empiecen con punto, p. ej. \".pdf\"")

    def positive_int(key: str, default: int) -> int:
        value = data.get(key, default)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ConfigError(f"'{key}' debe ser un entero positivo")
        return value

    def boolean(key: str, default: bool) -> bool:
        value = data.get(key, default)
        if not isinstance(value, bool):
            raise ConfigError(f"'{key}' debe ser true o false")
        return value

    return Rules(
        allowed_extensions=frozenset(e.lower() for e in exts),
        max_size_bytes=positive_int("max_size_bytes", defaults.max_size_bytes),
        max_name_length=positive_int("max_name_length", defaults.max_name_length),
        allow_hidden=boolean("allow_hidden", defaults.allow_hidden),
        check_content=boolean("check_content", defaults.check_content),
    )
