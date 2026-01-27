"""
Supabase Authentication Service.
Handles JWT verification and user quota management.
"""

import logging
from typing import Optional, Tuple
from datetime import datetime
import jwt
from supabase import create_client, Client
from fastapi import HTTPException, Header, Depends
from functools import lru_cache

from app.config import settings

logger = logging.getLogger(__name__)


class AuthService:
    """Supabase authentication and quota management."""

    def __init__(self):
        self.supabase: Optional[Client] = None
        self._init_client()

    def _init_client(self):
        """Initialize Supabase client."""
        if settings.supabase_url and settings.supabase_anon_key:
            try:
                self.supabase = create_client(
                    settings.supabase_url,
                    settings.supabase_anon_key
                )
                logger.info("Supabase client initialized")
            except Exception as e:
                logger.error(f"Failed to initialize Supabase client: {e}")
                self.supabase = None

    def is_configured(self) -> bool:
        """Check if Supabase is configured."""
        return self.supabase is not None

    def verify_jwt(self, token: str) -> Optional[dict]:
        """
        Verify Supabase JWT token.
        
        Args:
            token: JWT token from Authorization header
            
        Returns:
            Decoded token payload or None if invalid
        """
        if not token:
            return None

        try:
            # Remove 'Bearer ' prefix if present
            if token.startswith("Bearer "):
                token = token[7:]

            # Use Supabase client to verify token by getting user
            if self.supabase:
                try:
                    # Set the auth token and get user
                    user_response = self.supabase.auth.get_user(token)
                    if user_response and user_response.user:
                        return {
                            "sub": user_response.user.id,
                            "email": user_response.user.email,
                            "role": user_response.user.role,
                            "aud": "authenticated"
                        }
                except Exception as e:
                    logger.warning(f"Supabase auth verification failed: {e}")
                    return None

            # Fallback: decode JWT without verification (for dev/testing)
            # In production, always use Supabase client verification above
            if settings.supabase_jwt_secret:
                payload = jwt.decode(
                    token,
                    settings.supabase_jwt_secret,
                    algorithms=["HS256"],
                    audience="authenticated"
                )
                return payload
            
            return None
        except jwt.ExpiredSignatureError:
            logger.warning("JWT token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid JWT token: {e}")
            return None

    async def get_user_quota(self, user_id: str) -> Optional[dict]:
        """
        Get user quota from Supabase.
        
        Args:
            user_id: User UUID
            
        Returns:
            User quota dict or None
        """
        if not self.supabase:
            return None

        try:
            response = self.supabase.table("user_quotas").select("*").eq(
                "user_id", user_id
            ).single().execute()
            return response.data
        except Exception as e:
            logger.error(f"Failed to get user quota: {e}")
            return None

    async def check_and_deduct_quota(self, user_id: str) -> Tuple[bool, str]:
        """
        Check if user has quota and deduct one use.
        
        Args:
            user_id: User UUID
            
        Returns:
            Tuple of (success, message)
        """
        if not self.supabase:
            # If Supabase not configured, allow access (dev mode)
            logger.warning("Supabase not configured, allowing access")
            return True, "Supabase not configured"

        try:
            # Get current quota
            quota = await self.get_user_quota(user_id)
            
            if not quota:
                # Create default quota for new user
                await self._create_default_quota(user_id)
                quota = await self.get_user_quota(user_id)
                if not quota:
                    return False, "Failed to create user quota"

            # Check if quota needs reset (monthly)
            if quota.get("reset_date"):
                reset_date = datetime.fromisoformat(quota["reset_date"].replace("Z", "+00:00"))
                if datetime.now(reset_date.tzinfo) > reset_date:
                    await self._reset_monthly_quota(user_id)
                    quota = await self.get_user_quota(user_id)

            # Check remaining quota
            monthly_limit = quota.get("monthly_video_limit", 10)
            monthly_used = quota.get("monthly_videos_used", 0)
            
            if monthly_used >= monthly_limit:
                return False, f"Monthly quota exceeded ({monthly_used}/{monthly_limit}). Please upgrade your plan."

            # Deduct quota
            new_used = monthly_used + 1
            self.supabase.table("user_quotas").update({
                "monthly_videos_used": new_used,
                "updated_at": datetime.utcnow().isoformat()
            }).eq("user_id", user_id).execute()

            remaining = monthly_limit - new_used
            logger.info(f"User {user_id} quota deducted: {new_used}/{monthly_limit} (remaining: {remaining})")
            
            return True, f"Quota used: {new_used}/{monthly_limit}"

        except Exception as e:
            logger.error(f"Failed to check/deduct quota: {e}")
            return False, f"Quota check failed: {str(e)}"

    async def _create_default_quota(self, user_id: str):
        """Create default quota for new user."""
        try:
            from datetime import timedelta
            next_month = datetime.utcnow() + timedelta(days=30)
            
            self.supabase.table("user_quotas").insert({
                "user_id": user_id,
                "monthly_video_limit": 3,  # Free tier: 3 videos/month
                "monthly_videos_used": 0,
                "total_storage_mb": 500,
                "used_storage_mb": 0,
                "reset_date": next_month.isoformat(),
                "max_video_duration_seconds": 300,  # 5 minutes max for free
                "api_access_enabled": False,
                "priority_processing": False
            }).execute()
            logger.info(f"Created default quota for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to create default quota: {e}")

    async def _reset_monthly_quota(self, user_id: str):
        """Reset monthly quota."""
        try:
            from datetime import timedelta
            next_month = datetime.utcnow() + timedelta(days=30)
            
            self.supabase.table("user_quotas").update({
                "monthly_videos_used": 0,
                "reset_date": next_month.isoformat(),
                "updated_at": datetime.utcnow().isoformat()
            }).eq("user_id", user_id).execute()
            logger.info(f"Reset monthly quota for user {user_id}")
        except Exception as e:
            logger.error(f"Failed to reset monthly quota: {e}")

    async def log_usage(
        self,
        user_id: str,
        video_url: str,
        video_title: str,
        resolution: str,
        file_size: int,
        oss_url: str
    ):
        """Log video download usage."""
        if not self.supabase:
            return

        try:
            # Generate a unique video_id
            import uuid
            video_id = f"dl_{uuid.uuid4().hex[:12]}"
            
            self.supabase.table("videos").insert({
                "video_id": video_id,
                "user_id": user_id,
                "title": video_title[:255] if video_title else "Unknown",
                "source_type": "youtube",
                "original_url": video_url,
                "oss_video_url": oss_url,
                "video_resolution": resolution,
                "video_size": file_size,
                "processing_status": "completed"
            }).execute()
            logger.info(f"Logged usage for user {user_id}: {video_title}")
        except Exception as e:
            logger.error(f"Failed to log usage: {e}")


# Global auth service instance
_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """Get or create global auth service instance."""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service


async def get_current_user(
    authorization: Optional[str] = Header(None, alias="Authorization")
) -> Optional[dict]:
    """
    FastAPI dependency to get current user from JWT.
    
    Returns None if no auth header (allows anonymous access).
    Raises HTTPException if token is invalid.
    """
    auth_service = get_auth_service()
    
    if not auth_service.is_configured():
        # Dev mode: no auth required
        return None
    
    if not authorization:
        return None
    
    user = auth_service.verify_jwt(authorization)
    if authorization and not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return user


async def require_auth(
    authorization: Optional[str] = Header(None, alias="Authorization")
) -> dict:
    """
    FastAPI dependency that requires authentication.
    
    Raises HTTPException if not authenticated.
    """
    auth_service = get_auth_service()
    
    if not auth_service.is_configured():
        # Dev mode: return mock user
        return {"sub": "dev-user-id", "email": "dev@example.com"}
    
    if not authorization:
        raise HTTPException(status_code=401, detail="Authentication required")
    
    user = auth_service.verify_jwt(authorization)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    
    return user
