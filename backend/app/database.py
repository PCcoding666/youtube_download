"""
PostgreSQL数据库管理
用于用户认证、匿名使用追踪、使用配额和付费管理
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging
import os

from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql import func

logger = logging.getLogger(__name__)

# 获取数据库URL从环境变量
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://ytuser:ytpassword123@localhost:5432/ytdownloader")

# 创建数据库引擎
engine = create_engine(DATABASE_URL, pool_pre_ping=True, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# ============================================================================
# 数据库模型
# ============================================================================

class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_active = Column(Boolean, default=True)
    is_premium = Column(Boolean, default=False)


class Session(Base):
    """会话表"""
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    token = Column(String(255), unique=True, nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    expires_at = Column(DateTime(timezone=True), nullable=False)


class AnonymousUsage(Base):
    """匿名用户使用记录（基于IP）"""
    __tablename__ = "anonymous_usage"

    id = Column(Integer, primary_key=True, index=True)
    ip_address = Column(String(45), nullable=False, index=True)  # 支持IPv6
    usage_count = Column(Integer, default=0)
    first_used_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class UserQuota(Base):
    """用户配额表"""
    __tablename__ = "user_quotas"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)
    free_downloads_remaining = Column(Integer, default=3)
    total_downloads = Column(Integer, default=0)
    last_reset_date = Column(DateTime(timezone=True), server_default=func.now())


class UsageLog(Base):
    """使用记录表"""
    __tablename__ = "usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)  # 可为空（匿名用户）
    ip_address = Column(String(45), nullable=True)  # 记录IP
    video_url = Column(Text, nullable=False)
    video_title = Column(String(500), nullable=True)
    resolution = Column(String(20), nullable=True)
    file_size = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PaymentOrder(Base):
    """付费订单表"""
    __tablename__ = "payment_orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    order_number = Column(String(100), unique=True, nullable=False, index=True)
    amount = Column(Float, nullable=False)
    plan_type = Column(String(20), nullable=False)  # monthly, yearly
    status = Column(String(20), default="pending")  # pending, paid, failed
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    paid_at = Column(DateTime(timezone=True), nullable=True)


# ============================================================================
# 数据库管理类
# ============================================================================

class Database:
    """PostgreSQL数据库管理器"""

    def __init__(self):
        """初始化数据库连接"""
        self.engine = engine
        self.SessionLocal = SessionLocal
        self.init_database()

    def init_database(self):
        """初始化数据库表结构"""
        try:
            Base.metadata.create_all(bind=self.engine)
            logger.info(f"数据库初始化完成: {DATABASE_URL.split('@')[1]}")
        except Exception as e:
            logger.error(f"数据库初始化失败: {e}")
            raise

    def get_session(self) -> Session:
        """获取数据库会话"""
        return self.SessionLocal()

    def hash_password(self, password: str) -> str:
        """哈希密码"""
        return hashlib.sha256(password.encode()).hexdigest()

    # ========================================================================
    # 匿名用户管理（基于IP）
    # ========================================================================

    def check_anonymous_usage(self, ip_address: str) -> tuple[bool, int]:
        """
        检查匿名用户使用次数
        
        Returns:
            (是否可以使用, 已使用次数)
        """
        session = self.get_session()
        try:
            usage = session.query(AnonymousUsage).filter(
                AnonymousUsage.ip_address == ip_address
            ).first()

            if not usage:
                # 新用户，可以使用
                return True, 0

            # 检查是否超过3次
            if usage.usage_count >= 3:
                return False, usage.usage_count

            return True, usage.usage_count

        finally:
            session.close()

    def increment_anonymous_usage(self, ip_address: str) -> int:
        """
        增加匿名用户使用次数
        
        Returns:
            当前使用次数
        """
        session = self.get_session()
        try:
            usage = session.query(AnonymousUsage).filter(
                AnonymousUsage.ip_address == ip_address
            ).first()

            if not usage:
                # 创建新记录
                usage = AnonymousUsage(ip_address=ip_address, usage_count=1)
                session.add(usage)
            else:
                # 增加计数
                usage.usage_count += 1
                usage.last_used_at = datetime.now()

            session.commit()
            return usage.usage_count

        except Exception as e:
            session.rollback()
            logger.error(f"增加匿名使用次数失败: {e}")
            raise
        finally:
            session.close()

    # ========================================================================
    # 用户管理
    # ========================================================================

    def create_user(self, username: str, email: str, password: str) -> Optional[int]:
        """创建新用户"""
        session = self.get_session()
        try:
            password_hash = self.hash_password(password)

            user = User(
                username=username,
                email=email,
                password_hash=password_hash
            )
            session.add(user)
            session.flush()

            # 创建初始配额（高级会员无限制）
            quota = UserQuota(
                user_id=user.id,
                free_downloads_remaining=999999,  # 注册用户无限制
                total_downloads=0
            )
            session.add(quota)

            session.commit()
            logger.info(f"用户创建成功: {username} (ID: {user.id})")
            return user.id

        except Exception as e:
            session.rollback()
            logger.error(f"用户创建失败: {e}")
            return None
        finally:
            session.close()

    def authenticate_user(self, email: str, password: str) -> Optional[Dict[str, Any]]:
        """验证用户登录"""
        session = self.get_session()
        try:
            password_hash = self.hash_password(password)

            user = session.query(User).filter(
                User.email == email,
                User.password_hash == password_hash
            ).first()

            if user:
                return {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "is_active": user.is_active,
                    "is_premium": user.is_premium,
                }
            return None

        finally:
            session.close()

    def create_session(self, user_id: int, expires_in_hours: int = 24) -> str:
        """创建用户会话token"""
        session = self.get_session()
        try:
            token = secrets.token_urlsafe(32)
            expires_at = datetime.now() + timedelta(hours=expires_in_hours)

            db_session = Session(
                user_id=user_id,
                token=token,
                expires_at=expires_at
            )
            session.add(db_session)
            session.commit()

            return token

        finally:
            session.close()

    def verify_token(self, token: str) -> Optional[Dict[str, Any]]:
        """验证token并返回用户信息"""
        session = self.get_session()
        try:
            db_session = session.query(Session).filter(
                Session.token == token,
                Session.expires_at > datetime.now()
            ).first()

            if not db_session:
                return None

            user = session.query(User).filter(User.id == db_session.user_id).first()

            if user:
                return {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "is_active": user.is_active,
                    "is_premium": user.is_premium,
                }
            return None

        finally:
            session.close()

    def get_user_quota(self, user_id: int) -> Optional[Dict[str, Any]]:
        """获取用户配额信息"""
        session = self.get_session()
        try:
            quota = session.query(UserQuota).filter(
                UserQuota.user_id == user_id
            ).first()

            if quota:
                return {
                    "free_downloads_remaining": quota.free_downloads_remaining,
                    "total_downloads": quota.total_downloads,
                    "last_reset_date": quota.last_reset_date,
                }
            return None

        finally:
            session.close()

    def check_and_deduct_quota(self, user_id: int) -> tuple[bool, str]:
        """检查并扣除配额"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()

            if user and user.is_premium:
                # 高级用户无限制
                quota = session.query(UserQuota).filter(UserQuota.user_id == user_id).first()
                if quota:
                    quota.total_downloads += 1
                    session.commit()
                return True, "高级用户，无限制使用"

            # 普通注册用户也无限制（因为已经注册了）
            quota = session.query(UserQuota).filter(UserQuota.user_id == user_id).first()
            if quota:
                quota.total_downloads += 1
                session.commit()

            return True, "注册用户，无限制使用"

        except Exception as e:
            session.rollback()
            logger.error(f"配额检查失败: {e}")
            return False, "配额检查失败"
        finally:
            session.close()

    def log_usage(
        self, 
        video_url: str, 
        video_title: str, 
        resolution: str, 
        file_size: int,
        user_id: Optional[int] = None,
        ip_address: Optional[str] = None
    ):
        """记录使用日志"""
        session = self.get_session()
        try:
            log = UsageLog(
                user_id=user_id,
                ip_address=ip_address,
                video_url=video_url,
                video_title=video_title,
                resolution=resolution,
                file_size=file_size
            )
            session.add(log)
            session.commit()

        except Exception as e:
            session.rollback()
            logger.error(f"记录使用日志失败: {e}")
        finally:
            session.close()

    def create_payment_order(self, user_id: int, plan_type: str, amount: float) -> str:
        """创建付费订单"""
        session = self.get_session()
        try:
            order_number = f"ORD{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(4)}"

            order = PaymentOrder(
                user_id=user_id,
                order_number=order_number,
                amount=amount,
                plan_type=plan_type
            )
            session.add(order)
            session.commit()

            return order_number

        finally:
            session.close()

    def complete_payment(self, order_number: str) -> bool:
        """完成付款（模拟）"""
        session = self.get_session()
        try:
            order = session.query(PaymentOrder).filter(
                PaymentOrder.order_number == order_number
            ).first()

            if not order:
                return False

            # 更新订单状态
            order.status = "paid"
            order.paid_at = datetime.now()

            # 升级用户为高级用户
            user = session.query(User).filter(User.id == order.user_id).first()
            if user:
                user.is_premium = True

            session.commit()
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"完成支付失败: {e}")
            return False
        finally:
            session.close()

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """根据ID获取用户信息"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()

            if user:
                return {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "is_active": user.is_active,
                    "is_premium": user.is_premium,
                    "created_at": user.created_at,
                }
            return None

        finally:
            session.close()


# 全局数据库实例
_db_instance = None


def get_database() -> Database:
    """获取数据库单例"""
    global _db_instance
    if _db_instance is None:
        _db_instance = Database()
    return _db_instance
