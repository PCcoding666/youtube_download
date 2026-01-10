#!/usr/bin/env python3
"""
直接测试 token 提取逻辑
"""
import asyncio
import sys
import json
import urllib.parse
sys.path.append('.')

from app.config import settings
from app.services.agentgo_service import TokenExtractor


async def test_token_extraction():
    """测试 token 提取"""
    print("=== Token 提取测试 ===\n")
    
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        print("❌ Playwright 未安装")
        return False
    
    api_key = settings.agentgo_api_key
    if not api_key:
        print("❌ AGENTGO_API_KEY 未设置")
        return False
    
    # 构建 WebSocket URL
    ws_url = "wss://app.browsers.live"
    options = {
        "_apikey": api_key,
        "_region": "us",
        "_disable_proxy": False
    }
    url_option_value = urllib.parse.quote(json.dumps(options))
    full_ws_url = f"{ws_url}?launch-options={url_option_value}"
    
    print(f"连接到 AgentGo 浏览器...")
    
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect(full_ws_url, timeout=60000)
            print("✅ 成功连接到 AgentGo 浏览器")
            
            context = await browser.new_context()
            page = await context.new_page()
            
            # 先导航到 YouTube 视频页面
            print("\n1. 导航到 YouTube 视频页面...")
            video_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
            await page.goto(video_url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)
            
            title = await page.title()
            print(f"   页面标题: {title}")
            
            # 直接测试 JavaScript 提取
            print("\n2. 直接测试 JavaScript 提取...")
            
            # 方法 1: 简单的 ytcfg.get
            print("\n   2a. 测试 ytcfg.get('VISITOR_DATA')...")
            visitor_data_1 = await page.evaluate('''
                () => {
                    if (window.ytcfg && typeof window.ytcfg.get === 'function') {
                        return window.ytcfg.get('VISITOR_DATA');
                    }
                    return null;
                }
            ''')
            if visitor_data_1:
                print(f"   ✅ 成功 (长度: {len(visitor_data_1)})")
            else:
                print("   ❌ 失败")
            
            # 方法 2: ytcfg.data_
            print("\n   2b. 测试 ytcfg.data_.VISITOR_DATA...")
            visitor_data_2 = await page.evaluate('''
                () => {
                    if (window.ytcfg && window.ytcfg.data_ && window.ytcfg.data_.VISITOR_DATA) {
                        return window.ytcfg.data_.VISITOR_DATA;
                    }
                    return null;
                }
            ''')
            if visitor_data_2:
                print(f"   ✅ 成功 (长度: {len(visitor_data_2)})")
            else:
                print("   ❌ 失败")
            
            # 方法 3: 检查 ytcfg 是否存在
            print("\n   2c. 检查 ytcfg 对象...")
            ytcfg_info = await page.evaluate('''
                () => {
                    return {
                        ytcfg_exists: typeof window.ytcfg !== 'undefined',
                        ytcfg_get_exists: typeof window.ytcfg?.get === 'function',
                        ytcfg_data_exists: typeof window.ytcfg?.data_ !== 'undefined',
                        keys: window.ytcfg?.data_ ? Object.keys(window.ytcfg.data_).slice(0, 10) : []
                    };
                }
            ''')
            print(f"   ytcfg 存在: {ytcfg_info.get('ytcfg_exists')}")
            print(f"   ytcfg.get 存在: {ytcfg_info.get('ytcfg_get_exists')}")
            print(f"   ytcfg.data_ 存在: {ytcfg_info.get('ytcfg_data_exists')}")
            print(f"   部分 keys: {ytcfg_info.get('keys')}")
            
            # 测试 TokenExtractor
            print("\n3. 使用 TokenExtractor 提取...")
            extractor = TokenExtractor()
            
            # 测试简化的 visitor data 提取
            print("\n   3a. 测试 _extract_visitor_data_js_only...")
            visitor_data = await extractor._extract_visitor_data_js_only(page)
            if visitor_data:
                print(f"   ✅ Visitor Data 提取成功 (长度: {len(visitor_data)})")
            else:
                print("   ❌ Visitor Data 提取失败")
            
            await browser.close()
            print("\n✅ 测试完成")
            return True
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
            return False


if __name__ == "__main__":
    asyncio.run(test_token_extraction())
