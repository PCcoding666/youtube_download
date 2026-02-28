"""
YouTube Visitor Data provider via InnerTube API.

Fetches visitor_data directly from YouTube's InnerTube API.
No API key, no account, no browser needed - just a simple HTTP POST.

visitor_data is used by yt-dlp to appear as a legitimate YouTube visitor,
reducing the chance of bot detection during concurrent downloads.
"""

import logging
import time
import random
from typing import Optional
import requests

logger = logging.getLogger(__name__)


class VisitorDataProvider:
    """
    Fetches YouTube visitor_data via InnerTube API.
    
    InnerTube is YouTube's internal API used by its web/mobile frontends.
    Every response includes a visitorData token that identifies the "visitor session".
    
    No API key or authentication needed.
    """

    # InnerTube API endpoint
    INNERTUBE_URL = "https://www.youtube.com/youtubei/v1/player"
    
    # Different client configs to rotate (reduces fingerprinting)
    CLIENT_CONFIGS = [
        {
            "clientName": "MWEB",
            "clientVersion": "2.20250101.00.00",
            "platform": "MOBILE",
        },
        {
            "clientName": "WEB",
            "clientVersion": "2.20250101.00.00",
            "platform": "DESKTOP",
        },
        {
            "clientName": "ANDROID",
            "clientVersion": "19.02.39",
            "platform": "MOBILE",
        },
    ]
    
    # Well-known video IDs for bootstrapping (short, always available)
    BOOTSTRAP_VIDEO_IDS = [
        "jNQXAC9IVRw",  # Me at the zoo
        "dQw4w9WgXcQ",  # Rick Astley
        "9bZkp7q19f0",  # Gangnam Style
    ]

    def __init__(self, proxy: Optional[str] = None):
        """
        Initialize the visitor data provider.
        
        Args:
            proxy: Optional HTTP proxy URL for the InnerTube request
        """
        self._proxy = proxy
        self._cached_visitor_data: Optional[str] = None
        self._cache_expires_at: float = 0
        # Cache duration: 30 minutes (visitor_data is session-based, refreshes help)
        self._cache_ttl = 1800

    def get_visitor_data(
        self,
        video_id: Optional[str] = None,
        force_refresh: bool = False,
        proxy: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get YouTube visitor_data from InnerTube API.
        
        Args:
            video_id: Optional specific video ID to use for the request
            force_refresh: Force fetch new visitor_data (bypass cache)
            proxy: Optional proxy URL override for this request
            
        Returns:
            visitor_data string (e.g. "CgtrWnc1bDJLVm9hRSjj...") or None
        """
        # Return cached if valid
        if (
            not force_refresh
            and self._cached_visitor_data
            and time.time() < self._cache_expires_at
        ):
            logger.debug("Using cached visitor_data")
            return self._cached_visitor_data
        
        # Pick a random client config and bootstrap video
        client = random.choice(self.CLIENT_CONFIGS)
        if not video_id:
            video_id = random.choice(self.BOOTSTRAP_VIDEO_IDS)
        
        try:
            start = time.time()
            
            payload = {
                "context": {
                    "client": {
                        "clientName": client["clientName"],
                        "clientVersion": client["clientVersion"],
                        "platform": client["platform"],
                        "hl": "en",
                        "gl": "US",
                    }
                },
                "videoId": video_id,
            }
            
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                "Content-Type": "application/json",
                "Origin": "https://www.youtube.com",
                "Referer": "https://www.youtube.com/",
            }
            
            # Use proxy if provided
            effective_proxy = proxy or self._proxy
            proxies = None
            if effective_proxy:
                proxies = {"http": effective_proxy, "https": effective_proxy}
            
            response = requests.post(
                self.INNERTUBE_URL,
                json=payload,
                headers=headers,
                proxies=proxies,
                timeout=15,
            )
            
            elapsed = time.time() - start
            
            if response.status_code != 200:
                logger.warning(
                    f"InnerTube API returned {response.status_code} "
                    f"(client: {client['clientName']}, elapsed: {elapsed:.1f}s)"
                )
                return self._cached_visitor_data  # Return stale cache if available
            
            data = response.json()
            visitor_data = (
                data.get("responseContext", {}).get("visitorData")
            )
            
            if visitor_data and isinstance(visitor_data, str) and len(visitor_data) > 10:
                # Cache it
                self._cached_visitor_data = visitor_data
                self._cache_expires_at = time.time() + self._cache_ttl
                
                logger.info(
                    f"✓ Got visitor_data via InnerTube API "
                    f"(client: {client['clientName']}, length: {len(visitor_data)}, "
                    f"elapsed: {elapsed:.1f}s)"
                )
                return visitor_data
            else:
                logger.warning(
                    f"InnerTube API response missing visitor_data "
                    f"(client: {client['clientName']})"
                )
                return self._cached_visitor_data
                
        except requests.exceptions.Timeout:
            logger.warning("InnerTube API request timed out (15s)")
            return self._cached_visitor_data
        except requests.exceptions.ConnectionError as e:
            logger.warning(f"InnerTube API connection error: {e}")
            return self._cached_visitor_data
        except Exception as e:
            logger.error(f"InnerTube API error: {e}")
            return self._cached_visitor_data


# Global instance
_visitor_data_provider: Optional[VisitorDataProvider] = None


def get_visitor_data_provider() -> VisitorDataProvider:
    """Get the global visitor data provider instance."""
    global _visitor_data_provider
    if _visitor_data_provider is None:
        _visitor_data_provider = VisitorDataProvider()
    return _visitor_data_provider


def get_visitor_data(
    video_id: Optional[str] = None,
    force_refresh: bool = False,
    proxy: Optional[str] = None,
) -> Optional[str]:
    """
    Convenience function to get YouTube visitor_data.
    
    Args:
        video_id: Optional video ID for the InnerTube request
        force_refresh: Force refresh (bypass cache)
        proxy: Optional proxy URL
        
    Returns:
        visitor_data string or None
    """
    provider = get_visitor_data_provider()
    return provider.get_visitor_data(
        video_id=video_id,
        force_refresh=force_refresh,
        proxy=proxy,
    )
