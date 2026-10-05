# Arquitectura y orden de implementación

## Objetivo

Una colección de 14 herramientas de laboratorio en Python, cada una ejecutable por separado, con datos sintéticos, pruebas y documentación suficiente para explicarlas en una entrevista. No son productos de seguridad listos para producción.

La colección vive en la carpeta `ciberseguridad/` del repositorio [Tipos-de-Proyectos](../../README.md). Todo lo necesario (menú, documentación, configuración de Git) está dentro de esa carpeta, así que podría moverse a un repositorio propio sin cambios.

## Principios

| Principio | Cómo se aplica |
|---|---|
| Independencia | Cada proyecto vive en `ciberseguridad/NN-nombre/` con su código, `requirements.txt`, datos, pruebas y README. Ningún proyecto importa código de otro. Las copias intencionales de módulos (`timeutils.py` en 08, 09, 11 y 12; `models.py` y `parsers.py` en 09 y 12) las vigila `tools/check_shared_copies.py`. |
| Local y gratuito | Sin APIs de pago ni servicios externos obligatorios. Solo archivos locales. |
| Pocas dependencias | Biblioteca estándar siempre que sea razonable. Cada dependencia externa se justifica en el README del proyecto. |
| Seguro por defecto | Sin privilegios de administrador. Nada destructivo por defecto: no se borran archivos, no se sobrescriben exportaciones sin `--force`, no se ejecutan adjuntos ni archivos analizados. |
| Entrada no confiable | Todo lo que viene de archivos analizados se valida; el texto se limpia antes de mostrarse en terminal o exportarse a CSV/HTML. |
| Datos sintéticos | Usuarios inventados e IPs de rangos de documentación (RFC 5737 y RFC 3849). Nunca registros o correos reales. |
| Compatibilidad | Python 3.10 o superior, `pathlib`, UTF-8 explícito, sin códigos de color ni símbolos que fallen en la consola de Windows. |

## Plantilla de cada proyecto

```
NN-nombre/
├── README.md            documentación con las 12 secciones acordadas
├── requirements.txt     dependencias para ejecutar
├── requirements-dev.txt dependencias para probar (incluye pytest)
├── pytest.ini           configuración de pruebas
├── config/settings.json configuración editable
├── paquete/
│   ├── __main__.py      permite "python -m paquete"
│   ├── cli.py           interfaz: argumentos, mensajes, códigos de salida
│   ├── <lógica>.py      reglas del dominio, sin print() ni input()
│   └── report.py        presentación: texto, JSON, CSV...
├── samples/             datos sintéticos identificados como tales
├── tests/               pruebas automáticas
└── docs/screenshots/    capturas reales que agregarás tú
```

La separación `cli` → lógica → `report` permite probar la lógica sin terminal y cambiar la interfaz (por ejemplo, a una web) sin tocar las reglas.

## Decisión: copias en lugar de una biblioteca compartida

Los proyectos 09 y 12 necesitan el mismo lector de registros. Se copiaron `models.py`, `parsers.py` y `timeutils.py` en ambos en lugar de crear un paquete común, porque el requisito es que cada proyecto funcione solo (se puede copiar una carpeta a otra computadora y funciona).

- Costo: si corriges un error en una copia, hay que llevarlo a la otra.
- Mitigación: `tools/check_shared_copies.py` compara las copias y la integración continua falla si difieren.
- En un producto real se extraería un paquete instalable (`pip install`) con versión propia.

## Orden de implementación

Se agrupan proyectos que comparten conceptos para que cada entrega refuerce lo aprendido en la anterior.

| Entrega | Proyectos | Conceptos | Estado |
|---|---|---|---|
| 1 | [09 Contador de intentos de login](../09-contador-logins/README.md), [12 Detector de múltiples accesos](../12-detector-accesos/README.md) | Análisis de logs, expresiones regulares, fechas y zonas horarias, ventanas deslizantes | Implementada |
| 2 | [11 Buscador en logs](../11-buscador-logs/README.md), [08 Generador de reportes](../08-generador-reportes/README.md) | Lectura incremental, contexto de líneas, Markdown/HTML con escape | Implementada |
| 3 | 07 Duplicados, 13 Verificador de archivos sospechosos | SHA-256 por bloques, metadatos de archivos | Pendiente |
| 4 | 03 Validador de archivos, 10 Clasificador de archivos | Reglas de validación, operaciones de archivos simuladas y reversibles | Pendiente |
| 5 | 06 Analizador de correos | Formato .eml, URLs, indicadores de phishing y falsos positivos | Pendiente |
| 6 | 02 Laboratorio TOTP, 04 Monitor del sistema | Únicas con dependencias externas previstas (biblioteca TOTP mantenida, `psutil`); se confirmarán en su entrega | Pendiente |
| 7 | 01 Quiz, 05 Glosario, 14 Checklist | Datos JSON editables, búsqueda sin acentos, persistencia local | Pendiente |

Se empezó por los logs porque el análisis de registros de autenticación es una tarea central en puestos de soporte, SOC y administración de sistemas, y genera las preguntas técnicas más ricas para una entrevista.

## Convenciones

- Carpetas de proyecto en español y numeradas (`09-contador-logins`), para ubicarlas rápido en GitHub.
- Identificadores y nombres de paquete en inglés (estándar en la industria, `login_counter`); comentarios, docstrings, mensajes y documentación en español.
- Fechas internas siempre en UTC; se convierten a la zona elegida solo al mostrarlas.
- Códigos de salida: `0` correcto, `1` error de entrada o configuración, `2` argumentos inválidos.
- Las exportaciones se escriben en `output/` (ignorada por Git) en los ejemplos de la documentación.
