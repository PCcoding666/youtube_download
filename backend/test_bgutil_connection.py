#!/usr/bin/env python3
"""Test bgutil PO Token provider connection and yt-dlp integration."""
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import requests
import yt_dlp


def test_bgutil_server():
    """Test if bgutil server is reachable."""
    bgutil_url = os.environ.get('BGUTIL_URL', 'http://127.0.0.1:4416')
    print(f"\n=== Testing bgutil server at {bgutil_url} ===")
    
    try:
        response = requests.get(f"{bgutil_url}/ping", timeout=5)
        if response.status_code == 200:
            data = response.json()
            print(f"✅ bgutil server is running (version: {data.get('version')})")
            return True
        else:
            print(f"❌ bgutil server returned status {response.status_code}")
            return False
    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to bgutil server at {bgutil_url}")
        return False
    except Exception as e:
        print(f"❌ Error connecting to bgutil: {e}")
        return False


def test_get_po_token():
    """Test fetching PO Token from bgutil server."""
    bgutil_url = os.environ.get('BGUTIL_URL', 'http://127.0.0.1:4416')
    print(f"\n=== Testing PO Token fetch from {bgutil_url} ===")
    
    try:
        response = requests.post(
            f"{bgutil_url}/get_pot",
            json={'bypass_cache': False, 'disable_innertube': True},
            headers={'Content-Type': 'application/json'},
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"❌ Server returned status {response.status_code}")
            return None
        
        data = response.json()
        if 'error' in data:
            print(f"❌ Server error: {data['error']}")
            return None
        
        po_token = data.get('poToken')
        if po_token:
            print(f"✅ Got PO Token (length: {len(po_token)})")
            print(f"   Token preview: {po_token[:50]}...")
            return po_token
        else:
            print("❌ No poToken in response")
            return None
            
    except Exception as e:
        print(f"❌ Error fetching PO Token: {e}")
        return None


def test_ytdlp_with_po_token(po_token: str):
    """Test yt-dlp with manually provided PO Token."""
    proxy = os.environ.get('HTTP_PROXY') or os.environ.get('YOUTUBE_PROXY')
    
    print("\n=== Testing yt-dlp with PO Token ===")
    print(f"Proxy: {proxy or 'None'}")
    
    # Test video URL
    test_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"  # "Me at the zoo" - first YouTube video
    
    # po_token format: CLIENT.CONTEXT+TOKEN (as a list)
    po_token_config = f'mweb.gvs+{po_token}'
    
    opts = {
        'quiet': False,
        'no_warnings': False,
        'skip_download': True,
        'format': 'best',
        'extractor_args': {
            'youtube': {
                'player_client': ['mweb', 'web'],
                'po_token': [po_token_config],  # Must be a list!
            }
        }
    }
    
    if proxy:
        opts['proxy'] = proxy
        print(f"Using proxy: {proxy}")
    
    print(f"PO Token config: {po_token_config[:60]}...")
    
    try:
        print(f"\nExtracting info from: {test_url}")
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(test_url, download=False)
            
        print("\n✅ Successfully extracted video info!")
        print(f"   Title: {info.get('title')}")
        print(f"   Duration: {info.get('duration')}s")
        print(f"   Uploader: {info.get('uploader')}")
        print(f"   Formats available: {len(info.get('formats', []))}")
        return True
        
    except Exception as e:
        error_msg = str(e)
        print(f"\n❌ yt-dlp extraction failed: {error_msg}")
        
        if 'Sign in to confirm' in error_msg or 'not a bot' in error_msg:
            print("\n⚠️  Bot detection triggered!")
            print("   The PO Token may not be working correctly.")
        
        return False


def main():
    print("=" * 60)
    print("bgutil PO Token Provider Test (Direct HTTP)")
    print("=" * 60)
    
    # Test 1: bgutil server connection
    server_ok = test_bgutil_server()
    
    if not server_ok:
        print("\n⚠️  bgutil server is not running!")
        print("   Start it with: docker run -d -p 4416:4416 brainicism/bgutil-ytdlp-pot-provider")
        print("   Or use docker-compose: docker-compose up -d bgutil")
        return 1
    
    # Test 2: Fetch PO Token
    po_token = test_get_po_token()
    
    if not po_token:
        print("\n⚠️  Failed to get PO Token from bgutil server")
        return 1
    
    # Test 3: yt-dlp with PO Token
    ytdlp_ok = test_ytdlp_with_po_token(po_token)
    
    print("\n" + "=" * 60)
    print("Test Results:")
    print("  bgutil server: ✅ OK")
    print("  PO Token fetch: ✅ OK")
    print(f"  yt-dlp + PO Token: {'✅ OK' if ytdlp_ok else '❌ FAILED'}")
    print("=" * 60)
    
    return 0 if ytdlp_ok else 1


if __name__ == "__main__":
    sys.exit(main())
