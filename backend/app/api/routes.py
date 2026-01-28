"""
API routes for video processing.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Response, Request, Depends, Header
from typing import Dict, Optional
import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
import shutil

from app.models import (
    ProcessRequest,
    ProcessResponse,
    TaskStatusResponse,
    TaskResultResponse,
    TaskStatus,
    TaskData,
    TranscriptSegment,
    HealthResponse,
    ExtractURLRequest,
    ExtractURLResponse,
    ExtractedVideoInfo,
    DownloadURLs,
    VideoFormatInfo,
)
from app.config import settings
from app.services.downloader import YouTubeDownloader, DownloadError, get_proxy_rotator
from app.services.transcriber import ParaformerTranscriber
from app.services.storage import get_storage
from app.services.auth_service import get_auth_service, get_current_user, require_auth
from app.utils.ffmpeg_tools import extract_audio, check_ffmpeg_installed
from app.database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["video"])

# In-memory task storage (use Redis/DB for production)
tasks: Dict[str, TaskData] = {}


def get_task(task_id: str) -> TaskData:
    """Get task by ID or raise 404."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks[task_id]


def get_client_ip(request: Request) -> str:
    """
    Extract client IP from request, handling proxy headers.

    Args:
        request: FastAPI request object

    Returns:
        Client IP address string
    """
    # Check for forwarded headers (common with reverse proxies)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP in the chain (original client)
        return forwarded_for.split(",")[0].strip()

    # Check for real IP header (used by some proxies)
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    # Fallback to direct client IP
    return request.client.host if request.client else "0.0.0.0"


async def get_region_for_request(request: Request) -> tuple[str, Optional[str], str]:
    """
    Get AgentGo region for the request based on client IP.

    Args:
        request: FastAPI request object

    Returns:
        Tuple of (region, country_code, client_ip)
    """
    client_ip = get_client_ip(request)

    # Check if geo-routing is enabled
    if not getattr(settings, "enable_geo_routing", True):
        logger.debug("Geo-routing disabled, using default region")
        return getattr(settings, "agentgo_region", "us"), None, client_ip

    try:
        from app.services.geo_service import get_region_for_ip

        region, country_code = await get_region_for_ip(client_ip)
        logger.info(
            f"Geo-routing: IP {client_ip} -> Country {country_code} -> Region {region}"
        )
        return region, country_code, client_ip
    except Exception as e:
        logger.warning(f"Geo-routing failed for IP {client_ip}: {e}")
        return getattr(settings, "agentgo_region", "us"), None, client_ip


