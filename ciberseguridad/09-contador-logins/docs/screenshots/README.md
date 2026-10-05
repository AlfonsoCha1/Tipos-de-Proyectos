# Capturas

Carpeta para capturas **reales** de tu propia ejecución. Todavía no hay ninguna.

Capturas sugeridas:

| Archivo sugerido | Qué mostrar | Comando |
|---|---|---|
| `01-resumen-lab-linux.png` | tablas por usuario e IP y líneas no interpretadas | `python -m login_counter samples/auth_lab.log` |
| `02-syslog-windows.png` | el mismo análisis en Windows, con `auth.log` | `python -m login_counter samples/auth_syslog.log --year 2026 --tz America/Mexico_City` |
| `03-csv-en-hoja-de-calculo.png` | el usuario `'=HYPERLINK(1)` neutralizado al abrir el CSV exportado | `python -m login_counter samples/logins.csv --export-csv output/conteos.csv` |
| `04-pruebas.png` | resultado de las pruebas | `python -m pytest -v` |

Después enlázalas en la sección 13 del [README del proyecto](../../README.md#13-capturas). Antes de publicar una captura, revisa que no muestre rutas con tu nombre de usuario ni datos reales.
