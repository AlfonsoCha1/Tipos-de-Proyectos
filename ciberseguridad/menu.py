"""Menú de terminal de Cybersecurity Python Lab.

Cada proyecto sigue siendo independiente: el menú solo ejecuta
``python -m <paquete>`` dentro de la carpeta del proyecto, exactamente como
lo harías a mano, y muestra el comando para que puedas repetirlo.

Uso:
    python menu.py              menú interactivo
    python menu.py --list       lista de proyectos y su estado
    python menu.py --test-all   ejecuta las pruebas de los proyectos disponibles
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import shlex
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parent
# Cada proyecto es una carpeta "NN-nombre" junto a este archivo.
PROJECTS_DIR = ROOT


@dataclass(frozen=True)
class Project:
    """Proyecto del portafolio. ``demo`` son los argumentos de la demostración."""

    number: int
    folder: str
    title: str
    package: str
    demo: tuple[str, ...] = ()

    @property
    def path(self) -> Path:
        return PROJECTS_DIR / self.folder

    @property
    def available(self) -> bool:
        return (self.path / self.package / "__main__.py").is_file()


# Orden y nombres de carpeta definidos en docs/ARQUITECTURA.md.
PROJECTS = (
    Project(1, "01-quiz-ciberseguridad", "Quiz de ciberseguridad", "security_quiz"),
    Project(2, "02-laboratorio-2fa", "Laboratorio de códigos 2FA (TOTP)", "totp_lab"),
    Project(3, "03-validador-archivos", "Validador de archivos", "file_validator"),
    Project(4, "04-monitor-sistema", "Monitor básico del sistema", "system_monitor"),
    Project(5, "05-glosario", "Glosario interactivo", "security_glossary"),
    Project(6, "06-analizador-correos", "Analizador de correos", "email_analyzer"),
    Project(7, "07-buscador-duplicados", "Buscador de archivos duplicados", "duplicate_finder"),
    Project(8, "08-generador-reportes", "Generador de reportes de seguridad", "report_generator"),
    Project(9, "09-contador-logins", "Contador de intentos de login", "login_counter",
            ("samples/auth_lab.log",)),
    Project(10, "10-clasificador-archivos", "Clasificador de archivos", "file_organizer"),
    Project(11, "11-buscador-logs", "Buscador de información en logs", "log_search"),
    Project(12, "12-detector-accesos", "Detector de múltiples accesos", "failed_login_detector",
            ("samples/auth_lab.log", "--display-tz", "America/Mexico_City")),
    Project(13, "13-verificador-archivos", "Verificador de archivos sospechosos", "file_inspector"),
    Project(14, "14-checklist-seguridad", "Checklist de seguridad", "security_checklist"),
)


def split_arguments(text: str) -> list[str]:
    """Divide los argumentos escritos por el usuario respetando comillas.

    En Windows se usa el modo no POSIX para no perder las barras invertidas de
    rutas como ``C:\\logs\\auth.log``; luego se quitan las comillas sobrantes.

    Raises:
        ValueError: si hay comillas sin cerrar.
    """
    if os.name == "nt":
        return [part.strip('"') for part in shlex.split(text, posix=False)]
    return shlex.split(text)


def run_project(project: Project, args: Sequence[str]) -> int:
    """Ejecuta el proyecto como proceso independiente y devuelve su código de salida."""
    command = [sys.executable, "-m", project.package, *args]
    shown = " ".join(["python", "-m", project.package, *args])
    print(f"\n> {shown}\n  (en {project.path.relative_to(ROOT)})\n")
    return subprocess.run(command, cwd=project.path, check=False).returncode


def run_tests(project: Project) -> int:
    """Ejecuta pytest dentro de la carpeta del proyecto."""
    if importlib.util.find_spec("pytest") is None:
        print("pytest no está instalado. Ejecuta: python -m pip install -r requirements-dev.txt")
        return 1
    print(f"\n> python -m pytest  (en {project.path.relative_to(ROOT)})")
    return subprocess.run([sys.executable, "-m", "pytest"], cwd=project.path, check=False).returncode


def list_projects() -> None:
    for project in PROJECTS:
        status = "disponible" if project.available else "pendiente"
        print(f"{project.number:>2}. [{status:<10}] {project.title}  ({project.folder}/)")


def test_all() -> int:
    """Ejecuta las pruebas de cada proyecto disponible. Devuelve 1 si alguna falla."""
    available = [p for p in PROJECTS if p.available]
    failed = [p for p in available if run_tests(p) != 0]
    print(f"\nProyectos probados: {len(available)} | con fallos: {len(failed)}")
    for project in failed:
        print(f"  - {project.folder}")
    return 1 if failed or not available else 0


def _ask(prompt: str) -> str:
    return input(prompt).strip()


def project_menu(project: Project) -> None:
    while True:
        print(f"\n{project.number:02d} - {project.title}")
        print("  1. Demostración con datos de ejemplo")
        print("  2. Ejecutar con mis propios argumentos")
        print("  3. Ver ayuda (--help)")
        print("  4. Ejecutar pruebas")
        print("  0. Volver")
        choice = _ask("Opción: ")
        if choice == "1":
            run_project(project, project.demo)
        elif choice == "2":
            text = _ask(f"Argumentos para 'python -m {project.package}': ")
            try:
                run_project(project, split_arguments(text))
            except ValueError as exc:
                print(f"No se pudieron leer los argumentos: {exc}")
        elif choice == "3":
            run_project(project, ["--help"])
        elif choice == "4":
            run_tests(project)
        elif choice == "0":
            return
        else:
            print("Opción no válida.")


def interactive() -> int:
    by_number = {str(p.number): p for p in PROJECTS}
    while True:
        print("\nCybersecurity Python Lab - herramientas de laboratorio y aprendizaje")
        list_projects()
        print(" T. Ejecutar pruebas de todos los proyectos disponibles")
        print(" 0. Salir")
        choice = _ask("Elige un proyecto: ").upper()
        if choice == "0":
            return 0
        if choice == "T":
            test_all()
            continue
        project = by_number.get(choice.lstrip("0") or "0")
        if project is None:
            print("Opción no válida.")
        elif not project.available:
            print(f"El proyecto {project.number} todavía no está implementado (ver docs/ARQUITECTURA.md).")
        else:
            project_menu(project)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Menú de Cybersecurity Python Lab")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--list", action="store_true", help="muestra los proyectos y su estado")
    group.add_argument("--test-all", action="store_true", help="ejecuta las pruebas de todos los proyectos disponibles")
    args = parser.parse_args(argv)

    if args.list:
        list_projects()
        return 0
    if args.test_all:
        return test_all()
    try:
        return interactive()
    except (KeyboardInterrupt, EOFError):
        print("\nHasta luego.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
