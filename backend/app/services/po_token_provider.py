"""
PO Token provider service.
Fetches PO Tokens from bgutil server for YouTube downloads.

This is a workaround for the bgutil-ytdlp-pot-provider plugin issue
where the plugin fails with "No request handlers configured" error
when a proxy is configured in yt-dlp.
"""

import logging
import time
from typing import Optional, Dict, Any
import requests

from app.config import settings

logger = logging.getLogger(__name__)


class POTokenProvider:
    """
    Fetches PO Tokens from bgutil HTTP server.

    The bgutil server generates Proof of Origin tokens that help
    bypass YouTube's bot detection.
    """

    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize the PO Token provider.

        Args:
            base_url: bgutil server URL (default: from settings or http://127.0.0.1:4416)
        """
        self.base_url = base_url or settings.bgutil_url
        self._last_token: Optional[Dict[str, Any]] = None
        self._token_expires_at: float = 0

    def is_available(self) -> bool:
        """Check if bgutil server is available."""
        try:
            # 访问 localhost 时禁用代理
            response = requests.get(
                f"{self.base_url}/ping",
                timeout=5,
                proxies={"http": None, "https": None},
            )
            if response.status_code == 200:
                data = response.json()
                logger.info(f"bgutil server available (version: {data.get('version')})")
                return True
            return False
        except Exception as e:
            logger.warning(f"bgutil server not available: {e}")
            return False

    def get_po_token(
        self,
        bypass_cache: bool = False,
        disable_innertube: bool = True,
        content_binding: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get a PO Token from bgutil server.

        Args:
            bypass_cache: Force generate a new token
            disable_innertube: Disable innertube challenge (recommended)
            content_binding: Optional content binding for the token

        Returns:
            PO Token string or None if failed
        """
        # Check if we have a valid cached token
        if (
            not bypass_cache
            and self._last_token
            and time.time() < self._token_expires_at
        ):
            logger.debug("Using cached PO Token")
            return self._last_token.get("poToken")

        try:
            payload = {
                "bypass_cache": bypass_cache,
                "disable_innertube": disable_innertube,
            }

            if content_binding:
                payload["content_binding"] = content_binding

            logger.info(f"Fetching PO Token from {self.base_url}/get_pot")

            # 访问 localhost 时禁用代理
            response = requests.post(
                f"{self.base_url}/get_pot",
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=30,
                proxies={"http": None, "https": None},
            )

            if response.status_code != 200:
                logger.error(f"bgutil server returned status {response.status_code}")
                return None

            data = response.json()

            if "error" in data:
                logger.error(f"bgutil server error: {data['error']}")
                return None

            po_token = data.get("poToken")
            if not po_token:
                logger.error("No poToken in response")
                return None

            # Cache the token
            self._last_token = data
            # Set expiry to 6 hours from now (tokens typically last 12+ hours)
            self._token_expires_at = time.time() + 6 * 3600

            logger.info(f"✓ Got PO Token (length: {len(po_token)})")
            return po_token

        except requests.exceptions.ConnectionError:
            logger.error(f"Cannot connect to bgutil server at {self.base_url}")
            return None
        except Exception as e:
            logger.error(f"Error fetching PO Token: {e}")
            return None


# Global instance
_po_token_provider: Optional[POTokenProvider] = None


def get_po_token_provider() -> POTokenProvider:
    """Get the global PO Token provider instance."""
    global _po_token_provider
    if _po_token_provider is None:
        _po_token_provider = POTokenProvider()
    return _po_token_provider


async def get_po_token(bypass_cache: bool = False) -> Optional[str]:
    """
    Convenience function to get a PO Token.

    Args:
        bypass_cache: Force generate a new token

    Returns:
        PO Token string or None if failed
    """
    provider = get_po_token_provider()
    return provider.get_po_token(bypass_cache=bypass_cache)
