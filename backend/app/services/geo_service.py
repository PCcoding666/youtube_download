"""
GeoIP service for intelligent region routing.
Identifies user's geographic location from IP address and maps to AgentGo regions.
"""

import logging
import aiohttp
from typing import Optional, Dict, Tuple
from pathlib import Path

logger = logging.getLogger(__name__)


# AgentGo supported regions
AGENTGO_REGIONS = ["us", "uk", "de", "fr", "jp", "sg", "in", "au", "ca"]

# Country code to AgentGo region mapping
# ISO 3166-1 alpha-2 country codes -> AgentGo region
COUNTRY_TO_REGION: Dict[str, str] = {
    # North America
    "US": "us",
    "CA": "ca",
    "MX": "us",
    # United Kingdom and Ireland
    "GB": "uk",
    "IE": "uk",
    # Germany and Central Europe
    "DE": "de",
    "AT": "de",
    "CH": "de",
    "PL": "de",
    "CZ": "de",
    "HU": "de",
    # France and surrounding countries
    "FR": "fr",
    "BE": "fr",
    "LU": "fr",
    "MC": "fr",
    # Japan and Korea
    "JP": "jp",
    "KR": "jp",
    # Southeast Asia
    "SG": "sg",
    "MY": "sg",
    "TH": "sg",
    "VN": "sg",
    "PH": "sg",
    "ID": "sg",
    # India and South Asia
    "IN": "in",
    "BD": "in",
    "PK": "in",
    "LK": "in",
    "NP": "in",
    # Australia and Oceania
    "AU": "au",
    "NZ": "au",
    "FJ": "au",
    # China and Hong Kong/Taiwan - route to Singapore or Japan
    "CN": "sg",
    "HK": "sg",
    "TW": "jp",
    "MO": "sg",
    # Russia and Eastern Europe - route to Germany
    "RU": "de",
    "UA": "de",
    "BY": "de",
    # Nordic countries
    "SE": "uk",
    "NO": "uk",
    "DK": "uk",
    "FI": "uk",
    # Southern Europe
    "IT": "fr",
    "ES": "fr",
    "PT": "fr",
    "GR": "de",
    # Middle East - route to Singapore or UK
    "AE": "sg",
    "SA": "sg",
    "IL": "uk",
    "TR": "de",
    # Africa - route to UK or France
    "ZA": "uk",
    "EG": "uk",
    "NG": "uk",
    "KE": "uk",
    "MA": "fr",
    "DZ": "fr",
    "TN": "fr",
    # South America - route to US
    "BR": "us",
    "AR": "us",
    "CL": "us",
    "CO": "us",
    "PE": "us",
    "VE": "us",
}

# Default region when country is unknown or not mapped
DEFAULT_REGION = "us"