async def process_video_task(task_id: str):
    """
    Background task to process video.
    Steps: Download -> Extract Audio -> Upload -> Transcribe
    """
    task = tasks.get(task_id)
    if not task:
        logger.error(f"Task not found: {task_id}")
        return

    # Create temp directory for this task
    temp_dir = Path(settings.temp_dir) / task_id
    temp_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Step 1: Download YouTube video
        task.status = TaskStatus.DOWNLOADING
        task.progress = 10
        task.updated_at = datetime.now()

        logger.info(
            f"[{task_id}] Downloading video: {task.youtube_url} "
            f"(region: {task.region or 'default'})"
        )

        # Create downloader with region for intelligent routing
        downloader = YouTubeDownloader(resolution=task.resolution, region=task.region)

        # Pre-fetch authentication bundle for the region if available
        if task.region:
            try:
                logger.info(
                    f"[{task_id}] Pre-fetching authentication bundle for region: {task.region}"
                )
                # Add timeout for authentication bundle fetching
                await asyncio.wait_for(
                    downloader.prefetch_authentication_for_region(),
                    timeout=90,  # 90 seconds timeout for authentication
                )
                logger.info(f"[{task_id}] Authentication bundle pre-fetch completed")
            except asyncio.TimeoutError:
                logger.warning(
                    f"[{task_id}] Authentication bundle pre-fetch timed out after 90s, continuing with fallback"
                )
                # Continue with download - fallback mechanisms will handle this
            except Exception as e:
                logger.warning(
                    f"[{task_id}] Failed to prefetch authentication bundle: {e}"
                )
                # Fallback to legacy cookie prefetching for backward compatibility
                try:
                    logger.info(
                        f"[{task_id}] Attempting legacy cookie prefetch as fallback"
                    )
                    await asyncio.wait_for(
                        downloader.prefetch_cookies_for_region(),
                        timeout=60,  # 60 seconds timeout for legacy cookies
                    )
                    logger.info(f"[{task_id}] Legacy cookie prefetch completed")
                except asyncio.TimeoutError:
                    logger.warning(
                        f"[{task_id}] Legacy cookie prefetch timed out after 60s"
                    )
                except Exception as e2:
                    logger.warning(f"[{task_id}] Failed to prefetch cookies: {e2}")
                    # Continue anyway - direct download may still work

        # Use enhanced download with timeout handling
        try:
            video_path, video_info = await asyncio.wait_for(
                downloader.download(task.youtube_url, str(temp_dir)),
                timeout=600,  # 10 minutes timeout for download
            )
        except asyncio.TimeoutError:
            logger.error(f"[{task_id}] Download timed out after 10 minutes")
            raise DownloadError("Download operation timed out after 10 minutes")
        except Exception as e:
            # Enhanced error handling for token extraction failures
            error_msg = str(e).lower()
            if any(
                keyword in error_msg
                for keyword in ["token", "authentication", "po_token", "visitor_data"]
            ):
                logger.error(f"[{task_id}] Token extraction related error: {e}")
                raise DownloadError(f"Authentication token extraction failed: {str(e)}")
            else:
                # Re-raise original exception for other types of errors
                raise

        task.video_path = video_path
        task.video_title = video_info.get("title", "Unknown")
        task.video_duration = video_info.get("duration", 0)
        task.progress = 30
        task.updated_at = datetime.now()

        logger.info(f"[{task_id}] Download complete: {task.video_title}")

        # Step 2: Extract audio
        task.status = TaskStatus.EXTRACTING_AUDIO
        task.progress = 40
        task.updated_at = datetime.now()

        logger.info(f"[{task_id}] Extracting audio...")

        audio_path = await extract_audio(video_path)
        task.audio_path = audio_path
        task.progress = 50
        task.updated_at = datetime.now()

        logger.info(f"[{task_id}] Audio extraction complete")

        # Step 3: Upload to OSS
        task.status = TaskStatus.UPLOADING
        task.progress = 60
        task.updated_at = datetime.now()

        logger.info(f"[{task_id}] Uploading to OSS...")

        storage = get_storage()

        # Upload video
        video_key = f"videos/{task_id}/{Path(video_path).name}"
        task.video_url = await storage.upload_file(video_path, video_key)

        # Upload audio
        audio_key = f"audio/{task_id}/{Path(audio_path).name}"
        task.audio_url = await storage.upload_file(audio_path, audio_key)

        task.progress = 70
        task.updated_at = datetime.now()

        logger.info(f"[{task_id}] Upload complete")

        # Step 4: Transcribe (if enabled)
        if task.enable_transcription and settings.qwen_api_key:
            task.status = TaskStatus.TRANSCRIBING
            task.progress = 80
            task.updated_at = datetime.now()

            logger.info(f"[{task_id}] Starting transcription...")

            transcriber = ParaformerTranscriber()
            segments = await transcriber.transcribe_from_url(task.audio_url)

            if segments:
                task.transcript = segments
                task.full_text = transcriber.get_full_text(segments)
                logger.info(
                    f"[{task_id}] Transcription complete: {len(segments)} segments"
                )
            else:
                logger.warning(f"[{task_id}] Transcription returned no results")

        # Complete
        task.status = TaskStatus.COMPLETED
        task.progress = 100
        task.completed_at = datetime.now()
        task.updated_at = datetime.now()

        logger.info(f"[{task_id}] Task completed successfully")

    except DownloadError as e:
        error_msg = str(e)
        logger.error(f"[{task_id}] Download error: {error_msg}")

        # Provide more specific error messages for different failure types
        if "timeout" in error_msg.lower():
            task.error_message = f"Download timed out: {error_msg}"
        elif any(
            keyword in error_msg.lower()
            for keyword in ["token", "authentication", "po_token", "visitor_data"]
        ):
            task.error_message = f"Authentication failed: {error_msg}"
        elif any(
            keyword in error_msg.lower()
            for keyword in ["403", "blocked", "bot", "captcha"]
        ):
            task.error_message = f"Access blocked by YouTube: {error_msg}"
        else:
            task.error_message = f"Download failed: {error_msg}"

        task.status = TaskStatus.FAILED
        task.updated_at = datetime.now()

    except Exception as e:
        logger.error(f"[{task_id}] Processing error: {e}")
        task.status = TaskStatus.FAILED
        task.error_message = str(e)
        task.updated_at = datetime.now()

    finally:
        # Cleanup temp files
        try:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
                logger.info(f"[{task_id}] Cleaned up temp directory")
        except Exception as e:
            logger.warning(f"[{task_id}] Failed to cleanup: {e}")


@router.post("/process", response_model=ProcessResponse)
async def process_video(
    request_data: ProcessRequest, request: Request, background_tasks: BackgroundTasks
):
    """
    Submit a YouTube video for processing.

    Automatically routes to optimal region based on client IP:
    - Downloads the video using region-matched AgentGo browser
    - Extracts audio
    - Uploads to cloud storage
    - Optionally transcribes audio
    """
    # Validate URL
    if not request_data.youtube_url.startswith(
        ("https://www.youtube.com", "https://youtube.com", "https://youtu.be")
    ):
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")

    # Get region for this request based on client IP
    region, country_code, client_ip = await get_region_for_request(request)

    # Create task with geo-routing info
    task = TaskData(
        youtube_url=request_data.youtube_url,
        enable_transcription=request_data.enable_transcription,
        resolution=request_data.resolution.value,
        user_ip=client_ip,
        country_code=country_code,
        region=region,
    )

    tasks[task.task_id] = task

    # Start background processing
    background_tasks.add_task(process_video_task, task.task_id)

    logger.info(
        f"Task created: {task.task_id} for {request_data.youtube_url} "
        f"(IP: {client_ip}, Country: {country_code}, Region: {region})"
    )

    return ProcessResponse(
        task_id=task.task_id,
        status=task.status,
        message=f"Task submitted successfully. Region: {region}. Use /status/{{task_id}} to check progress.",
    )


@router.get("/status/{task_id}", response_model=TaskStatusResponse)
async def get_status(task_id: str):
    """Get current status of a processing task."""
    task = get_task(task_id)

    return TaskStatusResponse(
        task_id=task.task_id,
        status=task.status,
        progress=task.progress,
        error_message=task.error_message,
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


@router.get("/result/{task_id}", response_model=TaskResultResponse)
async def get_result(task_id: str):
    """Get processing result for a completed task."""
    task = get_task(task_id)

    transcript_segments = None
    if task.transcript:
        transcript_segments = [
            TranscriptSegment(
                text=seg.get("text", ""),
                start_time=seg.get("start_time", 0),
                end_time=seg.get("end_time", 0),
                speaker_id=seg.get("speaker_id"),
            )
            for seg in task.transcript
        ]

    return TaskResultResponse(
        task_id=task.task_id,
        status=task.status,
        video_url=task.video_url,
        audio_url=task.audio_url,
        video_title=task.video_title,
        video_duration=task.video_duration,
        transcript=transcript_segments,
        full_text=task.full_text,
        created_at=task.created_at,
        completed_at=task.completed_at,
    )


@router.get("/download/{task_id}/subtitle")
async def download_subtitle(task_id: str):
    """Download SRT subtitle file for a task."""
    task = get_task(task_id)

    if not task.transcript:
        raise HTTPException(
            status_code=404, detail="No transcript available for this task"
        )

    transcriber = ParaformerTranscriber()
    srt_content = transcriber.generate_srt(task.transcript)

    # Clean filename
    filename = task.video_title or task_id
    filename = "".join(c for c in filename if c.isalnum() or c in (" ", "-", "_"))[:50]

    return Response(
        content=srt_content,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}.srt"'},
    )


