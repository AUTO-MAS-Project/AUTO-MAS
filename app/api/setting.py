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


from fastapi import APIRouter, Body
from app.core import Config
from app.services import Notify
from app.models.common_contract import (
    OutBase,
    project_model,
    project_model_list,
    project_model_map,
)
from app.models.setting_contract import (
    GlobalConfigRead,
    SettingGetOut,
    SettingUpdateIn,
    WebhookCreateOut,
    WebhookDeleteIn,
    WebhookGetIn,
    WebhookGetOut,
    WebhookIndexItem,
    WebhookRead,
    WebhookReorderIn,
    WebhookTestIn,
    WebhookUpdateIn,
)
from app.models import Webhook as WebhookConfig
from app.api.common import error_out

router = APIRouter(prefix="/api/setting", tags=["全局设置"])


@router.post(
    "/get",
    tags=["Get"],
    summary="查询配置",
    response_model=SettingGetOut,
    status_code=200,
)
async def get_scripts() -> SettingGetOut:
    """查询配置"""

    try:
        data = await Config.get_setting()
    except Exception as e:
        return error_out(SettingGetOut, e, data=GlobalConfigRead())
    return SettingGetOut(data=project_model(GlobalConfigRead, data))


@router.post(
    "/update",
    tags=["Update"],
    summary="更新配置",
    response_model=OutBase,
    status_code=200,
)
async def update_script(script: SettingUpdateIn = Body(...)) -> OutBase:
    """更新配置"""

    try:
        data = script.data.model_dump(exclude_unset=True)
        await Config.update_setting(data)

    except Exception as e:
        return error_out(OutBase, e)
    return OutBase()


@router.post(
    "/test_notify",
    tags=["Action"],
    summary="测试通知",
    response_model=OutBase,
    status_code=200,
)
async def test_notify() -> OutBase:
    """测试通知"""

    try:
        await Notify.send_test_notification()
    except Exception as e:
        return error_out(OutBase, e)
    return OutBase()


@router.post(
    "/webhook/get",
    tags=["Get"],
    summary="查询 webhook 配置",
    response_model=WebhookGetOut,
    status_code=200,
)
async def get_webhook(webhook: WebhookGetIn = Body(...)) -> WebhookGetOut:
    try:
        index, data = await Config.get_webhook(None, None, webhook.webhookId)
        index = project_model_list(WebhookIndexItem, index)
        data = project_model_map(WebhookRead, data)
    except Exception as e:
        return error_out(WebhookGetOut, e, index=[], data={})
    return WebhookGetOut(index=index, data=data)


@router.post(
    "/webhook/add",
    tags=["Add"],
    summary="添加webhook项",
    response_model=WebhookCreateOut,
    status_code=200,
)
async def add_webhook() -> WebhookCreateOut:
    try:
        uid, config = await Config.add_webhook(None, None)
        data = project_model(WebhookRead, await config.toDict())
    except Exception as e:
        return error_out(WebhookCreateOut, e, webhookId="", data=WebhookRead())
    return WebhookCreateOut(webhookId=str(uid), data=data)


@router.post(
    "/webhook/update",
    tags=["Update"],
    summary="更新webhook项",
    response_model=OutBase,
    status_code=200,
)
async def update_webhook(webhook: WebhookUpdateIn = Body(...)) -> OutBase:
    try:
        await Config.update_webhook(
            None, None, webhook.webhookId, webhook.data.model_dump(exclude_unset=True)
        )
    except Exception as e:
        return error_out(OutBase, e)
    return OutBase()


@router.post(
    "/webhook/delete",
    tags=["Delete"],
    summary="删除webhook项",
    response_model=OutBase,
    status_code=200,
)
async def delete_webhook(webhook: WebhookDeleteIn = Body(...)) -> OutBase:
    try:
        await Config.del_webhook(None, None, webhook.webhookId)
    except Exception as e:
        return error_out(OutBase, e)
    return OutBase()


@router.post(
    "/webhook/order",
    tags=["Update"],
    summary="重新排序webhook项",
    response_model=OutBase,
    status_code=200,
)
async def reorder_webhook(webhook: WebhookReorderIn = Body(...)) -> OutBase:
    try:
        await Config.reorder_webhook(None, None, webhook.indexList)
    except Exception as e:
        return error_out(OutBase, e)
    return OutBase()


@router.post(
    "/webhook/test",
    tags=["Action"],
    summary="测试Webhook配置",
    response_model=OutBase,
    status_code=200,
)
async def test_webhook(webhook: WebhookTestIn = Body(...)) -> OutBase:
    """测试自定义Webhook"""

    try:
        webhook_config = WebhookConfig()
        await webhook_config.load(webhook.data.model_dump(exclude_unset=True))
        await Notify.WebhookPush(
            "AUTO-MAS Webhook测试",
            "这是一条测试消息，如果您收到此消息，说明Webhook配置正确！",
            webhook_config,
        )
    except Exception as e:
        return error_out(OutBase, e, message=f"Webhook测试失败: {str(e)}")
    return OutBase()
