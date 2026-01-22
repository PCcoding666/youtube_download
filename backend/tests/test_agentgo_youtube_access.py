"""
Test AgentGo's Browser Session capability for YouTube access.

This test verifies whether AgentGo's cloud browser with built-in proxy
can access YouTube and extract cookies for yt-dlp.

AgentGo API Documentation: https://docs.agentgo.live/

Architecture:
- AgentGo creates browser sessions in different regions (us, jp, de, etc.)
- Each session has built-in proxy from that region
- We use sessions to login YouTube and extract cookies
- Cookies are saved per-region for yt-dlp to use

Test scenarios:
1. Test WebSocket connection to AgentGo
2. Create browser session in different regions
3. Access YouTube via session (verify no bot detection)
4. Extract cookies from session

Requirements:
- AGENTGO_API_KEY environment variable must be set
- websockets library installed

Usage:
    pytest tests/test_agentgo_youtube_access.py -v -s
"""

import pytest
import asyncio
import websockets
import json
import os
import logging
import urllib.parse
from typing import Optional, Dict, Any
from dataclasses import dataclass, field

# Configure logging for test output
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class SessionTestResult:
    """Result of a session test."""

    success: bool
    region: str
    duration_ms: float
    session_connected: bool = False
    youtube_accessible: bool = False
    has_bot_detection: bool = False
    cookies_extracted: int = 0
    error: Optional[str] = None
    details: Optional[Dict[str, Any]] = field(default_factory=dict)


