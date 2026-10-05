"""Verifica que las copias intencionales de módulos compartidos sigan iguales.

Los proyectos 09 y 12 comparten parsers.py, models.py y timeutils.py como
copias (cada proyecto debe funcionar solo, ver docs/ARQUITECTURA.md). Este
script avisa si alguien modificó una copia y olvidó la otra. También lo
ejecuta la integración continua opcional (ver ci/github-actions.yml).

Uso (desde la carpeta ciberseguridad): python tools/check_shared_copies.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

SHARED_GROUPS = {
    module: [
        ROOT / "09-contador-logins" / "login_counter" / module,
        ROOT / "12-detector-accesos" / "failed_login_detector" / module,
    ]
    for module in ("models.py", "parsers.py", "timeutils.py")
}


def main() -> int:
    problems = 0
    for module, paths in SHARED_GROUPS.items():
        existing = [path for path in paths if path.is_file()]
        contents = {path.read_text(encoding="utf-8") for path in existing}
        if len(contents) > 1:
            problems += 1
            print(f"DIFERENTES: {module}")
            for path in existing:
                print(f"  - {path.relative_to(ROOT)}")
        else:
            print(f"OK: {module} ({len(existing)} copias)")
    if problems:
        print("\nSincroniza las copias o documenta por qué ahora deben ser distintas.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
