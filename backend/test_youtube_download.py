#!/usr/bin/env python3
"""
测试YouTube下载功能
使用当前的认证bundle（即使没有PO Token）
"""

import asyncio
import sys

sys.path.append(".")

from app.services.downloader import YouTubeDownloader
from app.services.agentgo_service import get_agentgo_service


async def test_youtube_download():
    """测试YouTube下载功能"""
    print("=== YouTube下载功能测试 ===\n")

    # 测试视频URL（一个简单的公开视频）
    test_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo" - 第一个YouTube视频

    print(f"测试视频: {test_url}")

    try:
        # 1. 获取认证bundle
        print("\n1. 获取认证bundle...")
        service = get_agentgo_service()
        auth_bundle = await service.get_youtube_authentication_bundle(region="us")

        if auth_bundle:
            print("✅ 认证bundle获取成功")
            print(f"   Cookies: {len(auth_bundle.cookies)} 个")
            print(f"   PO Token: {'✅' if auth_bundle.po_token else '❌'}")
            print(f"   Visitor Data: {'✅' if auth_bundle.visitor_data else '❌'}")
        else:
            print("❌ 认证bundle获取失败")
            return

        # 2. 创建下载器并配置认证
        print("\n2. 配置下载器...")
        downloader = YouTubeDownloader(region="us")
        downloader.set_authentication_bundle(auth_bundle)

        # 3. 测试视频信息提取（不实际下载）
        print("\n3. 测试视频信息提取...")

        import yt_dlp

        # 配置yt-dlp
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
        }

        # 添加cookies
        if auth_bundle.cookie_file_path:
            ydl_opts["cookiefile"] = auth_bundle.cookie_file_path
            print(f"   使用cookie文件: {auth_bundle.cookie_file_path}")

        # 添加tokens（如果有）
        if auth_bundle.has_tokens():
            extractor_args = downloader.configure_with_tokens(auth_bundle)
            ydl_opts["extractor_args"] = extractor_args
            print(f"   配置了tokens: {list(extractor_args.get('youtube', {}).keys())}")
        else:
            print("   仅使用cookies认证")

        # 尝试提取视频信息
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(test_url, download=False)

                print("✅ 视频信息提取成功!")
                print(f"   标题: {info.get('title', 'N/A')}")
                print(f"   时长: {info.get('duration', 'N/A')}秒")
                print(f"   上传者: {info.get('uploader', 'N/A')}")
                print(f"   可用格式数量: {len(info.get('formats', []))}")

                # 检查是否有高质量格式
                formats = info.get("formats", [])
                if formats:
                    best_format = max(formats, key=lambda f: f.get("height", 0) or 0)
                    print(f"   最高分辨率: {best_format.get('height', 'N/A')}p")

                return True

            except Exception as e:
                print(f"❌ 视频信息提取失败: {e}")

                # 检查是否是403错误
                if "403" in str(e):
                    print("   这是403 Forbidden错误 - 需要PO Token")
                    print("   建议: 检查网络连接，确保能访问YouTube")
                elif "Sign in to confirm your age" in str(e):
                    print("   这是年龄验证错误 - 视频需要登录")
                elif "Private video" in str(e):
                    print("   这是私有视频错误")
                else:
                    print(f"   其他错误: {type(e).__name__}")

                return False

    except Exception as e:
        print(f"❌ 测试过程中出错: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """主函数"""
    success = await test_youtube_download()

    print("\n=== 测试结果 ===")
    if success:
        print("✅ YouTube下载功能正常工作!")
        print("   系统能够成功提取视频信息，应该能够下载视频")
    else:
        print("❌ YouTube下载功能存在问题")
        print("   可能需要PO Token来访问某些视频")

    print("\n建议:")
    print("- 如果测试成功，系统应该能处理大部分YouTube视频")
    print("- 如果遇到403错误，可能需要解决网络连接问题以获取PO Token")
    print("- 可以尝试重启后端服务来应用最新的改进")


if __name__ == "__main__":
    asyncio.run(main())