@router.get("/tasks")
async def list_tasks():
    """List all tasks (for debugging)."""
    return {
        "count": len(tasks),
        "tasks": [
            {
                "task_id": t.task_id,
                "status": t.status,
                "progress": t.progress,
                "video_title": t.video_title,
                "created_at": t.created_at,
            }
            for t in tasks.values()
        ],
    }


@router.delete("/tasks/{task_id}")
async def delete_task(task_id: str):
    """Delete a task."""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    del tasks[task_id]
    return {"message": "Task deleted successfully"}


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    return HealthResponse(status="healthy", version="1.0.0")


@router.get("/quota/anonymous")
async def check_anonymous_quota(request: Request):
    """
    检查匿名用户的配额（基于IP）
    
    Returns:
        剩余使用次数
    """
    db = get_database()
    client_ip = get_client_ip(request)
    
    can_use, usage_count = db.check_anonymous_usage(client_ip)
    remaining = max(0, 3 - usage_count)
    
    return {
        "ip": client_ip,
        "used": usage_count,
        "remaining": remaining,
        "total": 3,
        "can_use": can_use,
        "need_register": not can_use
    }


@router.get("/system/info")
async def system_info(request: Request):
    """
    Get system information including proxy pool status and geo-routing info.
    """
    proxy_rotator = get_proxy_rotator()

    # Get geo-routing info for current request
    geo_info = {}
    try:
        region, country_code, client_ip = await get_region_for_request(request)
        geo_info = {
            "enabled": getattr(settings, "enable_geo_routing", True),
            "client_ip": client_ip,
            "detected_country": country_code,
            "selected_region": region,
            "supported_regions": ["us", "uk", "de", "fr", "jp", "sg", "in", "au", "ca"],
        }
    except Exception as e:
        geo_info = {"enabled": False, "error": str(e)}

    # Get cached authentication bundles per region
    cached_regions = {}
    auth_bundle_info = {}
    try:
        from app.services.agentgo_service import get_agentgo_service

        service = get_agentgo_service()
        cached_regions = service.get_all_cached_regions()

        # Get detailed info about cached authentication bundles
        for region, cookie_file in cached_regions.items():
            try:
                # Try to get authentication bundle info
                auth_bundle = await service.get_youtube_authentication_bundle(
                    region=region
                )
                if auth_bundle:
                    auth_bundle_info[region] = {
                        "cookie_file": cookie_file,
                        "has_tokens": auth_bundle.has_tokens(),
                        "po_token_available": bool(auth_bundle.po_token),
                        "visitor_data_available": bool(auth_bundle.visitor_data),
                        "extraction_timestamp": auth_bundle.extraction_timestamp.isoformat(),
                        "is_expired": auth_bundle.is_expired(),
                    }
                else:
                    auth_bundle_info[region] = {
                        "cookie_file": cookie_file,
                        "has_tokens": False,
                        "po_token_available": False,
                        "visitor_data_available": False,
                        "extraction_timestamp": None,
                        "is_expired": True,
                    }
            except Exception as e:
                auth_bundle_info[region] = {"cookie_file": cookie_file, "error": str(e)}
    except Exception:
        pass

    return {
        "ffmpeg_installed": check_ffmpeg_installed(),
        "oss_configured": bool(settings.oss_access_key_id),
        "transcription_enabled": bool(settings.qwen_api_key),
        "proxy_configured": bool(settings.youtube_proxy),
        "proxy_pool": {
            "total_proxies": len(proxy_rotator),
            "proxies": proxy_rotator.get_all(),
            "failed_proxies": list(proxy_rotator.failed_proxies),
        },
        "geo_routing": geo_info,
        "cached_cookies_regions": list(cached_regions.keys()),
        "authentication_bundles": auth_bundle_info,
        "temp_dir": settings.temp_dir,
    }


@router.get("/geo/detect")
async def detect_geo(request: Request):
    """
    Detect geographic location for the current request.

    Returns:
        Client IP, detected country, and mapped AgentGo region
    """
    region, country_code, client_ip = await get_region_for_request(request)

    return {
        "client_ip": client_ip,
        "country_code": country_code,
        "agentgo_region": region,
        "geo_routing_enabled": getattr(settings, "enable_geo_routing", True),
        "supported_regions": ["us", "uk", "de", "fr", "jp", "sg", "in", "au", "ca"],
    }


@router.get("/geo/lookup/{ip}")
async def lookup_ip_geo(ip: str):
    """
    Look up geographic information for a specific IP address.

    Args:
        ip: IP address to look up

    Returns:
        Country code and mapped AgentGo region
    """
    try:
        from app.services.geo_service import get_region_for_ip

        region, country_code = await get_region_for_ip(ip)

        return {
            "ip": ip,
            "country_code": country_code,
            "agentgo_region": region,
            "supported_regions": ["us", "uk", "de", "fr", "jp", "sg", "in", "au", "ca"],
        }
    except Exception as e:
        return {"ip": ip, "error": str(e)}


