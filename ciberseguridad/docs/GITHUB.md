# Trabajar con GitHub y comprobar una instalación limpia

Esta colección está publicada en la carpeta `ciberseguridad/` del repositorio **Tipos-de-Proyectos**:
<https://github.com/AlfonsoCha1/Tipos-de-Proyectos/tree/main/ciberseguridad>

## 1. Descargar el repositorio a tu computadora

Una sola vez:

```bash
git clone https://github.com/AlfonsoCha1/Tipos-de-Proyectos.git
cd Tipos-de-Proyectos/ciberseguridad
```

Si ya lo tenías clonado, trae los cambios nuevos (por ejemplo, cada entrega):

```bash
cd Tipos-de-Proyectos
git pull
```

Si subes archivos desde la página web de GitHub ("Add files via upload"), haz `git pull` antes de trabajar en tu computadora para no tener versiones distintas.

## 2. Comprobar que funciona desde una instalación limpia

Clona en una carpeta temporal, como lo haría un reclutador:

**Linux Mint**

```bash
cd /tmp
git clone https://github.com/AlfonsoCha1/Tipos-de-Proyectos.git prueba-limpia
cd prueba-limpia/ciberseguridad
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python tools/check_shared_copies.py
python menu.py --test-all
python menu.py
```

**Windows (PowerShell)**

```powershell
cd $env:TEMP
git clone https://github.com/AlfonsoCha1/Tipos-de-Proyectos.git prueba-limpia
cd prueba-limpia\ciberseguridad
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python tools\check_shared_copies.py
python menu.py --test-all
python menu.py
```

Si PowerShell bloquea `Activate.ps1`, ejecuta una vez `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, o usa `cmd` con `.venv\Scripts\activate.bat`. Si `python3 -m venv` falla en Linux Mint con un mensaje sobre `ensurepip`: `sudo apt install python3-venv` (instalar programas sí requiere `sudo`; las herramientas del laboratorio no).

Resultado esperado: `Proyectos probados: 2 | con fallos: 0` (el número crecerá con cada entrega). Anota en [METODOLOGIA.md](METODOLOGIA.md) la fecha, el sistema y el resultado real.

## 3. Subir tus propios cambios

Configura tu identidad una sola vez (usa el correo *noreply* de GitHub si no quieres exponer tu correo: Settings → Emails):

```bash
git config --global user.name "Tu Nombre"
git config --global user.email "TU_ID+AlfonsoCha1@users.noreply.github.com"
```

Después de modificar algo (por ejemplo, un ejercicio del README):

```bash
cd Tipos-de-Proyectos
git pull
git status                       # revisa qué cambió
git add ciberseguridad
git commit -m "09: agrega columna de porcentaje de fallos"
git push
```

GitHub no acepta tu contraseña en la terminal. Opciones para autenticarte:

- **GitHub CLI** (recomendado): instala `gh`, ejecuta `gh auth login` y elige HTTPS.
  - Linux Mint: `sudo apt install gh`
  - Windows: `winget install --id GitHub.cli`
- **Token personal**: Settings → Developer settings → Personal access tokens → *Fine-grained*, con permiso *Contents: Read and write* solo para este repositorio. Úsalo como contraseña cuando Git la pida. No lo guardes en ningún archivo del repositorio.

## 4. Antes de cada `push`: revisa que no se cuele nada privado

Desde la carpeta `ciberseguridad`:

```bash
git status --ignored .         # .venv/, output/ y __pycache__/ deben salir como ignorados
git ls-files .                 # lista exacta de lo que está en el repositorio
git grep -n -I -E "ghp_|github_pat_|AKIA[0-9A-Z]{16}|PRIVATE KEY-----" -- . ':!docs/GITHUB.md'   # formatos comunes de credenciales: no debe mostrar nada
```

Los únicos `.log` que deben aparecer en `git ls-files` son los de `*/samples/` (datos sintéticos). Si analizaste un registro real de tu equipo, déjalo fuera de la carpeta del repositorio. El archivo [`.gitignore`](../.gitignore) de esta carpeta ignora entornos virtuales, cachés, exportaciones (`output/`), secretos y cualquier `.log` fuera de `samples/`.

## 5. Integración continua (opcional)

[`ci/github-actions.yml`](../ci/github-actions.yml) ejecuta las pruebas en Ubuntu y Windows, con Python 3.10 y 3.13, cada vez que cambia algo dentro de `ciberseguridad/`. Está **desactivado**: GitHub solo ejecuta flujos guardados en `.github/workflows/` en la raíz del repositorio, y no se agregó ahí para no tocar el resto de Tipos-de-Proyectos sin tu decisión.

Para activarlo, desde la raíz del repositorio:

```bash
mkdir -p .github/workflows
cp ciberseguridad/ci/github-actions.yml .github/workflows/ciberseguridad.yml
git add .github/workflows/ciberseguridad.yml
git commit -m "Activa pruebas automáticas de ciberseguridad"
git push
```

Después revisa la pestaña **Actions** del repositorio:

- Verde: las pruebas pasaron en esos sistemas. Ese resultado sí puedes mencionarlo, porque lo produjo GitHub.
- Rojo: abre el paso que falló y lee el error; casi siempre es una diferencia de rutas, codificación o zona horaria.

No agregues insignias (*badges*) de estado hasta que la integración continua esté en verde de forma estable.

## 6. Capturas

Después de ejecutar cada herramienta en tu equipo, guarda capturas en `NN-nombre/docs/screenshots/` siguiendo la lista del README de esa carpeta y enlázalas en la sección "Capturas" del README del proyecto. Solo capturas reales de tu propia ejecución.
