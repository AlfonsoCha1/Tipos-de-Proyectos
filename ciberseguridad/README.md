# Cybersecurity Python Lab

**Laboratorio de ciberseguridad defensiva en Python** · *Defensive cybersecurity lab in Python*

Colección de 14 herramientas pequeñas e independientes para practicar programación aplicada a la ciberseguridad: análisis de registros de autenticación, detección de patrones sospechosos, validación e inspección de archivos y automatización. Cada proyecto tiene su propio código, datos sintéticos, pruebas automáticas y una guía para entenderlo, modificarlo y explicarlo en una entrevista.

> Son **herramientas de laboratorio y aprendizaje**, no productos de seguridad listos para producción. Trabajan con archivos locales, no se conectan a servicios externos, no requieren permisos de administrador y no hacen nada destructivo por defecto.

[← Volver a Tipos-de-Proyectos](../README.md)

## Proyectos

| # | Proyecto | Qué hace | Habilidades que practica | Estado |
|---|---|---|---|---|
| 01 | [Quiz de ciberseguridad](01-quiz-ciberseguridad/README.md) | 24 preguntas por categoría y dificultad, opciones mezcladas, explicación de cada respuesta y qué repasar | JSON editable validado, semillas reproducibles, entrada simulada en pruebas | **Disponible** |
| 02 | [Laboratorio de códigos 2FA](02-laboratorio-2fa/README.md) | genera, verifica y explica paso a paso códigos TOTP; ventana de reloj y rechazo de códigos repetidos | HMAC, RFC 4226 y RFC 6238 (validado con los vectores oficiales), `secrets`, `compare_digest` | **Disponible** |
| 03 | [Validador de archivos](03-validador-archivos/README.md) | lista blanca de extensiones, tamaño, nombres peligrosos (`..`, `CON`, doble extensión) y contenido real; explica cada rechazo | validación de entrada, firmas de archivo, path traversal | **Disponible** |
| 04 | [Monitor básico del sistema](04-monitor-sistema/README.md) | CPU, RAM y discos contra umbrales de aviso y alerta, varias muestras y CSV | `psutil`, umbrales, lector simulado para pruebas | **Disponible** |
| 05 | [Glosario interactivo](05-glosario/README.md) | 43 términos con sinónimos; búsqueda sin mayúsculas ni acentos y sugerencias | normalización Unicode, `difflib`, relevancia | **Disponible** |
| 06 | [Analizador de correos](06-analizador-correos/README.md) | triaje de phishing en `.eml` o texto: SPF/DKIM/DMARC, dominios parecidos, enlaces engañosos, adjuntos con hash; puntuación con falsos positivos | `email` (MIME), `html.parser`, Levenshtein, defang de URLs, IOC en JSON | **Disponible** |
| 07 | [Buscador de duplicados](07-buscador-duplicados/README.md) | agrupa archivos idénticos por tamaño y SHA-256 sin borrar nada | hashing por bloques, `os.walk` seguro, enlaces duros y simbólicos | **Disponible** |
| 08 | [Generador de reportes](08-generador-reportes/README.md) | convierte eventos JSON, JSON Lines o CSV en un reporte Markdown y HTML, y lista las filas que no pudo usar | validación de esquema, escape de HTML/Markdown, CSP, reportes reproducibles | **Disponible** |
| 09 | [Contador de intentos de login](09-contador-logins/README.md) | cuenta accesos exitosos y fallidos por usuario e IP en tres formatos y reporta las líneas que no entiende | análisis de logs de OpenSSH, regex, `ipaddress`, zonas horarias, generadores, CSV/JSON seguros, pytest | **Disponible** |
| 10 | [Clasificador de archivos](10-clasificador-archivos/README.md) | organiza por tipo con simulación, confirmación, sin sobrescribir y con journal para revertir | operaciones de archivos seguras y reversibles, escritura atómica | **Disponible** |
| 11 | [Buscador en logs](11-buscador-logs/README.md) | busca palabras, IPs, rangos de red y fechas con líneas de contexto, sin cargar el archivo completo | lectura incremental, `deque`, `ipaddress` (CIDR), zonas horarias | **Disponible** |
| 12 | [Detector de múltiples accesos](12-detector-accesos/README.md) | alerta cuando una cuenta o IP acumula demasiados fallos en una ventana de tiempo, con explicación y evidencia | ventana deslizante (`deque`), correlación de varias fuentes, UTC, `bisect`, detección sin bloqueo | **Disponible** |
| 13 | [Verificador de archivos sospechosos](13-verificador-archivos/README.md) | MD5/SHA-1/SHA-256, tipo real por firma, doble extensión, `U+202E`, PDF activo, ZIP con scripts y lista de IOC | triaje de archivos sin ejecutarlos, firmas, indicadores de compromiso | **Disponible** |
| 14 | [Checklist de seguridad](14-checklist-seguridad/README.md) | 18 hábitos de seguridad con estados, notas, avance por categoría y exportación | persistencia local atómica, no destruir datos dañados, exportación segura | **Disponible** |