class GeoIPService:
    """
    GeoIP service for identifying user location and mapping to AgentGo regions.

    Supports two modes:
    1. Local GeoIP2 database (MaxMind GeoLite2) - faster, requires database file
    2. Free online API fallback (ip-api.com) - no setup required
    """

    def __init__(self, geoip_db_path: Optional[str] = None):
        """
        Initialize GeoIP service.

        Args:
            geoip_db_path: Path to MaxMind GeoLite2-Country.mmdb database file.
                          If not provided or file doesn't exist, uses online API.
        """
        self.geoip_db_path = geoip_db_path
        self._geoip_reader = None
        self._init_geoip_database()

    def _init_geoip_database(self):
        """Initialize GeoIP2 database reader if available."""
        if not self.geoip_db_path:
            logger.info("GeoIP database path not configured, using online API fallback")
            return

        db_path = Path(self.geoip_db_path)
        if not db_path.exists():
            logger.warning(
                f"GeoIP database not found at {self.geoip_db_path}, using online API"
            )
            return

        try:
            import geoip2.database

            self._geoip_reader = geoip2.database.Reader(str(db_path))
            logger.info(f"GeoIP database initialized: {self.geoip_db_path}")
        except ImportError:
            logger.warning("geoip2 package not installed, using online API fallback")
        except Exception as e:
            logger.error(f"Failed to initialize GeoIP database: {e}")

    def _lookup_local(self, ip: str) -> Optional[str]:
        """
        Look up country code using local GeoIP2 database.

        Args:
            ip: IP address to look up

        Returns:
            ISO 3166-1 alpha-2 country code or None
        """
        if not self._geoip_reader:
            return None

        try:
            response = self._geoip_reader.country(ip)
            country_code = response.country.iso_code
            logger.debug(f"GeoIP local lookup: {ip} -> {country_code}")
            return country_code
        except Exception as e:
            logger.debug(f"GeoIP local lookup failed for {ip}: {e}")
            return None

    async def _lookup_online(self, ip: str) -> Optional[str]:
        """
        Look up country code using free online API (ip-api.com).

        Args:
            ip: IP address to look up

        Returns:
            ISO 3166-1 alpha-2 country code or None
        """
        try:
            async with aiohttp.ClientSession() as session:
                # ip-api.com free tier - 45 requests per minute
                url = f"http://ip-api.com/json/{ip}?fields=status,countryCode"
                async with session.get(
                    url, timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        if data.get("status") == "success":
                            country_code = data.get("countryCode")
                            logger.debug(f"GeoIP online lookup: {ip} -> {country_code}")
                            return country_code
        except Exception as e:
            logger.warning(f"GeoIP online lookup failed for {ip}: {e}")

        return None

    async def get_country_code(self, ip: str) -> Optional[str]:
        """
        Get country code for an IP address.
        Uses local database if available, falls back to online API.

        Args:
            ip: IP address to look up

        Returns:
            ISO 3166-1 alpha-2 country code or None
        """
        # Skip private/local IPs
        if self._is_private_ip(ip):
            logger.debug(f"Skipping private IP: {ip}")
            return None

        # Try local database first
        country_code = self._lookup_local(ip)
        if country_code:
            return country_code

        # Fallback to online API
        return await self._lookup_online(ip)

    def _is_private_ip(self, ip: str) -> bool:
        """Check if IP is a private/local address."""
        import ipaddress

        try:
            addr = ipaddress.ip_address(ip)
            return addr.is_private or addr.is_loopback or addr.is_reserved
        except ValueError:
            return False

    def map_to_agentgo_region(self, country_code: Optional[str]) -> str:
        """
        Map country code to AgentGo region.

        Args:
            country_code: ISO 3166-1 alpha-2 country code

        Returns:
            AgentGo region code (us, uk, de, fr, jp, sg, in, au, ca)
        """
        if not country_code:
            return DEFAULT_REGION

        region = COUNTRY_TO_REGION.get(country_code.upper(), DEFAULT_REGION)
        logger.debug(f"Country {country_code} mapped to region: {region}")
        return region

    async def get_region_for_ip(self, ip: str) -> Tuple[str, Optional[str]]:
        """
        Get AgentGo region for an IP address.

        Args:
            ip: User's IP address

        Returns:
            Tuple of (agentgo_region, country_code)
        """
        country_code = await self.get_country_code(ip)
        region = self.map_to_agentgo_region(country_code)

        logger.info(f"IP {ip} -> Country: {country_code} -> Region: {region}")
        return region, country_code

    def get_supported_regions(self) -> list:
        """Get list of AgentGo supported regions."""
        return AGENTGO_REGIONS.copy()

    def close(self):
        """Close GeoIP database reader."""
        if self._geoip_reader:
            try:
                self._geoip_reader.close()
            except Exception:
                pass


# Global service instance
_geo_service: Optional[GeoIPService] = None


def get_geo_service() -> GeoIPService:
    """Get or create global GeoIP service instance."""
    global _geo_service
    if _geo_service is None:
        from app.config import settings

        _geo_service = GeoIPService(
            geoip_db_path=getattr(settings, "geoip_db_path", None)
        )
    return _geo_service


async def get_region_for_ip(ip: str) -> Tuple[str, Optional[str]]:
    """
    Convenience function to get AgentGo region for an IP address.

    Args:
        ip: User's IP address

    Returns:
        Tuple of (agentgo_region, country_code)
    """
    service = get_geo_service()
    return await service.get_region_for_ip(ip)


def get_region_from_country(country_code: str) -> str:
    """
    Get AgentGo region from country code.

    Args:
        country_code: ISO 3166-1 alpha-2 country code

    Returns:
        AgentGo region code
    """
    return COUNTRY_TO_REGION.get(country_code.upper(), DEFAULT_REGION)
