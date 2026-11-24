# Datos sintéticos

**Todo en esta carpeta es inventado** para practicar. No son documentos reales.

| Archivo en `carpeta_demo/` | Contenido | Para qué sirve |
|---|---|---|
| `documentos/reporte_q3.txt`, `documentos/copia de reporte_q3.txt`, `respaldo/reporte_final.txt` | el mismo reporte (70 B) | grupo de 3 con nombres distintos |
| `.cache/reporte_q3.txt` | el mismo reporte, en carpeta oculta | solo aparece con `--include-hidden` |
| `imagenes/logo.svg`, `respaldo/logo (copia).svg` | el mismo SVG (100 B) | grupo de 2, nombre con espacios y paréntesis |
| `documentos/notas.txt`, `respaldo/notas_viejas.txt` | 24 B cada uno, **contenido distinto** | demuestra que el mismo tamaño no basta |
| `vacio.txt`, `respaldo/vacio_copia.txt` | vacíos | solo forman grupo con `--min-size 0` |

Resultado esperado sin opciones: 7 archivos considerados, 2 grupos, 3 copias sobrantes, 240 B recuperables. Con `--include-hidden --min-size 0`: grupos de 4, 2 y 2. Lo verifican las pruebas de `tests/test_scanner.py`.

`.gitattributes` pide a Git no convertir saltos de línea en estos archivos, para que tamaños y huellas sean iguales en Linux y Windows.
