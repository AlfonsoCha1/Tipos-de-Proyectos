# Datos sintéticos

**Todo en esta carpeta es inventado** para practicar. No son registros reales de ninguna persona, empresa ni equipo.

- Usuarios: nombres ficticios.
- IPs: rangos reservados para documentación: `192.0.2.0/24`, `198.51.100.0/24` y `203.0.113.0/24` ([RFC 5737](https://www.rfc-editor.org/rfc/rfc5737)) y `2001:db8::/32` ([RFC 3849](https://www.rfc-editor.org/rfc/rfc3849)).

| Archivo | Qué simula | Para qué sirve en este proyecto |
|---|---|---|
| `auth_lab.log` | formato "lab" de los proyectos 09 y 12 (copia) | buscar por usuario, IP, rango y fecha; líneas en UTC y en `-06:00` |
| `auth_syslog.log` | `auth.log` de OpenSSH, fechas sin año (copia del 09) | demuestra `--year` y la búsqueda por rango de fechas en syslog |
| `app_mixed.log` | registro de una aplicación ficticia | líneas sin fecha (error con *traceback*), IPv6, mayúsculas distintas (`admin` / `ADMIN`) y una secuencia ANSI que la herramienta debe escapar |

Los resultados de la sección 4 del README están verificados en `tests/test_cli.py`; si editas un archivo de ejemplo, actualiza también las pruebas.
