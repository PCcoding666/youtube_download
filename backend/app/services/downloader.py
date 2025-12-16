"""YouTube video downloader service using yt-dlp.
Implements triple fallback strategy for reliable downloads.
Supports Clash API for intelligent node switching.
"""
import yt_dlp
import asyncio
import logging
import random
from typing import Optional, Dict, Any, Tuple, List
from pathlib import Path
import re

from app.config import settings

logger = logging.getLogger(__name__)


class DownloadError(Exception):
    """Custom exception for download failures."""
    pass


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
    Implements triple fallback strategy with proxy rotation for maximum reliability.
    """
    
    # User-Agent strings for browser simulation
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
    
    def __init__(self, proxy: Optional[str] = None, use_rotation: bool = True, resolution: str = "720"):
        """
        Initialize downloader with optional proxy.
        
        Args:
            proxy: Specific HTTP proxy address (overrides rotation)
            use_rotation: Whether to use proxy rotation (default: True)
            resolution: Video resolution (360, 480, 720, 1080, 1440, 2160, best, audio)
        """
        self.use_rotation = use_rotation and proxy is None
        self.proxy_rotator = get_proxy_rotator() if self.use_rotation else None
        self.current_proxy = proxy  # Will be set per-request if using rotation
        self.resolution = resolution
        
        if not self.use_rotation and proxy:
            self.current_proxy = proxy
        elif not self.use_rotation and settings.youtube_proxy:
            self.current_proxy = settings.youtube_proxy.split(',')[0].strip()
    
    def _get_format_string(self) -> str:
        """
        Get yt-dlp format string based on resolution setting.
        
        Returns:
            Format string for yt-dlp
        """
        if self.resolution == "audio":
            return "bestaudio/best"
        elif self.resolution == "best":
            return "bestvideo+bestaudio/best"
        else:
            # Specific resolution
            height = int(self.resolution)
            return f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"
    
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
            
            # Anti-bot HTTP headers
            'http_headers': {
                'User-Agent': self.USER_AGENT,
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Sec-Ch-Ua': '"Chromium";v="131", "Not_A Brand";v="24"',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
            },
            
            # Disable cache to avoid stale bot detection data
            'no_cache_dir': True,
            
            # Geo bypass
            'geo_bypass': True,
            'geo_bypass_country': 'US',
            
            # Quiet output
            'quiet': True,
            'no_warnings': True,
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
        
        return opts
    
    def _get_strategy_config(self, strategy: int) -> Dict[str, Any]:
        """
        Get configuration for specific download strategy.
        
        Args:
            strategy: Strategy number (1-3)
            
        Returns:
            Strategy-specific yt-dlp options
        """
        strategies = {
            1: {
                # Strategy 1: Default with Android + Web client
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'web'],
                        'skip': ['hls', 'dash'],
                    }
                }
            },
            2: {
                # Strategy 2: Android client only
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android'],
                    }
                }
            },
            3: {
                # Strategy 3: TV Embedded client (fallback)
                'extractor_args': {
                    'youtube': {
                        'player_client': ['tv_embedded'],
                    }
                }
            }
        }
        return strategies.get(strategy, strategies[1])
    
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
    
    async def download(self, url: str, output_dir: str) -> Tuple[str, Dict[str, Any]]:
        """
        Download YouTube video using triple fallback strategy with proxy rotation.
        
        Args:
            url: YouTube video URL
            output_dir: Local directory to save video
            
        Returns:
            Tuple of (video file path, video info dict)
            
        Raises:
            DownloadError: If all download strategies and proxies fail
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        errors = []
        
        # Get list of proxies to try
        if self.use_rotation and self.proxy_rotator and len(self.proxy_rotator) > 0:
            proxies_to_try = self.proxy_rotator.get_all()
            logger.info(f"Will try {len(proxies_to_try)} proxies for download")
        else:
            proxies_to_try = [self.current_proxy] if self.current_proxy else [None]
        
        # Try each proxy with each strategy
        for proxy in proxies_to_try:
            proxy_label = proxy or "direct"
            
            for strategy in [1, 2, 3]:
                logger.info(f"Trying strategy {strategy} with proxy: {proxy_label}")
                
                try:
                    result = await self._download_with_strategy(url, output_dir, strategy, proxy)
                    
                    # Mark proxy as successful
                    if self.proxy_rotator and proxy:
                        self.proxy_rotator.mark_success(proxy)
                    
                    logger.info(f"Download succeeded with strategy {strategy}, proxy: {proxy_label}")
                    return result
                    
                except Exception as e:
                    error_msg = f"Strategy {strategy} with proxy {proxy_label} failed: {str(e)}"
                    logger.warning(error_msg)
                    errors.append(error_msg)
                    
                    # Check if it's an IP block error
                    error_str = str(e).lower()
                    if any(keyword in error_str for keyword in ['403', 'blocked', 'bot', 'captcha', 'rate limit']):
                        if self.proxy_rotator and proxy:
                            self.proxy_rotator.mark_failed(proxy)
                        # Try next proxy immediately
                        break
                    
                    continue
        
        # All strategies and proxies failed
        # Try switching Clash node and retry once more
        new_node = await self._try_switch_clash_node()
        if new_node:
            logger.info(f"Switched to new Clash node: {new_node}, retrying download...")
            try:
                # Use the same proxy (Clash will route through new node)
                proxy = proxies_to_try[0] if proxies_to_try else None
                return await self._download_with_strategy(url, output_dir, 1, proxy)
            except Exception as e:
                errors.append(f"Final retry after node switch failed: {e}")
        
        raise DownloadError(
            f"All download attempts failed for {url}. Tried {len(proxies_to_try)} proxies. "
            f"Last errors: {'; '.join(errors[-3:])}")
    
    async def _try_switch_clash_node(self) -> Optional[str]:
        """
        Try to switch Clash node for better YouTube access.
        
        Returns:
            New node name if successful, None otherwise
        """
        try:
            from app.services.clash_api import switch_youtube_node
            return await switch_youtube_node()
        except Exception as e:
            logger.warning(f"Failed to switch Clash node: {e}")
            return None
    
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
    proxy: Optional[str] = None
) -> Tuple[str, Dict[str, Any]]:
    """
    Quick download function.
    
    Args:
        url: YouTube video URL
        output_dir: Output directory
        proxy: Optional proxy address
        
    Returns:
        Tuple of (video file path, video info dict)
    """
    downloader = YouTubeDownloader(proxy=proxy)
    return await downloader.download(url, output_dir)
