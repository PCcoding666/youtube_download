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

from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, Float, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.sql import func
from typing import List

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
    is_admin = Column(Boolean, default=False)  # 管理员标识
    credit_balance = Column(Integer, default=0)  # Credit 余额


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
    """付费订单表 - 充值订单"""
    __tablename__ = "payment_orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    order_number = Column(String(100), unique=True, nullable=False, index=True)
    amount = Column(Float, nullable=False)  # USD 金额
    credit_amount = Column(Integer, default=0)  # 充值的 credit 数量
    plan_type = Column(String(20), nullable=False, default="credit")  # credit (保留兼容)
    status = Column(String(20), default="pending")  # pending, paid, failed
    lemon_order_id = Column(String(100), nullable=True, index=True)  # LemonSqueezy 订单 ID
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    paid_at = Column(DateTime(timezone=True), nullable=True)


class CreditTransaction(Base):
    """Credit 交易记录表"""
    __tablename__ = "credit_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    type = Column(String(20), nullable=False, index=True)  # recharge, consume, refund
    amount = Column(Integer, nullable=False)  # 正数=增加, 负数=扣除
    balance_after = Column(Integer, nullable=False)  # 交易后余额
    description = Column(String(500), nullable=True)
    order_number = Column(String(100), nullable=True, index=True)  # 关联充值订单号
    video_url = Column(Text, nullable=True)  # 关联的视频 URL（消费时）
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class UserApiKey(Base):
    """用户 API Key 表"""
    __tablename__ = "user_api_keys"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    key_hash = Column(String(64), unique=True, nullable=False, index=True)  # SHA256 哈希
    key_prefix = Column(String(8), nullable=False)  # 前8位明文，用于显示
    name = Column(String(100), nullable=True)  # 用户自定义名称
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_used_at = Column(DateTime(timezone=True), nullable=True)


# ============================================================================
# 管理员统计相关表
# ============================================================================

