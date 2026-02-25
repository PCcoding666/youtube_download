"""
Credit 充值相关 API 路由
处理充值、余额查询、交易记录、LemonSqueezy Webhook
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel, Field
from typing import Optional
import logging

from app.database import get_database
from app.api.auth_routes import get_current_user
from app.services import lemonsqueezy_service
from app.config import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/credits", tags=["credits"])


# ============================================================================
# 请求/响应模型
# ============================================================================


class CheckoutRequest(BaseModel):
    """充值请求 - 自定义金额"""
    amount: int = Field(..., ge=1, description="充值金额 (SGD 整数, 最低 1)")


class CheckoutResponse(BaseModel):
    """充值响应"""
    success: bool
    checkout_url: Optional[str] = None
    order_number: Optional[str] = None
    sgd_amount: int = 0
    credit_amount: int = 0
    message: str = ""


class BalanceResponse(BaseModel):
    """余额响应"""
    credit_balance: int
    username: str
    user_id: int


# ============================================================================
# API 端点
# ============================================================================


@router.post("/checkout", response_model=CheckoutResponse)
async def create_checkout(
    request: CheckoutRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    创建充值 Checkout

    用户自定义金额（SGD 整数, 最低 1, 建议 10）
    1 SGD = 5 credits
    """
    db = get_database()
    sgd_amount = request.amount
    credit_amount = lemonsqueezy_service.calculate_credits(sgd_amount)

    # 检查 LemonSqueezy 是否配置
    if not lemonsqueezy_service.is_configured():
        # 开发模式：直接完成充值（模拟）
        order_number = db.create_credit_order(
            user_id=current_user["id"],
            usd_amount=float(sgd_amount),
            credit_amount=credit_amount,
        )
        success, amount = db.complete_credit_order(order_number)
        return CheckoutResponse(
            success=success,
            order_number=order_number,
            sgd_amount=sgd_amount,
            credit_amount=credit_amount,
            message=f"[开发模式] 充值成功! +{credit_amount} credits",
        )

    # 创建本地订单
    order_number = db.create_credit_order(
        user_id=current_user["id"],
        usd_amount=float(sgd_amount),  # 存储 SGD 金额 (字段复用)
        credit_amount=credit_amount,
    )

    # 创建 LemonSqueezy Checkout (单一 variant + custom_price)
    result = await lemonsqueezy_service.create_checkout(
        user_email=current_user["email"],
        sgd_amount=sgd_amount,
        custom_data={
            "user_id": str(current_user["id"]),
            "order_number": order_number,
        },
    )

    if not result:
        raise HTTPException(status_code=500, detail="创建支付链接失败")

    return CheckoutResponse(
        success=True,
        checkout_url=result["checkout_url"],
        order_number=order_number,
        sgd_amount=sgd_amount,
        credit_amount=credit_amount,
        message=f"请前往支付页面完成充值 S${sgd_amount} = {credit_amount} credits",
    )


@router.post("/webhook")
async def lemonsqueezy_webhook(request: Request):
    """
    LemonSqueezy Webhook 回调

    处理 order_created 事件，自动增加用户 credit
    """
    # 读取原始请求体
    body = await request.body()
    signature = request.headers.get("X-Signature", "")

    # 验证签名
    if not lemonsqueezy_service.verify_webhook_signature(body, signature):
        logger.warning("Webhook 签名验证失败")
        raise HTTPException(status_code=403, detail="Invalid signature")

    # 解析数据
    import json
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    parsed = lemonsqueezy_service.parse_order_webhook(data)
    if not parsed:
        # 不是 order_created 事件，忽略
        return {"status": "ignored"}

    logger.info(
        f"Webhook 收到订单: order_id={parsed['order_id']}, "
        f"email={parsed['user_email']}, amount=S${parsed['sgd_amount']}"
    )

    db = get_database()

    # 方式1: 通过 custom_data 中的 order_number 关联
    custom_data = parsed.get("custom_data", {})
    order_number = custom_data.get("order_number")

    if order_number:
        success, credit_amount = db.complete_credit_order(
            order_number=order_number,
            lemon_order_id=parsed["order_id"],
        )
    else:
        # 方式2: 通过 email 直接充值
        success, credit_amount = db.complete_credit_order_by_lemon_id(
            lemon_order_id=parsed["order_id"],
            user_email=parsed["user_email"],
            usd_amount=parsed["sgd_amount"],  # 复用字段存 SGD
        )

    if success:
        logger.info(f"Webhook 充值成功: +{credit_amount} credits for {parsed['user_email']}")
    else:
        logger.warning(f"Webhook 充值处理失败或重复: order_id={parsed['order_id']}")

    return {"status": "ok", "credits_added": credit_amount if success else 0}


@router.get("/balance", response_model=BalanceResponse)
async def get_balance(current_user: dict = Depends(get_current_user)):
    """
    查询当前 Credit 余额
    """
    db = get_database()
    balance = db.get_credit_balance(current_user["id"])

    return BalanceResponse(
        credit_balance=balance,
        username=current_user["username"],
        user_id=current_user["id"],
    )


@router.get("/transactions")
async def get_transactions(
    current_user: dict = Depends(get_current_user),
    limit: int = 50,
    offset: int = 0,
):
    """
    查询 Credit 交易记录
    """
    db = get_database()
    transactions = db.get_credit_transactions(
        user_id=current_user["id"],
        limit=limit,
        offset=offset,
    )

    balance = db.get_credit_balance(current_user["id"])

    return {
        "credit_balance": balance,
        "transactions": transactions,
        "limit": limit,
        "offset": offset,
    }


@router.get("/packages")
async def get_packages():
    """
    获取充值信息（自定义金额模式）
    """
    return {
        "mode": "custom",
        "currency": "SGD",
        "min_amount": lemonsqueezy_service.MIN_AMOUNT_SGD,
        "suggested_amount": lemonsqueezy_service.SUGGESTED_AMOUNT_SGD,
        "credits_per_sgd": lemonsqueezy_service.CREDITS_PER_SGD,
        "rate": "1 SGD = 5 Credits",
        "payment_configured": lemonsqueezy_service.is_configured(),
        "suggested_amounts": [1, 5, 10, 20, 50],
    }
