# 08 · Generador de reportes de seguridad

> Herramienta de laboratorio y aprendizaje. Solo lee los archivos de eventos que le indiques y solo escribe los reportes que le pidas (nunca sobrescribe sin `--force`).

Convierte una lista de eventos de seguridad (JSON, JSON Lines o CSV) en un reporte legible en **Markdown** y en **HTML**: resumen ejecutivo, conteos por severidad, fuente y día, IPs y cuentas más frecuentes, tabla de todos los eventos (los más graves primero) y una lista de las filas que **no** se pudieron usar y por qué. Todo el texto que viene de los eventos se escapa, porque un reporte que se abre en un navegador no debe poder ejecutar lo que contiene un log.

[← Volver al portafolio de ciberseguridad](../README.md) · Proyectos relacionados: [09 · Contador de intentos de login](../09-contador-logins/README.md) · [12 · Detector de múltiples accesos](../12-detector-accesos/README.md)

## Contenido

1. [Qué problema resuelve](#1-qué-problema-resuelve)
2. [Instalación desde cero](#2-instalación-desde-cero)
3. [Comandos](#3-comandos)
4. [Ejemplo de entrada y salida](#4-ejemplo-de-entrada-y-salida)
5. [Archivos y carpetas](#5-archivos-y-carpetas)
6. [Funciones principales y recorrido de los datos](#6-funciones-principales-y-recorrido-de-los-datos)
7. [Dependencias](#7-dependencias)
8. [Limitaciones y errores frecuentes](#8-limitaciones-y-errores-frecuentes)
9. [Pruebas](#9-pruebas)
10. [Ejercicios](#10-ejercicios)
11. [Preguntas de entrevista](#11-preguntas-de-entrevista)
12. [Guion de demostración](#12-guion-de-demostración)
13. [Capturas](#13-capturas)

## 1. Qué problema resuelve

Las herramientas de detección producen listas de eventos que casi nadie lee completas. Un reporte útil responde rápido: *¿qué es lo más grave?, ¿cuánto pasó y cuándo?, ¿qué IP o cuenta se repite?, ¿qué datos no pude usar?* Este proyecto automatiza ese paso y lo hace con tres cuidados que importan en seguridad:

- **Nada se descarta en silencio:** las filas con fecha ilegible, severidad inventada o IP mal escrita aparecen en el reporte con su origen y el motivo.
- **El texto del evento es entrada no confiable:** se escapa para Markdown y HTML, se eliminan los caracteres de control y el HTML sale sin JavaScript ni recursos externos.
- **El reporte es reproducible:** con los mismos datos y `--generated-at` fijo, el resultado es idéntico byte a byte.

## 2. Instalación desde cero

Requisitos: Python 3.10 o superior.

**Linux Mint**

```bash
cd Tipos-de-Proyectos/ciberseguridad/08-generador-reportes
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Si aparece un error sobre `ensurepip`: `sudo apt install python3-venv` (una sola vez; la herramienta no necesita `sudo`).

**Windows (PowerShell)**

```powershell
cd Tipos-de-Proyectos\ciberseguridad\08-generador-reportes
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

Si PowerShell bloquea la activación: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` (solo vale para esa ventana), o usa `cmd` con `.venv\Scripts\activate.bat`.

## 3. Comandos

Desde la carpeta `ciberseguridad/08-generador-reportes`:

| Objetivo | Comando |
|---|---|
| Reporte Markdown **y** HTML en `output/` | `python -m report_generator samples/eventos.json` |
| Ver el Markdown en la terminal, sin crear archivos | `python -m report_generator samples/eventos.csv --stdout --display-tz=-06:00` |
| Solo HTML, con nombre y título propios | `python -m report_generator samples/eventos.csv --output-format html --name vpn --title "Reporte VPN"` |
| Juntar varios archivos de distintos formatos | `python -m report_generator samples/eventos.json samples/eventos.csv samples/eventos_hostiles.jsonl --force` |
| Reporte idéntico cada vez (para comparar) | `python -m report_generator samples/eventos.csv --generated-at 2026-10-01T12:00:00Z --force` |
| Ayuda | `python -m report_generator --help` |
| Pruebas | `python -m pytest` |

Después abre `output/reporte.html` con tu navegador (doble clic) o `output/reporte.md` en cualquier editor.

| Opción | Uso | Por defecto |
|---|---|---|
| `--input-format` | `auto`, `json`, `jsonl`, `csv` | `auto` (por extensión) |
| `--output-format` | `md`, `html`, `both` | `both` |
| `--output-dir` | carpeta de salida (se crea si no existe) | `output` |
| `--name` | nombre base de los archivos (letras, números, `.`, `-`, `_`; sin rutas) | `reporte` |
| `--title` | título del reporte | `Reporte de eventos de seguridad` |
| `--top N` | cuántas IPs y cuentas listar (1 a 50) | `5` |
| `--tz` / `--display-tz` | zona para fechas sin desplazamiento / zona del reporte | `UTC` / `UTC` |
| `--generated-at` | fecha de generación fija (ISO 8601) | ahora (UTC) |
| `--stdout` | imprime el Markdown y no escribe archivos | desactivado |
| `--force` | permite sobrescribir reportes existentes | desactivado |

> **Zonas con signo negativo:** escribe `--display-tz=-06:00` (con `=`). Con un espacio, `argparse` cree que `-06:00` es otra opción y falla. Con un nombre IANA no hay problema: `--display-tz America/Mexico_City` (en Windows requiere `tzdata`, que ya instala `requirements.txt`).

### Esquema de los eventos

| Campo | ¿Obligatorio? | Detalle |
|---|---|---|
| `timestamp` | sí | ISO 8601: `2026-09-14T08:10:02-06:00`, `…Z` o sin zona (se usa `--tz`) |
| `severity` | sí | `critica`, `alta`, `media`, `baja`, `info` (también `critical`, `high`, `medium`, `low`; sin distinguir mayúsculas) |
| `title` | sí | máximo 200 caracteres |
| `source` | no | sistema que generó el evento (máx. 100) |
| `description` | no | detalle (máx. 2 000); se muestra para eventos críticos y altos |
| `ip` | no | IPv4 o IPv6 válida; se normaliza (`::ffff:192.0.2.1` → `192.0.2.1`) |
| `user` | no | cuenta afectada (máx. 100) |

JSON: una lista de objetos, o un objeto con la clave `events`. JSON Lines: un objeto por línea. CSV: encabezado con al menos `timestamp,severity,title`; las columnas extra se ignoran.

## 4. Ejemplo de entrada y salida

Salida real sobre `samples/eventos.csv` (datos sintéticos), ejecutada con Python 3.13 en Linux:

```text
$ python -m report_generator samples/eventos.csv --stdout --generated-at 2026-10-01T12:00:00Z --display-tz=-06:00
# Reporte de eventos de seguridad

Generado: 2026-10-01 06:00:00-06:00 · herramienta report_generator 0.1.0

- Archivos: eventos.csv
- Filas leídas: 6 · eventos válidos: 5 · filas rechazadas: 1

> Reporte generado automáticamente a partir de los datos recibidos. No valida que los eventos sean ciertos ni completos; úsalo como apoyo para la revisión humana.

## Resumen ejecutivo

- Hay 2 evento(s) de severidad crítica o alta (1 crítica(s), 1 alta(s)); revísalos primero.
- Periodo cubierto: 2026-09-16 08:00:00-06:00 a 2026-09-16 09:45:00-06:00.

## Eventos por severidad

| Severidad | Eventos |
|---|---|
| Crítica | 1 |
| Alta | 1 |
| Media | 1 |
| Baja | 1 |
| Informativa | 1 |
...
## Todos los eventos (más graves primero)

| Hora | Severidad | Fuente | Título | IP | Cuenta | Origen |
|---|---|---|---|---|---|---|
| 2026-09-16 09:15:00-06:00 | Crítica | correo | =HYPERLINK("https://ejemplo.invalid","clic") | `203.0.113.9` |  | eventos.csv:5 |
| 2026-09-16 08:00:00-06:00 | Alta | vpn | Inicio de sesión desde país inusual | `192.0.2.15` | carlos | eventos.csv:2 |
| 2026-09-16 08:30:00-06:00 | Media | vpn | Intentos fallidos de VPN | `192.0.2.15` | carlos | eventos.csv:3 |
| 2026-09-16 09:00:00-06:00 | Baja | directorio | Usuario creado |  | diana | eventos.csv:4 |
| 2026-09-16 09:45:00-06:00 | Informativa | respaldos | Respaldo completado |  |  | eventos.csv:6 |
...
## Filas rechazadas

Estas filas no se incluyeron en las estadísticas porque no cumplen el esquema:

| Origen | Motivo |
|---|---|
| eventos.csv:7 | la fila tiene menos columnas que el encabezado |
```

(`...` marca partes recortadas aquí; la herramienta imprime el reporte completo.)

**Mensajes de la ejecución normal** (`python -m report_generator samples/eventos.json`):

```text
Reporte guardado en output/reporte.md
Reporte guardado en output/reporte.html
Aviso: 5 fila(s) rechazada(s); aparecen en el reporte.
Eventos válidos: 9 de 14 fila(s).
```

(`Aviso:` sale por el canal de errores; `eventos.json` incluye 5 filas inválidas a propósito.) Si repites el comando, la herramienta se niega a pisar el reporte:

```text
Error: output/reporte.md ya existe. Usa --force para sobrescribirlo o cambia --name.
```

**Filas rechazadas de `eventos.json`** (el reporte las lista con su origen):

| Origen | Motivo |
|---|---|
| `eventos.json[10]` | severidad desconocida: 'urgente' (usa critica, alta, media, baja, info) |
| `eventos.json[11]` | fecha con formato no reconocido: 'ayer por la tarde' |
| `eventos.json[12]` | faltan campos obligatorios: title |
| `eventos.json[13]` | IP no válida: '192.0.2.999' |
| `eventos.json[14]` | la fila no es un objeto con campos |

**Entrada hostil** (`samples/eventos_hostiles.jsonl`): un título `<script>alert('xss')</script>` aparece en el HTML como texto (`&lt;script&gt;…`), nunca como etiqueta; las secuencias ANSI y los saltos de línea se convierten en `\x1b` y espacios. Lo comprueban las pruebas y puedes verlo abriendo `output/reporte.html` después de generar ese archivo.

## 5. Archivos y carpetas

```
08-generador-reportes/
├── README.md
├── requirements.txt          dependencias de ejecución (solo tzdata, y solo en Windows)
├── requirements-dev.txt      incluye pytest
├── pytest.ini
├── report_generator/
│   ├── __main__.py           permite "python -m report_generator"
│   ├── cli.py                argumentos, plan de salida (sin pisar archivos) y códigos de salida
│   ├── loader.py             lee JSON/JSONL/CSV y valida cada fila contra el esquema
│   ├── models.py             Event, RejectedRow y las severidades
│   ├── analysis.py           estadísticas y frases del resumen (funciones puras)
│   ├── render.py             Markdown y HTML, con el escape de texto no confiable
│   └── timeutils.py          fechas y zonas (copia compartida con 09, 11 y 12)
├── samples/                  datos sintéticos (ver samples/README.md)
├── tests/                    pruebas automáticas
└── docs/screenshots/         capturas reales que agregarás tú
```

No hay `config/settings.json`: los parámetros se indican en la línea de comandos.

## 6. Funciones principales y recorrido de los datos

1. `cli.main` valida las opciones y calcula **antes de leer nada** qué archivos escribiría (`_plan_outputs`): si alguno existe y no hay `--force`, se detiene sin tocar nada.
2. `loader.load_files` lee cada archivo según su formato (`_iter_rows`) y pasa cada fila por `validate_row`, que devuelve un `Event` válido o un `RejectedRow` con el motivo. Hay topes: 20 MB por archivo y 50 000 filas.
3. `analysis.summarize` calcula conteos por severidad/fuente/día y los "top" con un orden determinista (más frecuente primero y, si empatan, por texto), y `build_highlights` genera las frases del resumen con reglas fijas y verificables: no usa IA ni puntajes.
4. `render.render_markdown` y `render.render_html` construyen el reporte. Todo texto del evento pasa por `md_escape` o `html_escape` (que antes colapsa saltos de línea y escapa caracteres de control).
5. `cli.main` escribe los archivos en UTF-8 con saltos de línea `\n` (o imprime con `--stdout`) y avisa cuántas filas se rechazaron.

## 7. Dependencias

Solo la biblioteca estándar de Python 3.10+ (`json`, `csv`, `html`, `ipaddress`, `argparse`). `requirements.txt` incluye `tzdata`, **solo en Windows**, porque Windows no trae la base de zonas horarias que usa `zoneinfo` (Linux Mint sí). `pytest` es solo para las pruebas.

## 8. Limitaciones y errores frecuentes

- **El reporte no valida la verdad de los datos:** resume lo que recibe. Un evento falso aparece como cualquier otro.
- **El HTML está endurecido pero no es "seguro por magia":** sin JavaScript, sin recursos externos y con `Content-Security-Policy`; aun así, no publiques reportes con datos sensibles en lugares públicos.
- **El Markdown se escapa de forma conservadora** (`*`, `_`, `[`, `]`, `|`, `` ` ``, `#`, `!`, `~`, `<`, `>`, `&`), por lo que en el texto bruto verás barras invertidas; al renderizarse se ven bien.
- **`=HYPERLINK(...)` en un título no es peligroso aquí** (el reporte no es una hoja de cálculo). El riesgo de inyección de fórmulas aplica a exportaciones CSV, como en los proyectos 09 y 12.
- **CSV con comas en un campo:** deben ir entre comillas (`"Con, coma"`). Una fila con menos columnas que el encabezado se rechaza.
- **Fechas sin zona** se interpretan en `--tz` (por defecto UTC). Si tus registros están en hora local, indícalo.
- **Una fila válida no implica un evento importante:** las frases del resumen son conteos simples (por ejemplo "IP con 3 o más eventos"), no un análisis de riesgo.
- **Zonas con signo negativo:** `--display-tz=-06:00`, con `=`.
- **Códigos de salida:** 0 si se generó el reporte (aunque haya filas rechazadas), 1 si hay error de opciones, de entrada o de escritura, o si no queda ningún evento válido.

## 9. Pruebas

```bash
python -m pytest
python -m pytest -v tests/test_render.py
```

| Archivo | Qué comprueba |
|---|---|
| `test_loader.py` | validación de cada campo y de sus límites, severidades en inglés, IPs, fechas con y sin zona, JSON (lista y `events`), JSON Lines con línea rota, CSV con BOM/CRLF/comillas/fila corta/columnas extra, archivo inexistente, no UTF-8, demasiado grande, demasiadas filas |
| `test_render.py` | conteos y ceros, orden determinista, días en la zona de visualización, frases del resumen, reporte idéntico con datos desordenados, escape de Markdown y HTML, HTML hostil sin etiquetas ni atributos peligrosos (con `html.parser`), CSP y sin JavaScript, severidad siempre como texto, tabla sin romperse por `\|` y saltos de línea, filas rechazadas |
| `test_cli.py` | los comandos de esta guía, un solo formato, `--stdout` sin archivos, **no sobrescribir sin `--force`**, reproducibilidad, zona de visualización, título hostil, opciones inválidas (y que no se cree ninguna carpeta), errores sin *traceback* |

**Pruebas ejecutadas** al preparar esta entrega (Linux x86_64 en la nube, 5 de octubre de 2026): `python -m pytest` → **59 passed** con Python 3.10.20, 3.11.17, 3.12.3, 3.13.16 y 3.14.6 (pytest 9.1.1), cada versión en un entorno virtual nuevo instalado con `requirements-dev.txt`. También `python tools/check_shared_copies.py` → OK y `python menu.py --test-all` → `Proyectos probados: 4 | con fallos: 0`. Además revisé el HTML generado en un navegador (Chromium) para comprobar que se ve bien y que el contenido hostil no abre ningún diálogo ni ejecuta código.

**Pruebas pendientes de ejecutar por ti**: Linux Mint y Windows en tus equipos (`python -m pytest`), y abrir `output/reporte.html` en tu navegador. Anótalas en [docs/METODOLOGIA.md](../docs/METODOLOGIA.md) cuando las hagas.

## 10. Ejercicios

1. **Leer las alertas del proyecto 12.** Agrega `--input-format detector` que lea el JSON que exporta `failed_login_detector --export-json` y lo convierta en eventos (la severidad de la alerta ya viene calculada). Así encadenas detección y reporte sin copiar nada a mano.
2. **Gráfica sin dependencias.** Agrega al HTML una barra por severidad hecha solo con `<div>` y CSS (ancho proporcional al conteo), cuidando que el número siga visible como texto.
3. **Resumen comparativo.** Agrega `--compare ARCHIVO_ANTERIOR` que muestre cuántos eventos nuevos hay por severidad respecto a un reporte previo. Piensa qué identifica a un evento como "el mismo" entre ejecuciones.

## 11. Preguntas de entrevista

**1. ¿Por qué escapas el contenido si "es solo un reporte"?**
Porque el contenido viene de logs, y los logs los influye quien ataca (un nombre de usuario puede ser `<script>…</script>`). Un reporte HTML que alguien abre en su navegador sería un vector de XSS almacenado. Escapo con `html.escape` en cada punto donde entra texto del evento, y como defensa adicional el HTML no lleva JavaScript y declara una `Content-Security-Policy` que bloquea scripts y recursos externos. Una prueba parsea el HTML generado con un evento hostil y verifica que no aparezcan etiquetas ni atributos `on…`.

**2. ¿Qué haces con los datos inválidos?**
No los descarto en silencio: cada fila rechazada se devuelve con su origen (`archivo:línea` o `archivo[índice]`) y el motivo, y aparece en el reporte y en un aviso. Si ningún evento es válido, termina con error en vez de generar un reporte vacío que parezca "todo bien".

**3. ¿Cómo garantizas que el reporte sea reproducible?**
Todos los ordenamientos son deterministas (gravedad, fecha, origen; los empates de los "top" se resuelven por texto), no hay datos aleatorios y la fecha de generación puede fijarse con `--generated-at`. Una prueba genera el mismo reporte dos veces con los eventos en orden inverso y compara los bytes.

**4. ¿Por qué evitar sobrescribir archivos por defecto?**
Un reporte puede ser evidencia de un incidente; pisarlo por error es destruirla. La herramienta calcula las rutas antes de leer nada y se detiene si alguna existe, salvo `--force`. Además `--name` solo admite caracteres seguros, así que no se puede escapar de la carpeta de salida con `../`.

**5. ¿Cómo generas el "resumen ejecutivo" sin IA?**
Con reglas fijas sobre conteos (eventos críticos/altos, la IP o cuenta más repetida a partir de 3 eventos). Cada frase se puede verificar contra las tablas del propio reporte. Para un primer reporte prefiero esa transparencia a un texto generado que suene bien pero que nadie pueda comprobar.

## 12. Guion de demostración

Duración aproximada: 2 a 3 minutos.

1. (10 s) "Convierte eventos de seguridad en un reporte Markdown y HTML. Datos sintéticos; solo escribe donde yo le indico."
2. (30 s) Abre `samples/eventos.json`: "hay filas buenas y filas malas a propósito: una severidad inventada, una fecha ilegible, una IP imposible".
3. (30 s) Ejecuta `python -m report_generator samples/eventos.json` y abre `output/reporte.html`: resumen ejecutivo, severidad con texto y color, y al final las filas rechazadas con su motivo.
4. (20 s) Repite el comando: "se niega a sobrescribir sin `--force`".
5. (30 s) Ejecuta con `samples/eventos_hostiles.jsonl --force` y abre el HTML: "el `<script>` aparece como texto; no se ejecuta".
6. (20 s) Ejecuta `samples/eventos.csv --stdout --display-tz=-06:00`: "misma información en Markdown, con la hora de México".
7. (15 s) Abre `tests/test_render.py` y muestra la prueba del HTML hostil.

## 13. Capturas

Pendiente: agrega capturas reales en [`docs/screenshots/`](docs/screenshots/README.md) después de ejecutar la herramienta en tu equipo.

<!-- Ejemplo, cuando exista el archivo:
![Reporte HTML abierto en Windows](docs/screenshots/01-reporte-html-windows.png)
-->
