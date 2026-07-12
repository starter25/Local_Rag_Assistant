import json
import re
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from app.config import (
    CHAT_STORE_FILE,
    CHROMA_DIR,
    DEFAULT_PROJECT_ID,
    DOCUMENT_DIR,
    DOCUMENT_INDEX_FILE,
    PROJECTS_DIR,
    PROJECT_STORE_FILE,
)


PROJECT_STORE_LOCK = threading.Lock()


@dataclass(frozen=True)
class ProjectContext:
    id: str
    name: str
    base_dir: Path
    document_dir: Path
    chroma_dir: Path
    document_index_file: Path
    chat_store_file: Path


def _now() -> float:
    return time.time()


def _default_project(now: float | None = None) -> dict:
    timestamp = now or _now()

    return {
        "id": DEFAULT_PROJECT_ID,
        "name": "Default",
        "created_at": timestamp,
        "updated_at": timestamp,
    }


def _empty_store() -> dict:
    return {
        "version": 1,
        "active_project_id": DEFAULT_PROJECT_ID,
        "projects": [_default_project()],
    }


def normalize_project_id(name: str) -> str:
    value = (name or "").strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")

    return value or "project"


def _ensure_store_shape(store: dict) -> dict:
    if not isinstance(store, dict):
        store = _empty_store()

    projects = store.get("projects")

    if not isinstance(projects, list):
        projects = []

    normalized_projects = []
    seen_ids = set()

    for project in projects:
        if not isinstance(project, dict):
            continue

        project_id = normalize_project_id(project.get("id") or project.get("name") or "")

        if not project_id or project_id in seen_ids:
            continue

        timestamp = float(project.get("created_at") or _now())
        normalized = {
            "id": project_id,
            "name": str(project.get("name") or project_id),
            "created_at": timestamp,
            "updated_at": float(project.get("updated_at") or timestamp),
        }
        normalized_projects.append(normalized)
        seen_ids.add(project_id)

    if DEFAULT_PROJECT_ID not in seen_ids:
        normalized_projects.insert(0, _default_project())

    normalized_projects.sort(key=lambda item: (item["id"] != DEFAULT_PROJECT_ID, item["name"].lower()))

    active_project_id = store.get("active_project_id") or DEFAULT_PROJECT_ID

    if active_project_id not in {project["id"] for project in normalized_projects}:
        active_project_id = DEFAULT_PROJECT_ID

    return {
        "version": int(store.get("version") or 1),
        "active_project_id": active_project_id,
        "projects": normalized_projects,
    }


def load_project_store() -> dict:
    if not PROJECT_STORE_FILE.exists():
        return _empty_store()

    try:
        data = json.loads(PROJECT_STORE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_store()

    return _ensure_store_shape(data)


def save_project_store(store: dict):
    PROJECT_STORE_FILE.parent.mkdir(parents=True, exist_ok=True)
    normalized = _ensure_store_shape(store)
    temp_path = Path(str(PROJECT_STORE_FILE) + ".tmp")
    temp_path.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temp_path.replace(PROJECT_STORE_FILE)


def _unique_project_id(base_id: str, existing_ids: set[str]) -> str:
    project_id = base_id
    index = 2

    while project_id in existing_ids:
        project_id = f"{base_id}-{index}"
        index += 1

    return project_id


def _project_by_id(store: dict, project_id: str) -> dict | None:
    safe_id = normalize_project_id(project_id or DEFAULT_PROJECT_ID)

    for project in store["projects"]:
        if project["id"] == safe_id:
            return project

    return None


def _context_for_project(project: dict) -> ProjectContext:
    project_id = project["id"]
    name = project["name"]

    if project_id == DEFAULT_PROJECT_ID:
        return ProjectContext(
            id=project_id,
            name=name,
            base_dir=PROJECT_STORE_FILE.parent,
            document_dir=DOCUMENT_DIR,
            chroma_dir=CHROMA_DIR,
            document_index_file=DOCUMENT_INDEX_FILE,
            chat_store_file=CHAT_STORE_FILE,
        )

    base_dir = PROJECTS_DIR / project_id

    return ProjectContext(
        id=project_id,
        name=name,
        base_dir=base_dir,
        document_dir=base_dir / "documents",
        chroma_dir=base_dir / "chroma_db",
        document_index_file=base_dir / "document_index.json",
        chat_store_file=base_dir / "chats" / "chats.json",
    )


def ensure_project_dirs(context: ProjectContext):
    context.base_dir.mkdir(parents=True, exist_ok=True)
    context.document_dir.mkdir(parents=True, exist_ok=True)
    context.chroma_dir.mkdir(parents=True, exist_ok=True)
    context.document_index_file.parent.mkdir(parents=True, exist_ok=True)
    context.chat_store_file.parent.mkdir(parents=True, exist_ok=True)


def list_projects() -> dict:
    with PROJECT_STORE_LOCK:
        store = load_project_store()
        save_project_store(store)
        return store


def create_project(name: str) -> dict:
    clean_name = (name or "").strip()

    if not clean_name:
        raise ValueError("Project name is required.")

    with PROJECT_STORE_LOCK:
        store = load_project_store()
        existing_ids = {project["id"] for project in store["projects"]}
        project_id = _unique_project_id(normalize_project_id(clean_name), existing_ids)
        now = _now()
        project = {
            "id": project_id,
            "name": clean_name,
            "created_at": now,
            "updated_at": now,
        }
        store["projects"].append(project)
        save_project_store(store)
        ensure_project_dirs(_context_for_project(project))
        return project


def get_project(project_id: str = DEFAULT_PROJECT_ID) -> dict | None:
    store = load_project_store()
    return _project_by_id(store, project_id)


def get_project_context(project_id: str = DEFAULT_PROJECT_ID) -> ProjectContext:
    project = get_project(project_id)

    if not project:
        raise ValueError(f"Project not found: {project_id}")

    context = _context_for_project(project)
    ensure_project_dirs(context)
    return context


def project_context_to_dict(context: ProjectContext) -> dict:
    data = asdict(context)

    for key, value in data.items():
        if isinstance(value, Path):
            data[key] = str(value)

    return data
