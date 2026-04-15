#!/usr/bin/env python3
"""
ShortGen - AI 视频生成 Agent
支持：剧情分镜生成视频 / 热点自动生成视频 / 完整音视频合成
"""

import asyncio
import argparse
import os
import sys
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from src.storyboard import StoryboardGenerator
from src.trending import TrendingFetcher
from src.video_gen import VideoGenerator
from src.audio_gen import AudioGenerator
from src.character_manager import CharacterManager
from src.composer import VideoComposer
from src.config import Config, get_output_root
from src.scene_image_gen import SceneImageGenerator


def resolve_project_name(output_name: str | None) -> str:
    """为当前运行生成项目目录名"""
    if output_name:
        return output_name
    return f"project_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def setup_project_environment(project_name: str):
    """设置当前运行的独立项目输出目录"""
    project_root = Path("output/projects") / project_name
    os.environ["PROJECT_OUTPUT_ROOT"] = str(project_root)


def setup_directories():
    """创建必要的目录"""
    dirs = [
        get_output_root() / "videos",
        get_output_root() / "storyboards",
        get_output_root() / "images",
        get_output_root() / "audios",
        get_output_root() / "characters",
        get_output_root() / "final",
    ]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)


async def generate_from_plot(plot: str, output_name: str = None, provider: str = "dreamina"):
    """根据剧情生成视频（基础版，不含音频）"""
    output_name = resolve_project_name(output_name)
    setup_project_environment(output_name)
    setup_directories()

    print(f"🎬 开始生成视频...")
    print(f"📁 项目目录: {get_output_root()}")
    print(f"📖 剧情: {plot[:100]}...")

    # 1. 生成分镜脚本
    storyboard_gen = StoryboardGenerator()
    storyboard = await storyboard_gen.generate(plot)

    print(f"\n✅ 分镜脚本已生成，共 {len(storyboard.scenes)} 个场景")
    for i, scene in enumerate(storyboard.scenes, 1):
        print(f"  场景{i}: {scene.description[:50]}...")

    # 保存分镜脚本
    output_file = storyboard_gen.save(storyboard, output_name)
    print(f"\n💾 分镜脚本已保存: {output_file}")

    # 2. 生成视频
    video_gen = VideoGenerator(provider=provider)
    video_files = await video_gen.generate_from_storyboard(storyboard, output_name)

    print(f"\n🎉 视频生成完成！")
    for f in video_files:
        if f.status == "success":
            print(f"  📹 场景 {f.scene_number}: {f.file_path}")
        else:
            print(f"  ❌ 场景 {f.scene_number}: {f.error_message}")

    return video_files


