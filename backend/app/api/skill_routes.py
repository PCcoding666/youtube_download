"""
OpenClaw Skill 外部 API 路由
对外暴露的标准化接口，使用 API Key 认证
核心下载逻辑不暴露，仅提供调用入口
"""

from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel, Field
from typing import Optional
import logging
import time
import asyncio
import uuid
import subprocess
import json
from pathlib import Path
import shutil

from app.database import get_database
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/skill", tags=["skill-api"])


# ============================================================================
# 请求/响应模型
# ============================================================================


class SkillDownloadRequest(BaseModel):
    """Skill 下载请求"""
    youtube_url: str = Field(..., description="YouTube 视频 URL")
    resolution: str = Field(default="720", description="视频分辨率: 360, 480, 720, 1080, best")


class SkillDownloadResponse(BaseModel):
    """Skill 下载响应"""
    success: bool
    download_url: Optional[str] = None
    video_title: Optional[str] = None
    video_duration: Optional[int] = None
    file_size: Optional[int] = None
    resolution: Optional[str] = None
    credits_used: int = 0
    credits_remaining: int = 0
    error_message: Optional[str] = None
    processing_time: Optional[float] = None


class SkillBalanceResponse(BaseModel):
    """Skill 余额响应"""
    credit_balance: int
    username: str


# ============================================================================
# API Key 认证依赖
# ============================================================================


async def verify_skill_api_key(authorization: Optional[str] = Header(None)) -> dict:
    """
    验证 API Key 并返回用户信息

    Header 格式: Authorization: Bearer sk-yt-xxxxx
    """
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing API Key. Use: Authorization: Bearer sk-yt-xxxxx")

    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid authorization format. Use: Bearer sk-yt-xxxxx")

    api_key = parts[1]
    db = get_database()
    user = db.verify_api_key(api_key)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid or inactive API Key")

    return user


# ============================================================================
# API 端点
# ============================================================================


@router.get("/health")
async def skill_health():
    """
    健康检查（无需认证）
    """
    return {
        "status": "healthy",
        "service": "YouTube Video Downloader Skill",
        "version": "1.0.0",
        "credit_rate": "1 download = 1 credit, S$1 = 5 credits",
    }


@router.get("/balance", response_model=SkillBalanceResponse)
async def skill_balance(
    authorization: Optional[str] = Header(None),
):
    """
    查询 Credit 余额

    需要 API Key 认证
    """
    user = await verify_skill_api_key(authorization)

    return SkillBalanceResponse(
        credit_balance=user["credit_balance"],
        username=user["username"],
    )


