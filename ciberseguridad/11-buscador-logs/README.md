# 11 · Buscador en logs

> Herramienta de laboratorio y aprendizaje. **Solo lee** archivos: no modifica, no borra, no ejecuta nada de lo que analiza ni se conecta a ningún servicio.

Busca palabras, direcciones IP, rangos de red (CIDR) y rangos de fechas en uno o varios archivos de log y muestra cada coincidencia con líneas de contexto, como un `grep` más consciente de lo que es una IP o una fecha. Lee los archivos línea por línea (no los carga completos en memoria), escapa el texto antes de mostrarlo y dice claramente cuando una línea no se pudo evaluar.

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

En una investigación se hacen siempre las mismas preguntas sobre un log: *¿qué pasó con esta cuenta? ¿qué hizo esta IP o toda esta red? ¿qué ocurrió entre las 9:00 y las 9:30? ¿qué había justo antes y después de este error?* Un `grep` simple responde la primera, pero se equivoca con las demás: `192.0.2.1` también coincide con `192.0.2.10`, no entiende rangos como `198.51.100.0/24` y no compara fechas escritas en zonas horarias distintas.

Esta herramienta resuelve esos cuatro casos con criterios que se combinan, lee archivos grandes sin cargarlos en memoria y es honesta con lo que no puede evaluar (por ejemplo, líneas de un *traceback* que no traen fecha).

## 2. Instalación desde cero

Requisitos: Python 3.10 o superior.

**Linux Mint**

```bash
cd Tipos-de-Proyectos/ciberseguridad/11-buscador-logs
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Si aparece un error sobre `ensurepip`: `sudo apt install python3-venv` (una sola vez; la herramienta no necesita `sudo`).

**Windows (PowerShell)**

```powershell
cd Tipos-de-Proyectos\ciberseguridad\11-buscador-logs
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

Si PowerShell bloquea la activación: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` (solo vale para esa ventana), o usa `cmd` con `.venv\Scripts\activate.bat`.

## 3. Comandos

Desde la carpeta `ciberseguridad/11-buscador-logs`:

| Objetivo | Comando |
|---|---|
| Todo lo de una red | `python -m log_search samples/auth_lab.log --cidr 198.51.100.0/24 -C 1` |
| Una palabra en un día (hora de México) | `python -m log_search samples/app_mixed.log -k "acceso denegado" --from 2026-09-14 --to 2026-09-14 --tz=-06:00` |
| Palabra **y** IP a la vez | `python -m log_search samples/app_mixed.log -k admin --ip 203.0.113.50 --count` |
| Errores en una franja con contexto | `python -m log_search samples/app_mixed.log -k error -C 2 --from 2026-09-14T09:12:00 --to 2026-09-14T09:13:00 --tz=-06:00` |
| Syslog sin año | `python -m log_search samples/auth_syslog.log --year 2026 -k "failed password" --from 2026-09-14T08:20:00 --to 2026-09-14T08:21:00` |
| Distinguir mayúsculas | `python -m log_search samples/app_mixed.log -k ADMIN --case-sensitive` |
| Exigir todas las palabras | `python -m log_search samples/app_mixed.log -k acceso -k admin --all` |
| Guardar resultados | `python -m log_search samples/auth_lab.log -k admin -C 1 --export-json output/admin.json` |
| Ayuda | `python -m log_search --help` |
| Pruebas | `python -m pytest` |

| Opción | Uso | Por defecto |
|---|---|---|
| `-k`, `--keyword` | palabra o frase (repetible) | — |
| `--all` | exigir todas las palabras en vez de alguna | alguna |
| `--case-sensitive` | distinguir mayúsculas | no distingue |
| `--ip` / `--cidr` | IP exacta / rango de red (repetibles) | — |
| `--from` / `--to` | `AAAA-MM-DD` (día completo) o `AAAA-MM-DDTHH:MM:SS`; ambos inclusivos | sin límite |
| `--tz` | zona para `--from`/`--to` y para fechas sin desplazamiento | `UTC` |
| `--year` | año para syslog tradicional | año actual |
| `-C`, `--context` | líneas de contexto antes y después (0 a 20) | `0` |
| `--max-matches` | máximo de coincidencias por archivo (1 a 10 000) | `200` |
| `--count` | solo totales | desactivado |
| `--export-json` / `--force` | guardar resultados / permitir sobrescribir | desactivado |

> **Zonas con signo negativo:** escribe `--tz=-06:00` (con `=`). Con un espacio, `argparse` cree que `-06:00` es otra opción y falla. Con un nombre IANA no hay problema: `--tz America/Mexico_City` (en Windows requiere `tzdata`, que ya instala `requirements.txt`).

### Cómo se combinan los criterios

- **Palabras:** coincide si la línea contiene **alguna** (o **todas** con `--all`).
- **IPs y rangos:** coincide si la línea trae **alguna** IP igual a una de `--ip` **o** dentro de un `--cidr`. Se comparan direcciones completas: `--ip 192.0.2.1` no coincide con `192.0.2.10`.
- **Fechas:** coincide si la fecha al inicio de la línea está entre `--from` y `--to`.
- **Entre tipos** (palabras, IPs, fechas) se exige que se cumplan **todos** los que se indiquen. Si no indicas ninguno, la herramienta se detiene con un error.

## 4. Ejemplo de entrada y salida

Salida real de la herramienta sobre los datos sintéticos de `samples/` (ejecutada con Python 3.13 en Linux).

**Todo lo de una red, con una línea de contexto:**

```text
$ python -m log_search samples/auth_lab.log --cidr 198.51.100.0/24 -C 1
Criterios (todos deben cumplirse):
  - IPs o rangos: 198.51.100.0/24

