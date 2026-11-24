"""Reglas de validación de archivos subidos. No imprime nada.

Imagina el filtro de un formulario que acepta documentos de clientes: antes de
guardar un archivo hay que decidir si su nombre es seguro para el sistema de
archivos, si su tamaño es razonable y si su contenido coincide con lo que dice
ser. Cada regla devuelve un ``Problem`` con código, mensaje y por qué importa,
para que el rechazo se pueda explicar a quien subió el archivo.
"""

from __future__ import annotations

import os
import re
import stat
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Sequence

# Nombres que Windows reserva para dispositivos, con o sin extensión.
WINDOWS_RESERVED = frozenset(
    ["CON", "PRN", "AUX", "NUL"] + [f"COM{i}" for i in range(1, 10)] + [f"LPT{i}" for i in range(1, 10)]
)
FORBIDDEN_CHARS = set('<>:"/\\|?*')
EXECUTABLE_EXTENSIONS = frozenset(
    ".exe .scr .com .pif .bat .cmd .msi .js .jse .vbs .vbe .wsf .hta .ps1 .lnk .jar .dll .cpl .reg .iso .docm .xlsm".split()
)

# Firmas mínimas para comprobar que el contenido corresponde a la extensión.
SIGNATURES: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".zip": (b"PK\x03\x04", b"PK\x05\x06"),
    ".docx": (b"PK\x03\x04",),
    ".xlsx": (b"PK\x03\x04",),
    ".pptx": (b"PK\x03\x04",),
}
TEXT_EXTENSIONS = frozenset(".txt .csv .md .json .xml .log".split())
EXECUTABLE_MAGIC = (b"MZ", b"\x7fELF")


@dataclass(frozen=True)
class Rules:
    allowed_extensions: frozenset[str] = frozenset(".pdf .png .jpg .jpeg .txt .csv .docx".split())
    max_size_bytes: int = 5 * 1024 * 1024
    max_name_length: int = 100
    allow_hidden: bool = False
    check_content: bool = True


@dataclass(frozen=True)
class Problem:
    code: str
    message: str
    why: str


@dataclass
class Validation:
    name: str
    path: Path | None
    size: int | None
    problems: list[Problem] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        return not self.problems


def extensions_of(name: str) -> list[str]:
    parts = name.split(".")[1:]
    return ["." + part.lower() for part in parts if part]


def validate_name(name: str, rules: Rules) -> list[Problem]:
    """Revisa solo el nombre; sirve también para nombres que no se pueden crear en tu sistema."""
    problems: list[Problem] = []
    if not name or not name.strip():
        return [Problem("NOMBRE_VACIO", "el nombre está vacío", "no se puede guardar ni identificar")]

    if any(unicodedata.category(c) in ("Cc", "Cf") for c in name):
        problems.append(Problem(
            "NOMBRE_CARACTERES_CONTROL", "tiene caracteres de control o invisibles (p. ej. U+202E)",
            "pueden ocultar la extensión real o alterar terminales y registros",
        ))
    if "/" in name or "\\" in name or name in (".", "..") or ".." in name.split("/"):
        problems.append(Problem(
            "NOMBRE_CON_RUTA", "contiene separadores de carpeta o '..'",
            "un nombre como '../../config' podría escribir fuera de la carpeta de subidas (path traversal)",
        ))
    bad = sorted(FORBIDDEN_CHARS.intersection(name) - {"/", "\\"})
    if bad:
        problems.append(Problem(
            "NOMBRE_CARACTERES_PROHIBIDOS", f"usa caracteres que Windows no permite: {' '.join(bad)}",
            "el archivo no se podría guardar ni copiar a un equipo con Windows",
        ))
    stem = name.split(".")[0].rstrip(" ").upper()
    if stem in WINDOWS_RESERVED:
        problems.append(Problem(
            "NOMBRE_RESERVADO", f"'{stem}' es un nombre reservado de Windows",
            "Windows lo trata como un dispositivo (p. ej. la consola), no como un archivo",
        ))
    if name != name.rstrip(" ."):
        problems.append(Problem(
            "NOMBRE_TERMINA_EN_PUNTO_O_ESPACIO", "termina en punto o espacio",
            "Windows los quita en silencio: el archivo guardado no tendría el nombre esperado",
        ))
    if len(name) > rules.max_name_length:
        problems.append(Problem(
            "NOMBRE_LARGO", f"tiene {len(name)} caracteres (máximo {rules.max_name_length})",
            "las rutas largas fallan en algunos sistemas y facilitan esconder la extensión",
        ))
    if name.startswith(".") and not rules.allow_hidden:
        problems.append(Problem(
            "NOMBRE_OCULTO", "empieza con punto (archivo oculto en Linux y macOS)",
            "un archivo oculto pasa desapercibido; también podría sobrescribir configuraciones como .htaccess",
        ))

    exts = extensions_of(name.rstrip(" ."))
    last = exts[-1] if exts else ""
    if len(exts) >= 2 and last in EXECUTABLE_EXTENSIONS:
        problems.append(Problem(
            "DOBLE_EXTENSION", f"doble extensión que termina en ejecutable: '{''.join(exts[-2:])}'",
            "Windows oculta la última extensión: el usuario vería un documento y ejecutaría un programa",
        ))
    if not last:
        problems.append(Problem("SIN_EXTENSION", "no tiene extensión", "no se puede saber qué tipo de archivo es"))
    elif last not in rules.allowed_extensions:
        allowed = ", ".join(sorted(rules.allowed_extensions))
        problems.append(Problem(
            "EXTENSION_NO_PERMITIDA", f"la extensión '{last}' no está permitida (permitidas: {allowed})",
            "lista blanca: solo se acepta lo que el sistema necesita, no se intenta adivinar lo peligroso",
        ))
    return problems


