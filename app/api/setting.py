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


from typing import Annotated

from fastapi import APIRouter, Body, Path


from app.core import Config
from app.models import Webhook as WebhookConfig
from app.contracts.common_contract import (
    IndexOrderPatch,
    OutBase,
    dump_writable_data,
    project_model,
    project_model_list,
    project_model_map,
)
from app.contracts.setting_contract import (
    GlobalConfigRead,
    SettingGetOut,
    WebhookCreateOut,
    WebhookDetailOut,
    WebhookGetOut,
    WebhookIndexItem,
    WebhookRead,
)
from app.services import Notify

router = APIRouter(prefix="/api/setting", tags=["全局设置"])

WebhookIdPath = Annotated[str, Path(description="Webhook ID")]


@router.get(
    "",
    tags=["Get"],
    summary="查询全局配置",
    response_model=SettingGetOut,
)
async def get_setting() -> SettingGetOut:
    return SettingGetOut(
        data=project_model(GlobalConfigRead, await Config.get_setting())
    )


@router.patch(
    "",
    tags=["Update"],
    summary="更新全局配置",
    response_model=OutBase,
)
async def update_setting(data: GlobalConfigRead = Body(...)) -> OutBase:
    await Config.update_setting(dump_writable_data(data))
    return OutBase()


@router.post(
    "/actions/test-notify",
    tags=["Action"],
    summary="测试通知",
    response_model=OutBase,
)
async def test_notify() -> OutBase:
    await Notify.send_test_notification()
    return OutBase()


@router.get(
    "/webhooks",
    tags=["Get"],
    summary="查询全部全局 Webhook 配置",
    response_model=WebhookGetOut,
)
async def list_webhooks() -> WebhookGetOut:
    index, data = await Config.get_webhook(None, None, None)
    return WebhookGetOut(
        index=project_model_list(WebhookIndexItem, index),
        data=project_model_map(WebhookRead, data),
    )


@router.post(
    "/webhooks",
    tags=["Add"],
    summary="创建全局 Webhook 配置",
    response_model=WebhookCreateOut,
)
async def create_webhook() -> WebhookCreateOut:
    uid, config = await Config.add_webhook(None, None)
    return WebhookCreateOut(
        id=str(uid),
        data=project_model(WebhookRead, await config.toDict()),
    )


@router.patch(
    "/webhooks/order",
    tags=["Update"],
    summary="重新排序全局 Webhook",
    response_model=OutBase,
)
async def reorder_webhooks(body: IndexOrderPatch = Body(...)) -> OutBase:
    await Config.reorder_webhook(None, None, body.index_list)
    return OutBase()


@router.post(
    "/webhooks/test",
    tags=["Action"],
    summary="测试指定 Webhook 配置",
    response_model=OutBase,
)
async def test_webhook(data: WebhookRead = Body(...)) -> OutBase:
    webhook_config = WebhookConfig()
    await webhook_config.load(dump_writable_data(data))
    await Notify.WebhookPush(
        "AUTO-MAS Webhook测试",
        "这是一条测试消息，如果您收到此消息，说明Webhook配置正确！",
        webhook_config,
    )
    return OutBase()


@router.get(
    "/webhooks/{webhook_id}",
    tags=["Get"],
    summary="查询单个全局 Webhook 配置",
    response_model=WebhookDetailOut,
)
async def get_webhook(webhook_id: WebhookIdPath) -> WebhookDetailOut:
    _, data = await Config.get_webhook(None, None, webhook_id)
    projected = project_model_map(WebhookRead, data)
    return WebhookDetailOut(data=projected[webhook_id])


@router.patch(
    "/webhooks/{webhook_id}",
    tags=["Update"],
    summary="更新全局 Webhook 配置",
    response_model=OutBase,
)
async def update_webhook(
    webhook_id: WebhookIdPath, data: WebhookRead = Body(...)
) -> OutBase:
    await Config.update_webhook(None, None, webhook_id, dump_writable_data(data))
    return OutBase()


@router.delete(
    "/webhooks/{webhook_id}",
    tags=["Delete"],
    summary="删除全局 Webhook 配置",
    response_model=OutBase,
)
async def delete_webhook(webhook_id: WebhookIdPath) -> OutBase:
    await Config.del_webhook(None, None, webhook_id)
    return OutBase()