async def generate_full(
    plot: str,
    output_name: str = None,
    provider: str = "dreamina",
    enable_audio: bool = True,
    enable_characters: bool = True
):
    """
    完整视频生成流程

    包含：分镜生成 → 角色预生成 → 分镜图生成 → 视频生成 → 音频生成 → 视频合成
    """
    output_name = resolve_project_name(output_name)
    setup_project_environment(output_name)
    setup_directories()

    print("=" * 50)
    print("🎬 ShortGen 完整视频生成")
    print("=" * 50)
    print(f"📁 项目目录: {get_output_root()}")
    print(f"📖 剧情: {plot[:100]}...")

    # 1. 生成分镜脚本（增强版，包含角色和对话）
    print("\n📝 步骤 1/6: 生成分镜脚本...")
    storyboard_gen = StoryboardGenerator()
    storyboard = await storyboard_gen.generate(
        plot,
        extract_characters=enable_characters
    )

    print(f"\n✅ 分镜脚本已生成")
    print(f"   📌 标题: {storyboard.title}")
    print(f"   👥 角色: {len(storyboard.characters)} 个")
    print(f"   🎬 场景: {len(storyboard.scenes)} 个")
    print(f"   ⏱️ 时长: {storyboard.total_duration:.1f} 秒")

    # 2. 预生成角色图片（如果有角色）
    character_manager = CharacterManager()
    if enable_characters and storyboard.characters:
        print(f"\n🎨 步骤 2/6: 预生成角色图片...")
        character_manager.load_from_storyboard(storyboard)
        char_results = await character_manager.prepare_characters(storyboard.characters)

        success_count = sum(1 for r in char_results if r.status.startswith("success"))
        print(f"   ✅ 成功: {success_count}/{len(char_results)}")
    else:
        print(f"\n🎨 步骤 2/6: 跳过角色生成（无角色或已禁用）")

    # 3. 生成分镜图
    print(f"\n🖼️ 步骤 3/6: 生成场景分镜图...")
    scene_image_gen = SceneImageGenerator()
    scene_image_results = await scene_image_gen.generate_for_storyboard(
        storyboard,
        output_name=output_name,
    )
    success_scene_images = [
        result for result in scene_image_results if result.status.startswith("success")
    ]
    print(f"   ✅ 成功: {len(success_scene_images)}/{len(scene_image_results)}")

    # 在角色图和分镜图写回后再保存一次分镜脚本
    storyboard_file = storyboard_gen.save(storyboard, output_name)
    print(f"   💾 已更新分镜文件: {storyboard_file}")

    # 4. 生成视频
    print(f"\n🎬 步骤 4/6: 生成视频片段...")
    video_gen = VideoGenerator(provider=provider)
    video_results = await video_gen.generate_from_storyboard(storyboard, output_name)

    success_videos = [v for v in video_results if v.status == "success"]
    print(f"   ✅ 成功: {len(success_videos)}/{len(video_results)}")

    # 5. 生成音频（如果启用）
    audio_results = []
    if enable_audio:
        print(f"\n🔊 步骤 5/6: 生成音频...")

        # 检查 TTS 配置
        audio_warnings = Config.validate_audio()
        if audio_warnings:
            print(f"   ⚠️ {audio_warnings[0]}")
            print(f"   跳过音频生成...")
        else:
            audio_gen = AudioGenerator()

            # 设置角色音色
            for char in storyboard.characters:
                if char.voice_id:
                    audio_gen.set_character_voice(char.id, char.voice_id)

            # 为每个场景生成音频
            for scene in storyboard.scenes:
                scene_audios = await audio_gen.generate_for_scene(scene)
                audio_results.extend(scene_audios)

                if scene_audios:
                    success_audios = [a for a in scene_audios if a.status == "success"]
                    print(f"   场景 {scene.scene_number}: {len(success_audios)} 个音频")

            # 生成背景音乐
            if storyboard.background_music:
                print(f"   🎵 生成背景音乐...")
                bgm_result = await audio_gen.generate_background_music(
                    prompt=storyboard.background_music
                )
                audio_results.append(bgm_result)
    else:
        print(f"\n🔊 步骤 5/6: 跳过音频生成（已禁用）")

    # 6. 合成最终视频
    print(f"\n🎞️ 步骤 6/6: 合成最终视频...")
    composer = VideoComposer()
    final_result = await composer.compose(
        video_results,
        audio_results,
        storyboard,
        output_name
    )

    # 输出结果
    print("\n" + "=" * 50)
    if final_result.status == "success":
        print("🎉 视频生成完成！")
        print(f"   📹 输出: {final_result.output_path}")
        print(f"   ⏱️ 时长: {final_result.duration:.1f} 秒")
        print(f"   🎞️ 场景数: {final_result.scenes_count}")
        print(f"   🔊 含音频: {'是' if final_result.has_audio else '否'}")
    else:
        print("❌ 视频合成失败")
        print(f"   错误: {final_result.error_message}")
    print("=" * 50)

    return final_result


async def generate_from_trending(
    category: str = "general",
    provider: str = "dreamina",
    full_mode: bool = True
):
    """根据热点生成视频"""
    print(f"🔥 获取热点新闻...")

    # 1. 获取热点
    trending_fetcher = TrendingFetcher()
    trends = await trending_fetcher.fetch(category)

    if not trends:
        print("❌ 未能获取热点新闻")
        return

    print(f"\n📰 找到 {len(trends)} 条热点:")
    for i, t in enumerate(trends[:5], 1):
        print(f"  {i}. {t.title}")

    # 2. 选择第一个热点生成视频
    selected = trends[0]
    print(f"\n👉 选择热点: {selected.title}")

    # 3. 根据热点生成剧情
    storyboard_gen = StoryboardGenerator()
    plot = await storyboard_gen.generate_plot_from_trend(selected)

    print(f"\n📝 生成的剧情:\n{plot}\n")

    # 4. 生成视频
    output_name = f"trending_{selected.id}"
    if full_mode:
        return await generate_full(plot, output_name, provider)
    else:
        return await generate_from_plot(plot, output_name, provider)


