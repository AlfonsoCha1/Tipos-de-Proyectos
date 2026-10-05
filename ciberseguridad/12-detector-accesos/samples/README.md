# Datos sintéticos

**Todo en esta carpeta es inventado** para practicar. No son registros reales de ninguna persona, empresa ni equipo.

- Usuarios: nombres ficticios.
- IPs: rangos reservados para documentación: `192.0.2.0/24`, `198.51.100.0/24` y `203.0.113.0/24` ([RFC 5737](https://www.rfc-editor.org/rfc/rfc5737)) y `2001:db8::/32` ([RFC 3849](https://www.rfc-editor.org/rfc/rfc3849)).

| Archivo | Qué simula | Con la configuración por defecto (5 fallos en 5 min) |
|---|---|---|
| `auth_lab.log` | fuerza bruta contra `admin` rotando 2 IPs (líneas en UTC y fuera de orden) seguida de un acceso exitoso; *password spraying* desde `198.51.100.23` contra 6 cuentas; fallos lentos de `carlos`; 5 fallos de `luis` en 6 minutos | 2 alertas: cuenta `admin` (alta) e IP `198.51.100.23` (media). Con `--window 10` aparecen 2 más (`luis` y su IP) |
| `auth_syslog.log` | `auth.log` de OpenSSH con *spraying* desde `198.51.100.23`, incluido un `message repeated 2 times` | 1 alerta: IP `198.51.100.23` |
| `logins.csv` | CSV pequeño (se usa sobre todo en las pruebas de formato) | 0 alertas |
| `normal_activity.log` | un día normal de oficina: algunos errores de contraseña sin ráfagas | 0 alertas |
| `multi_fuente/servidor_web.log` | servidor web que registra en hora de Ciudad de México (`-06:00`): 3 fallos de `elena` | 0 alertas por sí solo |
| `multi_fuente/vpn.csv` | VPN que registra en UTC: 2 fallos de `elena` y un acceso exitoso | 0 alertas por sí solo; **1 alerta alta** si se analiza junto con `servidor_web.log` |

`auth_lab.log`, `auth_syslog.log` y `logins.csv` son copias de los del proyecto 09. Los resultados están verificados en `tests/test_cli.py`; si editas un archivo de ejemplo, actualiza también las pruebas.
