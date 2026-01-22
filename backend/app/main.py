"""
FastAPI application entry point.
YouTube Video Downloader & Transcriber MVP
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import re
from pathlib import Path

from app.config import settings
from app.api.routes import router
from app.utils.ffmpeg_tools import check_ffmpeg_installed, get_ffmpeg_version


# Configure comprehensive logging with security considerations
class SecureFormatter(logging.Formatter):
    """Custom formatter that sanitizes sensitive data from log messages."""

    SENSITIVE_PATTERNS = [
        (r"[A-Za-z0-9+/=]{20,}", "[REDACTED_TOKEN]"),  # Tokens
        (r"password[=:]\s*\S+", "password=[REDACTED]"),  # Passwords
        (r"api[_-]?key[=:]\s*\S+", "api_key=[REDACTED]"),  # API keys
        (r"secret[=:]\s*\S+", "secret=[REDACTED]"),  # Secrets
        (r"pot=[^&\s]+", "pot=[REDACTED]"),  # PO tokens in URLs
    ]

    def format(self, record):
        # Get the original formatted message
        msg = super().format(record)

        # Sanitize sensitive data
        for pattern, replacement in self.SENSITIVE_PATTERNS:
            msg = re.sub(pattern, replacement, msg, flags=re.IGNORECASE)

        return msg


# Configure logging with enhanced security and monitoring
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[
        logging.StreamHandler(),
    ],
)

# Apply secure formatter to all handlers
secure_formatter = SecureFormatter(
    "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"
)

for handler in logging.root.handlers:
    handler.setFormatter(secure_formatter)

# Set specific log levels for token extraction monitoring
logging.getLogger("app.services.agentgo_service").setLevel(logging.INFO)
logging.getLogger("app.services.downloader").setLevel(logging.INFO)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    logger.info("Starting YouTube Transcriber API...")

    # Check FFmpeg
    if check_ffmpeg_installed():
        version = get_ffmpeg_version()
        logger.info(f"FFmpeg found: {version}")
    else:
        logger.warning("FFmpeg not found! Audio extraction will fail.")

    # Create temp directory
    temp_path = Path(settings.temp_dir)
    temp_path.mkdir(parents=True, exist_ok=True)
    logger.info(f"Temp directory: {temp_path}")

    # Check configurations
    if not settings.qwen_api_key:
        logger.warning("QWEN_API_KEY not set. Transcription will be disabled.")

    if not settings.oss_access_key_id:
        logger.warning("OSS credentials not set. File upload will fail.")

    if settings.youtube_proxy:
        logger.info(f"YouTube proxy configured: {settings.youtube_proxy}")

    logger.info("API ready to receive requests")

    yield

    # Shutdown
    logger.info("Shutting down YouTube Transcriber API...")


# Create FastAPI app
app = FastAPI(
    title="YouTube Video Transcriber API",
    description="""
    A lightweight API for downloading YouTube videos and transcribing audio.
    
    ## Features
    - Download YouTube videos (up to 720p)
    - Extract audio from videos
    - Transcribe audio using Aliyun Paraformer-v2
    - Upload files to Aliyun OSS
    - Generate SRT subtitles
    
    ## Usage
    1. POST /api/v1/process with a YouTube URL
    2. Poll /api/v1/status/{task_id} for progress
    3. GET /api/v1/result/{task_id} for the final result
    """,
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Configure CORS
origins = settings.cors_origins.split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(router)


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "YouTube Video Transcriber API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/v1/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
