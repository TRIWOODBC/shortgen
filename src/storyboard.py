import json
from datetime import datetime
from pathlib import Path

from openai import OpenAI

from .models import Storyboard, Scene, TrendingItem, Character, Dialogue
from .config import Config, get_output_path


SYSTEM_PROMPT = """你是一个专业的短视频分镜师和提示词工程师。
你的任务是将用户的剧情描述转换为结构化的分镜脚本。

每个分镜场景需要包含：
1. 场景描述（中文）- 详细的视觉描述
2. 视频生成提示词（英文）- 给AI视频生成模型的详细提示词，需要包含：
   - 主体描述
   - 场景/环境
   - 动作/运动
   - 镜头角度和运动
   - 光线和氛围
   - 风格（ cinematic, realistic, anime 等）
3. 场景时长（秒）- 建议3-8秒
4. 镜头运动（可选）- 如：推进、拉远、平移等
5. 氛围（可选）- 如：紧张、温馨、神秘等

输出格式必须是有效的JSON，符合 Storyboard 结构。
"""

ENHANCED_SYSTEM_PROMPT = """你是一个专业的短视频分镜师和提示词工程师。
你的任务是将用户的剧情描述转换为结构化的分镜脚本。

请特别注意：
1. 提取剧情中的角色，生成详细的外观描述（用于AI生成角色参考图）
2. 为每个场景添加对话或旁白内容
3. 确保角色在不同场景中保持一致的外观描述
4. 为角色分配合适的音色类型

每个分镜场景需要包含：
1. 场景描述（中文）
2. 视频生成提示词（英文）
3. 场景时长
4. 镜头运动（可选）
5. 氛围（可选）
6. 出场角色ID列表
7. 对话内容（如有）
8. 旁白内容（如有）

角色定义需要包含：
1. 角色ID
2. 角色名称
3. 详细外观描述（用于生成参考图，英文）
4. 建议的TTS音色类型（male_warm / female_gentle / child / storyteller）

输出格式必须是有效的JSON。
"""

GENERATE_PLOT_PROMPT = """你是一个短视频编剧。根据以下热点新闻，创作一个适合短视频的剧情概要。

要求：
1. 剧情要有吸引力，能在15-30秒内讲完
2. 有明确的开始、发展和结尾
3. 适合视觉化呈现
4. 不要直接引用新闻原文，而是改编成一个故事

热点标题: {title}
热点描述: {description}

请输出一个200字左右的剧情描述，只输出剧情内容。"""


