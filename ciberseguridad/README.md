# Cybersecurity Python Lab

**Laboratorio de ciberseguridad defensiva en Python** · *Defensive cybersecurity lab in Python*

Colección de 14 herramientas pequeñas e independientes para practicar programación aplicada a la ciberseguridad: análisis de registros de autenticación, detección de patrones sospechosos, validación e inspección de archivos y automatización. Cada proyecto tiene su propio código, datos sintéticos, pruebas automáticas y una guía para entenderlo, modificarlo y explicarlo en una entrevista.

> Son **herramientas de laboratorio y aprendizaje**, no productos de seguridad listos para producción. Trabajan con archivos locales, no se conectan a servicios externos, no requieren permisos de administrador y no hacen nada destructivo por defecto.

[← Volver a Tipos-de-Proyectos](../README.md)

## Proyectos

| # | Proyecto | Qué hace | Habilidades que practica | Estado |
|---|---|---|---|---|
| 01 | Quiz de ciberseguridad | preguntas por categoría y dificultad, puntuación y explicación de cada respuesta | JSON editable, funciones, validación de entradas | Pendiente |
| 02 | Laboratorio de códigos 2FA | genera y verifica códigos TOTP y explica el secreto compartido y el reloj | autenticación, TOTP (RFC 6238), manejo de secretos | Pendiente |
| 03 | Validador de archivos | revisa extensión, tamaño y nombre, y explica cada rechazo | `pathlib`, reglas de validación | Pendiente |
| 04 | Monitor básico del sistema | CPU, RAM y disco con umbrales y exportación | monitoreo, `psutil`, CSV | Pendiente |
| 05 | Glosario interactivo | búsqueda de términos sin distinguir mayúsculas ni acentos | diccionarios, normalización Unicode | Pendiente |
| 06 | Analizador de correos | señala indicadores de phishing en texto o `.eml` sin abrir enlaces | `email`, expresiones regulares, falsos positivos | Pendiente |
| 07 | Buscador de duplicados | agrupa archivos idénticos por tamaño y SHA-256 sin borrar nada | hashing por bloques | Pendiente |
| **08** | **[Generador de reportes](08-generador-reportes/README.md)** | convierte eventos JSON, JSON Lines o CSV en un reporte Markdown y HTML, y lista las filas que no pudo usar | validación de esquema, escape de HTML/Markdown, CSP, reportes reproducibles | **Disponible** |
| **09** | **[Contador de intentos de login](09-contador-logins/README.md)** | cuenta accesos exitosos y fallidos por usuario e IP en tres formatos y reporta las líneas que no entiende | análisis de logs de OpenSSH, regex, `ipaddress`, zonas horarias, generadores, CSV/JSON seguros, pytest | **Disponible** |
| 10 | Clasificador de archivos | organiza por extensión con simulación, confirmación y reversión | operaciones de archivos seguras y reversibles | Pendiente |
| **11** | **[Buscador en logs](11-buscador-logs/README.md)** | busca palabras, IPs, rangos de red y fechas con líneas de contexto, sin cargar el archivo completo | lectura incremental, `deque`, `ipaddress` (CIDR), zonas horarias | **Disponible** |
| **12** | **[Detector de múltiples accesos](12-detector-accesos/README.md)** | alerta cuando una cuenta o IP acumula demasiados fallos en una ventana de tiempo, con explicación y evidencia | ventana deslizante (`deque`), correlación de varias fuentes, UTC, `bisect`, detección sin bloqueo | **Disponible** |
| 13 | Verificador de archivos sospechosos | tamaño, extensión, SHA-256 y doble extensión, sin ejecutar nada | hashing, metadatos | Pendiente |
| 14 | Checklist de seguridad | lista editable con estados, notas, persistencia y exportación | persistencia local, interfaz básica | Pendiente |

Los proyectos pendientes se agregarán por entregas; el orden y el motivo están en [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md#orden-de-implementación).

## Estado de validación

Qué está verificado y qué falta, sin mezclarlos:

| Qué | Estado |
|---|---|
| Pruebas automáticas de 08, 09, 11 y 12 (59 + 70 + 60 + 88) con `python menu.py --test-all` | **Ejecutadas por el asistente** en Linux (nube) con Python 3.10, 3.11, 3.12, 3.13 y 3.14, cada una en un entorno virtual nuevo |
| Pruebas de 09 y 12 (70 + 88) en Windows | **Ejecutadas por Alfonso** el 5 de octubre de 2026 en Windows con Python 3.14.8 (ver [docs/METODOLOGIA.md](docs/METODOLOGIA.md#registro-de-validaciones)) |
| Pruebas de 08 y 11 en Windows y de todos en Linux Mint | **Pendientes de ejecutar por ti** |
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
├── 08-generador-reportes/     proyecto 08: código, README, samples/, tests/
├── 09-contador-logins/        proyecto 09: código, README, samples/, tests/
├── 11-buscador-logs/          proyecto 11: código, README, samples/, tests/
└── 12-detector-accesos/       proyecto 12: código, README, samples/, tests/
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

Available now (4 of 14):

- **[09 · Login attempt counter](09-contador-logins/README.md)**: counts successful and failed logins per user and IP from OpenSSH `auth.log`, a documented lab format and CSV; reports every line it could not parse, with line number and reason; exports to JSON/CSV with CSV-injection protection.
- **[12 · Failed-login burst detector](12-detector-accesos/README.md)**: sliding-window detection per account and per IP over unordered, multi-source, multi-timezone logs; explainable alerts with evidence and a follow-up success check. It alerts only and never blocks accounts or addresses.

- **[11 · Log search](11-buscador-logs/README.md)**: finds keywords, IPs, CIDR ranges and date ranges in log files with grep-style context lines; streams files instead of loading them, reports lines it cannot evaluate (for example, undated stack-trace lines) and escapes control characters before printing.
- **[08 · Report generator](08-generador-reportes/README.md)**: turns security events (JSON, JSON Lines or CSV) into a Markdown and a self-contained HTML report; validates every row, lists rejected rows with the reason, escapes all untrusted text and refuses to overwrite existing reports without `--force`.

Quick start: see [Inicio rápido](#inicio-rápido) above (commands are the same in English). Development is AI-assisted; see [docs/METODOLOGIA.md](docs/METODOLOGIA.md).
