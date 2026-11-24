# Datos sintéticos

**Todo en esta carpeta es inventado e inofensivo.** Simula archivos que subieron usuarios a un formulario.

| Archivo en `subidas/` | Qué es | Resultado con `config/settings.json` |
|---|---|---|
| `foto_perfil.png` | PNG real de 1×1 píxel | ACEPTADO |
| `contrato_firmado.pdf` | PDF mínimo | ACEPTADO |
| `notas.txt` | texto | ACEPTADO |
| `clientes.csv` | CSV con datos inventados | ACEPTADO |
| `manual_usuario.txt` | texto de unos 3 KB | ACEPTADO (RECHAZADO con las reglas estrictas por tamaño y extensión) |
| `comprobante.pdf` | **texto** con extensión de PDF | RECHAZADO: `CONTENIDO_NO_COINCIDE` |
| `presentacion.pptx` | ZIP con extensión de PowerPoint | RECHAZADO: `EXTENSION_NO_PERMITIDA` |
| `.htaccess` | configuración de servidor web | RECHAZADO: `NOMBRE_OCULTO` y extensión |
| `archivo_vacio.txt` | 0 bytes | RECHAZADO: `ARCHIVO_VACIO` |
| `LEEME` | texto sin extensión | RECHAZADO: `SIN_EXTENSION` |

`reglas_estrictas.json` acepta solo `.pdf`, `.png` y `.jpg` de hasta 2 KB: con ellas solo pasan `contrato_firmado.pdf` y `foto_perfil.png`.

Los nombres que no se pueden crear en Windows (`CON.txt`, `informe.pdf.`) o que serían peligrosos de guardar (`factura.pdf.exe`) se prueban con `--name`, sin crear archivos. Los resultados están verificados por `tests/test_rules.py`.
