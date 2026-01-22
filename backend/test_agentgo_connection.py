#!/usr/bin/env python3
"""
AgentGo连接诊断脚本 - 改进版
测试AgentGo API连接和基本功能，包括详细的错误诊断
"""

import asyncio
import sys

sys.path.append(".")

from app.config import settings
from app.services.agentgo_service import get_agentgo_service


async def test_agentgo_connection():
    """测试AgentGo连接和基本功能"""
    print("=== AgentGo连接诊断 (改进版) ===\n")

    # 1. 检查配置
    print("1. 配置检查:")
    print(
        f"   API Key: {settings.agentgo_api_key[:20]}..."
        if settings.agentgo_api_key
        else "   API Key: 未设置"
    )
    print(f"   API URL: {settings.agentgo_api_url}")
    print(f"   YouTube Email: {settings.youtube_email}")
    print(
        f"   YouTube Password: {'*' * len(settings.youtube_password) if settings.youtube_password else '未设置'}"
    )

    service = get_agentgo_service()
    print(f"   is_api_configured(): {service.is_api_configured()}")
    print(f"   is_configured(): {service.is_configured()}")

    if not service.is_api_configured():
        print("❌ AgentGo API未配置，无法继续测试")
        return

    print("✅ 配置检查通过\n")

    # 2. 测试认证bundle获取 (改进版)
    print("2. 测试认证bundle获取 (改进版):")
    try:
        print("   正在获取认证bundle (使用改进的导航策略)...")
        auth_bundle = await service.get_youtube_authentication_bundle(
            region="us", force_refresh=True
        )

        if auth_bundle:
            print("✅ 认证bundle获取成功!")
            print(f"   Region: {auth_bundle.region}")
            print(f"   Cookies: {len(auth_bundle.cookies)} 个")
            print(
                f"   PO Token: {'✅ 已获取' if auth_bundle.po_token else '❌ 未获取'}"
            )
            print(
                f"   Visitor Data: {'✅ 已获取' if auth_bundle.visitor_data else '❌ 未获取'}"
            )
            print(f"   Cookie File: {auth_bundle.cookie_file_path}")

            if auth_bundle.po_token:
                print(f"   PO Token (前20字符): {auth_bundle.po_token[:20]}...")
                print(
                    f"   PO Token (格式化): {auth_bundle.get_formatted_po_token()[:25]}..."
                )
            if auth_bundle.visitor_data:
                print(f"   Visitor Data (前20字符): {auth_bundle.visitor_data[:20]}...")

            # 检查token质量
            if auth_bundle.has_tokens():
                print("✅ 成功获取到YouTube认证tokens!")
                print("   这应该能够解决YouTube 403错误问题")
            else:
                print("⚠️  只获取到cookies，没有获取到PO Token或Visitor Data")
                print("   可能仍会遇到YouTube 403错误")

        else:
            print("❌ 认证bundle获取失败")

    except Exception as e:
        print(f"❌ 认证bundle获取出错: {e}")
        import traceback

        traceback.print_exc()

    # 3. 测试yt-dlp配置生成
    print("\n3. 测试yt-dlp配置生成:")
    try:
        if auth_bundle and auth_bundle.has_tokens():
            from app.services.downloader import YouTubeDownloader

            downloader = YouTubeDownloader()

            # 测试token配置
            extractor_args = downloader.configure_with_tokens(auth_bundle)
            print("✅ yt-dlp配置生成成功!")
            print(f"   配置项数量: {len(extractor_args)}")

            if "youtube" in extractor_args:
                youtube_config = extractor_args["youtube"]
                print(f"   YouTube配置: {list(youtube_config.keys())}")

                if "po_token" in youtube_config:
                    print(f"   PO Token配置: {youtube_config['po_token'][:25]}...")
                if "visitor_data" in youtube_config:
                    print(
                        f"   Visitor Data配置: {youtube_config['visitor_data'][:20]}..."
                    )

        else:
            print("⚠️  无法测试yt-dlp配置 - 没有可用的tokens")

    except Exception as e:
        print(f"❌ yt-dlp配置测试失败: {e}")

    print("\n=== 诊断完成 ===")

    # 4. 提供解决建议
    print("\n4. 问题解决建议:")
    if auth_bundle and auth_bundle.has_tokens():
        print("✅ 系统配置正常，应该能够解决YouTube 403错误")
        print("   建议: 重启后端服务以应用最新的token提取改进")
    elif auth_bundle and auth_bundle.cookies:
        print("⚠️  部分功能正常，但token提取失败")
        print("   可能原因:")
        print("   - 网络连接问题 (代理设置冲突)")
        print("   - YouTube反爬虫机制")
        print("   - AgentGo服务限制")
        print("   建议: 检查网络设置，尝试不同的代理配置")
    else:
        print("❌ 系统配置有问题")
        print("   建议: 检查AgentGo API密钥和网络连接")


if __name__ == "__main__":
    asyncio.run(test_agentgo_connection())
