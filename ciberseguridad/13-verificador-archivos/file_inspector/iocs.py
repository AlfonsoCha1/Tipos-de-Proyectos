"""Lista local de indicadores de compromiso (IOC): huellas de archivos ya conocidos.

Formato del archivo: una huella por línea (MD5, SHA-1 o SHA-256 en hexadecimal),
opcionalmente seguida de ``#`` y una descripción. Las líneas vacías y las que
empiezan con ``#`` se ignoran. Las inválidas se reportan, no se descartan en silencio.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

HASH_LENGTHS = {32: "md5", 40: "sha1", 64: "sha256"}
_HEX = re.compile(r"^[0-9a-fA-F]+$")


class IocError(Exception):
    """El archivo de indicadores no existe o no se puede leer."""


@dataclass
class IocList:
    entries: dict[str, str] = field(default_factory=dict)  # huella en minúsculas -> descripción
    invalid_lines: list[tuple[int, str]] = field(default_factory=list)
    source: Path | None = None

    def lookup(self, *digests: str) -> tuple[str, str] | None:
        """Devuelve (huella, descripción) de la primera huella que esté en la lista."""
        for digest in digests:
            label = self.entries.get(digest.lower())
            if label is not None:
                return digest.lower(), label
        return None


def parse_iocs(text: str) -> IocList:
    result = IocList()
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        value, _, comment = line.partition("#")
        value = value.strip()
        if len(value) in HASH_LENGTHS and _HEX.match(value):
            result.entries[value.lower()] = comment.strip() or f"IOC {HASH_LENGTHS[len(value)]}"
        else:
            result.invalid_lines.append((number, raw[:120]))
    return result


def load_iocs(path: Path) -> IocList:
    try:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
    except FileNotFoundError as exc:
        raise IocError(f"No existe la lista de indicadores: {path}") from exc
    except OSError as exc:
        raise IocError(f"No se pudo leer la lista de indicadores {path}: {exc}") from exc
    result = parse_iocs(text)
    result.source = path
    return result
