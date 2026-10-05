# Metodología

## Desarrollo con asistencia de IA

La primera versión del código, los datos sintéticos, las pruebas y la documentación de este repositorio se generó con ayuda de un asistente de IA (Claude, de Anthropic), a partir de requisitos que definí: proyectos independientes, datos sintéticos, seguridad por defecto, compatibilidad con Linux Mint y Windows, y documentación orientada al aprendizaje.

Lo que eso significa en la práctica:

- El asistente propuso la arquitectura, escribió el código y ejecutó las pruebas en un entorno Linux en la nube.
- Mi trabajo es revisar, ejecutar, entender, modificar y validar cada proyecto en mis propios equipos antes de presentarlo como parte de mi portafolio.
- Este documento registra solo cambios y validaciones que yo haya hecho realmente. No se llenan de antemano.
- En el historial de Git, los commits que subió el asistente aparecen con el autor `Claude <noreply@anthropic.com>`. Los cambios que yo haga aparecerán con mi nombre. Así el historial muestra con honestidad quién hizo qué.

## Cómo valido cada proyecto

1. Instalación desde cero en un entorno virtual nuevo (Linux Mint y Windows).
2. Ejecución de `python -m pytest` dentro de la carpeta del proyecto.
3. Ejecución manual de cada comando del README y comparación con la salida documentada.
4. Lectura del código hasta poder explicar cada módulo sin mirar la documentación.
5. Al menos uno de los ejercicios propuestos en el README.
6. Capturas reales en `docs/screenshots/` de cada proyecto.

## Registro de validaciones

| Fecha | Proyecto | Sistema y versión de Python | Qué ejecuté | Resultado |
|---|---|---|---|---|
| | | | | |

## Registro de cambios propios

| Fecha | Proyecto | Cambio | Por qué | Cómo lo probé |
|---|---|---|---|---|
| | | | | |

## Decisiones que puedo defender

Marca cada una cuando puedas explicarla con tus palabras:

- [ ] Por qué cada proyecto es independiente y por qué los proyectos 09 y 12 tienen módulos copiados.
- [ ] Por qué todas las fechas se convierten a UTC al leerlas.
- [ ] Cómo funciona la ventana deslizante del detector y por qué ordena los eventos primero.
- [ ] Por qué se cuentan solo las líneas `Accepted`/`Failed` de OpenSSH y no `Invalid user`.
- [ ] Por qué se neutralizan celdas CSV que empiezan con `=`, `+`, `-` o `@`.
- [ ] Por qué el detector no bloquea cuentas ni IPs.
