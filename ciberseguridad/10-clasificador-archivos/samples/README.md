# Datos sintéticos

**Todo en esta carpeta es inventado.** Cada archivo de `descargas_demo/` es una línea de texto: para clasificar solo importa la extensión.

| Qué contiene | Para qué sirve |
|---|---|
| 12 archivos con extensiones de imagen, documento, hoja de cálculo, presentación, comprimido, audio, código e instalador | una categoría distinta para cada tipo |
| `notas_sin_extension` y `archivo.desconocido` | van a `Otros` |
| `.configuracion_oculta` | archivo oculto: se queda en su lugar |
| `Imagenes/vacaciones_playa.jpg` y `vacaciones_playa.jpg` | choque de nombre: el nuevo se renombra a `vacaciones_playa (1).jpg` |
| `Proyectos/leeme.txt` | las carpetas no se mueven |

Resultado esperado de la simulación: 13 movimientos, 1 renombrado y 1 archivo que se queda. Lo verifican `tests/test_organizer.py` y `tests/test_cli.py`.

**No ejecutes `--apply` directamente sobre esta carpeta.** Copia la carpeta a otro lugar o usa `python -m file_organizer --demo`, que trabaja sobre una copia temporal.
