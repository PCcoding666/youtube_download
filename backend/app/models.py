"""
Pydantic models for request/response validation.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, HttpUrl, field_validator
from enum import Enum
from datetime import datetime
import uuid
import re


class TaskStatus(str, Enum):
    """Task processing status enum."""
    PENDING = "pending"
    DOWNLOADING = "downloading"
    EXTRACTING_AUDIO = "extracting_audio"
    UPLOADING = "uploading"
    TRANSCRIBING = "transcribing"
    COMPLETED = "completed"
    FAILED = "failed"


class VideoResolution(str, Enum):
    """Video resolution options."""
    RES_360P = "360"
    RES_480P = "480"
    RES_720P = "720"
    RES_1080P = "1080"
    RES_1440P = "1440"
    RES_2160P = "2160"  # 4K
    BEST = "best"
    AUDIO_ONLY = "audio"


class ProcessRequest(BaseModel):
    """Request model for video processing."""
    youtube_url: str = Field(..., description="YouTube video URL")
    enable_transcription: bool = Field(default=True, description="Enable audio transcription")
    resolution: VideoResolution = Field(default=VideoResolution.RES_720P, description="Video resolution")
    
    class Config:
        json_schema_extra = {
            "example": {
                "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "enable_transcription": True,
                "resolution": "720"
            }
        }


class ProcessResponse(BaseModel):
    """Response model for video processing submission."""
    task_id: str = Field(..., description="Unique task identifier")
    status: TaskStatus = Field(..., description="Current task status")
    message: str = Field(default="Task submitted successfully")


class TranscriptSegment(BaseModel):
    """Single transcript segment with timestamp."""
    text: str = Field(..., description="Transcribed text")
    start_time: float = Field(..., description="Start time in seconds")
    end_time: float = Field(..., description="End time in seconds")
    speaker_id: Optional[int] = Field(default=None, description="Speaker identifier")


class TaskStatusResponse(BaseModel):
    """Response model for task status query."""
    task_id: str
    status: TaskStatus
    progress: int = Field(default=0, ge=0, le=100, description="Progress percentage")
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class TaskResultResponse(BaseModel):
    """Response model for completed task result."""
    task_id: str
    status: TaskStatus
    video_url: Optional[str] = None
    audio_url: Optional[str] = None
    video_title: Optional[str] = None
    video_duration: Optional[float] = None
    transcript: Optional[List[TranscriptSegment]] = None
    full_text: Optional[str] = None
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class VideoInfo(BaseModel):
    """Video metadata information."""
    title: str
    duration: float
    thumbnail: Optional[str] = None
    description: Optional[str] = None
    uploader: Optional[str] = None


class TaskData(BaseModel):
    """Internal task data storage model."""
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    youtube_url: str
    status: TaskStatus = TaskStatus.PENDING
    progress: int = 0
    enable_transcription: bool = True
    resolution: str = "720"  # Default resolution
    
    # Geo-routing fields
    user_ip: Optional[str] = None  # User's IP address
    country_code: Optional[str] = None  # ISO country code
    region: Optional[str] = None  # AgentGo region for routing
    
    # File paths
    video_path: Optional[str] = None
    audio_path: Optional[str] = None
    
    # URLs after upload
    video_url: Optional[str] = None
    audio_url: Optional[str] = None
    
    # Video info
    video_title: Optional[str] = None
    video_duration: Optional[float] = None
    
    # Transcription result
    transcript: Optional[List[Dict[str, Any]]] = None
    full_text: Optional[str] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    
    # Error handling
    error_message: Optional[str] = None
    retry_count: int = 0


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    version: str = "1.0.0"
    timestamp: datetime = Field(default_factory=datetime.now)


class AuthenticationBundle(BaseModel):
    """Complete authentication data for YouTube access."""
    cookies: List[Dict[str, Any]] = Field(description="Browser cookies")
    po_token: Optional[str] = Field(default=None, description="YouTube PO token")
    visitor_data: Optional[str] = Field(default=None, description="YouTube visitor data")
    region: str = Field(description="Geographic region of extraction")
    extraction_timestamp: datetime = Field(description="When tokens were extracted")
    cookie_file_path: Optional[str] = Field(default=None, description="Path to cookie file")
    
    # IP information for proxy consistency
    browser_ip: Optional[str] = Field(default=None, description="IP address of AgentGo browser")
    browser_country: Optional[str] = Field(default=None, description="Country code of AgentGo browser")
    browser_location: Optional[Dict[str, str]] = Field(default=None, description="Detailed location info of AgentGo browser")
    
    @field_validator('po_token')
    @classmethod
    def validate_po_token(cls, v):
        """Validate PO token format."""
        if v is None:
            return v
        
        # PO tokens should be non-empty strings
        if not isinstance(v, str) or len(v.strip()) == 0:
            raise ValueError("PO token must be a non-empty string")
        
        # Remove any existing web+ prefix for validation
        token_value = v.replace('web+', '') if v.startswith('web+') else v
        
        # Basic format validation - PO tokens are typically base64-like strings
        if not re.match(r'^[A-Za-z0-9+/=_-]+$', token_value):
            raise ValueError("PO token contains invalid characters")
        
        return v
    
    @field_validator('visitor_data')
    @classmethod
    def validate_visitor_data(cls, v):
        """Validate visitor data format."""
        if v is None:
            return v
        
        # Visitor data should be non-empty strings
        if not isinstance(v, str) or len(v.strip()) == 0:
            raise ValueError("Visitor data must be a non-empty string")
        
        # Basic format validation - visitor data is typically base64-like with URL encoding
        # Allow alphanumeric, underscore, hyphen, percent (for URL encoding), plus, equals
        if not re.match(r'^[A-Za-z0-9_\-+=%]+$', v):
            raise ValueError("Visitor data contains invalid characters")
        
        return v
    
    @field_validator('region')
    @classmethod
    def validate_region(cls, v):
        """Validate region format."""
        if not isinstance(v, str) or len(v.strip()) == 0:
            raise ValueError("Region must be a non-empty string")
        return v.strip()
    
    def is_expired(self, max_age_seconds: int = 3600) -> bool:
        """Check if authentication bundle has expired."""
        if not isinstance(max_age_seconds, int) or max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be a positive integer")
        
        age_seconds = (datetime.now() - self.extraction_timestamp).total_seconds()
        return age_seconds > max_age_seconds
    
    def has_tokens(self) -> bool:
        """Check if bundle contains PO token or visitor data."""
        return bool(self.po_token) or bool(self.visitor_data)
    
    def get_formatted_po_token(self) -> Optional[str]:
        """Get PO token formatted for yt-dlp (with web+ prefix)."""
        if not self.po_token:
            return None
        
        # Add web+ prefix if not already present
        if self.po_token.startswith('web+'):
            return self.po_token
        return f"web+{self.po_token}"


class TokenExtractionResult(BaseModel):
    """Result of token extraction attempt."""
    success: bool = Field(description="Whether extraction was successful")
    po_token: Optional[str] = Field(default=None, description="Extracted PO token")
    visitor_data: Optional[str] = Field(default=None, description="Extracted visitor data")
    error_message: Optional[str] = Field(default=None, description="Error message if extraction failed")
    extraction_method: str = Field(description="Method used for extraction")
    extraction_duration: float = Field(description="Time taken for extraction in seconds")
    
    @field_validator('extraction_method')
    @classmethod
    def validate_extraction_method(cls, v):
        """Validate extraction method is one of the expected values."""
        valid_methods = ["network_intercept", "javascript", "combined", "fallback", "visitor_data_only"]
        if v not in valid_methods:
            raise ValueError(f"extraction_method must be one of: {', '.join(valid_methods)}")
        return v
    
    @field_validator('extraction_duration')
    @classmethod
    def validate_extraction_duration(cls, v):
        """Validate extraction duration is non-negative."""
        if not isinstance(v, (int, float)) or v < 0:
            raise ValueError("extraction_duration must be a non-negative number")
        return float(v)
    
    @field_validator('po_token')
    @classmethod
    def validate_po_token(cls, v):
        """Validate PO token format if present."""
        if v is None:
            return v
        
        # Use same validation as AuthenticationBundle
        if not isinstance(v, str) or len(v.strip()) == 0:
            raise ValueError("PO token must be a non-empty string")
        
        token_value = v.replace('web+', '') if v.startswith('web+') else v
        if not re.match(r'^[A-Za-z0-9+/=_-]+$', token_value):
            raise ValueError("PO token contains invalid characters")
        
        return v
    
    @field_validator('visitor_data')
    @classmethod
    def validate_visitor_data(cls, v):
        """Validate visitor data format if present."""
        if v is None:
            return v
        
        # Use same validation as AuthenticationBundle
        if not isinstance(v, str) or len(v.strip()) == 0:
            raise ValueError("Visitor data must be a non-empty string")
        
        # Allow alphanumeric, underscore, hyphen, percent (for URL encoding), plus, equals
        if not re.match(r'^[A-Za-z0-9_\-+=%]+$', v):
            raise ValueError("Visitor data contains invalid characters")
        
        return v


# ============================================================================
# New models for direct URL extraction (no server-side download)
# ============================================================================

class ExtractURLRequest(BaseModel):
    """Request model for extracting direct download URLs."""
    youtube_url: str = Field(..., description="YouTube video URL")
    resolution: VideoResolution = Field(default=VideoResolution.RES_720P, description="Preferred resolution")
    
    class Config:
        json_schema_extra = {
            "example": {
                "youtube_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                "resolution": "720"
            }
        }


class VideoFormatInfo(BaseModel):
    """Information about a single video/audio format."""
    format_id: str
    url: str
    ext: str
    resolution: Optional[str] = None
    height: Optional[int] = None
    width: Optional[int] = None
    fps: Optional[float] = None  # Changed to float to handle fractional fps
    vcodec: Optional[str] = None
    acodec: Optional[str] = None
    filesize: Optional[int] = None
    tbr: Optional[float] = None  # Total bitrate
    format_note: Optional[str] = None
    is_video: bool = False
    is_audio: bool = False
    is_video_only: bool = False
    is_audio_only: bool = False
    has_both: bool = False
    protocol: Optional[str] = None  # https, m3u8, etc.
    is_direct_download: bool = False  # True if direct download URL


class DownloadURLs(BaseModel):
    """Download URLs for a video."""
    video_url: Optional[str] = Field(None, description="Direct video download URL (googlevideo.com)")
    audio_url: Optional[str] = Field(None, description="Direct audio download URL (if separate)")
    video_format: Optional[VideoFormatInfo] = None
    audio_format: Optional[VideoFormatInfo] = None
    needs_merge: bool = Field(False, description="Whether video and audio need to be merged client-side")
    resolution: str = Field(..., description="Requested resolution")


class ExtractedVideoInfo(BaseModel):
    """Extracted video metadata."""
    video_id: str
    title: str
    duration: int = Field(..., description="Duration in seconds")
    thumbnail: Optional[str] = None
    description: Optional[str] = None
    uploader: Optional[str] = None
    uploader_id: Optional[str] = None
    view_count: Optional[int] = None
    like_count: Optional[int] = None
    upload_date: Optional[str] = None
    format_count: int = Field(..., description="Number of available formats")


class ExtractURLResponse(BaseModel):
    """Response model for URL extraction - returns direct download links."""
    success: bool = Field(..., description="Whether extraction was successful")
    video_info: Optional[ExtractedVideoInfo] = Field(None, description="Video metadata")
    download_urls: Optional[DownloadURLs] = Field(None, description="Direct download URLs")
    all_formats: Optional[List[VideoFormatInfo]] = Field(None, description="All available formats")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    extraction_time: Optional[float] = Field(None, description="Time taken for extraction in seconds")
    
    # Geo-routing and authentication info
    client_ip: Optional[str] = Field(None, description="Detected client IP address")
    detected_country: Optional[str] = Field(None, description="Detected country code")
    agentgo_region: Optional[str] = Field(None, description="AgentGo region used for authentication")
    auth_method: Optional[str] = Field(None, description="Authentication method used (agentgo/cookies/none)")
    
    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "video_info": {
                    "video_id": "dQw4w9WgXcQ",
                    "title": "Rick Astley - Never Gonna Give You Up",
                    "duration": 212,
                    "thumbnail": "https://i.ytimg.com/vi/dQw4w9WgXcQ/maxresdefault.jpg",
                    "uploader": "Rick Astley",
                    "format_count": 22
                },
                "download_urls": {
                    "video_url": "https://rr1---sn-xxx.googlevideo.com/videoplayback?...",
                    "audio_url": None,
                    "needs_merge": False,
                    "resolution": "720"
                },
                "extraction_time": 2.5
            }
        }
