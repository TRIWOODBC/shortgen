"""
角色管理模块 - 维护角色库和图片缓存

职责:
1. 管理角色定义
2. 预生成/缓存角色参考图
3. 为图生视频提供角色图片
"""

import asyncio
from typing import List, Optional, Dict

from .models import Character, CharacterImageResult
from .image_gen import ImageGenerator
from .config import Config, resolve_output_dir


# 预设音色映射
VOICE_PRESETS = {
    "male_warm": "zh_male_chunhou_zhiboshuangkuai_moon_bigtts",
    "female_gentle": "zh_female_shuangkuaisisi_moon_bigtts",
    "child": "zh_child_happy_moon_bigtts",
    "storyteller": "zh_female_wanwanroumei_moon_bigtts",
    "narrator_male": "zh_male_chunhou_zhiboshuangkuai_moon_bigtts",
    "narrator_female": "zh_female_wanwanroumei_moon_bigtts",
}


class CharacterManager:
    """
    角色管理器

    职责:
    1. 管理角色定义
    2. 预生成/缓存角色参考图
    3. 为图生视频提供角色图片
    """

    def __init__(self):
        self.image_gen = ImageGenerator()
        self.characters_dir = resolve_output_dir(Config().CHARACTER_IMAGE_DIR)
        self.characters_dir.mkdir(parents=True, exist_ok=True)
        self._character_cache: Dict[str, Character] = {}

    async def prepare_characters(
        self,
        characters: List[Character],
        regenerate: bool = False
    ) -> List[CharacterImageResult]:
        """
        预生成所有角色的参考图片

        应在视频生成前调用，确保所有角色图片就绪

        Args:
            characters: 角色列表
            regenerate: 是否重新生成已有图片

        Returns:
            生成结果列表
        """
        results = []

        for character in characters:
            print(f"  🎨 生成角色图片: {character.name}")
            result = await self.image_gen.generate_character_image(
                character,
                regenerate=regenerate
            )

            if result.status.startswith("success"):
                # 更新角色的图片路径
                character.image_path = result.image_path
                self._character_cache[character.id] = character
                print(f"     ✅ {result.image_path}")
            else:
                print(f"     ❌ {result.error_message}")

            results.append(result)
            await asyncio.sleep(1)  # 避免 API 限流

        return results

    def get_character_image(self, character_id: str) -> Optional[str]:
        """
        获取角色参考图路径

        Args:
            character_id: 角色 ID

        Returns:
            图片路径，不存在则返回 None
        """
        # 先从缓存获取
        character = self._character_cache.get(character_id)
        if character and character.image_path:
            return character.image_path

        # 尝试从文件系统加载
        image_path = self.characters_dir / f"{character_id}.png"
        if image_path.exists():
            return str(image_path)

        return None

    def get_character_voice(self, character_id: str) -> Optional[str]:
        """
        获取角色对应的 TTS 音色

        Args:
            character_id: 角色 ID

        Returns:
            音色 ID，不存在则返回默认音色
        """
        character = self._character_cache.get(character_id)
        if character and character.voice_id:
            return character.voice_id

        # 返回默认音色
        return Config().VOLC_TTS_DEFAULT_VOICE

    def get_character(self, character_id: str) -> Optional[Character]:
        """获取角色对象"""
        return self._character_cache.get(character_id)

    def load_from_storyboard(self, storyboard: 'Storyboard'):
        """
        从分镜脚本加载角色

        Args:
            storyboard: 分镜脚本对象
        """
        for character in storyboard.characters:
            self._character_cache[character.id] = character

    def get_scene_reference_image(
        self,
        scene: 'Scene',
        default_to_first: bool = True
    ) -> Optional[str]:
        """
        获取场景的参考图片（用于图生视频）

        优先使用场景指定的参考图，否则使用场景中第一个角色的图片

        Args:
            scene: 场景对象
            default_to_first: 是否默认使用第一个角色的图片

        Returns:
            参考图片路径
        """
        # 场景指定的参考图优先
        if scene.reference_image:
            return scene.reference_image

        # 使用场景中第一个角色的图片
        if default_to_first and scene.character_ids:
            return self.get_character_image(scene.character_ids[0])

        return None

    def clear_cache(self):
        """清空角色缓存"""
        self._character_cache.clear()

    def list_characters(self) -> List[Character]:
        """列出所有已加载的角色"""
        return list(self._character_cache.values())

    @staticmethod
    def resolve_voice_id(voice_type: Optional[str]) -> str:
        """
        解析音色 ID

        支持预设名称和直接 ID

        Args:
            voice_type: 音色类型或 ID

        Returns:
            实际的音色 ID
        """
        if not voice_type:
            return Config().VOLC_TTS_DEFAULT_VOICE

        # 如果是预设名称，转换为实际 ID
        if voice_type in VOICE_PRESETS:
            return VOICE_PRESETS[voice_type]

        # 否则直接返回
        return voice_type
