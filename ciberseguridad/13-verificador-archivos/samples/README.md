# Datos sintéticos

**Todo en esta carpeta es inventado e inofensivo.** Ninguna huella de `iocs_lab.txt` corresponde a malware real.

| Archivo | Qué es | Veredicto esperado |
|---|---|---|
| `archivos/notas.txt` | texto | SIN INDICIOS |
| `archivos/logo.png` | imagen PNG real de 1×1 píxel | SIN INDICIOS |
| `archivos/reporte_mensual.pdf` | PDF mínimo sin contenido activo | SIN INDICIOS |
| `archivos/contrato.docx` | ZIP con la estructura mínima de Word | SIN INDICIOS |
| `archivos/imagen_perfil.jpg` | **texto** con extensión de imagen | REVISAR (`TIPO_NO_COINCIDE`) |
| `archivos/muestra_ioc.txt` | texto cuya SHA-256 está en `iocs_lab.txt` | SOSPECHOSO (`COINCIDE_CON_IOC`) |
| `iocs_lab.txt` | 3 huellas de laboratorio y 1 línea inválida a propósito | la línea 7 se reporta como aviso |

Los casos con "ejecutables" disfrazados no se guardan aquí para que nadie los abra por error ni alarmen a un antivirus: `python -m file_inspector --demo` los crea en una carpeta temporal y los borra al terminar (ver `file_inspector/demo.py`).

`.gitattributes` evita que Git cambie los saltos de línea en Windows, para que las huellas coincidan con las de este README y de las pruebas.
