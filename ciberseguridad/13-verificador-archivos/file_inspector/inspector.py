"""Reglas del verificador. No imprime nada y nunca ejecuta ni extrae archivos.

Cada indicio es un ``Finding`` con gravedad, código, explicación y siguiente
paso sugerido. El veredicto de un archivo es la gravedad más alta encontrada:

* ALTA  -> SOSPECHOSO   (no lo abras; investiga)
* MEDIA -> REVISAR      (puede ser legítimo, confirma su origen)
* nada o solo BAJA -> SIN INDICIOS (no significa "seguro": solo que estas reglas no encontraron nada)
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Sequence

from .iocs import IocList
from .signatures import (
    BIDI_CONTROLS,
    DECOY_EXTENSIONS,
    EMPTY,
    PDF,
    RISKY_EXTENSIONS,
    TEXT,
    UNKNOWN,
    ZIP,
    FileType,
    detect_type,
)

HEAD_BYTES = 8192
BLOCK_SIZE = 1024 * 1024
PDF_SCAN_LIMIT = 5 * 1024 * 1024
MAX_ZIP_ENTRIES = 1000
SEVERITY_ORDER = {"BAJA": 1, "MEDIA": 2, "ALTA": 3}
VERDICTS = {3: "SOSPECHOSO", 2: "REVISAR", 1: "SIN INDICIOS", 0: "SIN INDICIOS"}
PDF_ACTIVE_KEYS = (b"/JavaScript", b"/JS", b"/OpenAction", b"/Launch", b"/EmbeddedFile", b"/AA")


@dataclass(frozen=True)
class Finding:
    severity: str  # ALTA, MEDIA o BAJA
    code: str
    message: str
    advice: str = ""


@dataclass
class Inspection:
    path: Path
    size: int
    extension: str
    detected: FileType
    md5: str
    sha1: str
    sha256: str
    findings: list[Finding] = field(default_factory=list)

    @property
    def level(self) -> int:
        return max((SEVERITY_ORDER[f.severity] for f in self.findings), default=0)

    @property
    def verdict(self) -> str:
        return VERDICTS[self.level]


@dataclass(frozen=True)
class Skipped:
    path: Path
    reason: str


def all_extensions(name: str) -> list[str]:
    """``'factura.pdf.exe'`` -> ``['.pdf', '.exe']`` (en minúsculas)."""
    stripped = name.rstrip(" .")
    parts = stripped.split(".")[1:]
    return ["." + part.strip().lower() for part in parts if part.strip()]


def hashes_of(path: Path) -> tuple[str, str, str, bytes]:
    """Calcula MD5, SHA-1 y SHA-256 en una sola lectura por bloques; devuelve también el inicio."""
    md5, sha1, sha256 = hashlib.md5(usedforsecurity=False), hashlib.sha1(usedforsecurity=False), hashlib.sha256()
    head = b""
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(BLOCK_SIZE), b""):
            if len(head) < HEAD_BYTES:
                head += block[: HEAD_BYTES - len(head)]
            md5.update(block)
            sha1.update(block)
            sha256.update(block)
    return md5.hexdigest(), sha1.hexdigest(), sha256.hexdigest(), head


def _name_findings(name: str, extensions: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    if any(char in BIDI_CONTROLS for char in name):
        findings.append(Finding(
            "ALTA", "NOMBRE_BIDI",
            "el nombre contiene un carácter de control bidireccional (p. ej. U+202E) que invierte "
            "cómo se ve: la extensión real queda oculta",
            "no confíes en el nombre que ves; usa la extensión real que muestra este reporte",
        ))
    if re.search(r" {5,}", name):
        findings.append(Finding(
            "MEDIA", "NOMBRE_ESPACIOS",
            "el nombre tiene muchos espacios seguidos, un truco para empujar la extensión real fuera de la vista",
        ))
    last = extensions[-1] if extensions else ""
    if len(extensions) >= 2 and last in RISKY_EXTENSIONS and extensions[-2] in DECOY_EXTENSIONS:
        findings.append(Finding(
            "ALTA", "DOBLE_EXTENSION",
            f"doble extensión: aparenta ser '{extensions[-2]}' pero termina en '{last}'",
            "no lo abras: Windows oculta por defecto la última extensión y quien lo reciba verá un "
            "documento; activa la opción de mostrar extensiones y reporta de dónde llegó",
        ))
    elif last in RISKY_EXTENSIONS:
        findings.append(Finding(
            "MEDIA", "EXTENSION_RIESGOSA",
            f"la extensión '{last}' se ejecuta o puede contener macros al abrirse",
            "ábrelo solo si sabes de dónde viene y lo esperabas",
        ))
    if len(name) > 150:
        findings.append(Finding("BAJA", "NOMBRE_LARGO", f"nombre muy largo ({len(name)} caracteres)"))
    return findings


def _type_findings(detected: FileType, extension: str) -> list[Finding]:
    if detected in (EMPTY, UNKNOWN):
        return []
    if detected.executable and extension not in detected.extensions and extension not in RISKY_EXTENSIONS:
        return [Finding(
            "ALTA", "EJECUTABLE_DISFRAZADO",
            f"el contenido es {detected.label} pero la extensión es '{extension or '(ninguna)'}'",
            "no lo abras ni lo renombres; calcula su hash y consúltalo en tu fuente de inteligencia",
        )]
    if detected.executable:
        return [Finding("MEDIA", "CONTENIDO_EJECUTABLE", f"el contenido es {detected.label}")]
    if extension and extension not in detected.extensions:
        if detected is TEXT and extension not in DECOY_EXTENSIONS and extension not in RISKY_EXTENSIONS:
            return []  # p. ej. ".conf" o ".toml": texto con extensión que no está en la lista
        return [Finding(
            "MEDIA", "TIPO_NO_COINCIDE",
            f"la extensión '{extension}' no corresponde al contenido real ({detected.label})",
            "puede ser un error al guardar, o un intento de engañar a un filtro por extensión",
        )]
    return []


def _pdf_findings(path: Path) -> list[Finding]:
    """Busca palabras clave de contenido activo en los primeros MB del PDF (sin interpretarlo)."""
    with path.open("rb") as handle:
        data = handle.read(PDF_SCAN_LIMIT)
    found = sorted({key.decode() for key in PDF_ACTIVE_KEYS if re.search(re.escape(key) + rb"[\s/<\[(]", data)})
    if not found:
        return []
    return [Finding(
        "MEDIA", "PDF_ACTIVO",
        "el PDF declara contenido activo: " + ", ".join(found),
        "ábrelo en un visor con JavaScript desactivado o en un entorno aislado",
    )]


def _zip_findings(path: Path) -> list[Finding]:
    """Lista los nombres dentro del ZIP sin extraer nada."""
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
    except (zipfile.BadZipFile, OSError, ValueError):
        return [Finding("BAJA", "ZIP_DANADO", "parece ZIP pero no se pudo leer su índice")]
    findings: list[Finding] = []
    if len(infos) > MAX_ZIP_ENTRIES:
        findings.append(Finding("MEDIA", "ZIP_ENORME", f"el ZIP tiene {len(infos)} entradas"))
        infos = infos[:MAX_ZIP_ENTRIES]
    risky = sorted({info.filename for info in infos if all_extensions(Path(info.filename).name)[-1:]
                    and all_extensions(Path(info.filename).name)[-1] in RISKY_EXTENSIONS})
    if risky:
        shown = ", ".join(risky[:5]) + (" ..." if len(risky) > 5 else "")
        findings.append(Finding(
            "MEDIA", "ZIP_CON_EJECUTABLES", f"contiene archivos que se ejecutan: {shown}",
            "un documento de Office normal no trae scripts ni ejecutables",
        ))
    if any(info.flag_bits & 0x1 for info in infos):
        findings.append(Finding(
            "MEDIA", "ZIP_CIFRADO", "tiene entradas cifradas: los antivirus no pueden revisar su contenido",
            "un ZIP cifrado con la contraseña en el mismo correo es una técnica común de evasión",
        ))
    if any(Path(info.filename).is_absolute() or ".." in Path(info.filename).parts for info in infos):
        findings.append(Finding(
            "ALTA", "ZIP_SLIP", "contiene rutas absolutas o con '..': al extraerlo podría escribir fuera de la carpeta",
        ))
    return findings


def inspect_file(path: Path, iocs: IocList | None = None) -> Inspection:
    """Analiza un archivo. Lanza ``OSError`` si no se puede leer."""
    md5, sha1, sha256, head = hashes_of(path)
    size = path.stat().st_size
    extensions = all_extensions(path.name)
    extension = extensions[-1] if extensions else ""
    detected = detect_type(head)

    findings = _name_findings(path.name, extensions)
    findings += _type_findings(detected, extension)
    if detected is PDF:
        findings += _pdf_findings(path)
    if detected is ZIP:
        findings += _zip_findings(path)
    if detected is EMPTY:
        findings.append(Finding("BAJA", "VACIO", "el archivo está vacío"))
    if iocs is not None:
        match = iocs.lookup(sha256, sha1, md5)
        if match is not None:
            findings.insert(0, Finding(
                "ALTA", "COINCIDE_CON_IOC",
                f"su huella está en la lista de indicadores: {match[1]}",
                "trátalo como un incidente: aísla el equipo donde apareció y escala según tu procedimiento",
            ))

    findings.sort(key=lambda f: -SEVERITY_ORDER[f.severity])
    return Inspection(path, size, extension, detected, md5, sha1, sha256, findings)


def iter_targets(paths: Sequence[Path], recursive: bool, skipped: list[Skipped]) -> Iterator[Path]:
    """Archivos regulares a revisar. No sigue enlaces simbólicos."""
    for path in paths:
        try:
            st = path.lstat()
        except OSError as exc:
            skipped.append(Skipped(path, f"no se pudo abrir: {exc.strerror or exc}"))
            continue
        if stat.S_ISREG(st.st_mode):
            yield path
        elif stat.S_ISDIR(st.st_mode):
            walker = os.walk(path, followlinks=False) if recursive else [(str(path), [], os.listdir(path))]
            for dirpath, dirnames, filenames in walker:
                dirnames.sort()
                for name in sorted(filenames):
                    child = Path(dirpath) / name
                    if child.is_symlink():
                        skipped.append(Skipped(child, "enlace simbólico (no se sigue)"))
                    elif child.is_file():
                        yield child
        elif stat.S_ISLNK(st.st_mode):
            skipped.append(Skipped(path, "enlace simbólico (no se sigue)"))
        else:
            skipped.append(Skipped(path, "no es un archivo ni una carpeta"))


def inspect_paths(
    paths: Sequence[Path], iocs: IocList | None = None, recursive: bool = False
) -> tuple[list[Inspection], list[Skipped]]:
    skipped: list[Skipped] = []
    results: list[Inspection] = []
    for target in iter_targets(paths, recursive, skipped):
        try:
            results.append(inspect_file(target, iocs))
        except OSError as exc:
            skipped.append(Skipped(target, f"no se pudo leer: {exc.strerror or exc}"))
    results.sort(key=lambda r: (-r.level, str(r.path)))
    return results, skipped