Los 14 proyectos están disponibles. El orden en que se construyeron y el motivo están en [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md#orden-de-implementación).

## Estado de validación

Qué está verificado y qué falta, sin mezclarlos:

| Qué | Estado |
|---|---|
| Pruebas automáticas de 08, 09, 11 y 12 (59 + 70 + 60 + 88) con `python menu.py --test-all` | **Ejecutadas por el asistente** en Linux (nube) con Python 3.10, 3.11, 3.12, 3.13 y 3.14, cada una en un entorno virtual nuevo |
| Pruebas automáticas de los 14 proyectos (622 en total; 345 nuevas de las entregas 3 a 7) con `python menu.py --test-all` | **Ejecutadas por el asistente** el 24 de noviembre de 2026 en Linux (nube) con Python 3.11 y 3.13, cada versión en un entorno virtual nuevo: `Proyectos probados: 14 \| con fallos: 0` |
| Pruebas de 09 y 12 (70 + 88) en Windows | **Ejecutadas por Alfonso** el 5 de octubre de 2026 en Windows con Python 3.14.8 (ver [docs/METODOLOGIA.md](docs/METODOLOGIA.md#registro-de-validaciones)) |
| Pruebas de los demás proyectos en Windows y de todos en Linux Mint | **Pendientes de ejecutar por ti** |
| Capturas de pantalla | **Pendientes**: solo se agregan capturas reales de tu ejecución (`docs/screenshots/` de cada proyecto) |
| Integración continua en GitHub | Preparada pero **desactivada** ([docs/GITHUB.md](docs/GITHUB.md#5-integración-continua-opcional)) |

## Inicio rápido

Requisitos: Python 3.10 o superior y Git.

**Linux Mint**

```bash
git clone https://github.com/AlfonsoCha1/Tipos-de-Proyectos.git
cd Tipos-de-Proyectos/ciberseguridad
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python menu.py
```

**Windows (PowerShell)**

```powershell
git clone https://github.com/AlfonsoCha1/Tipos-de-Proyectos.git
cd Tipos-de-Proyectos\ciberseguridad
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python menu.py
```

El menú muestra los 14 proyectos, ejecuta las demostraciones con datos de ejemplo y corre las pruebas. Por dentro solo ejecuta `python -m <paquete>` en la carpeta de cada proyecto, así que cada uno sigue funcionando por separado:

```bash
python menu.py --list        # proyectos y su estado
python menu.py --test-all    # pruebas de todos los proyectos disponibles

cd 09-contador-logins
python -m login_counter samples/auth_lab.log
```

## Estructura

```
ciberseguridad/
├── README.md                  este documento
├── menu.py                    menú de terminal para abrir cualquier proyecto
├── requirements-dev.txt       entorno único para el menú y las pruebas de todos los proyectos
├── .gitignore                 entornos virtuales, cachés, exportaciones, secretos y logs reales
├── docs/
│   ├── ARQUITECTURA.md        principios, plantilla de proyecto y orden de entregas
│   ├── METODOLOGIA.md         desarrollo con IA y registro de mis validaciones
│   └── GITHUB.md              clonar, subir cambios y comprobar una instalación limpia
├── tools/
│   └── check_shared_copies.py verifica que los módulos copiados entre proyectos sigan iguales
├── ci/
│   └── github-actions.yml     pruebas automáticas en Ubuntu y Windows (opcional, desactivado)
├── 01-quiz-ciberseguridad/    proyecto 01: código, README, samples/ o data/, tests/
├── 02-laboratorio-2fa/        proyecto 02: código, README, samples/ o data/, tests/
├── 03-validador-archivos/     proyecto 03: código, README, samples/ o data/, tests/
├── 04-monitor-sistema/        proyecto 04: código, README, samples/ o data/, tests/
├── 05-glosario/               proyecto 05: código, README, samples/ o data/, tests/
├── 06-analizador-correos/     proyecto 06: código, README, samples/ o data/, tests/
├── 07-buscador-duplicados/    proyecto 07: código, README, samples/ o data/, tests/
├── 08-generador-reportes/     proyecto 08: código, README, samples/ o data/, tests/
├── 09-contador-logins/        proyecto 09: código, README, samples/ o data/, tests/
├── 10-clasificador-archivos/  proyecto 10: código, README, samples/ o data/, tests/
├── 11-buscador-logs/          proyecto 11: código, README, samples/ o data/, tests/
├── 12-detector-accesos/       proyecto 12: código, README, samples/ o data/, tests/
├── 13-verificador-archivos/   proyecto 13: código, README, samples/ o data/, tests/
└── 14-checklist-seguridad/    proyecto 14: código, README, samples/ o data/, tests/
```

Cada carpeta de proyecto sigue la misma plantilla: `README.md` con 12 secciones (instalación, comandos, ejemplo real, recorrido de los datos, limitaciones, pruebas, ejercicios, preguntas de entrevista y guion de demostración), código en un paquete de Python, `samples/` con datos sintéticos identificados, `tests/` y `docs/screenshots/` para capturas reales.

## Principios

- **Datos sintéticos**: usuarios inventados e IPs de rangos reservados para documentación (RFC 5737 y RFC 3849). Nunca registros, correos ni datos personales reales.
- **Entrada no confiable**: todo lo que se lee de un archivo analizado se valida; el texto se limpia antes de mostrarse en la terminal o exportarse (caracteres de control, inyección de fórmulas en CSV).
- **Seguro por defecto**: sin `sudo`, sin borrar ni mover archivos sin confirmación, sin sobrescribir exportaciones sin `--force`, sin ejecutar lo que se analiza.
- **Pocas dependencias**: biblioteca estándar siempre que sea razonable; cada dependencia externa se justifica en el README de su proyecto.
- **Linux Mint y Windows**: rutas con `pathlib`, UTF-8 explícito y sin colores ni símbolos que fallen en la consola de Windows. Las diferencias reales se documentan en cada proyecto (por ejemplo, `tzdata` solo se instala en Windows).

## Metodología

Este laboratorio se desarrolla con asistencia de IA (Claude, de Anthropic) a partir de requisitos que yo definí. El asistente escribió la primera versión del código, los datos sintéticos, las pruebas y la documentación, y ejecutó las pruebas en un entorno Linux en la nube. Mi trabajo es revisar, ejecutar, entender y modificar cada proyecto en mis propios equipos. Las validaciones y cambios propios se registran en [docs/METODOLOGIA.md](docs/METODOLOGIA.md) solo cuando realmente los hago.

## English summary

**Cybersecurity Python Lab** is a collection of 14 small, independent Python tools for practicing defensive security programming: authentication log analysis, brute-force and password-spraying detection, file validation and inspection, and automation. Each project ships with its own code, clearly labeled synthetic data, automated tests (pytest) and documentation written in Spanish.

These are **lab and learning tools**, not production security products. They work on local files only, need no administrator privileges, call no external services and perform no destructive actions by default.

All 14 tools are available:

- **Log analysis and detection:** [09 · Login attempt counter](09-contador-logins/README.md), [12 · Failed-login burst detector](12-detector-accesos/README.md) (sliding windows, password spraying), [11 · Log search](11-buscador-logs/README.md) (keywords, IPs, CIDR ranges, dates) and [08 · Report generator](08-generador-reportes/README.md) (Markdown and self-contained HTML).
- **Triage of suspicious content:** [06 · Email analyzer](06-analizador-correos/README.md) (SPF/DKIM/DMARC results, lookalike domains, deceptive links, risky attachments, defanged URLs, explainable score with false-positive notes) and [13 · Suspicious file checker](13-verificador-archivos/README.md) (MD5/SHA-1/SHA-256, magic-byte type detection, double extensions, RTL-override names, active PDF content, ZIP slip, local IOC list).
- **Files and data safety:** [03 · Upload validator](03-validador-archivos/README.md) (allow-list, path traversal, Windows reserved names, content vs. extension), [07 · Duplicate finder](07-buscador-duplicados/README.md) (size then chunked SHA-256, never deletes) and [10 · File organizer](10-clasificador-archivos/README.md) (dry run by default, confirmation, no overwrites, undo journal).
- **Identity, monitoring and learning:** [02 · TOTP lab](02-laboratorio-2fa/README.md) (RFC 4226/6238 from scratch, verified against the official test vectors, replay protection), [04 · System monitor](04-monitor-sistema/README.md) (CPU, RAM and disk thresholds with `psutil`), [01 · Security quiz](01-quiz-ciberseguridad/README.md), [05 · Security glossary](05-glosario/README.md) and [14 · Security checklist](14-checklist-seguridad/README.md).

Quick start: see [Inicio rápido](#inicio-rápido) above (commands are the same in English). Development is AI-assisted; see [docs/METODOLOGIA.md](docs/METODOLOGIA.md).