== samples/auth_lab.log ==
    3- # Todo es inventado: usuarios ficticios e IPs de rangos reservados para
    4: # documentación (RFC 5737: 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24;
    5- # RFC 3849: 2001:db8::/32). No corresponden a personas ni equipos reales.
   --
   21- 2026-09-14T08:30:00-06:00 LOGIN_FAILURE user=carlos ip=192.0.2.30 method=password
   22: 2026-09-14T09:15:00-06:00 LOGIN_FAILURE user=root ip=198.51.100.23 method=password
   23: 2026-09-14T09:15:25-06:00 LOGIN_FAILURE user=test ip=198.51.100.23 method=password
   24: 2026-09-14T09:15:51-06:00 LOGIN_FAILURE user=oracle ip=198.51.100.23 method=password
   25: 2026-09-14T09:16:20-06:00 LOGIN_FAILURE user=guest ip=198.51.100.23 method=password
   26: 2026-09-14T09:16:48-06:00 LOGIN_FAILURE user=postgres ip=198.51.100.23 method=password
   27: 2026-09-14T09:17:30-06:00 LOGIN_FAILURE user=ubuntu ip=198.51.100.23 method=password
   28- 2026-09-14T09:05:00-06:00 LOGIN_FAILURE user=carlos ip=192.0.2.30 method=password

Resumen
  samples/auth_lab.log: 7 coincidencia(s) en 44 línea(s) leída(s)
Total: 7 coincidencia(s) en 1 archivo(s).
```

Cómo leerla: `:` marca una **coincidencia** y `-` una línea de **contexto** (igual que `grep`); `--` separa bloques que no son contiguos. La línea 4 coincide porque el comentario del archivo de ejemplo menciona ese rango: la herramienta busca texto, no entiende comentarios (ver [limitaciones](#8-limitaciones-y-errores-frecuentes)).

**Fecha con zona horaria y palabra:**

```text
$ python -m log_search samples/app_mixed.log -k "acceso denegado" --from 2026-09-14 --to 2026-09-14 --tz=-06:00
Criterios (todos deben cumplirse):
  - palabras (sin distinguir mayúsculas): 'acceso denegado'
  - fechas (UTC): desde 2026-09-14T06:00:00+00:00 hasta 2026-09-15T05:59:59+00:00

