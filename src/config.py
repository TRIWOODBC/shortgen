import os
from dataclasses import dataclass


@dataclass
class Config:
    """配置管理"""

    # Claude API
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # 视频生成 API
    RUNWAY_API_KEY: str = os.getenv("RUNWAY_API_KEY", "")
    PIKA_API_KEY: str = os.getenv("PIKA_API_KEY", "")

    # 即梦 (Dreamina) 认证信息
    DREAMINA_SESSION_ID: str = os.getenv("DREAMINA_SESSION_ID", "")
    DREAMINA_UID: str = os.getenv("DREAMINA_UID", "")
    DREAMINA_DID: str = os.getenv("DREAMINA_DID", "")

    # 新闻 API
    NEWS_API_KEY: str = os.getenv("NEWS_API_KEY", "")

    # 代理设置
    HTTP_PROXY: str = os.getenv("HTTP_PROXY", "")
    HTTPS_PROXY: str = os.getenv("HTTPS_PROXY", "")

    # 输出配置
    OUTPUT_DIR: str = "output"

    @classmethod
    def validate(cls) -> list[str]:
        """验证必要配置"""
        errors = []
        config = cls()

        if not config.ANTHROPIC_API_KEY:
            errors.append("缺少 ANTHROPIC_API_KEY 环境变量")

        # 检查至少一个视频生成平台
        has_video_api = any([
            config.RUNWAY_API_KEY,
            config.PIKA_API_KEY,
            all([config.DREAMINA_SESSION_ID, config.DREAMINA_UID, config.DREAMINA_DID])
        ])

        if not has_video_api:
            errors.append("至少需要配置一个视频生成 API: RUNWAY_API_KEY / PIKA_API_KEY / 或即梦认证信息")

        return errors
