import asyncio
import base64
import time
from pathlib import Path
from typing import List, Optional, Union
from datetime import datetime
from urllib.parse import urljoin
import json

import httpx
from PIL import Image

from .models import Storyboard, Scene, VideoResult
from .config import Config


class VideoGenerator:
    """视频生成器 - 支持多个平台"""

    def __init__(self, provider: str = "auto"):
        """
        初始化视频生成器

        Args:
            provider: 指定使用的平台
                     "auto" - 自动选择（按优先级：即梦 > Runway > Pika）
                     "dreamina" - 强制使用即梦
                     "runway" - 强制使用 Runway
                     "pika" - 强制使用 Pika
        """
        config = Config()
        self.provider = provider
        self.runway_key = config.RUNWAY_API_KEY
        self.pika_key = config.PIKA_API_KEY
        self.dreamina_session = config.DREAMINA_SESSION_ID
        self.proxy = config.HTTP_PROXY or None
        self.output_dir = Path("output/videos")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _get_provider(self) -> str:
        """确定使用哪个平台"""
        if self.provider != "auto":
            return self.provider

        # 自动选择优先级：即梦 > Runway > Pika
        if self.dreamina_session:
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
        """
        根据分镜脚本生成视频

        策略：
        1. 优先使用即梦（国内友好，速度快）
        2. 备选 Runway Gen-3（质量较高）
        3. 备选 Pika Labs
        """
        results = []
        provider = self._get_provider()

        for scene in storyboard.scenes:
            print(f"  🎬 正在生成场景 {scene.scene_number}/{len(storyboard.scenes)}...")

            try:
                if provider == "dreamina":
                    # 使用即梦生成器
                    dreamina = DreaminaGenerator()
                    video_path = await dreamina._generate_with_dreamina(scene, output_name)
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

    async def _generate_with_runway(self, scene: Scene, output_prefix: str = None) -> str:
        """
        使用 Runway Gen-3 生成视频

        注意：Runway API 可能有变化，这里提供基础实现框架
        请参考最新官方文档：https://docs.runwayml.com/
        """
        # Runway API 端点（可能需要根据实际文档调整）
        base_url = "https://api.runwayml.com/v1"

        async with httpx.AsyncClient(proxies=self.proxy, timeout=120) as client:
            headers = {
                "Authorization": f"Bearer {self.runway_key}",
                "Content-Type": "application/json"
            }

            # 1. 提交生成任务
            payload = {
                "prompt": scene.prompt,
                "duration": min(scene.duration, 10),  # Runway 通常限制最大 10 秒
                "ratio": "9:16"  # 短视频常用竖屏比例
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

            # 2. 轮询等待完成
            video_url = await self._poll_runway_task(client, headers, base_url, task_id)

            # 3. 下载视频
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
        """
        使用 Pika Labs 生成视频

        参考：https://pika.art/
        """
        base_url = "https://api.pika.art/v1"

        async with httpx.AsyncClient(proxies=self.proxy, timeout=120) as client:
            headers = {
                "Authorization": f"Bearer {self.pika_key}",
                "Content-Type": "application/json"
            }

            # 提交生成任务
            payload = {
                "prompt": scene.prompt,
                "duration": min(scene.duration, 3),  # Pika 免费版通常 3 秒
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

            # 轮询等待
            video_url = await self._poll_pika_task(client, headers, base_url, generation_id)

            # 下载
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

    async def generate_with_image_prompt(
        self,
        image_path: str,
        prompt: str,
        output_name: str = None
    ) -> str:
        """
        使用图片 + 提示词生成视频（Img2Video）

        部分平台支持从图片开始生成视频
        """
        # 实现 Img2Video 逻辑
        # 这里需要根据具体 API 文档实现
        raise NotImplementedError("Img2Video 功能待实现")

    async def _download_file(self, url: str, output_path: Path):
        """下载文件"""
        async with httpx.AsyncClient(proxies=self.proxy, timeout=120) as client:
            response = await client.get(url)
            response.raise_for_status()
            output_path.write_bytes(response.content)

        print(f"    ✅ 已保存: {output_path}")


class DreaminaGenerator(VideoGenerator):
    """
    即梦 (Dreamina) 视频生成器

    即梦是字节跳动旗下的 AI 视频生成工具，支持文生视频和图生视频。
    由于即梦目前没有公开 API，需要通过 Cookie/Session 方式调用。

    获取认证信息：
    1. 登录 https://jimeng.jianying.com/
    2. 打开浏览器开发者工具 (F12)
    3. 在 Application/Storage -> Cookies 中找到以下字段：
       - sessionid
       - uid
       - did
    4. 将这些值配置到 .env 文件中
    """

    def __init__(self):
        super().__init__()
        config = Config()
        self.session_id = getattr(config, 'DREAMINA_SESSION_ID', '')
        self.uid = getattr(config, 'DREAMINA_UID', '')
        self.did = getattr(config, 'DREAMINA_DID', '')
        self.base_url = "https://jimeng.jianying.com"

    async def generate_from_storyboard(
        self,
        storyboard: Storyboard,
        output_name: str = None
    ) -> List[VideoResult]:
        """根据分镜脚本使用即梦生成视频"""
        results = []

        for scene in storyboard.scenes:
            print(f"  🎬 [即梦] 正在生成场景 {scene.scene_number}/{len(storyboard.scenes)}...")

            try:
                video_path = await self._generate_with_dreamina(scene, output_name)

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

            # 避免请求过快
            await asyncio.sleep(3)

        return results

    async def _generate_with_dreamina(self, scene: Scene, output_prefix: str = None) -> str:
        """调用即梦 API 生成视频"""

        if not all([self.session_id, self.uid, self.did]):
            raise ValueError("缺少即梦认证信息，请配置 DREAMINA_SESSION_ID, DREAMINA_UID, DREAMINA_DID")

        headers = {
            "Content-Type": "application/json",
            "Cookie": f"sessionid={self.session_id}; uid={self.uid}; did={self.did}",
            "Referer": "https://jimeng.jianying.com/",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }

        async with httpx.AsyncClient(proxies=self.proxy, timeout=120) as client:
            # 1. 提交生成任务
            # 注意：以下 API 端点和参数格式可能需要根据实际接口调整
            payload = {
                "prompt": scene.prompt,
                "duration": min(int(scene.duration), 10),  # 即梦通常支持 5-10 秒
                "aspect_ratio": "9:16",  # 竖屏
                "model": "jimeng-2.0"  # 模型版本
            }

            # 提交任务
            submit_url = f"{self.base_url}/api/v1/video/generate"

            try:
                response = await client.post(
                    submit_url,
                    headers=headers,
                    json=payload
                )
                response.raise_for_status()
                data = response.json()

            except httpx.HTTPError as e:
                # 如果上述端点失败，使用模拟响应（实际使用时需要逆向正确的API）
                print(f"    ⚠️ API 调用失败，尝试备用方案: {e}")
                data = await self._try_alternative_api(client, headers, payload)

            task_id = data.get("data", {}).get("task_id") or data.get("task_id")
            if not task_id:
                raise ValueError(f"未能获取任务ID: {data}")

            print(f"    ⏳ 即梦任务已提交: {task_id}，等待生成...")

            # 2. 轮询等待完成
            video_url = await self._poll_dreamina_task(client, headers, task_id)

            # 3. 下载视频
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            prefix = output_prefix or f"scene_{scene.scene_number}"
            output_path = self.output_dir / f"{prefix}_{timestamp}_scene{scene.scene_number}.mp4"

            await self._download_file(video_url, output_path)

            return str(output_path)

    async def _try_alternative_api(self, client: httpx.AsyncClient, headers: dict, payload: dict) -> dict:
        """
        尝试备用 API 端点
        即梦可能使用不同的端点格式
        """
        # 尝试其他可能的端点
        alternative_urls = [
            f"{self.base_url}/api/video/generate",
            f"{self.base_url}/api/v2/generation",
            "https://api.icutool.com/jimeng/generate"  # 第三方中转（如果存在）
        ]

        for url in alternative_urls:
            try:
                response = await client.post(url, headers=headers, json=payload, timeout=10)
                if response.status_code == 200:
                    return response.json()
            except:
                continue

        raise ValueError("无法找到可用的即梦 API 端点，请检查认证信息或 API 文档")

    async def _poll_dreamina_task(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        task_id: str,
        max_retries: int = 60
    ) -> str:
        """轮询即梦任务状态"""

        status_urls = [
            f"{self.base_url}/api/v1/video/status",
            f"{self.base_url}/api/video/status",
            f"{self.base_url}/api/v1/task/status"
        ]

        for i in range(max_retries):
            for status_url in status_urls:
                try:
                    response = await client.get(
                        status_url,
                        headers=headers,
                        params={"task_id": task_id},
                        timeout=10
                    )

                    if response.status_code != 200:
                        continue

                    data = response.json()

                    # 解析状态（根据实际响应格式调整）
                    status = data.get("data", {}).get("status") or data.get("status")

                    if status in ["completed", "success", "done"]:
                        # 获取视频 URL
                        video_url = (
                            data.get("data", {}).get("video_url") or
                            data.get("data", {}).get("url") or
                            data.get("video_url")
                        )
                        if video_url:
                            return video_url

                    elif status in ["failed", "error", "fail"]:
                        error_msg = data.get("data", {}).get("error") or data.get("message", "Unknown error")
                        raise ValueError(f"即梦生成失败: {error_msg}")

                    # 还在生成中
                    break

                except httpx.RequestError:
                    continue

            # 显示进度
            if i % 6 == 0:  # 每30秒显示一次
                print(f"    ⏳ 仍在生成中... ({i//12}分钟)")

            await asyncio.sleep(5)

        raise TimeoutError("等待即梦视频生成超时")

    async def generate_with_image(
        self,
        image_path: str,
        prompt: str,
        output_name: str = None
    ) -> str:
        """
        使用即梦进行图生视频

        Args:
            image_path: 图片路径
            prompt: 视频动作描述
            output_name: 输出文件名
        """
        if not all([self.session_id, self.uid, self.did]):
            raise ValueError("缺少即梦认证信息")

        # 读取图片并转为 base64
        image = Image.open(image_path)
        import io
        buffer = io.BytesIO()
        image.save(buffer, format='PNG')
        img_base64 = base64.b64encode(buffer.getvalue()).decode()

        headers = {
            "Content-Type": "application/json",
            "Cookie": f"sessionid={self.session_id}; uid={self.uid}; did={self.did}",
            "Referer": "https://jimeng.jianying.com/",
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }

        payload = {
            "image": f"data:image/png;base64,{img_base64}",
            "prompt": prompt,
            "duration": 5,
            "aspect_ratio": "9:16",
            "model": "jimeng-2.0"
        }

        async with httpx.AsyncClient(proxies=self.proxy, timeout=120) as client:
            response = await client.post(
                f"{self.base_url}/api/v1/video/img2video",
                headers=headers,
                json=payload
            )
            response.raise_for_status()
            data = response.json()

            task_id = data.get("data", {}).get("task_id") or data.get("task_id")
            if not task_id:
                raise ValueError(f"未能获取任务ID: {data}")

            print(f"    ⏳ 即梦图生视频任务: {task_id}")

            video_url = await self._poll_dreamina_task(client, headers, task_id)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = self.output_dir / f"{output_name or 'img2video'}_{timestamp}.mp4"

            await self._download_file(video_url, output_path)

            return str(output_path)


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
