# Capturas

Carpeta para capturas **reales** de tu propia ejecución. Todavía no hay ninguna.

Capturas sugeridas:

| Archivo sugerido | Qué mostrar | Comando |
|---|---|---|
| `01-rango-cidr.png` | coincidencias con contexto (`:` y `-`) y el separador `--` | `python -m log_search samples/auth_lab.log --cidr 198.51.100.0/24 -C 1` |
| `02-fechas-zona.png` | filtro de un día en hora de México | `python -m log_search samples/app_mixed.log -k "acceso denegado" --from 2026-09-14 --to 2026-09-14 --tz=-06:00` |
| `03-sin-fecha.png` | el aviso de líneas sin fecha en el resumen | `python -m log_search samples/app_mixed.log -k error -C 2 --from 2026-09-14T09:12:00 --to 2026-09-14T09:13:00 --tz=-06:00` |
| `04-pruebas-windows.png` | pruebas en Windows | `python -m pytest -v` |

Después enlázalas en la sección 13 del [README del proyecto](../../README.md#13-capturas). Antes de publicar una captura, revisa que no muestre rutas con tu nombre de usuario ni datos reales.
