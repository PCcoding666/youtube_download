"""
API Key 管理路由
用户可以生成、查看、删除 API Key，用于外部 Skill 调用
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
import logging

from app.database import get_database
from app.api.auth_routes import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/apikeys", tags=["api-keys"])


# ============================================================================
# 请求/响应模型
# ============================================================================


class GenerateKeyRequest(BaseModel):
    """生成 API Key 请求"""
    name: Optional[str] = Field(None, max_length=100, description="Key 名称")


class GenerateKeyResponse(BaseModel):
    """生成 API Key 响应 - 仅此一次返回完整 Key"""
    success: bool
    api_key: Optional[str] = None  # 完整 Key, 仅此一次
    key_prefix: Optional[str] = None
    name: str = ""
    message: str = ""


class UpdateKeyRequest(BaseModel):
    """更新 API Key 请求"""
    name: Optional[str] = Field(None, max_length=100)
    is_active: Optional[bool] = None


# ============================================================================
# API 端点
# ============================================================================


@router.post("/generate", response_model=GenerateKeyResponse)
async def generate_api_key(
    request: GenerateKeyRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    生成新的 API Key

    返回完整的 API Key（仅此一次，请妥善保存）
    Key 格式: sk-yt-{random}
    """
    db = get_database()

    # 限制每个用户最多 5 个 Key
    existing_keys = db.list_api_keys(current_user["id"])
    if len(existing_keys) >= 5:
        raise HTTPException(
            status_code=400,
            detail="每个用户最多 5 个 API Key，请删除不需要的 Key 后再试"
        )

    name = request.name or "Default"
    raw_key = db.generate_api_key(user_id=current_user["id"], name=name)

    if not raw_key:
        raise HTTPException(status_code=500, detail="生成 API Key 失败")

    return GenerateKeyResponse(
        success=True,
        api_key=raw_key,
        key_prefix=raw_key[:12],
        name=name,
        message="API Key 生成成功！请立即复制保存，此 Key 不会再次显示。",
    )


@router.get("/list")
async def list_api_keys(current_user: dict = Depends(get_current_user)):
    """
    列出用户所有 API Key

    仅显示 Key 前缀，不显示完整 Key
    """
    db = get_database()
    keys = db.list_api_keys(current_user["id"])

    return {
        "keys": keys,
        "count": len(keys),
        "max_keys": 5,
    }


@router.delete("/{key_id}")
async def delete_api_key(
    key_id: int,
    current_user: dict = Depends(get_current_user),
):
    """
    删除 API Key
    """
    db = get_database()
    success = db.delete_api_key(key_id=key_id, user_id=current_user["id"])

    if not success:
        raise HTTPException(status_code=404, detail="API Key 不存在")

    return {"success": True, "message": "API Key 已删除"}


@router.put("/{key_id}")
async def update_api_key(
    key_id: int,
    request: UpdateKeyRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    更新 API Key 名称或状态
    """
    db = get_database()
    success = db.update_api_key(
        key_id=key_id,
        user_id=current_user["id"],
        name=request.name,
        is_active=request.is_active,
    )

    if not success:
        raise HTTPException(status_code=404, detail="API Key 不存在")

    return {"success": True, "message": "API Key 已更新"}
