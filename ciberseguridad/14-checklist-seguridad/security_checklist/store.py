"""Plantilla y avance de la checklist: lectura, validación y guardado seguro.

La plantilla (qué tareas existen) y el avance (qué hiciste) viven en archivos
distintos. Así puedes actualizar la plantilla sin perder tu avance, y tu avance
(que puede tener notas personales) no se sube al repositorio: se guarda en
``output/``, carpeta que ``.gitignore`` ignora.

El avance se guarda de forma atómica (archivo temporal + ``os.replace``): si
el programa se interrumpe al guardar, el archivo anterior sigue intacto. Si el
archivo de avance está dañado, NO se sobrescribe: se pide revisarlo.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_TEMPLATE = PROJECT_DIR / "data" / "plantilla.json"
DEFAULT_STATE = PROJECT_DIR / "output" / "mi_checklist.json"
STATUSES = ("pendiente", "en_progreso", "hecho", "no_aplica")
MAX_NOTE = 500


class ChecklistError(Exception):
    """Plantilla o avance inválidos, id desconocido, estado no válido..."""


@dataclass(frozen=True)
class Task:
    id: str
    category: str
    title: str
    why: str


@dataclass
class Progress:
    status: str = "pendiente"
    note: str = ""
    updated: str = ""


@dataclass
class Checklist:
    tasks: list[Task]
    progress: dict[str, Progress] = field(default_factory=dict)
    orphans: list[str] = field(default_factory=list)  # ids del avance que ya no están en la plantilla

    def get(self, task_id: str) -> Progress:
        return self.progress.setdefault(task_id, Progress())

    def counts(self) -> dict[str, int]:
        result = {status: 0 for status in STATUSES}
        for task in self.tasks:
            result[self.get(task.id).status] += 1
        return result

    def percent_done(self) -> float:
        counts = self.counts()
        applicable = len(self.tasks) - counts["no_aplica"]
        return 100.0 * counts["hecho"] / applicable if applicable else 100.0


def load_template(path: Path | None = None) -> list[Task]:
    template_path = path or DEFAULT_TEMPLATE
    try:
        raw = json.loads(template_path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError as exc:
        raise ChecklistError(f"No existe la plantilla: {template_path}") from exc
    except json.JSONDecodeError as exc:
        raise ChecklistError(f"{template_path} no es JSON válido (línea {exc.lineno}): {exc.msg}") from exc
    items = raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(items, list) or not items:
        raise ChecklistError("la plantilla debe tener una lista 'items' con al menos una tarea")
    tasks, errors, seen = [], [], set()
    for position, item in enumerate(items, start=1):
        missing = [k for k in ("id", "categoria", "tarea", "por_que") if not isinstance(item, dict) or not str(item.get(k, "")).strip()]
        if missing:
            errors.append(f"item #{position}: falta {', '.join(missing)}")
        elif item["id"] in seen:
            errors.append(f"item #{position}: id repetido '{item['id']}'")
        else:
            seen.add(item["id"])
            tasks.append(Task(item["id"].strip(), item["categoria"].strip(), item["tarea"].strip(), item["por_que"].strip()))
    if errors:
        raise ChecklistError("la plantilla tiene errores:\n  - " + "\n  - ".join(errors))
    return tasks


def load_checklist(template: Path | None = None, state: Path | None = None) -> Checklist:
    checklist = Checklist(load_template(template))
    state_path = state or DEFAULT_STATE
    if not state_path.exists():
        return checklist  # primera vez: todo pendiente
    try:
        raw = json.loads(state_path.read_text(encoding="utf-8-sig"))
        entries = raw["items"]
        if not isinstance(entries, dict):
            raise TypeError("'items' debe ser un objeto")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ChecklistError(
            f"No se pudo leer tu avance en {state_path} ({exc}). No se sobrescribió; "
            "revísalo o muévelo a otro lugar para empezar de nuevo."
        ) from exc
    known = {task.id for task in checklist.tasks}
    for task_id, value in entries.items():
        if task_id not in known:
            checklist.orphans.append(task_id)
            continue
        status = value.get("estado") if isinstance(value, dict) else None
        if status not in STATUSES:
            raise ChecklistError(f"estado inválido para '{task_id}' en {state_path}: {status!r}")
        checklist.progress[task_id] = Progress(status, str(value.get("nota", ""))[:MAX_NOTE], str(value.get("actualizado", "")))
    return checklist


def save_checklist(checklist: Checklist, state: Path | None = None) -> Path:
    state_path = state or DEFAULT_STATE
    state_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "_ayuda": "Tu avance. Se edita con 'python -m security_checklist mark'. No lo subas a Git.",
        "version": 1,
        "guardado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "items": {
            task_id: {"estado": p.status, "nota": p.note, "actualizado": p.updated}
            for task_id, p in checklist.progress.items()
            if p.status != "pendiente" or p.note
        },
    }
    tmp = state_path.with_name(state_path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, state_path)
    return state_path


def mark(checklist: Checklist, task_id: str, status: str, note: str | None = None) -> Task:
    task = next((t for t in checklist.tasks if t.id == task_id), None)
    if task is None:
        raise ChecklistError(f"no existe la tarea '{task_id}'. Usa 'list' para ver los id.")
    if status not in STATUSES:
        raise ChecklistError(f"estado inválido '{status}' (usa {', '.join(STATUSES)})")
    progress = checklist.get(task_id)
    progress.status = status
    if note is not None:
        if len(note) > MAX_NOTE:
            raise ChecklistError(f"la nota tiene {len(note)} caracteres; el máximo es {MAX_NOTE}")
        progress.note = note.strip()
    progress.updated = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return task