== samples/app_mixed.log ==
   16: 2026-09-14T15:21:10Z ERROR app: acceso denegado user=admin ip=2001:db8::50

Resumen
  samples/app_mixed.log: 1 coincidencia(s) en 20 línea(s) leída(s)
Total: 1 coincidencia(s) en 1 archivo(s).
```

"El 14 de septiembre" en hora de México es de 06:00Z a 05:59Z del día siguiente. La línea 22 de `app_mixed.log` (`Acceso denegado ... 2026-09-15T08:02:00-06:00`) queda fuera: es del día 15.

**Líneas sin fecha:** el *traceback* del archivo de ejemplo no empieza con fecha, así que con un filtro de fechas no puede evaluarse. La herramienta lo dice en vez de ocultarlo:

```text
$ python -m log_search samples/app_mixed.log -k error -C 2 --from 2026-09-14T09:12:00 --to 2026-09-14T09:13:00 --tz=-06:00
...
   10: 2026-09-14T09:12:30-06:00 ERROR app: fallo al consultar la base de datos
   11-     Traceback (most recent call last):
   12-       File "db.py", line 42, in query

Resumen
  samples/app_mixed.log: 1 coincidencia(s) en 20 línea(s) leída(s)  [2 sin fecha reconocible (excluidas por el filtro de fechas)]
