"""AgentGo browser automation service for YouTube access.
Primary solution for YouTube authentication and proxy access.

Uses AgentGo's cloud browser with built-in proxy to:
1. Login to YouTube and extract cookies for yt-dlp
2. Provide proxy access through remote browser sessions

AgentGo uses WebSocket-based browser automation:
- WebSocket URL: wss://app.browsers.live
- Authentication via launch-options parameter
- Regions: us, uk, de, fr, jp, sg, au, ca, in

AgentGo API: https://docs.agentgo.live/
"""

import asyncio
import logging
import json
import os
import time
import urllib.parse
import re
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime
import hashlib

try:
    import websockets

    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False
    websockets = None

try:
    from playwright.async_api import async_playwright

    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False

from app.config import settings
from app.models import AuthenticationBundle, TokenExtractionResult

logger = logging.getLogger(__name__)


class TokenExtractionMetrics:
    """
    Performance metrics collector for token extraction operations.
    Tracks timing, success rates, and error patterns for monitoring.
    """

    def __init__(self):
        """Initialize metrics collector."""
        self.logger = logging.getLogger(__name__ + ".TokenExtractionMetrics")
        self._extraction_attempts = 0
        self._successful_extractions = 0
        self._po_token_successes = 0
        self._visitor_data_successes = 0
        self._total_extraction_time = 0.0
        self._error_counts: Dict[str, int] = {}
        self._region_performance: Dict[str, Dict[str, Any]] = {}

    def record_extraction_attempt(self, region: str, start_time: float):
        """Record the start of an extraction attempt."""
        self._extraction_attempts += 1
        self.logger.debug(
            f"Starting extraction attempt #{self._extraction_attempts} for region: {region}"
        )

        if region not in self._region_performance:
            self._region_performance[region] = {
                "attempts": 0,
                "successes": 0,
                "total_time": 0.0,
                "avg_time": 0.0,
            }
        self._region_performance[region]["attempts"] += 1

    def record_extraction_success(
        self, region: str, duration: float, has_po_token: bool, has_visitor_data: bool
    ):
        """Record a successful extraction with performance metrics."""
        self._successful_extractions += 1
        self._total_extraction_time += duration

        if has_po_token:
            self._po_token_successes += 1
        if has_visitor_data:
            self._visitor_data_successes += 1

        # Update region performance
        if region in self._region_performance:
            self._region_performance[region]["successes"] += 1
            self._region_performance[region]["total_time"] += duration
            self._region_performance[region]["avg_time"] = (
                self._region_performance[region]["total_time"]
                / self._region_performance[region]["successes"]
            )

        self.logger.info(
            f"Token extraction completed successfully for region {region} "
            f"in {duration:.2f}s (PO token: {'✓' if has_po_token else '✗'}, "
            f"visitor data: {'✓' if has_visitor_data else '✗'})"
        )

    def record_extraction_error(self, region: str, error_type: str, error_message: str):
        """Record an extraction error for monitoring."""
        self._error_counts[error_type] = self._error_counts.get(error_type, 0) + 1

        # Log error without sensitive information
        sanitized_message = self._sanitize_error_message(error_message)
        self.logger.warning(
            f"Token extraction failed for region {region}: {error_type} - {sanitized_message}"
        )

    def _sanitize_error_message(self, message: str) -> str:
        """Remove potentially sensitive information from error messages."""
        # Remove potential tokens, passwords, or API keys
        sanitized = re.sub(r"[A-Za-z0-9+/=]{20,}", "[REDACTED_TOKEN]", message)
        sanitized = re.sub(
            r"password[=:]\s*\S+", "password=[REDACTED]", sanitized, flags=re.IGNORECASE
        )
        sanitized = re.sub(
            r"api[_-]?key[=:]\s*\S+",
            "api_key=[REDACTED]",
            sanitized,
            flags=re.IGNORECASE,
        )
        return sanitized

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics summary."""
        success_rate = (
            (self._successful_extractions / self._extraction_attempts * 100)
            if self._extraction_attempts > 0
            else 0
        )
        avg_extraction_time = (
            (self._total_extraction_time / self._successful_extractions)
            if self._successful_extractions > 0
            else 0
        )
        po_token_rate = (
            (self._po_token_successes / self._successful_extractions * 100)
            if self._successful_extractions > 0
            else 0
        )
        visitor_data_rate = (
            (self._visitor_data_successes / self._successful_extractions * 100)
            if self._successful_extractions > 0
            else 0
        )

        return {
            "total_attempts": self._extraction_attempts,
            "successful_extractions": self._successful_extractions,
            "success_rate_percent": round(success_rate, 2),
            "average_extraction_time_seconds": round(avg_extraction_time, 2),
            "po_token_success_rate_percent": round(po_token_rate, 2),
            "visitor_data_success_rate_percent": round(visitor_data_rate, 2),
            "error_counts": self._error_counts.copy(),
            "region_performance": self._region_performance.copy(),
        }

    def log_performance_summary(self):
        """Log current performance metrics summary."""
        summary = self.get_performance_summary()
        self.logger.info(
            f"Token extraction performance summary: "
            f"Success rate: {summary['success_rate_percent']}% "
            f"({summary['successful_extractions']}/{summary['total_attempts']}), "
            f"Avg time: {summary['average_extraction_time_seconds']}s, "
            f"PO token rate: {summary['po_token_success_rate_percent']}%, "
            f"Visitor data rate: {summary['visitor_data_success_rate_percent']}%"
        )


# Global metrics instance
_extraction_metrics: Optional[TokenExtractionMetrics] = None


def get_extraction_metrics() -> TokenExtractionMetrics:
    """Get or create global extraction metrics instance."""
    global _extraction_metrics
    if _extraction_metrics is None:
        _extraction_metrics = TokenExtractionMetrics()
    return _extraction_metrics


class AgentGoError(Exception):
    """Custom exception for AgentGo API errors."""

    pass


class TokenExtractor:
    """
    Token extraction component for YouTube authentication tokens.

    Handles extraction of PO tokens from network requests and visitor data
    from JavaScript execution using Playwright browser automation.
    """

    def __init__(self):
        """Initialize TokenExtractor with comprehensive logging."""
        self.logger = logging.getLogger(__name__ + ".TokenExtractor")
        self._extracted_po_tokens: List[tuple] = []  # (token, timestamp)
        self._extraction_timeout = 90  # seconds - increased for better success rate
        self._metrics = get_extraction_metrics()

        # Debug logging configuration
        self._debug_enabled = self.logger.isEnabledFor(logging.DEBUG)
        if self._debug_enabled:
            self.logger.debug("TokenExtractor initialized with debug logging enabled")

    def _log_secure(
        self, level: int, message: str, sensitive_data: Optional[Dict[str, Any]] = None
    ):
        """
        Log message with secure handling of sensitive data.

        Args:
            level: Logging level (logging.INFO, logging.WARNING, etc.)
            message: Base message to log
            sensitive_data: Optional dict of sensitive data to sanitize
        """
        if sensitive_data:
            # Create sanitized version for logging
            sanitized = {}
            for key, value in sensitive_data.items():
                if key.lower() in [
                    "token",
                    "po_token",
                    "password",
                    "api_key",
                    "secret",
                ]:
                    if value:
                        # Show only length and first/last few characters for debugging
                        if isinstance(value, str) and len(value) > 8:
                            sanitized[key] = (
                                f"[{len(value)} chars: {value[:3]}...{value[-3:]}]"
                            )
                        else:
                            sanitized[key] = "[REDACTED]"
                    else:
                        sanitized[key] = None
                elif key.lower() in ["visitor_data"] and value:
                    # Show length for visitor data
                    sanitized[key] = f"[{len(value)} chars]"
                else:
                    sanitized[key] = value

            message = f"{message} - Data: {sanitized}"

        self.logger.log(level, message)

    def _create_token_hash(self, token: str) -> str:
        """Create a hash of the token for secure logging and comparison."""
        return hashlib.sha256(token.encode()).hexdigest()[:8]

    async def extract_po_token(
        self, page, video_url: Optional[str] = None
    ) -> Optional[str]:
        """
        Extract PO token from network requests using Playwright request interception.

        PO Token is found in the request body of /youtubei/v1/player requests,
        specifically in serviceIntegrityDimensions.poToken field.

        Args:
            page: Playwright page object with network interception enabled
            video_url: Optional specific YouTube video URL to navigate to for better token extraction

        Returns:
            PO token string if found, None otherwise
        """
        extraction_start = time.time()
        operation_id = f"po_token_{int(extraction_start)}"

        try:
            self._log_secure(
                logging.INFO,
                f"Starting PO token extraction from network requests (operation: {operation_id})",
            )

            # Clear previous tokens
            self._extracted_po_tokens.clear()

            # Set up request interception with detailed logging
            # NOTE: This must be a sync function, not async, for Playwright event handlers
            def handle_request(request):
                try:
                    url = request.url

                    # Method 1: Look for PO token in /youtubei/v1/player request body
                    # This is the primary method according to yt-dlp PO Token Guide
                    if "/youtubei/v1/player" in url or "/youtubei/v1/next" in url:
                        self.logger.info(
                            f"🔍 Found player/next API request: {url[:80]}..."
                        )

                        # Get request body (POST data)
                        post_data = request.post_data
                        if post_data:
                            self.logger.debug(
                                f"Request has POST data (length: {len(post_data)})"
                            )
                            try:
                                body = json.loads(post_data)
                                # Look for serviceIntegrityDimensions.poToken
                                service_integrity = body.get(
                                    "serviceIntegrityDimensions", {}
                                )
                                po_token = service_integrity.get("poToken")

                                if po_token:
                                    self.logger.info(
                                        f"Found poToken in serviceIntegrityDimensions (length: {len(po_token)})"
                                    )
                                    if self.validate_po_token(po_token):
                                        timestamp = time.time()
                                        self._extracted_po_tokens.append(
                                            (po_token, timestamp)
                                        )

                                        token_hash = self._create_token_hash(po_token)
                                        self._log_secure(
                                            logging.INFO,
                                            f"✅ Found PO token in player API request body (hash: {token_hash})",
                                            {
                                                "token_length": len(po_token),
                                                "timestamp": timestamp,
                                            },
                                        )
                                    else:
                                        self.logger.warning(
                                            f"PO token validation failed (length: {len(po_token)})"
                                        )
                                else:
                                    self.logger.debug(
                                        "No poToken in serviceIntegrityDimensions"
                                    )
                            except json.JSONDecodeError as e:
                                self.logger.debug(
                                    f"Failed to parse POST data as JSON: {e}"
                                )
                        else:
                            self.logger.debug("No POST data in player request")

                    # Method 2: Look for PO token in URL parameters (pot=)
                    if "pot=" in url:
                        self.logger.info(
                            f"🔍 Found request with pot parameter: {url[:100]}..."
                        )

                        parsed_url = urllib.parse.urlparse(url)
                        query_params = urllib.parse.parse_qs(parsed_url.query)

                        if "pot" in query_params:
                            pot_value = query_params["pot"][0]
                            if pot_value and self.validate_po_token(pot_value):
                                timestamp = time.time()
                                self._extracted_po_tokens.append((pot_value, timestamp))

                                token_hash = self._create_token_hash(pot_value)
                                self._log_secure(
                                    logging.INFO,
                                    f"✅ Found PO token in URL parameter (hash: {token_hash})",
                                    {
                                        "token_length": len(pot_value),
                                        "timestamp": timestamp,
                                    },
                                )

                    # Method 3: Look for PO token in googlevideo.com requests (GVS)
                    if "googlevideo.com" in url:
                        self.logger.debug(
                            f"🔍 Found googlevideo request: {url[:100]}..."
                        )
                        if "pot=" in url:
                            parsed_url = urllib.parse.urlparse(url)
                            query_params = urllib.parse.parse_qs(parsed_url.query)

                            if "pot" in query_params:
                                pot_value = query_params["pot"][0]
                                if pot_value and self.validate_po_token(pot_value):
                                    timestamp = time.time()
                                    self._extracted_po_tokens.append(
                                        (pot_value, timestamp)
                                    )

                                    token_hash = self._create_token_hash(pot_value)
                                    self._log_secure(
                                        logging.INFO,
                                        f"✅ Found GVS PO token in googlevideo request (hash: {token_hash})",
                                        {
                                            "token_length": len(pot_value),
                                            "timestamp": timestamp,
                                        },
                                    )

                except Exception as e:
                    self._log_secure(
                        logging.WARNING,
                        f"Error processing request for PO token: {str(e)}",
                    )

            # Enable request interception
            page.on("request", handle_request)

            # Check if we're already on YouTube - skip navigation if so
            current_url = page.url
            if "youtube.com" in current_url and "/watch" in current_url:
                self.logger.info(
                    f"Already on YouTube video page: {current_url[:50]}..."
                )
                navigation_success = True
            else:
                # Navigate to YouTube video to trigger player API requests
                navigation_success = False

                # Use the provided video URL if available
                if video_url and video_url.startswith(
                    ("https://www.youtube.com/watch", "https://youtu.be/")
                ):
                    target_url = video_url
                    self.logger.info(
                        f"Using provided video URL for token extraction: {target_url}"
                    )
                else:
                    # Use a popular video that's likely to work
                    target_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
                    self.logger.info("Using default video for token extraction")

                # Navigate to video page
                try:
                    self.logger.info(f"Navigating to YouTube video: {target_url}")
                    await page.goto(
                        target_url, wait_until="domcontentloaded", timeout=60000
                    )
                    navigation_success = True
                    self.logger.info("Navigation to YouTube video successful")
                except Exception as e:
                    self.logger.warning(f"Direct navigation failed: {e}")

                # Fallback strategies
                if not navigation_success:
                    for fallback_url in [
                        "https://www.youtube.com",
                        "https://m.youtube.com",
                    ]:
                        try:
                            self.logger.info(f"Trying fallback: {fallback_url}")
                            await page.goto(
                                fallback_url,
                                wait_until="domcontentloaded",
                                timeout=60000,
                            )
                            navigation_success = True
                            break
                        except Exception as e:
                            self.logger.warning(f"Fallback navigation failed: {e}")

            if not navigation_success:
                self.logger.error("All navigation strategies failed")
                return None

            # Wait for page to load
            await asyncio.sleep(3)

            # Trigger video playback to generate player API requests
            try:
                self.logger.info(
                    "Attempting to trigger video playback for PO token generation..."
                )

                # Try to click play button or interact with video
                play_selectors = [
                    "button.ytp-large-play-button",
                    "button.ytp-play-button",
                    "#movie_player",
                    "video",
                ]

                for selector in play_selectors:
                    try:
                        element = page.locator(selector).first
                        if await element.is_visible(timeout=2000):
                            await element.click(timeout=3000)
                            self.logger.info(f"Clicked play element: {selector}")
                            await asyncio.sleep(2)
                            break
                    except Exception:
                        continue

                # Scroll to trigger more requests
                await page.evaluate("window.scrollTo(0, 300)")
                await asyncio.sleep(1)

                # Try to seek in video to trigger more player requests
                try:
                    await page.evaluate("""
                        () => {
                            const video = document.querySelector('video');
                            if (video) {
                                video.currentTime = 5;
                                video.play();
                            }
                        }
                    """)
                    self.logger.debug("Triggered video seek")
                except Exception:
                    pass

            except Exception as e:
                self.logger.debug(f"Page interaction failed (not critical): {e}")

            # Wait for network requests with PO tokens
            self.logger.info("Waiting for network requests with PO tokens...")
            await asyncio.sleep(5)

            # Also try to extract PO token from page JavaScript
            try:
                js_po_token = await page.evaluate("""
                    () => {
                        try {
                            // Method 1: From ytInitialPlayerResponse
                            if (window.ytInitialPlayerResponse && 
                                window.ytInitialPlayerResponse.serviceIntegrityDimensions &&
                                window.ytInitialPlayerResponse.serviceIntegrityDimensions.poToken) {
                                return window.ytInitialPlayerResponse.serviceIntegrityDimensions.poToken;
                            }
                            
                            // Method 2: From ytcfg
                            if (window.ytcfg && typeof window.ytcfg.get === 'function') {
                                const poToken = window.ytcfg.get('PO_TOKEN');
                                if (poToken) return poToken;
                            }
                            
                            // Method 3: Search in page scripts
                            const scripts = document.querySelectorAll('script');
                            for (const script of scripts) {
                                const text = script.textContent || '';
                                const match = text.match(/"poToken"\\s*:\\s*"([^"]+)"/);
                                if (match && match[1]) {
                                    return match[1];
                                }
                            }
                            
                            return null;
                        } catch (e) {
                            return null;
                        }
                    }
                """)

                if js_po_token and self.validate_po_token(js_po_token):
                    timestamp = time.time()
                    self._extracted_po_tokens.append((js_po_token, timestamp))
                    token_hash = self._create_token_hash(js_po_token)
                    self._log_secure(
                        logging.INFO,
                        f"✅ Found PO token via JavaScript extraction (hash: {token_hash})",
                        {"token_length": len(js_po_token)},
                    )
            except Exception as e:
                self.logger.debug(f"JavaScript PO token extraction failed: {e}")

            # Select the most recent valid token
            if self._extracted_po_tokens:
                # Sort by timestamp (most recent first)
                self._extracted_po_tokens.sort(key=lambda x: x[1], reverse=True)
                selected_token = self._extracted_po_tokens[0][0]

                extraction_duration = time.time() - extraction_start
                token_hash = self._create_token_hash(selected_token)

                self._log_secure(
                    logging.INFO,
                    f"PO token extraction completed successfully (operation: {operation_id})",
                    {
                        "duration_seconds": round(extraction_duration, 2),
                        "token_hash": token_hash,
                        "tokens_found": len(self._extracted_po_tokens),
                        "selected_token_age": round(
                            time.time() - self._extracted_po_tokens[0][1], 2
                        ),
                    },
                )

                return selected_token

            extraction_duration = time.time() - extraction_start
            self.logger.warning(
                f"No PO token found in network requests after {extraction_duration:.2f}s "
                f"(operation: {operation_id})"
            )
            return None

        except Exception as e:
            extraction_duration = time.time() - extraction_start
            self._log_secure(
                logging.ERROR,
                f"PO token extraction failed after {extraction_duration:.2f}s (operation: {operation_id}): {str(e)}",
            )
            self._metrics.record_extraction_error(
                "unknown", "po_token_extraction", str(e)
            )
            return None

    async def extract_visitor_data(
        self, page, video_url: Optional[str] = None
    ) -> Optional[str]:
        """
        Extract visitor data using JavaScript execution with both ytcfg methods.

        Args:
            page: Playwright page object
            video_url: Optional specific YouTube video URL to navigate to for better data extraction

        Returns:
            Visitor data string if found, None otherwise
        """
        extraction_start = time.time()
        operation_id = f"visitor_data_{int(extraction_start)}"

        try:
            self._log_secure(
                logging.INFO,
                f"Starting visitor data extraction using JavaScript (operation: {operation_id})",
            )

            # Ensure we're on a YouTube page with multiple navigation strategies
            current_url = page.url
            navigation_needed = "youtube.com" not in current_url

            if navigation_needed:
                navigation_success = False

                # Use the provided video URL if available, otherwise use a default video for better visitor data extraction
                if video_url and video_url.startswith(
                    ("https://www.youtube.com/watch", "https://youtu.be/")
                ):
                    target_url = video_url
                    self.logger.info(
                        f"Using provided video URL for visitor data extraction: {target_url}"
                    )
                else:
                    target_url = "https://www.youtube.com/watch?v=_MLwQUebJUc"  # Fallback video for better visitor data extraction
                    if video_url:
                        self.logger.warning(
                            f"Invalid video URL provided: {video_url}, using fallback for visitor data"
                        )
                    else:
                        self.logger.info(
                            "No video URL provided, using fallback video for visitor data extraction"
                        )

                # Strategy 1: Direct navigation to YouTube video with extended timeout
                try:
                    self.logger.info(
                        f"Navigating to YouTube video for visitor data extraction: {target_url}"
                    )
                    await page.goto(
                        target_url, wait_until="domcontentloaded", timeout=60000
                    )
                    navigation_success = True
                    self.logger.info(
                        "Navigation to video successful for visitor data extraction"
                    )
                except Exception as e:
                    self.logger.warning(
                        f"Direct navigation to video failed for visitor data: {e}"
                    )

                # Strategy 2: Fallback to homepage if video failed (with extended timeout)
                if not navigation_success:
                    try:
                        self.logger.info(
                            "Falling back to YouTube homepage for visitor data extraction..."
                        )
                        await page.goto(
                            "https://www.youtube.com",
                            wait_until="domcontentloaded",
                            timeout=60000,
                        )
                        navigation_success = True
                        self.logger.info(
                            "Homepage navigation successful for visitor data"
                        )
                    except Exception as e:
                        self.logger.warning(
                            f"Homepage navigation failed for visitor data: {e}"
                        )

                # Strategy 3: Try mobile YouTube if desktop failed (with extended timeout)
                if not navigation_success:
                    try:
                        self.logger.info(
                            "Trying mobile YouTube for visitor data extraction..."
                        )
                        await page.goto(
                            "https://m.youtube.com",
                            wait_until="domcontentloaded",
                            timeout=60000,
                        )
                        navigation_success = True
                        self.logger.info("Mobile YouTube navigation successful")
                    except Exception as e:
                        self.logger.warning(
                            f"Mobile navigation failed for visitor data: {e}"
                        )

                if not navigation_success:
                    self.logger.error(
                        "All navigation strategies failed for visitor data extraction"
                    )
                    return None

                # Wait for page to fully load
                await asyncio.sleep(2)
            else:
                self.logger.debug(f"Already on YouTube page: {current_url[:100]}...")

            # Try both ytcfg methods for visitor data extraction
            self.logger.debug(
                "Executing JavaScript to extract visitor data using multiple methods..."
            )
            visitor_data = await page.evaluate("""
                () => {
                    const methods = [];
                    let result = null;
                    
                    try {
                        // Method 1: window.ytcfg.get('VISITOR_DATA')
                        if (window.ytcfg && typeof window.ytcfg.get === 'function') {
                            const visitorData1 = window.ytcfg.get('VISITOR_DATA');
                            methods.push('ytcfg.get');
                            if (visitorData1 && typeof visitorData1 === 'string' && visitorData1.trim().length > 0) {
                                result = visitorData1;
                                console.log('Found visitor data via ytcfg.get method');
                                return result;
                            }
                        }
                        
                        // Method 2: window.ytcfg.data_.VISITOR_DATA
                        if (window.ytcfg && window.ytcfg.data_ && window.ytcfg.data_.VISITOR_DATA) {
                            const visitorData2 = window.ytcfg.data_.VISITOR_DATA;
                            methods.push('ytcfg.data_');
                            if (typeof visitorData2 === 'string' && visitorData2.trim().length > 0) {
                                result = visitorData2;
                                console.log('Found visitor data via ytcfg.data_ method');
                                return result;
                            }
                        }
                        
                        // Method 3: Try to find in global variables
                        if (window.ytInitialData && window.ytInitialData.responseContext && 
                            window.ytInitialData.responseContext.visitorData) {
                            const visitorData3 = window.ytInitialData.responseContext.visitorData;
                            methods.push('ytInitialData');
                            if (typeof visitorData3 === 'string' && visitorData3.trim().length > 0) {
                                result = visitorData3;
                                console.log('Found visitor data via ytInitialData method');
                                return result;
                            }
                        }
                        
                        console.log('No visitor data found, tried methods:', methods);
                        return null;
                    } catch (error) {
                        console.error('Error extracting visitor data:', error);
                        return null;
                    }
                }
            """)

            extraction_duration = time.time() - extraction_start

            if visitor_data and self.validate_visitor_data(visitor_data):
                visitor_hash = self._create_token_hash(visitor_data)
                self._log_secure(
                    logging.INFO,
                    f"Visitor data extraction completed successfully (operation: {operation_id})",
                    {
                        "duration_seconds": round(extraction_duration, 2),
                        "visitor_data_hash": visitor_hash,
                        "data_length": len(visitor_data),
                    },
                )
                return visitor_data

            self._log_secure(
                logging.WARNING,
                f"No visitor data found using JavaScript methods after {extraction_duration:.2f}s "
                f"(operation: {operation_id})",
            )
            return None

        except Exception as e:
            extraction_duration = time.time() - extraction_start
            self._log_secure(
                logging.ERROR,
                f"Visitor data extraction failed after {extraction_duration:.2f}s (operation: {operation_id}): {str(e)}",
            )
            self._metrics.record_extraction_error(
                "unknown", "visitor_data_extraction", str(e)
            )
            return None

    async def _extract_visitor_data_js_only(self, page) -> Optional[str]:
        """
        Extract visitor data using JavaScript only, without any navigation.
        This is a simplified version for use when already on a YouTube page.

        Args:
            page: Playwright page object (must already be on YouTube)

        Returns:
            Visitor data string if found, None otherwise
        """
        try:
            self.logger.debug(
                "Extracting visitor data using JavaScript (no navigation)..."
            )

            visitor_data = await page.evaluate("""
                () => {
                    try {
                        // Method 1: window.ytcfg.get('VISITOR_DATA')
                        if (window.ytcfg && typeof window.ytcfg.get === 'function') {
                            const visitorData = window.ytcfg.get('VISITOR_DATA');
                            if (visitorData && typeof visitorData === 'string' && visitorData.trim().length > 0) {
                                return visitorData;
                            }
                        }
                        
                        // Method 2: window.ytcfg.data_.VISITOR_DATA
                        if (window.ytcfg && window.ytcfg.data_ && window.ytcfg.data_.VISITOR_DATA) {
                            const visitorData = window.ytcfg.data_.VISITOR_DATA;
                            if (typeof visitorData === 'string' && visitorData.trim().length > 0) {
                                return visitorData;
                            }
                        }
                        
                        // Method 3: ytInitialData
                        if (window.ytInitialData && window.ytInitialData.responseContext && 
                            window.ytInitialData.responseContext.visitorData) {
                            const visitorData = window.ytInitialData.responseContext.visitorData;
                            if (typeof visitorData === 'string' && visitorData.trim().length > 0) {
                                return visitorData;
                            }
                        }
                        
                        return null;
                    } catch (error) {
                        console.error('Error extracting visitor data:', error);
                        return null;
                    }
                }
            """)

            if visitor_data and self.validate_visitor_data(visitor_data):
                return visitor_data

            return None

        except Exception as e:
            self.logger.warning(f"JavaScript visitor data extraction failed: {e}")
            return None

    def validate_po_token(self, token: str) -> bool:
        """
        Validate PO token format with detailed logging.

        Args:
            token: PO token string to validate

        Returns:
            True if token is valid, False otherwise
        """
        if not token or not isinstance(token, str):
            if self._debug_enabled:
                self.logger.debug(
                    f"PO token validation failed: invalid type or empty (type: {type(token)})"
                )
            return False

        # Remove web+ prefix if present for validation
        token_value = token.replace("web+", "") if token.startswith("web+") else token

        # Check if token is non-empty after stripping
        if len(token_value.strip()) == 0:
            if self._debug_enabled:
                self.logger.debug("PO token validation failed: empty after stripping")
            return False

        # Basic format validation - PO tokens are typically base64-like strings
        if not re.match(r"^[A-Za-z0-9+/=_-]+$", token_value):
            if self._debug_enabled:
                self.logger.debug(
                    f"PO token validation failed: invalid characters (length: {len(token_value)})"
                )
            return False

        # Additional length check - PO tokens are usually substantial
        if len(token_value) < 10:
            if self._debug_enabled:
                self.logger.debug(
                    f"PO token validation failed: too short (length: {len(token_value)})"
                )
            return False

        if self._debug_enabled:
            token_hash = self._create_token_hash(token)
            self.logger.debug(
                f"PO token validation passed (hash: {token_hash}, length: {len(token_value)})"
            )

        return True

    async def get_browser_ip_info(self, page) -> Optional[Dict[str, str]]:
        """
        Get the IP address and location information of the AgentGo browser.
        This is crucial for ensuring yt-dlp uses the same network environment.

        Args:
            page: Playwright page object

        Returns:
            Dict with IP info: {'ip': '1.2.3.4', 'country': 'US', 'region': 'us'}
        """
        try:
            self.logger.info(
                "Getting AgentGo browser IP information for proxy consistency..."
            )

            # Navigate to IP check service
            await page.goto(
                "https://httpbin.org/ip", wait_until="domcontentloaded", timeout=30000
            )
            await asyncio.sleep(1)

            # Extract IP information
            ip_info = await page.evaluate("""
                () => {
                    try {
                        const bodyText = document.body.innerText;
                        const data = JSON.parse(bodyText);
                        return {
                            ip: data.origin || null,
                            source: 'httpbin'
                        };
                    } catch (e) {
                        return null;
                    }
                }
            """)

            if ip_info and ip_info.get("ip"):
                # Try to get more detailed location info
                try:
                    await page.goto(
                        "https://ipapi.co/json/",
                        wait_until="domcontentloaded",
                        timeout=15000,
                    )
                    await asyncio.sleep(1)

                    location_info = await page.evaluate("""
                        () => {
                            try {
                                const bodyText = document.body.innerText;
                                const data = JSON.parse(bodyText);
                                return {
                                    country: data.country_code || null,
                                    region: data.region || null,
                                    city: data.city || null
                                };
                            } catch (e) {
                                return {};
                            }
                        }
                    """)

                    if location_info:
                        ip_info.update(location_info)

                except Exception as e:
                    self.logger.debug(f"Could not get detailed location info: {e}")

                self.logger.info(
                    f"AgentGo browser IP: {ip_info.get('ip')} ({ip_info.get('country', 'Unknown')})"
                )
                return ip_info

            return None

        except Exception as e:
            self.logger.warning(f"Failed to get browser IP info: {e}")
            return None

    def validate_visitor_data(self, data: str) -> bool:
        """
        Validate visitor data format with detailed logging.

        Args:
            data: Visitor data string to validate

        Returns:
            True if data is valid, False otherwise
        """
        if not data or not isinstance(data, str):
            if self._debug_enabled:
                self.logger.debug(
                    f"Visitor data validation failed: invalid type or empty (type: {type(data)})"
                )
            return False

        # Check if data is non-empty after stripping
        if len(data.strip()) == 0:
            if self._debug_enabled:
                self.logger.debug(
                    "Visitor data validation failed: empty after stripping"
                )
            return False

        # Basic format validation - visitor data is typically base64-like with URL encoding
        # Allow alphanumeric, underscore, hyphen, percent (for URL encoding), plus, equals
        if not re.match(r"^[A-Za-z0-9_\-+=%]+$", data):
            if self._debug_enabled:
                self.logger.debug(
                    f"Visitor data validation failed: invalid characters (length: {len(data)})"
                )
            return False

        # Additional length check - visitor data is usually substantial
        if len(data) < 5:
            if self._debug_enabled:
                self.logger.debug(
                    f"Visitor data validation failed: too short (length: {len(data)})"
                )
            return False

        if self._debug_enabled:
            data_hash = self._create_token_hash(data)
            self.logger.debug(
                f"Visitor data validation passed (hash: {data_hash}, length: {len(data)})"
            )

        return True

    def format_po_token_for_ytdlp(self, token: str) -> str:
        """
        Format PO token for yt-dlp compatibility (with web+ prefix).

        Args:
            token: Raw PO token

        Returns:
            Formatted token with web+ prefix
        """
        if not token:
            self.logger.warning("Attempted to format empty PO token")
            return ""

        # Add web+ prefix if not already present
        if token.startswith("web+"):
            formatted_token = token
        else:
            formatted_token = f"web+{token}"

        if self._debug_enabled:
            token_hash = self._create_token_hash(formatted_token)
            self.logger.debug(f"Formatted PO token for yt-dlp (hash: {token_hash})")

        return formatted_token

    async def extract_tokens_with_timeout(
        self, page, timeout: int = 90, video_url: Optional[str] = None
    ) -> TokenExtractionResult:
        """
        Extract visitor data with timeout handling and comprehensive monitoring.

        NOTE: PO Token extraction has been removed from AgentGo.
        PO Token should be provided by bgutil (localhost:4416).
        AgentGo's role is only to provide Cookies + Visitor Data.

        Args:
            page: Playwright page object
            timeout: Maximum time to spend on extraction
            video_url: Optional specific YouTube video URL to use for extraction

        Returns:
            TokenExtractionResult with extraction results and performance metrics
        """
        start_time = time.time()
        operation_id = f"combined_extraction_{int(start_time)}"

        self._log_secure(
            logging.INFO,
            f"Starting combined token extraction with {timeout}s timeout (operation: {operation_id})",
        )

        po_token = None
        visitor_data = None

        try:
            # IMPORTANT: Navigate to YouTube FIRST before extracting tokens
            # This prevents navigation conflicts when running extractions
            target_url = (
                video_url
                if video_url
                and video_url.startswith(
                    ("https://www.youtube.com/watch", "https://youtu.be/")
                )
                else "https://www.youtube.com/watch?v=_MLwQUebJUc"
            )

            current_url = page.url
            if "youtube.com" not in current_url:
                self.logger.info(
                    f"Pre-navigating to YouTube before token extraction: {target_url}"
                )
                navigation_success = False

                # Try navigation strategies
                for strategy_name, nav_url, wait_until in [
                    ("video page", target_url, "domcontentloaded"),
                    ("homepage", "https://www.youtube.com", "domcontentloaded"),
                    ("mobile", "https://m.youtube.com", "domcontentloaded"),
                ]:
                    if navigation_success:
                        break
                    try:
                        self.logger.info(f"Trying navigation strategy: {strategy_name}")
                        await page.goto(nav_url, wait_until=wait_until, timeout=60000)
                        navigation_success = True
                        self.logger.info(f"Navigation to {strategy_name} successful")
                    except Exception as e:
                        self.logger.warning(
                            f"Navigation to {strategy_name} failed: {e}"
                        )

                if not navigation_success:
                    self.logger.error("All pre-navigation strategies failed")
                    return TokenExtractionResult(
                        success=False,
                        po_token=None,
                        visitor_data=None,
                        error_message="Failed to navigate to YouTube",
                        extraction_method="combined",
                        extraction_duration=time.time() - start_time,
                    )

                # Wait for page to stabilize
                await asyncio.sleep(3)
            else:
                self.logger.info(f"Already on YouTube page: {current_url[:50]}...")

            # Extract visitor data FIRST (just JavaScript, no page interaction needed)
            # This should be done before PO token extraction which involves scrolling
            self.logger.info("Extracting visitor data (JavaScript only)...")
            try:
                visitor_data = await asyncio.wait_for(
                    self._extract_visitor_data_js_only(page), timeout=15
                )
                if visitor_data:
                    self.logger.info(
                        f"✅ Visitor data extracted successfully (length: {len(visitor_data)})"
                    )
            except asyncio.TimeoutError:
                self.logger.warning("Visitor data extraction timed out")
            except Exception as e:
                self.logger.warning(f"Visitor data extraction failed: {e}")

            # NOTE: PO Token extraction is SKIPPED here
            # PO Token should be provided by bgutil (localhost:4416), not AgentGo
            # AgentGo's role is only to provide Cookies + Visitor Data
            po_token = None

            # Handle exceptions from tasks
            if isinstance(po_token, Exception):
                self._log_secure(
                    logging.WARNING,
                    f"PO token extraction failed (operation: {operation_id}): {str(po_token)}",
                )
                po_token = None

            if isinstance(visitor_data, Exception):
                self._log_secure(
                    logging.WARNING,
                    f"Visitor data extraction failed (operation: {operation_id}): {str(visitor_data)}",
                )
                visitor_data = None

            extraction_duration = time.time() - start_time
            # Success is based on visitor_data only (PO Token comes from bgutil)
            success = bool(visitor_data)

            # Log extraction results with performance metrics
            if success:
                self._log_secure(
                    logging.INFO,
                    f"Token extraction completed successfully (operation: {operation_id})",
                    {
                        "duration_seconds": round(extraction_duration, 2),
                        "visitor_data_found": bool(visitor_data),
                        "timeout_used": timeout,
                    },
                )
            else:
                self._log_secure(
                    logging.WARNING,
                    f"Token extraction completed with no visitor data (operation: {operation_id})",
                    {
                        "duration_seconds": round(extraction_duration, 2),
                        "timeout_used": timeout,
                    },
                )

            return TokenExtractionResult(
                success=success,
                po_token=None,  # PO Token comes from bgutil, not AgentGo
                visitor_data=visitor_data,
                error_message=None if success else "No visitor data extracted",
                extraction_method="visitor_data_only",
                extraction_duration=extraction_duration,
            )

        except asyncio.TimeoutError:
            extraction_duration = time.time() - start_time
            error_msg = f"Token extraction timed out after {timeout}s"

            self._log_secure(
                logging.ERROR,
                f"Combined token extraction timed out (operation: {operation_id})",
                {
                    "timeout_seconds": timeout,
                    "actual_duration": round(extraction_duration, 2),
                },
            )

            self._metrics.record_extraction_error("unknown", "timeout", error_msg)

            return TokenExtractionResult(
                success=False,
                po_token=None,
                visitor_data=None,
                error_message=error_msg,
                extraction_method="combined",
                extraction_duration=extraction_duration,
            )

        except Exception as e:
            extraction_duration = time.time() - start_time
            error_msg = str(e)

            self._log_secure(
                logging.ERROR,
                f"Combined token extraction failed with error (operation: {operation_id}): {error_msg}",
                {"duration_seconds": round(extraction_duration, 2)},
            )

            self._metrics.record_extraction_error(
                "unknown", "extraction_error", error_msg
            )

            return TokenExtractionResult(
                success=False,
                po_token=None,
                visitor_data=None,
                error_message=error_msg,
                extraction_method="combined",
                extraction_duration=extraction_duration,
            )


class AgentGoService:
    """
    AgentGo browser automation service.

    Supports two modes:
    1. WebSocket + Playwright: For browser automation (wss://app.browsers.live)
    2. REST API: For simple scraping (https://app.agentgo.live/api)

    Primary responsibilities:
    1. Create browser sessions with built-in proxy (multiple regions supported)
    2. Handle YouTube access and cookie extraction for yt-dlp authentication
    3. Provide reliable YouTube access bypassing geo-restrictions and bot detection
    4. Support intelligent region routing with per-region cookie caching

    Supported regions: us, uk, de, fr, jp, sg, in, au, ca
    """

    # WebSocket endpoint for Playwright browser sessions
    WS_ENDPOINT = "wss://app.browsers.live"

    # REST API endpoint
    API_ENDPOINT = "https://app.agentgo.live/api"

    # Cookie file directory for persistence
    COOKIE_DIR = "/tmp/youtube_cookies"

    # Legacy cookie file path for backward compatibility
    COOKIE_FILE = "/tmp/youtube_cookies.txt"

    # Supported regions for browser sessions
    SUPPORTED_REGIONS = ["us", "uk", "de", "fr", "jp", "sg", "in", "au", "ca"]

    # Cookie expiry time (1 hour in seconds)
    COOKIE_EXPIRY = 3600

    def __init__(self):
        """Initialize AgentGo service with API configuration and comprehensive logging."""
        self.api_key = settings.agentgo_api_key
        self.youtube_email = settings.youtube_email
        self.youtube_password = settings.youtube_password
        self.default_region = getattr(settings, "agentgo_region", "us")

        # Initialize token extractor
        self.token_extractor = TokenExtractor()

        # Initialize metrics
        self._metrics = get_extraction_metrics()

        # Enhanced logging setup
        self.logger = logging.getLogger(__name__ + ".AgentGoService")
        self._debug_enabled = self.logger.isEnabledFor(logging.DEBUG)

        # Per-region cookie cache: {region: (cookie_file_path, timestamp)}
        self._region_cookies_cache: Dict[str, tuple] = {}

        # Legacy single-region cache for backward compatibility
        self._cookies_cache: Optional[str] = None
        self._cookies_timestamp: float = 0

        # Ensure cookie directory exists
        Path(self.COOKIE_DIR).mkdir(parents=True, exist_ok=True)

        # Log initialization status
        self._log_initialization_status()

    def _log_initialization_status(self):
        """Log AgentGo service initialization status with security considerations."""
        config_status = {
            "api_key_configured": bool(self.api_key),
            "youtube_email_configured": bool(self.youtube_email),
            "youtube_password_configured": bool(self.youtube_password),
            "default_region": self.default_region,
            "cookie_dir_exists": Path(self.COOKIE_DIR).exists(),
            "debug_logging": self._debug_enabled,
        }

        self.logger.info(f"AgentGo service initialized: {config_status}")

        if not self.is_configured():
            self.logger.warning(
                "AgentGo service not fully configured. "
                "Set AGENTGO_API_KEY, YOUTUBE_EMAIL, YOUTUBE_PASSWORD for full functionality."
            )
        elif self._debug_enabled:
            self.logger.debug(
                "AgentGo service fully configured and ready for token extraction"
            )

    def _log_agentgo_usage(
        self,
        region: str,
        video_url: Optional[str] = None,
        video_id: Optional[str] = None,
        success: bool = False,
        duration_seconds: float = 0,
        error_message: Optional[str] = None,
        extraction_method: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_id: Optional[int] = None
    ):
        """记录 AgentGo 使用到数据库"""
        try:
            from app.database import get_database
            db = get_database()
            db.log_agentgo_usage(
                region=region,
                video_url=video_url,
                video_id=video_id,
                success=success,
                duration_seconds=duration_seconds,
                error_message=error_message,
                extraction_method=extraction_method,
                ip_address=ip_address,
                user_id=user_id
            )
        except Exception as e:
            self.logger.error(f"Failed to log AgentGo usage: {e}")

    def _log_secure(
        self, level: int, message: str, sensitive_data: Optional[Dict[str, Any]] = None
    ):
        """
        Log message with secure handling of sensitive data.

        Args:
            level: Logging level
            message: Base message to log
            sensitive_data: Optional dict of sensitive data to sanitize
        """
        if sensitive_data:
            # Create sanitized version for logging
            sanitized = {}
            for key, value in sensitive_data.items():
                if key.lower() in ["api_key", "password", "email", "token", "po_token"]:
                    if value:
                        sanitized[key] = "[REDACTED]"
                    else:
                        sanitized[key] = None
                elif key.lower() in ["visitor_data"] and value:
                    sanitized[key] = f"[{len(value)} chars]"
                elif key.lower() in ["cookies"] and isinstance(value, list):
                    sanitized[key] = f"[{len(value)} cookies]"
                else:
                    sanitized[key] = value

            message = f"{message} - Data: {sanitized}"

        self.logger.log(level, message)

    def is_configured(self) -> bool:
        """Check if AgentGo is properly configured for full authentication."""
        return bool(self.api_key and self.youtube_email and self.youtube_password)

    def is_api_configured(self) -> bool:
        """Check if AgentGo API is configured (for session-only usage)."""
        return bool(self.api_key)

    def _is_cookie_expired(self, region: Optional[str] = None) -> bool:
        """
        Check if cached cookies have expired.

        Args:
            region: Region to check. If None, checks legacy cache.
        """
        if region:
            # Check region-specific cache
            if region not in self._region_cookies_cache:
                return True
            cookie_file, timestamp = self._region_cookies_cache[region]
            if not Path(cookie_file).exists():
                return True
            return (time.time() - timestamp) > self.COOKIE_EXPIRY
        else:
            # Legacy check
            if not self._cookies_cache or not Path(self._cookies_cache).exists():
                return True
            return (time.time() - self._cookies_timestamp) > self.COOKIE_EXPIRY

    def _get_cookie_file_path(self, region: str) -> str:
        """Get cookie file path for a specific region."""
        return str(Path(self.COOKIE_DIR) / f"cookies_{region}.txt")

    def _get_cached_cookie_for_region(self, region: str) -> Optional[str]:
        """
        Get cached cookie file path for a region if valid.

        Args:
            region: Region code

        Returns:
            Cookie file path if valid, None otherwise
        """
        if region not in self._region_cookies_cache:
            return None

        cookie_file, timestamp = self._region_cookies_cache[region]

        # Check if expired
        if (time.time() - timestamp) > self.COOKIE_EXPIRY:
            logger.debug(f"Cookies for region {region} have expired")
            return None

        # Check if file exists
        if not Path(cookie_file).exists():
            logger.debug(f"Cookie file for region {region} not found")
            return None

        return cookie_file

    def _build_ws_url(self, region: str = "us") -> str:
        """
        Build WebSocket connection URL with launch options.

        Args:
            region: Geographic region for the browser session

        Returns:
            WebSocket URL with encoded launch options
        """
        options = {
            "_apikey": self.api_key,
            "_region": region.lower(),
            "_disable_proxy": False,
        }

        url_option_value = urllib.parse.quote(json.dumps(options))
        return f"{self.WS_ENDPOINT}?launch-options={url_option_value}"

    async def _connect_and_get_cookies(
        self, region: str, timeout: int = 60
    ) -> List[Dict[str, Any]]:
        """
        Connect to AgentGo via WebSocket and extract YouTube cookies.
        Uses Playwright's connect method (not CDP) as AgentGo implements Playwright protocol.

        Args:
            region: Geographic region for the browser session
            timeout: Connection timeout in seconds

        Returns:
            List of cookie objects from the browser
        """
        if not HAS_PLAYWRIGHT:
            raise AgentGoError(
                "Playwright is not installed. Run: pip install playwright"
            )

        ws_url = self._build_ws_url(region)
        logger.info(f"Connecting to AgentGo browser (region: {region})...")

        cookies = []

        async with async_playwright() as p:
            browser = None
            context = None
            try:
                # AgentGo uses Playwright protocol, try connect() first
                try:
                    browser = await p.chromium.connect(ws_url, timeout=timeout * 1000)
                    logger.info("Connected via Playwright protocol")
                except Exception as e:
                    logger.warning(f"Playwright connect failed: {e}, trying CDP...")
                    # Fallback to CDP connection
                    browser = await p.chromium.connect_over_cdp(
                        ws_url, timeout=timeout * 1000
                    )
                    logger.info("Connected via CDP protocol")

                # Get or create context with error handling for Playwright compatibility issues
                try:
                    contexts = browser.contexts
                    if contexts:
                        context = contexts[0]
                        logger.info(
                            f"Using existing context (pages: {len(context.pages)})"
                        )
                    else:
                        context = await browser.new_context()
                        logger.info("Created new browser context")
                except KeyError as ke:
                    # Handle Playwright compatibility issue with AgentGo
                    logger.warning(
                        f"BrowserContext compatibility issue: {ke}, creating new context..."
                    )
                    context = await browser.new_context()
                    logger.info("Created new browser context after compatibility fix")

                # Get or create page
                try:
                    pages = context.pages
                    if pages:
                        page = pages[0]
                    else:
                        page = await context.new_page()
                except Exception as e:
                    logger.warning(f"Error getting pages: {e}, creating new page...")
                    page = await context.new_page()

                # Navigate to YouTube video for better cookie extraction
                target_url = "https://www.youtube.com/watch?v=_MLwQUebJUc"
                logger.info(f"Navigating to YouTube video: {target_url}")
                await page.goto(
                    target_url, wait_until="domcontentloaded", timeout=60000
                )
                await asyncio.sleep(2)

                # Extract cookies
                cookies = await context.cookies()
                logger.info(f"Extracted {len(cookies)} cookies from browser")

            except Exception as e:
                logger.error(f"Browser automation failed: {e}")
                raise AgentGoError(f"Failed to connect to AgentGo: {e}")
            finally:
                if browser:
                    try:
                        await browser.close()
                    except Exception:
                        pass

        return cookies

    async def _perform_youtube_login(self, page) -> bool:
        """
        Perform YouTube/Google login on the page.

        Args:
            page: Playwright page object

        Returns:
            True if login successful, False otherwise
        """
        try:
            logger.info("Attempting YouTube login...")

            # Navigate to Google login
            await page.goto(
                "https://accounts.google.com/ServiceLogin?service=youtube&hl=en",
                wait_until="networkidle",
                timeout=90000,  # Increased timeout for login page
            )
            await asyncio.sleep(2)

            # Enter email
            email_input = await page.wait_for_selector(
                'input[type="email"]',
                timeout=30000,  # Increased timeout for email input
            )
            await email_input.fill(self.youtube_email)
            await page.click("#identifierNext")
            await asyncio.sleep(3)

            # Enter password
            password_input = await page.wait_for_selector(
                'input[type="password"]',
                timeout=30000,  # Increased timeout for password input
            )
            await password_input.fill(self.youtube_password)
            await page.click("#passwordNext")
            await asyncio.sleep(5)

            # Navigate to YouTube video to set cookies with extended timeout
            target_url = "https://www.youtube.com/watch?v=_MLwQUebJUc"
            await page.goto(target_url, wait_until="networkidle", timeout=60000)
            await asyncio.sleep(2)

            # Verify login
            is_logged_in = await page.evaluate("""
                () => document.querySelector('ytd-topbar-menu-button-renderer') !== null ||
                      document.querySelector('#avatar-btn') !== null
            """)

            logger.info(f"Login {'successful' if is_logged_in else 'may have failed'}")
            return is_logged_in

        except Exception as e:
            logger.warning(f"Login failed: {e}")
            return False

    def _convert_to_netscape_format(self, cookies: List[Dict[str, Any]]) -> str:
        """
        Convert cookies to Netscape format for yt-dlp.

        Args:
            cookies: List of cookie objects

        Returns:
            Netscape format cookie string
        """
        lines = ["# Netscape HTTP Cookie File"]
        lines.append("# https://curl.haxx.se/rfc/cookie_spec.html")
        lines.append("# This is a generated file! Do not edit.\n")

        for cookie in cookies:
            # Extract cookie fields
            domain = cookie.get("domain", "")
            # Remove leading dot for subdomains flag
            subdomain = "TRUE" if domain.startswith(".") else "FALSE"
            domain = domain.lstrip(".")

            path = cookie.get("path", "/")
            secure = "TRUE" if cookie.get("secure", False) else "FALSE"

            # Handle expiry - use far future for session cookies
            expires = cookie.get("expires", 0) or cookie.get("expirationDate", 0)
            if not expires:
                expires = 2147483647  # Max 32-bit timestamp
            expires = int(expires)

            name = cookie.get("name", "")
            value = cookie.get("value", "")

            # Skip invalid cookies
            if not name or not domain:
                continue

            # Format: domain, subdomain, path, secure, expires, name, value
            line = (
                f".{domain}\t{subdomain}\t{path}\t{secure}\t{expires}\t{name}\t{value}"
            )
            lines.append(line)

        return "\n".join(lines)

    async def save_cookies_to_file(
        self, cookies: List[Dict[str, Any]], region: Optional[str] = None
    ) -> str:
        """
        Save cookies to Netscape format file for yt-dlp.

        Args:
            cookies: List of cookie objects
            region: Region code for region-specific cookie file

        Returns:
            Path to cookie file
        """
        cookie_content = self._convert_to_netscape_format(cookies)

        # Determine cookie file path
        if region:
            cookie_file = Path(self._get_cookie_file_path(region))
        else:
            cookie_file = Path(self.COOKIE_FILE)

        # Write to file
        cookie_file.write_text(cookie_content)
        cookie_path = str(cookie_file)

        logger.info(f"Cookies saved to: {cookie_path} (region: {region or 'default'})")

        # Update cache
        if region:
            self._region_cookies_cache[region] = (cookie_path, time.time())
        else:
            self._cookies_cache = cookie_path
            self._cookies_timestamp = time.time()

        return cookie_path

    async def get_youtube_authentication_bundle(
        self,
        region: Optional[str] = None,
        force_refresh: bool = False,
        video_url: Optional[str] = None,
    ) -> Optional[AuthenticationBundle]:
        """
        Get complete YouTube authentication bundle including cookies and tokens with comprehensive monitoring.

        Args:
            region: Geographic region for the browser session
            force_refresh: Force new extraction even if cached data exists
            video_url: Specific YouTube video URL to use for token extraction (improves success rate)

        Returns:
            AuthenticationBundle with cookies and tokens, or None if failed
        """
        operation_start = time.time()
        region = region or self.default_region
        operation_id = f"auth_bundle_{region}_{int(operation_start)}"

        self._log_secure(
            logging.INFO,
            f"Starting authentication bundle extraction (operation: {operation_id})",
            {
                "region": region,
                "force_refresh": force_refresh,
                "has_playwright": HAS_PLAYWRIGHT,
            },
        )

        # Record metrics
        self._metrics.record_extraction_attempt(region, operation_start)

        if not HAS_PLAYWRIGHT:
            error_msg = "Playwright is not installed. Run: pip install playwright"
            self.logger.error(error_msg)
            self._metrics.record_extraction_error(
                region, "missing_dependency", error_msg
            )
            return None

        # Validate region
        if region not in self.SUPPORTED_REGIONS:
            self.logger.warning(f"Unsupported region '{region}', falling back to 'us'")
            region = "us"

        # Check if we have valid cached cookies for this region (if not forcing refresh)
        cookie_file_path = None
        if not force_refresh:
            cached_cookie = self._get_cached_cookie_for_region(region)
            if cached_cookie:
                self._log_secure(
                    logging.INFO,
                    f"Using cached cookies for region: {region} (operation: {operation_id})",
                    {"cached_cookie_path": cached_cookie},
                )
                cookie_file_path = cached_cookie

        # Check configuration
        if not self.is_api_configured():
            error_msg = "AgentGo not configured. Required: AGENTGO_API_KEY"
            self.logger.warning(error_msg)
            self._metrics.record_extraction_error(region, "configuration", error_msg)
            return None

        # If we need to extract new data or don't have cached cookies
        if force_refresh or not cookie_file_path:
            try:
                self._log_secure(
                    logging.INFO,
                    f"Extracting fresh authentication bundle for region: {region} (operation: {operation_id})",
                )

                # Connect to AgentGo and extract tokens + cookies
                ws_url = self._build_ws_url(region)
                self.logger.info(
                    f"Connecting to AgentGo browser (region: {region}, operation: {operation_id})..."
                )

                # Temporarily clear proxy environment variables for browser connection
                original_env = {}
                proxy_vars = [
                    "https_proxy",
                    "http_proxy",
                    "all_proxy",
                    "HTTPS_PROXY",
                    "HTTP_PROXY",
                    "ALL_PROXY",
                ]
                for var in proxy_vars:
                    if var in os.environ:
                        original_env[var] = os.environ[var]
                        del os.environ[var]

                try:
                    async with async_playwright() as p:
                        browser = None
                        context = None
                        page = None
                        try:
                            # Connect to AgentGo browser with detailed logging
                            connection_start = time.time()

                            # Try Playwright protocol first, then CDP
                            try:
                                browser = await p.chromium.connect(
                                    ws_url, timeout=60000
                                )
                                connection_duration = time.time() - connection_start
                                self._log_secure(
                                    logging.INFO,
                                    f"Connected via Playwright protocol (operation: {operation_id})",
                                    {
                                        "connection_time_seconds": round(
                                            connection_duration, 2
                                        )
                                    },
                                )
                            except Exception as e:
                                self.logger.warning(
                                    f"Playwright connect failed: {e}, trying CDP..."
                                )
                                browser = await p.chromium.connect_over_cdp(
                                    ws_url, timeout=60000
                                )
                                connection_duration = time.time() - connection_start
                                self._log_secure(
                                    logging.INFO,
                                    f"Connected via CDP protocol (operation: {operation_id})",
                                    {
                                        "connection_time_seconds": round(
                                            connection_duration, 2
                                        )
                                    },
                                )

                            # Get or create context with error handling for Playwright compatibility issues
                            try:
                                contexts = browser.contexts
                                if contexts:
                                    context = contexts[0]
                                    self._log_secure(
                                        logging.INFO,
                                        f"Using existing context (operation: {operation_id})",
                                        {"pages_count": len(context.pages)},
                                    )
                                else:
                                    context = await browser.new_context()
                                    self.logger.info(
                                        f"Created new browser context (operation: {operation_id})"
                                    )
                            except KeyError as ke:
                                # Handle Playwright compatibility issue with AgentGo
                                # This happens when BrowserContext initialization fails due to missing 'options'
                                self.logger.warning(
                                    f"BrowserContext compatibility issue: {ke}, creating new context..."
                                )
                                context = await browser.new_context()
                                self.logger.info(
                                    f"Created new browser context after compatibility fix (operation: {operation_id})"
                                )

                            # Get or create page
                            try:
                                pages = context.pages
                                if pages:
                                    page = pages[0]
                                else:
                                    page = await context.new_page()
                            except Exception as e:
                                self.logger.warning(
                                    f"Error getting pages: {e}, creating new page..."
                                )
                                page = await context.new_page()

                            # Extract tokens using TokenExtractor with comprehensive logging
                            self.logger.info(
                                f"Starting token extraction (operation: {operation_id})..."
                            )
                            token_result = (
                                await self.token_extractor.extract_tokens_with_timeout(
                                    page, timeout=90, video_url=video_url
                                )
                            )

                            # Get browser IP information for proxy consistency
                            self.logger.info(
                                f"Getting browser IP information for proxy consistency (operation: {operation_id})..."
                            )
                            ip_info = await self.token_extractor.get_browser_ip_info(
                                page
                            )

                            # Extract cookies with logging
                            self.logger.info(
                                f"Extracting cookies (operation: {operation_id})..."
                            )
                            cookies_start = time.time()
                            cookies = await context.cookies()
                            cookies_duration = time.time() - cookies_start

                            if not cookies:
                                error_msg = "No cookies extracted from browser"
                                self.logger.error(
                                    f"{error_msg} (operation: {operation_id})"
                                )
                                self._metrics.record_extraction_error(
                                    region, "no_cookies", error_msg
                                )
                                raise AgentGoError(error_msg)

                            # Filter YouTube/Google related cookies with logging
                            youtube_cookies = [
                                c
                                for c in cookies
                                if any(
                                    domain in c.get("domain", "")
                                    for domain in [
                                        "youtube.com",
                                        "google.com",
                                        ".youtube.com",
                                        ".google.com",
                                    ]
                                )
                            ]

                            if not youtube_cookies:
                                self.logger.warning(
                                    f"No YouTube/Google cookies found, using all cookies (operation: {operation_id})"
                                )
                                youtube_cookies = cookies

                            self._log_secure(
                                logging.INFO,
                                f"Cookie extraction completed (operation: {operation_id})",
                                {
                                    "total_cookies": len(cookies),
                                    "youtube_cookies": len(youtube_cookies),
                                    "extraction_time_seconds": round(
                                        cookies_duration, 2
                                    ),
                                },
                            )

                            # Save cookies to file
                            cookie_file_path = await self.save_cookies_to_file(
                                youtube_cookies, region=region
                            )

                            # Create authentication bundle with comprehensive logging including IP info
                            auth_bundle = AuthenticationBundle(
                                cookies=youtube_cookies,
                                po_token=token_result.po_token,
                                visitor_data=token_result.visitor_data,
                                region=region,
                                extraction_timestamp=datetime.now(),
                                cookie_file_path=cookie_file_path,
                                browser_ip=ip_info.get("ip") if ip_info else None,
                                browser_country=ip_info.get("country")
                                if ip_info
                                else None,
                                browser_location=ip_info if ip_info else None,
                            )

                            # Log successful extraction with metrics
                            total_duration = time.time() - operation_start
                            self._log_secure(
                                logging.INFO,
                                f"Authentication bundle created successfully (operation: {operation_id})",
                                {
                                    "total_duration_seconds": round(total_duration, 2),
                                    "cookies_count": len(youtube_cookies),
                                    "has_po_token": bool(token_result.po_token),
                                    "has_visitor_data": bool(token_result.visitor_data),
                                    "token_extraction_duration": round(
                                        token_result.extraction_duration, 2
                                    ),
                                },
                            )

                            # Record successful metrics
                            self._metrics.record_extraction_success(
                                region,
                                total_duration,
                                bool(token_result.po_token),
                                bool(token_result.visitor_data),
                            )

                            return auth_bundle

                        except Exception as e:
                            total_duration = time.time() - operation_start
                            error_msg = f"Browser automation failed: {e}"
                            self._log_secure(
                                logging.ERROR,
                                f"Browser automation failed (operation: {operation_id})",
                                {
                                    "error": str(e),
                                    "duration_seconds": round(total_duration, 2),
                                },
                            )
                            self._metrics.record_extraction_error(
                                region, "browser_automation", str(e)
                            )
                            raise AgentGoError(error_msg)
                        finally:
                            if browser:
                                try:
                                    await browser.close()
                                    self.logger.debug(
                                        f"Browser closed successfully (operation: {operation_id})"
                                    )
                                except Exception as close_error:
                                    self.logger.warning(
                                        f"Error closing browser (operation: {operation_id}): {close_error}"
                                    )
                finally:
                    # Restore original proxy environment variables
                    for var, value in original_env.items():
                        os.environ[var] = value

            except Exception as e:
                total_duration = time.time() - operation_start
                self._log_secure(
                    logging.ERROR,
                    f"Failed to get authentication bundle for region {region} (operation: {operation_id})",
                    {"error": str(e), "duration_seconds": round(total_duration, 2)},
                )
                self._metrics.record_extraction_error(region, "general_error", str(e))
                return None

        else:
            # Use cached cookies without tokens (fallback mode)
            try:
                self._log_secure(
                    logging.INFO,
                    f"Creating authentication bundle from cached cookies (operation: {operation_id})",
                    {"cookie_file_path": cookie_file_path},
                )

                # Load cookies from file
                cookie_file = Path(cookie_file_path)
                if not cookie_file.exists():
                    error_msg = f"Cached cookie file not found: {cookie_file_path}"
                    self.logger.error(f"{error_msg} (operation: {operation_id})")
                    return None

                # Parse cookies from Netscape format (simplified - just return empty list for now)
                # In a real implementation, you'd parse the Netscape format back to cookie objects
                cookies = []  # This would be parsed from the file

                auth_bundle = AuthenticationBundle(
                    cookies=cookies,
                    po_token=None,
                    visitor_data=None,
                    region=region,
                    extraction_timestamp=datetime.now(),
                    cookie_file_path=cookie_file_path,
                )

                total_duration = time.time() - operation_start
                self._log_secure(
                    logging.INFO,
                    f"Using cached authentication bundle for region {region} (operation: {operation_id})",
                    {
                        "cookies_only": True,
                        "duration_seconds": round(total_duration, 2),
                    },
                )
                return auth_bundle

            except Exception as e:
                total_duration = time.time() - operation_start
                self._log_secure(
                    logging.ERROR,
                    f"Failed to create authentication bundle from cached cookies (operation: {operation_id})",
                    {"error": str(e), "duration_seconds": round(total_duration, 2)},
                )
                return None

    async def get_youtube_cookies(
        self,
        force_refresh: bool = False,
        region: Optional[str] = None,
        max_retries: int = 2,
    ) -> Optional[AuthenticationBundle]:
        """
        Get YouTube authentication bundle using AgentGo browser automation.
        Main entry point for authentication extraction with region-aware caching.

        Uses WebSocket + Playwright to connect to AgentGo's remote browser
        and extract cookies and tokens for yt-dlp authentication.

        Args:
            force_refresh: Force new extraction even if cached data exists
            region: Geographic region for the browser session.
                   Authentication data is cached per-region for optimal routing.
            max_retries: Maximum number of retry attempts

        Returns:
            AuthenticationBundle with cookies and tokens, or None if failed
        """
        logger.info(
            f"Getting YouTube authentication bundle for region: {region or self.default_region}"
        )

        # Delegate to the new comprehensive method
        return await self.get_youtube_authentication_bundle(
            region=region, force_refresh=force_refresh
        )

    async def get_youtube_cookies_file_path(
        self,
        force_refresh: bool = False,
        region: Optional[str] = None,
        max_retries: int = 2,
    ) -> Optional[str]:
        """
        Get YouTube cookie file path using AgentGo browser automation.
        Backward compatibility method that returns cookie file path.

        Args:
            force_refresh: Force new extraction even if cached data exists
            region: Geographic region for the browser session
            max_retries: Maximum number of retry attempts

        Returns:
            Path to cookie file, or None if failed
        """
        auth_bundle = await self.get_youtube_cookies(
            force_refresh=force_refresh, region=region
        )

        if auth_bundle and auth_bundle.cookie_file_path:
            return auth_bundle.cookie_file_path

        return None

    def get_cached_cookie_file(self, region: Optional[str] = None) -> Optional[str]:
        """
        Get path to cached cookie file if exists.

        Args:
            region: Region code. If None, returns legacy cache path.

        Returns:
            Cookie file path if exists, None otherwise
        """
        if region:
            return self._get_cached_cookie_for_region(region)

        # Legacy behavior
        if Path(self.COOKIE_FILE).exists():
            return self.COOKIE_FILE
        return None

    def get_all_cached_regions(self) -> Dict[str, str]:
        """
        Get all regions with valid cached cookies.

        Returns:
            Dict of {region: cookie_file_path} for valid caches
        """
        valid_caches = {}
        for region in self.SUPPORTED_REGIONS:
            cookie_file = self._get_cached_cookie_for_region(region)
            if cookie_file:
                valid_caches[region] = cookie_file
        return valid_caches

    def invalidate_region_cache(self, region: str):
        """Invalidate cached cookies for a specific region with logging."""
        if region in self._region_cookies_cache:
            del self._region_cookies_cache[region]
            self.logger.info(f"Invalidated cookie cache for region: {region}")
        else:
            self.logger.debug(f"No cache to invalidate for region: {region}")

    def get_performance_metrics(self) -> Dict[str, Any]:
        """Get comprehensive performance metrics for monitoring."""
        return self._metrics.get_performance_summary()

    def log_performance_summary(self):
        """Log current performance metrics summary."""
        self._metrics.log_performance_summary()

    def get_debug_info(self) -> Dict[str, Any]:
        """Get debug information for troubleshooting authentication issues."""
        cached_regions = list(self._region_cookies_cache.keys())
        valid_cached_regions = []

        for region in cached_regions:
            if not self._is_cookie_expired(region):
                valid_cached_regions.append(region)

        debug_info = {
            "service_configured": self.is_configured(),
            "api_configured": self.is_api_configured(),
            "default_region": self.default_region,
            "supported_regions": self.SUPPORTED_REGIONS,
            "cached_regions": cached_regions,
            "valid_cached_regions": valid_cached_regions,
            "cookie_dir_exists": Path(self.COOKIE_DIR).exists(),
            "cookie_expiry_seconds": self.COOKIE_EXPIRY,
            "has_playwright": HAS_PLAYWRIGHT,
            "has_websockets": HAS_WEBSOCKETS,
            "performance_metrics": self.get_performance_metrics(),
        }

        self.logger.debug(f"Debug info: {debug_info}")
        return debug_info

    async def extract_video_urls_directly(
        self,
        video_url: str,
        region: Optional[str] = None,
        resolution: str = "720",
        timeout: int = 120,
    ) -> Optional[Dict[str, Any]]:
        """
        Extract YouTube video direct URLs using AgentGo browser.

        This method uses AgentGo's cloud browser to access YouTube directly,
        capturing the googlevideo.com URLs from network requests.
        The entire process happens through AgentGo's proxy IP.

        Args:
            video_url: YouTube video URL to extract
            region: Geographic region for the browser session
            resolution: Preferred resolution (360, 480, 720, 1080, best)
            timeout: Maximum time to wait for extraction

        Returns:
            Dict with video info and download URLs, or None if failed
        """
        if not HAS_PLAYWRIGHT:
            self.logger.error("Playwright is not installed")
            return None

        region = region or self.default_region
        operation_id = f"direct_extract_{region}_{int(time.time())}"
        start_time = time.time()

        self.logger.info(
            f"Starting direct video URL extraction via AgentGo "
            f"(operation: {operation_id}, region: {region}, video: {video_url[:50]}...)"
        )

        # Store captured URLs
        captured_urls = {"video": [], "audio": [], "combined": []}
        video_info = {}

        async with async_playwright() as p:
            browser = None
            context = None

            try:
                # Connect to AgentGo browser
                ws_url = self._build_ws_url(region)
                self.logger.info(f"Connecting to AgentGo browser (region: {region})...")

                try:
                    browser = await p.chromium.connect(ws_url, timeout=60000)
                    self.logger.info("Connected via Playwright protocol")
                except Exception as e:
                    self.logger.warning(
                        f"Playwright connect failed: {e}, trying CDP..."
                    )
                    browser = await p.chromium.connect_over_cdp(ws_url, timeout=60000)
                    self.logger.info("Connected via CDP protocol")

                # Get or create context
                try:
                    contexts = browser.contexts
                    if contexts:
                        context = contexts[0]
                    else:
                        context = await browser.new_context()
                except Exception:
                    context = await browser.new_context()

                # Get or create page
                try:
                    pages = context.pages
                    page = pages[0] if pages else await context.new_page()
                except Exception:
                    page = await context.new_page()

                # Set up request interception to capture video URLs
                def handle_response(response):
                    try:
                        url = response.url

                        # Capture googlevideo.com URLs (direct video/audio streams)
                        if "googlevideo.com" in url and response.status == 200:
                            content_type = response.headers.get("content-type", "")

                            # Parse URL parameters
                            parsed = urllib.parse.urlparse(url)
                            params = urllib.parse.parse_qs(parsed.query)

                            url_info = {
                                "url": url,
                                "mime": params.get("mime", ["unknown"])[0],
                                "itag": params.get("itag", [""])[0],
                                "quality": params.get("quality", [""])[0]
                                if "quality" in params
                                else None,
                                "content_type": content_type,
                            }

                            # Categorize by type
                            mime = url_info["mime"]
                            if "video" in mime and "audio" in mime:
                                captured_urls["combined"].append(url_info)
                                self.logger.info(
                                    f"Captured combined stream: itag={url_info['itag']}"
                                )
                            elif "video" in mime:
                                captured_urls["video"].append(url_info)
                                self.logger.info(
                                    f"Captured video stream: itag={url_info['itag']}"
                                )
                            elif "audio" in mime:
                                captured_urls["audio"].append(url_info)
                                self.logger.info(
                                    f"Captured audio stream: itag={url_info['itag']}"
                                )

                    except Exception as e:
                        self.logger.debug(f"Error processing response: {e}")

                page.on("response", handle_response)

                # Navigate to the video page
                self.logger.info(f"Navigating to YouTube video: {video_url}")
                await page.goto(video_url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(3)

                # Extract video info AND streaming URLs directly from page JavaScript
                # This is more reliable than network interception
                try:
                    page_data = await page.evaluate("""
                        () => {
                            try {
                                const result = {
                                    info: {},
                                    streams: {
                                        formats: [],
                                        adaptiveFormats: []
                                    }
                                };
                                
                                // Get video info
                                const titleEl = document.querySelector('h1.ytd-video-primary-info-renderer, h1.title');
                                result.info.title = titleEl ? titleEl.textContent.trim() : document.title.replace(' - YouTube', '');
                                
                                // Try to get from ytInitialPlayerResponse
                                if (window.ytInitialPlayerResponse) {
                                    const pr = window.ytInitialPlayerResponse;
                                    const vd = pr.videoDetails || {};
                                    
                                    result.info.video_id = vd.videoId || '';
                                    result.info.title = vd.title || result.info.title;
                                    result.info.duration = parseInt(vd.lengthSeconds) || 0;
                                    result.info.author = vd.author || '';
                                    result.info.view_count = parseInt(vd.viewCount) || 0;
                                    result.info.thumbnail = vd.thumbnail?.thumbnails?.[0]?.url || '';
                                    
                                    // Get streaming data - THIS IS THE KEY!
                                    const sd = pr.streamingData || {};
                                    
                                    // Combined formats (video+audio in one stream)
                                    if (sd.formats) {
                                        result.streams.formats = sd.formats.map(f => ({
                                            url: f.url || null,
                                            signatureCipher: f.signatureCipher || null,
                                            itag: f.itag,
                                            mimeType: f.mimeType,
                                            qualityLabel: f.qualityLabel,
                                            width: f.width,
                                            height: f.height,
                                            bitrate: f.bitrate,
                                            contentLength: f.contentLength
                                        }));
                                    }
                                    
                                    // Adaptive formats (separate video and audio)
                                    if (sd.adaptiveFormats) {
                                        result.streams.adaptiveFormats = sd.adaptiveFormats.map(f => ({
                                            url: f.url || null,
                                            signatureCipher: f.signatureCipher || null,
                                            itag: f.itag,
                                            mimeType: f.mimeType,
                                            qualityLabel: f.qualityLabel || null,
                                            width: f.width || null,
                                            height: f.height || null,
                                            bitrate: f.bitrate,
                                            contentLength: f.contentLength,
                                            audioQuality: f.audioQuality || null
                                        }));
                                    }
                                }
                                
                                return result;
                            } catch (e) {
                                return { error: e.message };
                            }
                        }
                    """)

                    video_info = page_data.get("info", {})
                    streams = page_data.get("streams", {})

                    self.logger.info(
                        f"Extracted video info: {video_info.get('title', 'Unknown')[:50]}"
                    )
                    self.logger.info(
                        f"Found streams: {len(streams.get('formats', []))} combined, "
                        f"{len(streams.get('adaptiveFormats', []))} adaptive"
                    )

                    # Process formats from JavaScript extraction
                    for fmt in streams.get("formats", []):
                        if fmt.get("url"):
                            url_info = {
                                "url": fmt["url"],
                                "itag": str(fmt.get("itag", "")),
                                "mime": fmt.get("mimeType", ""),
                                "quality": fmt.get("qualityLabel", ""),
                                "height": fmt.get("height"),
                                "width": fmt.get("width"),
                            }
                            captured_urls["combined"].append(url_info)
                            self.logger.info(
                                f"Found combined format: {fmt.get('qualityLabel')} (itag={fmt.get('itag')})"
                            )
                        elif fmt.get("signatureCipher"):
                            self.logger.debug(
                                f"Combined format {fmt.get('qualityLabel')} (itag={fmt.get('itag')}) requires signature decryption"
                            )

                    # Track stats for adaptive formats
                    adaptive_with_url = 0
                    adaptive_with_cipher = 0

                    for fmt in streams.get("adaptiveFormats", []):
                        mime = fmt.get("mimeType", "")

                        if fmt.get("url"):
                            adaptive_with_url += 1
                            url_info = {
                                "url": fmt["url"],
                                "itag": str(fmt.get("itag", "")),
                                "mime": mime,
                                "quality": fmt.get("qualityLabel", ""),
                                "height": fmt.get("height"),
                                "width": fmt.get("width"),
                                "audioQuality": fmt.get("audioQuality"),
                            }

                            if "video" in mime:
                                captured_urls["video"].append(url_info)
                                self.logger.info(
                                    f"Found video format: {fmt.get('qualityLabel')} (itag={fmt.get('itag')})"
                                )
                            elif "audio" in mime:
                                captured_urls["audio"].append(url_info)
                                self.logger.info(
                                    f"Found audio format: {fmt.get('audioQuality')} (itag={fmt.get('itag')})"
                                )
                        elif fmt.get("signatureCipher"):
                            adaptive_with_cipher += 1
                            # Log what we're missing due to signature cipher
                            if "video" in mime:
                                self.logger.debug(
                                    f"Video format {fmt.get('qualityLabel')} (itag={fmt.get('itag')}) "
                                    f"requires signature decryption - skipping"
                                )
                            elif "audio" in mime:
                                self.logger.debug(
                                    f"Audio format {fmt.get('audioQuality')} (itag={fmt.get('itag')}) "
                                    f"requires signature decryption - skipping"
                                )

                    self.logger.info(
                        f"Adaptive formats: {adaptive_with_url} with direct URL, "
                        f"{adaptive_with_cipher} require signature decryption"
                    )

                    # If most formats require signature decryption, log a warning
                    if (
                        adaptive_with_cipher > adaptive_with_url
                        and adaptive_with_url < 5
                    ):
                        self.logger.warning(
                            f"Most adaptive formats ({adaptive_with_cipher}/{adaptive_with_url + adaptive_with_cipher}) "
                            f"require signature decryption. Consider using yt-dlp for better format support."
                        )

                except Exception as e:
                    self.logger.warning(f"Failed to extract from JavaScript: {e}")

                # Try to trigger video playback to capture more URLs
                try:
                    # Click play button
                    play_selectors = [
                        "button.ytp-large-play-button",
                        "button.ytp-play-button",
                        "#movie_player",
                        "video",
                    ]

                    for selector in play_selectors:
                        try:
                            element = page.locator(selector).first
                            if await element.is_visible(timeout=2000):
                                await element.click(timeout=3000)
                                self.logger.info(f"Clicked play element: {selector}")
                                await asyncio.sleep(2)
                                break
                        except Exception:
                            continue

                    # Try to change quality to get different streams
                    await page.evaluate("""
                        () => {
                            const video = document.querySelector('video');
                            if (video) {
                                video.currentTime = 5;
                                video.play();
                            }
                        }
                    """)

                except Exception as e:
                    self.logger.debug(f"Play interaction failed: {e}")

                # Wait for video streams to be captured
                self.logger.info("Waiting for video streams to be captured...")
                await asyncio.sleep(8)

                # Log browser IP for verification
                try:
                    ip_info = await self.token_extractor.get_browser_ip_info(page)
                    if ip_info:
                        self.logger.info(
                            f"AgentGo browser IP: {ip_info.get('ip')} ({ip_info.get('country', 'Unknown')})"
                        )
                except Exception:
                    pass

            except Exception as e:
                self.logger.error(f"Direct extraction failed: {e}")
                # Log failed extraction
                video_id = None
                try:
                    import re
                    match = re.search(r'(?:v=|/)([0-9A-Za-z_-]{11})', video_url)
                    if match:
                        video_id = match.group(1)
                except Exception:
                    pass
                self._log_agentgo_usage(
                    region=region,
                    video_url=video_url,
                    video_id=video_id,
                    success=False,
                    duration_seconds=time.time() - start_time,
                    error_message=str(e),
                    extraction_method="agentgo_direct"
                )
                return None

            finally:
                if browser:
                    try:
                        await browser.close()
                    except Exception:
                        pass

        # Process captured URLs
        duration = time.time() - start_time

        # Extract video ID for logging
        video_id = None
        try:
            import re
            match = re.search(r'(?:v=|/)([0-9A-Za-z_-]{11})', video_url)
            if match:
                video_id = match.group(1)
        except Exception:
            pass

        if not captured_urls["video"] and not captured_urls["combined"]:
            self.logger.warning(f"No video URLs captured after {duration:.2f}s")
            # Log failed extraction
            self._log_agentgo_usage(
                region=region,
                video_url=video_url,
                video_id=video_id,
                success=False,
                duration_seconds=duration,
                error_message="No video URLs captured",
                extraction_method="agentgo_direct"
            )
            return None

        # Select best URLs based on resolution preference
        result = self._select_best_urls(captured_urls, resolution)
        result["video_info"] = video_info
        result["extraction_time"] = duration
        result["region"] = region
        result["method"] = "agentgo_direct"

        self.logger.info(
            f"Direct extraction completed in {duration:.2f}s: "
            f"video={bool(result.get('video_url'))}, audio={bool(result.get('audio_url'))}"
        )

        # Log successful extraction
        self._log_agentgo_usage(
            region=region,
            video_url=video_url,
            video_id=video_id,
            success=True,
            duration_seconds=duration,
            extraction_method="agentgo_direct"
        )

        return result

    def _select_best_urls(
        self, captured_urls: Dict[str, List], resolution: str
    ) -> Dict[str, Any]:
        """
        Select best video and audio URLs from captured streams.

        For high resolutions (720p+), prefer adaptive streams (video + audio separate).
        For low resolutions (360p/480p), can use combined streams if available.

        Args:
            captured_urls: Dict with 'video', 'audio', 'combined' lists
            resolution: Preferred resolution

        Returns:
            Dict with video_url, audio_url, and format info
        """
        result = {
            "video_url": None,
            "audio_url": None,
            "video_format": None,
            "audio_format": None,
            "needs_merge": False,
            "all_formats": {
                "video": captured_urls.get("video", []),
                "audio": captured_urls.get("audio", []),
                "combined": captured_urls.get("combined", []),
            },
        }

        # Quality mapping for itags
        itag_quality = {
            # Combined (video+audio) - limited to 360p/720p
            "18": 360,
            "22": 720,
            # Video only (adaptive) - supports all resolutions
            "160": 144,
            "133": 240,
            "134": 360,
            "135": 480,
            "136": 720,
            "137": 1080,
            "264": 1440,
            "266": 2160,
            "298": 720,
            "299": 1080,
            "302": 720,
            "303": 1080,
            "308": 1440,
            "315": 2160,
            "330": 144,
            "331": 240,
            "332": 360,
            "333": 480,
            "334": 720,
            "335": 1080,
            "336": 1440,
            "337": 2160,
            # Audio only
            "139": 48,
            "140": 128,
            "141": 256,
            "171": 128,
            "172": 256,
            "249": 50,
            "250": 70,
            "251": 160,
        }

        target_height = int(resolution) if resolution.isdigit() else 1080

        # For high resolution (720p+), prefer adaptive streams
        # For low resolution (360p/480p), can use combined if no adaptive available
        prefer_adaptive = target_height >= 720

        # Try adaptive streams first for high resolution
        if prefer_adaptive and captured_urls["video"]:
            # Filter video streams by resolution
            suitable_video = []
            for v in captured_urls["video"]:
                height = v.get("height") or itag_quality.get(v["itag"], 0)
                if height and height <= target_height:
                    suitable_video.append((v, height))

            if not suitable_video:
                # No suitable resolution, get closest
                for v in captured_urls["video"]:
                    height = v.get("height") or itag_quality.get(v["itag"], 0)
                    if height:
                        suitable_video.append((v, height))

            if suitable_video:
                # Select highest quality within target
                best_video = max(suitable_video, key=lambda x: x[1])[0]
                result["video_url"] = best_video["url"]
                result["video_format"] = best_video
                result["needs_merge"] = True

                self.logger.info(
                    f"Selected adaptive video: {best_video.get('quality') or best_video.get('height')}p "
                    f"(itag={best_video.get('itag')})"
                )

                # Select best audio stream
                if captured_urls["audio"]:
                    best_audio = max(
                        captured_urls["audio"],
                        key=lambda x: itag_quality.get(x["itag"], 0),
                    )
                    result["audio_url"] = best_audio["url"]
                    result["audio_format"] = best_audio

                    self.logger.info(
                        f"Selected audio: {best_audio.get('audioQuality', 'unknown')} "
                        f"(itag={best_audio.get('itag')})"
                    )

                return result

        # Fallback to combined streams for low resolution or if no adaptive available
        if captured_urls["combined"]:
            # Filter by target resolution
            suitable_combined = []
            for c in captured_urls["combined"]:
                height = c.get("height") or itag_quality.get(c["itag"], 0)
                if height and height <= target_height:
                    suitable_combined.append((c, height))

            if not suitable_combined:
                suitable_combined = [
                    (c, itag_quality.get(c["itag"], 0))
                    for c in captured_urls["combined"]
                ]

            if suitable_combined:
                best_combined = max(suitable_combined, key=lambda x: x[1])[0]
                result["video_url"] = best_combined["url"]
                result["video_format"] = best_combined

                self.logger.info(
                    f"Selected combined stream: {best_combined.get('quality') or best_combined.get('height')}p "
                    f"(itag={best_combined.get('itag')})"
                )
                return result

        # Last resort: any video stream
        if captured_urls["video"]:
            best_video = max(
                captured_urls["video"],
                key=lambda x: x.get("height") or itag_quality.get(x["itag"], 0),
            )
            result["video_url"] = best_video["url"]
            result["video_format"] = best_video
            result["needs_merge"] = True

            if captured_urls["audio"]:
                best_audio = max(
                    captured_urls["audio"], key=lambda x: itag_quality.get(x["itag"], 0)
                )
                result["audio_url"] = best_audio["url"]
                result["audio_format"] = best_audio

        return result

        # Select best audio stream
        if captured_urls["audio"]:
            best_audio = max(
                captured_urls["audio"], key=lambda x: itag_quality.get(x["itag"], 0)
            )
            result["audio_url"] = best_audio["url"]
            result["audio_format"] = best_audio

        return result


# Global service instance
_agentgo_service: Optional[AgentGoService] = None


def get_agentgo_service() -> AgentGoService:
    """Get or create global AgentGo service instance."""
    global _agentgo_service
    if _agentgo_service is None:
        _agentgo_service = AgentGoService()
    return _agentgo_service


async def fetch_youtube_cookies_with_agentgo(
    force_refresh: bool = False, region: Optional[str] = None
) -> Optional[str]:
    """
    Convenience function to fetch YouTube cookies using AgentGo.
    Returns cookie file path for backward compatibility.

    Args:
        force_refresh: Force new login
        region: Geographic region for the browser session

    Returns:
        Path to cookie file, or None if failed
    """
    service = get_agentgo_service()
    return await service.get_youtube_cookies_file_path(
        force_refresh=force_refresh, region=region
    )


async def fetch_youtube_authentication_bundle(
    force_refresh: bool = False, region: Optional[str] = None
) -> Optional[AuthenticationBundle]:
    """
    Convenience function to fetch YouTube authentication bundle using AgentGo.

    Args:
        force_refresh: Force new extraction
        region: Geographic region for the browser session

    Returns:
        AuthenticationBundle with cookies and tokens, or None if failed
    """
    service = get_agentgo_service()
    return await service.get_youtube_cookies(force_refresh=force_refresh, region=region)


async def get_cookies_for_region(region: str) -> Optional[str]:
    """
    Get or fetch cookies for a specific region.
    Returns cookie file path for backward compatibility.

    Args:
        region: Geographic region code (us, uk, de, fr, jp, sg, in, au, ca)

    Returns:
        Path to cookie file, or None if failed
    """
    service = get_agentgo_service()
    return await service.get_youtube_cookies_file_path(region=region)


async def get_authentication_bundle_for_region(
    region: str,
) -> Optional[AuthenticationBundle]:
    """
    Get or fetch authentication bundle for a specific region.

    Args:
        region: Geographic region code (us, uk, de, fr, jp, sg, in, au, ca)

    Returns:
        AuthenticationBundle with cookies and tokens, or None if failed
    """
    service = get_agentgo_service()
    return await service.get_youtube_cookies(region=region)
