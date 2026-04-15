"""
场景分镜图生成模块

职责:
1. 根据分镜场景生成单帧分镜图
2. 尽量把角色描述融合进每个场景的画面提示词
3. 将生成结果写回 scene.scene_image_path / scene.reference_image
"""

from pathlib import Path
from typing import Dict, List

from .image_gen import ImageGenerator
from .models import Character, Scene, SceneImageResult, Storyboard
from .config import get_output_path


class SceneImageGenerator:
    """场景分镜图生成器"""

    def __init__(self):
        self.image_gen = ImageGenerator()
        self.output_dir = get_output_path("images")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def generate_for_storyboard(
        self,
        storyboard: Storyboard,
        output_name: str | None = None,
        regenerate: bool = False,
    ) -> List[SceneImageResult]:
        """为整个分镜脚本生成逐镜分镜图"""
        character_map: Dict[str, Character] = {
            character.id: character for character in storyboard.characters
        }
        results: List[SceneImageResult] = []

        for scene in storyboard.scenes:
            result = await self.generate_for_scene(
                scene=scene,
                character_map=character_map,
                output_name=output_name,
                regenerate=regenerate,
            )
            results.append(result)

            if result.status.startswith("success"):
                scene.scene_image_path = result.image_path
                # 让后续视频生成优先吃场景分镜图
                scene.reference_image = result.image_path

        return results

    async def generate_for_scene(
        self,
        scene: Scene,
        character_map: Dict[str, Character],
        output_name: str | None = None,
        regenerate: bool = False,
    ) -> SceneImageResult:
        """为单个场景生成分镜图"""
        image_path = self._build_scene_image_path(scene.scene_number, output_name)
        if image_path.exists() and not regenerate:
            return SceneImageResult(
                scene_number=scene.scene_number,
                image_path=str(image_path),
                status="success (cached)",
            )

        prompt = self._build_scene_prompt(scene, character_map)
        reference_images = self._get_reference_images(scene, character_map)
        reference_image = reference_images[0] if reference_images else None

        try:
            generated_path = await self.image_gen.generate_scene_image(
                image_id=self._build_scene_image_name(scene.scene_number, output_name),
                prompt=prompt,
                reference_image=reference_image,
                reference_images=reference_images,
                regenerate=regenerate,
            )
        except Exception as exc:
            return SceneImageResult(
                scene_number=scene.scene_number,
                image_path="",
                status="failed",
                error_message=str(exc),
            )

        return SceneImageResult(
            scene_number=scene.scene_number,
            image_path=str(generated_path),
            status="success",
        )

    def _build_scene_image_path(self, scene_number: int, output_name: str | None) -> Path:
        return self.output_dir / f"{self._build_scene_image_name(scene_number, output_name)}.png"

    def _build_scene_image_name(self, scene_number: int, output_name: str | None) -> str:
        prefix = output_name or "storyboard"
        return f"{prefix}_scene{scene_number}"

    def _build_scene_prompt(
        self,
        scene: Scene,
        character_map: Dict[str, Character],
    ) -> str:
        """将角色描述和场景提示词融合成场景分镜图提示词"""
        character_descriptions = []
        for character_id in scene.character_ids:
            character = character_map.get(character_id)
            if character:
                character_descriptions.append(
                    f"{character.name}: {character.description}"
                )

        prompt_parts = [
            scene.prompt,
            f"Scene description in Chinese context: {scene.description}",
        ]

        if character_descriptions:
            prompt_parts.append(
                "Keep these characters visually consistent: "
                + " | ".join(character_descriptions)
            )

        if scene.camera_movement:
            prompt_parts.append(f"Camera language: {scene.camera_movement}")
        if scene.mood:
            prompt_parts.append(f"Mood: {scene.mood}")

        prompt_parts.append(
            "single cinematic keyframe, one film still, no text, no watermark"
        )
        return ", ".join(prompt_parts)

    def _get_reference_images(
        self,
        scene: Scene,
        character_map: Dict[str, Character],
    ) -> list[str]:
        """
        收集场景参考图。

        优先取场景已有 reference_image，其次取出场角色的人设图。
        这样在支持多参考图的 provider 上，可以同时把角色图和分镜稿一起用于生成分镜图。
        """
        references: list[str] = []
        if scene.reference_image:
            references.append(scene.reference_image)

        for character_id in scene.character_ids:
            character = character_map.get(character_id)
            if character and character.image_path and character.image_path not in references:
                references.append(character.image_path)

        return references
