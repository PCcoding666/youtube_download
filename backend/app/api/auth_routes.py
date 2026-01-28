"""
用户认证相关的API路由
"""

from fastapi import APIRouter, HTTPException, Depends, Header
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
import logging

from app.database import get_database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


# ============================================================================
# 请求/响应模型
# ============================================================================


class RegisterRequest(BaseModel):
    """用户注册请求"""

    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr
    password: str = Field(..., min_length=6)


class LoginRequest(BaseModel):
    """用户登录请求"""

    email: EmailStr
    password: str


class AuthResponse(BaseModel):
    """认证响应"""

    success: bool
    message: str
    token: Optional[str] = None
    user: Optional[dict] = None


class UserInfoResponse(BaseModel):
    """用户信息响应"""

    id: int
    username: str
    email: str
    is_premium: bool
    quota: dict


class PaymentRequest(BaseModel):
    """付费请求"""

    plan_type: str = Field(..., description="套餐类型: monthly, yearly")


# ============================================================================
# 依赖函数
# ============================================================================


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    """从token获取当前用户"""
    if not authorization:
        raise HTTPException(status_code=401, detail="未提供认证令牌")

    # 解析 Bearer token
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(status_code=401, detail="无效的认证令牌格式")

    token = parts[1]
    db = get_database()
    user = db.verify_token(token)

    if not user:
        raise HTTPException(status_code=401, detail="认证令牌无效或已过期")

    return user


# ============================================================================
# API端点
# ============================================================================


@router.post("/register", response_model=AuthResponse)
async def register(request: RegisterRequest):
    """
    用户注册

    创建新用户账号，自动获得3次免费下载机会
    """
    db = get_database()

    # 创建用户
    user_id = db.create_user(request.username, request.email, request.password)

    if not user_id:
        raise HTTPException(status_code=400, detail="用户名或邮箱已存在")

    # 创建会话
    token = db.create_session(user_id)

    # 获取用户信息
    user = db.get_user_by_id(user_id)

    return AuthResponse(
        success=True,
        message="注册成功！您已获得3次免费下载机会",
        token=token,
        user={
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "is_premium": user["is_premium"],
        },
    )


@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest):
    """
    用户登录

    使用邮箱和密码登录
    """
    db = get_database()

    # 验证用户
    user = db.authenticate_user(request.email, request.password)

    if not user:
        raise HTTPException(status_code=401, detail="邮箱或密码错误")

    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="账号已被禁用")

    # 创建会话
    token = db.create_session(user["id"])

    return AuthResponse(
        success=True,
        message="登录成功",
        token=token,
        user={
            "id": user["id"],
            "username": user["username"],
            "email": user["email"],
            "is_premium": user["is_premium"],
        },
    )


@router.get("/me", response_model=UserInfoResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """
    获取当前用户信息

    需要认证
    """
    db = get_database()

    quota = db.get_user_quota(current_user["id"])

    return UserInfoResponse(
        id=current_user["id"],
        username=current_user["username"],
        email=current_user["email"],
        is_premium=current_user["is_premium"],
        quota={
            "free_downloads_remaining": quota["free_downloads_remaining"],
            "total_downloads": quota["total_downloads"],
        },
    )


@router.get("/quota")
async def get_quota(current_user: dict = Depends(get_current_user)):
    """
    获取用户配额信息

    需要认证
    """
    db = get_database()

    quota = db.get_user_quota(current_user["id"])

    if not quota:
        raise HTTPException(status_code=404, detail="配额信息不存在")

    return {
        "user_id": current_user["id"],
        "username": current_user["username"],
        "is_premium": current_user["is_premium"],
        "free_downloads_remaining": quota["free_downloads_remaining"],
        "total_downloads": quota["total_downloads"],
        "status": "unlimited" if current_user["is_premium"] else "limited",
    }


@router.post("/payment/create")
async def create_payment_order(
    request: PaymentRequest, current_user: dict = Depends(get_current_user)
):
    """
    创建付费订单

    需要认证
    """
    db = get_database()

    # 定义价格
    pricing = {"monthly": 9.99, "yearly": 99.99}

    if request.plan_type not in pricing:
        raise HTTPException(status_code=400, detail="无效的套餐类型")

    amount = pricing[request.plan_type]

    # 创建订单
    order_number = db.create_payment_order(current_user["id"], request.plan_type, amount)

    return {
        "success": True,
        "order_number": order_number,
        "amount": amount,
        "plan_type": request.plan_type,
        "message": "订单创建成功",
    }


@router.post("/payment/complete/{order_number}")
async def complete_payment_order(
    order_number: str, current_user: dict = Depends(get_current_user)
):
    """
    完成付款（模拟）

    这是一个模拟付款接口，实际应用中应该对接真实支付网关
    """
    db = get_database()

    success = db.complete_payment(order_number)

    if not success:
        raise HTTPException(status_code=404, detail="订单不存在")

    return {
        "success": True,
        "message": "支付成功！您已升级为高级用户",
        "is_premium": True,
    }


@router.get("/logout")
async def logout(authorization: Optional[str] = Header(None)):
    """
    用户登出

    注意：当前实现中token会自动过期，这里只是一个占位符
    实际应用中应该将token加入黑名单
    """
    return {"success": True, "message": "登出成功"}
