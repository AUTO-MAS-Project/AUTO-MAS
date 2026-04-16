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


import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Path
from pydantic import TypeAdapter

from app.core import Config
from app.contracts.common_contract import (
    ComboBoxItem,
    ComboBoxOut,
    IndexOrderPatch,
    OutBase,
    dump_writable_data,
    project_model,
    project_model_list,
    project_model_map,
)
from app.contracts.scripts_contract import (
    ScriptPatchBody,
    InfrastructureImportBody,
    ScriptCreateIn,
    ScriptCreateOut,
    ScriptDetailOut,
    ScriptFileBody,
    ScriptGetOut,
    ScriptIndexItem,
    ScriptUploadBody,
    ScriptUrlBody,
    UserPatchBody,
    UserCreateOut,
    UserDetailOut,
    UserGetOut,
    UserIndexItem,
    project_script_model,
    project_script_model_map,
    project_user_model,
    project_user_model_map,
    script_contract_type_from_runtime,
    user_contract_type_from_script,
    dump_script_patch_data,
    dump_user_patch_data,
)
from app.contracts.setting_contract import (
    WebhookCreateOut,
    WebhookDetailOut,
    WebhookGetOut,
    WebhookIndexItem,
    WebhookRead,
)

COMBOBOX_ITEMS_ADAPTER: TypeAdapter[list[ComboBoxItem]] = TypeAdapter(
    list[ComboBoxItem]
)

router = APIRouter(prefix="/api/scripts", tags=["脚本管理"])

ScriptIdPath = Annotated[str, Path(description="脚本 ID")]
UserIdPath = Annotated[str, Path(description="用户 ID")]
WebhookIdPath = Annotated[str, Path(description="Webhook ID")]


@router.get(
    "",
    tags=["Get"],
    summary="查询全部脚本",
    response_model=ScriptGetOut,
)
async def list_scripts() -> ScriptGetOut:
    index, data = await Config.get_script(None)
    script_index = project_model_list(ScriptIndexItem, index)
    return ScriptGetOut(
        index=script_index, data=project_script_model_map(script_index, data)
    )


@router.post(
    "",
    tags=["Add"],
    summary="创建脚本",
    response_model=ScriptCreateOut,
)
async def create_script(script: ScriptCreateIn = Body(...)) -> ScriptCreateOut:
    uid, config = await Config.add_script(script.type, script.copyFromId)
    data = project_script_model(
        script_contract_type_from_runtime(type(config).__name__),
        await config.toDict(),
    )
    return ScriptCreateOut(id=str(uid), data=data)


@router.patch(
    "/order",
    tags=["Update"],
    summary="重新排序脚本",
    response_model=OutBase,
)
async def reorder_scripts(body: IndexOrderPatch = Body(...)) -> OutBase:
    await Config.reorder_script(body.index_list)
    return OutBase()


@router.get(
    "/{script_id}",
    tags=["Get"],
    summary="查询单个脚本",
    response_model=ScriptDetailOut,
)
async def get_script(script_id: ScriptIdPath) -> ScriptDetailOut:
    index, data = await Config.get_script(script_id)
    script_index = project_model_list(ScriptIndexItem, index)
    projected = project_script_model_map(script_index, data)
    return ScriptDetailOut(data=projected[script_id])


@router.patch(
    "/{script_id}",
    tags=["Update"],
    summary="更新脚本配置",
    response_model=OutBase,
)
async def update_script(
    script_id: ScriptIdPath,
    body: ScriptPatchBody = Body(...),
) -> OutBase:
    script_type = script_contract_type_from_runtime(
        type(Config.ScriptConfig[uuid.UUID(script_id)]).__name__
    )
    await Config.update_script(
        script_id, dump_script_patch_data(script_type, body.data)
    )
    return OutBase()


@router.delete(
    "/{script_id}",
    tags=["Delete"],
    summary="删除脚本",
    response_model=OutBase,
)
async def delete_script(script_id: ScriptIdPath) -> OutBase:
    await Config.del_script(script_id)
    return OutBase()


