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

from app.api.common import api_delete, api_get, api_patch, api_post
from app.core import Config
from app.models import Webhook as WebhookConfig
from app.models.common_contract import (
    IndexOrderPatch,
    OutBase,
    project_model,
    project_model_list,
    project_model_map,
)
from app.models.setting_contract import (
    GlobalConfigPatch,
    GlobalConfigRead,
    SettingGetOut,
    WebhookCreateOut,
    WebhookDetailOut,
    WebhookGetOut,
    WebhookIndexItem,
    WebhookPatch,
    WebhookRead,
)
from app.services import Notify

router = APIRouter(prefix="/api/setting", tags=["全局设置"])

WebhookIdPath = Annotated[str, Path(description="Webhook ID")]


async def _build_setting_out() -> SettingGetOut:
    return SettingGetOut(
        data=project_model(GlobalConfigRead, await Config.get_setting())
    )


async def _update_setting_config(data: GlobalConfigPatch) -> OutBase:
    await Config.update_setting(data.model_dump(exclude_unset=True))
    return OutBase()


async def _build_webhook_collection_out() -> WebhookGetOut:
    index, data = await Config.get_webhook(None, None, None)
    return WebhookGetOut(
        index=project_model_list(WebhookIndexItem, index),
        data=project_model_map(WebhookRead, data),
    )


async def _build_webhook_detail_out(webhook_id: str) -> WebhookDetailOut:
    _, data = await Config.get_webhook(None, None, webhook_id)
    projected = project_model_map(WebhookRead, data)
    return WebhookDetailOut(data=projected[webhook_id])


async def _build_webhook_create_out() -> WebhookCreateOut:
    uid, config = await Config.add_webhook(None, None)
    return WebhookCreateOut(
        id=str(uid),
        data=project_model(WebhookRead, await config.toDict()),
    )


async def _update_webhook_config(webhook_id: str, data: WebhookPatch) -> OutBase:
    await Config.update_webhook(
        None, None, webhook_id, data.model_dump(exclude_unset=True)
    )
    return OutBase()


async def _delete_webhook_config(webhook_id: str) -> OutBase:
    await Config.del_webhook(None, None, webhook_id)
    return OutBase()


async def _test_webhook_config(data: WebhookPatch) -> OutBase:
    webhook_config = WebhookConfig()
    await webhook_config.load(data.model_dump(exclude_unset=True))
    await Notify.WebhookPush(
        "AUTO-MAS Webhook测试",
        "这是一条测试消息，如果您收到此消息，说明Webhook配置正确！",
        webhook_config,
    )
    return OutBase()


@api_get(
    router,
    "",
    model_cls=SettingGetOut,
    data=GlobalConfigRead(),
    route_kwargs={
        "tags": ["Get"],
        "summary": "查询全局配置",
        "response_model": SettingGetOut,
        "status_code": 200,
    },
)
async def get_setting() -> SettingGetOut:
    return await _build_setting_out()


@api_patch(
    router,
    "",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Update"],
        "summary": "更新全局配置",
        "response_model": OutBase,
        "status_code": 200,
    },
)
async def update_setting(data: GlobalConfigPatch = Body(...)) -> OutBase:
    return await _update_setting_config(data)


@api_post(
    router,
    "/actions/test-notify",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Action"],
        "summary": "测试通知",
        "response_model": OutBase,
        "status_code": 200,
    },
)
async def test_notify() -> OutBase:
    await Notify.send_test_notification()
    return OutBase()


@api_get(
    router,
    "/webhooks",
    model_cls=WebhookGetOut,
    index=[],
    data={},
    route_kwargs={
        "tags": ["Get"],
        "summary": "查询全部全局 Webhook 配置",
        "response_model": WebhookGetOut,
        "status_code": 200,
    },
)
async def list_webhooks() -> WebhookGetOut:
    return await _build_webhook_collection_out()


@api_post(
    router,
    "/webhooks",
    model_cls=WebhookCreateOut,
    id="",
    data=WebhookRead(),
    route_kwargs={
        "tags": ["Add"],
        "summary": "创建全局 Webhook 配置",
        "response_model": WebhookCreateOut,
        "status_code": 200,
    },
)
async def create_webhook() -> WebhookCreateOut:
    return await _build_webhook_create_out()


@api_patch(
    router,
    "/webhooks/order",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Update"],
        "summary": "重新排序全局 Webhook",
        "response_model": OutBase,
        "status_code": 200,
    },
)
async def reorder_webhooks(body: IndexOrderPatch = Body(...)) -> OutBase:
    await Config.reorder_webhook(None, None, body.index_list)
    return OutBase()


@api_post(
    router,
    "/webhooks/test",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Action"],
        "summary": "测试指定 Webhook 配置",
        "response_model": OutBase,
        "status_code": 200,
    },
)
async def test_webhook(data: WebhookPatch = Body(...)) -> OutBase:
    return await _test_webhook_config(data)


@api_get(
    router,
    "/webhooks/{webhook_id}",
    model_cls=WebhookDetailOut,
    data=WebhookRead(),
    route_kwargs={
        "tags": ["Get"],
        "summary": "查询单个全局 Webhook 配置",
        "response_model": WebhookDetailOut,
        "status_code": 200,
    },
)
async def get_webhook(webhook_id: WebhookIdPath) -> WebhookDetailOut:
    return await _build_webhook_detail_out(webhook_id)


@api_patch(
    router,
    "/webhooks/{webhook_id}",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Update"],
        "summary": "更新全局 Webhook 配置",
        "response_model": OutBase,
        "status_code": 200,
    },
)
async def update_webhook(
    webhook_id: WebhookIdPath, data: WebhookPatch = Body(...)
) -> OutBase:
    return await _update_webhook_config(webhook_id, data)


@api_delete(
    router,
    "/webhooks/{webhook_id}",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Delete"],
        "summary": "删除全局 Webhook 配置",
        "response_model": OutBase,
        "status_code": 200,
    },
)
async def delete_webhook(webhook_id: WebhookIdPath) -> OutBase:
    return await _delete_webhook_config(webhook_id)
