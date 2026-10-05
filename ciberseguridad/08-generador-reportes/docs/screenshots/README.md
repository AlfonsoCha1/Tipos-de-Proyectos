# Capturas

Carpeta para capturas **reales** de tu propia ejecución. Todavía no hay ninguna.

Capturas sugeridas:

| Archivo sugerido | Qué mostrar | Comando |
|---|---|---|
| `01-reporte-html.png` | el HTML abierto en tu navegador (resumen y tabla de severidad) | `python -m report_generator samples/eventos.json` y abre `output/reporte.html` |
| `02-filas-rechazadas.png` | el final del reporte con las filas rechazadas y su motivo | el mismo comando; baja hasta el final |
| `03-entrada-hostil.png` | el título `<script>…` mostrado como texto | `python -m report_generator samples/eventos_hostiles.jsonl --force` |
| `04-no-sobrescribe.png` | el mensaje al repetir el comando sin `--force` | repite el comando 1 |
| `05-pruebas-windows.png` | pruebas en Windows | `python -m pytest -v` |

Después enlázalas en la sección 13 del [README del proyecto](../../README.md#13-capturas). Antes de publicar una captura, revisa que no muestre rutas con tu nombre de usuario ni datos reales.