class StoryboardGenerator:
    """分镜脚本生成器 — 支持 DeepSeek / GLM / Kimi / OpenAI 等"""

    def __init__(self):
        config = Config()
        self.model = config.get_llm_model()
        self.client = OpenAI(
            api_key=config.LLM_API_KEY,
            base_url=config.get_llm_base_url(),
        )
        print(f"  🤖 LLM: {config.LLM_PROVIDER} ({self.model})")

    async def generate(self, plot: str, extract_characters: bool = False) -> Storyboard:
        """
        根据剧情生成分镜脚本

        Args:
            plot: 剧情描述
            extract_characters: 是否提取角色信息和对话

        Returns:
            Storyboard 对象
        """
        if extract_characters:
            prompt = f"""请将以下剧情转换为完整的分镜脚本，包括角色定义和对话内容：

剧情描述：
{plot}

请输出符合以下格式的JSON：
{{
    "title": "视频标题",
    "summary": "剧情摘要",
    "characters": [
        {{
            "id": "char_1",
            "name": "角色名称",
            "description": "Detailed appearance description in English for AI image generation, including facial features, hair, clothing, age, etc.",
            "voice_type": "male_warm / female_gentle / child / storyteller"
        }}
    ],
    "background_music": "背景音乐风格描述（如：soft piano, epic orchestral, ambient electronic）",
    "scenes": [
        {{
            "scene_number": 1,
            "description": "场景描述（中文）",
            "prompt": "Video generation prompt in English with detailed visual description, camera movement, lighting, and style",
            "duration": 5.0,
            "camera_movement": "镜头运动",
            "mood": "氛围",
            "character_ids": ["char_1"],
            "dialogues": [
                {{
                    "character_id": "char_1",
                    "text": "对话内容",
                    "emotion": "情感（如：开心、悲伤、紧张）"
                }}
            ],
            "narration": "旁白内容（可选，用于连接场景或补充说明）"
        }}
    ],
    "total_duration": 总时长
}}

要求：
- 提取所有主要角色，给出详细的英文外观描述
- 为对话场景生成自然流畅的对话
- 旁白用于连接场景或补充说明
- 每个场景时长3-8秒
- 总时长控制在15-45秒
- 提示词必须是英文，且详细具体
- 只输出JSON，不要输出其他内容"""

            system_prompt = ENHANCED_SYSTEM_PROMPT
        else:
            prompt = f"""请将以下剧情转换为分镜脚本：

剧情描述：
{plot}

请输出符合以下格式的JSON：
{{
    "title": "视频标题",
    "summary": "剧情摘要",
    "scenes": [
        {{
            "scene_number": 1,
            "description": "场景描述（中文）",
            "prompt": "Video generation prompt in English with detailed visual description, camera movement, lighting, and style",
            "duration": 5.0,
            "camera_movement": "镜头运动",
            "mood": "氛围"
        }}
    ],
    "total_duration": 总时长
}}

要求：
- 将剧情拆分为3-6个场景
- 每个场景时长3-8秒
- 总时长控制在15-45秒
- 提示词必须是英文，且详细具体
- 场景之间要有连贯性
- 只输出JSON，不要输出其他内容"""

            system_prompt = SYSTEM_PROMPT

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]
        )

        # 解析JSON响应
        content = response.choices[0].message.content

        # 提取JSON（可能被 ```json 包围）
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        data = json.loads(content.strip())

        # 构建Scene对象
        scenes = []
        for scene_data in data["scenes"]:
            # 处理对话
            dialogues = []
            if "dialogues" in scene_data:
                for d in scene_data["dialogues"]:
                    dialogues.append(Dialogue(
                        character_id=d["character_id"],
                        text=d["text"],
                        emotion=d.get("emotion")
                    ))

            scenes.append(Scene(
                scene_number=scene_data["scene_number"],
                description=scene_data["description"],
                prompt=scene_data["prompt"],
                duration=scene_data.get("duration", 5.0),
                camera_movement=scene_data.get("camera_movement"),
                mood=scene_data.get("mood"),
                character_ids=scene_data.get("character_ids", []),
                reference_image=scene_data.get("reference_image"),
                scene_image_path=scene_data.get("scene_image_path"),
                dialogues=dialogues,
                narration=scene_data.get("narration"),
                audio_configs=scene_data.get("audio_configs", [])
            ))

        # 构建Character对象
        characters = []
        if "characters" in data:
            for char_data in data["characters"]:
                characters.append(Character(
                    id=char_data["id"],
                    name=char_data["name"],
                    description=char_data["description"],
                    image_path=char_data.get("image_path"),
                    voice_id=char_data.get("voice_type")
                ))

        return Storyboard(
            title=data["title"],
            summary=data["summary"],
            scenes=scenes,
            total_duration=data.get("total_duration", sum(s.duration for s in scenes)),
            characters=characters,
            background_music=data.get("background_music")
        )

    async def generate_plot_from_trend(self, trend: TrendingItem) -> str:
        """根据热点生成剧情"""
        prompt = GENERATE_PLOT_PROMPT.format(
            title=trend.title,
            description=trend.description or "暂无描述"
        )

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        return response.choices[0].message.content.strip()

    def save(self, storyboard: Storyboard, output_name: str = None) -> str:
        """保存分镜脚本到文件"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = output_name or f"storyboard_{timestamp}"

        output_path = get_output_path("storyboards") / f"{filename}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        output_path.write_text(
            storyboard.model_dump_json(indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        # 同时保存可读的Markdown版本
        md_path = get_output_path("storyboards") / f"{filename}.md"
        md_content = self._to_markdown(storyboard)
        md_path.write_text(md_content, encoding="utf-8")

        return str(output_path)

    def _to_markdown(self, storyboard: Storyboard) -> str:
        """转换为Markdown格式"""
        lines = [
            f"# {storyboard.title}",
            "",
            f"> 生成时间: {storyboard.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## 剧情摘要",
            "",
            storyboard.summary,
            "",
            f"**总时长**: {storyboard.total_duration}秒",
            "",
            "## 分镜脚本",
            ""
        ]

        for scene in storyboard.scenes:
            lines.extend([
                f"### 场景 {scene.scene_number}",
                "",
                f"**描述**: {scene.description}",
                "",
                f"**提示词**: `{scene.prompt}`",
                "",
                f"**时长**: {scene.duration}秒",
                ""
            ])
            if scene.camera_movement:
                lines.append(f"**镜头运动**: {scene.camera_movement}")
            if scene.mood:
                lines.append(f"**氛围**: {scene.mood}")
            if scene.character_ids:
                lines.append(f"**出场角色**: {', '.join(scene.character_ids)}")
            if scene.scene_image_path:
                lines.append(f"**分镜图**: `{scene.scene_image_path}`")
            if scene.reference_image:
                lines.append(f"**视频参考图**: `{scene.reference_image}`")
            lines.append("")

        return "\n".join(lines)