@router.post(
    "/{script_id}/actions/import-file",
    tags=["Action"],
    summary="从文件导入脚本配置",
    response_model=OutBase,
)
async def import_script_from_file(
    script_id: ScriptIdPath, body: ScriptFileBody = Body(...)
) -> OutBase:
    await Config.import_script_from_file(script_id, body.path)
    return OutBase()


@router.post(
    "/{script_id}/actions/export-file",
    tags=["Action"],
    summary="导出脚本配置到文件",
    response_model=OutBase,
)
async def export_script_to_file(
    script_id: ScriptIdPath, body: ScriptFileBody = Body(...)
) -> OutBase:
    await Config.export_script_to_file(script_id, body.path)
    return OutBase()


@router.post(
    "/{script_id}/actions/import-web",
    tags=["Action"],
    summary="从网络导入脚本配置",
    response_model=OutBase,
)
async def import_script_from_web(
    script_id: ScriptIdPath, body: ScriptUrlBody = Body(...)
) -> OutBase:
    await Config.import_script_from_web(script_id, body.url)
    return OutBase()


@router.post(
    "/{script_id}/actions/upload-web",
    tags=["Action"],
    summary="上传脚本配置到网络",
    response_model=OutBase,
)
async def upload_script_to_web(
    script_id: ScriptIdPath, body: ScriptUploadBody = Body(...)
) -> OutBase:
    await Config.upload_script_to_web(
        script_id, body.config_name, body.author, body.description
    )
    return OutBase()


@router.get(
    "/{script_id}/users",
    tags=["Get"],
    summary="查询脚本下的全部用户",
    response_model=UserGetOut,
)
async def list_users(script_id: ScriptIdPath) -> UserGetOut:
    index, data = await Config.get_user(script_id, None)
    user_index = project_model_list(UserIndexItem, index)
    return UserGetOut(index=user_index, data=project_user_model_map(user_index, data))


@router.post(
    "/{script_id}/users",
    tags=["Add"],
    summary="创建用户",
    response_model=UserCreateOut,
)
async def create_user(script_id: ScriptIdPath) -> UserCreateOut:
    uid, config = await Config.add_user(script_id)
    script_type = script_contract_type_from_runtime(
        type(Config.ScriptConfig[uuid.UUID(script_id)]).__name__
    )
    user_type = user_contract_type_from_script(script_type)
    data = project_user_model(user_type, await config.toDict())
    return UserCreateOut(id=str(uid), data=data)


@router.patch(
    "/{script_id}/users/order",
    tags=["Update"],
    summary="重新排序用户",
    response_model=OutBase,
)
async def reorder_users(
    script_id: ScriptIdPath, body: IndexOrderPatch = Body(...)
) -> OutBase:
    await Config.reorder_user(script_id, body.index_list)
    return OutBase()


@router.get(
    "/{script_id}/users/{user_id}",
    tags=["Get"],
    summary="查询单个用户",
    response_model=UserDetailOut,
)
async def get_user(script_id: ScriptIdPath, user_id: UserIdPath) -> UserDetailOut:
    index, data = await Config.get_user(script_id, user_id)
    user_index = project_model_list(UserIndexItem, index)
    projected = project_user_model_map(user_index, data)
    return UserDetailOut(data=projected[user_id])


@router.patch(
    "/{script_id}/users/{user_id}",
    tags=["Update"],
    summary="更新用户配置",
    response_model=OutBase,
)
async def update_user(
    script_id: ScriptIdPath,
    user_id: UserIdPath,
    body: UserPatchBody = Body(...),
) -> OutBase:
    script_type = script_contract_type_from_runtime(
        type(Config.ScriptConfig[uuid.UUID(script_id)]).__name__
    )
    user_type = user_contract_type_from_script(script_type)
    await Config.update_user(
        script_id, user_id, dump_user_patch_data(user_type, body.data)
    )
    return OutBase()


@router.delete(
    "/{script_id}/users/{user_id}",
    tags=["Delete"],
    summary="删除用户",
    response_model=OutBase,
)
async def delete_user(script_id: ScriptIdPath, user_id: UserIdPath) -> OutBase:
    await Config.del_user(script_id, user_id)
    return OutBase()


