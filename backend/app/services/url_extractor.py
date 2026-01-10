"""YouTube video URL extractor service using yt-dlp.
Only extracts direct download URLs without downloading the video.
Traffic goes directly from user to Google servers.
"""
import yt_dlp
import asyncio
import logging
import time
import aiohttp
from typing import Optional, Dict, Any, List
from pathlib import Path

from app.config import settings
from app.models import AuthenticationBundle

logger = logging.getLogger(__name__)

# bgutil PO Token server configuration
BGUTIL_SERVER_URL = "http://localhost:4416"


class ExtractionError(Exception):
    """Custom exception for URL extraction failures."""
    pass


class BotDetectionError(ExtractionError):
    """Exception for YouTube bot detection errors."""
    pass


async def get_po_token_from_bgutil(
    visitor_data: Optional[str] = None,
    proxy: Optional[str] = None,
    timeout: int = 30
) -> Optional[Dict[str, Any]]:
    """
    Get PO Token from bgutil HTTP server.
    
    Args:
        visitor_data: Optional visitor data to use as content binding
        proxy: Optional proxy for bgutil to use (passed to bgutil server)
        timeout: Request timeout in seconds
        
    Returns:
        Dict with poToken, contentBinding, expiresAt or None if failed
    """
    try:
        # Use a session that explicitly ignores proxy env vars for local bgutil server
        # trust_env=False prevents aiohttp from using http_proxy/https_proxy env vars
        async with aiohttp.ClientSession(trust_env=False) as session:
            # First ping the server
            try:
                async with session.get(
                    f"{BGUTIL_SERVER_URL}/ping",
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as resp:
                    if resp.status != 200:
                        logger.warning("bgutil server not responding")
                        return None
                    ping_data = await resp.json()
                    logger.debug(f"bgutil server v{ping_data.get('version')} running")
            except Exception as e:
                logger.warning(f"bgutil server not available: {e}")
                return None
            
            # Request PO Token - pass proxy to bgutil so it can access Google APIs
            request_data = {}
            if visitor_data:
                request_data['content_binding'] = visitor_data
            # Always pass proxy to bgutil for Google API access
            if proxy:
                request_data['proxy'] = proxy
            else:
                # Default to local proxy if not specified
                request_data['proxy'] = "http://127.0.0.1:7890"
            
            logger.info(f"Requesting PO Token from bgutil server (proxy: {request_data.get('proxy')})...")
            async with session.post(
                f"{BGUTIL_SERVER_URL}/get_pot",
                json=request_data,
                timeout=aiohttp.ClientTimeout(total=timeout)
            ) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    logger.error(f"bgutil server error: {error_text}")
                    return None
                
                result = await resp.json()
                po_token = result.get('poToken')
                content_binding = result.get('contentBinding')
                
                if po_token:
                    logger.info(f"✅ Got PO Token from bgutil (length: {len(po_token)})")
                    return {
                        'po_token': po_token,
                        'visitor_data': content_binding,
                        'expires_at': result.get('expiresAt')
                    }
                else:
                    logger.warning("bgutil returned empty PO Token")
                    return None
                    
    except asyncio.TimeoutError:
        logger.error("bgutil request timed out")
        return None
    except Exception as e:
        logger.error(f"Failed to get PO Token from bgutil: {e}")
        return None


def is_bot_detection_error(error_msg: str) -> bool:
    """Check if error message indicates YouTube bot detection."""
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
        'failed to extract any player response',
        'unable to extract',
        'sign in to confirm your age',
        '403'
    ]
    error_lower = error_msg.lower()
    return any(keyword in error_lower for keyword in bot_keywords)


