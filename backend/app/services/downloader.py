"""YouTube video downloader service using yt-dlp.
Implements fallback strategy with proxy rotation for reliable downloads.
Integrates AgentGo as primary solution for YouTube authentication.
"""
import yt_dlp
import asyncio
import logging
import random
import time
from typing import Optional, Dict, Any, Tuple, List
from pathlib import Path
import re

from app.config import settings
from app.models import AuthenticationBundle

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Custom exception for download failures."""
    pass


class BotDetectionError(DownloadError):
    """Exception for YouTube bot detection errors."""
    pass


def is_bot_detection_error(error_msg: str) -> bool:
    """
    Check if error message indicates YouTube bot detection.
    
    Args:
        error_msg: Error message string
        
    Returns:
        True if error is related to bot detection
    """
    bot_keywords = [
        'sign in to confirm',
        'not a bot',
        'confirm you\'re not a bot',
        'verify you are human',
        'captcha',
        'unusual traffic',
        'automated queries',
        'too many requests',
        'rate limit exceeded',
        'please try again later',
        'failed to extract any player response',  # YouTube API access blocked
        'unable to extract',
        'sign in to confirm your age'
    ]
    error_lower = error_msg.lower()
    return any(keyword in error_lower for keyword in bot_keywords)


class ProxyRotator:
    """
    Proxy pool rotator for avoiding IP blocks.
    Supports multiple proxy addresses with automatic rotation.
    """
    
    def __init__(self, proxies: List[str]):
        """
        Initialize with list of proxy addresses.
        
        Args:
            proxies: List of proxy URLs, e.g., ["http://127.0.0.1:33210", "socks5://127.0.0.1:33211"]
        """
        self.proxies = proxies if proxies else []
        self.current_index = 0
        self.failed_proxies: set = set()  # Track temporarily failed proxies
    
    def get_random(self) -> Optional[str]:
        """Get a random proxy from the pool."""
        available = [p for p in self.proxies if p not in self.failed_proxies]
        if not available:
            # Reset failed proxies if all have failed
            self.failed_proxies.clear()
            available = self.proxies
        
        if not available:
            return None
        return random.choice(available)
    
    def get_next(self) -> Optional[str]:
        """Get next proxy in round-robin fashion."""
        if not self.proxies:
            return None
        
        proxy = self.proxies[self.current_index]
        self.current_index = (self.current_index + 1) % len(self.proxies)
        return proxy
    
    def mark_failed(self, proxy: str):
        """Mark a proxy as temporarily failed."""
        if proxy:
            self.failed_proxies.add(proxy)
            logger.warning(f"Proxy marked as failed: {proxy}")
    
    def mark_success(self, proxy: str):
        """Mark a proxy as working (remove from failed list)."""
        self.failed_proxies.discard(proxy)
    
    def get_all(self) -> List[str]:
        """Get all available proxies."""
        return self.proxies.copy()
    
    def __len__(self):
        return len(self.proxies)


# Global proxy rotator instance
_proxy_rotator: Optional[ProxyRotator] = None


def get_proxy_rotator() -> ProxyRotator:
    """Get or create global proxy rotator instance."""
    global _proxy_rotator
    if _proxy_rotator is None:
        _proxy_rotator = ProxyRotator(settings.youtube_proxy_list)
        if _proxy_rotator.proxies:
            logger.info(f"Initialized proxy rotator with {len(_proxy_rotator)} proxies")
    return _proxy_rotator


class YouTubeDownloader:
    """
    Lightweight YouTube downloader with proxy rotation support.
    Implements fallback strategy with proxy rotation for maximum reliability.
    Uses AgentGo as primary solution for cookie-based authentication.
    Supports intelligent region routing for optimal download performance.
    """
    
    # User-Agent strings for browser simulation
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
    
    def __init__(
        self, 
        proxy: Optional[str] = None, 
        use_rotation: bool = True, 
        resolution: str = "720",
        region: Optional[str] = None,
        auth_bundle: Optional[AuthenticationBundle] = None
    ):
        """
        Initialize downloader with optional proxy, region, and authentication bundle.
        
        Args:
            proxy: Specific HTTP proxy address (overrides rotation)
            use_rotation: Whether to use proxy rotation (default: True)
            resolution: Video resolution (360, 480, 720, 1080, 1440, 2160, best, audio)
            region: Geographic region for AgentGo browser session.
                   Used for intelligent region routing to match user's location.
            auth_bundle: Complete authentication data including cookies and tokens
        """
        self.use_rotation = use_rotation and proxy is None
        self.proxy_rotator = get_proxy_rotator() if self.use_rotation else None
        self.current_proxy = proxy  # Will be set per-request if using rotation
        self.resolution = resolution
        self.region = region  # Region for geo-routing
        self._auth_bundle: Optional[AuthenticationBundle] = auth_bundle
        self._cookie_file: Optional[str] = None  # Path to cookie file for authentication
        
        # Set cookie file from auth bundle if available
        if self._auth_bundle and self._auth_bundle.cookie_file_path:
            self._cookie_file = self._auth_bundle.cookie_file_path
        
        if not self.use_rotation and proxy:
            self.current_proxy = proxy
        elif not self.use_rotation and settings.youtube_proxy:
            self.current_proxy = settings.youtube_proxy.split(',')[0].strip()
    
    def configure_with_tokens(self, auth_bundle: AuthenticationBundle) -> Dict[str, Any]:
        """
        Configure yt-dlp extractor_args with tokens from authentication bundle.
        Includes comprehensive logging without exposing sensitive data.
        
        Args:
            auth_bundle: Authentication bundle containing tokens and cookies
            
        Returns:
            Dictionary of extractor_args for yt-dlp configuration
        """
        config_start = time.time()
        operation_id = f"config_{int(config_start)}"
        
        logger.info(f"Configuring yt-dlp with authentication data (operation: {operation_id})")
        
        # Base configuration - always use web client for consistency
        extractor_args = {
            'youtube': {
                'player_client': ['web']  # Use web client to match token origin
            }
        }
        
        config_details = {
            'player_client': 'web',
            'po_token_configured': False,
            'visitor_data_configured': False,
            'region': auth_bundle.region if hasattr(auth_bundle, 'region') else 'unknown',
            'has_cookies': bool(auth_bundle.cookies)
        }
        
        # Add PO token if available
        if auth_bundle.po_token:
            formatted_token = auth_bundle.get_formatted_po_token()
            if formatted_token:
                extractor_args['youtube']['po_token'] = formatted_token
                config_details['po_token_configured'] = True
                config_details['po_token_length'] = len(formatted_token)
                logger.info(f"✓ Configured yt-dlp with PO token (operation: {operation_id}, length: {len(formatted_token)})")
            else:
                logger.warning(f"Failed to format PO token for yt-dlp (operation: {operation_id})")
        else:
            logger.info(f"⚠ No PO token available - may encounter 403 errors for some videos (operation: {operation_id})")
        
        # Add visitor data if available
        if auth_bundle.visitor_data:
            extractor_args['youtube']['visitor_data'] = auth_bundle.visitor_data
            config_details['visitor_data_configured'] = True
            config_details['visitor_data_length'] = len(auth_bundle.visitor_data)
            logger.info(f"✓ Configured yt-dlp with visitor data (operation: {operation_id}, length: {len(auth_bundle.visitor_data)})")
        else:
            logger.info(f"⚠ No visitor data available (operation: {operation_id})")
        
        # Add fallback strategies when tokens are missing
        if not (auth_bundle.po_token or auth_bundle.visitor_data):
            logger.info(f"Adding fallback configuration for cookie-only authentication (operation: {operation_id})")
            # Try multiple player clients as fallback
            extractor_args['youtube']['player_client'] = ['web', 'android', 'ios']
            config_details['fallback_clients'] = True
        
        config_duration = time.time() - config_start
        
        # Provide clear status summary
        token_status = []
        if config_details['po_token_configured']:
            token_status.append("PO Token ✓")
        if config_details['visitor_data_configured']:
            token_status.append("Visitor Data ✓")
        if config_details['has_cookies']:
            token_status.append("Cookies ✓")
        
        status_summary = ", ".join(token_status) if token_status else "Cookies only"
        
        logger.info(
            f"yt-dlp authentication configuration completed (operation: {operation_id}) in {config_duration:.3f}s: "
            f"{status_summary}"
        )
        
        if not (config_details['po_token_configured'] or config_details['visitor_data_configured']):
            logger.warning(
                f"Limited authentication available - some YouTube videos may return 403 errors. "
                f"Consider checking AgentGo network connectivity."
            )
        
        return extractor_args
    
    def set_authentication_bundle(self, auth_bundle: Optional[AuthenticationBundle]):
        """
        Set authentication bundle for the downloader with comprehensive logging.
        Also logs IP information for proxy consistency verification.
        
        Args:
            auth_bundle: Authentication bundle to use, or None to clear
        """
        if auth_bundle:
            # Log bundle details without sensitive information
            bundle_info = {
                'region': auth_bundle.region,
                'has_po_token': bool(auth_bundle.po_token),
                'has_visitor_data': bool(auth_bundle.visitor_data),
                'cookies_count': len(auth_bundle.cookies) if auth_bundle.cookies else 0,
                'extraction_timestamp': auth_bundle.extraction_timestamp.isoformat() if auth_bundle.extraction_timestamp else None,
                'has_cookie_file': bool(auth_bundle.cookie_file_path),
                'browser_ip': getattr(auth_bundle, 'browser_ip', None),
                'browser_country': getattr(auth_bundle, 'browser_country', None)
            }
            
            logger.info(f"Updated authentication bundle: {bundle_info}")
            
            # Log IP consistency information for proxy configuration
            if hasattr(auth_bundle, 'browser_ip') and auth_bundle.browser_ip:
                logger.info(f"🌐 AgentGo browser IP: {auth_bundle.browser_ip} ({getattr(auth_bundle, 'browser_country', 'Unknown')})")
                logger.warning(
                    f"⚠️  PROXY CONSISTENCY: For optimal success rate, ensure yt-dlp uses the same IP as AgentGo. "
                    f"AgentGo IP: {auth_bundle.browser_ip} (Region: {auth_bundle.region}). "
                    f"Configure your proxy to route through the same region/IP to avoid 403 errors."
                )
            else:
                logger.warning("❌ No IP information available from AgentGo - cannot verify proxy consistency")
            
            # Check if bundle is expired
            if hasattr(auth_bundle, 'is_expired') and auth_bundle.is_expired():
                logger.warning(f"Authentication bundle for region {auth_bundle.region} has expired")
            
            self._auth_bundle = auth_bundle
            
            # Update cookie file path
            if auth_bundle.cookie_file_path:
                self._cookie_file = auth_bundle.cookie_file_path
                logger.debug(f"Updated cookie file path: {auth_bundle.cookie_file_path}")
        else:
            logger.info("Cleared authentication bundle")
            self._auth_bundle = None
            self._cookie_file = None
    
    def get_current_ip(self) -> Optional[str]:
        """
        Get current local IP address for comparison with AgentGo browser IP.
        
        Returns:
            Current IP address string or None if failed
        """
        try:
            import requests
            response = requests.get('https://httpbin.org/ip', timeout=10)
            if response.status_code == 200:
                data = response.json()
                return data.get('origin')
        except Exception as e:
            logger.debug(f"Failed to get current IP: {e}")
        return None
    
    def check_ip_consistency(self) -> bool:
        """
        Check if current IP matches AgentGo browser IP.
        
        Returns:
            True if IPs match or cannot be determined, False if they differ
        """
        if not self._auth_bundle or not hasattr(self._auth_bundle, 'browser_ip') or not self._auth_bundle.browser_ip:
            logger.debug("Cannot check IP consistency - no AgentGo IP available")
            return True  # Assume OK if we can't check
        
        current_ip = self.get_current_ip()
        if not current_ip:
            logger.debug("Cannot check IP consistency - failed to get current IP")
            return True  # Assume OK if we can't check
        
        agentgo_ip = self._auth_bundle.browser_ip
        if current_ip == agentgo_ip:
            logger.info(f"✅ IP consistency check passed: {current_ip}")
            return True
        else:
            logger.warning(
                f"❌ IP MISMATCH DETECTED! "
                f"Current IP: {current_ip}, AgentGo IP: {agentgo_ip}. "
                f"This may cause 403 errors. Consider using a proxy that matches AgentGo's IP."
            )
            return False
    
    def _progress_hook(self, d: Dict[str, Any]) -> None:
        """Progress hook for yt-dlp to track download status."""
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '0%')
            speed = d.get('_speed_str', 'N/A')
            logger.info(f"Downloading: {percent} at {speed}")
        elif d['status'] == 'finished':
            logger.info("Download completed, now post-processing...")
        elif d['status'] == 'error':
            logger.error(f"Download error: {d.get('error', 'Unknown error')}")
        """Progress hook for yt-dlp to track download status."""
        if d['status'] == 'downloading':
            percent = d.get('_percent_str', '0%')
            speed = d.get('_speed_str', 'N/A')
            logger.info(f"Downloading: {percent} at {speed}")
        elif d['status'] == 'finished':
            logger.info("Download completed, now post-processing...")
        elif d['status'] == 'error':
            logger.error(f"Download error: {d.get('error', 'Unknown error')}")
    
    def _get_format_string(self) -> str:
        """
        Get yt-dlp format string based on resolution setting.
        Following yt-dlp community best practices for quality selection.
        
        Returns:
            Format string for yt-dlp
        """
        if self.resolution == "audio":
            return "bestaudio/best"
        elif self.resolution == "best":
            # Best quality with proper codec preference (VP9 > AVC1)
            return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
        else:
            # Specific resolution with quality-aware selection
            # Following yt-dlp community recommendation:
            # 1. Prefer mp4 container for compatibility
            # 2. Prefer AVC1 (H.264) codec for better quality at same resolution
            # 3. Use height filter to match exact resolution
            # 4. Fallback to best available if exact match not found
            height = int(self.resolution)
            return (
                f"bestvideo[height={height}][ext=mp4]+bestaudio[ext=m4a]/"
                f"bestvideo[height={height}]+bestaudio/"
                f"bestvideo[height<={height}][ext=mp4]+bestaudio[ext=m4a]/"
                f"bestvideo[height<={height}]+bestaudio/"
                f"best[height<={height}]/best"
            )
    
    def _build_base_config(self, proxy: Optional[str] = None) -> Dict[str, Any]:
        """Build base yt-dlp configuration with optional proxy."""
        opts = {
            # Basic settings
            'noplaylist': True,
            'retries': 10,
            'fragment_retries': 10,
            'socket_timeout': 60,
            
            # Format selection based on resolution
            'format': self._get_format_string(),
            'merge_output_format': 'mp4' if self.resolution != "audio" else 'mp3',
            
            # Anti-bot HTTP headers - Enhanced for 2024
            'http_headers': {
                'User-Agent': self.USER_AGENT,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Sec-Ch-Ua': '"Chromium";v="131", "Not_A Brand";v="24"',
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"Windows"',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Upgrade-Insecure-Requests': '1',
            },
            
            # Disable cache to avoid stale bot detection data
            'no_cache_dir': True,
            
            # Geo bypass
            'geo_bypass': True,
            'geo_bypass_country': 'US',
            
            # Try to extract cookies from browser if available
            # In Docker, this might fail gracefully - that's OK
            # 'cookiesfrombrowser': ('chrome',),  # Disabled in Docker
            
            # Anti-throttling - slow down to appear more human
            'sleep_interval': 1,
            'max_sleep_interval': 3,
            'sleep_interval_requests': 1,
            'sleep_interval_subtitles': 1,
            
            # Logging configuration - capture errors and progress
            'quiet': False,  # Enable output for debugging
            'no_warnings': False,  # Show warnings
            'progress_hooks': [self._progress_hook],  # Track download progress
            'logger': logger,  # Use our logger
        }
        
        # Audio-only specific settings
        if self.resolution == "audio":
            opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }]
        
        if proxy:
            opts['proxy'] = proxy
            logger.info(f"Using proxy: {proxy}")
        
        # Add cookies if available
        if self._cookie_file and Path(self._cookie_file).exists():
            opts['cookiefile'] = self._cookie_file
            logger.info(f"Using cookie file: {self._cookie_file}")
        
        return opts
    
    def _get_strategy_config(self, strategy: int) -> Dict[str, Any]:
        """
        Get configuration for specific download strategy with comprehensive logging.
        Enhanced with 2024 anti-bot detection strategies and token support.
        
        Args:
            strategy: Strategy number (1-4)
            
        Returns:
            Strategy-specific yt-dlp options
        """
        logger.debug(f"Configuring download strategy {strategy}")
        
        strategies = {
            1: {
                # Strategy 1: iOS client (best for avoiding bot detection)
                'extractor_args': {
                    'youtube': {
                        'player_client': ['ios', 'web'],
                        'skip': ['hls', 'dash'],
                    }
                }
            },
            2: {
                # Strategy 2: Android client with web fallback
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'web'],
                        'skip': ['hls'],
                    }
                }
            },
            3: {
                # Strategy 3: Web client only (requires cookies, enhanced with tokens)
                'extractor_args': {
                    'youtube': {
                        'player_client': ['web'],
                    }
                }
            },
            4: {
                # Strategy 4: TV Embedded client (last resort)
                'extractor_args': {
                    'youtube': {
                        'player_client': ['tv_embedded'],
                    }
                }
            }
        }
        
        config = strategies.get(strategy, strategies[1])
        
        # Enhance with tokens if available and using web client
        if self._auth_bundle and self._auth_bundle.has_tokens():
            youtube_config = config['extractor_args']['youtube']
            
            # Only add tokens for web client strategies (3) or when web is in client list
            if (strategy == 3 or 'web' in youtube_config.get('player_client', [])):
                token_config_details = {
                    'strategy': strategy,
                    'po_token_added': False,
                    'visitor_data_added': False
                }
                
                # Add PO token if available
                if self._auth_bundle.po_token:
                    formatted_token = self._auth_bundle.get_formatted_po_token()
                    if formatted_token:
                        youtube_config['po_token'] = formatted_token
                        token_config_details['po_token_added'] = True
                        logger.debug(f"Added PO token to strategy {strategy} configuration")
                
                # Add visitor data if available
                if self._auth_bundle.visitor_data:
                    youtube_config['visitor_data'] = self._auth_bundle.visitor_data
                    token_config_details['visitor_data_added'] = True
                    logger.debug(f"Added visitor data to strategy {strategy} configuration")
                
                if token_config_details['po_token_added'] or token_config_details['visitor_data_added']:
                    logger.info(
                        f"Enhanced strategy {strategy} with tokens: "
                        f"PO token: {'✓' if token_config_details['po_token_added'] else '✗'}, "
                        f"Visitor data: {'✓' if token_config_details['visitor_data_added'] else '✗'}"
                    )
            else:
                logger.debug(f"Strategy {strategy} does not support token enhancement (no web client)")
        else:
            if self._auth_bundle:
                logger.debug(f"Strategy {strategy}: Authentication bundle available but no tokens to add")
            else:
                logger.debug(f"Strategy {strategy}: No authentication bundle available")
        
        return config
    
    def _sanitize_filename(self, filename: str) -> str:
        """Remove or replace characters that are invalid in filenames."""
        # Replace invalid characters with underscore
        sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
        # Remove leading/trailing spaces and dots
        sanitized = sanitized.strip('. ')
        # Limit length
        if len(sanitized) > 200:
            sanitized = sanitized[:200]
        return sanitized
    
    async def get_video_info(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Extract video information without downloading.
        
        Args:
            url: YouTube video URL
            
        Returns:
            Video metadata dict or None if failed
        """
        # Get a proxy for info extraction
        proxy = None
        if self.use_rotation and self.proxy_rotator:
            proxy = self.proxy_rotator.get_random()
        else:
            proxy = self.current_proxy
        
        opts = self._build_base_config(proxy)
        opts['skip_download'] = True
        opts.update(self._get_strategy_config(1))
        
        try:
            loop = asyncio.get_event_loop()
            
            def extract():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=False)
            
            info = await loop.run_in_executor(None, extract)
            
            return {
                'title': info.get('title', 'Unknown'),
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail'),
                'description': info.get('description'),
                'uploader': info.get('uploader'),
                'view_count': info.get('view_count'),
            }
        except Exception as e:
            logger.error(f"Failed to extract video info: {e}")
            return None
    
    async def download_with_enhanced_auth(
        self, 
        url: str, 
        output_dir: str,
        auth_bundle: Optional[AuthenticationBundle] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Download YouTube video using enhanced authentication with tokens.
        
        Args:
            url: YouTube video URL
            output_dir: Local directory to save video
            auth_bundle: Optional authentication bundle to use
            
        Returns:
            Tuple of (video file path, video info dict)
            
        Raises:
            DownloadError: If all download strategies and proxies fail
        """
        # Set authentication bundle if provided
        if auth_bundle:
            self.set_authentication_bundle(auth_bundle)
        
        # Use the existing download method which now supports tokens
        return await self.download(url, output_dir)
    
    async def download(self, url: str, output_dir: str) -> Tuple[str, Dict[str, Any]]:
        """
        Download YouTube video using triple fallback strategy with proxy rotation and comprehensive monitoring.
        
        Args:
            url: YouTube video URL
            output_dir: Local directory to save video
            
        Returns:
            Tuple of (video file path, video info dict)
            
        Raises:
            DownloadError: If all download strategies and proxies fail
        """
        download_start = time.time()
        operation_id = f"download_{int(download_start)}"
        
        logger.info(
            f"Starting YouTube download (operation: {operation_id}): "
            f"URL: {url[:50]}..., Output: {output_dir}, "
            f"Resolution: {self.resolution}, Region: {self.region or 'default'}"
        )
        
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        # Check IP consistency if we have AgentGo authentication
        if self._auth_bundle:
            logger.info(f"Checking IP consistency with AgentGo browser (operation: {operation_id})...")
            ip_consistent = self.check_ip_consistency()
            if not ip_consistent:
                logger.warning(
                    f"IP mismatch detected! This may cause 403 errors. "
                    f"Consider configuring a proxy that matches AgentGo's region: {self._auth_bundle.region}"
                )
        
        errors = []
        
        # Get list of proxies to try
        if self.use_rotation and self.proxy_rotator and len(self.proxy_rotator) > 0:
            proxies_to_try = self.proxy_rotator.get_all()
            logger.info(f"Will try {len(proxies_to_try)} proxies for download (operation: {operation_id})")
        else:
            proxies_to_try = [self.current_proxy] if self.current_proxy else [None]
            logger.info(f"Using single proxy/direct connection (operation: {operation_id})")
        
        # Log authentication status
        if self._auth_bundle:
            auth_info = {
                'region': self._auth_bundle.region,
                'has_po_token': bool(self._auth_bundle.po_token),
                'has_visitor_data': bool(self._auth_bundle.visitor_data),
                'cookies_count': len(self._auth_bundle.cookies) if self._auth_bundle.cookies else 0
            }
            logger.info(f"Using authentication bundle (operation: {operation_id}): {auth_info}")
        else:
            logger.info(f"No authentication bundle available (operation: {operation_id})")
        
        # Try each proxy with each strategy
        for proxy_idx, proxy in enumerate(proxies_to_try):
            proxy_label = proxy or "direct"
            
            for strategy in [1, 2, 3, 4]:
                attempt_start = time.time()
                logger.info(
                    f"Trying strategy {strategy} with proxy: {proxy_label} "
                    f"(proxy {proxy_idx + 1}/{len(proxies_to_try)}, operation: {operation_id})"
                )
                
                try:
                    result = await self._download_with_strategy(url, output_dir, strategy, proxy)
                    
                    # Mark proxy as successful
                    if self.proxy_rotator and proxy:
                        self.proxy_rotator.mark_success(proxy)
                    
                    download_duration = time.time() - download_start
                    attempt_duration = time.time() - attempt_start
                    
                    logger.info(
                        f"Download succeeded (operation: {operation_id}): "
                        f"Strategy {strategy}, Proxy: {proxy_label}, "
                        f"Total time: {download_duration:.2f}s, "
                        f"Attempt time: {attempt_duration:.2f}s"
                    )
                    return result
                    
                except Exception as e:
                    attempt_duration = time.time() - attempt_start
                    error_msg = f"Strategy {strategy} with proxy {proxy_label} failed after {attempt_duration:.2f}s: {str(e)}"
                    logger.warning(f"{error_msg} (operation: {operation_id})")
                    errors.append(error_msg)
                    
                    # Check if it's an IP block error
                    error_str = str(e).lower()
                    if any(keyword in error_str for keyword in ['403', 'blocked', 'bot', 'captcha', 'rate limit']):
                        if self.proxy_rotator and proxy:
                            self.proxy_rotator.mark_failed(proxy)
                        logger.warning(f"IP block detected, skipping to next proxy (operation: {operation_id})")
                        # Try next proxy immediately
                        break
                    
                    continue
        
        # All strategies and proxies failed
        download_duration = time.time() - download_start
        
        # Check if it's a bot detection error - try AgentGo fallback
        bot_detection = any(is_bot_detection_error(e) for e in errors)
        if bot_detection:
            logger.info(f"Bot detection encountered, attempting AgentGo cookie fallback (operation: {operation_id})...")
            try:
                result = await self._try_agentgo_fallback(url, output_dir, proxies_to_try)
                if result:
                    total_duration = time.time() - download_start
                    logger.info(f"AgentGo fallback succeeded after {total_duration:.2f}s (operation: {operation_id})")
                    return result
            except Exception as e:
                fallback_error = f"AgentGo fallback failed: {e}"
                logger.error(f"{fallback_error} (operation: {operation_id})")
                errors.append(fallback_error)
        
        # Log comprehensive failure information
        logger.error(
            f"All download attempts failed (operation: {operation_id}): "
            f"URL: {url[:50]}..., Duration: {download_duration:.2f}s, "
            f"Proxies tried: {len(proxies_to_try)}, Strategies tried: 4, "
            f"Bot detection: {bot_detection}"
        )
        
        raise DownloadError(
            f"All download attempts failed for {url}. Tried {len(proxies_to_try)} proxies. "
            f"Last errors: {'; '.join(errors[-3:])}")
    
    

    async def _try_agentgo_fallback(
        self,
        url: str,
        output_dir: str,
        proxies_to_try: List[str]
    ) -> Optional[Tuple[str, Dict[str, Any]]]:
        """
        Try AgentGo browser automation to get YouTube authentication bundle and retry download.
        Uses region-aware authentication fetching for optimal routing.
        
        This is called when YouTube bot detection is triggered.
        
        Args:
            url: YouTube video URL
            output_dir: Output directory
            proxies_to_try: List of proxies to try
            
        Returns:
            Tuple of (video file path, video info dict) if successful, None otherwise
        """
        try:
            from app.services.agentgo_service import get_agentgo_service
            
            service = get_agentgo_service()
            
            # Check if AgentGo is configured
            if not service.is_configured():
                logger.warning(
                    "AgentGo not configured. Set AGENTGO_API_KEY, YOUTUBE_EMAIL, "
                    "YOUTUBE_PASSWORD in environment to enable authentication fallback."
                )
                return None
            
            # Get authentication bundle using AgentGo with region-aware routing
            logger.info(
                f"Fetching YouTube authentication bundle via AgentGo browser automation "
                f"(region: {self.region or 'default'})..."
            )
            auth_bundle = await service.get_youtube_authentication_bundle(
                force_refresh=True,
                region=self.region,
                video_url=url  # Pass the video URL for better token extraction
            )
            
            if not auth_bundle:
                logger.error("Failed to obtain YouTube authentication bundle via AgentGo")
                return None
            
            # Update authentication bundle
            self.set_authentication_bundle(auth_bundle)
            logger.info(f"Successfully obtained authentication bundle, retrying download...")
            
            # Retry download with enhanced authentication
            for proxy in proxies_to_try[:2]:  # Try first 2 proxies
                for strategy in [1, 3]:  # iOS and Web clients work best with tokens
                    try:
                        result = await self._download_with_strategy(
                            url, output_dir, strategy, proxy
                        )
                        logger.info(f"AgentGo authentication bundle fallback succeeded!")
                        return result
                    except Exception as e:
                        logger.warning(f"Authentication bundle retry failed: {e}")
                        continue
            
            return None
            
        except ImportError:
            logger.warning("AgentGo service not available")
            return None
        except Exception as e:
            logger.error(f"AgentGo fallback error: {e}")
            return None
    
    async def prefetch_authentication_for_region(self):
        """
        Pre-fetch authentication bundle for the configured region.
        Called before download to ensure authentication data is ready.
        """
        if not self.region:
            return
        
        try:
            from app.services.agentgo_service import get_agentgo_service
            
            service = get_agentgo_service()
            if not service.is_api_configured():
                logger.info(f"AgentGo API not configured, skipping authentication bundle prefetch")
                return
            
            # Check if we already have valid authentication bundle for this region
            cached_auth = await service.get_youtube_authentication_bundle(region=self.region)
            if cached_auth and not cached_auth.is_expired():
                self.set_authentication_bundle(cached_auth)
                logger.info(f"Using pre-cached authentication bundle for region: {self.region}")
            else:
                # Fetch authentication bundle in background (don't block download)
                logger.info(f"Pre-fetching authentication bundle for region: {self.region}")
                auth_bundle = await service.get_youtube_authentication_bundle(
                    region=self.region,
                    force_refresh=True
                )
                if auth_bundle:
                    self.set_authentication_bundle(auth_bundle)
                    
                    # Log the quality of authentication data
                    if auth_bundle.has_tokens():
                        logger.info(f"Successfully pre-fetched authentication bundle with tokens for region: {self.region}")
                    else:
                        logger.info(f"Pre-fetched authentication bundle with cookies only for region: {self.region}")
                        logger.info("Note: PO Token not available - may encounter YouTube 403 errors for some videos")
                else:
                    logger.warning(f"Failed to pre-fetch authentication bundle for region: {self.region}")
                    
        except Exception as e:
            logger.warning(f"Failed to prefetch authentication bundle: {e}")
            logger.info("Download will proceed with fallback authentication methods")
    
    async def prefetch_cookies_for_region(self):
        """
        Pre-fetch cookies for the configured region.
        Backward compatibility method - delegates to prefetch_authentication_for_region.
        """
        await self.prefetch_authentication_for_region()
    
    async def _download_with_strategy(
        self, 
        url: str, 
        output_dir: str, 
        strategy: int,
        proxy: Optional[str] = None
    ) -> Tuple[str, Dict[str, Any]]:
        """
        Download video using specific strategy and proxy.
        
        Args:
            url: YouTube video URL
            output_dir: Output directory
            strategy: Strategy number (1-3)
            proxy: Proxy URL to use
            
        Returns:
            Tuple of (video file path, video info dict)
        """
        opts = self._build_base_config(proxy)
        opts.update(self._get_strategy_config(strategy))
        opts['outtmpl'] = f"{output_dir}/%(id)s.%(ext)s"
        
        loop = asyncio.get_event_loop()
        
        def do_download():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                filename = ydl.prepare_filename(info)
                return filename, info
        
        filename, info = await loop.run_in_executor(None, do_download)
        
        # Verify file exists
        if not Path(filename).exists():
            raise DownloadError(f"Downloaded file not found: {filename}")
        
        video_info = {
            'title': info.get('title', 'Unknown'),
            'duration': info.get('duration', 0),
            'thumbnail': info.get('thumbnail'),
            'description': info.get('description'),
            'uploader': info.get('uploader'),
        }
        
        return filename, video_info


# Convenience function for quick downloads
async def download_youtube_video(
    url: str, 
    output_dir: str,
    proxy: Optional[str] = None,
    region: Optional[str] = None,
    auth_bundle: Optional[AuthenticationBundle] = None,
    timeout: int = 300
) -> Tuple[str, Dict[str, Any]]:
    """
    Quick download function with enhanced authentication, timeout handling, and comprehensive monitoring.
    
    Args:
        url: YouTube video URL
        output_dir: Output directory
        proxy: Optional proxy address
        region: Geographic region for intelligent routing
        auth_bundle: Optional authentication bundle with tokens and cookies
        timeout: Maximum time to spend on download operation (seconds)
        
    Returns:
        Tuple of (video file path, video info dict)
        
    Raises:
        DownloadError: If download fails or times out
        asyncio.TimeoutError: If operation exceeds timeout
    """
    operation_start = time.time()
    operation_id = f"quick_download_{int(operation_start)}"
    
    logger.info(
        f"Starting quick download (operation: {operation_id}): "
        f"URL: {url[:50]}..., Region: {region or 'default'}, "
        f"Timeout: {timeout}s, Has auth bundle: {bool(auth_bundle)}"
    )
    
    downloader = YouTubeDownloader(
        proxy=proxy, 
        region=region,
        auth_bundle=auth_bundle
    )
    
    try:
        # Pre-fetch authentication if region is specified and no auth bundle provided
        if region and not auth_bundle:
            logger.info(f"Pre-fetching authentication bundle for region: {region} (operation: {operation_id})")
            try:
                # Use timeout for authentication fetching
                auth_start = time.time()
                await asyncio.wait_for(
                    downloader.prefetch_authentication_for_region(),
                    timeout=60  # 1 minute timeout for authentication
                )
                auth_duration = time.time() - auth_start
                logger.info(f"Authentication pre-fetch completed in {auth_duration:.2f}s (operation: {operation_id})")
            except asyncio.TimeoutError:
                logger.warning(f"Authentication pre-fetch timed out for region {region} (operation: {operation_id}), continuing with fallback")
            except Exception as e:
                logger.warning(f"Authentication pre-fetch failed for region {region} (operation: {operation_id}): {e}, continuing with fallback")
        
        # Perform download with timeout
        logger.info(f"Starting download with timeout: {timeout}s (operation: {operation_id})")
        download_start = time.time()
        
        result = await asyncio.wait_for(
            downloader.download(url, output_dir),
            timeout=timeout
        )
        
        total_duration = time.time() - operation_start
        download_duration = time.time() - download_start
        
        logger.info(
            f"Quick download completed successfully (operation: {operation_id}): "
            f"Total time: {total_duration:.2f}s, Download time: {download_duration:.2f}s"
        )
        
        return result
        
    except asyncio.TimeoutError:
        total_duration = time.time() - operation_start
        error_msg = f"Download operation timed out after {timeout}s"
        logger.error(f"{error_msg} (operation: {operation_id}, total time: {total_duration:.2f}s)")
        raise DownloadError(f"Download operation timed out after {timeout} seconds")
    except Exception as e:
        total_duration = time.time() - operation_start
        logger.error(f"Quick download failed (operation: {operation_id}) after {total_duration:.2f}s: {e}")
        raise
        logger.error(f"Download failed: {e}")
        raise