@router.get("/geo/cookies")
async def get_cached_cookies():
    """
    Get information about cached authentication bundles per region.

    Returns:
        List of regions with valid cached authentication data
    """
    try:
        from app.services.agentgo_service import get_agentgo_service

        service = get_agentgo_service()

        cached = service.get_all_cached_regions()
        auth_bundle_details = {}

        # Get detailed information about each cached region
        for region, cookie_file in cached.items():
            try:
                auth_bundle = await service.get_youtube_authentication_bundle(
                    region=region
                )
                if auth_bundle:
                    auth_bundle_details[region] = {
                        "cookie_file": cookie_file,
                        "has_tokens": auth_bundle.has_tokens(),
                        "po_token_available": bool(auth_bundle.po_token),
                        "visitor_data_available": bool(auth_bundle.visitor_data),
                        "extraction_timestamp": auth_bundle.extraction_timestamp.isoformat(),
                        "is_expired": auth_bundle.is_expired(),
                        "age_seconds": (
                            datetime.now() - auth_bundle.extraction_timestamp
                        ).total_seconds(),
                    }
                else:
                    auth_bundle_details[region] = {
                        "cookie_file": cookie_file,
                        "error": "Failed to load authentication bundle",
                    }
            except Exception as e:
                auth_bundle_details[region] = {
                    "cookie_file": cookie_file,
                    "error": str(e),
                }

        return {
            "cached_regions": list(cached.keys()),
            "total_cached": len(cached),
            "supported_regions": service.SUPPORTED_REGIONS,
            "authentication_bundles": auth_bundle_details,
        }
    except Exception as e:
        return {"error": str(e)}


@router.post("/auth/test/{region}")
async def test_authentication_bundle(region: str):
    """
    Test authentication bundle extraction for a specific region.

    Args:
        region: AgentGo region code to test

    Returns:
        Test results including token extraction status
    """
    supported_regions = ["us", "uk", "de", "fr", "jp", "sg", "in", "au", "ca"]

    if region not in supported_regions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid region. Supported: {', '.join(supported_regions)}",
        )

    try:
        from app.services.agentgo_service import get_agentgo_service

        service = get_agentgo_service()

        if not service.is_configured():
            return {
                "success": False,
                "region": region,
                "message": "AgentGo not configured. Set AGENTGO_API_KEY, YOUTUBE_EMAIL, YOUTUBE_PASSWORD.",
            }

        start_time = time.time()

        # Test authentication bundle extraction with timeout
        try:
            auth_bundle = await asyncio.wait_for(
                service.get_youtube_authentication_bundle(
                    region=region, force_refresh=True
                ),
                timeout=180,  # 3 minutes timeout for testing
            )
        except asyncio.TimeoutError:
            return {
                "success": False,
                "region": region,
                "duration": time.time() - start_time,
                "message": "Authentication bundle extraction timed out after 3 minutes",
            }

        duration = time.time() - start_time

        if auth_bundle:
            return {
                "success": True,
                "region": region,
                "duration": duration,
                "results": {
                    "cookies_count": len(auth_bundle.cookies),
                    "has_tokens": auth_bundle.has_tokens(),
                    "po_token_available": bool(auth_bundle.po_token),
                    "po_token_length": len(auth_bundle.po_token)
                    if auth_bundle.po_token
                    else 0,
                    "visitor_data_available": bool(auth_bundle.visitor_data),
                    "visitor_data_length": len(auth_bundle.visitor_data)
                    if auth_bundle.visitor_data
                    else 0,
                    "cookie_file_path": auth_bundle.cookie_file_path,
                    "extraction_timestamp": auth_bundle.extraction_timestamp.isoformat(),
                },
                "message": "Authentication bundle extraction successful",
            }
        else:
            return {
                "success": False,
                "region": region,
                "duration": duration,
                "message": "Failed to extract authentication bundle",
            }

    except Exception as e:
        logger.error(f"Error testing authentication bundle for region {region}: {e}")
        return {
            "success": False,
            "region": region,
            "error": str(e),
            "message": "Authentication bundle test failed with exception",
        }


@router.post("/geo/prefetch/{region}")
async def prefetch_cookies_for_region(region: str):
    """
    Pre-fetch and cache authentication bundle for a specific region.

    Args:
        region: AgentGo region code (us, uk, de, fr, jp, sg, in, au, ca)

    Returns:
        Status of the prefetch operation
    """
    supported_regions = ["us", "uk", "de", "fr", "jp", "sg", "in", "au", "ca"]

    if region not in supported_regions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid region. Supported: {', '.join(supported_regions)}",
        )

    try:
        from app.services.agentgo_service import get_agentgo_service

        service = get_agentgo_service()

        if not service.is_configured():
            return {
                "success": False,
                "message": "AgentGo not configured. Set AGENTGO_API_KEY, YOUTUBE_EMAIL, YOUTUBE_PASSWORD.",
            }

        # Use enhanced authentication bundle fetching with timeout
        try:
            auth_bundle = await asyncio.wait_for(
                service.get_youtube_authentication_bundle(
                    region=region, force_refresh=True
                ),
                timeout=120,  # 2 minutes timeout
            )
        except asyncio.TimeoutError:
            return {
                "success": False,
                "region": region,
                "message": "Authentication bundle fetch timed out after 2 minutes",
            }

        if auth_bundle:
            return {
                "success": True,
                "region": region,
                "cookie_file": auth_bundle.cookie_file_path,
                "has_tokens": auth_bundle.has_tokens(),
                "po_token_available": bool(auth_bundle.po_token),
                "visitor_data_available": bool(auth_bundle.visitor_data),
                "message": f"Authentication bundle for region {region} cached successfully",
            }
        else:
            return {
                "success": False,
                "region": region,
                "message": "Failed to fetch authentication bundle",
            }
    except Exception as e:
        logger.error(
            f"Error prefetching authentication bundle for region {region}: {e}"
        )
        return {"success": False, "region": region, "error": str(e)}


