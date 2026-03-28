import os
from dataclasses import dataclass

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

    # 视频生成平台选择: auto / dreamina / runway / pika
    VIDEO_PROVIDER: str = os.getenv("VIDEO_PROVIDER", "auto")

    # 新闻 API
    NEWS_API_KEY: str = os.getenv("NEWS_API_KEY", "")

    # 代理设置
    HTTP_PROXY: str = os.getenv("HTTP_PROXY", "")
    HTTPS_PROXY: str = os.getenv("HTTPS_PROXY", "")

    # 输出配置
    OUTPUT_DIR: str = "output"

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

    @classmethod
    def validate(cls) -> list[str]:
        """验证必要配置"""
        errors = []
        config = cls()

        if not config.LLM_API_KEY:
            errors.append(
                f"缺少 LLM_API_KEY 环境变量（当前 LLM_PROVIDER={config.LLM_PROVIDER}）"
            )

        # 检查至少一个视频生成平台
        has_video_api = any([
            config.RUNWAY_API_KEY,
            config.PIKA_API_KEY,
            all([config.VOLC_ACCESS_KEY, config.VOLC_SECRET_KEY]),
        ])

        if not has_video_api:
            errors.append(
                "至少需要配置一个视频生成 API:\n"
                "  - 即梦(推荐): VOLC_ACCESS_KEY + VOLC_SECRET_KEY\n"
                "  - Runway: RUNWAY_API_KEY\n"
                "  - Pika: PIKA_API_KEY"
            )

        return errors
