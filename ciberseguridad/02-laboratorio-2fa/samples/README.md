# Datos de ejemplo

`secreto_demo.txt` contiene el secreto **público** que usa el RFC 6238 en sus vectores de prueba: el texto `12345678901234567890` codificado en Base32 (`GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ`). Está en el repositorio a propósito para que los ejemplos sean reproducibles; **nunca lo uses en una cuenta real**.

Con ese secreto y `--at 2026-11-24T10:00:00-06:00` el código es `120159` y el contador `T = 59851200`; lo verifican las pruebas de `tests/test_cli.py`.

Tus secretos reales van fuera del repositorio o en `secrets/` o archivos `*.secret`, que `.gitignore` ignora.