# ============================================================================
# User Quota API
# ============================================================================


@router.get("/user/quota")
async def get_user_quota(current_user: dict = Depends(require_auth)):
    """
    Get current user's quota information.
    
    Requires authentication.
    """
    auth_service = get_auth_service()
    user_id = current_user.get("sub")
    
    if not auth_service.is_configured():
        return {
            "configured": False,
            "message": "Quota system not configured (dev mode)"
        }
    
    quota = await auth_service.get_user_quota(user_id)
    
    if not quota:
        # Create default quota
        await auth_service._create_default_quota(user_id)
        quota = await auth_service.get_user_quota(user_id)
    
    return {
        "configured": True,
        "user_id": user_id,
        "quota": {
            "monthly_limit": quota.get("monthly_video_limit", 0),
            "monthly_used": quota.get("monthly_videos_used", 0),
            "remaining": quota.get("monthly_video_limit", 0) - quota.get("monthly_videos_used", 0),
            "reset_date": quota.get("reset_date"),
            "storage_limit_mb": quota.get("total_storage_mb", 0),
            "storage_used_mb": quota.get("used_storage_mb", 0),
            "max_video_duration_seconds": quota.get("max_video_duration_seconds", 300),
            "priority_processing": quota.get("priority_processing", False)
        }
    }


@router.get("/user/history")
async def get_user_history(
    current_user: dict = Depends(require_auth),
    limit: int = 20
):
    """
    Get user's download history.
    
    Requires authentication.
    """
    auth_service = get_auth_service()
    user_id = current_user.get("sub")
    
    if not auth_service.is_configured() or not auth_service.supabase:
        return {"configured": False, "videos": []}
    
    try:
        response = auth_service.supabase.table("videos").select(
            "video_id, title, original_url, oss_video_url, video_resolution, video_size, created_at"
        ).eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
        
        return {
            "configured": True,
            "videos": response.data or []
        }
    except Exception as e:
        logger.error(f"Failed to get user history: {e}")
        return {"configured": True, "videos": [], "error": str(e)}


# ============================================================================
# Direct URL Extraction API (download to server, upload to OSS)
# ============================================================================


async def get_current_user_local(authorization: Optional[str] = Header(None)) -> Optional[dict]:
    """从本地数据库获取当前用户"""
    if not authorization:
        return None

    # 解析 Bearer token
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None

    token = parts[1]
    db = get_database()
    user = db.verify_token(token)

    return user


