"""
Application configuration management.
Load settings from environment variables.
"""
from typing import Optional
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
    
    # YouTube Proxy (optional)
    # Support multiple proxies separated by comma for rotation
    # e.g., "http://127.0.0.1:33210,http://127.0.0.1:33211,socks5://127.0.0.1:33212"
    youtube_proxy: Optional[str] = None
    
    # Clash API for node switching (optional)
    clash_api_url: str = "http://127.0.0.1:9090"
    clash_api_secret: str = ""
    
    # Preferred nodes for YouTube download (node name keywords)
    youtube_preferred_nodes: str = "美国,日本原生,新加坡"
    
    @property
    def youtube_proxy_list(self) -> list:
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
    cors_origins: str = "http://localhost:5173,http://localhost:3000"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


settings = get_settings()
