import json
from datetime import datetime
from pathlib import Path

from openai import OpenAI

from .models import Storyboard, Scene, TrendingItem
from .config import Config


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

    async def generate(self, plot: str) -> Storyboard:
        """根据剧情生成分镜脚本"""
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

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=4096,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
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

        # 构建Storyboard对象
        scenes = [Scene(**scene) for scene in data["scenes"]]

        return Storyboard(
            title=data["title"],
            summary=data["summary"],
            scenes=scenes,
            total_duration=data.get("total_duration", sum(s.duration for s in scenes))
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

        output_path = Path("output/storyboards") / f"{filename}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        output_path.write_text(
            storyboard.model_dump_json(indent=2, ensure_ascii=False),
            encoding="utf-8"
        )

        # 同时保存可读的Markdown版本
        md_path = Path("output/storyboards") / f"{filename}.md"
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
            lines.append("")

        return "\n".join(lines)