@router.post(
    "/{script_id}/users/{user_id}/actions/import-infrastructure",
    tags=["Action"],
    summary="导入基建配置文件",
    response_model=OutBase,
)
async def import_infrastructure(
    script_id: ScriptIdPath,
    user_id: UserIdPath,
    body: InfrastructureImportBody = Body(...),
) -> OutBase:
    await Config.set_infrastructure(script_id, user_id, body.path)
    return OutBase()


@router.get(
    "/{script_id}/users/{user_id}/infrastructure-options",
    tags=["Get"],
    summary="用户自定义基建排班可选项",
    response_model=ComboBoxOut,
)
async def get_user_infrastructure_options(
    script_id: ScriptIdPath, user_id: UserIdPath
) -> ComboBoxOut:
    raw_data = await Config.get_user_combox_infrastructure(script_id, user_id)
    data = COMBOBOX_ITEMS_ADAPTER.validate_python(raw_data or [])
    return ComboBoxOut(data=data)


@router.get(
    "/{script_id}/users/{user_id}/webhooks",
    tags=["Get"],
    summary="查询用户下的全部 Webhook",
    response_model=WebhookGetOut,
)
async def list_user_webhooks(
    script_id: ScriptIdPath, user_id: UserIdPath
) -> WebhookGetOut:
    index, data = await Config.get_webhook(script_id, user_id, None)
    return WebhookGetOut(
        index=project_model_list(WebhookIndexItem, index),
        data=project_model_map(WebhookRead, data),
    )


@router.post(
    "/{script_id}/users/{user_id}/webhooks",
    tags=["Add"],
    summary="创建用户 Webhook",
    response_model=WebhookCreateOut,
)
async def create_user_webhook(
    script_id: ScriptIdPath, user_id: UserIdPath
) -> WebhookCreateOut:
    uid, config = await Config.add_webhook(script_id, user_id)
    return WebhookCreateOut(
        id=str(uid),
        data=project_model(WebhookRead, await config.toDict()),
    )


@router.patch(
    "/{script_id}/users/{user_id}/webhooks/order",
    tags=["Update"],
    summary="重新排序用户 Webhook",
    response_model=OutBase,
)
async def reorder_user_webhooks(
    script_id: ScriptIdPath,
    user_id: UserIdPath,
    body: IndexOrderPatch = Body(...),
) -> OutBase:
    await Config.reorder_webhook(script_id, user_id, body.index_list)
    return OutBase()


@router.get(
    "/{script_id}/users/{user_id}/webhooks/{webhook_id}",
    tags=["Get"],
    summary="查询单个用户 Webhook",
    response_model=WebhookDetailOut,
)
async def get_user_webhook(
    script_id: ScriptIdPath,
    user_id: UserIdPath,
    webhook_id: WebhookIdPath,
) -> WebhookDetailOut:
    _, data = await Config.get_webhook(script_id, user_id, webhook_id)
    projected = project_model_map(WebhookRead, data)
    return WebhookDetailOut(data=projected[webhook_id])


@router.patch(
    "/{script_id}/users/{user_id}/webhooks/{webhook_id}",
    tags=["Update"],
    summary="更新用户 Webhook",
    response_model=OutBase,
)
async def update_user_webhook(
    script_id: ScriptIdPath,
    user_id: UserIdPath,
    webhook_id: WebhookIdPath,
    data: WebhookRead = Body(...),
) -> OutBase:
    await Config.update_webhook(
        script_id,
        user_id,
        webhook_id,
        dump_writable_data(data),
    )
    return OutBase()


@router.delete(
    "/{script_id}/users/{user_id}/webhooks/{webhook_id}",
    tags=["Delete"],
    summary="删除用户 Webhook",
    response_model=OutBase,
)
async def delete_user_webhook(
    script_id: ScriptIdPath,
    user_id: UserIdPath,
    webhook_id: WebhookIdPath,
) -> OutBase:
    await Config.del_webhook(script_id, user_id, webhook_id)
    return OutBase()
