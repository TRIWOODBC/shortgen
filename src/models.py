from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
from enum import Enum


class AudioType(str, Enum):
    """音频类型"""
    NARRATION = "narration"      # 旁白
    DIALOGUE = "dialogue"        # 对话
    BACKGROUND_MUSIC = "bgm"     # 背景音乐
    SOUND_EFFECT = "sfx"         # 音效


class Character(BaseModel):
    """角色定义"""
    id: str = Field(..., description="角色唯一标识")
    name: str = Field(..., description="角色名称")
    description: str = Field(..., description="角色外观描述（用于生成参考图）")
    image_path: Optional[str] = Field(None, description="角色参考图片路径")
    voice_id: Optional[str] = Field(None, description="TTS 音色 ID")


class Dialogue(BaseModel):
    """对话内容"""
    character_id: str = Field(..., description="说话角色 ID")
    text: str = Field(..., description="对话文本")
    emotion: Optional[str] = Field(None, description="情感标签")


class AudioConfig(BaseModel):
    """音频配置"""
    audio_type: AudioType = Field(..., description="音频类型")
    text: Optional[str] = Field(None, description="TTS 文本内容（旁白/对话）")
    character_id: Optional[str] = Field(None, description="说话角色 ID（对话时）")
    voice_id: Optional[str] = Field(None, description="指定音色 ID")
    music_path: Optional[str] = Field(None, description="本地音乐文件路径")
    music_prompt: Optional[str] = Field(None, description="AI 音乐生成提示词")
    volume: float = Field(default=1.0, ge=0.0, le=1.0, description="音量 0-1")
    fade_in: float = Field(default=0.0, ge=0.0, description="淡入时长（秒）")
    fade_out: float = Field(default=0.0, ge=0.0, description="淡出时长（秒）")
    start_offset: float = Field(default=0.0, ge=0.0, description="开始偏移（秒）")


class Scene(BaseModel):
    """分镜场景"""

    scene_number: int = Field(..., description="场景编号")
    description: str = Field(..., description="场景描述")
    prompt: str = Field(..., description="视频生成提示词（英文）")
    duration: float = Field(default=5.0, description="场景时长（秒）")
    camera_movement: Optional[str] = Field(None, description="镜头运动")
    mood: Optional[str] = Field(None, description="氛围/情绪")

    # 新增字段
    character_ids: List[str] = Field(default_factory=list, description="本场景出现的角色 ID 列表")
    reference_image: Optional[str] = Field(None, description="角色参考图片路径（图生视频时）")
    scene_image_path: Optional[str] = Field(None, description="场景分镜图路径")
    dialogues: List[Dialogue] = Field(default_factory=list, description="对话列表")
    narration: Optional[str] = Field(None, description="旁白文本")
    audio_configs: List[AudioConfig] = Field(default_factory=list, description="音频配置列表")


class Storyboard(BaseModel):
    """分镜脚本"""

    title: str = Field(..., description="视频标题")
    summary: str = Field(..., description="剧情摘要")
    scenes: List[Scene] = Field(..., description="场景列表")
    total_duration: float = Field(..., description="总时长")
    created_at: datetime = Field(default_factory=datetime.now)

    # 新增字段
    characters: List[Character] = Field(default_factory=list, description="角色列表")
    background_music: Optional[str] = Field(None, description="全局背景音乐路径或提示词")


class TrendingItem(BaseModel):
    """热点条目"""

    id: str = Field(..., description="唯一标识")
    title: str = Field(..., description="标题")
    description: Optional[str] = Field(None, description="描述")
    url: Optional[str] = Field(None, description="链接")
    category: str = Field(default="general", description="类别")
    hot_score: Optional[float] = Field(None, description="热度分数")


class VideoResult(BaseModel):
    """视频生成结果"""

    scene_number: int
    file_path: str
    status: str  # success, failed, pending
    error_message: Optional[str] = None


class AudioResult(BaseModel):
    """音频生成结果"""
    scene_number: int
    audio_type: AudioType
    file_path: str
    duration: float
    status: str  # success, failed, pending
    error_message: Optional[str] = None


class CharacterImageResult(BaseModel):
    """角色图片生成结果"""
    character_id: str
    character_name: str
    image_path: str
    status: str
    error_message: Optional[str] = None


class SceneImageResult(BaseModel):
    """场景分镜图生成结果"""
    scene_number: int
    image_path: str
    status: str
    error_message: Optional[str] = None


class ComposedVideoResult(BaseModel):
    """合成视频结果"""
    output_path: str
    duration: float
    scenes_count: int
    has_audio: bool
    status: str
    error_message: Optional[str] = None
