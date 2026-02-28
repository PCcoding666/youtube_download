"""
FastAPI application entry point.
YouTube Video Downloader & Transcriber MVP
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

from app.config import settings
from app.api.routes import router
from app.api.auth_routes import router as auth_router
from app.api.admin_routes import router as admin_router
from app.api.credit_routes import router as credit_router
from app.api.apikey_routes import router as apikey_router
from app.api.skill_routes import router as skill_router
from app.middleware.logging_middleware import RequestLoggingMiddleware
from app.utils.ffmpeg_tools import check_ffmpeg_installed, get_ffmpeg_version
from app.database import get_database


# Beijing timezone (UTC+8)
BEIJING_TZ = timezone(timedelta(hours=8))


# Configure comprehensive logging with security considerations
class SecureFormatter(logging.Formatter):
    """Custom formatter that sanitizes sensitive data from log messages and uses Beijing time."""

    SENSITIVE_PATTERNS = [
        (r"[A-Za-z0-9+/=]{20,}", "[REDACTED_TOKEN]"),  # Tokens
        (r"password[=:]\s*\S+", "password=[REDACTED]"),  # Passwords
        (r"api[_-]?key[=:]\s*\S+", "api_key=[REDACTED]"),  # API keys
        (r"secret[=:]\s*\S+", "secret=[REDACTED]"),  # Secrets
        (r"pot=[^&\s]+", "pot=[REDACTED]"),  # PO tokens in URLs
    ]

    converter = lambda *args: datetime.now(BEIJING_TZ).timetuple()

    def format(self, record):
        # Get the original formatted message
        msg = super().format(record)

        # Sanitize sensitive data
        for pattern, replacement in self.SENSITIVE_PATTERNS:
            msg = re.sub(pattern, replacement, msg, flags=re.IGNORECASE)

        return msg


# Configure logging with enhanced security and monitoring
# Create logs directory
LOG_DIR = Path("/app/logs")
LOG_DIR.mkdir(parents=True, exist_ok=True)

# Create handlers
console_handler = logging.StreamHandler()

# File handler with daily rotation (at Beijing midnight)
from logging.handlers import TimedRotatingFileHandler
file_handler = TimedRotatingFileHandler(
    filename=LOG_DIR / "app.log",
    when="midnight",
    interval=1,
    backupCount=30,  # Keep 30 days of logs
    encoding="utf-8",
    atTime=None,
)

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
    handlers=[console_handler, file_handler],
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

    # 初始化数据库
    try:
        db = get_database()
        logger.info("本地数据库初始化成功")
    except Exception as e:
        logger.error(f"数据库初始化失败: {e}")

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

    # Pre-warm visitor_data cache (InnerTube API) so first request doesn't wait
    try:
        from app.services.visitor_data_provider import get_visitor_data
        vd = get_visitor_data()
        if vd:
            logger.info(f"Pre-warmed visitor_data cache (length: {len(vd)})")
        else:
            logger.warning("Failed to pre-warm visitor_data cache")
    except Exception as e:
        logger.warning(f"visitor_data pre-warm error: {e}")

    # Pre-initialize download pool services
    try:
        from app.services.download_pool import get_bgutil_lb, get_proxy_distributor, get_download_controller
        lb = get_bgutil_lb()
        get_proxy_distributor()
        get_download_controller()
        logger.info(f"Download pool initialized: {lb.instance_count} bgutil instances")
    except Exception as e:
        logger.warning(f"Download pool init error: {e}")

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

# Add request logging middleware
app.add_middleware(RequestLoggingMiddleware)

# Include API routes
app.include_router(router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(credit_router)
app.include_router(apikey_router)
app.include_router(skill_router)


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
