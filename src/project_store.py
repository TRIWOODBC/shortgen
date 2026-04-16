import json
import os
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import Character, Storyboard


BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output"
PROJECTS_DIR = OUTPUT_DIR / "projects"


def slugify_project_name(name: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff_-]+", "-", name.strip())
    cleaned = re.sub(r"-{2,}", "-", cleaned).strip("-")
    return cleaned or f"project_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def get_projects_root() -> Path:
    return PROJECTS_DIR


def get_project_root(project_id: str) -> Path:
    return get_projects_root() / project_id


def set_project_environment(project_id: str) -> Path:
    project_root = get_project_root(project_id)
    os.environ["PROJECT_OUTPUT_ROOT"] = str(project_root)
    return project_root


def ensure_project_dirs(project_id: str) -> Path:
    project_root = set_project_environment(project_id)
    for name in ("storyboards", "characters", "images", "videos", "audios", "final"):
        (project_root / name).mkdir(parents=True, exist_ok=True)
    return project_root


def get_project_meta_path(project_id: str) -> Path:
    return get_project_root(project_id) / "project.json"


def load_project_meta(project_id: str) -> dict[str, Any]:
    meta_path = get_project_meta_path(project_id)
    if not meta_path.exists():
        return {
            "id": project_id,
            "name": project_id,
            "plot": "",
            "manual_characters": [],
            "next_character_id": 1,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    meta.setdefault("next_character_id", 1)
    return meta


def save_project_meta(project_id: str, meta: dict[str, Any]) -> dict[str, Any]:
    ensure_project_dirs(project_id)
    meta.setdefault("id", project_id)
    meta.setdefault("name", project_id)
    meta.setdefault("next_character_id", 1)
    meta.setdefault("created_at", datetime.now().isoformat())
    meta["updated_at"] = datetime.now().isoformat()
    get_project_meta_path(project_id).write_text(
        json.dumps(meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return meta


def get_storyboard_json_path(project_id: str) -> Path:
    return get_project_root(project_id) / "storyboards" / f"{project_id}.json"


def get_storyboard_md_path(project_id: str) -> Path:
    return get_project_root(project_id) / "storyboards" / f"{project_id}.md"


def load_storyboard(project_id: str) -> Storyboard | None:
    storyboard_path = get_storyboard_json_path(project_id)
    if not storyboard_path.exists():
        return None
    return Storyboard.model_validate_json(storyboard_path.read_text(encoding="utf-8"))


def collect_project_summary(project_id: str) -> dict[str, Any]:
    root = get_project_root(project_id)
    meta = load_project_meta(project_id)
    storyboard = load_storyboard(project_id)
    manual_characters = meta.get("manual_characters", [])

    def rel(path: Path) -> str:
        return str(path.relative_to(root.parent.parent))

    characters = sorted((root / "characters").glob("*"))
    images = sorted((root / "images").glob("*"))
    videos = sorted((root / "videos").glob("*"))

    return {
        "id": project_id,
        "name": meta.get("name", project_id),
        "plot": meta.get("plot", ""),
        "manual_characters": manual_characters,
        "created_at": meta.get("created_at"),
        "updated_at": meta.get("updated_at"),
        "has_storyboard": storyboard is not None,
        "storyboard": storyboard.model_dump(mode="json") if storyboard else None,
        "counts": {
            "characters": len(characters),
            "images": len(images),
            "videos": len(videos),
            "scenes": len(storyboard.scenes) if storyboard else 0,
        },
        "assets": {
            "characters": [rel(path) for path in characters],
            "images": [rel(path) for path in images],
            "videos": [rel(path) for path in videos],
            "storyboard_json": rel(get_storyboard_json_path(project_id))
            if get_storyboard_json_path(project_id).exists()
            else None,
            "storyboard_md": rel(get_storyboard_md_path(project_id))
            if get_storyboard_md_path(project_id).exists()
            else None,
        },
    }


def load_manual_characters(project_id: str) -> list[Character]:
    meta = load_project_meta(project_id)
    return [Character.model_validate(item) for item in meta.get("manual_characters", [])]


def save_manual_characters(project_id: str, characters: list[Character]) -> list[dict[str, Any]]:
    meta = load_project_meta(project_id)
    meta["manual_characters"] = [character.model_dump(mode="json") for character in characters]
    save_project_meta(project_id, meta)
    return meta["manual_characters"]


def allocate_character_id(project_id: str) -> str:
    meta = load_project_meta(project_id)
    next_id = int(meta.get("next_character_id", 1) or 1)
    meta["next_character_id"] = next_id + 1
    save_project_meta(project_id, meta)
    return str(next_id)


def sync_next_character_id(project_id: str) -> int:
    meta = load_project_meta(project_id)
    storyboard = load_storyboard(project_id)
    manual_characters = load_manual_characters(project_id)

    numeric_ids: list[int] = []
    for character in manual_characters:
        if character.id.isdigit():
            numeric_ids.append(int(character.id))

    if storyboard:
        for character in storyboard.characters:
            if character.id.isdigit():
                numeric_ids.append(int(character.id))

    current_next = int(meta.get("next_character_id", 1) or 1)
    expected_next = (max(numeric_ids) + 1) if numeric_ids else 1
    meta["next_character_id"] = max(current_next, expected_next)
    save_project_meta(project_id, meta)
    return int(meta["next_character_id"])


def delete_project(project_id: str) -> None:
    root = get_project_root(project_id)
    if root.exists():
        shutil.rmtree(root)


def delete_storyboard_files(project_id: str) -> None:
    for path in (get_storyboard_json_path(project_id), get_storyboard_md_path(project_id)):
        if path.exists():
            path.unlink()


def delete_project_file(path_str: str | None) -> None:
    if not path_str:
        return

    path = Path(path_str)
    if path.exists() and path.is_file():
        path.unlink()


def _replace_root_in_value(value: Any, old_root: Path, new_root: Path) -> Any:
    """递归更新项目内存储的绝对路径。"""
    if isinstance(value, str):
        try:
            path = Path(value)
            if path.is_absolute():
                relative = path.resolve().relative_to(old_root.resolve())
                return str(new_root.resolve() / relative)
        except Exception:
            pass

        old_root_str = str(old_root.resolve())
        if value.startswith(old_root_str):
            return str(new_root.resolve()) + value[len(old_root_str):]
        return value

    if isinstance(value, list):
        return [_replace_root_in_value(item, old_root, new_root) for item in value]

    if isinstance(value, dict):
        return {
            key: _replace_root_in_value(item, old_root, new_root)
            for key, item in value.items()
        }

    return value


def rename_project(project_id: str, new_name: str) -> str:
    """重命名项目目录，并同步更新项目内元数据与分镜文件名。"""
    old_root = get_project_root(project_id)
    if not old_root.exists():
        raise FileNotFoundError("项目不存在")

    new_project_id = slugify_project_name(new_name)
    new_root = get_project_root(new_project_id)
    if new_root.exists() and new_project_id != project_id:
        raise FileExistsError("目标项目名已存在")

    old_meta_path = old_root / "project.json"
    old_storyboard_json_path = old_root / "storyboards" / f"{project_id}.json"
    old_storyboard_md_path = old_root / "storyboards" / f"{project_id}.md"

    old_meta = json.loads(old_meta_path.read_text(encoding="utf-8")) if old_meta_path.exists() else {}
    old_storyboard = (
        json.loads(old_storyboard_json_path.read_text(encoding="utf-8"))
        if old_storyboard_json_path.exists()
        else None
    )
    old_storyboard_md = old_storyboard_md_path.read_text(encoding="utf-8") if old_storyboard_md_path.exists() else None

    if new_project_id != project_id:
        old_root.rename(new_root)
    else:
        new_root = old_root

    updated_meta = _replace_root_in_value(old_meta, old_root, new_root)
    updated_meta["id"] = new_project_id
    updated_meta["name"] = new_name
    updated_meta["updated_at"] = datetime.now().isoformat()
    (new_root / "project.json").write_text(
        json.dumps(updated_meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    storyboard_dir = new_root / "storyboards"
    old_json_after_rename = storyboard_dir / f"{project_id}.json"
    old_md_after_rename = storyboard_dir / f"{project_id}.md"
    new_json_path = storyboard_dir / f"{new_project_id}.json"
    new_md_path = storyboard_dir / f"{new_project_id}.md"

    if old_storyboard is not None:
        updated_storyboard = _replace_root_in_value(old_storyboard, old_root, new_root)
        new_json_path.write_text(
            json.dumps(updated_storyboard, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        if old_json_after_rename.exists() and old_json_after_rename != new_json_path:
            old_json_after_rename.unlink()

    if old_storyboard_md is not None:
        updated_md = old_storyboard_md.replace(str(old_root), str(new_root))
        new_md_path.write_text(updated_md, encoding="utf-8")
        if old_md_after_rename.exists() and old_md_after_rename != new_md_path:
            old_md_after_rename.unlink()

    return new_project_id


def list_projects() -> list[dict[str, Any]]:
    root = get_projects_root()
    root.mkdir(parents=True, exist_ok=True)
    project_ids = sorted(
        [path.name for path in root.iterdir() if path.is_dir()],
        reverse=True,
    )
    return [collect_project_summary(project_id) for project_id in project_ids]
