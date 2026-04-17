import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

from src.runtime_settings import apply_runtime_config_to_env


load_dotenv()
apply_runtime_config_to_env()

# 预设的 LLM 平台配置
LLM_PRESETS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    },
    "glm": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4/",
        "model": "glm-4-flash",
    },
    "kimi": {
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o",
    },
}


@dataclass
class Config:
    """配置管理"""

    # LLM 配置（用于分镜脚本生成）
    # LLM_PROVIDER: deepseek / glm / kimi / openai / custom
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "deepseek")
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    # 以下两项为可选，不填则根据 LLM_PROVIDER 自动设置
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "")

    # 火山引擎 (Volcengine) 认证 — 用于即梦视频生成
    VOLC_ACCESS_KEY: str = os.getenv("VOLC_ACCESS_KEY", "")
    VOLC_SECRET_KEY: str = os.getenv("VOLC_SECRET_KEY", "")

    # 即梦视频模型 req_key
    JIMENG_MODEL: str = os.getenv("JIMENG_MODEL", "jimeng_t2v_v30")

    # 视频生成 API（备选平台）
    RUNWAY_API_KEY: str = os.getenv("RUNWAY_API_KEY", "")
    PIKA_API_KEY: str = os.getenv("PIKA_API_KEY", "")

    # 视频生成平台选择: dreamina / auto / runway / pika
    VIDEO_PROVIDER: str = os.getenv("VIDEO_PROVIDER", "dreamina")

    # 新闻 API
    NEWS_API_KEY: str = os.getenv("NEWS_API_KEY", "")

    # 代理设置
    HTTP_PROXY: str = os.getenv("HTTP_PROXY", "")
    HTTPS_PROXY: str = os.getenv("HTTPS_PROXY", "")

    # 输出配置
    OUTPUT_DIR: str = "output"

    # === 火山引擎 TTS 配置 ===
    VOLC_TTS_ACCESS_TOKEN: str = os.getenv("VOLC_TTS_ACCESS_TOKEN", "")
    VOLC_TTS_APP_ID: str = os.getenv("VOLC_TTS_APP_ID", "")
    VOLC_TTS_DEFAULT_VOICE: str = os.getenv(
        "VOLC_TTS_DEFAULT_VOICE",
        "zh_female_shuangkuaisisi_moon_bigtts"
    )

    # === Suno API 配置（AI 音乐生成）===
    SUNO_API_KEY: str = os.getenv("SUNO_API_KEY", "")
    SUNO_API_URL: str = os.getenv("SUNO_API_URL", "https://api.suno.ai/v1")

    # === Stable Audio API 配置（AI 音乐生成）===
    STABLE_AUDIO_API_KEY: str = os.getenv("STABLE_AUDIO_API_KEY", "")
    STABLE_AUDIO_API_URL: str = os.getenv(
        "STABLE_AUDIO_API_URL",
        "https://api.stability.ai/v2beta/audio"
    )

    # === 音乐库配置 ===
    MUSIC_LIBRARY_PATH: str = os.getenv("MUSIC_LIBRARY_PATH", "assets/music")

    # === 音频生成配置 ===
    AUDIO_PROVIDER: str = os.getenv("AUDIO_PROVIDER", "volcengine")
    AUDIO_OUTPUT_FORMAT: str = os.getenv("AUDIO_OUTPUT_FORMAT", "mp3")
    AUDIO_SAMPLE_RATE: int = int(os.getenv("AUDIO_SAMPLE_RATE", "44100"))

    # === 角色一致性配置 ===
    CHARACTER_IMAGE_DIR: str = os.getenv("CHARACTER_IMAGE_DIR", "output/characters")
    CHARACTER_IMAGE_PROVIDER: str = os.getenv("CHARACTER_IMAGE_PROVIDER", "signed_aksk")
    ARK_API_KEY: str = os.getenv("ARK_API_KEY", "")
    ARK_BASE_URL: str = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3")
    CHARACTER_IMAGE_MODEL: str = os.getenv(
        "CHARACTER_IMAGE_MODEL",
        "jimeng_t2i_v40"
    )
    PUBLIC_ASSET_BASE_URL: str = os.getenv("PUBLIC_ASSET_BASE_URL", "")

    # === 视频合成配置 ===
    FFMPEG_PATH: str = os.getenv("FFMPEG_PATH", "ffmpeg")
    VIDEO_CODEC: str = os.getenv("VIDEO_CODEC", "libx264")
    AUDIO_CODEC: str = os.getenv("AUDIO_CODEC", "aac")
    OUTPUT_FORMAT: str = os.getenv("OUTPUT_FORMAT", "mp4")

    def get_llm_base_url(self) -> str:
        """获取 LLM API base URL"""
        if self.LLM_BASE_URL:
            return self.LLM_BASE_URL
        preset = LLM_PRESETS.get(self.LLM_PROVIDER, {})
        return preset.get("base_url", "https://api.deepseek.com")

    def get_llm_model(self) -> str:
        """获取 LLM 模型名称"""
        if self.LLM_MODEL:
            return self.LLM_MODEL
        preset = LLM_PRESETS.get(self.LLM_PROVIDER, {})
        return preset.get("model", "deepseek-chat")

    def get_tts_config(self) -> dict:
        """获取 TTS 配置"""
        return {
            "access_token": self.VOLC_TTS_ACCESS_TOKEN,
            "app_id": self.VOLC_TTS_APP_ID,
            "default_voice": self.VOLC_TTS_DEFAULT_VOICE,
        }

    @classmethod
    def validate(cls) -> list[str]:
        """验证必要配置"""
        errors = []
        config = cls()

        if not config.LLM_API_KEY:
            errors.append(
                f"缺少 LLM_API_KEY 环境变量（当前 LLM_PROVIDER={config.LLM_PROVIDER}）"
            )

        provider = (config.VIDEO_PROVIDER or "dreamina").lower()
        has_jimeng = all([config.VOLC_ACCESS_KEY, config.VOLC_SECRET_KEY])
        has_runway = bool(config.RUNWAY_API_KEY)
        has_pika = bool(config.PIKA_API_KEY)

        if provider == "dreamina" and not has_jimeng:
            errors.append(
                "当前 VIDEO_PROVIDER=dreamina，但未完整配置即梦凭证:\n"
                "  需要 VOLC_ACCESS_KEY + VOLC_SECRET_KEY"
            )
        elif provider == "runway" and not has_runway:
            errors.append(
                "当前 VIDEO_PROVIDER=runway，但未配置 RUNWAY_API_KEY"
            )
        elif provider == "pika" and not has_pika:
            errors.append(
                "当前 VIDEO_PROVIDER=pika，但未配置 PIKA_API_KEY"
            )
        elif provider == "auto" and not any([has_jimeng, has_runway, has_pika]):
            errors.append(
                "VIDEO_PROVIDER=auto 时，至少需要配置一个视频生成 API:\n"
                "  - 即梦(推荐): VOLC_ACCESS_KEY + VOLC_SECRET_KEY\n"
                "  - Runway: RUNWAY_API_KEY\n"
                "  - Pika: PIKA_API_KEY"
            )

        return errors

    @classmethod
    def validate_audio(cls) -> list[str]:
        """验证音频功能配置"""
        warnings = []
        config = cls()

        if not config.VOLC_TTS_ACCESS_TOKEN or not config.VOLC_TTS_APP_ID:
            warnings.append(
                "未配置火山引擎 TTS，音频功能将不可用:\n"
                "  需要配置 VOLC_TTS_ACCESS_TOKEN 和 VOLC_TTS_APP_ID"
            )

        return warnings


def get_output_root() -> Path:
    """获取当前运行的输出根目录"""
    project_root = os.getenv("PROJECT_OUTPUT_ROOT")
    if project_root:
        return Path(project_root)
    return Path("output")


def resolve_output_dir(path_str: str) -> Path:
    """将配置中的输出目录解析到当前项目目录下。"""
    path = Path(path_str)
    if path.is_absolute():
        return path

    parts = list(path.parts)
    if parts and parts[0] == "output":
        parts = parts[1:]

    return get_output_root().joinpath(*parts)


def get_output_path(*parts: str) -> Path:
    """获取当前运行下的输出路径"""
    return get_output_root().joinpath(*parts)