def validate_content(head: bytes, extension: str) -> list[Problem]:
    """Compara los primeros bytes con la extensión declarada."""
    if head.startswith(EXECUTABLE_MAGIC):
        return [Problem(
            "CONTENIDO_EJECUTABLE", "el contenido es un programa ejecutable",
            "un programa disfrazado con otra extensión es una técnica clásica de malware",
        )]
    expected = SIGNATURES.get(extension)
    if expected is not None and not head.startswith(expected):
        return [Problem(
            "CONTENIDO_NO_COINCIDE", f"el contenido no corresponde a un archivo '{extension}'",
            "la extensión se cambia con solo renombrar; el contenido real es lo que abrirá el programa",
        )]
    if extension in TEXT_EXTENSIONS:
        if b"\x00" in head:
            return [Problem(
                "CONTENIDO_NO_COINCIDE", f"'{extension}' debería ser texto pero tiene bytes binarios",
                "un binario renombrado a .txt evita filtros que solo revisan la extensión",
            )]
    return []


def validate_file(path: Path, rules: Rules) -> Validation:
    """Valida nombre, tamaño y contenido de un archivo existente. Lanza OSError si no se puede leer."""
    st = path.stat()
    result = Validation(path.name, path, st.st_size, validate_name(path.name, rules))
    if st.st_size == 0:
        result.problems.append(Problem("ARCHIVO_VACIO", "el archivo está vacío", "una subida vacía suele ser un error"))
    elif st.st_size > rules.max_size_bytes:
        result.problems.append(Problem(
            "DEMASIADO_GRANDE",
            f"pesa {st.st_size} bytes (máximo {rules.max_size_bytes})",
            "los archivos enormes llenan el disco y pueden usarse para negar el servicio",
        ))
    if rules.check_content and st.st_size > 0 and st.st_size <= rules.max_size_bytes:
        with path.open("rb") as handle:
            head = handle.read(64)
        exts = extensions_of(path.name)
        result.problems += validate_content(head, exts[-1] if exts else "")
    return result


@dataclass(frozen=True)
class Skipped:
    path: Path
    reason: str


def iter_files(paths: Sequence[Path], skipped: list[Skipped]) -> Iterator[Path]:
    """Archivos regulares de las rutas dadas (las carpetas se revisan sin subcarpetas)."""
    for path in paths:
        try:
            st = path.lstat()
        except OSError as exc:
            skipped.append(Skipped(path, f"no se pudo abrir: {exc.strerror or exc}"))
            continue
        if stat.S_ISDIR(st.st_mode):
            for child in sorted(path.iterdir()):
                if child.is_symlink():
                    skipped.append(Skipped(child, "enlace simbólico (no se sigue)"))
                elif child.is_file():
                    yield child
        elif stat.S_ISREG(st.st_mode):
            yield path
        else:
            skipped.append(Skipped(path, "no es un archivo regular"))


def validate_paths(paths: Sequence[Path], rules: Rules) -> tuple[list[Validation], list[Skipped]]:
    skipped: list[Skipped] = []
    results = []
    for path in iter_files(paths, skipped):
        try:
            results.append(validate_file(path, rules))
        except OSError as exc:
            skipped.append(Skipped(path, f"no se pudo leer: {exc.strerror or exc}"))
    return results, skipped


def safe_storage_name(name: str) -> str:
    """Propone un nombre seguro (para el ejercicio de "sanear"): solo letras, números, '-', '_' y un punto."""
    base = os.path.basename(name.replace("\\", "/")).rstrip(" .")
    normalized = unicodedata.normalize("NFKD", base).encode("ascii", "ignore").decode()
    stem, dot, ext = normalized.rpartition(".")
    if not dot:
        stem, ext = normalized, ""
    stem = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_") or "archivo"
    ext = re.sub(r"[^A-Za-z0-9]+", "", ext).lower()
    if stem.upper() in WINDOWS_RESERVED:
        stem = f"_{stem}"
    return f"{stem[:80]}.{ext}" if ext else stem[:80]
