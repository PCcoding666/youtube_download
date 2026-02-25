"""
LemonSqueezy 支付集成服务
用于创建充值 Checkout 和验证 Webhook 签名
使用单一 variant + custom_price 控制不同充值金额
"""

import hmac
import hashlib
import logging
from typing import Optional, Dict, Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

LEMONSQUEEZY_API_BASE = "https://api.lemonsqueezy.com/v1"

# Credit 汇率: 1 SGD = 5 credits
CREDITS_PER_SGD = 5
MIN_AMOUNT_SGD = 1
SUGGESTED_AMOUNT_SGD = 10


def is_configured() -> bool:
    """检查 LemonSqueezy 是否配置"""
    return bool(settings.lemonsqueezy_api_key and settings.lemonsqueezy_store_id)


def calculate_credits(sgd_amount: int) -> int:
    """根据 SGD 金额计算 credits"""
    return sgd_amount * CREDITS_PER_SGD


def _get_headers() -> Dict[str, str]:
    """获取 API 请求头"""
    return {
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
        "Authorization": f"Bearer {settings.lemonsqueezy_api_key}",
    }


async def create_checkout(
    user_email: str,
    sgd_amount: int,
    custom_data: Optional[Dict[str, Any]] = None,
) -> Optional[Dict[str, Any]]:
    """
    创建 LemonSqueezy Checkout (使用单一 variant + custom_price)

    Args:
        user_email: 用户邮箱 (用于关联)
        sgd_amount: 充值金额（SGD 整数, 最低 1）
        custom_data: 自定义数据 (传递 user_id, order_number 等)

    Returns:
        Checkout 数据 (包含 checkout URL) 或 None
    """
    if not is_configured():
        logger.error("LemonSqueezy 未配置")
        return None

    store_id = settings.lemonsqueezy_store_id
    variant_id = settings.lemonsqueezy_variant_id

    if not variant_id:
        logger.error("LemonSqueezy variant_id 未配置")
        return None

    # 金额转为 cents
    price_in_cents = sgd_amount * 100
    credit_amount = calculate_credits(sgd_amount)

    payload = {
        "data": {
            "type": "checkouts",
            "attributes": {
                "custom_price": price_in_cents,
                "checkout_data": {
                    "email": user_email,
                    "custom": {
                        **(custom_data or {}),
                        "sgd_amount": str(sgd_amount),
                        "credit_amount": str(credit_amount),
                    },
                },
                "product_options": {
                    "name": f"Credit Recharge - {credit_amount} Credits",
                    "description": f"S${sgd_amount} = {credit_amount} Credits for YouTube Downloader",
                    "redirect_url": "https://u2foru.site/?page=pricing",
                },
            },
            "relationships": {
                "store": {
                    "data": {
                        "type": "stores",
                        "id": store_id,
                    }
                },
                "variant": {
                    "data": {
                        "type": "variants",
                        "id": variant_id,
                    }
                },
            },
        }
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{LEMONSQUEEZY_API_BASE}/checkouts",
                headers=_get_headers(),
                json=payload,
            )

            if response.status_code in (200, 201):
                data = response.json()
                checkout_url = data.get("data", {}).get("attributes", {}).get("url")
                logger.info(f"LemonSqueezy Checkout 创建成功: S${sgd_amount} = {credit_amount} credits, URL: {checkout_url}")
                return {
                    "checkout_url": checkout_url,
                    "checkout_id": data.get("data", {}).get("id"),
                }
            else:
                logger.error(
                    f"LemonSqueezy Checkout 创建失败: {response.status_code} - {response.text}"
                )
                return None

    except Exception as e:
        logger.error(f"LemonSqueezy API 调用失败: {e}")
        return None


def verify_webhook_signature(payload: bytes, signature: str) -> bool:
    """
    验证 LemonSqueezy Webhook 签名

    Args:
        payload: 原始请求体 bytes
        signature: X-Signature header 值

    Returns:
        签名是否有效
    """
    if not settings.lemonsqueezy_webhook_secret:
        logger.warning("LemonSqueezy Webhook Secret 未配置, 跳过签名验证")
        return True  # 开发环境跳过

    expected = hmac.HMAC(
        settings.lemonsqueezy_webhook_secret.encode(),
        payload,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(expected, signature)


def parse_order_webhook(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    解析 LemonSqueezy order_created webhook 数据

    Returns:
        包含 order_id, email, amount, custom_data 的字典
    """
    try:
        meta = data.get("meta", {})
        event_name = meta.get("event_name", "")

        if event_name != "order_created":
            return None

        attrs = data.get("data", {}).get("attributes", {})
        order_id = str(data.get("data", {}).get("id", ""))

        # 金额从 cents 转 SGD
        total = attrs.get("total", 0)
        sgd_amount = total / 100.0 if total else 0

        user_email = attrs.get("user_email", "")
        custom_data = meta.get("custom_data", {})

        return {
            "order_id": order_id,
            "user_email": user_email,
            "sgd_amount": sgd_amount,
            "status": attrs.get("status", ""),
            "custom_data": custom_data,
        }

    except Exception as e:
        logger.error(f"解析 Webhook 数据失败: {e}")
        return None
