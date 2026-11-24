"""Lógica del buscador: recorrer carpetas, agrupar por tamaño y comparar huellas.

El orden importa para el rendimiento:

1. Se recorre cada carpeta y se anota solo ``(ruta, tamaño)``; no se lee nada.
2. Se agrupa por tamaño. Dos archivos de distinto tamaño no pueden ser iguales,
   así que los tamaños únicos se descartan sin leerlos.
3. Solo los archivos con tamaño repetido se leen por bloques para calcular su
   SHA-256. Así un archivo de varios GB no se carga completo en memoria.

Este módulo no imprime nada ni borra nada: devuelve datos para ``report``.
"""

from __future__ import annotations

import hashlib
import os
import stat
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Iterator, Sequence

DEFAULT_BLOCK_SIZE = 1024 * 1024  # 1 MiB por lectura


@dataclass(frozen=True)
class ScanOptions:
    """Opciones del recorrido. Los valores por defecto son los seguros."""

    min_size: int = 1  # los archivos vacíos son "iguales" entre sí pero no ocupan espacio
    include_hidden: bool = False
    block_size: int = DEFAULT_BLOCK_SIZE


@dataclass(frozen=True)
class FileEntry:
    path: Path
    size: int


@dataclass(frozen=True)
class Skipped:
    """Archivo o carpeta que no se pudo revisar, con el motivo."""

    path: Path
    reason: str


@dataclass
class DuplicateGroup:
    """Archivos con el mismo contenido (mismo tamaño y misma huella SHA-256)."""

    sha256: str
    size: int
    paths: list[Path] = field(default_factory=list)

    @property
    def wasted_bytes(self) -> int:
        """Espacio que ocupan las copias sobrantes (todas menos una)."""
        return self.size * (len(self.paths) - 1)


@dataclass
class ScanResult:
    groups: list[DuplicateGroup]
    files_seen: int
    bytes_seen: int
    files_hashed: int
    skipped: list[Skipped]

    @property
    def duplicate_files(self) -> int:
        """Copias sobrantes: en un grupo de 3 archivos iguales hay 2 sobrantes."""
        return sum(len(group.paths) - 1 for group in self.groups)

    @property
    def wasted_bytes(self) -> int:
        return sum(group.wasted_bytes for group in self.groups)


def is_hidden(path: Path, st: os.stat_result | None = None) -> bool:
    """Oculto si el nombre empieza con punto (Linux) o tiene el atributo oculto (Windows)."""
    if path.name.startswith("."):
        return True
    attributes = getattr(st, "st_file_attributes", 0) if st is not None else 0
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_HIDDEN", 0))


def iter_files(
    roots: Sequence[Path], options: ScanOptions, skipped: list[Skipped]
) -> Iterator[FileEntry]:
    """Recorre las carpetas y produce los archivos regulares a considerar.

    * No sigue enlaces simbólicos: podrían apuntar fuera de la carpeta elegida
      o crear ciclos infinitos.
    * Un mismo archivo físico se cuenta una sola vez, aunque dos carpetas de
      entrada se traslapen o haya enlaces duros (mismo dispositivo e inodo).
    * Lo que no se puede leer se anota en ``skipped`` en vez de detener todo.
    """
    seen_ids: set[tuple[int, int]] = set()
    seen_paths: set[Path] = set()

    def visit(path: Path, st: os.stat_result) -> Iterator[FileEntry]:
        identity = (st.st_dev, st.st_ino)
        resolved = path.resolve()
        if (st.st_ino and identity in seen_ids) or resolved in seen_paths:
            return
        seen_ids.add(identity)
        seen_paths.add(resolved)
        if st.st_size >= options.min_size:
            yield FileEntry(path, st.st_size)

    for root in roots:
        try:
            root_st = root.lstat()
        except OSError as exc:
            skipped.append(Skipped(root, f"no se pudo abrir: {exc.strerror or exc}"))
            continue
        if stat.S_ISREG(root_st.st_mode):
            yield from visit(root, root_st)
            continue
        if not stat.S_ISDIR(root_st.st_mode):
            skipped.append(Skipped(root, "no es un archivo ni una carpeta"))
            continue

        def on_error(exc: OSError) -> None:
            skipped.append(Skipped(Path(exc.filename or root), f"no se pudo leer la carpeta: {exc.strerror or exc}"))

        for dirpath, dirnames, filenames in os.walk(root, onerror=on_error, followlinks=False):
            current = Path(dirpath)
            if not options.include_hidden:
                dirnames[:] = [d for d in dirnames if not is_hidden(current / d, _safe_lstat(current / d))]
            dirnames.sort()
            for name in sorted(filenames):
                path = current / name
                st = _safe_lstat(path)
                if st is None:
                    skipped.append(Skipped(path, "desapareció o no se puede consultar"))
                    continue
                if stat.S_ISLNK(st.st_mode):
                    skipped.append(Skipped(path, "enlace simbólico (no se sigue)"))
                    continue
                if not stat.S_ISREG(st.st_mode):
                    continue  # sockets, dispositivos, etc.
                if not options.include_hidden and is_hidden(path, st):
                    continue
                yield from visit(path, st)


def _safe_lstat(path: Path) -> os.stat_result | None:
    try:
        return path.lstat()
    except OSError:
        return None


def sha256_of(path: Path, block_size: int = DEFAULT_BLOCK_SIZE) -> str:
    """Calcula el SHA-256 leyendo por bloques (memoria constante)."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(block_size), b""):
            digest.update(block)
    return digest.hexdigest()


def group_by_size(entries: Iterable[FileEntry]) -> dict[int, list[Path]]:
    """Devuelve solo los tamaños que se repiten (los demás no pueden tener duplicado)."""
    by_size: dict[int, list[Path]] = defaultdict(list)
    for entry in entries:
        by_size[entry.size].append(entry.path)
    return {size: paths for size, paths in by_size.items() if len(paths) > 1}


def find_duplicates(
    roots: Sequence[Path],
    options: ScanOptions = ScanOptions(),
    hasher: Callable[[Path, int], str] = sha256_of,
) -> ScanResult:
    """Busca grupos de archivos idénticos. ``hasher`` se puede sustituir en pruebas."""
    skipped: list[Skipped] = []
    entries = list(iter_files(roots, options, skipped))
    candidates = group_by_size(entries)

    groups: list[DuplicateGroup] = []
    hashed = 0
    for size, paths in candidates.items():
        by_hash: dict[str, list[Path]] = defaultdict(list)
        for path in paths:
            try:
                digest = hasher(path, options.block_size)
            except OSError as exc:
                skipped.append(Skipped(path, f"no se pudo leer: {exc.strerror or exc}"))
                continue
            hashed += 1
            by_hash[digest].append(path)
        for digest, same in by_hash.items():
            if len(same) > 1:
                groups.append(DuplicateGroup(digest, size, sorted(same, key=str)))

    # Primero los grupos que más espacio desperdician; después, orden estable.
    groups.sort(key=lambda g: (-g.wasted_bytes, -len(g.paths), str(g.paths[0])))
    return ScanResult(
        groups=groups,
        files_seen=len(entries),
        bytes_seen=sum(entry.size for entry in entries),
        files_hashed=hashed,
        skipped=skipped,
    )


def format_size(num_bytes: int) -> str:
    """Tamaño legible en unidades binarias: 1536 -> '1.5 KiB'."""
    value = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB"):
        if value < 1024 or unit == "GiB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GiB"  # pragma: no cover
