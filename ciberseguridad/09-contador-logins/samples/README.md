# Datos sintéticos

**Todo en esta carpeta es inventado** para practicar. No son registros reales de ninguna persona, empresa ni equipo.

- Usuarios: nombres ficticios (`ana`, `luis`, `admin`...).
- IPs: rangos reservados para documentación, que no pertenecen a nadie en Internet: `192.0.2.0/24`, `198.51.100.0/24` y `203.0.113.0/24` ([RFC 5737](https://www.rfc-editor.org/rfc/rfc5737)) y `2001:db8::/32` ([RFC 3849](https://www.rfc-editor.org/rfc/rfc3849)).
- Huellas de llaves SSH: texto de relleno (`HUELLAsinteticaDeEjemplo`).

| Archivo | Formato | Qué contiene | Resultado esperado |
|---|---|---|---|
| `auth_lab.log` | lab | ataque a `admin` desde 2 IPs con líneas en UTC y fuera de orden; *password spraying* desde `198.51.100.23`; fallos lentos de `carlos`; una línea sin zona horaria (`sofia`, IPv6); 5 líneas dañadas a propósito al final | 29 intentos (6 exitosos, 23 fallidos), 10 líneas ignoradas (comentarios), 5 no interpretadas |
| `auth_syslog.log` | `auth.log` de OpenSSH | `Invalid user` + `Failed password for invalid user`, `message repeated 2 times`, `sshd-session`, IPv6, líneas de otros procesos (CRON, sudo) y 3 líneas dañadas | 13 intentos (3 exitosos, 10 fallidos), 5 ignoradas, 3 no interpretadas |
| `logins.csv` | CSV | columna extra `note`, un usuario malicioso `=HYPERLINK(1)` para probar la inyección CSV y 2 filas con errores | 5 intentos (2 exitosos, 3 fallidos), 2 no interpretadas |

Estos números están verificados por las pruebas de `tests/test_counter.py`. Si editas un archivo de ejemplo, actualiza también las pruebas.

Las mismas copias de `auth_lab.log`, `auth_syslog.log` y `logins.csv` están en el proyecto 12, porque cada proyecto debe funcionar por separado.
