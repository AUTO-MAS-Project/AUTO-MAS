#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""全局设置 API：请求/响应字段基于 ``Setting`` / ``Webhook``，直接操作 ``Config.setting``。"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Body
from pydantic import BaseModel, Field

from app.config import CollectionOrderItem
from app.config.errors import ConfigAggregateError
from app.core import Config
from app.models.config import Setting, Webhook
from app.models.schema import OutBase

router = APIRouter(prefix="/api/setting", tags=["全局设置"])


# ==================== 字段（基于 ConfigEntry） ====================


class SettingGetOut(OutBase):
    data: Setting = Field(default_factory=Setting, description="全局设置")


class SettingUpdateIn(BaseModel):
    data: Setting = Field(..., description="全局设置补丁（Wire 形状）")


class WebhookGetIn(BaseModel):
    webhookId: Optional[str] = Field(
        default=None, description="Webhook ID；缺省返回全部"
    )


class WebhookGetOut(OutBase):
    order: list[CollectionOrderItem] = Field(
        default_factory=list, description="Webhook 顺序"
    )
    data: dict[str, Webhook] = Field(
        default_factory=dict, description="Webhook 数据，key 为 uid"
    )


class WebhookCreateOut(OutBase):
    webhookId: str = Field(default="", description="新 Webhook ID")
    data: Webhook = Field(default_factory=Webhook, description="Webhook 配置")


class WebhookUpdateIn(BaseModel):
    webhookId: str = Field(..., description="Webhook ID")
    data: Webhook = Field(..., description="Webhook 补丁（Wire 形状）")


class WebhookDeleteIn(BaseModel):
    webhookId: str = Field(..., description="Webhook ID")


class WebhookReorderIn(BaseModel):
    indexList: list[str] = Field(..., description="按新顺序排列的 Webhook UID 列表")


class WebhookTestIn(BaseModel):
    data: Webhook = Field(..., description="待测试的 Webhook 配置")


# ==================== 全局设置 ====================


@router.post(
    "/get",
    tags=["Get"],
    summary="查询配置",
    response_model=SettingGetOut,
    status_code=200,
)
async def get_setting() -> SettingGetOut:
    """查询全局设置。"""
    try:
        return SettingGetOut(data=Config.setting)
    except Exception as e:
        return SettingGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            data=Setting(),
        )


@router.post(
    "/update",
    tags=["Update"],
    summary="更新配置",
    response_model=OutBase,
    status_code=200,
)
async def update_setting(body: SettingUpdateIn = Body(...)) -> OutBase:
    """更新全局设置（仅 Group 字段；``custom_webhooks`` 走独立端点）。"""
    try:
        await Config.setting.update(body.data)
    except ConfigAggregateError as e:
        return OutBase(code=500, status="error", message=str(e))
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/test_notify",
    tags=["Action"],
    summary="测试通知",
    response_model=OutBase,
    status_code=200,
)
async def test_notify() -> OutBase:
    """测试通知：置位 ``Setting.notify.test`` 触发器。"""
    try:
        Config.setting.notify.test = True
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


# ==================== 自定义 Webhook ====================


@router.post(
    "/webhook/get",
    tags=["Get"],
    summary="查询 webhook 配置",
    response_model=WebhookGetOut,
    status_code=200,
)
async def get_webhook(body: WebhookGetIn = Body(...)) -> WebhookGetOut:
    try:
        col = Config.setting.custom_webhooks
        uids = [UUID(body.webhookId)] if body.webhookId else list(col.keys())
        return WebhookGetOut(
            order=[
                CollectionOrderItem(uid=uid, type=type(col[uid]).__name__)
                for uid in uids
            ],
            data={str(uid): col[uid] for uid in uids},
        )
    except Exception as e:
        return WebhookGetOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            order=[],
            data={},
        )


@router.post(
    "/webhook/add",
    tags=["Add"],
    summary="添加webhook项",
    response_model=WebhookCreateOut,
    status_code=200,
)
async def add_webhook() -> WebhookCreateOut:
    try:
        col = Config.setting.custom_webhooks
        uid = col.add(Webhook)
        await col.commit()
        return WebhookCreateOut(webhookId=str(uid), data=col[uid])
    except Exception as e:
        return WebhookCreateOut(
            code=500,
            status="error",
            message=f"{type(e).__name__}: {str(e)}",
            webhookId="",
            data=Webhook(),
        )


@router.post(
    "/webhook/update",
    tags=["Update"],
    summary="更新webhook项",
    response_model=OutBase,
    status_code=200,
)
async def update_webhook(body: WebhookUpdateIn = Body(...)) -> OutBase:
    try:
        await Config.setting.custom_webhooks[UUID(body.webhookId)].update(body.data)
    except ConfigAggregateError as e:
        return OutBase(code=500, status="error", message=str(e))
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/webhook/delete",
    tags=["Delete"],
    summary="删除webhook项",
    response_model=OutBase,
    status_code=200,
)
async def delete_webhook(body: WebhookDeleteIn = Body(...)) -> OutBase:
    try:
        col = Config.setting.custom_webhooks
        col.remove(body.webhookId)
        await col.commit()
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/webhook/order",
    tags=["Update"],
    summary="重新排序webhook项",
    response_model=OutBase,
    status_code=200,
)
async def reorder_webhook(body: WebhookReorderIn = Body(...)) -> OutBase:
    try:
        col = Config.setting.custom_webhooks
        col.set_order(list(map(UUID, body.indexList)))
        await col.commit()
    except Exception as e:
        return OutBase(
            code=500, status="error", message=f"{type(e).__name__}: {str(e)}"
        )
    return OutBase()


@router.post(
    "/webhook/test",
    tags=["Action"],
    summary="测试Webhook配置",
    response_model=OutBase,
    status_code=200,
)
async def test_webhook(body: WebhookTestIn = Body(...)) -> OutBase:
    """测试自定义 Webhook：激活 Body 冷态并置位 ``info.test`` 触发器。"""
    try:
        webhook = body.data
        await webhook.activate()
        webhook.info.test = True
    except Exception as e:
        return OutBase(code=500, status="error", message=f"Webhook测试失败: {str(e)}")
    return OutBase()
