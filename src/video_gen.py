import asyncio
import base64
import io
import time
from pathlib import Path
from typing import List, Optional
from datetime import datetime

import httpx
from PIL import Image

from .models import Storyboard, Scene, VideoResult
from .config import Config, get_output_path


class VideoGenerator:
    """视频生成器 - 支持多个平台"""

    def __init__(self, provider: str = "dreamina"):
        """
        初始化视频生成器

        Args:
            provider: 指定使用的平台
                     "dreamina" - 强制使用即梦（火山引擎官方 API）
                     "auto" - 自动选择（按优先级：即梦 > Runway > Pika）
                     "runway" - 强制使用 Runway
                     "pika" - 强制使用 Pika
        """
        config = Config()
        self.provider = config.VIDEO_PROVIDER if provider in ("auto", "", None) else provider
        self.runway_key = config.RUNWAY_API_KEY
        self.pika_key = config.PIKA_API_KEY
        self.volc_ak = config.VOLC_ACCESS_KEY
        self.volc_sk = config.VOLC_SECRET_KEY
        self.proxy = config.HTTP_PROXY or None
        self.output_dir = get_output_path("videos")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _get_provider(self) -> str:
        """确定使用哪个平台"""
        if self.provider not in ("auto", ""):
            return self.provider

        # 自动选择优先级：即梦 > Runway > Pika
        if self.volc_ak and self.volc_sk:
            return "dreamina"
        elif self.runway_key:
            return "runway"
        elif self.pika_key:
            return "pika"
        else:
            raise ValueError("未配置任何视频生成 API")

    async def generate_from_storyboard(
        self,
        storyboard: Storyboard,
        output_name: str = None
    ) -> List[VideoResult]:
        """根据分镜脚本生成视频"""
        results = []
        provider = self._get_provider()

        print(f"  📡 使用平台: {provider}")

        for scene in storyboard.scenes:
            print(f"  🎬 正在生成场景 {scene.scene_number}/{len(storyboard.scenes)}...")

            try:
                if provider == "dreamina":
                    dreamina = DreaminaGenerator()
                    reference_image = self._get_reference_image(scene, storyboard)
                    if reference_image:
                        print(f"    🖼️ 使用参考图生成场景 {scene.scene_number}")
                        video_path = await dreamina.generate_video_from_image(
                            image_path=reference_image,
                            prompt=scene.prompt,
                            output_name=self._build_scene_output_prefix(scene, output_name),
                            duration=max(3, int(round(scene.duration)))
                        )
                    else:
                        video_path = await dreamina.generate_video(scene, output_name)
                elif provider == "runway":
                    video_path = await self._generate_with_runway(scene, output_name)
                elif provider == "pika":
                    video_path = await self._generate_with_pika(scene, output_name)
                else:
                    raise ValueError(f"未知的视频生成平台: {provider}")

                results.append(VideoResult(
                    scene_number=scene.scene_number,
                    file_path=video_path,
                    status="success"
                ))

            except Exception as e:
                print(f"    ❌ 场景 {scene.scene_number} 生成失败: {e}")
                results.append(VideoResult(
                    scene_number=scene.scene_number,
                    file_path="",
                    status="failed",
                    error_message=str(e)
                ))

            # 避免 API 限流
            await asyncio.sleep(2)

        return results

    def _build_scene_output_prefix(self, scene: Scene, output_name: Optional[str]) -> str:
        """构建场景输出前缀"""
        prefix = output_name or "scene"
        return f"{prefix}_scene{scene.scene_number}"

    def _get_reference_image(self, scene: Scene, storyboard: Storyboard) -> Optional[str]:
        """优先使用场景参考图/分镜图，否则回退到角色参考图"""
        if scene.reference_image and Path(scene.reference_image).exists():
            return scene.reference_image

        if scene.scene_image_path and Path(scene.scene_image_path).exists():
            return scene.scene_image_path

        if not scene.character_ids:
            return None

        character_map = {
            character.id: character.image_path
            for character in storyboard.characters
            if character.image_path
        }

        for character_id in scene.character_ids:
            image_path = character_map.get(character_id)
            if image_path and Path(image_path).exists():
                return image_path

        return None

    async def _generate_with_runway(self, scene: Scene, output_prefix: str = None) -> str:
        """使用 Runway Gen-3 生成视频"""
        base_url = "https://api.runwayml.com/v1"

        async with httpx.AsyncClient(proxies=self.proxy, timeout=120) as client:
            headers = {
                "Authorization": f"Bearer {self.runway_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "prompt": scene.prompt,
                "duration": min(scene.duration, 10),
                "ratio": "9:16"
            }

            response = await client.post(
                f"{base_url}/generation",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()

            task_id = data.get("id")
            if not task_id:
                raise ValueError(f"未能获取任务ID: {data}")

            print(f"    ⏳ 任务已提交: {task_id}，等待生成...")

            video_url = await self._poll_runway_task(client, headers, base_url, task_id)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            prefix = output_prefix or f"scene_{scene.scene_number}"
            output_path = self.output_dir / f"{prefix}_{timestamp}_scene{scene.scene_number}.mp4"

            await self._download_file(video_url, output_path)

            return str(output_path)

    async def _poll_runway_task(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        base_url: str,
        task_id: str,
        max_retries: int = 60
    ) -> str:
        """轮询 Runway 任务状态"""
        for i in range(max_retries):
            response = await client.get(
                f"{base_url}/generation/{task_id}",
                headers=headers
            )
            response.raise_for_status()
            data = response.json()

            status = data.get("status")

            if status == "completed":
                return data.get("url")
            elif status in ["failed", "error"]:
                raise ValueError(f"生成失败: {data.get('error', 'Unknown error')}")

            await asyncio.sleep(5)

        raise TimeoutError("等待视频生成超时")

    async def _generate_with_pika(self, scene: Scene, output_prefix: str = None) -> str:
        """使用 Pika Labs 生成视频"""
        base_url = "https://api.pika.art/v1"

        async with httpx.AsyncClient(proxies=self.proxy, timeout=120) as client:
            headers = {
                "Authorization": f"Bearer {self.pika_key}",
                "Content-Type": "application/json"
            }

            payload = {
                "prompt": scene.prompt,
                "duration": min(scene.duration, 3),
                "aspect_ratio": "9:16"
            }

            response = await client.post(
                f"{base_url}/generations",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()

            generation_id = data.get("id")
            print(f"    ⏳ Pika 任务已提交: {generation_id}")

            video_url = await self._poll_pika_task(client, headers, base_url, generation_id)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            prefix = output_prefix or f"scene_{scene.scene_number}"
            output_path = self.output_dir / f"{prefix}_{timestamp}_scene{scene.scene_number}.mp4"

            await self._download_file(video_url, output_path)

            return str(output_path)

    async def _poll_pika_task(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        base_url: str,
        generation_id: str,
        max_retries: int = 60
    ) -> str:
        """轮询 Pika 任务状态"""
        for i in range(max_retries):
            response = await client.get(
                f"{base_url}/generations/{generation_id}",
                headers=headers
            )
            response.raise_for_status()
            data = response.json()

            status = data.get("status")

            if status == "completed":
                return data.get("video_url")
            elif status == "failed":
                raise ValueError(f"Pika 生成失败: {data}")

            await asyncio.sleep(5)

        raise TimeoutError("等待 Pika 视频生成超时")

    async def _download_file(self, url: str, output_path: Path):
        """下载文件"""
        async with httpx.AsyncClient(proxies=self.proxy, timeout=120) as client:
            response = await client.get(url)
            response.raise_for_status()
            output_path.write_bytes(response.content)

        print(f"    ✅ 已保存: {output_path}")


class DreaminaGenerator:
    """
    即梦 (Dreamina) 视频生成器 — 基于火山引擎官方 API

    使用火山引擎 VisualService SDK 调用即梦 AI 视频生成能力。

    前置条件：
    1. 注册火山引擎账号: https://console.volcengine.com/
    2. 开通「即梦AI」或「智能视觉」服务
    3. 获取 AccessKey (AK) 和 SecretKey (SK)
    4. 将 AK/SK 配置到 .env 文件中

    支持的 req_key:
    - jimeng_t2v_v30: 文生视频 3.0（标准版）
    - jimeng_ti2v_v30_pro: 图生视频 3.0 Pro
    - jimeng_t2v_v30_pro: 文生视频 3.0 Pro
    """

    # 视频生成宽高对照表 (竖屏 9:16)
    ASPECT_RATIOS = {
        "9:16": (720, 1280),
        "16:9": (1280, 720),
        "1:1": (1024, 1024),
        "4:3": (1024, 768),
        "3:4": (768, 1024),
    }

    def __init__(self):
        config = Config()
        self.ak = config.VOLC_ACCESS_KEY
        self.sk = config.VOLC_SECRET_KEY
        self.model = config.JIMENG_MODEL
        self.proxy = config.HTTP_PROXY or None
        self.output_dir = get_output_path("videos")
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if not self.ak or not self.sk:
            raise ValueError(
                "缺少火山引擎认证信息，请配置 VOLC_ACCESS_KEY 和 VOLC_SECRET_KEY\n"
                "获取方式: https://console.volcengine.com/ → 密钥管理"
            )

        # 初始化火山引擎 VisualService
        self._init_visual_service()

    def _init_visual_service(self):
        """初始化火山引擎 Visual Service SDK"""
        try:
            from volcengine.visual.VisualService import VisualService
        except ImportError:
            raise ImportError(
                "请先安装火山引擎 SDK: pip install volcengine\n"
                "详情参考: https://github.com/volcengine/volc-sdk-python"
            )

        self.visual_service = VisualService()
        self.visual_service.set_ak(self.ak)
        self.visual_service.set_sk(self.sk)

    async def generate_video(
        self,
        scene: Scene,
        output_prefix: str = None,
        aspect_ratio: str = "9:16"
    ) -> str:
        """
        文生视频 (Text-to-Video)

        Args:
            scene: 分镜场景
            output_prefix: 输出文件名前缀
            aspect_ratio: 画面比例，默认 9:16（竖屏）

        Returns:
            视频文件路径
        """
        # 根据时长选择帧数: 121帧=5秒, 241帧=10秒
        frames = 241 if scene.duration > 5 else 121

        # 构造请求参数（按官方文档）
        form = {
            "req_key": self.model,
            "prompt": scene.prompt,
            "frames": frames,
            "aspect_ratio": aspect_ratio,
            "seed": -1,  # 随机种子
        }

        # 1. 提交任务
        task_id = await self._submit_task(form)
        print(f"    ⏳ 即梦任务已提交: {task_id}，等待生成...")

        # 2. 轮询等待结果
        video_url = await self._poll_task(task_id, req_key=self.model)

        # 3. 下载视频
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = output_prefix or f"scene_{scene.scene_number}"
        output_path = self.output_dir / f"{prefix}_{timestamp}_scene{scene.scene_number}.mp4"

        await self._download_file(video_url, output_path)

        return str(output_path)

    async def generate_video_from_image(
        self,
        image_path: str,
        prompt: str,
        output_name: str = None,
        duration: int = 5
    ) -> str:
        """
        图生视频 (Image-to-Video)

        Args:
            image_path: 首帧图片路径
            prompt: 运动/动作描述
            output_name: 输出文件名
            duration: 视频时长（秒）

        Returns:
            视频文件路径
        """
        # 读取图片并转换为 base64
        image = Image.open(image_path)
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        img_base64 = base64.b64encode(buffer.getvalue()).decode()

        # 构造请求参数
        form = {
            "req_key": "jimeng_ti2v_v30_pro",  # 图生视频使用 Pro 版
            "prompt": prompt,
            "image_url": f"data:image/png;base64,{img_base64}",
            "frames": 241 if duration > 5 else 121,
            "aspect_ratio": "9:16",
            "seed": -1,
        }

        # 1. 提交任务
        task_id = await self._submit_task(form)
        print(f"    ⏳ 即梦图生视频任务: {task_id}")

        # 2. 轮询等待结果
        video_url = await self._poll_task(task_id, req_key=form["req_key"])

        # 3. 下载视频
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = self.output_dir / f"{output_name or 'img2video'}_{timestamp}.mp4"

        await self._download_file(video_url, output_path)

        return str(output_path)

    async def _submit_task(self, form: dict) -> str:
        """
        提交视频生成任务

        使用 CVSync2AsyncSubmitTask 接口异步提交任务。
        """
        # SDK 使用同步调用，放到线程池中执行以兼容 async
        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None, self.visual_service.cv_sync2async_submit_task, form
        )

        # 检查响应（火山引擎成功码为 10000）
        code = resp.get("code", -1)
        if code not in (0, 10000):
            message = resp.get("message", "未知错误")
            raise ValueError(f"即梦任务提交失败 (code={code}): {message}")

        task_id = resp.get("data", {}).get("task_id")
        if not task_id:
            raise ValueError(f"未能获取任务ID，响应: {resp}")

        return task_id

    async def _poll_task(
        self,
        task_id: str,
        req_key: Optional[str] = None,
        max_wait_seconds: int = 600,
        poll_interval: int = 5
    ) -> str:
        """
        轮询任务状态直到完成

        Args:
            task_id: 任务 ID
            max_wait_seconds: 最大等待时间（秒），默认 10 分钟
            poll_interval: 轮询间隔（秒），默认 5 秒

        Returns:
            视频 URL

        Status 说明：
            - in_queue: 排队中
            - generating: 生成中
            - done: 完成（需检查 code 判断成功/失败）
            - not_found: 任务不存在
            - expired: 任务过期（超过 12 小时）
        """
        form = {
            "req_key": req_key or self.model,
            "task_id": task_id,
        }

        start_time = time.time()
        poll_count = 0

        while (time.time() - start_time) < max_wait_seconds:
            # SDK 同步调用放到线程池
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None, self.visual_service.cv_sync2async_get_result, form
            )

            code = resp.get("code", -1)
            data = resp.get("data", {})
            status = data.get("status", "")
            message = resp.get("message", "")

            if status == "done":
                if code in (0, 10000):
                    # 生成成功，提取视频 URL
                    video_url = (
                        data.get("video_url") or
                        data.get("resp_data", {}).get("video_url") or
                        # 有些版本结果在 video_urls 列表中
                        (data.get("video_urls", [None]) or [None])[0]
                    )
                    if video_url:
                        return video_url
                    else:
                        raise ValueError(f"任务完成但未找到视频 URL，响应: {resp}")
                else:
                    raise ValueError(f"即梦生成失败 (code={code}): {message}")

            elif status in ("not_found", "expired"):
                raise ValueError(f"任务异常 (status={status}): {message}")

            elif status in ("in_queue", "generating", ""):
                poll_count += 1
                elapsed = int(time.time() - start_time)

                # 每 30 秒打印一次进度
                if poll_count % 6 == 0:
                    print(f"    ⏳ 仍在生成中... (已等待 {elapsed} 秒)")

                await asyncio.sleep(poll_interval)

            else:
                # 未知状态，继续等待
                poll_count += 1
                await asyncio.sleep(poll_interval)

        raise TimeoutError(f"等待即梦视频生成超时（已等待 {max_wait_seconds} 秒）")

    async def _download_file(self, url: str, output_path: Path):
        """下载视频文件"""
        async with httpx.AsyncClient(proxies=self.proxy, timeout=120) as client:
            response = await client.get(url)
            response.raise_for_status()
            output_path.write_bytes(response.content)

        print(f"    ✅ 已保存: {output_path}")


class MockVideoGenerator(VideoGenerator):
    """
    模拟视频生成器 - 用于测试

    不实际调用 API，而是生成一个占位视频或图片
    """

    async def generate_from_storyboard(
        self,
        storyboard: Storyboard,
        output_name: str = None
    ) -> List[VideoResult]:
        """模拟生成视频"""
        results = []

        for scene in storyboard.scenes:
            print(f"  🎬 [MOCK] 模拟生成场景 {scene.scene_number}...")

            # 创建一个占位文本文件表示"视频"
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            prefix = output_name or f"scene_{scene.scene_number}"
            output_path = self.output_dir / f"{prefix}_{timestamp}_scene{scene.scene_number}.txt"

            content = f"""Mock Video Generation
Scene: {scene.scene_number}
Prompt: {scene.prompt}
Duration: {scene.duration}s
Generated at: {datetime.now()}
"""
            output_path.write_text(content, encoding="utf-8")

            results.append(VideoResult(
                scene_number=scene.scene_number,
                file_path=str(output_path),
                status="success (mock)"
            ))

            await asyncio.sleep(0.5)

        return results