class ApiUsageLog(Base):
    """API 使用记录表 - 记录所有请求"""
    __tablename__ = "api_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    endpoint = Column(String(255), nullable=False, index=True)
    method = Column(String(10), nullable=False)
    status_code = Column(Integer)
    response_time_ms = Column(Float)  # 响应时间(毫秒)
    request_size = Column(Integer, default=0)  # 请求大小
    response_size = Column(Integer, default=0)  # 响应大小
    ip_address = Column(String(45), index=True)
    user_agent = Column(String(500))
    country_code = Column(String(10), index=True)
    city = Column(String(100))
    user_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class AgentGoUsageLog(Base):
    """AgentGo 调用记录表"""
    __tablename__ = "agentgo_usage_logs"

    id = Column(Integer, primary_key=True, index=True)
    region = Column(String(20), nullable=False, index=True)
    video_url = Column(Text)
    video_id = Column(String(50), index=True)
    success = Column(Boolean, default=False)
    duration_seconds = Column(Float)
    error_message = Column(Text, nullable=True)
    extraction_method = Column(String(50))  # cookies/po_token/direct
    ip_address = Column(String(45))
    user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class ProxyTrafficLog(Base):
    """代理流量记录表"""
    __tablename__ = "proxy_traffic_logs"

    id = Column(Integer, primary_key=True, index=True)
    request_bytes = Column(BigInteger, default=0)
    response_bytes = Column(BigInteger, default=0)
    total_bytes = Column(BigInteger, default=0)
    endpoint = Column(String(255), index=True)
    video_id = Column(String(50), nullable=True)
    resolution = Column(String(20))
    ip_address = Column(String(45))
    user_id = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)


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
                    "is_admin": user.is_admin,
                    "credit_balance": user.credit_balance,
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
                    "is_admin": user.is_admin,
                    "credit_balance": user.credit_balance,
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
                    "is_admin": user.is_admin,
                    "created_at": user.created_at,
                    "credit_balance": user.credit_balance,
                }
            return None

        finally:
            session.close()

    # ========================================================================
    # Credit 管理
    # ========================================================================

    def get_credit_balance(self, user_id: int) -> int:
        """获取用户 credit 余额"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            return user.credit_balance if user else 0
        finally:
            session.close()

    def add_credits(self, user_id: int, amount: int, description: str = "",
                    order_number: Optional[str] = None) -> tuple[bool, int]:
        """
        增加用户 credit

        Returns:
            (成功与否, 交易后余额)
        """
        session = self.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).with_for_update().first()
            if not user:
                return False, 0

            user.credit_balance += amount
            new_balance = user.credit_balance

            # 记录交易
            tx = CreditTransaction(
                user_id=user_id,
                type="recharge",
                amount=amount,
                balance_after=new_balance,
                description=description,
                order_number=order_number,
            )
            session.add(tx)
            session.commit()

            logger.info(f"用户 {user_id} 充值 {amount} credits, 余额: {new_balance}")
            return True, new_balance

        except Exception as e:
            session.rollback()
            logger.error(f"增加 credit 失败: {e}")
            return False, 0
        finally:
            session.close()

    def deduct_credit(self, user_id: int, amount: int = 1, description: str = "",
                      video_url: Optional[str] = None) -> tuple[bool, int]:
        """
        扣除用户 credit（下载前预扣）

        Returns:
            (成功与否, 交易后余额)
        """
        session = self.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).with_for_update().first()
            if not user:
                return False, 0

            if user.credit_balance < amount:
                return False, user.credit_balance

            user.credit_balance -= amount
            new_balance = user.credit_balance

            # 记录交易
            tx = CreditTransaction(
                user_id=user_id,
                type="consume",
                amount=-amount,
                balance_after=new_balance,
                description=description or "视频下载",
                video_url=video_url,
            )
            session.add(tx)
            session.commit()

            logger.info(f"用户 {user_id} 消耗 {amount} credit, 余额: {new_balance}")
            return True, new_balance

        except Exception as e:
            session.rollback()
            logger.error(f"扣除 credit 失败: {e}")
            return False, 0
        finally:
            session.close()

    def refund_credit(self, user_id: int, amount: int = 1, description: str = "",
                      video_url: Optional[str] = None) -> tuple[bool, int]:
        """
        退还用户 credit（下载失败时调用）

        Returns:
            (成功与否, 交易后余额)
        """
        session = self.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).with_for_update().first()
            if not user:
                return False, 0

            user.credit_balance += amount
            new_balance = user.credit_balance

            # 记录交易
            tx = CreditTransaction(
                user_id=user_id,
                type="refund",
                amount=amount,
                balance_after=new_balance,
                description=description or "下载失败退还",
                video_url=video_url,
            )
            session.add(tx)
            session.commit()

            logger.info(f"用户 {user_id} 退还 {amount} credit, 余额: {new_balance}")
            return True, new_balance

        except Exception as e:
            session.rollback()
            logger.error(f"退还 credit 失败: {e}")
            return False, 0
        finally:
            session.close()

    def check_credit(self, user_id: int, required: int = 1) -> tuple[bool, int]:
        """
        检查用户是否有足够的 credit

        Returns:
            (是否足够, 当前余额)
        """
        balance = self.get_credit_balance(user_id)
        return balance >= required, balance

    def get_credit_transactions(self, user_id: int, limit: int = 50,
                                offset: int = 0) -> List[Dict[str, Any]]:
        """获取用户 credit 交易记录"""
        session = self.get_session()
        try:
            txs = session.query(CreditTransaction).filter(
                CreditTransaction.user_id == user_id
            ).order_by(CreditTransaction.created_at.desc()).offset(offset).limit(limit).all()

            return [
                {
                    "id": tx.id,
                    "type": tx.type,
                    "amount": tx.amount,
                    "balance_after": tx.balance_after,
                    "description": tx.description,
                    "order_number": tx.order_number,
                    "video_url": tx.video_url,
                    "created_at": tx.created_at,
                }
                for tx in txs
            ]
        finally:
            session.close()

    def create_credit_order(self, user_id: int, usd_amount: float, credit_amount: int) -> str:
        """创建充值订单"""
        session = self.get_session()
        try:
            order_number = f"CRD{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(4)}"

            order = PaymentOrder(
                user_id=user_id,
                order_number=order_number,
                amount=usd_amount,
                credit_amount=credit_amount,
                plan_type="credit",
            )
            session.add(order)
            session.commit()

            return order_number

        except Exception as e:
            session.rollback()
            logger.error(f"创建充值订单失败: {e}")
            raise
        finally:
            session.close()

    def complete_credit_order(self, order_number: str,
                              lemon_order_id: Optional[str] = None) -> tuple[bool, int]:
        """
        完成充值订单 (Webhook 回调时调用)

        Returns:
            (成功与否, 充值的 credit 数量)
        """
        session = self.get_session()
        try:
            order = session.query(PaymentOrder).filter(
                PaymentOrder.order_number == order_number
            ).first()

            if not order or order.status == "paid":
                return False, 0

            order.status = "paid"
            order.paid_at = datetime.now()
            if lemon_order_id:
                order.lemon_order_id = lemon_order_id

            session.commit()

            # 增加 credit
            credit_amount = order.credit_amount or int(order.amount * 5)
            success, balance = self.add_credits(
                user_id=order.user_id,
                amount=credit_amount,
                description=f"充值 ${order.amount} = {credit_amount} credits",
                order_number=order_number,
            )

            return success, credit_amount

        except Exception as e:
            session.rollback()
            logger.error(f"完成充值订单失败: {e}")
            return False, 0
        finally:
            session.close()

    def complete_credit_order_by_lemon_id(self, lemon_order_id: str,
                                           user_email: str,
                                           usd_amount: float) -> tuple[bool, int]:
        """
        通过 LemonSqueezy 订单 ID 完成充值（Webhook 直接调用）
        如果没有预创建的订单，则自动创建并完成。

        Returns:
            (成功与否, 充值的 credit 数量)
        """
        session = self.get_session()
        try:
            # 检查是否已处理过
            existing = session.query(PaymentOrder).filter(
                PaymentOrder.lemon_order_id == lemon_order_id
            ).first()
            if existing and existing.status == "paid":
                return False, 0  # 已处理，防止重复

            # 找到用户
            user = session.query(User).filter(User.email == user_email).first()
            if not user:
                logger.error(f"Webhook: 用户不存在 email={user_email}")
                return False, 0

            credit_amount = int(usd_amount * 5)  # $1 = 5 credits

            if existing:
                # 有预创建的订单，完成它
                existing.status = "paid"
                existing.paid_at = datetime.now()
                existing.lemon_order_id = lemon_order_id
                session.commit()
                success, balance = self.add_credits(
                    user_id=user.id,
                    amount=credit_amount,
                    description=f"充值 ${usd_amount} = {credit_amount} credits",
                    order_number=existing.order_number,
                )
                return success, credit_amount
            else:
                # 没有预创建的订单（直接从 LemonSqueezy 购买），自动创建
                order_number = f"CRD{datetime.now().strftime('%Y%m%d%H%M%S')}{secrets.token_hex(4)}"
                order = PaymentOrder(
                    user_id=user.id,
                    order_number=order_number,
                    amount=usd_amount,
                    credit_amount=credit_amount,
                    plan_type="credit",
                    status="paid",
                    paid_at=datetime.now(),
                    lemon_order_id=lemon_order_id,
                )
                session.add(order)
                session.commit()

                success, balance = self.add_credits(
                    user_id=user.id,
                    amount=credit_amount,
                    description=f"充值 ${usd_amount} = {credit_amount} credits",
                    order_number=order_number,
                )
                return success, credit_amount

        except Exception as e:
            session.rollback()
            logger.error(f"通过 LemonSqueezy 完成充值失败: {e}")
            return False, 0
        finally:
            session.close()

    # ========================================================================
    # API Key 管理
    # ========================================================================

    def generate_api_key(self, user_id: int, name: Optional[str] = None) -> Optional[str]:
        """
        生成新的 API Key

        Returns:
            明文 API Key (仅此一次返回) 或 None
        """
        session = self.get_session()
        try:
            # 生成随机 key: sk-yt-{random}
            raw_key = f"sk-yt-{secrets.token_urlsafe(32)}"
            key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
            key_prefix = raw_key[:12]  # "sk-yt-XXXX"

            api_key = UserApiKey(
                user_id=user_id,
                key_hash=key_hash,
                key_prefix=key_prefix,
                name=name or "Default",
            )
            session.add(api_key)
            session.commit()

            logger.info(f"为用户 {user_id} 生成 API Key: {key_prefix}...")
            return raw_key

        except Exception as e:
            session.rollback()
            logger.error(f"生成 API Key 失败: {e}")
            return None
        finally:
            session.close()

    def verify_api_key(self, raw_key: str) -> Optional[Dict[str, Any]]:
        """
        验证 API Key 并返回关联的用户信息和余额

        Returns:
            用户信息字典或 None
        """
        session = self.get_session()
        try:
            key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

            api_key = session.query(UserApiKey).filter(
                UserApiKey.key_hash == key_hash,
                UserApiKey.is_active == True,
            ).first()

            if not api_key:
                return None

            # 更新最后使用时间
            api_key.last_used_at = datetime.now()
            session.commit()

            # 获取用户信息
            user = session.query(User).filter(User.id == api_key.user_id).first()
            if not user or not user.is_active:
                return None

            return {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "credit_balance": user.credit_balance,
                "is_active": user.is_active,
                "api_key_id": api_key.id,
                "api_key_name": api_key.name,
            }

        except Exception as e:
            session.rollback()
            logger.error(f"验证 API Key 失败: {e}")
            return None
        finally:
            session.close()

    def list_api_keys(self, user_id: int) -> List[Dict[str, Any]]:
        """获取用户所有 API Key（仅显示前缀）"""
        session = self.get_session()
        try:
            keys = session.query(UserApiKey).filter(
                UserApiKey.user_id == user_id
            ).order_by(UserApiKey.created_at.desc()).all()

            return [
                {
                    "id": key.id,
                    "key_prefix": key.key_prefix,
                    "name": key.name,
                    "is_active": key.is_active,
                    "created_at": key.created_at,
                    "last_used_at": key.last_used_at,
                }
                for key in keys
            ]
        finally:
            session.close()

    def delete_api_key(self, key_id: int, user_id: int) -> bool:
        """删除 API Key"""
        session = self.get_session()
        try:
            key = session.query(UserApiKey).filter(
                UserApiKey.id == key_id,
                UserApiKey.user_id == user_id,
            ).first()

            if not key:
                return False

            session.delete(key)
            session.commit()
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"删除 API Key 失败: {e}")
            return False
        finally:
            session.close()

    def update_api_key(self, key_id: int, user_id: int,
                       name: Optional[str] = None,
                       is_active: Optional[bool] = None) -> bool:
        """更新 API Key 名称或状态"""
        session = self.get_session()
        try:
            key = session.query(UserApiKey).filter(
                UserApiKey.id == key_id,
                UserApiKey.user_id == user_id,
            ).first()

            if not key:
                return False

            if name is not None:
                key.name = name
            if is_active is not None:
                key.is_active = is_active

            session.commit()
            return True

        except Exception as e:
            session.rollback()
            logger.error(f"更新 API Key 失败: {e}")
            return False
        finally:
            session.close()

    # ========================================================================
    # 管理员统计相关方法
    # ========================================================================

    def log_api_usage(
        self,
        endpoint: str,
        method: str,
        status_code: int,
        response_time_ms: float,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        country_code: Optional[str] = None,
        city: Optional[str] = None,
        user_id: Optional[int] = None,
        request_size: int = 0,
        response_size: int = 0
    ):
        """记录 API 使用日志"""
        session = self.get_session()
        try:
            log = ApiUsageLog(
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
            session.add(log)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"记录API使用日志失败: {e}")
        finally:
            session.close()

    def log_agentgo_usage(
        self,
        region: str,
        video_url: Optional[str] = None,
        video_id: Optional[str] = None,
        success: bool = False,
        duration_seconds: float = 0,
        error_message: Optional[str] = None,
        extraction_method: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_id: Optional[int] = None
    ):
        """记录 AgentGo 调用日志"""
        session = self.get_session()
        try:
            log = AgentGoUsageLog(
                region=region,
                video_url=video_url,
                video_id=video_id,
                success=success,
                duration_seconds=duration_seconds,
                error_message=error_message,
                extraction_method=extraction_method,
                ip_address=ip_address,
                user_id=user_id
            )
            session.add(log)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"记录AgentGo使用日志失败: {e}")
        finally:
            session.close()

    def log_proxy_traffic(
        self,
        request_bytes: int = 0,
        response_bytes: int = 0,
        endpoint: Optional[str] = None,
        video_id: Optional[str] = None,
        resolution: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_id: Optional[int] = None
    ):
        """记录代理流量日志"""
        session = self.get_session()
        try:
            log = ProxyTrafficLog(
                request_bytes=request_bytes,
                response_bytes=response_bytes,
                total_bytes=request_bytes + response_bytes,
                endpoint=endpoint,
                video_id=video_id,
                resolution=resolution,
                ip_address=ip_address,
                user_id=user_id
            )
            session.add(log)
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"记录代理流量日志失败: {e}")
        finally:
            session.close()

    def set_user_admin(self, user_id: int, is_admin: bool) -> bool:
        """设置用户管理员权限"""
        session = self.get_session()
        try:
            user = session.query(User).filter(User.id == user_id).first()
            if user:
                user.is_admin = is_admin
                session.commit()
                return True
            return False
        except Exception as e:
            session.rollback()
            logger.error(f"设置管理员权限失败: {e}")
            return False
        finally:
            session.close()

    def get_all_users(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """获取所有用户列表"""
        session = self.get_session()
        try:
            users = session.query(User).order_by(User.created_at.desc()).offset(offset).limit(limit).all()
            return [
                {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "is_active": user.is_active,
                    "is_premium": user.is_premium,
                    "is_admin": user.is_admin,
                    "created_at": user.created_at,
                }
                for user in users
            ]
        finally:
            session.close()

    def get_user_count(self) -> int:
        """获取用户总数"""
        session = self.get_session()
        try:
            return session.query(User).count()
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
