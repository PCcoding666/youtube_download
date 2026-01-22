"""
AgentGo Playwright Integration for YouTube Cookie Extraction.

This script:
1. Connects to AgentGo's cloud browser via Playwright CDP
2. Navigates to YouTube (uses AgentGo's built-in proxy)
3. Extracts cookies (for authenticated or anonymous sessions)
4. Saves cookies in Netscape format for yt-dlp
5. Tests yt-dlp extraction with the obtained cookies

Architecture:
    AgentGo Browser (with proxy) --> YouTube
           |
           v
    Playwright CDP --> Cookie Extraction
           |
           v
    yt-dlp (with cookies) --> Video URL Extraction

Usage:
    # Set environment variables
    export AGENTGO_API_KEY=your_api_key
    
    # Run the script
    python scripts/agentgo_get_cookies.py
    
    # Or with login (for full authentication)
    python scripts/agentgo_get_cookies.py --login
"""

import asyncio
import json
import os
import sys
import urllib.parse
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from playwright.async_api import async_playwright, Page
    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    print("[!] Playwright not installed. Some features may be limited.")



class AgentGoCookieExtractor:
    """
    Extract YouTube cookies using AgentGo's cloud browser.
    
    AgentGo provides:
    - Cloud browser with built-in proxy
    - Multiple geographic regions (us, uk, de, jp, etc.)
    - Playwright CDP endpoint for automation
    """
    
    # AgentGo WebSocket endpoint
    WS_ENDPOINT = "wss://app.browsers.live"
    
    # Default cookie save location
    COOKIE_FILE = "/tmp/youtube_cookies.txt"
    
    # Supported regions
    REGIONS = ['us', 'uk', 'de', 'fr', 'jp', 'sg', 'au', 'ca', 'in']
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        region: str = "us",
        cookie_file: Optional[str] = None
    ):
        self.api_key = api_key or os.getenv("AGENTGO_API_KEY", "")
        self.region = region.lower() if region in self.REGIONS else "us"
        self.cookie_file = cookie_file or self.COOKIE_FILE
        
        if not self.api_key:
            raise ValueError("AGENTGO_API_KEY is required")
    
    def _build_ws_url(self, session_id: Optional[str] = None) -> str:
        """Build WebSocket URL with launch options."""
        options = {
            "_apikey": self.api_key,
            "_region": self.region,
            "_disable_proxy": False,  # Keep proxy enabled for YouTube access
        }
        
        if session_id:
            options["_sessionId"] = session_id
        
        encoded = urllib.parse.quote(json.dumps(options))
        return f"{self.WS_ENDPOINT}?launch-options={encoded}"
    
    async def extract_cookies(
        self,
        login: bool = False,
        email: Optional[str] = None,
        password: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Connect to AgentGo and extract YouTube cookies.
        
        Args:
            login: Whether to perform YouTube login
            email: YouTube/Google email (required if login=True)
            password: YouTube/Google password (required if login=True)
            
        Returns:
            List of cookie dictionaries
        """
        ws_url = self._build_ws_url()
        print(f"[*] Connecting to AgentGo (region: {self.region})...")
        print(f"[*] WebSocket URL: {ws_url[:50]}...")
        
        async with async_playwright() as p:
            try:
                # Connect to AgentGo's browser via CDP
                browser = await p.chromium.connect_over_cdp(
                    ws_url,
                    timeout=60000  # 60 second timeout
                )
                
                print("[+] Connected to AgentGo browser!")
                
                # Get or create context
                contexts = browser.contexts
                if contexts:
                    context = contexts[0]
                    print("[*] Using existing browser context")
                else:
                    context = await browser.new_context()
                    print("[*] Created new browser context")
                
                # Create new page
                page = await context.new_page()
                
                # Navigate to YouTube video for better token extraction
                target_url = "https://www.youtube.com/watch?v=_MLwQUebJUc"
                print(f"[*] Navigating to YouTube video: {target_url}")
                await page.goto(target_url, wait_until="networkidle", timeout=60000)
                
                # Wait for page to fully load
                await asyncio.sleep(3)
                
                # Check current URL (might redirect based on region)
                current_url = page.url
                print(f"[*] Current URL: {current_url}")
                
                # Check if login is required and requested
                if login:
                    if not email or not password:
                        print("[!] Login requested but credentials not provided")
                    else:
                        await self._perform_login(page, email, password)
                
                # Extract cookies from context
                print("[*] Extracting cookies...")
                cookies = await context.cookies()
                
                # Filter for YouTube/Google cookies
                youtube_cookies = [
                    c for c in cookies
                    if any(d in c.get('domain', '') for d in ['youtube', 'google'])
                ]
                
                print(f"[+] Extracted {len(youtube_cookies)} YouTube/Google cookies")
                print(f"[*] Total cookies: {len(cookies)}")
                
                # Close page (but keep session for future use)
                await page.close()
                
                # Note: We don't close the browser to keep the session alive
                # AgentGo will manage session lifecycle
                
                return youtube_cookies
                
            except Exception as e:
                print(f"[!] Error: {type(e).__name__}: {e}")
                raise
    
    async def _perform_login(self, page: Page, email: str, password: str):
        """Perform Google login for YouTube."""
        print("[*] Starting login process...")
        
        try:
            # Click sign in button
            signin_btn = await page.query_selector('a[href*="accounts.google.com"]')
            if signin_btn:
                await signin_btn.click()
                await page.wait_for_load_state("networkidle")
            else:
                await page.goto("https://accounts.google.com/ServiceLogin?service=youtube", timeout=60000)
                await page.wait_for_load_state("networkidle")
            
            await asyncio.sleep(2)
            
            # Enter email
            email_input = await page.wait_for_selector('input[type="email"]', timeout=10000)
            await email_input.fill(email)
            await page.click('#identifierNext')
            await asyncio.sleep(3)
            
            # Enter password
            password_input = await page.wait_for_selector('input[type="password"]', timeout=10000)
            await password_input.fill(password)
            await page.click('#passwordNext')
            await asyncio.sleep(5)
            
            # Wait for redirect back to YouTube
            await page.wait_for_load_state("networkidle")
            
            # Check if login succeeded by navigating to a video
            target_url = "https://www.youtube.com/watch?v=_MLwQUebJUc"
            await page.goto(target_url, wait_until="networkidle", timeout=60000)
            
            print(f"[+] Login completed, current URL: {page.url}")
            
        except Exception as e:
            print(f"[!] Login failed: {e}")
    
    def _to_netscape_format(self, cookies: List[Dict[str, Any]]) -> str:
        """Convert cookies to Netscape format for yt-dlp."""
        lines = [
            "# Netscape HTTP Cookie File",
            "# https://curl.haxx.se/rfc/cookie_spec.html",
            "# Generated by AgentGo Cookie Extractor",
            f"# Date: {datetime.now().isoformat()}",
            ""
        ]
        
        for cookie in cookies:
            domain = cookie.get('domain', '')
            subdomain = "TRUE" if domain.startswith('.') else "FALSE"
            domain = domain.lstrip('.')
            
            path = cookie.get('path', '/')
            secure = "TRUE" if cookie.get('secure', False) else "FALSE"
            
            expires = cookie.get('expires', 0)
            if not expires:
                expires = 2147483647  # Far future for session cookies
            expires = int(expires)
            
            name = cookie.get('name', '')
            value = cookie.get('value', '')
            
            if not name or not domain:
                continue
            
            line = f".{domain}\t{subdomain}\t{path}\t{secure}\t{expires}\t{name}\t{value}"
            lines.append(line)
        
        return "\n".join(lines)
    
    async def save_cookies(self, cookies: List[Dict[str, Any]]) -> str:
        """Save cookies to Netscape format file."""
        content = self._to_netscape_format(cookies)
        
        with open(self.cookie_file, 'w') as f:
            f.write(content)
        
        print(f"[+] Saved {len(cookies)} cookies to {self.cookie_file}")
        return self.cookie_file
    
    async def run(
        self,
        login: bool = False,
        email: Optional[str] = None,
        password: Optional[str] = None
    ) -> Optional[str]:
        """
        Main entry point: extract cookies and save to file.
        
        Returns:
            Path to cookie file, or None if failed
        """
        try:
            cookies = await self.extract_cookies(login, email, password)
            
            if not cookies:
                print("[!] No cookies extracted")
                return None
            
            return await self.save_cookies(cookies)
            
        except Exception as e:
            print(f"[!] Failed: {e}")
            return None


async def test_ytdlp_with_cookies(cookie_file: str, video_url: str = "https://www.youtube.com/watch?v=jNQXAC9IVRw"):
    """Test yt-dlp extraction with the cookies."""
    try:
        import yt_dlp
    except ImportError:
        print("[!] yt-dlp not installed")
        return False
    
    print("\n[*] Testing yt-dlp with cookies...")
    print(f"[*] Cookie file: {cookie_file}")
    print(f"[*] Video URL: {video_url}")
    
    opts = {
        'cookiefile': cookie_file,
        'skip_download': True,
        'quiet': True,
        'no_warnings': True,
        'geo_bypass': True,
        'extractor_args': {
            'youtube': {'player_client': ['ios', 'web']}
        }
    }
    
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
            
            print("[+] Extraction successful!")
            print(f"    Title: {info.get('title')}")
            print(f"    Duration: {info.get('duration')}s")
            print(f"    Formats: {len(info.get('formats', []))}")
            
            # Get best URL
            for fmt in reversed(info.get('formats', [])):
                if fmt.get('url') and fmt.get('vcodec') != 'none':
                    print(f"    Download URL: {fmt['url'][:80]}...")
                    break
            
            return True
            
    except Exception as e:
        print(f"[!] yt-dlp failed: {e}")
        return False


async def main():
    parser = argparse.ArgumentParser(description="Extract YouTube cookies using AgentGo")
    parser.add_argument("--login", action="store_true", help="Perform YouTube login")
    parser.add_argument("--email", help="Google email (required if --login)")
    parser.add_argument("--password", help="Google password (required if --login)")
    parser.add_argument("--region", default="us", help="AgentGo region (us, uk, de, jp, etc.)")
    parser.add_argument("--output", default="/tmp/youtube_cookies.txt", help="Cookie file output path")
    parser.add_argument("--test", action="store_true", help="Test yt-dlp after extraction")
    parser.add_argument("--video", default="https://www.youtube.com/watch?v=jNQXAC9IVRw", help="Video URL for testing")
    
    args = parser.parse_args()
    
    # Check API key
    api_key = os.getenv("AGENTGO_API_KEY")
    if not api_key:
        print("[!] AGENTGO_API_KEY environment variable not set")
        print("    Set it with: export AGENTGO_API_KEY=your_api_key")
        sys.exit(1)
    
    print("=" * 60)
    print("AgentGo YouTube Cookie Extractor")
    print("=" * 60)
    print(f"Region: {args.region}")
    print(f"Login: {args.login}")
    print(f"Output: {args.output}")
    print("=" * 60)
    
    # Extract cookies
    extractor = AgentGoCookieExtractor(
        api_key=api_key,
        region=args.region,
        cookie_file=args.output
    )
    
    # Get credentials from env if not provided
    email = args.email or os.getenv("YOUTUBE_EMAIL")
    password = args.password or os.getenv("YOUTUBE_PASSWORD")
    
    cookie_file = await extractor.run(
        login=args.login,
        email=email,
        password=password
    )
    
    if cookie_file and args.test:
        print("\n" + "=" * 60)
        print("Testing yt-dlp Integration")
        print("=" * 60)
        success = await test_ytdlp_with_cookies(cookie_file, args.video)
        
        print("\n" + "=" * 60)
        if success:
            print("SUCCESS: AgentGo + Cookies + yt-dlp integration is working!")
        else:
            print("FAILED: yt-dlp extraction failed with the cookies")
        print("=" * 60)
    
    elif cookie_file:
        print(f"\n[+] Done! Cookie file saved to: {cookie_file}")
        print(f"    Use with yt-dlp: yt-dlp --cookies {cookie_file} <video_url>")


if __name__ == "__main__":
    asyncio.run(main())