class VideoFormat:
    """Represents a single video/audio format."""
    
    def __init__(self, fmt: Dict[str, Any]):
        self.format_id = fmt.get('format_id', '')
        self.url = fmt.get('url', '')
        self.ext = fmt.get('ext', '')
        self.resolution = fmt.get('resolution', 'audio only')
        self.height = fmt.get('height')
        self.width = fmt.get('width')
        self.fps = fmt.get('fps')
        self.vcodec = fmt.get('vcodec', 'none')
        self.acodec = fmt.get('acodec', 'none')
        self.filesize = fmt.get('filesize') or fmt.get('filesize_approx')
        self.tbr = fmt.get('tbr')  # Total bitrate
        self.format_note = fmt.get('format_note', '')
        self.protocol = fmt.get('protocol', '')  # https, m3u8, m3u8_native, etc.
    
    @property
    def is_video(self) -> bool:
        return self.vcodec != 'none' and self.vcodec is not None
    
    @property
    def is_audio(self) -> bool:
        return self.acodec != 'none' and self.acodec is not None
    
    @property
    def is_video_only(self) -> bool:
        return self.is_video and not self.is_audio
    
    @property
    def is_audio_only(self) -> bool:
        return self.is_audio and not self.is_video
    
    @property
    def has_both(self) -> bool:
        return self.is_video and self.is_audio
    
    @property
    def is_direct_download(self) -> bool:
        """Check if this is a direct download URL (not streaming)."""
        # https protocol means direct download from googlevideo.com
        # m3u8, m3u8_native, hls are streaming formats
        return self.protocol == 'https' and self.url and 'googlevideo.com' in self.url
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'format_id': self.format_id,
            'url': self.url,
            'ext': self.ext,
            'resolution': self.resolution,
            'height': self.height,
            'width': self.width,
            'fps': self.fps,
            'vcodec': self.vcodec,
            'acodec': self.acodec,
            'filesize': self.filesize,
            'tbr': self.tbr,
            'format_note': self.format_note,
            'is_video': self.is_video,
            'is_audio': self.is_audio,
            'is_video_only': self.is_video_only,
            'is_audio_only': self.is_audio_only,
            'has_both': self.has_both,
            'protocol': self.protocol,
            'is_direct_download': self.is_direct_download
        }


