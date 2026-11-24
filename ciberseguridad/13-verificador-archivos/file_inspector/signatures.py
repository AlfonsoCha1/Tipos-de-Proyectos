"""Firmas ("números mágicos") para identificar el tipo real de un archivo.

La extensión la elige quien nombra el archivo; los primeros bytes los exige el
programa que lo abre. Un ejecutable de Windows siempre empieza con ``MZ``
aunque se llame ``foto.jpg``. Por eso el tipo real se decide por el contenido.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FileType:
    key: str
    label: str
    extensions: frozenset[str]
    executable: bool = False


def _t(key: str, label: str, exts: str, executable: bool = False) -> FileType:
    return FileType(key, label, frozenset(exts.split()), executable)


PE = _t("pe", "ejecutable de Windows (PE)", ".exe .dll .sys .scr .cpl .ocx .com .efi .mui", True)
ELF = _t("elf", "ejecutable de Linux (ELF)", ".elf .so .bin .o .out", True)
MACHO = _t("macho", "ejecutable de macOS (Mach-O)", ".dylib .bundle .macho", True)
# Un script con "#!" no se ejecuta con doble clic en Windows ni sin permiso de
# ejecución en Linux, por eso no se marca como ejecutable binario.
SCRIPT = _t("script", "script con intérprete (#!)", ".sh .bash .py .pl .rb .php")
PDF = _t("pdf", "documento PDF", ".pdf")
PNG = _t("png", "imagen PNG", ".png")
JPEG = _t("jpeg", "imagen JPEG", ".jpg .jpeg .jfif")
GIF = _t("gif", "imagen GIF", ".gif")
ZIP = _t("zip", "archivo ZIP (también Office moderno, JAR, APK)",
         ".zip .docx .xlsx .pptx .docm .xlsm .pptm .odt .ods .odp .jar .apk .epub .xpi .vsix")
OLE = _t("ole", "documento Office antiguo o MSI (OLE)", ".doc .xls .ppt .msi .msg .dot .xlt")
RAR = _t("rar", "archivo RAR", ".rar")
SEVENZ = _t("7z", "archivo 7-Zip", ".7z")
GZIP = _t("gzip", "archivo GZIP", ".gz .tgz")
RTF = _t("rtf", "documento RTF", ".rtf .doc")
LNK = _t("lnk", "acceso directo de Windows (LNK)", ".lnk", True)
TEXT = _t("text", "texto",
          ".txt .csv .log .md .json .xml .html .htm .svg .ini .cfg .conf .yml .yaml .eml "
          ".js .vbs .ps1 .bat .cmd .sh .py .reg .hta .css .sql .rtf")
EMPTY = _t("empty", "archivo vacío", "")
UNKNOWN = _t("unknown", "binario no reconocido", "")

# (desplazamiento, bytes, tipo). Se prueban en orden.
SIGNATURES: tuple[tuple[int, bytes, FileType], ...] = (
    (0, b"MZ", PE),
    (0, b"\x7fELF", ELF),
    (0, b"\xfe\xed\xfa\xce", MACHO),
    (0, b"\xfe\xed\xfa\xcf", MACHO),
    (0, b"\xce\xfa\xed\xfe", MACHO),
    (0, b"\xcf\xfa\xed\xfe", MACHO),
    (0, b"%PDF-", PDF),
    (0, b"\x89PNG\r\n\x1a\n", PNG),
    (0, b"\xff\xd8\xff", JPEG),
    (0, b"GIF87a", GIF),
    (0, b"GIF89a", GIF),
    (0, b"PK\x03\x04", ZIP),
    (0, b"PK\x05\x06", ZIP),  # ZIP vacío
    (0, b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1", OLE),
    (0, b"Rar!\x1a\x07", RAR),
    (0, b"7z\xbc\xaf\x27\x1c", SEVENZ),
    (0, b"\x1f\x8b", GZIP),
    (0, b"{\\rtf", RTF),
    (0, b"\x4c\x00\x00\x00\x01\x14\x02\x00", LNK),
    (0, b"#!", SCRIPT),
)

# Extensiones que Windows o un intérprete ejecutan al hacer doble clic, o que
# suelen esconder macros o contenido activo.
RISKY_EXTENSIONS = frozenset(
    ".exe .scr .com .pif .bat .cmd .msi .msp .js .jse .vbs .vbe .wsf .wsh .hta .ps1 .psm1 "
    ".lnk .jar .dll .cpl .reg .iso .img .vhd .vhdx .docm .xlsm .pptm .dotm .xlam .chm .appx "
    ".msix .application .gadget .inf .sct".split()
)

# Extensiones "inocentes" que un atacante pone antes de la verdadera.
DECOY_EXTENSIONS = frozenset(
    ".pdf .doc .docx .xls .xlsx .ppt .pptx .txt .jpg .jpeg .png .gif .mp3 .mp4 .avi .zip .rar "
    ".csv .rtf .odt .html".split()
)

# Caracteres de control bidireccional: invierten el orden visual del nombre.
# "factura‮fdp.exe" se ve como "facturaexe.pdf".
BIDI_CONTROLS = frozenset("‪‫‬‭‮⁦⁧⁨⁩‎‏")


def detect_type(head: bytes) -> FileType:
    """Identifica el tipo por los primeros bytes. ``head`` basta con 8 KiB."""
    if not head:
        return EMPTY
    for offset, magic, file_type in SIGNATURES:
        if head[offset : offset + len(magic)] == magic:
            return file_type
    if b"\x00" not in head:
        try:
            head.decode("utf-8")
            return TEXT
        except UnicodeDecodeError as exc:
            # Un bloque cortado a la mitad de un carácter multibyte sigue siendo texto.
            if exc.start >= len(head) - 3:
                return TEXT
    return UNKNOWN
