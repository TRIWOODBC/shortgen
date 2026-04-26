from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from main import setup_directories
from src.character_manager import CharacterManager
from src.scene_image_gen import SceneImageGenerator
from src.video_gen import VideoGenerator
from src.storyboard import StoryboardGenerator
from src.models import Character, Scene, Storyboard
from src.project_store import (
    allocate_character_id,
    collect_project_summary,
    delete_project,
    delete_project_file,
    delete_storyboard_files,
    ensure_project_dirs,
    get_project_root,
    list_projects,
    load_manual_characters,
    load_project_meta,
    load_storyboard,
    rename_project,
    save_manual_characters,
    save_project_meta,
    set_project_environment,
    slugify_project_name,
    sync_next_character_id,
)
from src.runtime_settings import CONFIG_FIELDS, get_api_settings_payload, save_runtime_config


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
OUTPUT_DIR = BASE_DIR / "output"

app = FastAPI(title="ShortGen Studio")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media", StaticFiles(directory=str(OUTPUT_DIR)), name="media")
app.mount("/web", StaticFiles(directory=str(WEB_DIR)), name="web")


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1)
    plot: str = ""


class RenameProjectRequest(BaseModel):
    name: str = Field(..., min_length=1)


class PlotRequest(BaseModel):
    plot: str = Field(..., min_length=1)
    extract_characters: bool = True


class StoryboardUpdateRequest(BaseModel):
    storyboard: dict[str, Any]


class ManualCharacterRequest(BaseModel):
    id: str | None = None
    name: str = Field(..., min_length=1)
    description: str = Field(default="")