@router.post("/extract", response_model=ExtractURLResponse)
async def extract_direct_urls(
    request_data: ExtractURLRequest,
    request: Request,
    authorization: Optional[str] = Header(None)
):
    """
    Download YouTube video and upload to OSS.

    允许匿名用户使用3次（基于IP），之后需要注册+付费。
    注册用户无限制使用。
    
    Anonymous users get 3 downloads (IP-based), then need to register + upgrade.

    Workflow:
    1. Verify user authentication (if configured)
    2. Check user quota
    3. Download video using yt-dlp via subprocess
    4. Upload to OSS
    5. Deduct quota and log usage
    6. Return OSS download URL

    Args:
        request_data: YouTube URL and preferred resolution
        request: FastAPI request object for IP detection
        current_user: Authenticated user from JWT (optional)

    Returns:
        OSS download URLs and video metadata
    """
    import uuid
    import subprocess
    import json
    from pathlib import Path
    import shutil

    start_time = time.time()
    task_id = str(uuid.uuid4())[:8]
    temp_dir = Path(settings.temp_dir) / f"extract_{task_id}"

    # Validate URL
    if not request_data.youtube_url.startswith(
        ("https://www.youtube.com", "https://youtube.com", "https://youtu.be")
    ):
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")

    # Initialize variables for error handling
    client_ip = None
    country_code = None
    region = None
    user_id = None

    # 使用本地数据库进行认证和配额检查
    db = get_database()
    
    # 获取客户端IP
    client_ip = get_client_ip(request)
    
    # 获取当前用户（可选）
    current_user = await get_current_user_local(authorization)
    
    if current_user:
        # 已登录用户 - 无限制使用
        user_id = current_user["id"]
        quota_ok, quota_msg = db.check_and_deduct_quota(user_id)
        
        if not quota_ok:
            raise HTTPException(
                status_code=402,
                detail=quota_msg
            )
        
        logger.info(f"[{task_id}] User {user_id} ({current_user['username']}) - {quota_msg}")
    else:
        # 匿名用户 - 基于IP限制3次
        can_use, usage_count = db.check_anonymous_usage(client_ip)
        
        if not can_use:
            raise HTTPException(
                status_code=402,
                detail=f"免费额度已用完（{usage_count}/3次）。请注册并付费以继续使用。"
            )
        
        # 增加匿名使用次数
        new_count = db.increment_anonymous_usage(client_ip)
        logger.info(f"[{task_id}] Anonymous user {client_ip} - 使用次数: {new_count}/3")

    try:
        from app.services.storage import get_storage

        # Create temp directory
        temp_dir.mkdir(parents=True, exist_ok=True)

        # Get region based on user's IP
        region, country_code, client_ip = await get_region_for_request(request)
        logger.info(
            f"[{task_id}] Download request: {request_data.youtube_url[:50]}... "
            f"(IP: {client_ip}, Resolution: {request_data.resolution.value}, User: {user_id or 'anonymous'})"
        )

        # Step 1: Download video using subprocess (more stable than async yt-dlp)
        download_start = time.time()
        logger.info(f"[{task_id}] Starting download via subprocess...")

        resolution = request_data.resolution.value
        if resolution == "audio":
            format_str = "bestaudio[ext=m4a]/bestaudio"
        elif resolution == "best":
            format_str = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
        else:
            format_str = f"bestvideo[height<={resolution}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={resolution}]+bestaudio/best[height<={resolution}]"

        # Import agentgo service
        from app.services.agentgo_service import get_agentgo_service
        agentgo = get_agentgo_service()
        
        # Retry mechanism for YouTube anti-bot detection
        MAX_RETRIES = 3
        last_error = None
        result = None
        
        for attempt in range(1, MAX_RETRIES + 1):
            logger.info(f"[{task_id}] Download attempt {attempt}/{MAX_RETRIES}")
            
            # Get cookies (force refresh on retry)
            cookie_file_path = None
            try:
                if attempt == 1:
                    # First attempt: try cached cookies
                    cookie_file_path = agentgo.get_cached_cookie_file(region)
                
                # If no cached cookies or retrying, get fresh ones
                if not cookie_file_path and agentgo.is_api_configured():
                    logger.info(f"[{task_id}] Fetching fresh cookies for region: {region} (attempt {attempt})")
                    auth_bundle = await asyncio.wait_for(
                        agentgo.get_youtube_authentication_bundle(region=region, force_refresh=(attempt > 1)),
                        timeout=120
                    )
                    if auth_bundle and auth_bundle.cookie_file_path:
                        cookie_file_path = auth_bundle.cookie_file_path
                        logger.info(f"[{task_id}] Got fresh cookies: {cookie_file_path}")
            except asyncio.TimeoutError:
                logger.warning(f"[{task_id}] Cookie extraction timed out (attempt {attempt})")
            except Exception as e:
                logger.warning(f"[{task_id}] Failed to get cookies (attempt {attempt}): {e}")

            # Build yt-dlp command
            cmd = [
                "yt-dlp",
                "-f", format_str,
                "--merge-output-format", "mp4",
                "-o", f"{temp_dir}/%(id)s.%(ext)s",
                "--print-json",
                "--no-simulate",
                request_data.youtube_url
            ]

            # Add cookies if available
            if cookie_file_path and Path(cookie_file_path).exists():
                cmd.insert(1, "--cookies")
                cmd.insert(2, cookie_file_path)
                logger.info(f"[{task_id}] Using cookies file: {cookie_file_path}")
            else:
                logger.warning(f"[{task_id}] No cookies available, YouTube may block the request")

            # Add proxy if configured
            if settings.http_proxy:
                cmd.insert(1, "--proxy")
                cmd.insert(2, settings.http_proxy)
                logger.info(f"[{task_id}] Using proxy: {settings.http_proxy}")

            # Run yt-dlp in subprocess
            loop = asyncio.get_running_loop()
            
            def run_ytdlp():
                return subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=600  # 10 minutes timeout
                )

            result = await loop.run_in_executor(None, run_ytdlp)

            if result.returncode == 0:
                logger.info(f"[{task_id}] Download succeeded on attempt {attempt}")
                break  # Success!
            
            # Check if it's a bot detection error (worth retrying)
            error_msg = result.stderr[-500:] if result.stderr else "Unknown error"
            is_bot_error = "Sign in to confirm you're not a bot" in error_msg or "bot" in error_msg.lower()
            
            if is_bot_error and attempt < MAX_RETRIES:
                logger.warning(f"[{task_id}] Bot detection on attempt {attempt}, will retry with fresh cookies...")
                last_error = error_msg
                # Clear cached cookies to force refresh
                try:
                    cached_file = agentgo.get_cached_cookie_file(region)
                    if cached_file and Path(cached_file).exists():
                        Path(cached_file).unlink()
                        logger.info(f"[{task_id}] Cleared cached cookies for retry")
                except Exception:
                    pass
                await asyncio.sleep(2)  # Brief delay before retry
            else:
                logger.error(f"[{task_id}] yt-dlp failed: {error_msg}")
                last_error = error_msg
                if attempt == MAX_RETRIES:
                    raise Exception(f"Download failed after {MAX_RETRIES} attempts: {error_msg}")

        # Parse video info from JSON output
        video_info = {}
        try:
            # yt-dlp outputs JSON on stdout
            video_info = json.loads(result.stdout.strip().split('\n')[-1])
        except json.JSONDecodeError:
            logger.warning(f"[{task_id}] Could not parse video info JSON")

        download_time = time.time() - download_start

        # Find the downloaded file
        video_path = None
        for f in temp_dir.iterdir():
            if f.suffix == '.mp4':
                video_path = str(f)
                break

        if not video_path or not Path(video_path).exists():
            raise Exception("Downloaded file not found")

        file_size = Path(video_path).stat().st_size
        logger.info(f"[{task_id}] Download completed in {download_time:.2f}s: {file_size / 1024 / 1024:.2f} MB")

        # Step 2: Upload to OSS
        upload_start = time.time()
        logger.info(f"[{task_id}] Uploading to OSS...")

        storage = get_storage()

        # Sanitize filename for OSS
        safe_title = "".join(
            c for c in video_info.get("title", "video")[:50]
            if c.isalnum() or c in (" ", "-", "_")
        ).strip() or "video"

        video_ext = Path(video_path).suffix.lstrip('.') or 'mp4'
        object_key = f"downloads/{task_id}/{safe_title}.{video_ext}"
        oss_video_url = await storage.upload_file(video_path, object_key)

        upload_time = time.time() - upload_start
        extraction_time = time.time() - start_time

        logger.info(
            f"[{task_id}] Upload completed in {upload_time:.2f}s. "
            f"Total time: {extraction_time:.2f}s. URL: {oss_video_url}"
        )

        # Build response
        extracted_video_info = ExtractedVideoInfo(
            video_id=video_info.get("id", task_id),
            title=video_info.get("title", "Unknown"),
            duration=video_info.get("duration", 0),
            thumbnail=video_info.get("thumbnail"),
            description=video_info.get("description"),
            uploader=video_info.get("uploader"),
            uploader_id=video_info.get("uploader_id"),
            view_count=video_info.get("view_count"),
            like_count=video_info.get("like_count"),
            upload_date=video_info.get("upload_date"),
            format_count=len(video_info.get("formats", [])),
        )

        # Build download URLs - pointing to OSS
        video_format = VideoFormatInfo(
            format_id="oss",
            url=oss_video_url,
            ext=video_ext,
            resolution=f"{resolution}p" if resolution.isdigit() else resolution,
            height=int(resolution) if resolution.isdigit() else None,
            width=video_info.get("width"),
            fps=video_info.get("fps"),
            vcodec=video_info.get("vcodec", "merged"),
            acodec=video_info.get("acodec", "merged"),
            filesize=file_size,
            tbr=video_info.get("tbr"),
            format_note="Downloaded and uploaded to OSS",
            is_video=True,
            is_audio=True,
            is_video_only=False,
            is_audio_only=False,
            has_both=True,
            protocol="https",
            is_direct_download=True,
        )

        download_urls = DownloadURLs(
            video_url=oss_video_url,
            audio_url=None,
            video_format=video_format,
            audio_format=None,
            needs_merge=False,
            resolution=resolution,
        )

        # 记录使用日志到本地数据库
        db.log_usage(
            video_url=request_data.youtube_url,
            video_title=video_info.get("title", "Unknown"),
            resolution=resolution,
            file_size=file_size,
            user_id=user_id,
            ip_address=client_ip
        )

        return ExtractURLResponse(
            success=True,
            video_info=extracted_video_info,
            download_urls=download_urls,
            all_formats=[video_format],
            extraction_time=extraction_time,
            client_ip=client_ip,
            detected_country=country_code,
            agentgo_region=region,
            auth_method="subprocess",
        )

    except subprocess.TimeoutExpired:
        logger.error(f"[{task_id}] Download timed out")
        return ExtractURLResponse(
            success=False,
            error_message="Download timed out. Please try again with a shorter video.",
            extraction_time=time.time() - start_time,
            client_ip=client_ip,
            detected_country=country_code,
            agentgo_region=region,
        )
    except Exception as e:
        logger.error(f"[{task_id}] Download failed: {e}")
        return ExtractURLResponse(
            success=False,
            error_message=str(e),
            extraction_time=time.time() - start_time,
            client_ip=client_ip,
            detected_country=country_code,
            agentgo_region=region,
        )
    finally:
        # Cleanup temp files
        try:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
                logger.info(f"[{task_id}] Cleaned up temp directory")
        except Exception as e:
            logger.warning(f"[{task_id}] Failed to cleanup: {e}")


