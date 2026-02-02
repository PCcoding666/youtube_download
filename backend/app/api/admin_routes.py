"""
管理员 API 路由
提供管理员分析页面所需的统计数据接口
"""

from fastapi import APIRouter, HTTPException, Depends, Header, Query
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta, timezone
import logging

from app.database import get_database, ApiUsageLog, AgentGoUsageLog, ProxyTrafficLog, User, UsageLog
from app.api.auth_routes import get_current_user
from sqlalchemy import func, desc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


# ============================================================================
# 管理员权限验证
# ============================================================================

async def require_admin(current_user: dict = Depends(get_current_user)) -> dict:
    """验证管理员权限"""
    if not current_user.get("is_admin", False):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user


# ============================================================================
# 响应模型
# ============================================================================

class DashboardStats(BaseModel):
    """仪表盘统计数据"""
    # 下载统计
    total_requests_today: int
    total_requests_week: int
    total_requests_month: int
    download_success_rate: float = 0  # 下载成功率
    avg_download_time: float = 0  # 平均下载时间(秒)
    
    # AgentGo 统计
    agentgo_calls_today: int
    agentgo_success_rate: float
    
    # 流量统计（分类）
    total_traffic_bytes: int  # 总下载流量
    download_traffic_bytes: int = 0  # 服务器下载流量（等于总下载流量）
    proxy_traffic_bytes: int = 0  # 代理消耗流量（估算）
    agentgo_traffic_bytes: int = 0  # AgentGo 消耗流量（估算）
    today_traffic_bytes: int = 0  # 今日流量
    
    # 用户统计
    total_users: int
    active_users_today: int
    new_users_today: int
    
    # 其他统计
    total_downloads: int = 0  # 总下载次数
    unique_videos: int = 0  # 不同视频数


class TimeSeriesData(BaseModel):
    """时间序列数据点"""
    timestamp: str
    value: int


class GeoDistribution(BaseModel):
    """地理分布数据"""
    country_code: str
    count: int
    percentage: float


class AgentGoStats(BaseModel):
    """AgentGo 统计"""
    total_calls: int
    successful_calls: int
    failed_calls: int
    success_rate: float
    avg_duration: float
    by_region: Dict[str, int]


class TrafficStats(BaseModel):
    """流量统计"""
    # 总计
    total_bytes: int
    
    # 分类流量
    download_bytes: int = 0  # 实际下载流量（文件大小）
    proxy_bytes: int = 0  # 代理流量（估算：下载流量 * 1.1，因为有协议开销）
    agentgo_bytes: int = 0  # AgentGo 流量（估算：每次调用约 500KB）
    
    # 今日/本周/本月
    today_bytes: int = 0
    week_bytes: int = 0
    month_bytes: int = 0
    
    # 按分辨率/端点统计
    by_resolution: Dict[str, int]
    by_endpoint: Dict[str, int]
    
    # 趋势数据
    daily_trend: List[Dict[str, Any]] = []


class PopularVideo(BaseModel):
    """热门视频"""
    video_title: str
    video_url: str
    download_count: int
    total_bytes: int


class DownloadStats(BaseModel):
    """下载统计"""
    total_downloads: int
    successful_downloads: int
    failed_downloads: int
    success_rate: float
    avg_file_size: int
    avg_download_time: float
    by_resolution: Dict[str, int]
    popular_videos: List[PopularVideo] = []


# ============================================================================
# API 端点
# ============================================================================

