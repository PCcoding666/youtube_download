"""
Tests for authentication data models.
"""
import pytest
from datetime import datetime, timedelta
from pydantic import ValidationError

from app.models import AuthenticationBundle, TokenExtractionResult


class TestAuthenticationBundle:
    """Test cases for AuthenticationBundle model."""
    
    def test_valid_authentication_bundle_creation(self):
        """Test creating a valid authentication bundle."""
        bundle = AuthenticationBundle(
            cookies=[{"name": "test", "value": "value"}],
            po_token="test_token_123",
            visitor_data="visitor_123",
            region="us-east",
            extraction_timestamp=datetime.now()
        )
        
        assert bundle.cookies == [{"name": "test", "value": "value"}]
        assert bundle.po_token == "test_token_123"
        assert bundle.visitor_data == "visitor_123"
        assert bundle.region == "us-east"
        assert isinstance(bundle.extraction_timestamp, datetime)
    
    def test_authentication_bundle_without_tokens(self):
        """Test creating bundle without tokens (cookies only)."""
        bundle = AuthenticationBundle(
            cookies=[{"name": "session", "value": "abc123"}],
            region="eu-west",
            extraction_timestamp=datetime.now()
        )
        
        assert bundle.po_token is None
        assert bundle.visitor_data is None
        assert not bundle.has_tokens()
    
    def test_authentication_bundle_with_po_token_only(self):
        """Test bundle with only PO token."""
        bundle = AuthenticationBundle(
            cookies=[],
            po_token="web+token123",
            region="us-west",
            extraction_timestamp=datetime.now()
        )
        
        assert bundle.has_tokens()
        assert bundle.po_token == "web+token123"
        assert bundle.visitor_data is None
    
    def test_authentication_bundle_with_visitor_data_only(self):
        """Test bundle with only visitor data."""
        bundle = AuthenticationBundle(
            cookies=[],
            visitor_data="visitor_abc123",
            region="asia-east",
            extraction_timestamp=datetime.now()
        )
        
        assert bundle.has_tokens()
        assert bundle.po_token is None
        assert bundle.visitor_data == "visitor_abc123"
    
    def test_po_token_validation_empty_string(self):
        """Test PO token validation rejects empty strings."""
        with pytest.raises(ValidationError) as exc_info:
            AuthenticationBundle(
                cookies=[],
                po_token="",
                region="us-east",
                extraction_timestamp=datetime.now()
            )
        
        assert "PO token must be a non-empty string" in str(exc_info.value)
    
    def test_po_token_validation_whitespace_only(self):
        """Test PO token validation rejects whitespace-only strings."""
        with pytest.raises(ValidationError) as exc_info:
            AuthenticationBundle(
                cookies=[],
                po_token="   ",
                region="us-east",
                extraction_timestamp=datetime.now()
            )
        
        assert "PO token must be a non-empty string" in str(exc_info.value)
    
    def test_po_token_validation_invalid_characters(self):
        """Test PO token validation rejects invalid characters."""
        with pytest.raises(ValidationError) as exc_info:
            AuthenticationBundle(
                cookies=[],
                po_token="token@#$%",
                region="us-east",
                extraction_timestamp=datetime.now()
            )
        
        assert "PO token contains invalid characters" in str(exc_info.value)
    
    def test_visitor_data_validation_empty_string(self):
        """Test visitor data validation rejects empty strings."""
        with pytest.raises(ValidationError) as exc_info:
            AuthenticationBundle(
                cookies=[],
                visitor_data="",
                region="us-east",
                extraction_timestamp=datetime.now()
            )
        
        assert "Visitor data must be a non-empty string" in str(exc_info.value)
    
    def test_visitor_data_validation_invalid_characters(self):
        """Test visitor data validation rejects invalid characters."""
        with pytest.raises(ValidationError) as exc_info:
            AuthenticationBundle(
                cookies=[],
                visitor_data="visitor@#$",
                region="us-east",
                extraction_timestamp=datetime.now()
            )
        
        assert "Visitor data contains invalid characters" in str(exc_info.value)
    
    def test_region_validation_empty_string(self):
        """Test region validation rejects empty strings."""
        with pytest.raises(ValidationError) as exc_info:
            AuthenticationBundle(
                cookies=[],
                region="",
                extraction_timestamp=datetime.now()
            )
        
        assert "Region must be a non-empty string" in str(exc_info.value)
    
    def test_region_validation_whitespace_trimmed(self):
        """Test region validation trims whitespace."""
        bundle = AuthenticationBundle(
            cookies=[],
            region="  us-east  ",
            extraction_timestamp=datetime.now()
        )
        
        assert bundle.region == "us-east"
    
    def test_is_expired_not_expired(self):
        """Test is_expired returns False for recent timestamps."""
        recent_time = datetime.now() - timedelta(minutes=30)
        bundle = AuthenticationBundle(
            cookies=[],
            region="us-east",
            extraction_timestamp=recent_time
        )
        
        assert not bundle.is_expired(max_age_seconds=3600)  # 1 hour
    
    def test_is_expired_expired(self):
        """Test is_expired returns True for old timestamps."""
        old_time = datetime.now() - timedelta(hours=2)
        bundle = AuthenticationBundle(
            cookies=[],
            region="us-east",
            extraction_timestamp=old_time
        )
        
        assert bundle.is_expired(max_age_seconds=3600)  # 1 hour
    
    def test_is_expired_invalid_max_age(self):
        """Test is_expired raises error for invalid max_age_seconds."""
        bundle = AuthenticationBundle(
            cookies=[],
            region="us-east",
            extraction_timestamp=datetime.now()
        )
        
        with pytest.raises(ValueError) as exc_info:
            bundle.is_expired(max_age_seconds=0)
        
        assert "max_age_seconds must be a positive integer" in str(exc_info.value)
        
        with pytest.raises(ValueError) as exc_info:
            bundle.is_expired(max_age_seconds=-100)
        
        assert "max_age_seconds must be a positive integer" in str(exc_info.value)
    
    def test_get_formatted_po_token_none(self):
        """Test get_formatted_po_token returns None when no token."""
        bundle = AuthenticationBundle(
            cookies=[],
            region="us-east",
            extraction_timestamp=datetime.now()
        )
        
        assert bundle.get_formatted_po_token() is None
    
    def test_get_formatted_po_token_adds_prefix(self):
        """Test get_formatted_po_token adds web+ prefix."""
        bundle = AuthenticationBundle(
            cookies=[],
            po_token="token123",
            region="us-east",
            extraction_timestamp=datetime.now()
        )
        
        assert bundle.get_formatted_po_token() == "web+token123"
    
    def test_get_formatted_po_token_preserves_existing_prefix(self):
        """Test get_formatted_po_token preserves existing web+ prefix."""
        bundle = AuthenticationBundle(
            cookies=[],
            po_token="web+token123",
            region="us-east",
            extraction_timestamp=datetime.now()
        )
        
        assert bundle.get_formatted_po_token() == "web+token123"