@router.get("/extract/formats")
async def get_available_formats(youtube_url: str):
    """
    Get all available formats for a YouTube video.

    Args:
        youtube_url: YouTube video URL

    Returns:
        List of all available formats with their URLs
    """
    if not youtube_url.startswith(
        ("https://www.youtube.com", "https://youtube.com", "https://youtu.be")
    ):
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")

    try:
        from app.services.url_extractor import extract_youtube_urls

        result = await asyncio.wait_for(
            extract_youtube_urls(url=youtube_url, resolution="best", timeout=120),
            timeout=180,
        )

        return {
            "video_id": result["video_info"]["video_id"],
            "title": result["video_info"]["title"],
            "formats": result.get("all_formats", []),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract/agentgo")
async def extract_via_agentgo(request_data: ExtractURLRequest, request: Request):
    """
    Extract direct download URLs using AgentGo browser directly.

    This method performs the entire extraction through AgentGo's cloud browser,
    meaning all YouTube access happens via AgentGo's proxy IP, not the server IP.

    Benefits:
    - Server IP is never exposed to YouTube
    - Authentication tokens and video URLs are obtained from same IP
    - Better success rate for geo-restricted content

    Args:
        request_data: YouTube URL and preferred resolution
        request: FastAPI request object for IP detection

    Returns:
        Direct download URLs and video metadata
    """
    start_time = time.time()

    # Validate URL
    if not request_data.youtube_url.startswith(
        ("https://www.youtube.com", "https://youtube.com", "https://youtu.be")
    ):
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")

    try:
        from app.services.agentgo_service import get_agentgo_service

        # Get region based on user's IP
        region, country_code, client_ip = await get_region_for_request(request)
        logger.info(
            f"AgentGo direct extraction for: {request_data.youtube_url[:50]}... "
            f"(IP: {client_ip}, Country: {country_code}, Region: {region})"
        )

        agentgo_service = get_agentgo_service()

        if not agentgo_service.is_api_configured():
            return {
                "success": False,
                "error_message": "AgentGo not configured. Set AGENTGO_API_KEY environment variable.",
                "extraction_time": time.time() - start_time,
                "client_ip": client_ip,
                "detected_country": country_code,
                "agentgo_region": region,
            }

        # Extract URLs directly via AgentGo browser
        result = await asyncio.wait_for(
            agentgo_service.extract_video_urls_directly(
                video_url=request_data.youtube_url,
                region=region,
                resolution=request_data.resolution.value,
                timeout=120,
            ),
            timeout=180,
        )

        if not result:
            return {
                "success": False,
                "error_message": "Failed to extract video URLs via AgentGo",
                "extraction_time": time.time() - start_time,
                "client_ip": client_ip,
                "detected_country": country_code,
                "agentgo_region": region,
                "method": "agentgo_direct",
            }

        extraction_time = time.time() - start_time

        return {
            "success": True,
            "video_info": result.get("video_info", {}),
            "download_urls": {
                "video_url": result.get("video_url"),
                "audio_url": result.get("audio_url"),
                "video_format": result.get("video_format"),
                "audio_format": result.get("audio_format"),
                "needs_merge": result.get("needs_merge", False),
            },
            "extraction_time": extraction_time,
            "client_ip": client_ip,
            "detected_country": country_code,
            "agentgo_region": region,
            "method": "agentgo_direct",
            "message": "URLs extracted directly via AgentGo browser. Server IP was not exposed to YouTube.",
        }

    except asyncio.TimeoutError:
        logger.error(f"AgentGo extraction timed out for: {request_data.youtube_url}")
        return {
            "success": False,
            "error_message": "Extraction timed out. AgentGo browser session took too long.",
            "extraction_time": time.time() - start_time,
            "method": "agentgo_direct",
        }
    except Exception as e:
        logger.error(f"AgentGo extraction failed: {e}")
        return {
            "success": False,
            "error_message": str(e),
            "extraction_time": time.time() - start_time,
            "method": "agentgo_direct",
        }


# ============================================================================
# Proxy Download Endpoint
# ============================================================================


@router.get("/proxy-download")
async def proxy_download(url: str, filename: str = "video.mp4"):
    """
    Proxy download for Google Video URLs.

    This endpoint streams the video from Google servers and sets proper
    Content-Disposition headers to force browser download instead of playback.

    Args:
        url: The direct Google Video URL
        filename: Desired filename for download
    """
    import httpx
    from fastapi.responses import StreamingResponse

    # Validate that it's a googlevideo.com URL for security
    if "googlevideo.com" not in url:
        raise HTTPException(
            status_code=400, detail="Only googlevideo.com URLs are allowed"
        )

    try:
        # Stream the video from Google servers
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to fetch video: {response.status_code}",
                    )

                # Get content type and length from original response
                content_type = response.headers.get("content-type", "video/mp4")
                content_length = response.headers.get("content-length")

                # Create headers that force download
                headers = {
                    "Content-Disposition": f'attachment; filename="{filename}"',
                    "Content-Type": content_type,
                }

                if content_length:
                    headers["Content-Length"] = content_length

                # Stream the response
                async def stream_generator():
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        yield chunk

                return StreamingResponse(
                    stream_generator(), headers=headers, media_type=content_type
                )

    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Download timed out")
    except Exception as e:
        logger.error(f"Proxy download failed: {e}")
        raise HTTPException(status_code=500, detail=f"Download failed: {str(e)}")


