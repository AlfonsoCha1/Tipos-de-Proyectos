"""Pruebas de las reglas del verificador (signatures, iocs, inspector)."""

from __future__ import annotations

import hashlib
import io
import zipfile
from pathlib import Path

import pytest

from file_inspector.demo import FAKE_PE, IOC_SAMPLE, create_demo
from file_inspector.inspector import all_extensions, inspect_file, inspect_paths
from file_inspector.iocs import parse_iocs
from file_inspector.signatures import ELF, EMPTY, JPEG, PDF, PE, PNG, TEXT, UNKNOWN, ZIP, detect_type

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def codes(inspection):
    return [f.code for f in inspection.findings]


def make(tmp_path: Path, name: str, data: bytes) -> Path:
    path = tmp_path / name
    path.write_bytes(data)
    return path


@pytest.mark.parametrize(
    "head, expected",
    [
        (b"MZ\x90\x00", PE),
        (b"\x7fELF\x02", ELF),
        (b"%PDF-1.7", PDF),
        (b"\x89PNG\r\n\x1a\n....", PNG),
        (b"\xff\xd8\xff\xe0", JPEG),
        (b"PK\x03\x04", ZIP),
        (b"hola mundo\n", TEXT),
        ("acentos: áéí".encode(), TEXT),
        (b"\x00\x01\x02\x03", UNKNOWN),
        (b"", EMPTY),
    ],
)
def test_detect_type(head, expected):
    assert detect_type(head) is expected


def test_text_cut_in_the_middle_of_a_character_is_still_text():
    data = ("a" * 10 + "ñ").encode()[:-1]
    assert detect_type(data) is TEXT


@pytest.mark.parametrize(
    "name, expected",
    [("a.txt", [".txt"]), ("factura.PDF.exe", [".pdf", ".exe"]), ("sin_extension", []),
     (".bashrc", [".bashrc"]), ("raro.exe. . ", [".exe"])],
)
def test_all_extensions(name, expected):
    assert all_extensions(name) == expected


def test_hashes_match_hashlib(tmp_path):
    data = b"contenido de prueba" * 1000
    result = inspect_file(make(tmp_path, "a.bin", data))
    assert result.sha256 == hashlib.sha256(data).hexdigest()
    assert result.sha1 == hashlib.sha1(data).hexdigest()
    assert result.md5 == hashlib.md5(data).hexdigest()


def test_double_extension_is_suspicious(tmp_path):
    result = inspect_file(make(tmp_path, "factura.pdf.exe", FAKE_PE))
    assert result.verdict == "SOSPECHOSO"
    assert codes(result)[0] == "DOBLE_EXTENSION"


def test_executable_disguised_as_image(tmp_path):
    result = inspect_file(make(tmp_path, "foto.jpg", FAKE_PE))
    assert codes(result) == ["EJECUTABLE_DISFRAZADO"]
    assert result.detected is PE


def test_executable_with_own_extension_is_only_review(tmp_path):
    result = inspect_file(make(tmp_path, "instalador.exe", FAKE_PE))
    assert result.verdict == "REVISAR"
    assert set(codes(result)) == {"EXTENSION_RIESGOSA", "CONTENIDO_EJECUTABLE"}


def test_bidi_character_in_name(tmp_path):
    result = inspect_file(make(tmp_path, "pago‮fdp.exe", FAKE_PE))
    assert "NOMBRE_BIDI" in codes(result)
    assert result.verdict == "SOSPECHOSO"


def test_many_spaces_in_name(tmp_path):
    result = inspect_file(make(tmp_path, "documento.pdf          .txt", b"texto"))
    assert "NOMBRE_ESPACIOS" in codes(result)


def test_text_with_image_extension(tmp_path):
    result = inspect_file(make(tmp_path, "perfil.jpg", b"solo texto"))
    assert codes(result) == ["TIPO_NO_COINCIDE"]


def test_text_with_unlisted_extension_is_fine(tmp_path):
    assert inspect_file(make(tmp_path, "app.toml", b"clave = 1\n")).findings == []


