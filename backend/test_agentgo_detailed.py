#!/usr/bin/env python3
"""
AgentGo详细诊断脚本
深入检查AgentGo连接问题
"""
import asyncio
import sys
import json
import aiohttp
sys.path.append('.')

from app.config import settings


async def test_agentgo_api_directly():
    """直接测试AgentGo API连接"""
    print("=== AgentGo API直接连接测试 ===\n")
    
    api_key = settings.agentgo_api_key
    api_url = settings.agentgo_api_url
    
    print(f"API URL: {api_url}")
    print(f"API Key: {api_key[:20]}..." if api_key else "API Key: 未设置")
    
    if not api_key:
        print("❌ API Key未设置")
        return False
    
    # 测试API连接
    try:
        async with aiohttp.ClientSession() as session:
            # 尝试连接到API端点
            test_url = f"{api_url}/health" if "/api" in api_url else f"{api_url}/api/health"
            
            print(f"\n1. 测试API健康检查: {test_url}")
            try:
                async with session.get(test_url, timeout=10) as response:
                    print(f"   状态码: {response.status}")
                    if response.status == 200:
                        print("   ✅ API健康检查成功")
                    else:
                        print(f"   ⚠️ API返回状态码: {response.status}")
            except Exception as e:
                print(f"   ❌ API健康检查失败: {e}")
            
            # 测试WebSocket端点
            print("\n2. 测试WebSocket连接能力")
            ws_url = "wss://app.browsers.live"
            print(f"   WebSocket URL: {ws_url}")
            
            # 构建连接参数
            options = {
                "_apikey": api_key,
                "_region": "us",
                "_disable_proxy": False
            }
            
            import urllib.parse
            url_option_value = urllib.parse.quote(json.dumps(options))
            full_ws_url = f"{ws_url}?launch-options={url_option_value}"
            
            print(f"   完整WebSocket URL长度: {len(full_ws_url)}")
            
            # 尝试WebSocket连接 (简单测试)
            try:
                import websockets
                print("   尝试WebSocket连接...")
                async with websockets.connect(full_ws_url, open_timeout=15, close_timeout=5) as websocket:
                    print("   ✅ WebSocket连接成功")
                    return True
            except Exception as e:
                print(f"   ❌ WebSocket连接失败: {e}")
                return False
                
    except Exception as e:
        print(f"❌ 网络连接测试失败: {e}")
        return False


async def test_playwright_basic():
    """测试Playwright基本功能"""
    print("\n=== Playwright基本功能测试 ===\n")
    
    try:
        from playwright.async_api import async_playwright
        print("✅ Playwright导入成功")
        
        async with async_playwright() as p:
            print("✅ Playwright上下文创建成功")
            
            # 测试本地浏览器启动
            try:
                browser = await p.chromium.launch(headless=True)
                print("✅ 本地Chromium启动成功")
                
                context = await browser.new_context()
                page = await context.new_page()
                
                # 测试简单导航
                await page.goto("https://httpbin.org/get", timeout=10000)
                print("✅ 基本网页导航成功")
                
                await browser.close()
                return True
                
            except Exception as e:
                print(f"❌ 本地浏览器测试失败: {e}")
                return False
                
    except ImportError as e:
        print(f"❌ Playwright导入失败: {e}")
        return False
    except Exception as e:
        print(f"❌ Playwright测试失败: {e}")
        return False


async def test_network_connectivity():
    """测试网络连接性"""
    print("\n=== 网络连接性测试 ===\n")
    
    test_urls = [
        "https://www.google.com",
        "https://www.youtube.com", 
        "https://httpbin.org/get",
        "https://api.datasea.network"
    ]
    
    async with aiohttp.ClientSession() as session:
        for url in test_urls:
            try:
                async with session.get(url, timeout=5) as response:
                    print(f"✅ {url}: {response.status}")
            except Exception as e:
                print(f"❌ {url}: {e}")


async def main():
    """主测试函数"""
    print("=== AgentGo详细诊断 ===\n")
    
    # 1. 网络连接测试
    await test_network_connectivity()
    
    # 2. Playwright基本测试
    playwright_ok = await test_playwright_basic()
    
    # 3. AgentGo API测试
    if playwright_ok:
        api_ok = await test_agentgo_api_directly()
        
        if api_ok:
            print("\n✅ 所有基础测试通过，AgentGo应该能正常工作")
        else:
            print("\n❌ AgentGo API连接有问题")
    else:
        print("\n❌ Playwright基础功能有问题")
    
    print("\n=== 诊断完成 ===")


if __name__ == "__main__":
    asyncio.run(main())