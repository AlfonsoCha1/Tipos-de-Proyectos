# Datos sintéticos

**Todo en esta carpeta es inventado** para practicar. No son registros reales de ninguna persona, empresa ni equipo.

- Usuarios: nombres ficticios.
- IPs: rangos reservados para documentación: `192.0.2.0/24`, `198.51.100.0/24` y `203.0.113.0/24` ([RFC 5737](https://www.rfc-editor.org/rfc/rfc5737)) y `2001:db8::/32` ([RFC 3849](https://www.rfc-editor.org/rfc/rfc3849)).

| Archivo | Qué contiene | Resultado esperado |
|---|---|---|
| `eventos.json` | 14 filas en formato `{"events": [...]}` mezclando UTC y `-06:00`, una severidad en inglés (`High`) y **5 filas inválidas a propósito** (severidad inventada, fecha ilegible, falta el título, IP imposible, una fila que no es objeto) | 9 eventos válidos y 5 rechazados |
| `eventos.csv` | 6 filas CSV: un título que empieza con `=` (para comprobar que se muestra como texto) y **una fila incompleta** | 5 eventos válidos y 1 rechazado |
| `eventos_hostiles.jsonl` | JSON Lines con HTML, Markdown, una secuencia ANSI, un salto de línea dentro de un título, una IP mapeada en IPv6 y **una línea que no es JSON** | 3 eventos válidos y 1 rechazado; nada de esto debe ejecutarse ni romper el reporte |

Los resultados están verificados en `tests/test_cli.py`; si editas un archivo de ejemplo, actualiza también las pruebas.
