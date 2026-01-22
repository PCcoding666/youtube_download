#!/usr/bin/env python3
"""
测试 AgentGo 浏览器访问 YouTube 的能力
"""
import asyncio
import sys
import json
import urllib.parse
sys.path.append('.')

from app.config import settings


async def test_agentgo_youtube_access():
    """测试 AgentGo 浏览器能否访问 YouTube"""
    print("=== AgentGo YouTube 访问测试 ===\n")
    
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("❌ Playwright 未安装")
        return False
    
    api_key = settings.agentgo_api_key
    if not api_key:
        print("❌ AGENTGO_API_KEY 未设置")
        return False
    
    print(f"API Key: {api_key[:20]}...")
    
    # 构建 WebSocket URL
    ws_url = "wss://app.browsers.live"
    options = {
        "_apikey": api_key,
        "_region": "us",
        "_disable_proxy": False
    }
    url_option_value = urllib.parse.quote(json.dumps(options))
    full_ws_url = f"{ws_url}?launch-options={url_option_value}"
    
    print("连接到 AgentGo 浏览器 (region: us)...")
    
    async with async_playwright() as p:
        try:
            # 连接到 AgentGo 远程浏览器 (使用 Playwright 协议)
            try:
                browser = await p.chromium.connect(full_ws_url, timeout=60000)
                print("✅ 成功连接到 AgentGo 浏览器 (Playwright 协议)")
            except Exception as e:
                print(f"   Playwright 协议连接失败: {e}")
                print("   尝试 CDP 协议...")
                browser = await p.chromium.connect_over_cdp(full_ws_url, timeout=60000)
                print("✅ 成功连接到 AgentGo 浏览器 (CDP 协议)")
            
            # 获取浏览器 IP
            context = await browser.new_context()
            page = await context.new_page()
            
            print("\n1. 检查浏览器 IP...")
            try:
                await page.goto("https://httpbin.org/ip", timeout=30000)
                await asyncio.sleep(1)
                ip_text = await page.inner_text("body")
                ip_data = json.loads(ip_text)
                print(f"   浏览器 IP: {ip_data.get('origin', 'unknown')}")
            except Exception as e:
                print(f"   ❌ 获取 IP 失败: {e}")
            
            print("\n2. 测试访问 YouTube...")
            try:
                # 先尝试访问 YouTube 首页
                await page.goto("https://www.youtube.com", wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(3)
                
                title = await page.title()
                print(f"   页面标题: {title}")
                
                # 检查是否被阻止
                content = await page.content()
                if "blocked" in content.lower() or "access denied" in content.lower():
                    print("   ⚠️ YouTube 访问可能被阻止")
                elif "youtube" in title.lower():
                    print("   ✅ YouTube 首页访问成功!")
                else:
                    print(f"   ⚠️ 页面可能不是 YouTube (标题: {title})")
                
            except Exception as e:
                print(f"   ❌ YouTube 访问失败: {e}")
                
                # 尝试截图保存错误页面
                try:
                    await page.screenshot(path="/tmp/youtube_error.png")
                    print("   已保存错误截图到 /tmp/youtube_error.png")
                except:
                    pass
            
            print("\n3. 测试访问 YouTube 视频页面...")
            try:
                video_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
                await page.goto(video_url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(3)
                
                title = await page.title()
                print(f"   页面标题: {title}")
                
                if "me at the zoo" in title.lower() or "youtube" in title.lower():
                    print("   ✅ YouTube 视频页面访问成功!")
                    
                    # 尝试提取 visitor data
                    visitor_data = await page.evaluate('''
                        () => {
                            if (window.ytcfg && typeof window.ytcfg.get === 'function') {
                                return window.ytcfg.get('VISITOR_DATA');
                            }
                            return null;
                        }
                    ''')
                    
                    if visitor_data:
                        print(f"   ✅ Visitor Data 提取成功 (长度: {len(visitor_data)})")
                    else:
                        print("   ⚠️ Visitor Data 未找到")
                else:
                    print("   ⚠️ 可能不是预期的视频页面")
                    
            except Exception as e:
                print(f"   ❌ 视频页面访问失败: {e}")
            
            print("\n4. 提取 Cookies...")
            try:
                cookies = await context.cookies()
                youtube_cookies = [c for c in cookies if "youtube" in c.get("domain", "")]
                print(f"   获取到 {len(youtube_cookies)} 个 YouTube cookies")
                
                if youtube_cookies:
                    for cookie in youtube_cookies[:5]:
                        print(f"   - {cookie['name']}: {cookie['value'][:20]}...")
            except Exception as e:
                print(f"   ❌ Cookie 提取失败: {e}")
            
            await browser.close()
            print("\n✅ 测试完成")
            return True
            
        except Exception as e:
            print(f"❌ AgentGo 连接失败: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    asyncio.run(test_agentgo_youtube_access())