async def interactive_mode():
    """交互模式"""
    print("=" * 50)
    print("🎬 ShortGen - AI 视频生成 Agent")
    print("=" * 50)
    print("\n请选择模式:")
    print("1. 输入剧情生成完整视频（含音频和角色）")
    print("2. 输入剧情生成基础视频（仅视频）")
    print("3. 根据热点自动生成视频")
    print("4. 退出")

    choice = input("\n请输入选项 (1-4): ").strip()

    if choice == "1":
        print("\n请输入剧情描述（支持多行，输入空行结束）:")
        lines = []
        while True:
            line = input()
            if not line.strip():
                break
            lines.append(line)
        plot = "\n".join(lines)

        if plot.strip():
            output_name = input("\n输出文件名（可选，直接回车使用默认）: ").strip()
            await generate_full(plot, output_name or None)
        else:
            print("❌ 剧情不能为空")

    elif choice == "2":
        print("\n请输入剧情描述（支持多行，输入空行结束）:")
        lines = []
        while True:
            line = input()
            if not line.strip():
                break
            lines.append(line)
        plot = "\n".join(lines)

        if plot.strip():
            output_name = input("\n输出文件名（可选，直接回车使用默认）: ").strip()
            await generate_from_plot(plot, output_name or None)
        else:
            print("❌ 剧情不能为空")

    elif choice == "3":
        print("\n热点类别:")
        print("1. 综合")
        print("2. 科技")
        print("3. 娱乐")
        print("4. 体育")

        cat_choice = input("\n请选择类别 (1-4): ").strip()
        categories = {"1": "general", "2": "tech", "3": "entertainment", "4": "sports"}
        category = categories.get(cat_choice, "general")

        await generate_from_trending(category)

    elif choice == "4":
        print("再见！")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="ShortGen - AI 视频生成 Agent")
    parser.add_argument("--plot", "-p", help="剧情描述文本")
    parser.add_argument("--file", "-f", help="从文件读取剧情")
    parser.add_argument("--trending", "-t", action="store_true", help="根据热点生成")
    parser.add_argument("--category", "-c", default="general", help="热点类别")
    parser.add_argument("--output", "-o", help="输出文件名前缀")
    parser.add_argument(
        "--provider",
        choices=["dreamina", "auto", "runway", "pika"],
        default=Config().VIDEO_PROVIDER,
        help="视频生成平台，默认使用 .env 中的 VIDEO_PROVIDER"
    )
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式")
    parser.add_argument("--full", action="store_true", help="完整模式（含音频和角色）")
    parser.add_argument("--no-audio", action="store_true", help="禁用音频生成")
    parser.add_argument("--no-characters", action="store_true", help="禁用角色一致性")

    args = parser.parse_args()

    # 检查环境变量
    config_errors = Config.validate()
    if config_errors:
        print("❌ 配置错误:")
        for error in config_errors:
            print(f"   {error}")
        return

    # 交互模式
    if args.interactive or len(sys.argv) == 1:
        asyncio.run(interactive_mode())
        return

    # 文件模式
    if args.file:
        plot = Path(args.file).read_text(encoding="utf-8")
        if args.full:
            asyncio.run(generate_full(
                plot,
                args.output,
                args.provider,
                enable_audio=not args.no_audio,
                enable_characters=not args.no_characters
            ))
        else:
            asyncio.run(generate_from_plot(plot, args.output, args.provider))
        return

    # 剧情模式
    if args.plot:
        if args.full:
            asyncio.run(generate_full(
                args.plot,
                args.output,
                args.provider,
                enable_audio=not args.no_audio,
                enable_characters=not args.no_characters
            ))
        else:
            asyncio.run(generate_from_plot(args.plot, args.output, args.provider))
        return

    # 热点模式
    if args.trending:
        asyncio.run(generate_from_trending(
            args.category,
            args.provider,
            full_mode=args.full
        ))
        return

    # 默认显示帮助
    parser.print_help()


if __name__ == "__main__":
    main()
