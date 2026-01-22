"""Application configuration management.
Load settings from environment variables.
"""

from typing import Optional, List
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # API Keys
    qwen_api_key: str = ""

    # Aliyun OSS Configuration
    oss_access_key_id: str = ""
    oss_access_key_secret: str = ""
    oss_bucket: str = ""
    oss_endpoint: str = "oss-cn-beijing.aliyuncs.com"

    # YouTube Proxy - DEPRECATED (kept for backward compatibility)
    # PO Token is now handled by bgutil-ytdlp-pot-provider plugin
    # Cookies/Visitor Data come from AgentGo
    youtube_proxy: Optional[str] = None

    # AgentGo API for browser automation
    # Provides: Cookies + Visitor Data
    # PO Token: Handled by bgutil-ytdlp-pot-provider plugin (Docker sidecar)
    agentgo_api_key: str = ""
    agentgo_api_url: str = "https://api.browsers.live"
    agentgo_region: str = "us"  # Regions: us, uk, de, fr, jp, sg, in, au, ca

    # YouTube credentials for AgentGo login
    youtube_email: str = ""
    youtube_password: str = ""

    # HTTP Proxy for YouTube access (used by yt-dlp)
    http_proxy: Optional[str] = None

    # bgutil PO Token provider URL
    # In Docker: http://bgutil:4416 (container name)
    # Local: http://127.0.0.1:4416
    bgutil_url: str = "http://127.0.0.1:4416"

    # GeoIP Configuration
    geoip_db_path: Optional[str] = None
    enable_geo_routing: bool = True

    @property
    def youtube_proxy_list(self) -> List[str]:
        """DEPRECATED - kept for backward compatibility."""
        if not self.youtube_proxy:
            return []
        return [p.strip() for p in self.youtube_proxy.split(",") if p.strip()]

    # Application Configuration
    temp_dir: str = "/tmp/video_processing"
    log_level: str = "INFO"

    # Task Configuration
    max_video_duration: int = 600  # 10 minutes max
    transcription_timeout: int = 300  # 5 minutes timeout
    poll_interval: int = 5  # seconds

    # CORS Configuration
    cors_origins: str = "http://localhost:5173,http://localhost:5174,http://localhost:5175,http://localhost:3000"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
