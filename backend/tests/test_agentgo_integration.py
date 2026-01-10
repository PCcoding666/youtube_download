"""
Integration tests for enhanced AgentGoService with token extraction.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from datetime import datetime

from app.services.agentgo_service import AgentGoService, get_agentgo_service
from app.models import AuthenticationBundle, TokenExtractionResult


class TestAgentGoServiceIntegration:
    """Integration tests for AgentGoService with token extraction."""
    
    @pytest.mark.asyncio
    async def test_get_youtube_cookies_returns_authentication_bundle(self):
        """Test that get_youtube_cookies now returns AuthenticationBundle."""
        service = AgentGoService()
        
        # Mock the get_youtube_authentication_bundle method
        mock_bundle = AuthenticationBundle(
            cookies=[{"name": "test", "value": "value"}],
            po_token="test_token",
            visitor_data="test_visitor",
            region="us",
            extraction_timestamp=datetime.now(),
            cookie_file_path="/tmp/test_cookies.txt"
        )
        
        with patch.object(service, 'get_youtube_authentication_bundle', new_callable=AsyncMock) as mock_method:
            mock_method.return_value = mock_bundle
            
            result = await service.get_youtube_cookies(region="us")
            
            assert isinstance(result, AuthenticationBundle)
            assert result.po_token == "test_token"
            assert result.visitor_data == "test_visitor"
            assert result.region == "us"
            assert result.has_tokens()
            mock_method.assert_called_once_with(region="us", force_refresh=False)
    
    @pytest.mark.asyncio
    async def test_get_youtube_cookies_file_path_backward_compatibility(self):
        """Test backward compatibility method returns cookie file path."""
        service = AgentGoService()
        
        # Mock the get_youtube_cookies method to return AuthenticationBundle
        mock_bundle = AuthenticationBundle(
            cookies=[{"name": "test", "value": "value"}],
            region="us",
            extraction_timestamp=datetime.now(),
            cookie_file_path="/tmp/test_cookies.txt"
        )
        
        with patch.object(service, 'get_youtube_cookies', new_callable=AsyncMock) as mock_method:
            mock_method.return_value = mock_bundle
            
            result = await service.get_youtube_cookies_file_path(region="us")
            
            assert isinstance(result, str)
            assert result == "/tmp/test_cookies.txt"
            mock_method.assert_called_once_with(force_refresh=False, region="us")
    
    @pytest.mark.asyncio
    async def test_get_youtube_cookies_file_path_none_bundle(self):
        """Test backward compatibility method handles None bundle."""
        service = AgentGoService()
        
        with patch.object(service, 'get_youtube_cookies', new_callable=AsyncMock) as mock_method:
            mock_method.return_value = None
            
            result = await service.get_youtube_cookies_file_path(region="us")
            
            assert result is None
    
    @pytest.mark.asyncio
    async def test_get_youtube_cookies_file_path_no_cookie_file(self):
        """Test backward compatibility method handles bundle without cookie file."""
        service = AgentGoService()
        
        # Mock bundle without cookie_file_path
        mock_bundle = AuthenticationBundle(
            cookies=[{"name": "test", "value": "value"}],
            region="us",
            extraction_timestamp=datetime.now()
        )
        
        with patch.object(service, 'get_youtube_cookies', new_callable=AsyncMock) as mock_method:
            mock_method.return_value = mock_bundle
            
            result = await service.get_youtube_cookies_file_path(region="us")
            
            assert result is None
    
    def test_global_service_instance(self):
        """Test global service instance creation."""
        service1 = get_agentgo_service()
        service2 = get_agentgo_service()
        
        assert service1 is service2  # Should be the same instance
        assert isinstance(service1, AgentGoService)
    
    @pytest.mark.asyncio
    async def test_convenience_functions_backward_compatibility(self):
        """Test convenience functions maintain backward compatibility."""
        from app.services.agentgo_service import (
            fetch_youtube_cookies_with_agentgo,
            fetch_youtube_authentication_bundle,
            get_cookies_for_region,
            get_authentication_bundle_for_region
        )
        
        mock_bundle = AuthenticationBundle(
            cookies=[{"name": "test", "value": "value"}],
            region="us",
            extraction_timestamp=datetime.now(),
            cookie_file_path="/tmp/test_cookies.txt"
        )
        
        with patch('app.services.agentgo_service.get_agentgo_service') as mock_get_service:
            mock_service = Mock()
            mock_service.get_youtube_cookies_file_path = AsyncMock(return_value="/tmp/test_cookies.txt")
            mock_service.get_youtube_cookies = AsyncMock(return_value=mock_bundle)
            mock_get_service.return_value = mock_service
            
            # Test backward compatibility functions (return cookie file path)
            cookie_path = await fetch_youtube_cookies_with_agentgo(region="us")
            assert cookie_path == "/tmp/test_cookies.txt"
            
            cookie_path = await get_cookies_for_region("us")
            assert cookie_path == "/tmp/test_cookies.txt"
            
            # Test new functions (return AuthenticationBundle)
            bundle = await fetch_youtube_authentication_bundle(region="us")
            assert isinstance(bundle, AuthenticationBundle)
            assert bundle.region == "us"
            
            bundle = await get_authentication_bundle_for_region("us")
            assert isinstance(bundle, AuthenticationBundle)
            assert bundle.region == "us"
    
    @pytest.mark.asyncio
    async def test_token_extraction_integration(self):
        """Test that token extraction is properly integrated."""
        service = AgentGoService()
        
        # Verify TokenExtractor is initialized
        assert hasattr(service, 'token_extractor')
        assert service.token_extractor is not None
        
        # Test token extractor methods are available
        assert hasattr(service.token_extractor, 'extract_po_token')
        assert hasattr(service.token_extractor, 'extract_visitor_data')
        assert hasattr(service.token_extractor, 'extract_tokens_with_timeout')
        assert hasattr(service.token_extractor, 'validate_po_token')
        assert hasattr(service.token_extractor, 'validate_visitor_data')
    
    @pytest.mark.asyncio
    async def test_error_handling_and_logging(self):
        """Test comprehensive error handling and logging."""
        service = AgentGoService()
        
        # Test with invalid configuration
        service.api_key = None
        
        result = await service.get_youtube_cookies(region="us")
        assert result is None
        
        # Test with unsupported region - the region fallback happens in get_youtube_authentication_bundle
        service.api_key = "test_key"
        with patch.object(service, 'get_youtube_authentication_bundle', new_callable=AsyncMock) as mock_method:
            mock_method.return_value = None
            
            result = await service.get_youtube_cookies(region="invalid_region")
            assert result is None
            
            # Should have been called with the invalid region (fallback happens inside the method)
            mock_method.assert_called_once()
            call_args = mock_method.call_args
            assert call_args[1]['region'] == 'invalid_region'