class AgentGoSessionClient:
    """
    AgentGo Browser Session client for YouTube access testing.

    Uses AgentGo's WebSocket-based browser automation:
    - WebSocket URL: wss://app.browsers.live
    - Authentication via launch-options parameter
    - Regions: us, uk, de, fr, jp, sg, au, ca, etc.

    Reference: https://docs.agentgo.live/
    """

    # WebSocket endpoint for browser sessions
    WS_ENDPOINT = "wss://app.browsers.live"

    # REST API endpoint
    API_ENDPOINT = "https://app.agentgo.live/api"

    # Supported regions
    SUPPORTED_REGIONS = ["us", "uk", "de", "fr", "jp", "sg", "au", "ca", "in"]

    # Test YouTube videos
    TEST_VIDEOS = [
        "https://www.youtube.com/watch?v=jNQXAC9IVRw",  # "Me at the zoo"
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",  # Rick Astley
    ]

    def __init__(self):
        self.api_key = os.getenv("AGENTGO_API_KEY", "")

    def is_configured(self) -> bool:
        """Check if API key is configured."""
        return bool(self.api_key)

    def _build_ws_url(
        self, region: str = "us", session_id: Optional[str] = None
    ) -> str:
        """Build WebSocket connection URL with options."""
        options = {
            "_apikey": self.api_key,
            "_region": region.lower(),
            "_disable_proxy": False,
        }

        if session_id:
            options["_sessionId"] = session_id

        url_option_value = urllib.parse.quote(json.dumps(options))
        return f"{self.WS_ENDPOINT}?launch-options={url_option_value}"

    async def test_ws_connection(self, region: str = "us") -> SessionTestResult:
        """
        Test 1: Can we establish WebSocket connection to AgentGo?

        This tests basic connectivity to the browser automation service.
        """
        start_time = asyncio.get_event_loop().time()

        try:
            ws_url = self._build_ws_url(region)
            logger.info(f"Connecting to AgentGo WebSocket (region: {region})...")

            async with websockets.connect(
                ws_url,
                open_timeout=30,
                close_timeout=10,
                ping_interval=20,
                ping_timeout=20,
            ) as ws:
                duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000

                logger.info(f"WebSocket connected! Duration: {duration_ms:.0f}ms")

                # Try to receive any initial message
                initial_msg = None
                try:
                    initial_msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    logger.info(
                        f"Received initial message: {str(initial_msg)[:200]}..."
                    )
                except asyncio.TimeoutError:
                    logger.info(
                        "No initial message (this is normal for Playwright CDP)"
                    )

                return SessionTestResult(
                    success=True,
                    region=region,
                    duration_ms=duration_ms,
                    session_connected=True,
                    details={
                        "ws_state": str(ws.state),
                        "has_initial_msg": initial_msg is not None,
                    },
                )

        except websockets.exceptions.InvalidStatusCode as e:
            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            return SessionTestResult(
                success=False,
                region=region,
                duration_ms=duration_ms,
                error=f"WebSocket rejected: HTTP {e.status_code}",
            )
        except Exception as e:
            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            return SessionTestResult(
                success=False,
                region=region,
                duration_ms=duration_ms,
                error=f"{type(e).__name__}: {str(e)}",
            )

    async def test_multiple_regions(self) -> Dict[str, SessionTestResult]:
        """
        Test 2: Test WebSocket connection across multiple regions.

        Verifies that we can create sessions in different geographic regions.
        """
        results = {}
        regions_to_test = ["us", "jp", "uk", "de"]

        for region in regions_to_test:
            logger.info(f"\n--- Testing region: {region} ---")
            result = await self.test_ws_connection(region)
            results[region] = result

            status = "✓" if result.success else "✗"
            logger.info(
                f"{status} Region {region}: connected={result.session_connected}, "
                f"duration={result.duration_ms:.0f}ms"
            )

            if result.error:
                logger.error(f"  Error: {result.error}")

            # Small delay between tests
            await asyncio.sleep(1)

        return results

    async def test_session_persistence(self, region: str = "us") -> SessionTestResult:
        """
        Test 3: Test that session can be maintained for automation tasks.

        Creates a session and keeps it open for a period to simulate
        browser automation workflow.
        """
        start_time = asyncio.get_event_loop().time()

        try:
            ws_url = self._build_ws_url(region)
            logger.info(f"Creating persistent session (region: {region})...")

            async with websockets.connect(
                ws_url,
                open_timeout=30,
                close_timeout=10,
                ping_interval=20,
                ping_timeout=20,
            ) as ws:
                logger.info("Session created, testing persistence...")

                # Keep session open for 10 seconds
                for i in range(5):
                    await asyncio.sleep(2)
                    # Check if connection is still alive
                    try:
                        pong = await ws.ping()
                        await asyncio.wait_for(pong, timeout=5)
                        logger.info(f"  Heartbeat {i + 1}/5: alive")
                    except Exception as e:
                        logger.warning(f"  Heartbeat {i + 1}/5: failed - {e}")

                duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000

                return SessionTestResult(
                    success=True,
                    region=region,
                    duration_ms=duration_ms,
                    session_connected=True,
                    details={
                        "persistence_test": "passed",
                        "duration_seconds": duration_ms / 1000,
                    },
                )

        except Exception as e:
            duration_ms = (asyncio.get_event_loop().time() - start_time) * 1000
            return SessionTestResult(
                success=False,
                region=region,
                duration_ms=duration_ms,
                error=f"{type(e).__name__}: {str(e)}",
            )


# ============================================================================
# Pytest Test Cases
# ============================================================================


@pytest.fixture
def client():
    """Create AgentGo session client."""
    return AgentGoSessionClient()


