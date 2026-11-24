"""Crea archivos sintéticos e inofensivos para la demostración (``--demo``).

Los casos más llamativos (un "ejecutable" disfrazado de foto, una doble
extensión) no se guardan en el repositorio: se crean en una carpeta temporal,
se analizan y se borran al terminar. Ninguno es un programa real: solo empiezan
con los bytes que identifican a un ejecutable, seguidos de texto explicativo.
No pueden ejecutarse ni hacen nada.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

FAKE_PE = b"MZ" + b"\x00" * 30 + b"Archivo sintetico de laboratorio. No es un programa y no hace nada.\n"
IOC_SAMPLE = b"muestra de laboratorio marcada como indicador de compromiso\n"


def _zip(entries: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)
    return buffer.getvalue()


def demo_files() -> dict[str, bytes]:
    """Nombre -> contenido de cada archivo de la demostración."""
    return {
        "factura_noviembre.pdf.exe": FAKE_PE,
        "foto_vacaciones.jpg": FAKE_PE,
        "pago‮fdp.exe": FAKE_PE,  # se ve como "pagoexe.pdf"
        "estado_de_cuenta.pdf": (
            b"%PDF-1.4\n1 0 obj << /Type /Catalog /OpenAction 2 0 R >> endobj\n"
            b"2 0 obj << /S /JavaScript /JS (app.alert('demo de laboratorio');) >> endobj\n%%EOF\n"
        ),
        "contrato.docx": _zip({
            "[Content_Types].xml": b"<Types/>",
            "word/document.xml": b"<w:document/>",
            "word/payload.js": b"// script sintetico de laboratorio, no hace nada\n",
        }),
        "presupuesto.zip": _zip({"../../fuera_de_la_carpeta.txt": b"ruta peligrosa de laboratorio\n"}),
        "notas_reunion.txt": b"Notas de la reunion de seguridad (sintetico).\n",
        "muestra_ioc.txt": IOC_SAMPLE,
    }


def create_demo(folder: Path) -> list[Path]:
    created = []
    for name, data in demo_files().items():
        path = folder / name
        path.write_bytes(data)
        created.append(path)
    return created