@router.post("/extract/direct")
async def extract_direct_urls_only(request_data: ExtractURLRequest, request: Request):
    """
    Extract direct YouTube download URLs without downloading to server.
    
    This is a lightweight endpoint that only extracts URLs - 
    no server-side download, no OSS upload.
    The user downloads directly from YouTube CDN.
    """
    start_time = time.time()

    # Validate URL
    if not request_data.youtube_url.startswith(
        ("https://www.youtube.com", "https://youtube.com", "https://youtu.be")
    ):
        raise HTTPException(status_code=400, detail="Invalid YouTube URL")

    try:
        from app.services.url_extractor import extract_youtube_urls

        # Get region based on user's IP
        region, country_code, client_ip = await get_region_for_request(request)
        
        resolution = request_data.resolution.value
        logger.info(
            f"Direct URL extraction: {request_data.youtube_url[:50]}... "
            f"(IP: {client_ip}, Resolution: {resolution})"
        )

        # Extract URLs directly via yt-dlp with AgentGo authentication
        result = await asyncio.wait_for(
            extract_youtube_urls(
                url=request_data.youtube_url,
                resolution=resolution,
                region=region,  # Pass region to use AgentGo auth
                timeout=120,
            ),
            timeout=180,
        )

        extraction_time = time.time() - start_time
        
        if not result:
            return {
                "success": False,
                "error_message": "Failed to extract video URLs",
                "extraction_time": extraction_time,
            }

        video_info = result.get("video_info", {})
        download_urls = result.get("download_urls", {})
        
        return ExtractURLResponse(
            success=True,
            video_info=ExtractedVideoInfo(
                video_id=video_info.get("video_id", ""),
                title=video_info.get("title", "Unknown"),
                duration=video_info.get("duration", 0),
                thumbnail=video_info.get("thumbnail"),
                description=video_info.get("description"),
                uploader=video_info.get("uploader"),
                uploader_id=video_info.get("uploader_id"),
                view_count=video_info.get("view_count"),
                like_count=video_info.get("like_count"),
                upload_date=video_info.get("upload_date"),
                format_count=len(result.get("all_formats", [])),
            ),
            download_urls=DownloadURLs(
                video_url=download_urls.get("video_url"),
                audio_url=download_urls.get("audio_url"),
                video_format=download_urls.get("video_format"),
                audio_format=download_urls.get("audio_format"),
                needs_merge=download_urls.get("needs_merge", False),
                resolution=resolution,
            ),
            all_formats=result.get("all_formats"),
            error_message=None,
            extraction_time=extraction_time,
            client_ip=client_ip,
            detected_country=country_code,
            agentgo_region=region,
            auth_method="direct_ytdlp",
        )

    except asyncio.TimeoutError:
        return {
            "success": False,
            "error_message": "Extraction timed out",
            "extraction_time": time.time() - start_time,
        }
    except Exception as e:
        logger.error(f"Direct extraction error: {e}")
        return {
            "success": False,
            "error_message": str(e),
            "extraction_time": time.time() - start_time,
        }
