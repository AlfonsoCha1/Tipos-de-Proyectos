# Capturas

Carpeta para capturas **reales** de tu propia ejecución. Todavía no hay ninguna.

| Archivo sugerido | Qué mostrar | Comando |
|---|---|---|
| `01-subidas.png` | resumen y motivos de rechazo | `python -m file_validator samples/subidas` |
| `02-nombres.png` | doble extensión, nombre reservado y path traversal | `python -m file_validator --name factura.pdf.exe --name CON.txt --name ../../config.txt` |
| `03-pruebas.png` | resultado de las pruebas | `python -m pytest -v` |
