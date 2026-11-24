# Datos sintéticos

**Todos los mensajes son inventados.** Las marcas ("Banco Fénix", "Tienda Demo", "Paquetería Rápida") son ficticias y usan el dominio reservado `.example` ([RFC 2606](https://www.rfc-editor.org/rfc/rfc2606)); las IPs son de documentación ([RFC 5737](https://www.rfc-editor.org/rfc/rfc5737)). Los adjuntos son texto inofensivo.

| Archivo | Qué simula | Resultado esperado |
|---|---|---|
| `01_legitimo_estado_cuenta.eml` | aviso legítimo del banco con SPF/DKIM/DMARC en `pass` | BAJO, 15 puntos (falso positivo controlado: menciona "contraseña" para decir que nunca la pedirán) |
| `02_phishing_banco.eml` | dominio `bancofenlx`, `Reply-To` gratuito, DMARC fallido, enlace con texto del banco que lleva a una IP, urgencia y petición de NIP | ALTO, 100 puntos, 9 indicadores |
| `03_factura_con_adjunto.eml` | factura con `Factura_0925.pdf.exe` y una página HTML adjunta | ALTO, 60 puntos |
| `04_boletin_acortador.eml` | boletín legítimo con un enlace acortado | BAJO, 5 puntos |
| `05_sms_paqueteria.txt` | SMS de paquetería con dominio parecido y un dominio punycode | MEDIO, 55 puntos |
| `06_no_es_correo.eml` | texto con extensión `.eml` | se reporta como "no analizado" (con `--text` se analiza como texto) |

Los resultados están verificados por `tests/test_indicators.py`. `.gitattributes` evita que Git cambie los saltos de línea en Windows, para que los hashes de los adjuntos no cambien.