class TestTokenExtractionResult:
    """Test cases for TokenExtractionResult model."""
    
    def test_valid_token_extraction_result_success(self):
        """Test creating a successful token extraction result."""
        result = TokenExtractionResult(
            success=True,
            po_token="token123",
            visitor_data="visitor123",
            extraction_method="network_intercept",
            extraction_duration=1.5
        )
        
        assert result.success is True
        assert result.po_token == "token123"
        assert result.visitor_data == "visitor123"
        assert result.extraction_method == "network_intercept"
        assert result.extraction_duration == 1.5
        assert result.error_message is None
    
    def test_valid_token_extraction_result_failure(self):
        """Test creating a failed token extraction result."""
        result = TokenExtractionResult(
            success=False,
            error_message="Network timeout",
            extraction_method="javascript",
            extraction_duration=5.0
        )
        
        assert result.success is False
        assert result.po_token is None
        assert result.visitor_data is None
        assert result.error_message == "Network timeout"
        assert result.extraction_method == "javascript"
        assert result.extraction_duration == 5.0
    
    def test_extraction_method_validation_valid_methods(self):
        """Test extraction method validation accepts valid methods."""
        valid_methods = ["network_intercept", "javascript", "combined", "fallback"]
        
        for method in valid_methods:
            result = TokenExtractionResult(
                success=True,
                extraction_method=method,
                extraction_duration=1.0
            )
            assert result.extraction_method == method
    
    def test_extraction_method_validation_invalid_method(self):
        """Test extraction method validation rejects invalid methods."""
        with pytest.raises(ValidationError) as exc_info:
            TokenExtractionResult(
                success=True,
                extraction_method="invalid_method",
                extraction_duration=1.0
            )
        
        assert "extraction_method must be one of" in str(exc_info.value)
    
    def test_extraction_duration_validation_negative(self):
        """Test extraction duration validation rejects negative values."""
        with pytest.raises(ValidationError) as exc_info:
            TokenExtractionResult(
                success=True,
                extraction_method="javascript",
                extraction_duration=-1.0
            )
        
        assert "extraction_duration must be a non-negative number" in str(exc_info.value)
    
    def test_extraction_duration_validation_zero(self):
        """Test extraction duration validation accepts zero."""
        result = TokenExtractionResult(
            success=True,
            extraction_method="javascript",
            extraction_duration=0.0
        )
        
        assert result.extraction_duration == 0.0
    
    def test_extraction_duration_validation_converts_int(self):
        """Test extraction duration validation converts int to float."""
        result = TokenExtractionResult(
            success=True,
            extraction_method="javascript",
            extraction_duration=5
        )
        
        assert result.extraction_duration == 5.0
        assert isinstance(result.extraction_duration, float)
    
    def test_po_token_validation_in_result(self):
        """Test PO token validation in extraction result."""
        with pytest.raises(ValidationError) as exc_info:
            TokenExtractionResult(
                success=True,
                po_token="invalid@token",
                extraction_method="javascript",
                extraction_duration=1.0
            )
        
        assert "PO token contains invalid characters" in str(exc_info.value)
    
    def test_visitor_data_validation_in_result(self):
        """Test visitor data validation in extraction result."""
        with pytest.raises(ValidationError) as exc_info:
            TokenExtractionResult(
                success=True,
                visitor_data="invalid@visitor",
                extraction_method="javascript",
                extraction_duration=1.0
            )
        
        assert "Visitor data contains invalid characters" in str(exc_info.value)