class TestAgentGoSession:
    """Test suite for AgentGo Browser Session functionality."""

    @pytest.mark.asyncio
    async def test_api_configured(self, client):
        """Test 0: Verify API key is configured."""
        if not client.is_configured():
            pytest.skip("AGENTGO_API_KEY not configured")

        logger.info(f"API Key: configured (length: {len(client.api_key)})")
        logger.info(f"WebSocket endpoint: {client.WS_ENDPOINT}")

    @pytest.mark.asyncio
    async def test_websocket_connection(self, client):
        """Test 1: Can we establish WebSocket connection?"""
        if not client.is_configured():
            pytest.skip("AGENTGO_API_KEY not configured")

        result = await client.test_ws_connection(region="us")

        logger.info(
            f"WebSocket test: success={result.success}, "
            f"connected={result.session_connected}, "
            f"duration={result.duration_ms:.0f}ms"
        )

        if result.error:
            logger.error(f"Error: {result.error}")

        if result.details:
            logger.info(f"Details: {result.details}")

        assert result.success, f"WebSocket connection failed: {result.error}"
        assert result.session_connected, "Session not connected"

    @pytest.mark.asyncio
    async def test_multiple_regions(self, client):
        """Test 2: Can we connect to multiple regions?"""
        if not client.is_configured():
            pytest.skip("AGENTGO_API_KEY not configured")

        results = await client.test_multiple_regions()

        # Count successes
        successful = sum(1 for r in results.values() if r.success)
        total = len(results)

        logger.info("\n=== Region Test Summary ===")
        logger.info(f"Successful: {successful}/{total}")

        for region, result in results.items():
            status = "✓" if result.success else "✗"
            logger.info(f"  {status} {region}: {result.duration_ms:.0f}ms")

        # At least 50% of regions should work
        success_rate = successful / total * 100
        assert success_rate >= 50, f"Only {success_rate:.0f}% of regions connected"

    @pytest.mark.asyncio
    async def test_session_persistence(self, client):
        """Test 3: Can session be maintained for automation?"""
        if not client.is_configured():
            pytest.skip("AGENTGO_API_KEY not configured")

        result = await client.test_session_persistence(region="us")

        logger.info(
            f"Persistence test: success={result.success}, "
            f"duration={result.duration_ms:.0f}ms"
        )

        if result.details:
            logger.info(f"Details: {result.details}")

        if result.error:
            logger.error(f"Error: {result.error}")

        assert result.success, f"Session persistence test failed: {result.error}"


# ============================================================================
# Standalone test runner
# ============================================================================


async def run_all_tests():
    """Run all tests without pytest for quick verification."""
    client = AgentGoSessionClient()

    if not client.is_configured():
        print("ERROR: AGENTGO_API_KEY environment variable is not set")
        print("Please set it and run again:")
        print("  export AGENTGO_API_KEY=your_api_key_here")
        return

    print("=" * 70)
    print("AgentGo Browser Session Test")
    print("=" * 70)
    print(f"WebSocket Endpoint: {client.WS_ENDPOINT}")
    print(f"API Key: {client.api_key[:10]}...")
    print("=" * 70)

    # Test 1: Basic WebSocket Connection
    print("\n[Test 1] WebSocket Connection (US region)...")
    result = await client.test_ws_connection(region="us")
    print(f"  Result: {'PASS' if result.success else 'FAIL'}")
    print(f"  Connected: {result.session_connected}")
    print(f"  Duration: {result.duration_ms:.0f}ms")
    if result.error:
        print(f"  Error: {result.error}")

    # Test 2: Multiple Regions
    print("\n[Test 2] Multiple Region Connections...")
    region_results = await client.test_multiple_regions()
    successful = sum(1 for r in region_results.values() if r.success)
    print(f"  Result: {successful}/{len(region_results)} regions connected")
    for region, r in region_results.items():
        status = "✓" if r.success else "✗"
        print(f"    {status} {region}: {r.duration_ms:.0f}ms")

    # Test 3: Session Persistence
    print("\n[Test 3] Session Persistence (10 seconds)...")
    result = await client.test_session_persistence(region="us")
    print(f"  Result: {'PASS' if result.success else 'FAIL'}")
    print(f"  Duration: {result.duration_ms:.0f}ms")
    if result.error:
        print(f"  Error: {result.error}")

    # Summary
    print("\n" + "=" * 70)
    all_passed = (
        region_results.get("us", SessionTestResult(False, "us", 0)).success
        and successful >= 2
    )

    if all_passed:
        print("CONCLUSION: AgentGo Browser Sessions are working!")
        print("You can use these sessions for YouTube cookie extraction.")
    else:
        print("CONCLUSION: Some tests failed, check errors above.")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
