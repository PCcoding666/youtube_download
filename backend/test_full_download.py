#!/usr/bin/env python3
"""
完整下载测试 - 包含所有认证组件：
1. PO Token (bgutil server)
2. Visitor Data + Cookies (AgentGo)
3. 通过本地代理 (ClashX) 发请求
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
import yt_dlp
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


def get_po_token():
    """从 bgutil 获取 PO Token"""
    bgutil_url = os.environ.get('BGUTIL_URL', 'http://127.0.0.1:4416')
    print(f"\n[1] 获取 PO Token from {bgutil_url}")
    
    try:
        # 重要：访问 localhost 时不使用代理
        response = requests.post(
            f"{bgutil_url}/get_pot",
            json={'bypass_cache': False, 'disable_innertube': True},
            headers={'Content-Type': 'application/json'},
            timeout=30,
            proxies={'http': None, 'https': None}  # 禁用代理访问 localhost
        )
        
        if response.status_code == 200:
            data = response.json()
            po_token = data.get('poToken')
            if po_token:
                print(f"    ✅ PO Token 获取成功 (长度: {len(po_token)})")
                return po_token
        
        print(f"    ❌ 获取失败: {response.text}")
        return None
    except Exception as e:
        print(f"    ❌ 错误: {e}")
        return None


async def get_agentgo_auth():
    """从 AgentGo 获取 Visitor Data 和 Cookies"""
    print(f"\n[2] 获取 Visitor Data + Cookies from AgentGo")
    
    try:
        from app.services.agentgo_service import get_agentgo_service
        
        service = get_agentgo_service()
        
        if not service.is_configured():
            print("    ❌ AgentGo 未配置 (检查 AGENTGO_API_KEY)")
            return None, None
        
        print(f"    正在请求 AgentGo (region: us)...")
        auth_bundle = await service.get_youtube_authentication_bundle(
            force_refresh=True,
            region='us'
        )
        
        if not auth_bundle:
            print("    ❌ 获取认证失败")
            return None, None
        
        visitor_data = auth_bundle.visitor_data
        cookie_file = auth_bundle.cookie_file_path
        
        print(f"    ✅ Visitor Data: {visitor_data[:30] if visitor_data else 'None'}...")
        print(f"    ✅ Cookie File: {cookie_file}")
        
        return visitor_data, cookie_file
        
    except ImportError as e:
        print(f"    ❌ 导入错误: {e}")
        return None, None
    except Exception as e:
        print(f"    ❌ 错误: {e}")
        return None, None


def test_download(po_token, visitor_data, cookie_file):
    """使用完整认证测试下载"""
    proxy = os.environ.get('HTTP_PROXY', 'http://127.0.0.1:7890')
    
    print(f"\n[3] 测试 yt-dlp 下载")
    print(f"    Proxy: {proxy}")
    print(f"    PO Token: {'✅' if po_token else '❌'}")
    print(f"    Visitor Data: {'✅' if visitor_data else '❌'}")
    print(f"    Cookies: {'✅' if cookie_file else '❌'}")
    
    test_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    
    # 尝试不同的 client 策略
    strategies = [
        {
            'name': 'android_sdkless + web_safari',
            'player_client': ['android_sdkless', 'web_safari'],
        },
        {
            'name': 'tv_embedded',
            'player_client': ['tv_embedded'],
        },
        {
            'name': 'mweb with PO Token',
            'player_client': ['mweb'],
        },
    ]
    
    for strategy in strategies:
        print(f"\n    尝试策略: {strategy['name']}")
        
        # 构建 extractor_args
        youtube_args = {
            'player_client': strategy['player_client'],
        }
        
        # 只有 mweb/web 需要 PO Token
        if po_token and 'mweb' in strategy['player_client']:
            youtube_args['po_token'] = [f'mweb.gvs+{po_token}']
        
        if visitor_data:
            youtube_args['visitor_data'] = visitor_data
        
        opts = {
            'quiet': False,
            'no_warnings': False,
            'skip_download': True,
            'format': 'best[height<=720]',
            'proxy': proxy,
            'extractor_args': {
                'youtube': youtube_args
            }
        }
        
        if cookie_file and os.path.exists(cookie_file):
            opts['cookiefile'] = cookie_file
        
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(test_url, download=False)
            
            formats = info.get('formats', [])
            print(f"\n    ✅ 策略 '{strategy['name']}' 成功!")
            print(f"    标题: {info.get('title')}")
            print(f"    时长: {info.get('duration')}s")
            print(f"    可用格式数: {len(formats)}")
            
            if formats:
                print(f"\n    部分可用格式:")
                for f in formats[:5]:
                    res = f.get('height', 'audio')
                    ext = f.get('ext', '?')
                    vcodec = f.get('vcodec', 'none')[:10] if f.get('vcodec') else 'none'
                    print(f"      - {res}p {ext} ({vcodec})")
            
            return True
            
        except Exception as e:
            error_msg = str(e)
            print(f"    ❌ 策略失败: {error_msg[:100]}...")
            continue
    
    print(f"\n    ❌ 所有策略都失败了")
    return False


async def main():
    print("=" * 60)
    print("完整下载测试 (PO Token + Visitor Data + Cookies + Proxy)")
    print("=" * 60)
    
    # 1. 获取 PO Token
    po_token = get_po_token()
    
    # 2. 获取 AgentGo 认证
    visitor_data, cookie_file = await get_agentgo_auth()
    
    # 3. 测试下载
    success = test_download(po_token, visitor_data, cookie_file)
    
    print("\n" + "=" * 60)
    print("测试结果:")
    print(f"  PO Token: {'✅' if po_token else '❌'}")
    print(f"  Visitor Data: {'✅' if visitor_data else '❌'}")
    print(f"  Cookies: {'✅' if cookie_file else '❌'}")
    print(f"  下载测试: {'✅ 成功' if success else '❌ 失败'}")
    print("=" * 60)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