@router.get("/dashboard", response_model=DashboardStats)
async def get_dashboard_stats(admin: dict = Depends(require_admin)):
    """获取仪表盘概览数据"""
    db = get_database()
    session = db.get_session()
    
    try:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=7)
        month_start = today_start - timedelta(days=30)
        
        # ============ 下载请求统计 ============
        total_requests_today = session.query(ApiUsageLog).filter(
            ApiUsageLog.created_at >= today_start,
            ApiUsageLog.endpoint.like("%/extract")
        ).count()
        
        total_requests_week = session.query(ApiUsageLog).filter(
            ApiUsageLog.created_at >= week_start,
            ApiUsageLog.endpoint.like("%/extract")
        ).count()
        
        total_requests_month = session.query(ApiUsageLog).filter(
            ApiUsageLog.created_at >= month_start,
            ApiUsageLog.endpoint.like("%/extract")
        ).count()
        
        # 下载成功率 (有文件大小记录的算成功)
        total_downloads = session.query(UsageLog).count()
        successful_downloads = session.query(UsageLog).filter(
            UsageLog.file_size > 0
        ).count()
        download_success_rate = (successful_downloads / total_downloads * 100) if total_downloads > 0 else 0
        
        # 不同视频数
        unique_videos = session.query(UsageLog.video_url).distinct().count()
        
        # ============ AgentGo 统计 ============
        agentgo_today = session.query(AgentGoUsageLog).filter(
            AgentGoUsageLog.created_at >= today_start
        ).all()
        agentgo_all = session.query(AgentGoUsageLog).all()
        
        agentgo_calls_today = len(agentgo_today)
        agentgo_success_count = sum(1 for log in agentgo_today if log.success)
        agentgo_success_rate = (agentgo_success_count / agentgo_calls_today * 100) if agentgo_calls_today > 0 else 0
        
        # AgentGo 平均耗时
        avg_agentgo_duration = 0
        if agentgo_all:
            total_duration = sum(log.duration_seconds or 0 for log in agentgo_all)
            avg_agentgo_duration = total_duration / len(agentgo_all) if agentgo_all else 0
        
        # ============ 流量统计（分类）============
        # 总下载流量
        total_traffic_result = session.query(
            func.coalesce(func.sum(UsageLog.file_size), 0)
        ).scalar()
        total_traffic_bytes = int(total_traffic_result) if total_traffic_result else 0
        
        # 今日下载流量
        today_traffic_result = session.query(
            func.coalesce(func.sum(UsageLog.file_size), 0)
        ).filter(UsageLog.created_at >= today_start).scalar()
        today_traffic_bytes = int(today_traffic_result) if today_traffic_result else 0
        
        # 代理流量估算：下载流量 * 1.1 (协议开销约10%)
        proxy_traffic_bytes = int(total_traffic_bytes * 1.1)
        
        # AgentGo 流量估算：每次调用约 500KB (浏览器页面加载)
        agentgo_traffic_bytes = len(agentgo_all) * 500 * 1024
        
        # ============ 用户统计 ============
        total_users = session.query(User).count()
        
        active_users_today = session.query(ApiUsageLog.user_id).filter(
            ApiUsageLog.created_at >= today_start,
            ApiUsageLog.user_id.isnot(None),
            ApiUsageLog.endpoint.like("%/extract")
        ).distinct().count()
        
        new_users_today = session.query(User).filter(
            User.created_at >= today_start
        ).count()
        
        # 计算真正的总流量 = 下载流量 + 代理开销(10%) + AgentGo流量
        real_total_traffic_bytes = total_traffic_bytes + (proxy_traffic_bytes - total_traffic_bytes) + agentgo_traffic_bytes
        
        return DashboardStats(
            # 下载统计
            total_requests_today=total_requests_today,
            total_requests_week=total_requests_week,
            total_requests_month=total_requests_month,
            download_success_rate=round(download_success_rate, 1),
            avg_download_time=round(avg_agentgo_duration, 1),  # 使用 AgentGo 耗时作为参考
            
            # AgentGo 统计
            agentgo_calls_today=agentgo_calls_today,
            agentgo_success_rate=round(agentgo_success_rate, 1),
            
            # 流量统计
            total_traffic_bytes=real_total_traffic_bytes,  # 修复：使用真正的总流量
            download_traffic_bytes=total_traffic_bytes,
            proxy_traffic_bytes=proxy_traffic_bytes,
            agentgo_traffic_bytes=agentgo_traffic_bytes,
            today_traffic_bytes=today_traffic_bytes,
            
            # 用户统计
            total_users=total_users,
            active_users_today=active_users_today,
            new_users_today=new_users_today,
            
            # 其他
            total_downloads=total_downloads,
            unique_videos=unique_videos
        )
    finally:
        session.close()