def test_clean_files_have_no_findings(tmp_path):
    for name, data in [("n.txt", b"hola"), ("doc.pdf", b"%PDF-1.4\n%%EOF")]:
        assert inspect_file(make(tmp_path, name, data)).verdict == "SIN INDICIOS"


def test_pdf_with_active_content(tmp_path):
    data = b"%PDF-1.4\n<< /OpenAction 2 0 R >>\n<< /S /JavaScript /JS (x) >>"
    result = inspect_file(make(tmp_path, "cuenta.pdf", data))
    assert codes(result) == ["PDF_ACTIVO"]
    assert "/OpenAction" in result.findings[0].message


def _zip(entries, password_flag=False) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def test_office_document_with_script_inside(tmp_path):
    data = _zip({"word/document.xml": b"<x/>", "word/run.vbs": b"x"})
    result = inspect_file(make(tmp_path, "contrato.docx", data))
    assert codes(result) == ["ZIP_CON_EJECUTABLES"]


def test_zip_slip_paths(tmp_path):
    result = inspect_file(make(tmp_path, "a.zip", _zip({"../../x.txt": b"x"})))
    assert "ZIP_SLIP" in codes(result)


def test_broken_zip(tmp_path):
    result = inspect_file(make(tmp_path, "roto.zip", b"PK\x03\x04basura"))
    assert codes(result) == ["ZIP_DANADO"]


def test_empty_file(tmp_path):
    result = inspect_file(make(tmp_path, "vacio.txt", b""))
    assert result.detected is EMPTY and codes(result) == ["VACIO"]


def test_ioc_list_parsing():
    sha256 = "a" * 64
    iocs = parse_iocs(f"# comentario\n\n{sha256.upper()}  # malo\nno-es-hash\n{'b' * 32}\n")
    assert iocs.entries[sha256] == "malo"
    assert iocs.entries["b" * 32] == "IOC md5"
    assert iocs.invalid_lines == [(4, "no-es-hash")]


def test_ioc_match_by_any_hash(tmp_path):
    path = make(tmp_path, "x.txt", b"dato")
    md5 = hashlib.md5(b"dato").hexdigest()
    result = inspect_file(path, parse_iocs(f"{md5} # conocido"))
    assert codes(result)[0] == "COINCIDE_CON_IOC"
    assert result.verdict == "SOSPECHOSO"


def test_samples_folder_verdicts():
    from file_inspector.iocs import load_iocs

    results, skipped = inspect_paths([SAMPLES / "archivos"], load_iocs(SAMPLES / "iocs_lab.txt"))
    verdicts = {r.path.name: r.verdict for r in results}
    assert verdicts == {
        "muestra_ioc.txt": "SOSPECHOSO",
        "imagen_perfil.jpg": "REVISAR",
        "contrato.docx": "SIN INDICIOS",
        "logo.png": "SIN INDICIOS",
        "notas.txt": "SIN INDICIOS",
        "reporte_mensual.pdf": "SIN INDICIOS",
    }
    assert skipped == []


def test_ioc_sample_hash_is_in_list():
    text = (SAMPLES / "iocs_lab.txt").read_text(encoding="utf-8")
    assert hashlib.sha256(IOC_SAMPLE).hexdigest() in text


def test_demo_files_expected_verdicts(tmp_path):
    from file_inspector.iocs import load_iocs

    create_demo(tmp_path)
    results, _ = inspect_paths([tmp_path], load_iocs(SAMPLES / "iocs_lab.txt"))
    counts = {}
    for result in results:
        counts[result.verdict] = counts.get(result.verdict, 0) + 1
    assert counts == {"SOSPECHOSO": 5, "REVISAR": 2, "SIN INDICIOS": 1}
    assert results[0].verdict == "SOSPECHOSO"  # ordenados por gravedad


def test_recursive_flag(tmp_path):
    make(tmp_path, "a.txt", b"x")
    (tmp_path / "sub").mkdir()
    make(tmp_path / "sub", "b.txt", b"y")
    assert len(inspect_paths([tmp_path])[0]) == 1
    assert len(inspect_paths([tmp_path], recursive=True)[0]) == 2
