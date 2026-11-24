"""Pruebas de la lógica del buscador (scanner.py)."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from duplicate_finder.scanner import (
    ScanOptions,
    find_duplicates,
    format_size,
    group_by_size,
    is_hidden,
    sha256_of,
    FileEntry,
)

SAMPLES = Path(__file__).resolve().parent.parent / "samples" / "carpeta_demo"


def write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def test_sha256_by_blocks_matches_hashlib(tmp_path):
    data = os.urandom(10_000)
    path = write(tmp_path / "a.bin", data)
    assert sha256_of(path, block_size=4096) == hashlib.sha256(data).hexdigest()


def test_group_by_size_drops_unique_sizes():
    entries = [FileEntry(Path("a"), 10), FileEntry(Path("b"), 10), FileEntry(Path("c"), 5)]
    assert group_by_size(entries) == {10: [Path("a"), Path("b")]}


def test_same_size_different_content_is_not_duplicate(tmp_path):
    write(tmp_path / "x.txt", b"AAAA")
    write(tmp_path / "y.txt", b"BBBB")
    result = find_duplicates([tmp_path])
    assert result.groups == []
    assert result.files_hashed == 2  # mismo tamaño: hubo que comparar huellas


def test_unique_sizes_are_never_read(tmp_path):
    write(tmp_path / "a.txt", b"1")
    write(tmp_path / "b.txt", b"22")
    calls = []

    def fake_hasher(path, block_size):
        calls.append(path)
        return "x"

    find_duplicates([tmp_path], hasher=fake_hasher)
    assert calls == []


def test_finds_group_and_wasted_bytes(tmp_path):
    for name in ("a.txt", "sub/b.txt", "sub/c.txt"):
        write(tmp_path / name, b"contenido igual")
    write(tmp_path / "d.txt", b"otro")
    result = find_duplicates([tmp_path])
    assert len(result.groups) == 1
    group = result.groups[0]
    assert len(group.paths) == 3
    assert group.wasted_bytes == 2 * len(b"contenido igual")
    assert result.duplicate_files == 2


def test_empty_files_ignored_by_default(tmp_path):
    write(tmp_path / "a.txt", b"")
    write(tmp_path / "b.txt", b"")
    assert find_duplicates([tmp_path]).groups == []
    assert len(find_duplicates([tmp_path], ScanOptions(min_size=0)).groups) == 1


def test_hidden_files_and_folders(tmp_path):
    write(tmp_path / "a.txt", b"dato")
    write(tmp_path / ".oculto.txt", b"dato")
    write(tmp_path / ".carpeta" / "b.txt", b"dato")
    assert find_duplicates([tmp_path]).groups == []
    result = find_duplicates([tmp_path], ScanOptions(include_hidden=True))
    assert len(result.groups[0].paths) == 3


def test_is_hidden_by_name():
    assert is_hidden(Path(".git"))
    assert not is_hidden(Path("git"))


def test_overlapping_roots_count_each_file_once(tmp_path):
    write(tmp_path / "sub" / "a.txt", b"x1")
    write(tmp_path / "sub" / "b.txt", b"x1")
    result = find_duplicates([tmp_path, tmp_path / "sub"])
    assert result.files_seen == 2
    assert len(result.groups[0].paths) == 2


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="sin enlaces simbólicos")
def test_symlinks_are_not_followed(tmp_path):
    target = write(tmp_path / "real.txt", b"igual")
    try:
        (tmp_path / "enlace.txt").symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("el sistema no permite crear enlaces simbólicos")
    result = find_duplicates([tmp_path])
    assert result.groups == []
    assert any("enlace simbólico" in s.reason for s in result.skipped)


def test_unreadable_file_is_reported_not_fatal(tmp_path):
    write(tmp_path / "a.txt", b"igual")
    write(tmp_path / "b.txt", b"igual")

    def flaky_hasher(path, block_size):
        if path.name == "b.txt":
            raise PermissionError(13, "Permiso denegado", str(path))
        return "h"

    result = find_duplicates([tmp_path], hasher=flaky_hasher)
    assert result.groups == []
    assert [s.path.name for s in result.skipped] == ["b.txt"]


def test_missing_root_is_reported(tmp_path):
    result = find_duplicates([tmp_path / "no-existe"])
    assert result.files_seen == 0
    assert "no se pudo abrir" in result.skipped[0].reason


def test_groups_sorted_by_wasted_space(tmp_path):
    write(tmp_path / "s1.txt", b"pequeno")
    write(tmp_path / "s2.txt", b"pequeno")
    write(tmp_path / "g1.txt", b"G" * 100)
    write(tmp_path / "g2.txt", b"G" * 100)
    result = find_duplicates([tmp_path])
    assert [g.size for g in result.groups] == [100, 7]


def test_samples_expected_counts():
    result = find_duplicates([SAMPLES])
    assert result.files_seen == 7
    assert result.files_hashed == 7
    assert sorted(len(g.paths) for g in result.groups) == [2, 3]
    assert result.duplicate_files == 3


def test_samples_with_hidden_and_empty_files():
    result = find_duplicates([SAMPLES], ScanOptions(min_size=0, include_hidden=True))
    assert sorted(len(g.paths) for g in result.groups) == [2, 2, 4]


@pytest.mark.parametrize(
    "size, text",
    [(0, "0 B"), (1023, "1023 B"), (1024, "1.0 KiB"), (1536, "1.5 KiB"), (5 * 1024**2, "5.0 MiB")],
)
def test_format_size(size, text):
    assert format_size(size) == text
