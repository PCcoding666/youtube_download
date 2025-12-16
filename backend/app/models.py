"""
Pydantic models for request/response validation.
"""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, HttpUrl
from enum import Enum
from datetime import datetime
import uuid


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
