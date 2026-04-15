"""
图片生成模块 - 用于生成角色参考图

优先使用火山引擎 AK/SK + V4 签名调用视觉接口。
当前已验证可用的角色图链路为：CVProcess + jimeng_t2i_v40。
如果显式指定 ark，则走新版 Ark 图片生成 API。
"""

import asyncio
import base64
import io
import json
import datetime
import hashlib
import hmac
import time
from pathlib import Path
from typing import Optional

import httpx
import requests
from PIL import Image

from .models import Character, CharacterImageResult
from .config import Config, resolve_output_dir


class ImageGenerator:
    """图片生成器 - 用于角色参考图"""

    def __init__(self):
        config = Config()
        self.ak = config.VOLC_ACCESS_KEY
        self.sk = config.VOLC_SECRET_KEY
        self.ark_api_key = config.ARK_API_KEY
        self.ark_base_url = config.ARK_BASE_URL.rstrip("/")
        self.provider = config.CHARACTER_IMAGE_PROVIDER
        self.model = config.CHARACTER_IMAGE_MODEL
        self.output_dir = resolve_output_dir(config.CHARACTER_IMAGE_DIR)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.proxy = config.HTTP_PROXY or None
        self.visual_endpoint = "https://visual.volcengineapi.com"
        self.visual_host = "visual.volcengineapi.com"
        self.visual_region = "cn-north-1"
        self.visual_service = "cv"

        if self._use_legacy_visual():
            self._init_visual_service()

    def _use_legacy_visual(self) -> bool:
        """是否回退使用旧版 Visual Service"""
        return self.provider == "legacy"

    def _use_signed_aksk(self) -> bool:
        """是否使用 AK/SK 签名接口"""
        return self.provider == "signed_aksk" or (
            self.provider not in ("ark", "legacy") and self.ak and self.sk
        )

    def _create_client(self, timeout: int = 120) -> httpx.AsyncClient:
        """兼容不同 httpx 版本的代理参数"""
        kwargs = {"timeout": timeout}
        if self.proxy:
            try:
                return httpx.AsyncClient(proxy=self.proxy, **kwargs)
            except TypeError:
                return httpx.AsyncClient(proxies=self.proxy, **kwargs)
        return httpx.AsyncClient(**kwargs)

    def _ensure_visual_service(self):
        """确保旧版即梦生图服务已初始化"""
        if not self.ak or not self.sk:
            raise ValueError(
                "未配置旧版即梦生图凭证，请在 .env 中设置 "
                "VOLC_ACCESS_KEY 和 VOLC_SECRET_KEY"
            )
        if not hasattr(self, "visual_service"):
            self._init_visual_service()

    def _ensure_ark_config(self):
        """确保 Ark 图片生成配置有效"""
        if not self.ark_api_key:
            raise ValueError(
                "未配置 ARK_API_KEY，无法调用新版火山图片生成接口。"
            )

    def _ensure_signed_config(self):
        """确保 AK/SK 签名配置有效"""
        if not self.ak or not self.sk:
            raise ValueError(
                "未配置 VOLC_ACCESS_KEY / VOLC_SECRET_KEY，无法调用签名图片接口。"
            )
        if not self.model:
            raise ValueError("未配置 CHARACTER_IMAGE_MODEL(req_key)。")

    def _init_visual_service(self):
        """初始化火山引擎 Visual Service SDK"""
        try:
            from volcengine.visual.VisualService import VisualService
        except ImportError:
            raise ImportError("请安装火山引擎 SDK: pip install volcengine")

        self.visual_service = VisualService()
        self.visual_service.set_ak(self.ak)
        self.visual_service.set_sk(self.sk)

    async def generate_character_image(
        self,
        character: Character,
        style: str = "realistic portrait, high quality photography",
        regenerate: bool = False
    ) -> CharacterImageResult:
        """为角色生成参考图片"""
        existing_path = self.output_dir / f"{character.id}.png"
        if existing_path.exists() and not regenerate:
            return CharacterImageResult(
                character_id=character.id,
                character_name=character.name,
                image_path=str(existing_path),
                status="success (cached)"
            )

        prompt = self._build_character_prompt(character, style)

        try:
            if self._use_signed_aksk():
                image_bytes = await self._generate_image_signed(prompt)
                existing_path.write_bytes(image_bytes)
                return CharacterImageResult(
                    character_id=character.id,
                    character_name=character.name,
                    image_path=str(existing_path),
                    status="success"
                )
            elif self._use_legacy_visual():
                image_url = await self._generate_image_legacy(prompt)
            else:
                image_bytes = await self._generate_image_ark(prompt)
                existing_path.write_bytes(image_bytes)
                return CharacterImageResult(
                    character_id=character.id,
                    character_name=character.name,
                    image_path=str(existing_path),
                    status="success"
                )

            await self._download_and_save(image_url, existing_path)
            return CharacterImageResult(
                character_id=character.id,
                character_name=character.name,
                image_path=str(existing_path),
                status="success"
            )
        except Exception as e:
            return CharacterImageResult(
                character_id=character.id,
                character_name=character.name,
                image_path="",
                status="failed",
                error_message=str(e)
            )

    def _build_character_prompt(self, character: Character, style: str) -> str:
        """构建角色图片生成提示词"""
        return (
            f"{character.description}, "
            f"{style}, "
            f"neutral background, centered composition, "
            f"professional photography, detailed"
        )

    @staticmethod
    def _sign(key: bytes, msg: str) -> bytes:
        return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()

    def _get_signature_key(self, date_stamp: str) -> bytes:
        k_date = self._sign(self.sk.encode("utf-8"), date_stamp)
        k_region = self._sign(k_date, self.visual_region)
        k_service = self._sign(k_region, self.visual_service)
        return self._sign(k_service, "request")

    def _format_query(self, parameters: dict[str, str]) -> str:
        return "&".join(f"{key}={parameters[key]}" for key in sorted(parameters))

    def _signed_post(self, action: str, body: dict) -> dict:
        """
        使用 AK/SK V4 签名调用视觉接口。
        这套实现直接对应你给的官方签名示例。
        """
        self._ensure_signed_config()

        query = self._format_query({
            "Action": action,
            "Version": "2022-08-31",
        })
        request_body = json.dumps(
            body,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        request_body_bytes = request_body.encode("utf-8")

        now = datetime.datetime.utcnow()
        current_date = now.strftime("%Y%m%dT%H%M%SZ")
        date_stamp = now.strftime("%Y%m%d")

        payload_hash = hashlib.sha256(request_body_bytes).hexdigest()
        canonical_headers = (
            f"content-type:application/json\n"
            f"host:{self.visual_host}\n"
            f"x-content-sha256:{payload_hash}\n"
            f"x-date:{current_date}\n"
        )
        signed_headers = "content-type;host;x-content-sha256;x-date"
        canonical_request = (
            f"POST\n/\n{query}\n{canonical_headers}\n"
            f"{signed_headers}\n{payload_hash}"
        )

        credential_scope = (
            f"{date_stamp}/{self.visual_region}/{self.visual_service}/request"
        )
        string_to_sign = (
            f"HMAC-SHA256\n{current_date}\n{credential_scope}\n"
            f"{hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()}"
        )
        signing_key = self._get_signature_key(date_stamp)
        signature = hmac.new(
            signing_key,
            string_to_sign.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        authorization = (
            f"HMAC-SHA256 Credential={self.ak}/{credential_scope}, "
            f"SignedHeaders={signed_headers}, Signature={signature}"
        )
        headers = {
            "X-Date": current_date,
            "Authorization": authorization,
            "X-Content-Sha256": payload_hash,
            "Content-Type": "application/json",
        }
        url = f"{self.visual_endpoint}?{query}"

        response = requests.post(url, headers=headers, data=request_body_bytes, timeout=120)
        if response.status_code != 200:
            raise ValueError(response.text)

        return response.json()

    async def _generate_image_signed(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        use_realphoto: bool = True
    ) -> bytes:
        """使用 AK/SK 签名同步生成图片"""
        form = {
            "req_key": self.model,
            "prompt": prompt,
            "width": width,
            "height": height,
            "use_realphoto": use_realphoto,
            "seed": -1,
        }

        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(None, self._signed_post, "CVProcess", form)

        code = resp.get("code", -1)
        if code not in (0, 10000):
            raise ValueError(f"生图任务提交失败: {resp}")

        images = resp.get("data", {}).get("binary_data_base64", [])
        if not images:
            raise ValueError(f"未返回图片数据: {resp}")

        return base64.b64decode(images[0])

    async def _generate_image_ark(
        self,
        prompt: str,
        size: str = "1024x1024"
    ) -> bytes:
        """
        使用 Ark 图片生成 API 生成图片。

        参考火山引擎官方图片生成文档，走 /images/generations 接口。
        """
        self._ensure_ark_config()

        payload = {
            "model": self.model,
            "prompt": prompt,
            "size": size,
            "response_format": "b64_json",
        }

        headers = {
            "Authorization": f"Bearer {self.ark_api_key}",
            "Content-Type": "application/json",
        }

        async with self._create_client(timeout=120) as client:
            response = await client.post(
                f"{self.ark_base_url}/images/generations",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        items = data.get("data", [])
        if not items:
            raise ValueError(f"Ark 图片生成未返回数据: {data}")

        first = items[0]
        image_base64 = first.get("b64_json")
        image_url = first.get("url")

        if image_base64:
            return base64.b64decode(image_base64)

        if image_url:
            async with self._create_client(timeout=120) as client:
                response = await client.get(image_url)
                response.raise_for_status()
                return response.content

        raise ValueError(f"Ark 图片生成返回结构不符合预期: {data}")

    async def _generate_image_legacy(
        self,
        prompt: str,
        width: int = 1024,
        height: int = 1024,
        use_realphoto: bool = True
    ) -> str:
        """调用旧版即梦生图 API"""
        form = {
            "req_key": self.model,
            "prompt": prompt,
            "width": width,
            "height": height,
            "use_realphoto": use_realphoto,
            "seed": -1,
        }

        self._ensure_visual_service()

        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None, self.visual_service.cv_submit_task, form
        )

        code = resp.get("code", -1)
        if code not in (0, 10000):
            raise ValueError(f"生图任务提交失败: {resp.get('message', 'Unknown error')}")

        task_id = resp.get("data", {}).get("task_id")
        return await self._poll_image_task(task_id)

    async def _poll_image_task(
        self,
        task_id: str,
        max_wait: int = 300,
        interval: int = 3
    ) -> str:
        """轮询旧版图片生成任务"""
        form = {
            "req_key": self.model,
            "task_id": task_id,
        }

        self._ensure_visual_service()
        start_time = time.time()

        while (time.time() - start_time) < max_wait:
            loop = asyncio.get_event_loop()
            resp = await loop.run_in_executor(
                None, self.visual_service.cv_get_result, form
            )

            status = resp.get("data", {}).get("status", "")
            code = resp.get("code", -1)

            if status == "done" and code in (0, 10000):
                image_url = (
                    resp.get("data", {}).get("image_url") or
                    resp.get("data", {}).get("resp_data", {}).get("image_url")
                )
                if image_url:
                    return image_url
            elif status in ("not_found", "expired"):
                raise ValueError(f"任务异常: {status}")

            await asyncio.sleep(interval)

        raise TimeoutError("图片生成超时")

    async def _download_and_save(self, url: str, output_path: Path):
        """下载并保存图片"""
        async with self._create_client(timeout=60) as client:
            response = await client.get(url)
            response.raise_for_status()
            output_path.write_bytes(response.content)

    async def generate_image_with_reference(
        self,
        prompt: str,
        reference_image: str,
        strength: float = 0.5
    ) -> str:
        """
        基于参考图生成新图片（保持角色一致性）

        Ark 暂时用文字补充的方式兜底；旧版接口继续保留图生图。
        """
        if not self._use_legacy_visual() and not self._use_signed_aksk():
            reference = Image.open(reference_image)
            buffer = io.BytesIO()
            reference.save(buffer, format="PNG")
            encoded = base64.b64encode(buffer.getvalue()).decode()

            self._ensure_ark_config()
            payload = {
                "model": self.model,
                "prompt": prompt,
                "size": "1024x1024",
                "response_format": "b64_json",
                "image": [encoded],
            }
            headers = {
                "Authorization": f"Bearer {self.ark_api_key}",
                "Content-Type": "application/json",
            }
            async with self._create_client(timeout=120) as client:
                response = await client.post(
                    f"{self.ark_base_url}/images/generations",
                    headers=headers,
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()

            items = data.get("data", [])
            if not items or not items[0].get("b64_json"):
                raise ValueError(f"Ark 图生图未返回图片数据: {data}")

            output_path = self.output_dir / f"ref_{int(time.time())}.png"
            output_path.write_bytes(base64.b64decode(items[0]["b64_json"]))
            return str(output_path)

        if self._use_signed_aksk():
            raise ValueError(
                "签名接口的图生图参数仍需根据你账号开通的 req_key 确认，"
                "当前先支持文生角色图。"
            )

        image = Image.open(reference_image)
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        img_base64 = base64.b64encode(buffer.getvalue()).decode()

        form = {
            "req_key": "jimeng_high_aes_i2i",
            "prompt": prompt,
            "image": img_base64,
            "strength": strength,
            "seed": -1,
        }

        self._ensure_visual_service()

        loop = asyncio.get_event_loop()
        resp = await loop.run_in_executor(
            None, self.visual_service.cv_submit_task, form
        )

        code = resp.get("code", -1)
        if code not in (0, 10000):
            raise ValueError(f"图生图任务提交失败: {resp.get('message')}")

        task_id = resp.get("data", {}).get("task_id")
        image_url = await self._poll_image_task(task_id)

        output_path = self.output_dir / f"ref_{int(time.time())}.png"
        await self._download_and_save(image_url, output_path)
        return str(output_path)

    async def generate_image_with_references(
        self,
        prompt: str,
        reference_images: list[str],
    ) -> str:
        """
        使用多张参考图生成图片。

        当前主要对接 Ark/Seedream 4.0 的 image 数组形态。
        对于签名接口，如果未确认支持多参考图，则回退到首张参考图。
        """
        clean_images = [image for image in reference_images if image]
        if not clean_images:
            raise ValueError("reference_images 不能为空")

        if self._use_signed_aksk():
            return await self.generate_image_with_reference(prompt, clean_images[0])

        if self._use_legacy_visual():
            return await self.generate_image_with_reference(prompt, clean_images[0])

        self._ensure_ark_config()

        ark_images: list[str] = []
        for image_path in clean_images:
            if image_path.startswith("http://") or image_path.startswith("https://"):
                ark_images.append(image_path)
                continue

            image = Image.open(image_path)
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            encoded = base64.b64encode(buffer.getvalue()).decode()
            ark_images.append(f"data:image/png;base64,{encoded}")

        payload = {
            "model": self.model,
            "prompt": prompt,
            "size": "1024x1024",
            "response_format": "b64_json",
            "image": ark_images,
            "sequential_image_generation": "disabled",
            "stream": False,
            "watermark": True,
        }
        headers = {
            "Authorization": f"Bearer {self.ark_api_key}",
            "Content-Type": "application/json",
        }
        async with self._create_client(timeout=120) as client:
            response = await client.post(
                f"{self.ark_base_url}/images/generations",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        items = data.get("data", [])
        if not items or not items[0].get("b64_json"):
            raise ValueError(f"Ark 多参考图生成未返回图片数据: {data}")

        output_path = self.output_dir / f"refs_{int(time.time())}.png"
        output_path.write_bytes(base64.b64decode(items[0]["b64_json"]))
        return str(output_path)

    async def generate_scene_image(
        self,
        image_id: str,
        prompt: str,
        reference_image: str | None = None,
        reference_images: list[str] | None = None,
        regenerate: bool = False,
    ) -> str:
        """
        生成场景分镜图。

        如果底层接口支持参考图，则优先使用角色图参考；
        否则回退到纯文本生图，但保留相同的输出路径约定。
        """
        output_path = self.output_dir.parent / "images" / f"{image_id}.png"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if output_path.exists() and not regenerate:
            return str(output_path)

        scene_reference_images = [img for img in (reference_images or []) if img]
        if reference_image and reference_image not in scene_reference_images:
            scene_reference_images.insert(0, reference_image)

        if scene_reference_images:
            try:
                if len(scene_reference_images) == 1:
                    generated = await self.generate_image_with_reference(
                        prompt=prompt,
                        reference_image=scene_reference_images[0],
                    )
                else:
                    generated = await self.generate_image_with_references(
                        prompt=prompt,
                        reference_images=scene_reference_images,
                    )
                generated_path = Path(generated)
                if generated_path != output_path:
                    output_path.write_bytes(generated_path.read_bytes())
                return str(output_path)
            except Exception:
                # 当前 provider 不支持图参考时回退到文本生图
                pass

        scene_prompt = (
            f"{prompt}, cinematic storyboard frame, realistic film still, ultra detailed"
        )

        if self._use_signed_aksk():
            image_bytes = await self._generate_image_signed(scene_prompt)
            output_path.write_bytes(image_bytes)
            return str(output_path)

        if self._use_legacy_visual():
            image_url = await self._generate_image_legacy(scene_prompt)
            await self._download_and_save(image_url, output_path)
            return str(output_path)

        image_bytes = await self._generate_image_ark(scene_prompt)
        output_path.write_bytes(image_bytes)
        return str(output_path)
