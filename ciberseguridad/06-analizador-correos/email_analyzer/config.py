"""Lee y valida ``config/settings.json``: marcas protegidas, acortadores y frases."""

from __future__ import annotations

import json
from pathlib import Path

from .indicators import Settings

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config" / "settings.json"


class ConfigError(Exception):
    """La configuración no existe, no es JSON válido o tiene valores inválidos."""


def _string_list(data: dict, key: str) -> list[str]:
    value = data.get(key)
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        raise ConfigError(f"'{key}' debe ser una lista de textos")
    return [v.strip() for v in value]


def load_settings(path: Path | None = None) -> Settings:
    config_path = path or DEFAULT_CONFIG
    try:
        data = json.loads(config_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ConfigError(f"No existe el archivo de configuración: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"{config_path} no es JSON válido (línea {exc.lineno}): {exc.msg}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{config_path} debe contener un objeto JSON")
    protected = data.get("protected_domains")
    if not isinstance(protected, dict) or not all(
        isinstance(domains, list) and domains and all(isinstance(d, str) and "." in d for d in domains)
        for domains in protected.values()
    ):
        raise ConfigError("'protected_domains' debe ser {\"Marca\": [\"dominio.ejemplo\", ...]}")
    return Settings(
        protected_domains={brand: [d.lower() for d in domains] for brand, domains in protected.items()},
        shorteners=frozenset(d.lower() for d in _string_list(data, "shorteners")),
        urgency_phrases=tuple(_string_list(data, "urgency_phrases")),
        credential_phrases=tuple(_string_list(data, "credential_phrases")),
    )