@router.get("/stats/traffic")
async def get_traffic_stats(
    days: int = Query(default=7, ge=1, le=90),
    admin: dict = Depends(require_admin)
):
    """获取流量统计 - 分类统计下载、代理、AgentGo 流量"""
    db = get_database()
    session = db.get_session()
    
    try:
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = today_start - timedelta(days=7)
        month_start = today_start - timedelta(days=30)
        start_date = now - timedelta(days=days)
        
        # ============ 下载流量统计 ============
        usage_logs = session.query(UsageLog).filter(
            UsageLog.created_at >= start_date
        ).all()
        
        download_bytes = sum(log.file_size or 0 for log in usage_logs)
        
        # 今日/本周/本月流量 (使用 replace(tzinfo=None) 来处理 timezone 比较问题)
        today_bytes = sum(
            log.file_size or 0 for log in usage_logs 
            if log.created_at and log.created_at.replace(tzinfo=None) >= today_start.replace(tzinfo=None)
        )
        week_bytes = sum(
            log.file_size or 0 for log in usage_logs 
            if log.created_at and log.created_at.replace(tzinfo=None) >= week_start.replace(tzinfo=None)
        )
        month_bytes = sum(
            log.file_size or 0 for log in usage_logs 
            if log.created_at and log.created_at.replace(tzinfo=None) >= month_start.replace(tzinfo=None)
        )
        
        # 代理流量估算：下载流量 * 1.1 (协议开销约10%)
        proxy_bytes = int(download_bytes * 1.1)
        
        # AgentGo 流量估算：每次调用约 500KB
        agentgo_logs = session.query(AgentGoUsageLog).filter(
            AgentGoUsageLog.created_at >= start_date
        ).count()
        agentgo_bytes = agentgo_logs * 500 * 1024
        
        # 总流量 = 下载 + 代理开销 + AgentGo
        total_bytes = download_bytes + (proxy_bytes - download_bytes) + agentgo_bytes
        
        # 按分辨率统计
        by_resolution = {}
        for log in usage_logs:
            res = log.resolution or "unknown"
            by_resolution[res] = by_resolution.get(res, 0) + (log.file_size or 0)
        
        # 按端点统计
        by_endpoint = {
            "download": download_bytes,
            "proxy_overhead": proxy_bytes - download_bytes,
            "agentgo": agentgo_bytes
        }
        
        # 每日趋势（最近7天）
        daily_trend = []
        for i in range(min(days, 7)):
            day_start = (today_start - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            day_start_naive = day_start.replace(tzinfo=None)
            day_end_naive = day_end.replace(tzinfo=None)
            day_bytes = sum(
                log.file_size or 0 for log in usage_logs 
                if log.created_at and day_start_naive <= log.created_at.replace(tzinfo=None) < day_end_naive
            )
            daily_trend.append({
                "date": day_start.strftime("%Y-%m-%d"),
                "download_bytes": day_bytes,
                "proxy_bytes": int(day_bytes * 1.1),
            })
        daily_trend.reverse()  # 从旧到新排序
        
        return {
            "total_bytes": total_bytes,
            "download_bytes": download_bytes,
            "proxy_bytes": proxy_bytes,
            "agentgo_bytes": agentgo_bytes,
            "today_bytes": today_bytes,
            "week_bytes": week_bytes,
            "month_bytes": month_bytes,
            "by_resolution": by_resolution,
            "by_endpoint": by_endpoint,
            "daily_trend": daily_trend,
            "period_days": days
        }
    finally:
        session.close()


@router.get("/stats/agentgo")
async def get_agentgo_stats(
    days: int = Query(default=7, ge=1, le=90),
    admin: dict = Depends(require_admin)
):
    """获取 AgentGo 使用统计"""
    db = get_database()
    session = db.get_session()
    
    try:
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        logs = session.query(AgentGoUsageLog).filter(
            AgentGoUsageLog.created_at >= start_date
        ).all()
        
        total_calls = len(logs)
        successful_calls = sum(1 for log in logs if log.success)
        failed_calls = total_calls - successful_calls
        success_rate = (successful_calls / total_calls * 100) if total_calls > 0 else 0
        
        # 平均耗时
        durations = [log.duration_seconds for log in logs if log.duration_seconds]
        avg_duration = sum(durations) / len(durations) if durations else 0
        
        # 按区域统计
        by_region = {}
        for log in logs:
            region = log.region or "unknown"
            by_region[region] = by_region.get(region, 0) + 1
        
        # 按提取方法统计
        by_method = {}
        for log in logs:
            method = log.extraction_method or "unknown"
            by_method[method] = by_method.get(method, 0) + 1
        
        # 错误统计
        error_counts = {}
        for log in logs:
            if log.error_message:
                error_key = log.error_message[:100]  # 截断错误消息
                error_counts[error_key] = error_counts.get(error_key, 0) + 1
        
        return {
            "total_calls": total_calls,
            "successful_calls": successful_calls,
            "failed_calls": failed_calls,
            "success_rate": round(success_rate, 2),
            "avg_duration": round(avg_duration, 2),
            "by_region": by_region,
            "by_method": by_method,
            "top_errors": dict(sorted(error_counts.items(), key=lambda x: x[1], reverse=True)[:10]),
            "period_days": days
        }
    finally:
        session.close()


@router.get("/stats/downloads")
async def get_download_stats(
    days: int = Query(default=7, ge=1, le=90),
    admin: dict = Depends(require_admin)
):
    """获取下载统计 - 成功率、热门视频等"""
    db = get_database()
    session = db.get_session()
    
    try:
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # 获取所有下载记录
        all_logs = session.query(UsageLog).filter(
            UsageLog.created_at >= start_date
        ).all()
        
        total_downloads = len(all_logs)
        successful_downloads = sum(1 for log in all_logs if log.file_size and log.file_size > 0)
        failed_downloads = total_downloads - successful_downloads
        success_rate = (successful_downloads / total_downloads * 100) if total_downloads > 0 else 0
        
        # 平均文件大小
        file_sizes = [log.file_size for log in all_logs if log.file_size and log.file_size > 0]
        avg_file_size = sum(file_sizes) // len(file_sizes) if file_sizes else 0
        
        # 按分辨率统计下载次数
        by_resolution = {}
        for log in all_logs:
            res = log.resolution or "unknown"
            by_resolution[res] = by_resolution.get(res, 0) + 1
        
        # 热门视频 Top 10
        video_stats = {}
        for log in all_logs:
            if log.video_url:
                if log.video_url not in video_stats:
                    video_stats[log.video_url] = {
                        "video_title": log.video_title or "Unknown",
                        "video_url": log.video_url,
                        "download_count": 0,
                        "total_bytes": 0
                    }
                video_stats[log.video_url]["download_count"] += 1
                video_stats[log.video_url]["total_bytes"] += log.file_size or 0
        
        popular_videos = sorted(
            video_stats.values(), 
            key=lambda x: x["download_count"], 
            reverse=True
        )[:10]
        
        return {
            "total_downloads": total_downloads,
            "successful_downloads": successful_downloads,
            "failed_downloads": failed_downloads,
            "success_rate": round(success_rate, 1),
            "avg_file_size": avg_file_size,
            "by_resolution": by_resolution,
            "popular_videos": popular_videos,
            "period_days": days
        }
    finally:
        session.close()


@router.get("/stats/users")
async def get_user_stats(
    days: int = Query(default=30, ge=1, le=365),
    admin: dict = Depends(require_admin)
):
    """获取用户统计"""
    db = get_database()
    session = db.get_session()
    
    try:
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # 用户总数
        total_users = session.query(User).count()
        premium_users = session.query(User).filter(User.is_premium == True).count()
        admin_users = session.query(User).filter(User.is_admin == True).count()
        
        # 新用户统计
        new_users = session.query(User).filter(
            User.created_at >= start_date
        ).count()
        
        # 每日新增用户趋势
        daily_new_users = []
        for i in range(min(days, 30)):
            day_start = (datetime.now(timezone.utc) - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)
            count = session.query(User).filter(
                User.created_at >= day_start,
                User.created_at < day_end
            ).count()
            daily_new_users.append({
                "date": day_start.strftime("%Y-%m-%d"),
                "count": count
            })
        
        return {
            "total_users": total_users,
            "premium_users": premium_users,
            "admin_users": admin_users,
            "new_users_period": new_users,
            "daily_new_users": list(reversed(daily_new_users)),
            "period_days": days
        }
    finally:
        session.close()


@router.get("/stats/geo")
async def get_geo_stats(
    days: int = Query(default=7, ge=1, le=90),
    admin: dict = Depends(require_admin)
):
    """获取地理分布统计"""
    db = get_database()
    session = db.get_session()
    
    try:
        start_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # 按国家统计
        country_stats = session.query(
            ApiUsageLog.country_code,
            func.count(ApiUsageLog.id).label('count')
        ).filter(
            ApiUsageLog.created_at >= start_date,
            ApiUsageLog.country_code.isnot(None)
        ).group_by(ApiUsageLog.country_code).order_by(desc('count')).limit(20).all()
        
        total_with_country = sum(stat[1] for stat in country_stats)
        
        by_country = [
            {
                "country_code": stat[0] or "unknown",
                "count": stat[1],
                "percentage": round(stat[1] / total_with_country * 100, 2) if total_with_country > 0 else 0
            }
            for stat in country_stats
        ]
        
        # 按城市统计
        city_stats = session.query(
            ApiUsageLog.city,
            func.count(ApiUsageLog.id).label('count')
        ).filter(
            ApiUsageLog.created_at >= start_date,
            ApiUsageLog.city.isnot(None)
        ).group_by(ApiUsageLog.city).order_by(desc('count')).limit(20).all()
        
        by_city = [
            {"city": stat[0] or "unknown", "count": stat[1]}
            for stat in city_stats
        ]
        
        return {
            "by_country": by_country,
            "by_city": by_city,
            "period_days": days
        }
    finally:
        session.close()


@router.get("/stats/timeline")
async def get_timeline_stats(
    hours: int = Query(default=24, ge=1, le=168),
    admin: dict = Depends(require_admin)
):
    """获取时间线统计（按小时）"""
    db = get_database()
    session = db.get_session()
    
    try:
        data = []
        now = datetime.now(timezone.utc)
        
        for i in range(hours):
            hour_start = (now - timedelta(hours=i)).replace(minute=0, second=0, microsecond=0)
            hour_end = hour_start + timedelta(hours=1)
            
            # 下载请求数 - 只统计 /api/extract 端点
            api_count = session.query(ApiUsageLog).filter(
                ApiUsageLog.created_at >= hour_start,
                ApiUsageLog.created_at < hour_end,
                ApiUsageLog.endpoint == "/api/extract"
            ).count()
            
            # AgentGo 调用数
            agentgo_count = session.query(AgentGoUsageLog).filter(
                AgentGoUsageLog.created_at >= hour_start,
                AgentGoUsageLog.created_at < hour_end
            ).count()
            
            data.append({
                "timestamp": hour_start.isoformat(),
                "api_requests": api_count,
                "agentgo_calls": agentgo_count
            })
        
        return {
            "data": list(reversed(data)),
            "period_hours": hours
        }
    finally:
        session.close()


@router.get("/users")
async def get_users_list(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    admin: dict = Depends(require_admin)
):
    """获取用户列表"""
    db = get_database()
    users = db.get_all_users(limit=limit, offset=offset)
    total = db.get_user_count()
    
    return {
        "users": users,
        "total": total,
        "limit": limit,
        "offset": offset
    }


@router.post("/users/{user_id}/toggle-admin")
async def toggle_user_admin(
    user_id: int,
    admin: dict = Depends(require_admin)
):
    """切换用户管理员权限"""
    db = get_database()
    
    # 不能修改自己的权限
    if user_id == admin["id"]:
        raise HTTPException(status_code=400, detail="不能修改自己的管理员权限")
    
    user = db.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    new_admin_status = not user["is_admin"]
    success = db.set_user_admin(user_id, new_admin_status)
    
    if not success:
        raise HTTPException(status_code=500, detail="修改失败")
    
    return {
        "success": True,
        "user_id": user_id,
        "is_admin": new_admin_status,
        "message": f"已{'授予' if new_admin_status else '撤销'}管理员权限"
    }


@router.get("/recent-logs")
async def get_recent_logs(
    log_type: str = Query(default="api", regex="^(api|agentgo|traffic)$"),
    limit: int = Query(default=50, ge=1, le=200),
    admin: dict = Depends(require_admin)
):
    """获取最近日志记录"""
    db = get_database()
    session = db.get_session()
    
    try:
        if log_type == "api":
            logs = session.query(ApiUsageLog).order_by(
                ApiUsageLog.created_at.desc()
            ).limit(limit).all()
            
            return {
                "logs": [
                    {
                        "id": log.id,
                        "endpoint": log.endpoint,
                        "method": log.method,
                        "status_code": log.status_code,
                        "response_time_ms": log.response_time_ms,
                        "ip_address": log.ip_address,
                        "country_code": log.country_code,
                        "user_id": log.user_id,
                        "created_at": log.created_at.isoformat() if log.created_at else None
                    }
                    for log in logs
                ],
                "type": log_type
            }
        
        elif log_type == "agentgo":
            logs = session.query(AgentGoUsageLog).order_by(
                AgentGoUsageLog.created_at.desc()
            ).limit(limit).all()
            
            return {
                "logs": [
                    {
                        "id": log.id,
                        "region": log.region,
                        "video_id": log.video_id,
                        "success": log.success,
                        "duration_seconds": log.duration_seconds,
                        "extraction_method": log.extraction_method,
                        "error_message": log.error_message[:100] if log.error_message else None,
                        "created_at": log.created_at.isoformat() if log.created_at else None
                    }
                    for log in logs
                ],
                "type": log_type
            }
        
        else:  # traffic
            logs = session.query(ProxyTrafficLog).order_by(
                ProxyTrafficLog.created_at.desc()
            ).limit(limit).all()
            
            return {
                "logs": [
                    {
                        "id": log.id,
                        "total_bytes": log.total_bytes,
                        "request_bytes": log.request_bytes,
                        "response_bytes": log.response_bytes,
                        "endpoint": log.endpoint,
                        "video_id": log.video_id,
                        "resolution": log.resolution,
                        "created_at": log.created_at.isoformat() if log.created_at else None
                    }
                    for log in logs
                ],
                "type": log_type
            }
    finally:
        session.close()
