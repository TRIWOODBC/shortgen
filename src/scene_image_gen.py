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
        reference_strength: float = 0.3,
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
                reference_strength=reference_strength,
                regenerate=regenerate,
            )
            results.append(result)

            if result.status.startswith("success"):
                scene.scene_image_path = result.image_path
                # 仅在当前场景没有任何角色参考图时，才把生成出的分镜图回写成参考图。
                # 这样可以避免旧分镜图反过来压过上传的人设图。
                if not self._get_character_reference_images(scene, character_map):
                    scene.reference_image = result.image_path

        return results

    async def generate_for_scene(
        self,
        scene: Scene,
        character_map: Dict[str, Character],
        output_name: str | None = None,
        reference_strength: float = 0.3,
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
                reference_strength=reference_strength,
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
        identity_rules = []
        reference_bindings = []
        for character_id in scene.character_ids:
            character = character_map.get(character_id)
            if character:
                character_descriptions.append(
                    f"{character.name}: {character.description}"
                )
                identity_rules.append(
                    self._build_character_identity_rule(character)
                )
                reference_bindings.append(
                    self._build_reference_binding_rule(
                        len(reference_bindings) + 1,
                        character,
                    )
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
            prompt_parts.append(
                "Reference image binding: "
                + " | ".join(reference_bindings)
            )
            prompt_parts.append(
                "Identity lock: "
                + " | ".join(identity_rules)
            )
            prompt_parts.append(
                "Use the uploaded reference character image as the source of truth for face shape, hairstyle, glasses, outfit details, and age. "
                "Do not redesign the character into a different person."
            )
            prompt_parts.append(
                "Preserve the same person across scenes with matching facial structure, same black rectangular glasses, same black sports outfit, and consistent East Asian male appearance."
            )
            prompt_parts.append(
                "Prioritize character identity consistency over stylistic variation. Keep the same person, only change pose, camera angle, framing, lighting, and action."
            )
            prompt_parts.append(
                "If multiple characters appear in the same frame, keep each reference image matched to its own character identity and do not merge or swap them."
            )

        if scene.character_directions:
            prompt_parts.append(
                "Character assignment for this shot: "
                + scene.character_directions
            )
            prompt_parts.append(
                "Follow the character assignment strictly when composing the shot."
            )

        if scene.camera_movement:
            prompt_parts.append(f"Camera language: {scene.camera_movement}")
        if scene.mood:
            prompt_parts.append(f"Mood: {scene.mood}")

        prompt_parts.append(
            "single cinematic keyframe, one film still, no text, no watermark, no character redesign, no identity drift"
        )
        return ", ".join(prompt_parts)

    def _build_character_identity_rule(self, character: Character) -> str:
        """为角色生成更强的身份一致性约束描述。"""
        base = f"{character.name} must remain the exact same person as the uploaded reference image"

        description = (character.description or "").strip()
        if not description:
            return base

        normalized = description.replace("，", ",")
        traits = [part.strip() for part in normalized.split(",") if part.strip()]
        selected_traits = ", ".join(traits[:4])
        if selected_traits:
            return f"{base}, keeping these defining traits unchanged: {selected_traits}"
        return base

    def _build_reference_binding_rule(self, slot: int, character: Character) -> str:
        """为多参考图场景构建更明确的顺序绑定说明。"""
        return (
            f"Reference image {slot} corresponds to character {character.id} ({character.name}). "
            f"When this character appears, use that exact reference identity."
        )

    def _get_reference_images(
        self,
        scene: Scene,
        character_map: Dict[str, Character],
    ) -> list[str]:
        """
        收集场景参考图。

        优先取出场角色的人设图，其次才使用场景已有 reference_image。
        这样在支持多参考图的 provider 上，会先尽量锁定角色长相，再参考已有分镜图的构图或风格。
        """
        references: list[str] = []
        references.extend(self._get_character_reference_images(scene, character_map))

        if scene.reference_image and scene.reference_image not in references:
            references.append(scene.reference_image)

        return references

    def _get_character_reference_images(
        self,
        scene: Scene,
        character_map: Dict[str, Character],
    ) -> list[str]:
        """收集当前场景角色对应的人设参考图。"""
        references: list[str] = []

        name_to_image: dict[str, str] = {}
        for character in character_map.values():
            if character.name and character.image_path:
                name_to_image.setdefault(character.name.strip().lower(), character.image_path)

        for character_id in scene.character_ids:
            character = character_map.get(character_id)
            if not character:
                continue

            candidate = character.image_path
            if not candidate and character.name:
                candidate = name_to_image.get(character.name.strip().lower())

            if candidate and candidate not in references:
                references.append(candidate)

        return references
