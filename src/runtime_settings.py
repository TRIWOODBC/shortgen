from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


RUNTIME_CONFIG_PATH = Path(__file__).resolve().parent.parent / ".shortgen_runtime_config.json"

SECRET_FIELDS = {
    "LLM_API_KEY",
    "VOLC_ACCESS_KEY",
    "VOLC_SECRET_KEY",
    "RUNWAY_API_KEY",
    "PIKA_API_KEY",
    "ARK_API_KEY",
    "VOLC_TTS_ACCESS_TOKEN",
    "SUNO_API_KEY",
    "STABLE_AUDIO_API_KEY",
}

CONFIG_FIELDS = {
    "LLM_PROVIDER",
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "VIDEO_PROVIDER",
    "VOLC_ACCESS_KEY",
    "VOLC_SECRET_KEY",
    "JIMENG_MODEL",
    "RUNWAY_API_KEY",
    "PIKA_API_KEY",
    "CHARACTER_IMAGE_PROVIDER",
    "CHARACTER_IMAGE_MODEL",
    "PUBLIC_ASSET_BASE_URL",
    "ARK_API_KEY",
    "ARK_BASE_URL",
    "VOLC_TTS_ACCESS_TOKEN",
    "VOLC_TTS_APP_ID",
    "VOLC_TTS_DEFAULT_VOICE",
}


def load_runtime_config() -> dict[str, str]:
    if not RUNTIME_CONFIG_PATH.exists():
        return {}

    try:
        data = json.loads(RUNTIME_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if not isinstance(data, dict):
        return {}

    cleaned: dict[str, str] = {}
    for key, value in data.items():
        if key in CONFIG_FIELDS and isinstance(value, str):
            cleaned[key] = value
    return cleaned


def apply_runtime_config_to_env() -> dict[str, str]:
    config = load_runtime_config()
    for key, value in config.items():
        os.environ[key] = value
    return config


def save_runtime_config(updates: dict[str, Any]) -> dict[str, str]:
    existing = load_runtime_config()

    for key, value in updates.items():
        if key not in CONFIG_FIELDS:
            continue

        if value is None:
            continue

        text = str(value).strip()

        if key in SECRET_FIELDS and text == "":
            # 密钥字段留空时保持当前值，避免前端表单把已配置密钥清掉。
            continue

        existing[key] = text

    RUNTIME_CONFIG_PATH.write_text(
        json.dumps(existing, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    for key, value in existing.items():
        os.environ[key] = value

    return existing


def get_api_settings_payload() -> dict[str, Any]:
    runtime_config = load_runtime_config()
    payload: dict[str, Any] = {"values": {}, "configured": {}}

    for key in sorted(CONFIG_FIELDS):
        current = runtime_config.get(key, os.getenv(key, ""))
        if key in SECRET_FIELDS:
            payload["configured"][key] = bool(current)
        else:
            payload["values"][key] = current

    return payload
