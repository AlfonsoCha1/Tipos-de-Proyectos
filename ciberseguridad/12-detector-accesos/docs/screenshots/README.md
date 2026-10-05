# Capturas

Carpeta para capturas **reales** de tu propia ejecución. Todavía no hay ninguna.

Capturas sugeridas:

| Archivo sugerido | Qué mostrar | Comando |
|---|---|---|
| `01-alertas-lab.png` | las 2 alertas con su explicación y evidencia | `python -m failed_login_detector samples/auth_lab.log --display-tz America/Mexico_City` |
| `02-ventana-10.png` | cómo aparecen alertas nuevas al ampliar la ventana | `python -m failed_login_detector samples/auth_lab.log --window 10` |
| `03-multi-fuente.png` | la alerta que solo aparece al combinar servidor web y VPN | `python -m failed_login_detector samples/multi_fuente/servidor_web.log samples/multi_fuente/vpn.csv --display-tz America/Mexico_City` |
| `04-pruebas-windows.png` | pruebas en Windows | `python -m pytest -v` |

Después enlázalas en la sección 13 del [README del proyecto](../../README.md#13-capturas). Antes de publicar una captura, revisa que no muestre rutas con tu nombre de usuario ni datos reales.