@router.post("/download", response_model=SkillDownloadResponse)
async def skill_download(
    request_data: SkillDownloadRequest,
    request: Request,
    authorization: Optional[str] = Header(None),
):
    """
    下载 YouTube 视频

    需要 API Key 认证，每次成功下载消耗 1 credit
    下载失败不消耗 credit

    认证方式: Authorization: Bearer sk-yt-xxxxx
    """
    start_time = time.time()

    # 认证
    user = await verify_skill_api_key(authorization)
    user_id = user["id"]
    db = get_database()

    # 预扣 credit（防止并发超额）
    deduct_ok, balance = db.deduct_credit(
        user_id=user_id,
        amount=1,
        description="Skill 下载（预扣）",
        video_url=request_data.youtube_url,
    )
    if not deduct_ok:
        return SkillDownloadResponse(
            success=False,
            credits_remaining=balance,
            error_message=f"Credit 余额不足（当前: {balance}）。请在官网充值。S$1 = 5 credits",
        )

    # 验证 URL
    if not request_data.youtube_url.startswith(
        ("https://www.youtube.com", "https://youtube.com", "https://youtu.be")
    ):
        # URL 无效 - 退还 credit
        db.refund_credit(user_id, 1, "URL 无效退还", request_data.youtube_url)
        return SkillDownloadResponse(
            success=False,
            credits_remaining=balance + 1,
            error_message="Invalid YouTube URL",
        )

    task_id = str(uuid.uuid4())[:8]
    temp_dir = Path(settings.temp_dir) / f"skill_{task_id}"

    try:
        temp_dir.mkdir(parents=True, exist_ok=True)

        # 构建下载参数
        resolution = request_data.resolution
        if resolution == "audio":
            format_str = "bestaudio[ext=m4a]/bestaudio"
        elif resolution == "best":
            format_str = (
                "bestvideo[vcodec^=avc1][ext=mp4]+bestaudio[ext=m4a]/"
                "bestvideo[ext=mp4]+bestaudio[ext=m4a]/"
                "bestvideo+bestaudio/best"
            )
        else:
            format_str = (
                f"bestvideo[height<={resolution}][vcodec^=avc1]+bestaudio[ext=m4a]/"
                f"bestvideo[height<={resolution}][ext=mp4]+bestaudio[ext=m4a]/"
                f"bestvideo[height<={resolution}]+bestaudio/"
                f"best[height<={resolution}]"
            )

        # 获取 region (默认 us)
        region = getattr(settings, "agentgo_region", "us")

        # # [DISABLED] AgentGo cookies - temporarily disabled, using PO Token + Proxy only
        # from app.services.agentgo_service import get_agentgo_service
        # agentgo = get_agentgo_service()
        # cookie_file_path = None
        # try:
        #     cookie_file_path = agentgo.get_cached_cookie_file(region)
        #     if not cookie_file_path and agentgo.is_api_configured():
        #         auth_bundle = await asyncio.wait_for(
        #             agentgo.get_youtube_authentication_bundle(region=region),
        #             timeout=120,
        #         )
        #         if auth_bundle and auth_bundle.cookie_file_path:
        #             cookie_file_path = auth_bundle.cookie_file_path
        # except Exception as e:
        #     logger.warning(f"[skill:{task_id}] Cookie 获取失败: {e}")
        cookie_file_path = None

        # Get visitor_data via InnerTube API
        visitor_data = None
        try:
            from app.services.visitor_data_provider import get_visitor_data
            import re as re_vd
            vd_match = re_vd.search(r'[?&]v=([a-zA-Z0-9_-]{11})', request_data.youtube_url)
            vd_video_id = vd_match.group(1) if vd_match else None
            visitor_data = get_visitor_data(video_id=vd_video_id)
            if visitor_data:
                logger.info(f"[skill:{task_id}] ✅ visitor_data via InnerTube (length: {len(visitor_data)})")
        except Exception as e:
            logger.warning(f"[skill:{task_id}] visitor_data fetch error: {e}")

        # Pre-fetch PO Token directly from bgutil
        import os
        from app.services.download_pool import get_bgutil_lb, get_proxy_distributor
        bgutil_lb = get_bgutil_lb()
        po_token = bgutil_lb.fetch_po_token()

        # Build extractor args
        extractor_args_list = []
        if po_token:
            extractor_args_list.extend(["--extractor-args", f"youtube:po_token=web+{po_token}"])
        if visitor_data:
            extractor_args_list.extend(["--extractor-args", f"youtube:visitor_data={visitor_data}"])

        cmd = [
            "yt-dlp",
            "--js-runtimes", "node",
            "--remote-components", "ejs:github",
            *extractor_args_list,
            "-f", format_str,
            "--merge-output-format", "mp4",
            "-o", f"{temp_dir}/%(id)s.%(ext)s",
            "--print-json",
            "--no-simulate",
            request_data.youtube_url,
        ]

        if cookie_file_path and Path(cookie_file_path).exists():
            cmd.insert(1, "--cookies")
            cmd.insert(2, cookie_file_path)

        # Proxy: distributed across regions
        import re
        base_proxy_url = settings.http_proxy or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
        if base_proxy_url:
            proxy_dist = get_proxy_distributor()
            proxy_region = proxy_dist.get_next_region()
            proxy_url = proxy_dist.build_proxy_url(base_proxy_url, proxy_region)
            if proxy_url:
                cmd.insert(1, "--proxy")
                cmd.insert(2, proxy_url)

        # 执行下载
        # Set NO_PROXY to prevent bgutil connections from routing through external proxy
        loop = asyncio.get_running_loop()

        def run_ytdlp():
            env = os.environ.copy()
            env["NO_PROXY"] = "bgutil-1,bgutil-2,bgutil-3,localhost,127.0.0.1"
            env["no_proxy"] = "bgutil-1,bgutil-2,bgutil-3,localhost,127.0.0.1"
            return subprocess.run(cmd, capture_output=True, text=True, timeout=600, env=env)

        result = await loop.run_in_executor(None, run_ytdlp)

        if result.returncode != 0:
            error_msg = result.stderr[-300:] if result.stderr else "Download failed"
            logger.error(f"[skill:{task_id}] yt-dlp 失败: {error_msg}")
            db.refund_credit(user_id, 1, "yt-dlp 下载失败退还", request_data.youtube_url)
            return SkillDownloadResponse(
                success=False,
                credits_used=0,
                credits_remaining=balance + 1,
                error_message=f"Download failed: {error_msg}",
                processing_time=time.time() - start_time,
            )

        # 解析视频信息
        video_info = {}
        try:
            video_info = json.loads(result.stdout.strip().split('\n')[-1])
        except json.JSONDecodeError:
            pass

        # 找到下载的文件
        video_path = None
        for f in temp_dir.iterdir():
            if f.suffix == '.mp4':
                video_path = str(f)
                break

        if not video_path or not Path(video_path).exists():
            db.refund_credit(user_id, 1, "下载文件未找到退还", request_data.youtube_url)
            return SkillDownloadResponse(
                success=False,
                credits_used=0,
                credits_remaining=balance + 1,
                error_message="Downloaded file not found",
                processing_time=time.time() - start_time,
            )

        # 确保 H.264 编码兼容性（VP9/AV1 → H.264，兼容 QuickTime/iOS）
        from app.utils.ffmpeg_tools import ensure_h264_compatible
        video_path = await loop.run_in_executor(
            None, ensure_h264_compatible, video_path, f"skill:{task_id}"
        )

        file_size = Path(video_path).stat().st_size

        # 上传到 OSS
        from app.services.storage import get_storage
        storage = get_storage()

        safe_title = "".join(
            c for c in video_info.get("title", "video")[:50]
            if c.isalnum() or c in (" ", "-", "_")
        ).strip() or "video"

        video_ext = Path(video_path).suffix.lstrip('.') or 'mp4'
        object_key = f"skill/{task_id}/{safe_title}.{video_ext}"
        oss_video_url = await storage.upload_file(video_path, object_key)

        # 下载成功 - credit 已在前面预扣，无需再扣
        new_balance = balance  # balance 已经是扣除后的值

        # 记录使用日志
        db.log_usage(
            video_url=request_data.youtube_url,
            video_title=video_info.get("title", "Unknown"),
            resolution=resolution,
            file_size=file_size,
            user_id=user_id,
        )

        processing_time = time.time() - start_time

        return SkillDownloadResponse(
            success=True,
            download_url=oss_video_url,
            video_title=video_info.get("title"),
            video_duration=video_info.get("duration"),
            file_size=file_size,
            resolution=resolution,
            credits_used=1,
            credits_remaining=new_balance,
            processing_time=processing_time,
        )

    except subprocess.TimeoutExpired:
        db.refund_credit(user_id, 1, "下载超时退还", request_data.youtube_url)
        return SkillDownloadResponse(
            success=False,
            credits_used=0,
            credits_remaining=balance + 1,
            error_message="Download timed out (10 min limit)",
            processing_time=time.time() - start_time,
        )
    except Exception as e:
        logger.error(f"[skill:{task_id}] Error: {e}")
        db.refund_credit(user_id, 1, f"下载失败退还: {str(e)[:100]}", request_data.youtube_url)
        return SkillDownloadResponse(
            success=False,
            credits_used=0,
            credits_remaining=balance + 1,
            error_message=str(e),
            processing_time=time.time() - start_time,
        )
    finally:
        try:
            if temp_dir.exists():
                shutil.rmtree(temp_dir)
        except Exception:
            pass
