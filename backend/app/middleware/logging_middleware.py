"""
请求日志中间件
自动记录所有 API 请求到数据库
"""

import time
import logging
from typing import Optional, Callable
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp
import asyncio

logger = logging.getLogger(__name__)

# 只记录关键 API 调用（白名单模式）
# 这些是需要记录的关键业务端点
IMPORTANT_ENDPOINTS = [
    "/api/v1/extract",           # 视频下载请求 - 最重要
    "/api/v1/auth/login",        # 用户登录
    "/api/v1/auth/register",     # 用户注册
    "/api/v1/payment",           # 支付相关
    "/api/v1/proxy-download",    # 代理下载
]


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """请求日志中间件 - 只记录关键 API 请求"""

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self._db = None

    def _get_db(self):
        """延迟加载数据库实例"""
        if self._db is None:
            from app.database import get_database
            self._db = get_database()
        return self._db

    def _get_client_ip(self, request: Request) -> str:
        """获取客户端 IP 地址"""
        # 检查代理头
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
        return request.client.host if request.client else "0.0.0.0"

    def _should_log(self, path: str) -> bool:
        """判断是否应该记录此请求（白名单模式 - 只记录关键业务端点）"""
        # 只记录在白名单中的关键端点
        for important_path in IMPORTANT_ENDPOINTS:
            if path.startswith(important_path):
                return True
        return False

    async def _get_geo_info(self, ip_address: str) -> tuple[Optional[str], Optional[str]]:
        """获取地理位置信息"""
        try:
            from app.services.geo_service import get_geo_info
            info = await get_geo_info(ip_address)
            if info:
                return info.get("country_code"), info.get("city")
        except Exception as e:
            logger.debug(f"获取地理信息失败: {e}")
        return None, None

    def _get_user_id_from_request(self, request: Request) -> Optional[int]:
        """从请求中提取用户 ID"""
        # 尝试从 state 中获取（如果认证中间件已经设置）
        if hasattr(request.state, "user") and request.state.user:
            return request.state.user.get("id")
        
        # 尝试从 Authorization header 解析
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ")[1]
            try:
                db = self._get_db()
                user = db.verify_token(token)
                if user:
                    return user.get("id")
            except Exception:
                pass
        
        return None

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """处理请求并记录日志"""
        path = request.url.path
        
        # 检查是否需要记录
        if not self._should_log(path):
            return await call_next(request)
        
        # 记录请求开始时间
        start_time = time.time()
        
        # 获取请求信息
        ip_address = self._get_client_ip(request)
        user_agent = request.headers.get("User-Agent", "")[:500]
        method = request.method
        
        # 获取请求大小
        content_length = request.headers.get("Content-Length")
        request_size = int(content_length) if content_length else 0
        
        # 执行请求
        response = await call_next(request)
        
        # 计算响应时间
        response_time_ms = (time.time() - start_time) * 1000
        
        # 获取响应大小
        response_size = 0
        if hasattr(response, "headers"):
            response_content_length = response.headers.get("Content-Length")
            if response_content_length:
                response_size = int(response_content_length)
        
        # 获取用户 ID
        user_id = self._get_user_id_from_request(request)
        
        # 异步获取地理信息并记录日志
        asyncio.create_task(self._log_request(
            endpoint=path,
            method=method,
            status_code=response.status_code,
            response_time_ms=response_time_ms,
            ip_address=ip_address,
            user_agent=user_agent,
            user_id=user_id,
            request_size=request_size,
            response_size=response_size
        ))
        
        return response

    async def _log_request(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        response_time_ms: float,
        ip_address: str,
        user_agent: str,
        user_id: Optional[int],
        request_size: int,
        response_size: int
    ):
        """异步记录请求日志"""
        try:
            # 获取地理信息
            country_code, city = await self._get_geo_info(ip_address)
            
            # 记录到数据库
            db = self._get_db()
            db.log_api_usage(
                endpoint=endpoint,
                method=method,
                status_code=status_code,
                response_time_ms=response_time_ms,
                ip_address=ip_address,
                user_agent=user_agent,
                country_code=country_code,
                city=city,
                user_id=user_id,
                request_size=request_size,
                response_size=response_size
            )
        except Exception as e:
            logger.error(f"记录请求日志失败: {e}")
