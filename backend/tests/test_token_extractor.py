"""
Tests for TokenExtractor class.
"""
import pytest
from unittest.mock import Mock, AsyncMock, patch
from hypothesis import given, strategies as st, settings
from app.services.agentgo_service import TokenExtractor
from app.models import TokenExtractionResult


class TestTokenExtractor:
    """Test cases for TokenExtractor class."""
    
    def test_token_extractor_initialization(self):
        """Test TokenExtractor initializes correctly."""
        extractor = TokenExtractor()
        
        assert extractor is not None
        assert hasattr(extractor, 'logger')
        assert extractor._extraction_timeout == 30
        assert extractor._extracted_po_tokens == []
    
    def test_validate_po_token_valid(self):
        """Test PO token validation with valid tokens."""
        extractor = TokenExtractor()
        
        valid_tokens = [
            "abc123def456",
            "web+abc123def456",
            "ABC123DEF456GHI789",
            "token_with_underscores_123",
            "token-with-dashes-456",
            "base64+token/with=padding"
        ]
        
        for token in valid_tokens:
            assert extractor.validate_po_token(token), f"Token should be valid: {token}"
    
    def test_validate_po_token_invalid(self):
        """Test PO token validation with invalid tokens."""
        extractor = TokenExtractor()
        
        invalid_tokens = [
            "",
            "   ",
            None,
            123,
            "short",  # too short
            "token@with#invalid$chars",
            "token with spaces"
        ]
        
        for token in invalid_tokens:
            assert not extractor.validate_po_token(token), f"Token should be invalid: {token}"
    
    def test_validate_visitor_data_valid(self):
        """Test visitor data validation with valid data."""
        extractor = TokenExtractor()
        
        valid_data = [
            "visitor123",
            "VISITOR_DATA_123",
            "visitor-data-456",
            "visitor_data_789"
        ]
        
        for data in valid_data:
            assert extractor.validate_visitor_data(data), f"Visitor data should be valid: {data}"
    
    def test_validate_visitor_data_invalid(self):
        """Test visitor data validation with invalid data."""
        extractor = TokenExtractor()
        
        invalid_data = [
            "",
            "   ",
            None,
            123,
            "abc",  # too short
            "visitor@data#invalid",
            "visitor data with spaces"
        ]
        
        for data in invalid_data:
            assert not extractor.validate_visitor_data(data), f"Visitor data should be invalid: {data}"
    
    def test_format_po_token_for_ytdlp(self):
        """Test PO token formatting for yt-dlp."""
        extractor = TokenExtractor()
        
        # Test adding prefix
        assert extractor.format_po_token_for_ytdlp("token123") == "web+token123"
        
        # Test preserving existing prefix
        assert extractor.format_po_token_for_ytdlp("web+token123") == "web+token123"
        
        # Test empty token
        assert extractor.format_po_token_for_ytdlp("") == ""
        assert extractor.format_po_token_for_ytdlp(None) == ""
    
    @pytest.mark.asyncio
    async def test_extract_tokens_with_timeout_success(self):
        """Test successful token extraction with timeout."""
        extractor = TokenExtractor()
        
        # Mock page object
        mock_page = Mock()
        
        # Mock the extraction methods
        with patch.object(extractor, 'extract_po_token', new_callable=AsyncMock) as mock_po, \
             patch.object(extractor, 'extract_visitor_data', new_callable=AsyncMock) as mock_visitor:
            
            mock_po.return_value = "test_po_token"
            mock_visitor.return_value = "test_visitor_data"
            
            result = await extractor.extract_tokens_with_timeout(mock_page, timeout=10)
            
            assert isinstance(result, TokenExtractionResult)
            assert result.success is True
            assert result.po_token == "test_po_token"
            assert result.visitor_data == "test_visitor_data"
            assert result.extraction_method == "combined"
            assert result.error_message is None
            assert result.extraction_duration >= 0
    
    @pytest.mark.asyncio
    async def test_extract_tokens_with_timeout_partial_success(self):
        """Test partial token extraction (only one token found)."""
        extractor = TokenExtractor()
        
        # Mock page object
        mock_page = Mock()
        
        # Mock the extraction methods - only PO token succeeds
        with patch.object(extractor, 'extract_po_token', new_callable=AsyncMock) as mock_po, \
             patch.object(extractor, 'extract_visitor_data', new_callable=AsyncMock) as mock_visitor:
            
            mock_po.return_value = "test_po_token"
            mock_visitor.return_value = None
            
            result = await extractor.extract_tokens_with_timeout(mock_page, timeout=10)
            
            assert isinstance(result, TokenExtractionResult)
            assert result.success is True  # Success if at least one token found
            assert result.po_token == "test_po_token"
            assert result.visitor_data is None
            assert result.extraction_method == "combined"
            assert result.error_message is None
    
    @pytest.mark.asyncio
    async def test_extract_tokens_with_timeout_failure(self):
        """Test failed token extraction."""
        extractor = TokenExtractor()
        
        # Mock page object
        mock_page = Mock()
        
        # Mock the extraction methods to return None
        with patch.object(extractor, 'extract_po_token', new_callable=AsyncMock) as mock_po, \
             patch.object(extractor, 'extract_visitor_data', new_callable=AsyncMock) as mock_visitor:
            
            mock_po.return_value = None
            mock_visitor.return_value = None
            
            result = await extractor.extract_tokens_with_timeout(mock_page, timeout=10)
            
            assert isinstance(result, TokenExtractionResult)
            assert result.success is False
            assert result.po_token is None
            assert result.visitor_data is None
            assert result.extraction_method == "combined"
            assert result.error_message == "No tokens extracted"
    
    @pytest.mark.asyncio
    async def test_extract_tokens_with_timeout_exception(self):
        """Test token extraction with exception handling."""
        extractor = TokenExtractor()
        
        # Mock page object
        mock_page = Mock()
        
        # Mock the extraction methods to raise exceptions
        with patch.object(extractor, 'extract_po_token', new_callable=AsyncMock) as mock_po, \
             patch.object(extractor, 'extract_visitor_data', new_callable=AsyncMock) as mock_visitor:
            
            mock_po.side_effect = Exception("PO token extraction failed")
            mock_visitor.side_effect = Exception("Visitor data extraction failed")
            
            result = await extractor.extract_tokens_with_timeout(mock_page, timeout=10)
            
            assert isinstance(result, TokenExtractionResult)
            assert result.success is False
            assert result.po_token is None
            assert result.visitor_data is None
            assert result.extraction_method == "combined"
            assert result.error_message is not None


