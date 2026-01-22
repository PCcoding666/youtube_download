#!/usr/bin/env python3
"""
端到端下载测试 - 实际下载视频文件 (支持 1080p)
"""

import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
import yt_dlp
from dotenv import load_dotenv

load_dotenv()

OUTPUT_DIR = "/tmp/test_downloads"
TARGET_URL = "https://www.youtube.com/watch?v=1PaoWKvcJP0"


def get_po_token():
    """从 bgutil 获取 PO Token"""
    bgutil_url = os.environ.get("BGUTIL_URL", "http://127.0.0.1:4416")
    print("\n[1] 获取 PO Token...")

    try:
        response = requests.post(
            f"{bgutil_url}/get_pot",
            json={"bypass_cache": False, "disable_innertube": True},
            headers={"Content-Type": "application/json"},
            timeout=30,
            proxies={"http": None, "https": None},
        )

        if response.status_code == 200:
            data = response.json()
            po_token = data.get("poToken")
            if po_token:
                print("    ✅ PO Token 获取成功")
                return po_token
        return None
    except Exception as e:
        print(f"    ❌ 错误: {e}")
        return None


async def get_agentgo_auth():
    """从 AgentGo 获取认证"""
    print("\n[2] 获取 AgentGo 认证...")

    try:
        from app.services.agentgo_service import get_agentgo_service

        service = get_agentgo_service()
        if not service.is_configured():
            print("    ⚠️ AgentGo 未配置")
            return None, None

        auth_bundle = await service.get_youtube_authentication_bundle(
            force_refresh=True, region="us"
        )

        if auth_bundle:
            print("    ✅ Visitor Data + Cookies 获取成功")
            return auth_bundle.visitor_data, auth_bundle.cookie_file_path
        return None, None
    except Exception as e:
        print(f"    ❌ 错误: {e}")
        return None, None


def download_video(url, po_token, visitor_data, cookie_file, resolution="1080"):
    """实际下载视频 - 支持 1080p (需要合并视频+音频)"""
    proxy = os.environ.get("HTTP_PROXY", "http://127.0.0.1:7890")

    print(f"\n[3] 开始下载视频 ({resolution}p)...")
    print(f"    URL: {url}")
    print(f"    Proxy: {proxy}")
    print(f"    输出目录: {OUTPUT_DIR}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # 1080p 需要 mweb client + PO Token
    youtube_args = {
        "player_client": ["mweb", "web"],
    }

    if visitor_data:
        youtube_args["visitor_data"] = visitor_data

    if po_token:
        youtube_args["po_token"] = [f"mweb.gvs+{po_token}"]
        print("    使用 PO Token: ✅")

    def progress_hook(d):
        if d["status"] == "downloading":
            percent = d.get("_percent_str", "?%")
            speed = d.get("_speed_str", "?")
            print(f"\r    下载中: {percent} @ {speed}        ", end="", flush=True)
        elif d["status"] == "finished":
            print("\n    ✅ 片段下载完成")

    # 格式：1080p 视频 + 最佳音频
    format_str = (
        f"bestvideo[height<={resolution}]+bestaudio/best[height<={resolution}]/best"
    )

    opts = {
        "format": format_str,
        "proxy": proxy,
        "outtmpl": f"{OUTPUT_DIR}/%(id)s.%(ext)s",
        "progress_hooks": [progress_hook],
        "merge_output_format": "mp4",
        "extractor_args": {"youtube": youtube_args},
        # JavaScript runtime 配置
        "js_runtimes": {"node": {"path": "/opt/homebrew/bin/node"}},
        # 允许下载远程 JS challenge solver
        "remote_components": {"ejs:github"},
        "socket_timeout": 30,
        "retries": 5,
        "fragment_retries": 5,
    }

    if cookie_file and os.path.exists(cookie_file):
        opts["cookiefile"] = cookie_file

    start_time = time.time()

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

            if info.get("requested_downloads"):
                filename = info["requested_downloads"][0]["filepath"]
            else:
                filename = ydl.prepare_filename(info)
                if not os.path.exists(filename):
                    filename = filename.rsplit(".", 1)[0] + ".mp4"

        elapsed = time.time() - start_time

        if os.path.exists(filename):
            size_mb = os.path.getsize(filename) / (1024 * 1024)
            print("\n    ✅ 下载成功!")
            print(f"    文件: {filename}")
            print(f"    大小: {size_mb:.2f} MB")
            print(f"    耗时: {elapsed:.1f}s")
            print(f"    标题: {info.get('title', 'Unknown')}")
            print(f"    分辨率: {info.get('height', '?')}p")
            return filename
        else:
            for f in os.listdir(OUTPUT_DIR):
                if info.get("id") in f:
                    filepath = os.path.join(OUTPUT_DIR, f)
                    size_mb = os.path.getsize(filepath) / (1024 * 1024)
                    print("\n    ✅ 下载成功!")
                    print(f"    文件: {filepath}")
                    print(f"    大小: {size_mb:.2f} MB")
                    return filepath

            print("\n    ❌ 文件未找到")
            return None

    except Exception as e:
        print(f"\n    ❌ 下载失败: {e}")
        return None


async def main():
    url = TARGET_URL

    print("=" * 60)
    print("端到端下载测试 (1080p)")
    print("=" * 60)

    po_token = get_po_token()
    visitor_data, cookie_file = await get_agentgo_auth()
    result = download_video(url, po_token, visitor_data, cookie_file, resolution="1080")

    print("\n" + "=" * 60)
    if result:
        print(f"✅ 测试成功! 文件: {result}")
    else:
        print("❌ 测试失败")
    print("=" * 60)

    return 0 if result else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