class ExtractedVideo:
    """Represents extracted video information with download URLs."""
    
    def __init__(self, info: Dict[str, Any]):
        self.video_id = info.get('id', '')
        self.title = info.get('title', 'Unknown')
        self.duration = info.get('duration', 0)
        self.thumbnail = info.get('thumbnail', '')
        self.description = info.get('description', '')
        self.uploader = info.get('uploader', '')
        self.uploader_id = info.get('uploader_id', '')
        self.view_count = info.get('view_count', 0)
        self.like_count = info.get('like_count', 0)
        self.upload_date = info.get('upload_date', '')
        
        # Parse all formats
        self._formats = [VideoFormat(f) for f in info.get('formats', [])]
    
    @property
    def formats(self) -> List[VideoFormat]:
        return self._formats
    
    def get_best_video_audio_combined(self) -> Optional[VideoFormat]:
        """Get best format that has both video and audio."""
        combined = [f for f in self._formats if f.has_both and f.url]
        if not combined:
            return None
        return max(combined, key=lambda f: (f.height or 0, f.tbr or 0))
    
    def get_best_video_only(self, max_height: Optional[int] = None) -> Optional[VideoFormat]:
        """Get best video-only format (needs separate audio)."""
        video_only = [f for f in self._formats if f.is_video_only and f.url]
        if max_height:
            video_only = [f for f in video_only if f.height and f.height <= max_height]
        if not video_only:
            return None
        return max(video_only, key=lambda f: (f.height or 0, f.tbr or 0))
    
    def get_best_audio_only(self) -> Optional[VideoFormat]:
        """Get best audio-only format."""
        audio_only = [f for f in self._formats if f.is_audio_only and f.url]
        if not audio_only:
            return None
        return max(audio_only, key=lambda f: f.tbr or 0)
    
    def get_format_by_height(self, height: int) -> Optional[VideoFormat]:
        """Get format closest to specified height."""
        # First try combined formats
        combined = [f for f in self._formats if f.has_both and f.url and f.height]
        if combined:
            exact = [f for f in combined if f.height == height]
            if exact:
                return max(exact, key=lambda f: f.tbr or 0)
            # Get closest
            return min(combined, key=lambda f: abs((f.height or 0) - height))
        
        # Fall back to video-only
        video_only = [f for f in self._formats if f.is_video_only and f.url and f.height]
        if video_only:
            exact = [f for f in video_only if f.height == height]
            if exact:
                return max(exact, key=lambda f: f.tbr or 0)
            return min(video_only, key=lambda f: abs((f.height or 0) - height))
        
        return None
    
    def get_download_urls(self, resolution: str = "720", prefer_mp4: bool = True) -> Dict[str, Any]:
        """
        Get download URLs based on resolution preference.
        Prioritizes MP4 (H.264/AVC) over WEBM (VP9) for better compatibility.
        Prioritizes direct download URLs (https) over streaming (m3u8).
        
        For high resolutions (720p+), YouTube typically only provides separate
        video and audio streams, so we return both for client-side merging.
        
        Args:
            resolution: "360", "480", "720", "1080", "1440", "2160", "best", "audio"
            prefer_mp4: If True, prefer MP4 format over WEBM (default: True)
            
        Returns:
            Dict with video_url, audio_url (if separate), and format info
        """
        result = {
            'video_url': None,
            'audio_url': None,
            'video_format': None,
            'audio_format': None,
            'needs_merge': False,
            'resolution': resolution
        }
        
        def is_mp4_format(f) -> bool:
            """Check if format is MP4/M4A (H.264/AAC)."""
            return f.ext in ('mp4', 'm4a') or (f.vcodec and 'avc' in f.vcodec.lower())
        
        def format_sort_key(f, prefer_mp4: bool = True):
            """Sort key: (is_mp4, height, bitrate)."""
            mp4_score = 1 if (prefer_mp4 and is_mp4_format(f)) else 0
            return (mp4_score, f.height or 0, f.tbr or 0)
        
        if resolution == "audio":
            # Get best audio-only format (prefer M4A over WEBM)
            audio_only = [f for f in self._formats if f.is_audio_only and f.url]
            direct_audio = [f for f in audio_only if f.is_direct_download]
            if direct_audio:
                if prefer_mp4:
                    m4a_audio = [f for f in direct_audio if f.ext == 'm4a']
                    audio = max(m4a_audio, key=lambda f: f.tbr or 0) if m4a_audio else max(direct_audio, key=lambda f: f.tbr or 0)
                else:
                    audio = max(direct_audio, key=lambda f: f.tbr or 0)
            elif audio_only:
                audio = max(audio_only, key=lambda f: f.tbr or 0)
            else:
                audio = None
            
            if audio:
                result['audio_url'] = audio.url
                result['audio_format'] = audio.to_dict()
            return result
        
        target_height = int(resolution) if resolution != "best" else 9999
        
        # For 720p and above, prefer separate video + audio (higher quality)
        # For 360p/480p, try combined format first
        prefer_separate = target_height >= 720 or resolution == "best"
        
        # Get all direct download formats
        video_only_direct = [
            f for f in self._formats 
            if f.is_video_only and f.url and f.is_direct_download and f.height
        ]
        
        audio_only_direct = [
            f for f in self._formats 
            if f.is_audio_only and f.url and f.is_direct_download
        ]
        
        combined_direct = [
            f for f in self._formats 
            if f.has_both and f.url and f.is_direct_download and f.height
        ]
        
        # Strategy for high resolution: separate video + audio
        if prefer_separate and video_only_direct:
            if resolution == "best":
                video = max(video_only_direct, key=lambda f: format_sort_key(f, prefer_mp4))
            else:
                suitable = [f for f in video_only_direct if f.height and f.height <= target_height]
                if suitable:
                    # Prefer MP4, then highest quality at target resolution
                    video = max(suitable, key=lambda f: format_sort_key(f, prefer_mp4))
                else:
                    # Get closest to target, still prefer MP4
                    candidates = sorted(video_only_direct, key=lambda f: abs((f.height or 0) - target_height))
                    min_diff = abs((candidates[0].height or 0) - target_height)
                    closest = [f for f in candidates if abs((f.height or 0) - target_height) == min_diff]
                    video = max(closest, key=lambda f: format_sort_key(f, prefer_mp4))
            
            result['video_url'] = video.url
            result['video_format'] = video.to_dict()
            result['needs_merge'] = True
            
            # Get best audio (prefer M4A)
            if audio_only_direct:
                if prefer_mp4:
                    m4a_audio = [f for f in audio_only_direct if f.ext == 'm4a']
                    audio = max(m4a_audio, key=lambda f: f.tbr or 0) if m4a_audio else max(audio_only_direct, key=lambda f: f.tbr or 0)
                else:
                    audio = max(audio_only_direct, key=lambda f: f.tbr or 0)
                result['audio_url'] = audio.url
                result['audio_format'] = audio.to_dict()
            
            return result
        
        # Strategy for low resolution: try combined format first (prefer MP4)
        if combined_direct:
            if resolution == "best":
                best = max(combined_direct, key=lambda f: format_sort_key(f, prefer_mp4))
            else:
                suitable = [f for f in combined_direct if f.height and f.height <= target_height]
                if suitable:
                    best = max(suitable, key=lambda f: format_sort_key(f, prefer_mp4))
                else:
                    candidates = sorted(combined_direct, key=lambda f: abs((f.height or 0) - target_height))
                    min_diff = abs((candidates[0].height or 0) - target_height)
                    closest = [f for f in candidates if abs((f.height or 0) - target_height) == min_diff]
                    best = max(closest, key=lambda f: format_sort_key(f, prefer_mp4))
            
            result['video_url'] = best.url
            result['video_format'] = best.to_dict()
            return result
        
        # Fallback: separate video + audio even for low resolution
        if video_only_direct:
            if resolution == "best":
                video = max(video_only_direct, key=lambda f: format_sort_key(f, prefer_mp4))
            else:
                suitable = [f for f in video_only_direct if f.height and f.height <= target_height]
                if suitable:
                    video = max(suitable, key=lambda f: format_sort_key(f, prefer_mp4))
                else:
                    candidates = sorted(video_only_direct, key=lambda f: abs((f.height or 0) - target_height))
                    min_diff = abs((candidates[0].height or 0) - target_height)
                    closest = [f for f in candidates if abs((f.height or 0) - target_height) == min_diff]
                    video = max(closest, key=lambda f: format_sort_key(f, prefer_mp4))
            
            result['video_url'] = video.url
            result['video_format'] = video.to_dict()
            result['needs_merge'] = True
            
            if audio_only_direct:
                if prefer_mp4:
                    m4a_audio = [f for f in audio_only_direct if f.ext == 'm4a']
                    audio = max(m4a_audio, key=lambda f: f.tbr or 0) if m4a_audio else max(audio_only_direct, key=lambda f: f.tbr or 0)
                else:
                    audio = max(audio_only_direct, key=lambda f: f.tbr or 0)
                result['audio_url'] = audio.url
                result['audio_format'] = audio.to_dict()
            
            return result
        
        # Last resort: any format including streaming
        all_video = [f for f in self._formats if f.is_video and f.url and f.height]
        if all_video:
            if resolution == "best":
                video = max(all_video, key=lambda f: format_sort_key(f, prefer_mp4))
            else:
                suitable = [f for f in all_video if f.height and f.height <= target_height]
                if suitable:
                    video = max(suitable, key=lambda f: format_sort_key(f, prefer_mp4))
                else:
                    candidates = sorted(all_video, key=lambda f: abs((f.height or 0) - target_height))
                    min_diff = abs((candidates[0].height or 0) - target_height)
                    closest = [f for f in candidates if abs((f.height or 0) - target_height) == min_diff]
                    video = max(closest, key=lambda f: format_sort_key(f, prefer_mp4))
            
            result['video_url'] = video.url
            result['video_format'] = video.to_dict()
            
            if video.is_video_only:
                result['needs_merge'] = True
                all_audio = [f for f in self._formats if f.is_audio_only and f.url]
                if all_audio:
                    if prefer_mp4:
                        m4a_audio = [f for f in all_audio if f.ext == 'm4a']
                        audio = max(m4a_audio, key=lambda f: f.tbr or 0) if m4a_audio else max(all_audio, key=lambda f: f.tbr or 0)
                    else:
                        audio = max(all_audio, key=lambda f: f.tbr or 0)
                    result['audio_url'] = audio.url
                    result['audio_format'] = audio.to_dict()
        
        return result
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'video_id': self.video_id,
            'title': self.title,
            'duration': self.duration,
            'thumbnail': self.thumbnail,
            'description': self.description,
            'uploader': self.uploader,
            'uploader_id': self.uploader_id,
            'view_count': self.view_count,
            'like_count': self.like_count,
            'upload_date': self.upload_date,
            'format_count': len(self._formats)
        }


