"""
API routes for video processing.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Response
from typing import Dict, Any
import asyncio
import logging
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
    HealthResponse
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
        
        logger.info(f"[{task_id}] Downloading video: {task.youtube_url}")
        
        downloader = YouTubeDownloader(resolution=task.resolution)
        video_path, video_info = await downloader.download(
            task.youtube_url, 
            str(temp_dir)
        )
        
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
        logger.error(f"[{task_id}] Download error: {e}")
        task.status = TaskStatus.FAILED
        task.error_message = f"Download failed: {str(e)}"
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
    request: ProcessRequest,
    background_tasks: BackgroundTasks
):
    """
    Submit a YouTube video for processing.
    
    - Downloads the video
    - Extracts audio
    - Uploads to cloud storage
    - Optionally transcribes audio
    """
    # Validate URL
    if not request.youtube_url.startswith(("https://www.youtube.com", "https://youtube.com", "https://youtu.be")):
        raise HTTPException(
            status_code=400, 
            detail="Invalid YouTube URL"
        )
    
    # Create task
    task = TaskData(
        youtube_url=request.youtube_url,
        enable_transcription=request.enable_transcription,
        resolution=request.resolution.value
    )
    
    tasks[task.task_id] = task
    
    # Start background processing
    background_tasks.add_task(process_video_task, task.task_id)
    
    logger.info(f"Task created: {task.task_id} for {request.youtube_url}")
    
    return ProcessResponse(
        task_id=task.task_id,
        status=task.status,
        message="Task submitted successfully. Use /status/{task_id} to check progress."
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
async def system_info():
    """Get system information including proxy pool status."""
    proxy_rotator = get_proxy_rotator()
    
    # Try to get Clash info
    clash_info = None
    try:
        from app.services.clash_api import get_clash_client
        clash_client = get_clash_client()
        if await clash_client.is_available():
            current_node = await clash_client.get_current_node()
            youtube_nodes = await clash_client.get_youtube_preferred_nodes()
            clash_info = {
                "available": True,
                "current_node": current_node,
                "youtube_preferred_nodes_count": len(youtube_nodes),
                "youtube_preferred_nodes": youtube_nodes[:10]  # Limit to first 10
            }
        else:
            clash_info = {"available": False}
    except Exception as e:
        clash_info = {"available": False, "error": str(e)}
    
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
        "clash": clash_info,
        "temp_dir": settings.temp_dir
    }


@router.get("/clash/nodes")
async def get_clash_nodes(filter: str = None):
    """
    Get available Clash proxy nodes.
    
    Args:
        filter: Optional filter keywords (comma-separated)
    """
    try:
        from app.services.clash_api import get_clash_client
        client = get_clash_client()
        
        if not await client.is_available():
            return {"available": False, "message": "Clash API not available"}
        
        filter_keywords = None
        if filter:
            filter_keywords = [k.strip() for k in filter.split(',') if k.strip()]
        
        nodes = await client.get_proxy_names(filter_keywords)
        current = await client.get_current_node()
        
        return {
            "available": True,
            "current_node": current,
            "total_nodes": len(nodes),
            "nodes": nodes
        }
    except Exception as e:
        return {"available": False, "error": str(e)}


@router.post("/clash/switch")
async def switch_clash_node(node_name: str = None, auto: bool = False):
    """
    Switch Clash proxy node.
    
    Args:
        node_name: Specific node name to switch to
        auto: If true, automatically select best YouTube node
    """
    try:
        from app.services.clash_api import get_clash_client, switch_youtube_node
        
        if auto:
            new_node = await switch_youtube_node()
            if new_node:
                return {"success": True, "node": new_node, "mode": "auto"}
            else:
                return {"success": False, "message": "Failed to auto-switch node"}
        
        if not node_name:
            return {"success": False, "message": "Please provide node_name or set auto=true"}
        
        client = get_clash_client()
        success = await client.switch_node('SELECT', node_name)
        
        return {"success": success, "node": node_name, "mode": "manual"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/clash/youtube-nodes")
async def get_youtube_nodes():
    """Get nodes preferred for YouTube download."""
    try:
        from app.services.clash_api import get_youtube_nodes as fetch_youtube_nodes
        nodes = await fetch_youtube_nodes()
        
        return {
            "total": len(nodes),
            "nodes": nodes,
            "preferred_keywords": settings.youtube_preferred_nodes
        }
    except Exception as e:
        return {"error": str(e)}
