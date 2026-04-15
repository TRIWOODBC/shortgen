"""
视频合成模块 - 合并视频片段、添加音频

使用 FFmpeg 进行音视频合成
"""

import asyncio
import json
import shutil
from pathlib import Path
from typing import List, Optional, Dict
from datetime import datetime

from .models import (
    Storyboard, Scene, VideoResult, AudioResult,
    AudioType, ComposedVideoResult
)
from .config import Config, get_output_path


class VideoComposer:
    """
    视频合成器

    职责:
    1. 合并多个视频片段
    2. 添加音频轨道（旁白、对话、背景音乐）
    3. 添加转场效果（可选）
    4. 输出最终视频
    """

    def __init__(self):
        config = Config()
        self.ffmpeg_path = config.FFMPEG_PATH
        self.ffprobe_path = self.ffmpeg_path.replace("ffmpeg", "ffprobe")
        self.video_codec = config.VIDEO_CODEC
        self.audio_codec = config.AUDIO_CODEC
        self.output_dir = get_output_path("final")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 检查 FFmpeg 是否可用
        if not shutil.which(self.ffmpeg_path):
            print(f"  ⚠️ FFmpeg 未找到，请安装: brew install ffmpeg")

    async def compose(
        self,
        video_results: List[VideoResult],
        audio_results: List[AudioResult],
        storyboard: Storyboard,
        output_name: Optional[str] = None
    ) -> ComposedVideoResult:
        """
        合成最终视频

        Args:
            video_results: 视频片段生成结果
            audio_results: 音频生成结果
            storyboard: 分镜脚本
            output_name: 输出文件名

        Returns:
            合成结果
        """
        # 1. 过滤成功的视频
        success_videos = [v for v in video_results if v.status == "success"]
        if not success_videos:
            return ComposedVideoResult(
                output_path="",
                duration=0,
                scenes_count=0,
                has_audio=False,
                status="failed",
                error_message="没有成功的视频片段"
            )

        # 按场景编号排序
        success_videos.sort(key=lambda v: v.scene_number)

        print(f"  🎞️ 开始合成 {len(success_videos)} 个视频片段...")

        # 2. 准备视频文件列表
        video_files = [v.file_path for v in success_videos]

        # 3. 合并视频片段
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        merged_video = self.output_dir / f"merged_{timestamp}.mp4"

        try:
            await self._concat_videos(video_files, merged_video)
        except Exception as e:
            return ComposedVideoResult(
                output_path="",
                duration=0,
                scenes_count=len(success_videos),
                has_audio=False,
                status="failed",
                error_message=f"视频合并失败: {e}"
            )

        # 4. 处理音频
        final_output = merged_video
        has_audio = False

        if audio_results:
            print(f"  🔊 处理 {len(audio_results)} 个音频轨道...")

            # 按场景组织音频
            audio_by_scene = self._organize_audio(audio_results)

            # 混合音频
            try:
                mixed_audio = await self._mix_audio_tracks(
                    audio_by_scene,
                    storyboard.scenes,
                    storyboard.total_duration
                )

                if mixed_audio:
                    # 添加音频到视频
                    final_name = output_name or "final"
                    final_output = self.output_dir / f"{final_name}_{timestamp}.mp4"
                    await self._add_audio_to_video(merged_video, mixed_audio, final_output)
                    has_audio = True

                    # 删除临时文件
                    merged_video.unlink()
                    mixed_audio.unlink()

            except Exception as e:
                print(f"  ⚠️ 音频处理失败: {e}，使用无音频版本")
                final_output = merged_video

        # 5. 获取视频时长
        duration = await self._get_video_duration(final_output)

        return ComposedVideoResult(
            output_path=str(final_output),
            duration=duration,
            scenes_count=len(success_videos),
            has_audio=has_audio,
            status="success"
        )

    async def _concat_videos(
        self,
        video_files: List[str],
        output_path: Path
    ):
        """合并视频片段"""
        # 创建文件列表
        list_file = self.output_dir / "concat_list.txt"
        with open(list_file, "w") as f:
            for video in video_files:
                # FFmpeg concat 需要 file 'path' 格式
                f.write(f"file '{video}'\n")

        # FFmpeg concat 命令
        cmd = [
            self.ffmpeg_path,
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-c", "copy",
            "-y",
            str(output_path)
        ]

        await self._run_ffmpeg(cmd)

        # 清理临时文件
        if list_file.exists():
            list_file.unlink()

    async def _mix_audio_tracks(
        self,
        audio_by_scene: Dict,
        scenes: List[Scene],
        total_duration: float
    ) -> Optional[Path]:
        """
        混合所有音频轨道

        包括: 旁白、对话、背景音乐
        """
        voice_tracks = []
        bgm_track = None

        # 1. 收集旁白和对话
        for scene in scenes:
            scene_audios = audio_by_scene.get(scene.scene_number, [])
            for audio in scene_audios:
                if audio.status == "success" and audio.audio_type in (
                    AudioType.NARRATION,
                    AudioType.DIALOGUE
                ):
                    voice_tracks.append(audio.file_path)

        # 2. 获取背景音乐
        bgm_audios = audio_by_scene.get("bgm", [])
        if bgm_audios:
            for audio in bgm_audios:
                if audio.status == "success":
                    bgm_track = audio.file_path
                    break

        # 3. 合并语音轨道
        voice_track_path = None
        if voice_tracks:
            if len(voice_tracks) == 1:
                voice_track_path = Path(voice_tracks[0])
            else:
                voice_track_path = await self._concat_audio(voice_tracks)

        # 4. 准备背景音乐
        bgm_track_path = None
        if bgm_track:
            bgm_track_path = await self._prepare_bgm(
                bgm_track,
                total_duration,
                volume=0.3
            )

        # 5. 混合语音和背景音乐
        if voice_track_path and bgm_track_path:
            return await self._mix_two_tracks(
                voice_track_path,
                bgm_track_path,
                voice_volume=1.0,
                bgm_volume=0.3
            )
        elif voice_track_path:
            return voice_track_path
        elif bgm_track_path:
            return bgm_track_path

        return None

    async def _concat_audio(self, audio_files: List[str]) -> Path:
        """拼接多个音频文件"""
        output = self.output_dir / f"voice_concat_{datetime.now().strftime('%H%M%S')}.mp3"

        # 创建文件列表
        list_file = self.output_dir / "audio_concat_list.txt"
        with open(list_file, "w") as f:
            for audio in audio_files:
                f.write(f"file '{audio}'\n")

        cmd = [
            self.ffmpeg_path,
            "-f", "concat",
            "-safe", "0",
            "-i", str(list_file),
            "-y",
            str(output)
        ]

        await self._run_ffmpeg(cmd)
        list_file.unlink()

        return output

    async def _prepare_bgm(
        self,
        bgm_path: str,
        target_duration: float,
        volume: float = 0.3,
        fade_in: float = 2.0,
        fade_out: float = 2.0
    ) -> Path:
        """
        准备背景音乐

        调整音量、添加淡入淡出、裁剪/循环到目标时长
        """
        output = self.output_dir / f"bgm_prepared_{datetime.now().strftime('%H%M%S')}.mp3"

        # 获取原音频时长
        bgm_duration = await self._get_audio_duration(bgm_path)

        # 如果原音频短于目标时长，需要循环
        if bgm_duration < target_duration:
            # 循环播放
            loop_count = int(target_duration / bgm_duration) + 1

            filter_str = (
                f"volume={volume},"
                f"afade=t=in:st=0:d={fade_in},"
                f"afade=t=out:st={target_duration-fade_out}:d={fade_out}"
            )

            cmd = [
                self.ffmpeg_path,
                "-stream_loop", str(loop_count),
                "-i", bgm_path,
                "-t", str(target_duration),
                "-af", filter_str,
                "-y",
                str(output)
            ]
        else:
            # 直接裁剪
            filter_str = (
                f"volume={volume},"
                f"afade=t=in:st=0:d={fade_in},"
                f"afade=t=out:st={target_duration-fade_out}:d={fade_out}"
            )

            cmd = [
                self.ffmpeg_path,
                "-i", bgm_path,
                "-t", str(target_duration),
                "-af", filter_str,
                "-y",
                str(output)
            ]

        await self._run_ffmpeg(cmd)
        return output

    async def _mix_two_tracks(
        self,
        voice_path: Path,
        bgm_path: Path,
        voice_volume: float = 1.0,
        bgm_volume: float = 0.3
    ) -> Path:
        """混合两个音频轨道"""
        output = self.output_dir / f"mixed_{datetime.now().strftime('%H%M%S')}.mp3"

        filter_str = (
            f"[0:a]volume={voice_volume}[voice];"
            f"[1:a]volume={bgm_volume}[bgm];"
            f"[voice][bgm]amix=inputs=2:duration=first:dropout_transition=3"
        )

        cmd = [
            self.ffmpeg_path,
            "-i", str(voice_path),
            "-i", str(bgm_path),
            "-filter_complex", filter_str,
            "-y",
            str(output)
        ]

        await self._run_ffmpeg(cmd)
        return output

    async def _add_audio_to_video(
        self,
        video_path: Path,
        audio_path: Path,
        output_path: Path
    ):
        """将音频添加到视频"""
        cmd = [
            self.ffmpeg_path,
            "-i", str(video_path),
            "-i", str(audio_path),
            "-c:v", self.video_codec,
            "-c:a", self.audio_codec,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-shortest",
            "-y",
            str(output_path)
        ]

        await self._run_ffmpeg(cmd)

    async def _get_video_duration(self, video_path: Path) -> float:
        """获取视频时长"""
        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(video_path)
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()

            data = json.loads(stdout)
            return float(data.get("format", {}).get("duration", 0))
        except Exception:
            return 0.0

    async def _get_audio_duration(self, audio_path: str) -> float:
        """获取音频时长"""
        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            audio_path
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await process.communicate()

            data = json.loads(stdout)
            return float(data.get("format", {}).get("duration", 0))
        except Exception:
            return 0.0

    def _organize_audio(
        self,
        audio_results: List[AudioResult]
    ) -> Dict:
        """按场景组织音频"""
        organized: Dict = {}

        for audio in audio_results:
            if audio.audio_type == AudioType.BACKGROUND_MUSIC:
                key = "bgm"
            else:
                key = audio.scene_number

            if key not in organized:
                organized[key] = []
            organized[key].append(audio)

        return organized

    async def _run_ffmpeg(self, cmd: List[str]):
        """执行 FFmpeg 命令"""
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode() if stderr else "Unknown FFmpeg error"
            raise RuntimeError(f"FFmpeg 错误: {error_msg}")