# Property-Based Tests

class TestTokenExtractionProperties:
    """Property-based tests for token extraction methods."""
    
    @given(
        video_urls=st.one_of(
            st.none(),
            st.just("https://www.youtube.com/watch?v=dQw4w9WgXcQ"),
            st.just("https://youtu.be/dQw4w9WgXcQ"),
            st.just("https://www.youtube.com/watch?v=_MLwQUebJUc"),
            st.text(min_size=1, max_size=100).filter(lambda x: not x.startswith(('https://www.youtube.com/watch', 'https://youtu.be/')))
        ),
        navigation_success=st.booleans(),
        has_network_requests=st.booleans(),
        has_javascript_context=st.booleans()
    )
    @settings(max_examples=100, deadline=None)
    @pytest.mark.asyncio
    async def test_property_network_monitoring_and_javascript_execution_during_navigation(
        self, video_urls, navigation_success, has_network_requests, has_javascript_context
    ):
        """
        **Feature: youtube-token-extraction, Property 1: Network monitoring and JavaScript execution during navigation**
        **Validates: Requirements 1.1, 2.1**
        
        Property: For any YouTube page navigation, the system should monitor network requests 
        for PO tokens and execute JavaScript for visitor data extraction.
        
        This property tests that:
        1. Network request monitoring is set up during navigation (Requirement 1.1)
        2. JavaScript execution for visitor data extraction is attempted (Requirement 2.1)
        3. Both operations are attempted regardless of individual success/failure
        4. The system handles various navigation scenarios gracefully
        """
        extractor = TokenExtractor()
        
        # Create mock page with realistic behavior
        mock_page = Mock()
        mock_page.url = "https://www.youtube.com/watch?v=test123" if navigation_success else "about:blank"
        
        # Track if network monitoring was set up
        network_monitoring_setup = False
        def mock_page_on(event_type, handler):
            nonlocal network_monitoring_setup
            if event_type == "request":
                network_monitoring_setup = True
        mock_page.on = mock_page_on
        
        # Mock navigation behavior based on navigation_success
        if navigation_success:
            mock_page.goto = AsyncMock()
            mock_page.evaluate = AsyncMock()
            mock_page.locator.return_value.first.is_visible = AsyncMock(return_value=has_network_requests)
            mock_page.locator.return_value.first.hover = AsyncMock()
        else:
            mock_page.goto = AsyncMock(side_effect=Exception("Navigation failed"))
            mock_page.evaluate = AsyncMock(side_effect=Exception("JavaScript execution failed"))
        
        # Mock JavaScript execution context
        if has_javascript_context and navigation_success:
            # Simulate successful visitor data extraction
            mock_page.evaluate.return_value = "test_visitor_data_123" if has_javascript_context else None
        
        # Test PO token extraction (network monitoring)
        po_token_result = await extractor.extract_po_token(mock_page, video_urls)
        
        # Test visitor data extraction (JavaScript execution)  
        visitor_data_result = await extractor.extract_visitor_data(mock_page, video_urls)
        
        # Property assertions: The system should always attempt both operations
        
        # 1. Network monitoring should be set up during PO token extraction
        assert network_monitoring_setup, "Network request monitoring should be set up during navigation"
        
        # 2. Navigation should be attempted for both extraction methods
        if navigation_success:
            # If navigation succeeds, both methods should attempt their respective operations
            assert mock_page.goto.call_count >= 1, "Navigation should be attempted during token extraction"
            
            # JavaScript execution should be attempted for visitor data
            if has_javascript_context:
                assert mock_page.evaluate.call_count >= 1, "JavaScript execution should be attempted for visitor data extraction"
        
        # 3. Results should be consistent with the mocked behavior
        if navigation_success and has_javascript_context:
            # If both navigation and JS context are available, visitor data should be extracted
            assert visitor_data_result is not None or not has_javascript_context, \
                "Visitor data should be extracted when navigation and JS context are available"
        
        # 4. The system should handle failures gracefully (no exceptions should propagate)
        # If we reach this point, both extraction methods completed without raising exceptions
        assert True, "Both extraction methods should complete without raising exceptions"
        
        # 5. Results should be of correct types
        assert po_token_result is None or isinstance(po_token_result, str), \
            "PO token result should be None or string"
        assert visitor_data_result is None or isinstance(visitor_data_result, str), \
            "Visitor data result should be None or string"