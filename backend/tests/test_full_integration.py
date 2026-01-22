#!/usr/bin/env python3
"""
Complete integration test: AgentGo Proxy + YouTube Cookies + yt-dlp

This script tests the full architecture:
1. Verify AgentGo service connectivity
2. Use AgentGo Scrape API to access YouTube (with built-in proxy)
3. Test yt-dlp extraction with various configurations

Test Strategy:
- Test 1: Direct yt-dlp (baseline - usually fails due to bot detection)
- Test 2: yt-dlp with cookies only
- Test 3: yt-dlp with local proxy
- Test 4: yt-dlp with cookies + proxy
- Test 5: AgentGo Scrape API for YouTube access verification

Usage:
    # Set environment
    export AGENTGO_API_KEY=your_api_key
    
    # Run all tests
    python tests/test_full_integration.py
    
    # Run with proxy
    python tests/test_full_integration.py --proxy http://127.0.0.1:33210
"""

import asyncio
import aiohttp
import os
import sys
import time
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))


@dataclass
class TestResult:
    """Result of a single test."""
    name: str
    success: bool
    duration_ms: float
    details: Dict[str, Any]
    error: Optional[str] = None


# ============================================================================
# AgentGo Client
# ============================================================================

class AgentGoClient:
    """AgentGo API client for Scrape and browser sessions."""
    
    SCRAPE_API = "https://app.agentgo.live/api/scrape"
    TASK_API = "https://app.agentgo.live/api/scrape"  # For checking task status
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "x-api-key": api_key,
            "Content-Type": "application/json"
        }
    
    async def scrape_youtube(self, video_url: str, region: str = "us") -> Dict[str, Any]:
        """
        Use AgentGo Scrape API to access YouTube.
        
        This tests whether AgentGo's proxy can access YouTube without bot detection.
        """
        payload = {
            "url": video_url,
            "waitTime": 5000,
            "region": region,
            "screenshot": False,
            "extract": {
                "title": "meta[property='og:title']@content",
                "description": "meta[property='og:description']@content",
                "image": "meta[property='og:image']@content",
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                self.SCRAPE_API,
                headers=self.headers,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=60)
            ) as response:
                result = await response.json()
                return {
                    "status_code": response.status,
                    "success": response.status == 200 and result.get("success", False),
                    "data": result
                }
    
    async def check_connectivity(self) -> Tuple[bool, str]:
        """Check if AgentGo API is accessible."""
        try:
            async with aiohttp.ClientSession() as session:
                # Try a simple scrape request
                async with session.post(
                    self.SCRAPE_API,
                    headers=self.headers,
                    json={"url": "https://example.com", "waitTime": 1000},
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    if response.status == 200:
                        return True, "API accessible"
                    elif response.status == 401:
                        return False, "Invalid API key"
                    else:
                        text = await response.text()
                        return False, f"HTTP {response.status}: {text[:100]}"
        except Exception as e:
            return False, f"Connection error: {e}"


# ============================================================================
# yt-dlp Extractor
# ============================================================================

class YtdlpExtractor:
    """YouTube video extractor using yt-dlp."""
    
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
    
    def __init__(
        self,
        cookie_file: Optional[str] = None,
        proxy: Optional[str] = None
    ):
        self.cookie_file = cookie_file
        self.proxy = proxy
    
    async def extract(self, video_url: str) -> TestResult:
        """Extract video info using yt-dlp."""
        try:
            import yt_dlp
        except ImportError:
            return TestResult(
                name="yt-dlp",
                success=False,
                duration_ms=0,
                details={},
                error="yt-dlp not installed"
            )
        
        start = time.time()
        
        opts = {
            'noplaylist': True,
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'geo_bypass': True,
            'geo_bypass_country': 'US',
            'no_cache_dir': True,
            'http_headers': {
                'User-Agent': self.USER_AGENT,
            },
            'extractor_args': {
                'youtube': {'player_client': ['ios', 'web']}
            }
        }
        
        if self.cookie_file and os.path.exists(self.cookie_file):
            opts['cookiefile'] = self.cookie_file
        
        if self.proxy:
            opts['proxy'] = self.proxy
        
        loop = asyncio.get_event_loop()
        
        def do_extract():
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(video_url, download=False)
        
        try:
            info = await loop.run_in_executor(None, do_extract)
            duration_ms = (time.time() - start) * 1000
            
            # Get download URL
            download_url = None
            for fmt in reversed(info.get('formats', [])):
                if fmt.get('url') and fmt.get('vcodec') != 'none':
                    download_url = fmt.get('url')
                    break
            
            return TestResult(
                name="yt-dlp",
                success=True,
                duration_ms=duration_ms,
                details={
                    "title": info.get('title'),
                    "duration": info.get('duration'),
                    "formats": len(info.get('formats', [])),
                    "has_url": bool(download_url),
                    "url_preview": download_url[:80] if download_url else None,
                    "used_cookies": bool(self.cookie_file),
                    "used_proxy": bool(self.proxy),
                }
            )
            
        except Exception as e:
            duration_ms = (time.time() - start) * 1000
            error_str = str(e).lower()
            
            # Categorize error
            if any(kw in error_str for kw in ['sign in', 'bot', 'captcha']):
                error_type = "bot_detection"
            elif 'proxy' in error_str or 'connection' in error_str:
                error_type = "network_error"
            else:
                error_type = "extraction_error"
            
            return TestResult(
                name="yt-dlp",
                success=False,
                duration_ms=duration_ms,
                details={
                    "error_type": error_type,
                    "used_cookies": bool(self.cookie_file),
                    "used_proxy": bool(self.proxy),
                },
                error=str(e)[:200]
            )


# ============================================================================
# Main Test Runner
# ============================================================================

async def run_tests(
    api_key: Optional[str] = None,
    cookie_file: Optional[str] = None,
    proxy: Optional[str] = None,
    video_url: str = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
):
    """Run all integration tests."""
    
    results: List[TestResult] = []
    
    print("=" * 70)
    print("YouTube Download Integration Test")
    print("=" * 70)
    print(f"Time: {datetime.now().isoformat()}")
    print(f"Video: {video_url}")
    print(f"Cookie file: {cookie_file or 'Not provided'}")
    print(f"Proxy: {proxy or 'Not configured'}")
    print(f"AgentGo API: {'Configured' if api_key else 'Not configured'}")
    print("=" * 70)
    
    # Test 1: Direct yt-dlp (no cookies, no proxy)
    print("\n[Test 1] Direct yt-dlp (baseline)...")
    extractor = YtdlpExtractor()
    result = await extractor.extract(video_url)
    result.name = "Direct yt-dlp (no cookies/proxy)"
    results.append(result)
    print(f"  {'✓ PASS' if result.success else '✗ FAIL'} ({result.duration_ms:.0f}ms)")
    if result.error:
        print(f"  Error: {result.error[:80]}...")
    
    # Test 2: yt-dlp with cookies only
    if cookie_file and os.path.exists(cookie_file):
        print("\n[Test 2] yt-dlp with cookies...")
        extractor = YtdlpExtractor(cookie_file=cookie_file)
        result = await extractor.extract(video_url)
        result.name = "yt-dlp with cookies"
        results.append(result)
        print(f"  {'✓ PASS' if result.success else '✗ FAIL'} ({result.duration_ms:.0f}ms)")
        if result.success:
            print(f"  Title: {result.details.get('title')}")
            print(f"  Formats: {result.details.get('formats')}")
        elif result.error:
            print(f"  Error: {result.error[:80]}...")
    else:
        print("\n[Test 2] yt-dlp with cookies... SKIPPED (no cookie file)")
    
    # Test 3: yt-dlp with proxy only
    if proxy:
        print("\n[Test 3] yt-dlp with proxy...")
        extractor = YtdlpExtractor(proxy=proxy)
        result = await extractor.extract(video_url)
        result.name = "yt-dlp with proxy"
        results.append(result)
        print(f"  {'✓ PASS' if result.success else '✗ FAIL'} ({result.duration_ms:.0f}ms)")
        if result.error:
            print(f"  Error: {result.error[:80]}...")
    else:
        print("\n[Test 3] yt-dlp with proxy... SKIPPED (no proxy configured)")
    
    # Test 4: yt-dlp with cookies + proxy
    if cookie_file and os.path.exists(cookie_file) and proxy:
        print("\n[Test 4] yt-dlp with cookies + proxy...")
        extractor = YtdlpExtractor(cookie_file=cookie_file, proxy=proxy)
        result = await extractor.extract(video_url)
        result.name = "yt-dlp with cookies + proxy"
        results.append(result)
        print(f"  {'✓ PASS' if result.success else '✗ FAIL'} ({result.duration_ms:.0f}ms)")
        if result.success:
            print(f"  Title: {result.details.get('title')}")
            print(f"  Has URL: {result.details.get('has_url')}")
        elif result.error:
            print(f"  Error: {result.error[:80]}...")
    else:
        print("\n[Test 4] yt-dlp with cookies + proxy... SKIPPED")
    
    # Test 5: AgentGo Scrape API
    if api_key:
        print("\n[Test 5] AgentGo Scrape API (YouTube access test)...")
        client = AgentGoClient(api_key)
        
        # First check connectivity
        ok, msg = await client.check_connectivity()
        if not ok:
            print(f"  ✗ AgentGo API not accessible: {msg}")
            results.append(TestResult(
                name="AgentGo Scrape API",
                success=False,
                duration_ms=0,
                details={},
                error=msg
            ))
        else:
            start = time.time()
            try:
                response = await client.scrape_youtube(video_url)
                duration_ms = (time.time() - start) * 1000
                
                success = response.get("success", False)
                data = response.get("data", {})
                
                result = TestResult(
                    name="AgentGo Scrape API",
                    success=success,
                    duration_ms=duration_ms,
                    details={
                        "status_code": response.get("status_code"),
                        "has_data": bool(data),
                        "task_id": data.get("data", {}).get("taskId"),
                    }
                )
                results.append(result)
                
                print(f"  {'✓ PASS' if success else '✗ FAIL'} ({duration_ms:.0f}ms)")
                if data.get("data", {}).get("taskId"):
                    print(f"  Task ID: {data['data']['taskId']}")
                    print("  Note: Scrape API returns async task. Result available via task status API.")
                    
            except Exception as e:
                print(f"  ✗ Error: {e}")
                results.append(TestResult(
                    name="AgentGo Scrape API",
                    success=False,
                    duration_ms=0,
                    details={},
                    error=str(e)
                ))
    else:
        print("\n[Test 5] AgentGo Scrape API... SKIPPED (no API key)")
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    
    passed = sum(1 for r in results if r.success)
    total = len(results)
    
    for result in results:
        status = "✓" if result.success else "✗"
        print(f"  {status} {result.name}: {result.duration_ms:.0f}ms")
        if result.error and not result.success:
            print(f"      Error: {result.error[:60]}...")
    
    print(f"\nResult: {passed}/{total} tests passed")
    print("=" * 70)
    
    # Recommendations
    print("\nRECOMMENDATIONS:")
    
    direct_failed = any(r.name == "Direct yt-dlp (no cookies/proxy)" and not r.success for r in results)
    cookies_passed = any(r.name == "yt-dlp with cookies" and r.success for r in results)
    proxy_passed = any("proxy" in r.name.lower() and r.success for r in results)
    
    if direct_failed:
        print("  - Direct access blocked (expected). Need cookies and/or proxy.")
    
    if cookies_passed:
        print("  - Cookies authentication is working!")
        print("  - Architecture: AgentGo cookies + yt-dlp is viable.")
    else:
        print("  - Cookies not working or not available.")
        print("  - Need to obtain fresh cookies via AgentGo login.")
    
    if proxy_passed:
        print("  - Proxy is helping bypass restrictions.")
    
    if not (cookies_passed or proxy_passed) and direct_failed:
        print("  - ACTION NEEDED: Run AgentGo login to get fresh YouTube cookies.")
        print("  - Alternatively, configure a working proxy (YOUTUBE_PROXY env var).")
    
    print("=" * 70)
    
    return results


def main():
    parser = argparse.ArgumentParser(description="YouTube Download Integration Test")
    parser.add_argument("--cookies", help="Path to cookie file")
    parser.add_argument("--proxy", help="Proxy URL (http://host:port)")
    parser.add_argument("--video", default="https://www.youtube.com/watch?v=jNQXAC9IVRw",
                       help="YouTube video URL to test")
    
    args = parser.parse_args()
    
    # Load environment
    env_file = Path(__file__).parent.parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ.setdefault(key.strip(), value.strip())
    
    api_key = os.getenv("AGENTGO_API_KEY")
    cookie_file = args.cookies or "/tmp/youtube_cookies.txt"
    proxy = args.proxy or os.getenv("YOUTUBE_PROXY") or os.getenv("https_proxy")
    
    asyncio.run(run_tests(
        api_key=api_key,
        cookie_file=cookie_file,
        proxy=proxy,
        video_url=args.video
    ))


if __name__ == "__main__":
    main()
