#!/usr/bin/env python3
"""
YouTube 下载架构测试脚本

测试两种场景：
1. 本地开发（需要代理）
2. 新加坡服务器（直连）

验证 IP 一致性和下载速度
"""

import asyncio
import sys
import os
import time
import json
import subprocess

sys.path.insert(0, ".")

from app.services.url_extractor import YouTubeURLExtractor
from app.services.agentgo_service import get_agentgo_service
from app.config import settings


async def get_current_ip(use_proxy: bool = True) -> str:
    """获取当前出口 IP"""
    try:
        if use_proxy and settings.http_proxy:
            result = subprocess.run(
                ["curl", "-s", "-x", settings.http_proxy, "https://httpbin.org/ip"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        else:
            result = subprocess.run(
                ["curl", "-s", "https://httpbin.org/ip"],
                capture_output=True,
                text=True,
                timeout=30,
            )

        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get("origin", "Unknown")
    except Exception as e:
        return f"Error: {e}"
    return "Unknown"


async def test_architecture(video_url: str, resolution: str = "720"):
    """
    测试完整的下载架构
    """
    print("=" * 70)
    print("YouTube 下载架构测试")
    print("=" * 70)

    # 1. 检查环境
    print("\n[1/6] 环境检查")
    print(f"  代理配置: {settings.http_proxy or '未配置'}")

    proxy_ip = await get_current_ip(use_proxy=True)
    direct_ip = await get_current_ip(use_proxy=False)

    print(f"  代理 IP: {proxy_ip}")
    print(f"  直连 IP: {direct_ip}")

    # 判断是否在中国大陆
    is_china = "Error" in direct_ip or direct_ip == "Unknown"
    print(f"  环境: {'中国大陆 (需要代理)' if is_china else '海外 (可直连)'}")

    # 2. 获取 AgentGo 认证（可选）
    print("\n[2/6] AgentGo 认证")
    service = get_agentgo_service()
    auth_bundle = None

    if service.is_api_configured():
        try:
            auth_bundle = await service.get_youtube_authentication_bundle(
                region="us", force_refresh=False
            )
            if auth_bundle:
                print(f"  AgentGo IP: {auth_bundle.browser_ip}")
                print(
                    f"  Cookies: {len(auth_bundle.cookies) if auth_bundle.cookies else 0}"
                )
                print(
                    f"  Visitor Data: {len(auth_bundle.visitor_data) if auth_bundle.visitor_data else 0} chars"
                )
        except Exception as e:
            print(f"  AgentGo 获取失败: {e}")
    else:
        print("  AgentGo 未配置，跳过")

    # 3. 提取 URL
    print("\n[3/6] URL 提取 (yt-dlp)")
    extractor = YouTubeURLExtractor(region="us", auth_bundle=auth_bundle)

    start_time = time.time()
    video = await extractor.extract(video_url)
    extract_time = time.time() - start_time

    print(f"  标题: {video.title[:50]}")
    print(f"  耗时: {extract_time:.2f}s")

    urls = video.get_download_urls(resolution)

    if not urls.get("video_url"):
        print("  ❌ 未获取到视频 URL")
        return

    vf = urls.get("video_format", {})
    print(
        f"  视频: {vf.get('height')}p {vf.get('ext')} direct={vf.get('is_direct_download')}"
    )
    print(f"  需要合并: {urls.get('needs_merge')}")

    # 4. 下载测试（只下载 10 秒）
    print("\n[4/6] 下载测试 (10 秒片段)")
    output_dir = "/tmp/video_analysis/arch_test"
    os.makedirs(output_dir, exist_ok=True)
    output_file = f"{output_dir}/test_{int(time.time())}.mp4"

    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "warning",
        "-stats",
        "-t",
        "10",  # 只下载 10 秒
        "-i",
        urls["video_url"],
    ]

    if urls.get("audio_url"):
        cmd.extend(["-t", "10", "-i", urls["audio_url"]])
        cmd.extend(["-c", "copy", "-map", "0:v:0", "-map", "1:a:0"])
    else:
        cmd.extend(["-c", "copy"])

    cmd.append(output_file)

    # 设置代理
    env = os.environ.copy()
    if settings.http_proxy:
        env["http_proxy"] = settings.http_proxy
        env["https_proxy"] = settings.http_proxy
        print(f"  使用代理: {settings.http_proxy}")
    else:
        print("  直连下载")

    start_time = time.time()
    result = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=120)
    download_time = time.time() - start_time

    if result.returncode != 0 or not os.path.exists(output_file):
        print(f"  ❌ 下载失败: {result.stderr[:200]}")
        return

    file_size = os.path.getsize(output_file) / 1024 / 1024
    speed = file_size / download_time

    print(f"  文件大小: {file_size:.2f} MB")
    print(f"  下载耗时: {download_time:.2f}s")
    print(f"  下载速度: {speed:.2f} MB/s")

    # 5. 验证视频
    print("\n[5/6] 视频验证")
    probe_result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,codec_name",
            "-of",
            "json",
            output_file,
        ],
        capture_output=True,
        text=True,
    )

    if probe_result.returncode == 0:
        probe_data = json.loads(probe_result.stdout)
        if probe_data.get("streams"):
            s = probe_data["streams"][0]
            print(f"  分辨率: {s.get('width')}x{s.get('height')}")
            print(f"  编码: {s.get('codec_name')}")

    # 6. 清理
    print("\n[6/6] 清理")
    os.remove(output_file)
    print("  已删除测试文件")

    # 总结
    print("\n" + "=" * 70)
    print("测试总结")
    print("=" * 70)
    print(f"  URL 提取: {extract_time:.2f}s")
    print(f"  下载速度: {speed:.2f} MB/s")

    if speed < 0.5:
        print("\n  ⚠️ 下载速度较慢，可能原因:")
        print("     - 代理带宽限制")
        print("     - YouTube 限速")
        print("     - 网络不稳定")
        print("\n  建议: 部署到新加坡服务器后直连，速度会更快")
    else:
        print("\n  ✅ 下载速度正常")

    # IP 一致性分析
    print("\n  IP 一致性:")
    if auth_bundle and auth_bundle.browser_ip:
        if auth_bundle.browser_ip == proxy_ip:
            print(f"     ✅ AgentGo IP = 代理 IP ({proxy_ip})")
        else:
            print(
                f"     ⚠️ AgentGo IP ({auth_bundle.browser_ip}) ≠ 代理 IP ({proxy_ip})"
            )
            print("        当前能工作是因为 android_sdkless client 对 IP 不敏感")

    print("\n  部署建议:")
    print("     新加坡服务器: 直连 YouTube，无需代理，IP 自然一致")


if __name__ == "__main__":
    video_url = "https://www.youtube.com/watch?v=-aDkQH185FI"
    resolution = "720"

    if len(sys.argv) > 1:
        video_url = sys.argv[1]
    if len(sys.argv) > 2:
        resolution = sys.argv[2]

    asyncio.run(test_architecture(video_url, resolution))
