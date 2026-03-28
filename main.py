#!/usr/bin/env python3
"""
ShortGen - AI 视频生成 Agent
支持：剧情分镜生成视频 / 热点自动生成视频
"""

import asyncio
import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from src.storyboard import StoryboardGenerator
from src.trending import TrendingFetcher
from src.video_gen import VideoGenerator
from src.config import Config


def setup_directories():
    """创建必要的目录"""
    dirs = ["output/videos", "output/storyboards", "output/images"]
    for d in dirs:
        Path(d).mkdir(parents=True, exist_ok=True)


async def generate_from_plot(plot: str, output_name: str = None, provider: str = "auto"):
    """根据剧情生成视频"""
    print(f"🎬 开始生成视频...")
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
        print(f"  📹 {f}")

    return video_files


async def generate_from_trending(category: str = "general", provider: str = "auto"):
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
    return await generate_from_plot(plot, output_name, provider)


async def interactive_mode():
    """交互模式"""
    print("=" * 50)
    print("🎬 ShortGen - AI 视频生成 Agent")
    print("=" * 50)
    print("\n请选择模式:")
    print("1. 输入剧情生成视频")
    print("2. 根据热点自动生成视频")
    print("3. 退出")

    choice = input("\n请输入选项 (1-3): ").strip()

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
            await generate_from_plot(plot, output_name or None)
        else:
            print("❌ 剧情不能为空")

    elif choice == "2":
        print("\n热点类别:")
        print("1. 综合")
        print("2. 科技")
        print("3. 娱乐")
        print("4. 体育")

        cat_choice = input("\n请选择类别 (1-4): ").strip()
        categories = {"1": "general", "2": "tech", "3": "entertainment", "4": "sports"}
        category = categories.get(cat_choice, "general")

        await generate_from_trending(category)

    elif choice == "3":
        print("再见！")
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(description="ShortGen - AI 视频生成 Agent")
    parser.add_argument("--plot", "-p", help="剧情描述文本")
    parser.add_argument("--file", "-f", help="从文件读取剧情")
    parser.add_argument("--trending", "-t", action="store_true", help="根据热点生成")
    parser.add_argument("--category", "-c", default="general", help="热点类别")
    parser.add_argument("--output", "-o", help="输出文件名前缀")
    parser.add_argument("--interactive", "-i", action="store_true", help="交互模式")

    args = parser.parse_args()

    setup_directories()

    if args.interactive or len(sys.argv) == 1:
        asyncio.run(interactive_mode())
    elif args.file:
        plot = Path(args.file).read_text(encoding="utf-8")
        asyncio.run(generate_from_plot(plot, args.output))
    elif args.plot:
        asyncio.run(generate_from_plot(args.plot, args.output))
    elif args.trending:
        asyncio.run(generate_from_trending(args.category))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()