class CharacterAssistRequest(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = Field(default="")


class ManualStoryboardRequest(BaseModel):
    title: str = Field(default="未命名分镜项目")
    summary: str = Field(default="")
    plot: str = Field(default="")


class ApiSettingsUpdateRequest(BaseModel):
    settings: dict[str, str | None]


def _web_path(relative_path: str | None) -> str | None:
    if not relative_path:
        return None
    return f"/media/{relative_path}"


def _to_media_url(path_str: str | None) -> str | None:
    if not path_str:
        return None

    path = Path(path_str)
    if not path.is_absolute():
        if path.parts and path.parts[0] == "output":
            return _web_path(str(Path(*path.parts[1:])))
        return _web_path(str(path))

    try:
        relative = path.resolve().relative_to(OUTPUT_DIR.resolve())
        return _web_path(str(relative))
    except ValueError:
        return None


def _summary_with_web_assets(project_id: str) -> dict[str, Any]:
    summary = collect_project_summary(project_id)
    assets = summary["assets"]
    summary["assets"] = {
        key: [_web_path(path) for path in value] if isinstance(value, list) else _web_path(value)
        for key, value in assets.items()
    }

    storyboard = summary.get("storyboard")
    if storyboard:
        for character in storyboard.get("characters", []):
            character["image_url"] = _to_media_url(character.get("image_path"))

        for scene in storyboard.get("scenes", []):
            scene["scene_image_url"] = _to_media_url(scene.get("scene_image_path"))
            scene["reference_image_url"] = _to_media_url(scene.get("reference_image"))
            scene["video_url"] = _to_media_url(scene.get("video_path"))

    for character in summary.get("manual_characters", []):
        character["image_url"] = _to_media_url(character.get("image_path"))

    return summary


def _merge_characters(preferred: list[Character], fallback: list[Character]) -> list[Character]:
    merged: dict[str, Character] = {character.id: character for character in fallback}
    for character in preferred:
        merged[character.id] = character
    return list(merged.values())


def _enforce_manual_characters(storyboard: Storyboard, manual_characters: list[Character]) -> Storyboard:
    """当项目里已经有手动角色时，强制分镜稿只复用这些角色。"""
    if not manual_characters:
        return storyboard

    allowed_ids = {character.id for character in manual_characters}
    allowed_names = {
        character.id: [character.name.strip(), *(character.description.split("，")[:2] if character.description else [])]
        for character in manual_characters
    }

    storyboard.characters = manual_characters

    for scene in storyboard.scenes:
        filtered_ids = [character_id for character_id in scene.character_ids if character_id in allowed_ids]

        if not filtered_ids:
            text = f"{scene.description} {scene.prompt}".lower()
            inferred = []
            for character in manual_characters:
                keywords = [kw for kw in allowed_names.get(character.id, []) if kw]
                if any(keyword.lower() in text for keyword in keywords):
                    inferred.append(character.id)
            filtered_ids = inferred

        if not filtered_ids and len(manual_characters) == 1:
            filtered_ids = [manual_characters[0].id]

        scene.character_ids = list(dict.fromkeys(filtered_ids))

    return storyboard


def _ensure_scene_character_ids(storyboard: Storyboard) -> Storyboard:
    """尽量为场景补齐 character_ids，避免参考角色图时丢失绑定。"""
    if not storyboard.characters:
        return storyboard

    character_map = {character.id: character for character in storyboard.characters}

    if len(storyboard.characters) == 1:
        only_id = storyboard.characters[0].id
        for scene in storyboard.scenes:
            if not scene.character_ids:
                scene.character_ids = [only_id]
        return storyboard

    for scene in storyboard.scenes:
        if scene.character_ids:
            continue

        text = f"{scene.description} {scene.prompt}".lower()
        inferred_ids: list[str] = []
        for character in storyboard.characters:
            keywords = [character.name.strip()]
            if character.description:
                keywords.extend(
                    part.strip()
                    for part in character.description.replace("，", ",").split(",")[:2]
                    if part.strip()
                )

            if any(keyword.lower() in text for keyword in keywords if keyword):
                inferred_ids.append(character.id)

        scene.character_ids = list(dict.fromkeys([
            character_id for character_id in inferred_ids if character_id in character_map
        ]))

    return storyboard


def _upsert_character(
    project_id: str,
    character_id: str,
    name: str,
    description: str,
    image_path: str | None = None,
) -> None:
    manual_characters = load_manual_characters(project_id)
    existing = next((char for char in manual_characters if char.id == character_id), None)
    if existing:
        existing.name = name
        existing.description = description
        if image_path is not None:
            existing.image_path = image_path
    else:
        manual_characters.append(
            Character(
                id=character_id,
                name=name,
                description=description,
                image_path=image_path,
            )
        )

    save_manual_characters(project_id, manual_characters)

    storyboard = load_storyboard(project_id)
    if storyboard:
        matched = False
        for character in storyboard.characters:
            if character.id == character_id:
                character.name = name
                character.description = description
                if image_path is not None:
                    character.image_path = image_path
                matched = True
                break
        if not matched:
            storyboard.characters.append(
                Character(
                    id=character_id,
                    name=name,
                    description=description,
                    image_path=image_path,
                )
            )
        set_project_environment(project_id)
        StoryboardGenerator().save(storyboard, project_id)


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    html_path = WEB_DIR / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


@app.get("/api/settings/api")
async def api_get_settings() -> dict[str, Any]:
    return get_api_settings_payload()


@app.put("/api/settings/api")
async def api_update_settings(payload: ApiSettingsUpdateRequest) -> dict[str, Any]:
    unknown = [key for key in payload.settings.keys() if key not in CONFIG_FIELDS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"不支持的配置项: {', '.join(sorted(unknown))}")

    save_runtime_config(payload.settings)
    return {
        "ok": True,
        "message": "API 配置已保存到本地运行配置文件",
        **get_api_settings_payload(),
    }


@app.get("/api/projects")
async def api_list_projects() -> list[dict[str, Any]]:
    return [_summary_with_web_assets(item["id"]) for item in list_projects()]


@app.post("/api/projects")
async def api_create_project(payload: CreateProjectRequest) -> dict[str, Any]:
    project_id = slugify_project_name(payload.name)
    ensure_project_dirs(project_id)
    save_project_meta(
        project_id,
        {
            "id": project_id,
            "name": payload.name,
            "plot": payload.plot,
        },
    )
    return _summary_with_web_assets(project_id)


@app.put("/api/projects/{project_id}")
async def api_rename_project(project_id: str, payload: RenameProjectRequest) -> dict[str, Any]:
    root = get_project_root(project_id)
    if not root.exists():
        raise HTTPException(status_code=404, detail="项目不存在")

    try:
        new_project_id = rename_project(project_id, payload.name)
    except FileExistsError:
        raise HTTPException(status_code=400, detail="同名项目已存在")

    set_project_environment(new_project_id)
    return _summary_with_web_assets(new_project_id)


@app.delete("/api/projects/{project_id}")
async def api_delete_project(project_id: str) -> dict[str, Any]:
    root = get_project_root(project_id)
    if not root.exists():
        raise HTTPException(status_code=404, detail="项目不存在")

    delete_project(project_id)
    return {"ok": True, "project_id": project_id}


@app.get("/api/projects/{project_id}")
async def api_get_project(project_id: str) -> dict[str, Any]:
    root = get_project_root(project_id)
    if not root.exists():
        raise HTTPException(status_code=404, detail="项目不存在")
    return _summary_with_web_assets(project_id)


@app.post("/api/projects/{project_id}/storyboard/generate")
async def api_generate_storyboard(project_id: str, payload: PlotRequest) -> dict[str, Any]:
    ensure_project_dirs(project_id)
    set_project_environment(project_id)
    setup_directories()

    manual_characters = load_manual_characters(project_id)
    plot = payload.plot
    if manual_characters:
        manual_hint = "\n".join(
            f"- {character.id}: {character.name} / {character.description}"
            for character in manual_characters
        )
        plot = (
            f"{payload.plot}\n\n"
            "严格要求：请只使用以下已有角色设定和角色ID，不要新增任何新角色，不要创建新的角色ID。"
            "如果某一镜无法确定是哪位角色，也不要杜撰新角色，宁可让该镜头 character_ids 为空，后续由用户手动补充。\n"
            f"{manual_hint}"
        )

    storyboard_gen = StoryboardGenerator()
    storyboard = await storyboard_gen.generate(
        plot,
        extract_characters=payload.extract_characters,
    )
    if manual_characters:
        storyboard = _enforce_manual_characters(storyboard, manual_characters)
    storyboard = _ensure_scene_character_ids(storyboard)
    storyboard_gen.save(storyboard, project_id)

    meta = load_project_meta(project_id)
    meta["plot"] = payload.plot
    save_project_meta(project_id, meta)

    return _summary_with_web_assets(project_id)


@app.post("/api/projects/{project_id}/storyboard/manual")
async def api_create_manual_storyboard(project_id: str, payload: ManualStoryboardRequest) -> dict[str, Any]:
    ensure_project_dirs(project_id)
    set_project_environment(project_id)
    setup_directories()

    manual_characters = load_manual_characters(project_id)
    storyboard = Storyboard(
        title=payload.title or "未命名分镜项目",
        summary=payload.summary or payload.plot or "手动创建的分镜稿",
        scenes=[
            Scene(
                scene_number=1,
                description="请填写这一镜的中文描述",
                prompt="please write your visual prompt here",
                duration=5.0,
                character_ids=[character.id for character in manual_characters[:1]],
            )
        ],
        total_duration=5.0,
        characters=manual_characters,
    )
    StoryboardGenerator().save(storyboard, project_id)

    meta = load_project_meta(project_id)
    if payload.plot:
        meta["plot"] = payload.plot
        save_project_meta(project_id, meta)

    return _summary_with_web_assets(project_id)


@app.put("/api/projects/{project_id}/storyboard")
async def api_update_storyboard(project_id: str, payload: StoryboardUpdateRequest) -> dict[str, Any]:
    ensure_project_dirs(project_id)
    set_project_environment(project_id)
    setup_directories()

    storyboard = Storyboard.model_validate(payload.storyboard)
    storyboard_gen = StoryboardGenerator()
    storyboard_gen.save(storyboard, project_id)
    return _summary_with_web_assets(project_id)


@app.delete("/api/projects/{project_id}/storyboard")
async def api_delete_storyboard(project_id: str) -> dict[str, Any]:
    ensure_project_dirs(project_id)
    storyboard = load_storyboard(project_id)
    if not storyboard:
        raise HTTPException(status_code=404, detail="分镜稿不存在")

    for scene in storyboard.scenes:
        delete_project_file(scene.scene_image_path)
        delete_project_file(scene.video_path)

    delete_storyboard_files(project_id)
    return _summary_with_web_assets(project_id)


@app.post("/api/projects/{project_id}/storyboard/import")
async def api_import_storyboard(project_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
    ensure_project_dirs(project_id)
    set_project_environment(project_id)
    setup_directories()

    data = json.loads((await file.read()).decode("utf-8"))
    storyboard = Storyboard.model_validate(data)
    storyboard_gen = StoryboardGenerator()
    storyboard_gen.save(storyboard, project_id)
    return _summary_with_web_assets(project_id)


@app.post("/api/projects/{project_id}/characters/generate")
async def api_generate_characters(project_id: str, regenerate: bool = Form(default=False)) -> dict[str, Any]:
    storyboard = load_storyboard(project_id)
    if not storyboard:
        raise HTTPException(status_code=400, detail="请先生成或导入分镜稿")

    set_project_environment(project_id)
    setup_directories()
    manager = CharacterManager()
    manager.load_from_storyboard(storyboard)
    await manager.prepare_characters(storyboard.characters, regenerate=regenerate)

    StoryboardGenerator().save(storyboard, project_id)
    return _summary_with_web_assets(project_id)


@app.post("/api/projects/{project_id}/characters/{character_id}/upload")
async def api_upload_character_image(
    project_id: str,
    character_id: str,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    storyboard = load_storyboard(project_id)
    manual_characters = load_manual_characters(project_id)
    if not storyboard:
        storyboard = None

    root = ensure_project_dirs(project_id)
    target = root / "characters" / f"{character_id}.png"
    with target.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    found = False
    if storyboard:
        for character in storyboard.characters:
            if character.id == character_id:
                character.image_path = str(target)
                found = True
                break

    for character in manual_characters:
        if character.id == character_id:
            character.image_path = str(target)
            found = True
            break

    if not found:
        raise HTTPException(status_code=404, detail="角色不存在")

    save_manual_characters(project_id, manual_characters)
    set_project_environment(project_id)
    if storyboard:
        StoryboardGenerator().save(storyboard, project_id)
    return _summary_with_web_assets(project_id)


@app.post("/api/projects/{project_id}/characters/manual")
async def api_add_manual_character(project_id: str, payload: ManualCharacterRequest) -> dict[str, Any]:
    ensure_project_dirs(project_id)
    sync_next_character_id(project_id)
    manual_characters = load_manual_characters(project_id)

    character_id = allocate_character_id(project_id)
    new_character = Character(
        id=character_id,
        name=payload.name,
        description=payload.description,
    )

    manual_characters = [character for character in manual_characters if character.id != character_id]
    manual_characters.append(new_character)
    save_manual_characters(project_id, manual_characters)

    storyboard = load_storyboard(project_id)
    if storyboard:
        storyboard.characters = _merge_characters(manual_characters, storyboard.characters)
        set_project_environment(project_id)
        StoryboardGenerator().save(storyboard, project_id)

    return _summary_with_web_assets(project_id)


@app.put("/api/projects/{project_id}/characters/{character_id}")
async def api_update_character(
    project_id: str,
    character_id: str,
    payload: ManualCharacterRequest,
) -> dict[str, Any]:
    ensure_project_dirs(project_id)
    current_summary = _summary_with_web_assets(project_id)
    all_characters = {
        character["id"]: character
        for character in [
            *current_summary.get("manual_characters", []),
            *((current_summary.get("storyboard") or {}).get("characters") or []),
        ]
    }
    current = all_characters.get(character_id)
    image_path = current.get("image_path") if current else None
    _upsert_character(
        project_id=project_id,
        character_id=character_id,
        name=payload.name,
        description=payload.description,
        image_path=image_path,
    )
    return _summary_with_web_assets(project_id)


@app.delete("/api/projects/{project_id}/characters/{character_id}")
async def api_delete_character(project_id: str, character_id: str) -> dict[str, Any]:
    ensure_project_dirs(project_id)
    manual_characters = load_manual_characters(project_id)
    storyboard = load_storyboard(project_id)

    current_image_path: str | None = None
    matched = False

    filtered_manual_characters: list[Character] = []
    for character in manual_characters:
        if character.id == character_id:
            current_image_path = character.image_path or current_image_path
            matched = True
            continue
        filtered_manual_characters.append(character)

    save_manual_characters(project_id, filtered_manual_characters)

    if storyboard:
        filtered_storyboard_characters: list[Character] = []
        for character in storyboard.characters:
            if character.id == character_id:
                current_image_path = character.image_path or current_image_path
                matched = True
                continue
            filtered_storyboard_characters.append(character)

        storyboard.characters = filtered_storyboard_characters
        for scene in storyboard.scenes:
            scene.character_ids = [
                item for item in scene.character_ids if item != character_id
            ]

        set_project_environment(project_id)
        StoryboardGenerator().save(storyboard, project_id)

    if not matched:
        raise HTTPException(status_code=404, detail="角色不存在")

    delete_project_file(current_image_path)
    return _summary_with_web_assets(project_id)


@app.post("/api/projects/{project_id}/characters/assist-description")
async def api_assist_character_description(
    project_id: str,
    payload: CharacterAssistRequest,
) -> dict[str, Any]:
    ensure_project_dirs(project_id)
    helper = StoryboardGenerator()
    assisted = await helper.assist_character_description(
        name=payload.name,
        description=payload.description,
    )
    return assisted


@app.post("/api/projects/{project_id}/scene-images/generate")
async def api_generate_scene_images(
    project_id: str,
    regenerate: bool = Form(default=False),
    reference_scale: float = Form(default=0.3),
) -> dict[str, Any]:
    storyboard = load_storyboard(project_id)
    if not storyboard:
        raise HTTPException(status_code=400, detail="请先生成或导入分镜稿")

    reference_scale = max(0.0, min(1.0, reference_scale))

    set_project_environment(project_id)
    setup_directories()
    storyboard = _ensure_scene_character_ids(storyboard)
    generator = SceneImageGenerator()
    results = await generator.generate_for_storyboard(
        storyboard,
        output_name=project_id,
        reference_strength=reference_scale,
        regenerate=regenerate,
    )
    failed_results = [result for result in results if not result.status.startswith("success")]
    if failed_results:
        details = [
            {
                "scene_number": result.scene_number,
                "status": result.status,
                "error_message": result.error_message,
            }
            for result in failed_results
        ]
        raise HTTPException(
            status_code=400,
            detail={
                "message": "分镜图生成失败",
                "results": details,
            },
        )
    StoryboardGenerator().save(storyboard, project_id)
    return _summary_with_web_assets(project_id)


@app.post("/api/projects/{project_id}/scene-images/{scene_number}/upload")
async def api_upload_scene_image(
    project_id: str,
    scene_number: int,
    file: UploadFile = File(...),
) -> dict[str, Any]:
    storyboard = load_storyboard(project_id)
    if not storyboard:
        raise HTTPException(status_code=400, detail="请先生成、导入或手动创建分镜稿")

    root = ensure_project_dirs(project_id)
    target = root / "images" / f"{project_id}_scene{scene_number}.png"
    with target.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    matched = False
    for scene in storyboard.scenes:
        if scene.scene_number == scene_number:
            scene.scene_image_path = str(target)
            scene.reference_image = str(target)
            matched = True
            break

    if not matched:
        raise HTTPException(status_code=404, detail="场景不存在")

    set_project_environment(project_id)
    StoryboardGenerator().save(storyboard, project_id)
    return _summary_with_web_assets(project_id)


@app.delete("/api/projects/{project_id}/scene-images/{scene_number}")
async def api_delete_scene_image(project_id: str, scene_number: int) -> dict[str, Any]:
    storyboard = load_storyboard(project_id)
    if not storyboard:
        raise HTTPException(status_code=400, detail="请先生成、导入或手动创建分镜稿")

    matched = False
    for scene in storyboard.scenes:
        if scene.scene_number != scene_number:
            continue

        delete_project_file(scene.scene_image_path)
        scene.scene_image_path = None
        scene.reference_image = None
        matched = True
        break

    if not matched:
        raise HTTPException(status_code=404, detail="场景不存在")

    set_project_environment(project_id)
    StoryboardGenerator().save(storyboard, project_id)
    return _summary_with_web_assets(project_id)


@app.post("/api/projects/{project_id}/videos/generate")
async def api_generate_videos(
    project_id: str,
    regenerate: bool = Form(default=False),
) -> dict[str, Any]:
    storyboard = load_storyboard(project_id)
    if not storyboard:
        raise HTTPException(status_code=400, detail="请先生成、导入或手动创建分镜稿")

    set_project_environment(project_id)
    setup_directories()

    if regenerate:
        for scene in storyboard.scenes:
            delete_project_file(scene.video_path)
            scene.video_path = None

    generator = VideoGenerator(provider="auto")
    results = await generator.generate_from_storyboard(
        storyboard,
        output_name=project_id,
    )

    failed_results = [result for result in results if result.status != "success"]
    for result in results:
        if result.status != "success":
            continue

        for scene in storyboard.scenes:
            if scene.scene_number == result.scene_number:
                scene.video_path = result.file_path
                break

    StoryboardGenerator().save(storyboard, project_id)

    if failed_results:
        details = [
            {
                "scene_number": result.scene_number,
                "status": result.status,
                "error_message": result.error_message,
            }
            for result in failed_results
        ]
        raise HTTPException(
            status_code=400,
            detail={
                "message": "视频生成部分失败",
                "results": details,
            },
        )

    return _summary_with_web_assets(project_id)


@app.delete("/api/projects/{project_id}/videos/{scene_number}")
async def api_delete_video(project_id: str, scene_number: int) -> dict[str, Any]:
    storyboard = load_storyboard(project_id)
    if not storyboard:
        raise HTTPException(status_code=400, detail="请先生成、导入或手动创建分镜稿")

    matched = False
    for scene in storyboard.scenes:
        if scene.scene_number != scene_number:
            continue

        delete_project_file(scene.video_path)
        scene.video_path = None
        matched = True
        break

    if not matched:
        raise HTTPException(status_code=404, detail="场景不存在")

    set_project_environment(project_id)
    StoryboardGenerator().save(storyboard, project_id)
    return _summary_with_web_assets(project_id)


@app.get("/api/projects/{project_id}/storyboard/export")
async def api_export_storyboard(project_id: str) -> FileResponse:
    path = get_project_root(project_id) / "storyboards" / f"{project_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="分镜稿不存在")
    return FileResponse(path)
