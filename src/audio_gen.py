"""
音频生成模块 - 支持 TTS 和背景音乐生成

支持:
- 火山引擎 TTS (旁白、对话)
- Suno API (AI 音乐生成)
- Stable Audio (AI 音乐生成)
- 本地音乐库
"""

import asyncio
import base64
import random
import time
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime

import httpx

from .models import (
    AudioConfig, AudioResult, AudioType, Scene, Dialogue
)
from .config import Config, get_output_path


class AudioGenerator:
    """音频生成器 - 统一接口"""

    def __init__(self):
        config = Config()
        self.tts_token = config.VOLC_TTS_ACCESS_TOKEN
        self.tts_app_id = config.VOLC_TTS_APP_ID
        self.default_voice = config.VOLC_TTS_DEFAULT_VOICE
        self.suno_key = config.SUNO_API_KEY
        self.suno_url = config.SUNO_API_URL
        self.stable_audio_key = config.STABLE_AUDIO_API_KEY
        self.stable_audio_url = config.STABLE_AUDIO_API_URL
        self.music_library = Path(config.MUSIC_LIBRARY_PATH)
        self.output_dir = get_output_path("audios")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.proxy = config.HTTP_PROXY or None
        self._character_voices: Dict[str, str] = {}

    def set_character_voice(self, character_id: str, voice_id: str):
        """设置角色音色"""
        self._character_voices[character_id] = voice_id

    async def generate_for_scene(self, scene: Scene) -> List[AudioResult]:
        """
        为场景生成所有音频

        Args:
            scene: 场景对象

        Returns:
            音频生成结果列表
        """
        results = []

        # 1. 生成旁白
        if scene.narration:
            result = await self.generate_tts(
                text=scene.narration,
                scene_number=scene.scene_number,
                audio_type=AudioType.NARRATION
            )
            results.append(result)

        # 2. 生成对话
        for dialogue in scene.dialogues:
            voice_id = self._character_voices.get(
                dialogue.character_id,
                self.default_voice
            )
            result = await self.generate_tts(
                text=dialogue.text,
                scene_number=scene.scene_number,
                audio_type=AudioType.DIALOGUE,
                voice_id=voice_id
            )
            results.append(result)

        # 3. 处理自定义音频配置
        for audio_config in scene.audio_configs:
            result = await self.generate_audio(audio_config, scene.scene_number)
            results.append(result)

        return results

    async def generate_tts(
        self,
        text: str,
        scene_number: int,
        audio_type: AudioType,
        voice_id: Optional[str] = None
    ) -> AudioResult:
        """
        使用火山引擎 TTS 生成语音

        Args:
            text: 要合成的文本
            scene_number: 场景编号
            audio_type: 音频类型
            voice_id: 音色 ID

        Returns:
            音频生成结果
        """
        if not self.tts_token or not self.tts_app_id:
            return AudioResult(
                scene_number=scene_number,
                audio_type=audio_type,
                file_path="",
                duration=0,
                status="failed",
                error_message="未配置火山引擎 TTS (VOLC_TTS_ACCESS_TOKEN, VOLC_TTS_APP_ID)"
            )

        try:
            tts = VolcengineTTS(
                access_token=self.tts_token,
                app_id=self.tts_app_id,
                voice=voice_id or self.default_voice
            )

            audio_data = await tts.synthesize(text)

            # 保存音频文件
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"scene{scene_number}_{audio_type.value}_{timestamp}.mp3"
            output_path = self.output_dir / filename
            output_path.write_bytes(audio_data)

            duration = tts.estimate_duration(audio_data)

            return AudioResult(
                scene_number=scene_number,
                audio_type=audio_type,
                file_path=str(output_path),
                duration=duration,
                status="success"
            )

        except Exception as e:
            return AudioResult(
                scene_number=scene_number,
                audio_type=audio_type,
                file_path="",
                duration=0,
                status="failed",
                error_message=str(e)
            )

    async def generate_background_music(
        self,
        prompt: Optional[str] = None,
        local_path: Optional[str] = None,
        duration: float = 30.0,
        use_ai: bool = True
    ) -> AudioResult:
        """
        生成或获取背景音乐

        Args:
            prompt: AI 音乐生成提示词
            local_path: 本地音乐文件路径
            duration: 目标时长
            use_ai: 是否使用 AI 生成

        Returns:
            音频结果
        """
        # 优先使用本地音乐
        if local_path and Path(local_path).exists():
            return AudioResult(
                scene_number=0,
                audio_type=AudioType.BACKGROUND_MUSIC,
                file_path=local_path,
                duration=duration,
                status="success"
            )

        # AI 生成音乐
        if use_ai and prompt:
            if self.suno_key:
                return await self._generate_with_suno(prompt, duration)
            elif self.stable_audio_key:
                return await self._generate_with_stable_audio(prompt, duration)

        # 从本地音乐库随机选择
        return await self._get_random_from_library(duration)

    async def generate_audio(
        self,
        config: AudioConfig,
        scene_number: int
    ) -> AudioResult:
        """
        根据音频配置生成音频

        Args:
            config: 音频配置
            scene_number: 场景编号

        Returns:
            音频结果
        """
        if config.audio_type in (AudioType.NARRATION, AudioType.DIALOGUE):
            if not config.text:
                return AudioResult(
                    scene_number=scene_number,
                    audio_type=config.audio_type,
                    file_path="",
                    duration=0,
                    status="failed",
                    error_message="缺少 TTS 文本内容"
                )

            voice_id = config.voice_id
            if not voice_id and config.character_id:
                voice_id = self._character_voices.get(config.character_id)

            return await self.generate_tts(
                text=config.text,
                scene_number=scene_number,
                audio_type=config.audio_type,
                voice_id=voice_id
            )

        elif config.audio_type == AudioType.BACKGROUND_MUSIC:
            return await self.generate_background_music(
                prompt=config.music_prompt,
                local_path=config.music_path
            )

        return AudioResult(
            scene_number=scene_number,
            audio_type=config.audio_type,
            file_path="",
            duration=0,
            status="failed",
            error_message=f"不支持的音频类型: {config.audio_type}"
        )

    async def _get_random_from_library(self, duration: float) -> AudioResult:
        """从本地音乐库随机选择"""
        if not self.music_library.exists():
            return AudioResult(
                scene_number=0,
                audio_type=AudioType.BACKGROUND_MUSIC,
                file_path="",
                duration=0,
                status="failed",
                error_message=f"本地音乐库不存在: {self.music_library}"
            )

        music_files = list(self.music_library.glob("*.mp3"))
        if not music_files:
            music_files = list(self.music_library.glob("*.wav"))
        if not music_files:
            music_files = list(self.music_library.glob("*.m4a"))

        if not music_files:
            return AudioResult(
                scene_number=0,
                audio_type=AudioType.BACKGROUND_MUSIC,
                file_path="",
                duration=0,
                status="failed",
                error_message="本地音乐库为空"
            )

        selected = random.choice(music_files)
        return AudioResult(
            scene_number=0,
            audio_type=AudioType.BACKGROUND_MUSIC,
            file_path=str(selected),
            duration=duration,
            status="success"
        )

    async def _generate_with_suno(
        self,
        prompt: str,
        duration: float
    ) -> AudioResult:
        """使用 Suno API 生成音乐"""
        try:
            async with httpx.AsyncClient(proxies=self.proxy, timeout=120) as client:
                headers = {
                    "Authorization": f"Bearer {self.suno_key}",
                    "Content-Type": "application/json"
                }

                # Suno 生成请求
                payload = {
                    "prompt": prompt,
                    "duration": int(duration),
                    "instrumental": True,
                }

                response = await client.post(
                    f"{self.suno_url}/generate",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()

                # 获取生成的音乐 URL
                music_url = data.get("audio_url") or data.get("url")
                if not music_url:
                    return AudioResult(
                        scene_number=0,
                        audio_type=AudioType.BACKGROUND_MUSIC,
                        file_path="",
                        duration=0,
                        status="failed",
                        error_message="Suno 未返回音乐 URL"
                    )

                # 下载音乐
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = self.output_dir / f"bgm_suno_{timestamp}.mp3"

                audio_resp = await client.get(music_url)
                audio_resp.raise_for_status()
                output_path.write_bytes(audio_resp.content)

                return AudioResult(
                    scene_number=0,
                    audio_type=AudioType.BACKGROUND_MUSIC,
                    file_path=str(output_path),
                    duration=duration,
                    status="success"
                )

        except Exception as e:
            return AudioResult(
                scene_number=0,
                audio_type=AudioType.BACKGROUND_MUSIC,
                file_path="",
                duration=0,
                status="failed",
                error_message=f"Suno 生成失败: {e}"
            )

    async def _generate_with_stable_audio(
        self,
        prompt: str,
        duration: float
    ) -> AudioResult:
        """使用 Stable Audio API 生成音乐"""
        try:
            async with httpx.AsyncClient(proxies=self.proxy, timeout=120) as client:
                headers = {
                    "Authorization": f"Bearer {self.stable_audio_key}",
                    "Content-Type": "application/json"
                }

                payload = {
                    "text_prompts": [{"text": prompt}],
                    "audio_length": int(duration),
                }

                response = await client.post(
                    f"{self.stable_audio_url}/generate",
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()

                # 获取音乐数据
                audio_base64 = data.get("audio")
                if not audio_base64:
                    return AudioResult(
                        scene_number=0,
                        audio_type=AudioType.BACKGROUND_MUSIC,
                        file_path="",
                        duration=0,
                        status="failed",
                        error_message="Stable Audio 未返回音频数据"
                    )

                # 保存音乐
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = self.output_dir / f"bgm_stable_{timestamp}.mp3"
                output_path.write_bytes(base64.b64decode(audio_base64))

                return AudioResult(
                    scene_number=0,
                    audio_type=AudioType.BACKGROUND_MUSIC,
                    file_path=str(output_path),
                    duration=duration,
                    status="success"
                )

        except Exception as e:
            return AudioResult(
                scene_number=0,
                audio_type=AudioType.BACKGROUND_MUSIC,
                file_path="",
                duration=0,
                status="failed",
                error_message=f"Stable Audio 生成失败: {e}"
            )


class VolcengineTTS:
    """
    火山引擎 TTS 客户端

    API 文档: https://www.volcengine.com/docs/6561/79823
    """

    API_URL = "https://openspeech.bytedance.com/api/v1/tts"

    # 预设音色
    VOICES = {
        "female_gentle": "zh_female_shuangkuaisisi_moon_bigtts",
        "male_warm": "zh_male_chunhou_zhiboshuangkuai_moon_bigtts",
        "child": "zh_child_happy_moon_bigtts",
        "storyteller": "zh_female_wanwanroumei_moon_bigtts",
    }

    def __init__(
        self,
        access_token: str,
        app_id: str,
        voice: str = None,
        speed: float = 1.0,
        pitch: float = 1.0
    ):
        self.access_token = access_token
        self.app_id = app_id
        self.voice = voice or self.VOICES["female_gentle"]
        self.speed = speed
        self.pitch = pitch

    async def synthesize(self, text: str) -> bytes:
        """
        合成语音

        Args:
            text: 要合成的文本

        Returns:
            音频二进制数据 (MP3)
        """
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

        payload = {
            "app": {
                "appid": self.app_id,
                "token": "access_token",
            },
            "user": {
                "uid": "shortgen_user"
            },
            "audio": {
                "voice_type": self.voice,
                "encoding": "mp3",
                "speed_ratio": self.speed,
                "pitch_ratio": self.pitch,
                "volume_ratio": 1.0,
            },
            "request": {
                "reqid": f"req_{int(time.time() * 1000)}",
                "text": text,
                "text_type": "plain",
                "operation": "query"
            }
        }

        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(
                self.API_URL,
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()

        if data.get("code") != 3000:
            raise ValueError(
                f"TTS 合成失败 (code={data.get('code')}): "
                f"{data.get('message', 'Unknown error')}"
            )

        # 解码 base64 音频数据
        audio_base64 = data.get("data")
        if not audio_base64:
            raise ValueError("响应中没有音频数据")

        return base64.b64decode(audio_base64)

    def estimate_duration(self, audio_data: bytes) -> float:
        """
        估算音频时长

        简单方法：根据 MP3 平均比特率估算
        """
        # MP3 平均比特率约 128kbps
        # 时长 ≈ 字节数 * 8 / 比特率
        return len(audio_data) * 8 / (128 * 1000)
