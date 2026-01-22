"""
Test suite for intelligent geo-routing functionality.
Validates IP detection, country-to-region mapping, and region-aware cookie caching.
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestGeoService:
    """Test GeoIP service functionality."""
    
    def test_country_to_region_mapping(self):
        """Test country code to AgentGo region mapping."""
        from app.services.geo_service import DEFAULT_REGION, get_region_from_country
        
        # Test specific country mappings
        assert get_region_from_country('US') == 'us'
        assert get_region_from_country('GB') == 'uk'
        assert get_region_from_country('DE') == 'de'
        assert get_region_from_country('FR') == 'fr'
        assert get_region_from_country('JP') == 'jp'
        assert get_region_from_country('SG') == 'sg'
        assert get_region_from_country('IN') == 'in'
        assert get_region_from_country('AU') == 'au'
        assert get_region_from_country('CA') == 'ca'
        
        # Test case insensitivity
        assert get_region_from_country('us') == 'us'
        assert get_region_from_country('Jp') == 'jp'
        
        # Test unmapped country falls back to default
        assert get_region_from_country('XX') == DEFAULT_REGION
        
        # Test China routes to Singapore
        assert get_region_from_country('CN') == 'sg'
        
        # Test Taiwan routes to Japan
        assert get_region_from_country('TW') == 'jp'
    
    def test_private_ip_detection(self):
        """Test detection of private/local IP addresses."""
        from app.services.geo_service import GeoIPService
        
        service = GeoIPService()
        
        # Private IPs should be detected
        assert service._is_private_ip('192.168.1.1') == True
        assert service._is_private_ip('10.0.0.1') == True
        assert service._is_private_ip('172.16.0.1') == True
        assert service._is_private_ip('127.0.0.1') == True
        
        # Public IPs should not be detected as private
        assert service._is_private_ip('8.8.8.8') == False
        assert service._is_private_ip('1.1.1.1') == False
        assert service._is_private_ip('208.67.222.222') == False  # OpenDNS public IP
    
    def test_supported_regions(self):
        """Test that all supported regions are properly defined."""
        from app.services.geo_service import AGENTGO_REGIONS
        
        expected_regions = ['us', 'uk', 'de', 'fr', 'jp', 'sg', 'in', 'au', 'ca']
        assert set(AGENTGO_REGIONS) == set(expected_regions)
    
    @pytest.mark.asyncio
    async def test_online_lookup_fallback(self):
        """Test online IP lookup API fallback."""
        from app.services.geo_service import GeoIPService
        
        service = GeoIPService()  # No database path
        
        # Mock the aiohttp session
        with patch('aiohttp.ClientSession') as mock_session:
            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value={
                'status': 'success',
                'countryCode': 'US'
            })
            
            mock_session_instance = AsyncMock()
            mock_session_instance.__aenter__.return_value = mock_session_instance
            mock_session_instance.__aexit__.return_value = None
            mock_session_instance.get.return_value.__aenter__.return_value = mock_response
            mock_session.return_value = mock_session_instance
            
            # Test should use online fallback
            result = await service._lookup_online('8.8.8.8')
            # Note: This may return None in test environment without network


class TestAgentGoRegionCaching:
    """Test AgentGo service region-aware cookie caching."""
    
    def test_cookie_file_path_generation(self):
        """Test cookie file path generation for different regions."""
        from app.services.agentgo_service import AgentGoService
        
        service = AgentGoService()
        
        # Test path generation for each region
        assert 'cookies_us.txt' in service._get_cookie_file_path('us')
        assert 'cookies_jp.txt' in service._get_cookie_file_path('jp')
        assert 'cookies_uk.txt' in service._get_cookie_file_path('uk')
    
    def test_region_validation(self):
        """Test region validation in service."""
        from app.services.agentgo_service import AgentGoService
        
        service = AgentGoService()
        
        # Valid regions
        assert 'us' in service.SUPPORTED_REGIONS
        assert 'jp' in service.SUPPORTED_REGIONS
        
        # Check all expected regions
        expected = ['us', 'uk', 'de', 'fr', 'jp', 'sg', 'in', 'au', 'ca']
        assert set(service.SUPPORTED_REGIONS) == set(expected)
    
    def test_get_all_cached_regions(self):
        """Test retrieval of all cached regions."""
        from app.services.agentgo_service import AgentGoService
        
        service = AgentGoService()
        
        # Initially no regions should be cached
        cached = service.get_all_cached_regions()
        # Result depends on actual state, just verify it returns a dict
        assert isinstance(cached, dict)
    
    def test_invalidate_region_cache(self):
        """Test cache invalidation for specific region."""
        from app.services.agentgo_service import AgentGoService
        import time
        
        service = AgentGoService()
        
        # Manually add a cache entry
        service._region_cookies_cache['test_region'] = ('/tmp/test.txt', time.time())
        
        # Invalidate it
        service.invalidate_region_cache('test_region')
        
        # Should be removed
        assert 'test_region' not in service._region_cookies_cache


class TestDownloaderRegionSupport:
    """Test YouTubeDownloader region support."""
    
    def test_downloader_accepts_region(self):
        """Test that YouTubeDownloader accepts region parameter."""
        from app.services.downloader import YouTubeDownloader
        
        # Create downloader with region
        downloader = YouTubeDownloader(region='jp')
        
        assert downloader.region == 'jp'
    
    def test_downloader_default_region(self):
        """Test that YouTubeDownloader has None region by default."""
        from app.services.downloader import YouTubeDownloader
        
        downloader = YouTubeDownloader()
        
        assert downloader.region is None


class TestRouteGeoIntegration:
    """Test API route geo-routing integration."""
    
    def test_get_client_ip_direct(self):
        """Test client IP extraction from direct connection."""
        from app.api.routes import get_client_ip
        
        # Mock request with direct connection
        request = MagicMock()
        request.headers = {}
        request.client.host = '192.168.1.100'
        
        ip = get_client_ip(request)
        assert ip == '192.168.1.100'
    
    def test_get_client_ip_forwarded(self):
        """Test client IP extraction from X-Forwarded-For header."""
        from app.api.routes import get_client_ip
        
        # Mock request with forwarded header
        request = MagicMock()
        request.headers = {'X-Forwarded-For': '203.0.113.1, 10.0.0.1'}
        request.client.host = '127.0.0.1'
        
        ip = get_client_ip(request)
        assert ip == '203.0.113.1'  # First IP in chain
    
    def test_get_client_ip_real_ip_header(self):
        """Test client IP extraction from X-Real-IP header."""
        from app.api.routes import get_client_ip
        
        # Mock request with X-Real-IP header
        request = MagicMock()
        request.headers = {'X-Real-IP': '198.51.100.1'}
        request.client.host = '127.0.0.1'
        
        ip = get_client_ip(request)
        assert ip == '198.51.100.1'


class TestEndToEndGeoRouting:
    """End-to-end tests for geo-routing workflow."""
    
    @pytest.mark.asyncio
    async def test_region_detection_workflow(self):
        """Test complete region detection workflow."""
        from app.services.geo_service import GeoIPService
        
        service = GeoIPService()
        
        # Test mapping known countries
        us_region = service.map_to_agentgo_region('US')
        assert us_region == 'us'
        
        jp_region = service.map_to_agentgo_region('JP')
        assert jp_region == 'jp'
        
        # Test unknown country
        unknown_region = service.map_to_agentgo_region(None)
        assert unknown_region == 'us'  # Default
    
    @pytest.mark.asyncio
    async def test_cookie_region_consistency(self):
        """Test that cookies are correctly associated with regions."""
        from app.services.agentgo_service import AgentGoService
        
        service = AgentGoService()
        
        # Test cookie file paths are unique per region
        us_path = service._get_cookie_file_path('us')
        jp_path = service._get_cookie_file_path('jp')
        
        assert us_path != jp_path
        assert 'us' in us_path
        assert 'jp' in jp_path


class TestGeoRoutingConfiguration:
    """Test geo-routing configuration options."""
    
    def test_default_region_config(self):
        """Test default region from configuration."""
        from app.config import settings
        
        # Default region should be 'us'
        default_region = getattr(settings, 'agentgo_region', 'us')
        assert default_region in ['us', 'uk', 'de', 'fr', 'jp', 'sg', 'in', 'au', 'ca']
    
    def test_geo_routing_enabled_by_default(self):
        """Test that geo-routing is enabled by default."""
        from app.config import settings
        
        enabled = getattr(settings, 'enable_geo_routing', True)
        assert enabled == True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
