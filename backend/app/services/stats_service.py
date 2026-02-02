"""
统计服务
提供管理员分析页面所需的各类聚合统计查询
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy import func, desc, and_

from app.database import (
    get_database, 
    ApiUsageLog, 
    AgentGoUsageLog, 
    ProxyTrafficLog, 
    User,
    UsageLog
)

logger = logging.getLogger(__name__)


class StatsService:
    """统计服务 - 提供各类数据统计"""

    def __init__(self):
        self._db = None

    def _get_db(self):
        if self._db is None:
            self._db = get_database()
        return self._db

    def get_dashboard_overview(self) -> Dict[str, Any]:
        """获取仪表盘概览数据"""
        db = self._get_db()
        session = db.get_session()
        
        try:
            now = datetime.now()
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            week_start = today_start - timedelta(days=7)
            month_start = today_start - timedelta(days=30)
            
            # API 请求统计
            api_today = session.query(ApiUsageLog).filter(
                ApiUsageLog.created_at >= today_start
            ).count()
            
            api_week = session.query(ApiUsageLog).filter(
                ApiUsageLog.created_at >= week_start
            ).count()
            
            api_month = session.query(ApiUsageLog).filter(
                ApiUsageLog.created_at >= month_start
            ).count()
            
            # AgentGo 统计
            agentgo_today = session.query(AgentGoUsageLog).filter(
                AgentGoUsageLog.created_at >= today_start
            ).all()
            
            agentgo_count = len(agentgo_today)
            agentgo_success = sum(1 for log in agentgo_today if log.success)
            agentgo_rate = (agentgo_success / agentgo_count * 100) if agentgo_count > 0 else 0
            
            # 流量统计
            traffic_total = session.query(
                func.coalesce(func.sum(ProxyTrafficLog.total_bytes), 0)
            ).scalar() or 0
            
            traffic_today = session.query(
                func.coalesce(func.sum(ProxyTrafficLog.total_bytes), 0)
            ).filter(ProxyTrafficLog.created_at >= today_start).scalar() or 0
            
            # 用户统计
            total_users = session.query(User).count()
            new_users_today = session.query(User).filter(
                User.created_at >= today_start
            ).count()
            
            # 活跃用户（今日有请求的用户）
            active_users = session.query(ApiUsageLog.user_id).filter(
                ApiUsageLog.created_at >= today_start,
                ApiUsageLog.user_id.isnot(None)
            ).distinct().count()
            
            # 下载统计
            downloads_today = session.query(UsageLog).filter(
                UsageLog.created_at >= today_start
            ).count()
            
            downloads_total = session.query(UsageLog).count()
            
            return {
                "api_requests": {
                    "today": api_today,
                    "week": api_week,
                    "month": api_month
                },
                "agentgo": {
                    "calls_today": agentgo_count,
                    "success_rate": round(agentgo_rate, 2)
                },
                "traffic": {
                    "total_bytes": int(traffic_total),
                    "today_bytes": int(traffic_today),
                    "total_gb": round(int(traffic_total) / (1024**3), 2),
                    "today_gb": round(int(traffic_today) / (1024**3), 2)
                },
                "users": {
                    "total": total_users,
                    "new_today": new_users_today,
                    "active_today": active_users
                },
                "downloads": {
                    "today": downloads_today,
                    "total": downloads_total
                }
            }
        finally:
            session.close()

    def get_traffic_breakdown(self, days: int = 7) -> Dict[str, Any]:
        """获取流量明细"""
        db = self._get_db()
        session = db.get_session()
        
        try:
            start_date = datetime.now() - timedelta(days=days)
            
            logs = session.query(ProxyTrafficLog).filter(
                ProxyTrafficLog.created_at >= start_date
            ).all()
            
            # 按分辨率统计
            by_resolution = {}
            for log in logs:
                res = log.resolution or "unknown"
                by_resolution[res] = by_resolution.get(res, 0) + (log.total_bytes or 0)
            
            # 按日期统计
            daily_traffic = {}
            for log in logs:
                if log.created_at:
                    day = log.created_at.strftime("%Y-%m-%d")
                    daily_traffic[day] = daily_traffic.get(day, 0) + (log.total_bytes or 0)
            
            # 排序
            daily_traffic = dict(sorted(daily_traffic.items()))
            
            total = sum(log.total_bytes or 0 for log in logs)
            
            return {
                "total_bytes": total,
                "total_gb": round(total / (1024**3), 2),
                "by_resolution": by_resolution,
                "daily": [
                    {"date": k, "bytes": v, "gb": round(v / (1024**3), 3)}
                    for k, v in daily_traffic.items()
                ],
                "period_days": days
            }
        finally:
            session.close()

    def get_agentgo_analytics(self, days: int = 7) -> Dict[str, Any]:
        """获取 AgentGo 分析数据"""
        db = self._get_db()
        session = db.get_session()
        
        try:
            start_date = datetime.now() - timedelta(days=days)
            
            logs = session.query(AgentGoUsageLog).filter(
                AgentGoUsageLog.created_at >= start_date
            ).all()
            
            total = len(logs)
            successful = sum(1 for log in logs if log.success)
            failed = total - successful
            
            # 平均耗时
            durations = [log.duration_seconds for log in logs if log.duration_seconds]
            avg_duration = sum(durations) / len(durations) if durations else 0
            
            # 按区域统计
            by_region = {}
            region_success = {}
            for log in logs:
                region = log.region or "unknown"
                by_region[region] = by_region.get(region, 0) + 1
                if log.success:
                    region_success[region] = region_success.get(region, 0) + 1
            
            # 计算每个区域的成功率
            region_stats = [
                {
                    "region": region,
                    "total": count,
                    "success": region_success.get(region, 0),
                    "success_rate": round(region_success.get(region, 0) / count * 100, 2)
                }
                for region, count in by_region.items()
            ]
            
            # 按方法统计
            by_method = {}
            for log in logs:
                method = log.extraction_method or "unknown"
                by_method[method] = by_method.get(method, 0) + 1
            
            # 错误分析
            errors = {}
            for log in logs:
                if log.error_message:
                    key = log.error_message[:80]
                    errors[key] = errors.get(key, 0) + 1
            
            top_errors = sorted(errors.items(), key=lambda x: x[1], reverse=True)[:10]
            
            return {
                "summary": {
                    "total_calls": total,
                    "successful": successful,
                    "failed": failed,
                    "success_rate": round(successful / total * 100, 2) if total > 0 else 0,
                    "avg_duration_seconds": round(avg_duration, 2)
                },
                "by_region": region_stats,
                "by_method": by_method,
                "top_errors": [{"error": e[0], "count": e[1]} for e in top_errors],
                "period_days": days
            }
        finally:
            session.close()

    def get_api_analytics(self, days: int = 7) -> Dict[str, Any]:
        """获取 API 请求分析"""
        db = self._get_db()
        session = db.get_session()
        
        try:
            start_date = datetime.now() - timedelta(days=days)
            
            logs = session.query(ApiUsageLog).filter(
                ApiUsageLog.created_at >= start_date
            ).all()
            
            total = len(logs)
            
            # 状态码分布
            by_status = {}
            for log in logs:
                status = str(log.status_code or "unknown")
                by_status[status] = by_status.get(status, 0) + 1
            
            # 端点热度
            by_endpoint = {}
            for log in logs:
                endpoint = log.endpoint or "unknown"
                by_endpoint[endpoint] = by_endpoint.get(endpoint, 0) + 1
            
            top_endpoints = sorted(by_endpoint.items(), key=lambda x: x[1], reverse=True)[:15]
            
            # 平均响应时间
            response_times = [log.response_time_ms for log in logs if log.response_time_ms]
            avg_response_time = sum(response_times) / len(response_times) if response_times else 0
            
            # P95 响应时间
            if response_times:
                sorted_times = sorted(response_times)
                p95_index = int(len(sorted_times) * 0.95)
                p95_response_time = sorted_times[p95_index] if p95_index < len(sorted_times) else sorted_times[-1]
            else:
                p95_response_time = 0
            
            # 错误率
            error_count = sum(1 for log in logs if log.status_code and log.status_code >= 400)
            error_rate = (error_count / total * 100) if total > 0 else 0
            
            return {
                "summary": {
                    "total_requests": total,
                    "avg_response_time_ms": round(avg_response_time, 2),
                    "p95_response_time_ms": round(p95_response_time, 2),
                    "error_rate": round(error_rate, 2)
                },
                "by_status": by_status,
                "top_endpoints": [{"endpoint": e[0], "count": e[1]} for e in top_endpoints],
                "period_days": days
            }
        finally:
            session.close()

    def get_user_analytics(self, days: int = 30) -> Dict[str, Any]:
        """获取用户分析"""
        db = self._get_db()
        session = db.get_session()
        
        try:
            start_date = datetime.now() - timedelta(days=days)
            
            # 用户统计
            total_users = session.query(User).count()
            premium_users = session.query(User).filter(User.is_premium == True).count()
            admin_users = session.query(User).filter(User.is_admin == True).count()
            
            # 新增用户趋势
            new_users_period = session.query(User).filter(
                User.created_at >= start_date
            ).count()
            
            # 每日新增
            daily_new = {}
            users = session.query(User).filter(User.created_at >= start_date).all()
            for user in users:
                if user.created_at:
                    day = user.created_at.strftime("%Y-%m-%d")
                    daily_new[day] = daily_new.get(day, 0) + 1
            
            daily_new = dict(sorted(daily_new.items()))
            
            return {
                "summary": {
                    "total": total_users,
                    "premium": premium_users,
                    "admin": admin_users,
                    "new_in_period": new_users_period
                },
                "daily_new": [{"date": k, "count": v} for k, v in daily_new.items()],
                "period_days": days
            }
        finally:
            session.close()

    def get_geo_analytics(self, days: int = 7) -> Dict[str, Any]:
        """获取地理分布分析"""
        db = self._get_db()
        session = db.get_session()
        
        try:
            start_date = datetime.now() - timedelta(days=days)
            
            # 按国家统计
            country_stats = session.query(
                ApiUsageLog.country_code,
                func.count(ApiUsageLog.id).label('count')
            ).filter(
                ApiUsageLog.created_at >= start_date,
                ApiUsageLog.country_code.isnot(None)
            ).group_by(ApiUsageLog.country_code).order_by(desc('count')).limit(20).all()
            
            total = sum(stat[1] for stat in country_stats)
            
            by_country = [
                {
                    "country_code": stat[0],
                    "count": stat[1],
                    "percentage": round(stat[1] / total * 100, 2) if total > 0 else 0
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
            ).group_by(ApiUsageLog.city).order_by(desc('count')).limit(15).all()
            
            by_city = [{"city": stat[0], "count": stat[1]} for stat in city_stats]
            
            return {
                "by_country": by_country,
                "by_city": by_city,
                "period_days": days
            }
        finally:
            session.close()

    def get_hourly_timeline(self, hours: int = 24) -> List[Dict[str, Any]]:
        """获取按小时的时间线数据"""
        db = self._get_db()
        session = db.get_session()
        
        try:
            data = []
            now = datetime.now()
            
            for i in range(hours):
                hour_start = (now - timedelta(hours=i)).replace(minute=0, second=0, microsecond=0)
                hour_end = hour_start + timedelta(hours=1)
                
                api_count = session.query(ApiUsageLog).filter(
                    ApiUsageLog.created_at >= hour_start,
                    ApiUsageLog.created_at < hour_end
                ).count()
                
                agentgo_count = session.query(AgentGoUsageLog).filter(
                    AgentGoUsageLog.created_at >= hour_start,
                    AgentGoUsageLog.created_at < hour_end
                ).count()
                
                downloads = session.query(UsageLog).filter(
                    UsageLog.created_at >= hour_start,
                    UsageLog.created_at < hour_end
                ).count()
                
                data.append({
                    "timestamp": hour_start.isoformat(),
                    "hour": hour_start.strftime("%H:00"),
                    "api_requests": api_count,
                    "agentgo_calls": agentgo_count,
                    "downloads": downloads
                })
            
            return list(reversed(data))
        finally:
            session.close()


# 全局实例
_stats_service = None


def get_stats_service() -> StatsService:
    """获取统计服务单例"""
    global _stats_service
    if _stats_service is None:
        _stats_service = StatsService()
    return _stats_service