Total: 1 coincidencia(s) en 1 archivo(s).
```

**Texto malicioso:** una línea con secuencias ANSI se muestra con el carácter de control escapado, así no puede cambiar colores ni borrar la pantalla de tu terminal:

```text
$ python -m log_search samples/app_mixed.log -k rojo
...
   19: 2026-09-15T08:01:00-06:00 WARN  app: usuario \x1b[31mROJO\x1b[0m intentó entrar ip=198.51.100.23
```

Los conteos de estos ejemplos están verificados con `grep` independiente y con `tests/test_cli.py`.

## 5. Archivos y carpetas

```
11-buscador-logs/
├── README.md
├── requirements.txt          dependencias de ejecución (solo tzdata, y solo en Windows)
├── requirements-dev.txt      incluye pytest
├── pytest.ini
├── log_search/
│   ├── __main__.py           permite "python -m log_search"
│   ├── cli.py                argumentos, mensajes y códigos de salida
│   ├── matcher.py            criterios, lectura incremental y contexto (sin print)
│   ├── report.py             salida de terminal y exportación JSON, con escape de texto
│   └── timeutils.py          fechas y zonas (copia compartida con 08, 09 y 12)
├── samples/                  datos sintéticos (ver samples/README.md)
├── tests/                    pruebas automáticas
└── docs/screenshots/         capturas reales que agregarás tú
```

No hay `config/settings.json` en este proyecto: no hay umbrales que ajustar, todo se indica con opciones de la línea de comandos.

## 6. Funciones principales y recorrido de los datos

1. `cli.main` valida que los archivos existan, carga la zona (`timeutils.load_timezone`) y construye la consulta.
2. `matcher.build_query` valida y normaliza los criterios (IPs compactadas, rangos CIDR, fechas convertidas a UTC) y devuelve una `Query` inmutable. Rechaza criterios inválidos antes de abrir ningún archivo.
3. `matcher.search_file` recorre el archivo con `read_lines`, un generador que lee línea por línea, recorta las de más de 10 000 caracteres y decodifica UTF-8 sin fallar con bytes inválidos.
4. Por cada línea, `matcher.line_matches` evalúa palabras, IPs (`find_ips` extrae candidatas y `ipaddress` decide cuáles lo son) y fecha (`extract_timestamp`, ISO 8601 o syslog con `--year`).
5. El contexto se resuelve con un `deque` de tamaño fijo para las líneas anteriores y un contador para las posteriores. Solo se guardan coincidencias y contexto (hasta `--max-matches`), nunca el archivo entero.
6. `report.render_text` escapa los caracteres de control y arma la salida; `export_json` guarda lo mismo en un archivo (sin sobrescribir sin `--force`).

## 7. Dependencias

Solo la biblioteca estándar de Python 3.10+. `requirements.txt` incluye `tzdata`, **solo en Windows**, porque Windows no trae la base de zonas horarias que usa `zoneinfo` (Linux Mint sí). `pytest` es solo para las pruebas.

## 8. Limitaciones y errores frecuentes

- **Busca texto, no entiende comentarios ni estructura.** Una línea de comentario que mencione una IP coincide (se ve en el ejemplo de la sección 4).
- **Líneas sin fecha:** con `--from`/`--to`, las líneas de continuación (*tracebacks*, mensajes de varias líneas) no se pueden evaluar y se **excluyen**; el resumen las cuenta. Usa `-C` para verlas como contexto de la línea con fecha.
- **Formatos de fecha:** ISO 8601 y syslog tradicional al inicio de la línea. Otros (por ejemplo `14/Sep/2026:08:00:01 +0000` de Apache) no se reconocen: ver ejercicio 2.
- **Syslog no trae año:** se usa `--year` o el año actual. Si el log es de otro año y no lo indicas, el filtro de fechas dará resultados incorrectos.
- **IPs:** se reconocen IPv4 e IPv6 que aparezcan como palabra aparte; una IP pegada a letras (`ip192.0.2.1x`) no. Las IPv4 mapeadas en IPv6 (`::ffff:192.0.2.1`) se tratan como IPv4.
- **Límites de seguridad:** líneas de más de 10 000 caracteres se recortan; el máximo por defecto es 200 coincidencias por archivo (puedes subirlo hasta 10 000). Si se alcanza el límite, el resumen lo avisa.
- **Zonas con signo negativo:** `--tz=-06:00`, con `=`.
- **Rangos CIDR con bits de host** (`192.0.2.10/24`) se aceptan y se normalizan a `192.0.2.0/24`.
- **Códigos de salida:** 0 si la búsqueda terminó (haya o no coincidencias; "sin coincidencias" no es un error), 1 si hay un error de entrada o de criterios.

## 9. Pruebas

```bash
python -m pytest
python -m pytest -v tests/test_matcher.py
```

| Archivo | Qué comprueba |
|---|---|
| `test_matcher.py` | criterios inválidos, normalización de IPs, rangos IPv4/IPv6, IP exacta (sin coincidir por prefijo), palabras alguna/todas, mayúsculas, combinación Y entre tipos, límites inclusivos de fechas, zonas horarias, syslog con año, líneas sin fecha, contexto antes/después/solapado/en los bordes, `--max-matches`, líneas muy largas, BOM/CRLF/bytes inválidos, archivo vacío |
| `test_cli.py` | los comandos de esta guía sobre los datos de ejemplo, escape de ANSI, errores sin *traceback*, varios archivos, exportación JSON y protección contra sobrescritura |

**Pruebas ejecutadas** al preparar esta entrega (Linux x86_64 en la nube, 5 de octubre de 2026): `python -m pytest` → **60 passed** con Python 3.10.20, 3.11.17, 3.12.3, 3.13.16 y 3.14.6 (pytest 9.1.1), cada versión en un entorno virtual nuevo instalado con `requirements-dev.txt`. También `python tools/check_shared_copies.py` → OK y `python menu.py --test-all` → `Proyectos probados: 4 | con fallos: 0`. Los conteos de los ejemplos se verificaron además con `grep`.

**Pruebas pendientes de ejecutar por ti**: Linux Mint y Windows en tus equipos (`python -m pytest`). Anótalas en [docs/METODOLOGIA.md](../docs/METODOLOGIA.md) cuando las hagas.

## 10. Ejercicios

1. **Búsqueda con expresiones regulares.** Agrega `--regex PATRÓN`. Debes compilar el patrón una sola vez, capturar `re.error` con un mensaje claro y pensar en el riesgo de patrones que tardan mucho (ReDoS): ¿cómo limitarías el tiempo o el tamaño?
2. **Formato de Apache/Nginx.** Reconoce fechas como `[14/Sep/2026:08:00:01 +0000]` en `extract_timestamp` y agrega un archivo de ejemplo sintético con sus pruebas.
3. **Estadísticas por IP.** Agrega `--top-ips N`, que al final liste las IPs más frecuentes entre las líneas coincidentes (usa `collections.Counter` y `find_ips`).

## 11. Preguntas de entrevista

**1. ¿Por qué no usaste simplemente `grep`?**
`grep` compara texto: `192.0.2.1` coincide con `192.0.2.10`, no entiende rangos de red ni compara fechas en zonas horarias distintas. Aquí cada IP candidata se valida con `ipaddress` y se compara completa o contra una red, y las fechas se convierten a UTC antes de compararse. Para una búsqueda de texto simple, `grep` sigue siendo la herramienta correcta.

**2. ¿Cómo manejas archivos muy grandes?**
Leo línea por línea con un generador y solo guardo las coincidencias y su contexto. Las líneas anteriores viven en un `deque` de tamaño fijo y las posteriores se cuentan con un contador. Además hay topes: línea máxima de 10 000 caracteres (el resto se descarta sin acumularlo) y `--max-matches`. La memoria depende de las coincidencias, no del tamaño del archivo.

**3. ¿Qué pasa con las líneas sin fecha cuando filtro por fecha?**
No se pueden evaluar, así que se excluyen, pero no en silencio: el resumen las cuenta. Es una decisión deliberada: preferí un filtro estricto y explícito a "heredar" la fecha de la línea anterior, que sería una suposición que puede estar mal. `-C` permite ver esas líneas como contexto.

**4. ¿Qué riesgos hay al mostrar texto de un log en la terminal?**
Un log es entrada no confiable: una línea puede traer secuencias ANSI para cambiar colores, mover el cursor u ocultar texto. Antes de imprimir reemplazo los caracteres de control por su forma escapada (`\x1b`), y hay una prueba con un log que lo intenta.

**5. ¿Cómo se combinan los criterios y por qué?**
Alguna palabra (o todas con `--all`), alguna IP o rango, y fecha en el intervalo; entre tipos distintos se exige todo. Es lo que se espera al investigar ("fallos de esta red entre estas horas"). Lo documenté y lo cubren pruebas, porque la ambigüedad entre Y y O es una fuente clásica de falsos hallazgos.

## 12. Guion de demostración

Duración aproximada: 2 a 3 minutos.

1. (10 s) "Es un buscador de logs que entiende IPs, rangos de red y fechas con zonas horarias. Solo lee archivos, con datos sintéticos."
2. (30 s) Ejecuta `python -m log_search samples/auth_lab.log --cidr 198.51.100.0/24 -C 1`. Muestra `:` contra `-` y el separador `--`. "Esta red probó seis cuentas en dos minutos."
3. (30 s) Ejecuta `-k "acceso denegado" --from 2026-09-14 --to 2026-09-14 --tz=-06:00` sobre `app_mixed.log`. "El filtro convierte el día a UTC; la línea del 15 queda fuera."
4. (30 s) Ejecuta la búsqueda de `error` con `-C 2` y fechas: señala `2 sin fecha reconocible`. "No oculta lo que no puede evaluar."
5. (20 s) Ejecuta `-k rojo`: "el log trae una secuencia ANSI y la herramienta la muestra escapada".
6. (15 s) Abre `tests/test_matcher.py` y muestra la prueba de contexto en los bordes del archivo.

## 13. Capturas

Pendiente: agrega capturas reales en [`docs/screenshots/`](docs/screenshots/README.md) después de ejecutar la herramienta en tu equipo.

<!-- Ejemplo, cuando exista el archivo:
![Búsqueda por rango en Windows](docs/screenshots/01-rango-cidr-windows.png)
-->
