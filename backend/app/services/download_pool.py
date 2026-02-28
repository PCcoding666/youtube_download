"""
Download concurrency control and bgutil load balancing.

Provides:
1. bgutil PO Token provider round-robin load balancer (multiple instances)
2. Pre-fetched PO Token (bypasses yt-dlp plugin proxy issues)
3. Proxy region distribution for maximum spread
4. Download semaphore for global concurrency control
"""

import asyncio
import logging
import os
import re
import time
import itertools
import requests
from typing import Optional, List, Tuple

from app.config import settings

logger = logging.getLogger(__name__)


# =============================================================================
# bgutil Load Balancer
# =============================================================================

class BgutilLoadBalancer:
    """
    Round-robin load balancer across multiple bgutil PO Token provider instances.
    Distributes PO Token requests evenly to prevent any single instance from overloading.
    """

    def __init__(self):
        # Parse BGUTIL_URLS env var (comma-separated list of URLs)
        urls_str = os.environ.get("BGUTIL_URLS", "")
        if urls_str:
            self._urls = [u.strip() for u in urls_str.split(",") if u.strip()]
        else:
            # Fallback to single URL
            self._urls = [
                os.environ.get("YT_DLP_POT_PROVIDER_URL",
                    os.environ.get("BGUTIL_URL", "http://bgutil-1:4416"))
            ]

        self._cycle = itertools.cycle(range(len(self._urls)))
        self._lock = asyncio.Lock()

        logger.info(
            f"bgutil load balancer initialized with {len(self._urls)} instances: "
            f"{', '.join(self._urls)}"
        )

    @property
    def instance_count(self) -> int:
        return len(self._urls)

    def get_next_url(self) -> str:
        """Get next bgutil URL in round-robin order (thread-safe)."""
        idx = next(self._cycle)
        url = self._urls[idx]
        return url

    def get_all_urls(self) -> List[str]:
        return list(self._urls)

    def fetch_po_token(self, content_binding: Optional[str] = None) -> Optional[str]:
        """
        Pre-fetch PO Token directly from bgutil via HTTP (round-robin).
        
        This bypasses the yt-dlp bgutil plugin entirely, avoiding the proxy routing issue
        where --proxy causes bgutil internal connections to go through external proxy and timeout.
        
        Returns:
            PO Token string or None if all instances fail
        """
        # Try each instance until one succeeds
        for attempt in range(len(self._urls)):
            url = self.get_next_url()
            try:
                payload = {"disable_innertube": False}  # False = stronger token (796+ chars)
                if content_binding:
                    payload["content_binding"] = content_binding

                resp = requests.post(
                    f"{url}/get_pot",
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=10,
                    proxies={"http": None, "https": None},  # NEVER proxy internal calls
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    po_token = data.get("poToken")
                    if po_token:
                        logger.info(
                            f"✅ Pre-fetched PO Token from {url} "
                            f"(length: {len(po_token)}, attempt: {attempt + 1})"
                        )
                        return po_token
                        
                logger.warning(f"bgutil {url} returned unexpected response: {resp.status_code}")
                
            except requests.exceptions.Timeout:
                logger.warning(f"bgutil {url} timed out (10s), trying next...")
            except Exception as e:
                logger.warning(f"bgutil {url} error: {e}, trying next...")
        
        logger.error("All bgutil instances failed to provide PO Token")
        return None


# =============================================================================
# Proxy Region Distributor
# =============================================================================

class ProxyRegionDistributor:
    """
    Distributes proxy regions across requests for maximum spread.
    No longer tied to AgentGo region - pure round-robin across all available regions.
    """

    # All available Datasea proxy regions
    ALL_REGIONS = ["us", "sg", "jp", "uk", "de", "au", "ca"]

    def __init__(self):
        self._cycle = itertools.cycle(self.ALL_REGIONS)
        self._lock = asyncio.Lock()
        logger.info(
            f"Proxy region distributor initialized with {len(self.ALL_REGIONS)} regions: "
            f"{', '.join(self.ALL_REGIONS)}"
        )

    def get_next_region(self) -> str:
        """Get next proxy region in round-robin order."""
        return next(self._cycle)

    def build_proxy_url(self, base_proxy_url: str, region: str) -> Optional[str]:
        """
        Build region-specific proxy URL from base Datasea Gateway URL.

        Args:
            base_proxy_url: Base proxy URL like http://PCTrial-us:PCTrial0127@host:port
            region: Target region code (us, sg, jp, etc.)

        Returns:
            Region-adjusted proxy URL or original if can't parse
        """
        proxy_match = re.match(r'(https?://)([^:]+):([^@]+)@(.+)', base_proxy_url)
        if proxy_match:
            scheme = proxy_match.group(1)
            username = proxy_match.group(2)
            password = proxy_match.group(3)
            host_port = proxy_match.group(4)

            # Remove any existing region suffix from username
            base_username = re.sub(r'-[a-z]{2}$', '', username)

            # Build new proxy URL with target region
            new_username = f"{base_username}-{region}"
            return f"{scheme}{new_username}:{password}@{host_port}"
        else:
            return base_proxy_url


# =============================================================================
# Download Concurrency Controller
# =============================================================================

class DownloadConcurrencyController:
    """
    Global download concurrency limiter using asyncio.Semaphore.
    Prevents overwhelming bgutil, proxy gateway, and YouTube simultaneously.
    """

    def __init__(self, max_concurrent: int = 15):
        """
        Args:
            max_concurrent: Maximum number of simultaneous yt-dlp downloads.
                           Default 15 = good balance for 3 bgutil instances × 5 concurrent each.
        """
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._max = max_concurrent
        self._active = 0
        self._total = 0
        self._lock = asyncio.Lock()
        logger.info(f"Download concurrency controller initialized: max={max_concurrent}")

    @property
    def active_downloads(self) -> int:
        return self._active

    @property
    def max_concurrent(self) -> int:
        return self._max

    @property
    def total_downloads(self) -> int:
        return self._total

    async def acquire(self, task_id: str = "") -> None:
        """Acquire a download slot (blocks if at capacity)."""
        async with self._lock:
            self._total += 1
            queue_position = max(0, self._active - self._max + 1)

        if queue_position > 0:
            logger.info(
                f"[{task_id}] ⏳ Download queued (active: {self._active}/{self._max})"
            )

        await self._semaphore.acquire()

        async with self._lock:
            self._active += 1
            logger.info(
                f"[{task_id}] 🚀 Download slot acquired (active: {self._active}/{self._max})"
            )

    async def release(self, task_id: str = "") -> None:
        """Release a download slot."""
        self._semaphore.release()
        async with self._lock:
            self._active -= 1
            logger.debug(
                f"[{task_id}] Download slot released (active: {self._active}/{self._max})"
            )


# =============================================================================
# Global Instances
# =============================================================================

_bgutil_lb: Optional[BgutilLoadBalancer] = None
_proxy_distributor: Optional[ProxyRegionDistributor] = None
_download_controller: Optional[DownloadConcurrencyController] = None


def get_bgutil_lb() -> BgutilLoadBalancer:
    """Get global bgutil load balancer."""
    global _bgutil_lb
    if _bgutil_lb is None:
        _bgutil_lb = BgutilLoadBalancer()
    return _bgutil_lb


def get_proxy_distributor() -> ProxyRegionDistributor:
    """Get global proxy region distributor."""
    global _proxy_distributor
    if _proxy_distributor is None:
        _proxy_distributor = ProxyRegionDistributor()
    return _proxy_distributor


def get_download_controller() -> DownloadConcurrencyController:
    """Get global download concurrency controller."""
    global _download_controller
    if _download_controller is None:
        _download_controller = DownloadConcurrencyController(max_concurrent=15)
    return _download_controller
