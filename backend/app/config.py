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
    
    # YouTube Proxy (optional, for direct yt-dlp usage)
    # Support multiple proxies separated by comma for rotation
    # e.g., "http://127.0.0.1:33210,socks5://127.0.0.1:33211"
    youtube_proxy: Optional[str] = None
    
    # AgentGo API for browser automation (primary solution for YouTube access)
    # Get API key from https://docs.agentgo.live/
    agentgo_api_key: str = ""
    agentgo_api_url: str = "https://api.browsers.live"
    agentgo_region: str = "us"  # Default region: us, uk, de, fr, jp, sg, in, au, ca
    
    # YouTube credentials for AgentGo login
    youtube_email: str = ""
    youtube_password: str = ""
    
    # GeoIP Configuration
    # Path to MaxMind GeoLite2-Country.mmdb database file
    # Download from: https://dev.maxmind.com/geoip/geolite2-free-geolocation-data
    geoip_db_path: Optional[str] = None
    
    # Enable intelligent region routing based on user IP
    enable_geo_routing: bool = True
    
    @property
    def youtube_proxy_list(self) -> List[str]:
        """Get list of proxies for rotation."""
        if not self.youtube_proxy:
            return []
        return [p.strip() for p in self.youtube_proxy.split(',') if p.strip()]
    
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
