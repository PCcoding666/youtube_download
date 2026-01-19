"""
API routes for video processing.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Response, Request
from typing import Dict, Any, Optional
import asyncio
import logging
import json
import time
import urllib.parse
from typing import Dict, Any, Optional
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
    VideoFormatInfo
)
from app.config import settings
from app.services.downloader import YouTubeDownloader, DownloadError, get_proxy_rotator
from app.services.transcriber import ParaformerTranscriber
from app.services.storage import OSSStorage, get_storage
from app.utils.ffmpeg_tools import extract_audio, check_ffmpeg_installed

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
    if not getattr(settings, 'enable_geo_routing', True):
        logger.debug("Geo-routing disabled, using default region")
        return getattr(settings, 'agentgo_region', 'us'), None, client_ip
    
    try:
        from app.services.geo_service import get_region_for_ip
        region, country_code = await get_region_for_ip(client_ip)
        logger.info(f"Geo-routing: IP {client_ip} -> Country {country_code} -> Region {region}")
        return region, country_code, client_ip
    except Exception as e:
        logger.warning(f"Geo-routing failed for IP {client_ip}: {e}")
        return getattr(settings, 'agentgo_region', 'us'), None, client_ip


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
        downloader = YouTubeDownloader(
            resolution=task.resolution,
            region=task.region
        )
        
        # Pre-fetch authentication bundle for the region if available
        if task.region:
            try:
                logger.info(f"[{task_id}] Pre-fetching authentication bundle for region: {task.region}")
                # Add timeout for authentication bundle fetching
                await asyncio.wait_for(
                    downloader.prefetch_authentication_for_region(),
                    timeout=90  # 90 seconds timeout for authentication
                )
                logger.info(f"[{task_id}] Authentication bundle pre-fetch completed")
            except asyncio.TimeoutError:
                logger.warning(f"[{task_id}] Authentication bundle pre-fetch timed out after 90s, continuing with fallback")
                # Continue with download - fallback mechanisms will handle this
            except Exception as e:
                logger.warning(f"[{task_id}] Failed to prefetch authentication bundle: {e}")
                # Fallback to legacy cookie prefetching for backward compatibility
                try:
                    logger.info(f"[{task_id}] Attempting legacy cookie prefetch as fallback")
                    await asyncio.wait_for(
                        downloader.prefetch_cookies_for_region(),
                        timeout=60  # 60 seconds timeout for legacy cookies
                    )
                    logger.info(f"[{task_id}] Legacy cookie prefetch completed")
                except asyncio.TimeoutError:
                    logger.warning(f"[{task_id}] Legacy cookie prefetch timed out after 60s")
                except Exception as e2:
                    logger.warning(f"[{task_id}] Failed to prefetch cookies: {e2}")
                    # Continue anyway - direct download may still work
        
        # Use enhanced download with timeout handling
        try:
            video_path, video_info = await asyncio.wait_for(
                downloader.download(task.youtube_url, str(temp_dir)),
                timeout=600  # 10 minutes timeout for download
            )
        except asyncio.TimeoutError:
            logger.error(f"[{task_id}] Download timed out after 10 minutes")
            raise DownloadError("Download operation timed out after 10 minutes")
        except Exception as e:
            # Enhanced error handling for token extraction failures
            error_msg = str(e).lower()
            if any(keyword in error_msg for keyword in ['token', 'authentication', 'po_token', 'visitor_data']):
                logger.error(f"[{task_id}] Token extraction related error: {e}")
                raise DownloadError(f"Authentication token extraction failed: {str(e)}")
            else:
                # Re-raise original exception for other types of errors
                raise
        
        task.video_path = video_path
        task.video_title = video_info.get('title', 'Unknown')
        task.video_duration = video_info.get('duration', 0)
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
                logger.info(f"[{task_id}] Transcription complete: {len(segments)} segments")
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
        elif any(keyword in error_msg.lower() for keyword in ['token', 'authentication', 'po_token', 'visitor_data']):
            task.error_message = f"Authentication failed: {error_msg}"
        elif any(keyword in error_msg.lower() for keyword in ['403', 'blocked', 'bot', 'captcha']):
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
    request_data: ProcessRequest,
    request: Request,
    background_tasks: BackgroundTasks
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
    if not request_data.youtube_url.startswith(("https://www.youtube.com", "https://youtube.com", "https://youtu.be")):
        raise HTTPException(
            status_code=400, 
            detail="Invalid YouTube URL"
        )
    
    # Get region for this request based on client IP
    region, country_code, client_ip = await get_region_for_request(request)
    
    # Create task with geo-routing info
    task = TaskData(
        youtube_url=request_data.youtube_url,
        enable_transcription=request_data.enable_transcription,
        resolution=request_data.resolution.value,
        user_ip=client_ip,
        country_code=country_code,
        region=region
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
        message=f"Task submitted successfully. Region: {region}. Use /status/{{task_id}} to check progress."
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
        updated_at=task.updated_at
    )


@router.get("/result/{task_id}", response_model=TaskResultResponse)
async def get_result(task_id: str):
    """Get processing result for a completed task."""
    task = get_task(task_id)
    
    transcript_segments = None
    if task.transcript:
        transcript_segments = [
            TranscriptSegment(
                text=seg.get('text', ''),
                start_time=seg.get('start_time', 0),
                end_time=seg.get('end_time', 0),
                speaker_id=seg.get('speaker_id')
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
        completed_at=task.completed_at
    )


@router.get("/download/{task_id}/subtitle")
async def download_subtitle(task_id: str):
    """Download SRT subtitle file for a task."""
    task = get_task(task_id)
    
    if not task.transcript:
        raise HTTPException(
            status_code=404, 
            detail="No transcript available for this task"
        )
    
    transcriber = ParaformerTranscriber()
    srt_content = transcriber.generate_srt(task.transcript)
    
    # Clean filename
    filename = task.video_title or task_id
    filename = "".join(c for c in filename if c.isalnum() or c in (' ', '-', '_'))[:50]
    
    return Response(
        content=srt_content,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}.srt"'
        }
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
                "created_at": t.created_at
            }
            for t in tasks.values()
        ]
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
    return HealthResponse(
        status="healthy",
        version="1.0.0"
    )


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
            "enabled": getattr(settings, 'enable_geo_routing', True),
            "client_ip": client_ip,
            "detected_country": country_code,
            "selected_region": region,
            "supported_regions": ['us', 'uk', 'de', 'fr', 'jp', 'sg', 'in', 'au', 'ca']
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
                auth_bundle = await service.get_youtube_authentication_bundle(region=region)
                if auth_bundle:
                    auth_bundle_info[region] = {
                        "cookie_file": cookie_file,
                        "has_tokens": auth_bundle.has_tokens(),
                        "po_token_available": bool(auth_bundle.po_token),
                        "visitor_data_available": bool(auth_bundle.visitor_data),
                        "extraction_timestamp": auth_bundle.extraction_timestamp.isoformat(),
                        "is_expired": auth_bundle.is_expired()
                    }
                else:
                    auth_bundle_info[region] = {
                        "cookie_file": cookie_file,
                        "has_tokens": False,
                        "po_token_available": False,
                        "visitor_data_available": False,
                        "extraction_timestamp": None,
                        "is_expired": True
                    }
            except Exception as e:
                auth_bundle_info[region] = {
                    "cookie_file": cookie_file,
                    "error": str(e)
                }
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
            "failed_proxies": list(proxy_rotator.failed_proxies)
        },
        "geo_routing": geo_info,
        "cached_cookies_regions": list(cached_regions.keys()),
        "authentication_bundles": auth_bundle_info,
        "temp_dir": settings.temp_dir
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
        "geo_routing_enabled": getattr(settings, 'enable_geo_routing', True),
        "supported_regions": ['us', 'uk', 'de', 'fr', 'jp', 'sg', 'in', 'au', 'ca']
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
            "supported_regions": ['us', 'uk', 'de', 'fr', 'jp', 'sg', 'in', 'au', 'ca']
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
                auth_bundle = await service.get_youtube_authentication_bundle(region=region)
                if auth_bundle:
                    auth_bundle_details[region] = {
                        "cookie_file": cookie_file,
                        "has_tokens": auth_bundle.has_tokens(),
                        "po_token_available": bool(auth_bundle.po_token),
                        "visitor_data_available": bool(auth_bundle.visitor_data),
                        "extraction_timestamp": auth_bundle.extraction_timestamp.isoformat(),
                        "is_expired": auth_bundle.is_expired(),
                        "age_seconds": (datetime.now() - auth_bundle.extraction_timestamp).total_seconds()
                    }
                else:
                    auth_bundle_details[region] = {
                        "cookie_file": cookie_file,
                        "error": "Failed to load authentication bundle"
                    }
            except Exception as e:
                auth_bundle_details[region] = {
                    "cookie_file": cookie_file,
                    "error": str(e)
                }
        
        return {
            "cached_regions": list(cached.keys()),
            "total_cached": len(cached),
            "supported_regions": service.SUPPORTED_REGIONS,
            "authentication_bundles": auth_bundle_details
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
    supported_regions = ['us', 'uk', 'de', 'fr', 'jp', 'sg', 'in', 'au', 'ca']
    
    if region not in supported_regions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid region. Supported: {', '.join(supported_regions)}"
        )
    
    try:
        from app.services.agentgo_service import get_agentgo_service
        service = get_agentgo_service()
        
        if not service.is_configured():
            return {
                "success": False,
                "region": region,
                "message": "AgentGo not configured. Set AGENTGO_API_KEY, YOUTUBE_EMAIL, YOUTUBE_PASSWORD."
            }
        
        start_time = time.time()
        
        # Test authentication bundle extraction with timeout
        try:
            auth_bundle = await asyncio.wait_for(
                service.get_youtube_authentication_bundle(region=region, force_refresh=True),
                timeout=180  # 3 minutes timeout for testing
            )
        except asyncio.TimeoutError:
            return {
                "success": False,
                "region": region,
                "duration": time.time() - start_time,
                "message": "Authentication bundle extraction timed out after 3 minutes"
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
                    "po_token_length": len(auth_bundle.po_token) if auth_bundle.po_token else 0,
                    "visitor_data_available": bool(auth_bundle.visitor_data),
                    "visitor_data_length": len(auth_bundle.visitor_data) if auth_bundle.visitor_data else 0,
                    "cookie_file_path": auth_bundle.cookie_file_path,
                    "extraction_timestamp": auth_bundle.extraction_timestamp.isoformat()
                },
                "message": "Authentication bundle extraction successful"
            }
        else:
            return {
                "success": False,
                "region": region,
                "duration": duration,
                "message": "Failed to extract authentication bundle"
            }
            
    except Exception as e:
        logger.error(f"Error testing authentication bundle for region {region}: {e}")
        return {
            "success": False,
            "region": region,
            "error": str(e),
            "message": "Authentication bundle test failed with exception"
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
    supported_regions = ['us', 'uk', 'de', 'fr', 'jp', 'sg', 'in', 'au', 'ca']
    
    if region not in supported_regions:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid region. Supported: {', '.join(supported_regions)}"
        )
    
    try:
        from app.services.agentgo_service import get_agentgo_service
        service = get_agentgo_service()
        
        if not service.is_configured():
            return {
                "success": False,
                "message": "AgentGo not configured. Set AGENTGO_API_KEY, YOUTUBE_EMAIL, YOUTUBE_PASSWORD."
            }
        
        # Use enhanced authentication bundle fetching with timeout
        try:
            auth_bundle = await asyncio.wait_for(
                service.get_youtube_authentication_bundle(region=region, force_refresh=True),
                timeout=120  # 2 minutes timeout
            )
        except asyncio.TimeoutError:
            return {
                "success": False,
                "region": region,
                "message": "Authentication bundle fetch timed out after 2 minutes"
            }
        
        if auth_bundle:
            return {
                "success": True,
                "region": region,
                "cookie_file": auth_bundle.cookie_file_path,
                "has_tokens": auth_bundle.has_tokens(),
                "po_token_available": bool(auth_bundle.po_token),
                "visitor_data_available": bool(auth_bundle.visitor_data),
                "message": f"Authentication bundle for region {region} cached successfully"
            }
        else:
            return {
                "success": False,
                "region": region,
                "message": "Failed to fetch authentication bundle"
            }
    except Exception as e:
        logger.error(f"Error prefetching authentication bundle for region {region}: {e}")
        return {"success": False, "region": region, "error": str(e)}


# ============================================================================
# Direct URL Extraction API (no server-side download)
# ============================================================================

@router.post("/extract", response_model=ExtractURLResponse)
async def extract_direct_urls(request_data: ExtractURLRequest, request: Request):
    """
    Extract direct download URLs from YouTube video.
    
    Workflow:
    1. Detect user's region based on IP address
    2. Fetch authentication bundle from AgentGo for that region
    3. Use authentication to extract YouTube direct URLs via yt-dlp
    4. Return googlevideo.com direct links to frontend
    
    Args:
        request_data: YouTube URL and preferred resolution
        request: FastAPI request object for IP detection
        
    Returns:
        Direct download URLs and video metadata
    """
    start_time = time.time()
    
    # Validate URL
    if not request_data.youtube_url.startswith(("https://www.youtube.com", "https://youtube.com", "https://youtu.be")):
        raise HTTPException(
            status_code=400, 
            detail="Invalid YouTube URL"
        )
    
    try:
        from app.services.url_extractor import extract_youtube_urls
        from app.services.agentgo_service import get_agentgo_service
        
        # Step 1: Get region based on user's IP
        region, country_code, client_ip = await get_region_for_request(request)
        logger.info(
            f"Extracting direct URLs for: {request_data.youtube_url[:50]}... "
            f"(IP: {client_ip}, Country: {country_code}, Region: {region})"
        )
        
        # Step 2: Get authentication bundle from AgentGo for this region
        auth_bundle = None
        agentgo_service = get_agentgo_service()
        
        if agentgo_service.is_configured():
            try:
                logger.info(f"Fetching AgentGo authentication bundle for region: {region}")
                auth_bundle = await asyncio.wait_for(
                    agentgo_service.get_youtube_authentication_bundle(
                        region=region,
                        video_url=request_data.youtube_url
                    ),
                    timeout=90  # 90 seconds for auth bundle
                )
                if auth_bundle:
                    logger.info(
                        f"Got authentication bundle: cookies={len(auth_bundle.cookies) if auth_bundle.cookies else 0}, "
                        f"po_token={'yes' if auth_bundle.po_token else 'no'}, "
                        f"visitor_data={'yes' if auth_bundle.visitor_data else 'no'}"
                    )
                else:
                    logger.warning(f"Failed to get authentication bundle for region {region}")
            except asyncio.TimeoutError:
                logger.warning(f"AgentGo authentication timed out for region {region}")
            except Exception as e:
                logger.warning(f"AgentGo authentication failed for region {region}: {e}")
        else:
            logger.info("AgentGo not configured, proceeding without authentication")
        
        # Step 3: Extract URLs using authentication
        result = await asyncio.wait_for(
            extract_youtube_urls(
                url=request_data.youtube_url,
                resolution=request_data.resolution.value,
                region=region,
                auth_bundle=auth_bundle,
                timeout=120
            ),
            timeout=180  # Overall timeout
        )
        
        extraction_time = time.time() - start_time
        
        # Build response
        video_info = ExtractedVideoInfo(
            video_id=result['video_info']['video_id'],
            title=result['video_info']['title'],
            duration=result['video_info']['duration'],
            thumbnail=result['video_info'].get('thumbnail'),
            description=result['video_info'].get('description'),
            uploader=result['video_info'].get('uploader'),
            uploader_id=result['video_info'].get('uploader_id'),
            view_count=result['video_info'].get('view_count'),
            like_count=result['video_info'].get('like_count'),
            upload_date=result['video_info'].get('upload_date'),
            format_count=result['video_info']['format_count']
        )
        
        # Build download URLs
        urls = result['download_urls']
        video_format = None
        audio_format = None
        
        if urls.get('video_format'):
            vf = urls['video_format']
            video_format = VideoFormatInfo(
                format_id=vf['format_id'],
                url=vf['url'],
                ext=vf['ext'],
                resolution=vf.get('resolution'),
                height=vf.get('height'),
                width=vf.get('width'),
                fps=vf.get('fps'),
                vcodec=vf.get('vcodec'),
                acodec=vf.get('acodec'),
                filesize=vf.get('filesize'),
                tbr=vf.get('tbr'),
                format_note=vf.get('format_note'),
                is_video=vf.get('is_video', False),
                is_audio=vf.get('is_audio', False),
                is_video_only=vf.get('is_video_only', False),
                is_audio_only=vf.get('is_audio_only', False),
                has_both=vf.get('has_both', False),
                protocol=vf.get('protocol'),
                is_direct_download=vf.get('is_direct_download', False)
            )
        
        if urls.get('audio_format'):
            af = urls['audio_format']
            audio_format = VideoFormatInfo(
                format_id=af['format_id'],
                url=af['url'],
                ext=af['ext'],
                resolution=af.get('resolution'),
                height=af.get('height'),
                width=af.get('width'),
                fps=af.get('fps'),
                vcodec=af.get('vcodec'),
                acodec=af.get('acodec'),
                filesize=af.get('filesize'),
                tbr=af.get('tbr'),
                format_note=af.get('format_note'),
                is_video=af.get('is_video', False),
                is_audio=af.get('is_audio', False),
                is_video_only=af.get('is_video_only', False),
                is_audio_only=af.get('is_audio_only', False),
                has_both=af.get('has_both', False),
                protocol=af.get('protocol'),
                is_direct_download=af.get('is_direct_download', False)
            )
        
        download_urls = DownloadURLs(
            video_url=urls.get('video_url'),
            audio_url=urls.get('audio_url'),
            video_format=video_format,
            audio_format=audio_format,
            needs_merge=urls.get('needs_merge', False),
            resolution=urls.get('resolution', request_data.resolution.value)
        )
        
        # Build all formats list
        all_formats = []
        for fmt in result.get('all_formats', []):
            all_formats.append(VideoFormatInfo(
                format_id=fmt['format_id'],
                url=fmt['url'],
                ext=fmt['ext'],
                resolution=fmt.get('resolution'),
                height=fmt.get('height'),
                width=fmt.get('width'),
                fps=fmt.get('fps'),
                vcodec=fmt.get('vcodec'),
                acodec=fmt.get('acodec'),
                filesize=fmt.get('filesize'),
                tbr=fmt.get('tbr'),
                format_note=fmt.get('format_note'),
                is_video=fmt.get('is_video', False),
                is_audio=fmt.get('is_audio', False),
                is_video_only=fmt.get('is_video_only', False),
                is_audio_only=fmt.get('is_audio_only', False),
                has_both=fmt.get('has_both', False),
                protocol=fmt.get('protocol'),
                is_direct_download=fmt.get('is_direct_download', False)
            ))
        
        logger.info(f"URL extraction successful in {extraction_time:.2f}s: {video_info.title}")
        
        # Determine auth method used
        auth_method = "none"
        if auth_bundle:
            if auth_bundle.po_token or auth_bundle.visitor_data:
                auth_method = "agentgo_tokens"
            elif auth_bundle.cookies:
                auth_method = "agentgo_cookies"
        
        return ExtractURLResponse(
            success=True,
            video_info=video_info,
            download_urls=download_urls,
            all_formats=all_formats,
            extraction_time=extraction_time,
            client_ip=client_ip,
            detected_country=country_code,
            agentgo_region=region,
            auth_method=auth_method
        )
        
    except asyncio.TimeoutError:
        logger.error(f"URL extraction timed out for: {request_data.youtube_url}")
        return ExtractURLResponse(
            success=False,
            error_message="Extraction timed out. Please try again.",
            extraction_time=time.time() - start_time,
            client_ip=client_ip if 'client_ip' in dir() else None,
            detected_country=country_code if 'country_code' in dir() else None,
            agentgo_region=region if 'region' in dir() else None
        )
    except Exception as e:
        logger.error(f"URL extraction failed: {e}")
        return ExtractURLResponse(
            success=False,
            error_message=str(e),
            extraction_time=time.time() - start_time,
            client_ip=client_ip if 'client_ip' in dir() else None,
            detected_country=country_code if 'country_code' in dir() else None,
            agentgo_region=region if 'region' in dir() else None
        )


@router.get("/extract/formats")
async def get_available_formats(youtube_url: str):
    """
    Get all available formats for a YouTube video.
    
    Args:
        youtube_url: YouTube video URL
        
    Returns:
        List of all available formats with their URLs
    """
    if not youtube_url.startswith(("https://www.youtube.com", "https://youtube.com", "https://youtu.be")):
        raise HTTPException(
            status_code=400, 
            detail="Invalid YouTube URL"
        )
    
    try:
        from app.services.url_extractor import extract_youtube_urls
        
        result = await asyncio.wait_for(
            extract_youtube_urls(url=youtube_url, resolution="best", timeout=120),
            timeout=180
        )
        
        return {
            "video_id": result['video_info']['video_id'],
            "title": result['video_info']['title'],
            "formats": result.get('all_formats', [])
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
    if not request_data.youtube_url.startswith(("https://www.youtube.com", "https://youtube.com", "https://youtu.be")):
        raise HTTPException(
            status_code=400, 
            detail="Invalid YouTube URL"
        )
    
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
                "agentgo_region": region
            }
        
        # Extract URLs directly via AgentGo browser
        result = await asyncio.wait_for(
            agentgo_service.extract_video_urls_directly(
                video_url=request_data.youtube_url,
                region=region,
                resolution=request_data.resolution.value,
                timeout=120
            ),
            timeout=180
        )
        
        if not result:
            return {
                "success": False,
                "error_message": "Failed to extract video URLs via AgentGo",
                "extraction_time": time.time() - start_time,
                "client_ip": client_ip,
                "detected_country": country_code,
                "agentgo_region": region,
                "method": "agentgo_direct"
            }
        
        extraction_time = time.time() - start_time
        
        return {
            "success": True,
            "video_info": result.get('video_info', {}),
            "download_urls": {
                "video_url": result.get('video_url'),
                "audio_url": result.get('audio_url'),
                "video_format": result.get('video_format'),
                "audio_format": result.get('audio_format'),
                "needs_merge": result.get('needs_merge', False)
            },
            "extraction_time": extraction_time,
            "client_ip": client_ip,
            "detected_country": country_code,
            "agentgo_region": region,
            "method": "agentgo_direct",
            "message": "URLs extracted directly via AgentGo browser. Server IP was not exposed to YouTube."
        }
        
    except asyncio.TimeoutError:
        logger.error(f"AgentGo extraction timed out for: {request_data.youtube_url}")
        return {
            "success": False,
            "error_message": "Extraction timed out. AgentGo browser session took too long.",
            "extraction_time": time.time() - start_time,
            "method": "agentgo_direct"
        }
    except Exception as e:
        logger.error(f"AgentGo extraction failed: {e}")
        return {
            "success": False,
            "error_message": str(e),
            "extraction_time": time.time() - start_time,
            "method": "agentgo_direct"
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
    if 'googlevideo.com' not in url:
        raise HTTPException(
            status_code=400,
            detail="Only googlevideo.com URLs are allowed"
        )
    
    try:
        # Stream the video from Google servers
        async with httpx.AsyncClient(timeout=300.0) as client:
            async with client.stream('GET', url) as response:
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Failed to fetch video: {response.status_code}"
                    )
                
                # Get content type and length from original response
                content_type = response.headers.get('content-type', 'video/mp4')
                content_length = response.headers.get('content-length')
                
                # Create headers that force download
                headers = {
                    'Content-Disposition': f'attachment; filename="{filename}"',
                    'Content-Type': content_type,
                }
                
                if content_length:
                    headers['Content-Length'] = content_length
                
                # Stream the response
                async def stream_generator():
                    async for chunk in response.aiter_bytes(chunk_size=8192):
                        yield chunk
                
                return StreamingResponse(
                    stream_generator(),
                    headers=headers,
                    media_type=content_type
                )
                
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Download timed out"
        )
    except Exception as e:
        logger.error(f"Proxy download failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Download failed: {str(e)}"
        )
