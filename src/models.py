from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class Scene(BaseModel):
    """分镜场景"""

    scene_number: int = Field(..., description="场景编号")
    description: str = Field(..., description="场景描述")
    prompt: str = Field(..., description="视频生成提示词（英文）")
    duration: float = Field(default=5.0, description="场景时长（秒）")
    camera_movement: Optional[str] = Field(None, description="镜头运动")
    mood: Optional[str] = Field(None, description="氛围/情绪")


class Storyboard(BaseModel):
    """分镜脚本"""

    title: str = Field(..., description="视频标题")
    summary: str = Field(..., description="剧情摘要")
    scenes: List[Scene] = Field(..., description="场景列表")
    total_duration: float = Field(..., description="总时长")
    created_at: datetime = Field(default_factory=datetime.now)


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