class YouTubeURLExtractor:
    """
    Extract direct download URLs from YouTube videos.
    Does NOT download the video - only extracts googlevideo.com URLs.
    """
    
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
    
    def __init__(
        self,
        proxy: Optional[str] = None,
        region: Optional[str] = None,
        auth_bundle: Optional[AuthenticationBundle] = None
    ):
        """
        Initialize URL extractor.
        
        Args:
            proxy: Optional HTTP proxy address
            region: Geographic region for AgentGo browser session
            auth_bundle: Authentication data including cookies and tokens
        """
        self.proxy = proxy or (settings.youtube_proxy_list[0] if settings.youtube_proxy_list else None)
        self.region = region
        self._auth_bundle = auth_bundle
        self._cookie_file: Optional[str] = None
        
        if self._auth_bundle and self._auth_bundle.cookie_file_path:
            self._cookie_file = self._auth_bundle.cookie_file_path
    
    def set_authentication_bundle(self, auth_bundle: Optional[AuthenticationBundle]):
        """Set authentication bundle for the extractor."""
        self._auth_bundle = auth_bundle
        if auth_bundle and auth_bundle.cookie_file_path:
            self._cookie_file = auth_bundle.cookie_file_path
            logger.info(f"Set cookie file: {auth_bundle.cookie_file_path}")
        else:
            self._cookie_file = None
    
    def _build_opts(self, strategy: int = 1, po_token_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Build yt-dlp options for URL extraction with authentication."""
        opts = {
            'noplaylist': True,
            'skip_download': True,  # Key: don't download, just extract info
            'quiet': False,  # Enable output for debugging
            'no_warnings': False,
            'extract_flat': False,  # We need full format info
            'geo_bypass': True,
            'geo_bypass_country': 'US',
        }
        
        # Add proxy if available
        if self.proxy:
            opts['proxy'] = self.proxy
            logger.debug(f"Using proxy: {self.proxy}")
        
        # Add cookies if available
        if self._cookie_file and Path(self._cookie_file).exists():
            opts['cookiefile'] = self._cookie_file
            logger.info(f"Using cookie file: {self._cookie_file}")
        
        # Build extractor_args with authentication tokens from AgentGo
        youtube_args = {}
        
        # Use tokens from auth_bundle if available (from AgentGo)
        if self._auth_bundle and self._auth_bundle.has_tokens():
            # Use web client when we have tokens
            youtube_args['player_client'] = ['web']
            
            # Build po_token in the format yt-dlp expects: web+{visitor_data}+{po_token}
            if self._auth_bundle.po_token:
                if self._auth_bundle.visitor_data:
                    # Full format with visitor_data
                    po_token_formatted = f"web+{self._auth_bundle.visitor_data}+{self._auth_bundle.po_token}"
                    youtube_args['po_token'] = [po_token_formatted]
                    logger.info(f"Using AgentGo PO token with visitor_data (po_token length: {len(self._auth_bundle.po_token)})")
                else:
                    # Just po_token without visitor_data
                    po_token_formatted = f"web+{self._auth_bundle.po_token}"
                    youtube_args['po_token'] = [po_token_formatted]
                    logger.info(f"Using AgentGo PO token without visitor_data (length: {len(self._auth_bundle.po_token)})")
            
            # Add visitor data separately as well
            if self._auth_bundle.visitor_data:
                youtube_args['visitor_data'] = [self._auth_bundle.visitor_data]
                logger.info(f"Using AgentGo visitor data (length: {len(self._auth_bundle.visitor_data)})")
        
        # Strategy-specific overrides
        elif strategy == 4:
            # tv_embedded for 360p without PO Token
            youtube_args['player_client'] = ['tv_embedded']
        elif strategy == 5 and po_token_data:
            # Custom PO Token from bgutil
            youtube_args['player_client'] = ['web']
            po_token = po_token_data.get('po_token')
            visitor_data = po_token_data.get('visitor_data')
            
            if po_token and visitor_data:
                youtube_args['po_token'] = [f"web+{visitor_data}+{po_token}"]
                youtube_args['visitor_data'] = [visitor_data]
                logger.info(f"Using bgutil PO Token (visitor_data length: {len(visitor_data)})")
            elif po_token:
                youtube_args['po_token'] = [f"web+{po_token}"]
                logger.info("Using bgutil PO Token (no visitor_data)")
        # For other strategies without auth_bundle, let yt-dlp use defaults
        
        if youtube_args:
            opts['extractor_args'] = {'youtube': youtube_args}
            logger.info(f"Configured yt-dlp with youtube args: {list(youtube_args.keys())}")
        
        return opts
    
    async def extract(self, url: str, use_bgutil: bool = False) -> ExtractedVideo:
        """
        Extract video information and download URLs.
        
        Args:
            url: YouTube video URL
            use_bgutil: Whether to use our custom bgutil integration (default: False, let yt-dlp plugin handle it)
            
        Returns:
            ExtractedVideo object with all format URLs
            
        Raises:
            ExtractionError: If extraction fails
        """
        start_time = time.time()
        errors = []
        
        # Strategy 1: Use yt-dlp defaults (let GetPOT plugin handle PO Token)
        # Strategy 4: Fallback to tv_embedded (360p only, no PO Token needed)
        strategies = [1, 4]
        
        # Try multiple strategies
        for strategy in strategies:
            try:
                logger.info(f"Trying extraction strategy {strategy} for {url[:50]}...")
                
                opts = self._build_opts(strategy)
                loop = asyncio.get_event_loop()
                
                def do_extract():
                    with yt_dlp.YoutubeDL(opts) as ydl:
                        return ydl.extract_info(url, download=False)
                
                info = await loop.run_in_executor(None, do_extract)
                
                if info:
                    duration = time.time() - start_time
                    logger.info(f"Extraction succeeded with strategy {strategy} in {duration:.2f}s")
                    return ExtractedVideo(info)
                    
            except Exception as e:
                error_msg = str(e)
                errors.append(f"Strategy {strategy}: {error_msg}")
                logger.warning(f"Strategy {strategy} failed: {error_msg}")
                continue
        
        raise ExtractionError(f"All extraction strategies failed: {'; '.join(errors[-3:])}")
    
    async def _try_agentgo_fallback(self, url: str) -> Optional[ExtractedVideo]:
        """Try AgentGo to get fresh authentication and retry extraction."""
        try:
            from app.services.agentgo_service import get_agentgo_service
            
            service = get_agentgo_service()
            if not service.is_configured():
                logger.warning("AgentGo not configured for fallback")
                return None
            
            logger.info(f"Fetching authentication bundle via AgentGo (region: {self.region or 'default'})...")
            auth_bundle = await service.get_youtube_authentication_bundle(
                force_refresh=True,
                region=self.region,
                video_url=url
            )
            
            if not auth_bundle:
                logger.error("Failed to get authentication bundle from AgentGo")
                return None
            
            self.set_authentication_bundle(auth_bundle)
            
            # Retry with fresh auth
            opts = self._build_opts(strategy=3)  # Web client works best with tokens
            loop = asyncio.get_event_loop()
            
            def do_extract():
                with yt_dlp.YoutubeDL(opts) as ydl:
                    return ydl.extract_info(url, download=False)
            
            info = await loop.run_in_executor(None, do_extract)
            
            if info:
                logger.info("AgentGo fallback extraction succeeded")
                return ExtractedVideo(info)
            
            return None
            
        except ImportError:
            logger.warning("AgentGo service not available")
            return None
        except Exception as e:
            logger.error(f"AgentGo fallback error: {e}")
            return None
    
    async def prefetch_authentication(self):
        """Pre-fetch authentication bundle for the configured region."""
        if not self.region:
            return
        
        try:
            from app.services.agentgo_service import get_agentgo_service
            
            service = get_agentgo_service()
            if not service.is_api_configured():
                return
            
            auth_bundle = await service.get_youtube_authentication_bundle(region=self.region)
            if auth_bundle and not auth_bundle.is_expired():
                self.set_authentication_bundle(auth_bundle)
                logger.info(f"Pre-fetched authentication for region: {self.region}")
                
        except Exception as e:
            logger.warning(f"Failed to prefetch authentication: {e}")


async def extract_youtube_urls(
    url: str,
    resolution: str = "720",
    region: Optional[str] = None,
    auth_bundle: Optional[AuthenticationBundle] = None,
    timeout: int = 60
) -> Dict[str, Any]:
    """
    Quick function to extract YouTube download URLs.
    
    Args:
        url: YouTube video URL
        resolution: "360", "480", "720", "1080", "best", "audio"
        region: Geographic region for routing
        auth_bundle: Optional authentication bundle
        timeout: Extraction timeout in seconds
        
    Returns:
        Dict with video info and download URLs
    """
    extractor = YouTubeURLExtractor(region=region, auth_bundle=auth_bundle)
    
    # Pre-fetch auth if region specified
    if region and not auth_bundle:
        try:
            await asyncio.wait_for(extractor.prefetch_authentication(), timeout=30)
        except asyncio.TimeoutError:
            logger.warning("Authentication prefetch timed out")
        except Exception as e:
            logger.warning(f"Authentication prefetch failed: {e}")
    
    # Extract video info
    video = await asyncio.wait_for(extractor.extract(url), timeout=timeout)
    
    # Get download URLs for requested resolution
    urls = video.get_download_urls(resolution)
    
    return {
        'video_info': video.to_dict(),
        'download_urls': urls,
        'all_formats': [f.to_dict() for f in video.formats if f.url]
    }
