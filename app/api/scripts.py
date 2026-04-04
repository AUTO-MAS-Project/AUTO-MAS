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

from app.api.common import api_delete, api_get, api_patch, api_post, error_out
from app.core import Config
from app.models.common_contract import (
    ComboBoxItem,
    ComboBoxOut,
    IndexOrderPatch,
    OutBase,
    project_model,
    project_model_list,
    project_model_map,
)
from app.models.scripts_contract import (
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
    script_contract_type_from_create,
    script_contract_type_from_runtime,
    user_contract_type_from_script,
    dump_script_patch_data,
    dump_user_patch_data,
)
from app.models.setting_contract import (
    WebhookCreateOut,
    WebhookDetailOut,
    WebhookGetOut,
    WebhookIndexItem,
    WebhookPatch,
    WebhookRead,
)

COMBOBOX_ITEMS_ADAPTER: TypeAdapter[list[ComboBoxItem]] = TypeAdapter(
    list[ComboBoxItem]
)

router = APIRouter(prefix="/api/scripts", tags=["脚本管理"])

ScriptIdPath = Annotated[str, Path(description="脚本 ID")]
UserIdPath = Annotated[str, Path(description="用户 ID")]
WebhookIdPath = Annotated[str, Path(description="Webhook ID")]


async def _build_script_collection_out() -> ScriptGetOut:
    index, data = await Config.get_script(None)
    script_index = project_model_list(ScriptIndexItem, index)
    return ScriptGetOut(
        index=script_index, data=project_script_model_map(script_index, data)
    )


async def _build_script_detail_out(script_id: str) -> ScriptDetailOut:
    index, data = await Config.get_script(script_id)
    script_index = project_model_list(ScriptIndexItem, index)
    projected = project_script_model_map(script_index, data)
    return ScriptDetailOut(data=projected[script_id])


async def _build_user_collection_out(script_id: str) -> UserGetOut:
    index, data = await Config.get_user(script_id, None)
    user_index = project_model_list(UserIndexItem, index)
    return UserGetOut(index=user_index, data=project_user_model_map(user_index, data))


async def _build_user_detail_out(script_id: str, user_id: str) -> UserDetailOut:
    index, data = await Config.get_user(script_id, user_id)
    user_index = project_model_list(UserIndexItem, index)
    projected = project_user_model_map(user_index, data)
    return UserDetailOut(data=projected[user_id])


async def _build_webhook_collection_out(script_id: str, user_id: str) -> WebhookGetOut:
    index, data = await Config.get_webhook(script_id, user_id, None)
    return WebhookGetOut(
        index=project_model_list(WebhookIndexItem, index),
        data=project_model_map(WebhookRead, data),
    )


async def _build_webhook_detail_out(
    script_id: str, user_id: str, webhook_id: str
) -> WebhookDetailOut:
    _, data = await Config.get_webhook(script_id, user_id, webhook_id)
    projected = project_model_map(WebhookRead, data)
    return WebhookDetailOut(data=projected[webhook_id])


@api_get(
    router,
    "",
    model_cls=ScriptGetOut,
    index=[],
    data={},
    route_kwargs={
        "tags": ["Get"],
        "summary": "查询全部脚本",
        "response_model": ScriptGetOut,
        "status_code": 200,
    },
)
async def list_scripts() -> ScriptGetOut:
    return await _build_script_collection_out()


@router.post(
    "",
    tags=["Add"],
    summary="创建脚本",
    response_model=ScriptCreateOut,
    status_code=200,
)
async def create_script(script: ScriptCreateIn = Body(...)) -> ScriptCreateOut:
    try:
        uid, config = await Config.add_script(script.type, script.copyFromId)
        data = project_script_model(
            script_contract_type_from_runtime(type(config).__name__),
            await config.toDict(),
        )
    except Exception as e:
        return error_out(
            ScriptCreateOut,
            e,
            id="",
            data=project_script_model(
                script_contract_type_from_create(script.type),
                {},
            ),
        )
    return ScriptCreateOut(id=str(uid), data=data)


@api_patch(
    router,
    "/order",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Update"],
        "summary": "重新排序脚本",
        "response_model": OutBase,
        "status_code": 200,
    },
)
async def reorder_scripts(body: IndexOrderPatch = Body(...)) -> OutBase:
    await Config.reorder_script(body.index_list)
    return OutBase()


@router.get(
    "/{script_id}",
    tags=["Get"],
    summary="查询单个脚本",
    response_model=ScriptDetailOut,
    status_code=200,
)
async def get_script(script_id: ScriptIdPath) -> ScriptDetailOut:
    try:
        return await _build_script_detail_out(script_id)
    except Exception as e:
        script_type = "GeneralConfig"
        try:
            script_type = script_contract_type_from_runtime(
                type(Config.ScriptConfig[uuid.UUID(script_id)]).__name__
            )
        except Exception:
            pass
        return error_out(
            ScriptDetailOut,
            e,
            data=project_script_model(script_type, {}),
        )


@api_patch(
    router,
    "/{script_id}",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Update"],
        "summary": "更新脚本配置",
        "response_model": OutBase,
        "status_code": 200,
    },
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


@api_delete(
    router,
    "/{script_id}",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Delete"],
        "summary": "删除脚本",
        "response_model": OutBase,
        "status_code": 200,
    },
)
async def delete_script(script_id: ScriptIdPath) -> OutBase:
    await Config.del_script(script_id)
    return OutBase()


@api_post(
    router,
    "/{script_id}/actions/import-file",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Action"],
        "summary": "从文件导入脚本配置",
        "response_model": OutBase,
        "status_code": 200,
    },
)
async def import_script_from_file(
    script_id: ScriptIdPath, body: ScriptFileBody = Body(...)
) -> OutBase:
    await Config.import_script_from_file(script_id, body.path)
    return OutBase()


@api_post(
    router,
    "/{script_id}/actions/export-file",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Action"],
        "summary": "导出脚本配置到文件",
        "response_model": OutBase,
        "status_code": 200,
    },
)
async def export_script_to_file(
    script_id: ScriptIdPath, body: ScriptFileBody = Body(...)
) -> OutBase:
    await Config.export_script_to_file(script_id, body.path)
    return OutBase()


@api_post(
    router,
    "/{script_id}/actions/import-web",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Action"],
        "summary": "从网络导入脚本配置",
        "response_model": OutBase,
        "status_code": 200,
    },
)
async def import_script_from_web(
    script_id: ScriptIdPath, body: ScriptUrlBody = Body(...)
) -> OutBase:
    await Config.import_script_from_web(script_id, body.url)
    return OutBase()


@api_post(
    router,
    "/{script_id}/actions/upload-web",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Action"],
        "summary": "上传脚本配置到网络",
        "response_model": OutBase,
        "status_code": 200,
    },
)
async def upload_script_to_web(
    script_id: ScriptIdPath, body: ScriptUploadBody = Body(...)
) -> OutBase:
    await Config.upload_script_to_web(
        script_id, body.config_name, body.author, body.description
    )
    return OutBase()


@api_get(
    router,
    "/{script_id}/users",
    model_cls=UserGetOut,
    index=[],
    data={},
    route_kwargs={
        "tags": ["Get"],
        "summary": "查询脚本下的全部用户",
        "response_model": UserGetOut,
        "status_code": 200,
    },
)
async def list_users(script_id: ScriptIdPath) -> UserGetOut:
    return await _build_user_collection_out(script_id)


@router.post(
    "/{script_id}/users",
    tags=["Add"],
    summary="创建用户",
    response_model=UserCreateOut,
    status_code=200,
)
async def create_user(script_id: ScriptIdPath) -> UserCreateOut:
    script_type = None
    try:
        uid, config = await Config.add_user(script_id)
        script_type = script_contract_type_from_runtime(
            type(Config.ScriptConfig[uuid.UUID(script_id)]).__name__
        )
        user_type = user_contract_type_from_script(script_type)
        data = project_user_model(user_type, await config.toDict())
    except Exception as e:
        user_type = (
            user_contract_type_from_script(script_type)
            if script_type is not None
            else "GeneralUserConfig"
        )
        return error_out(
            UserCreateOut,
            e,
            id="",
            data=project_user_model(user_type, {}),
        )
    return UserCreateOut(id=str(uid), data=data)


@api_patch(
    router,
    "/{script_id}/users/order",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Update"],
        "summary": "重新排序用户",
        "response_model": OutBase,
        "status_code": 200,
    },
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
    status_code=200,
)
async def get_user(script_id: ScriptIdPath, user_id: UserIdPath) -> UserDetailOut:
    try:
        return await _build_user_detail_out(script_id, user_id)
    except Exception as e:
        user_type = "GeneralUserConfig"
        try:
            script_type = script_contract_type_from_runtime(
                type(Config.ScriptConfig[uuid.UUID(script_id)]).__name__
            )
            user_type = user_contract_type_from_script(script_type)
        except Exception:
            pass
        return error_out(
            UserDetailOut,
            e,
            data=project_user_model(user_type, {}),
        )


@api_patch(
    router,
    "/{script_id}/users/{user_id}",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Update"],
        "summary": "更新用户配置",
        "response_model": OutBase,
        "status_code": 200,
    },
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


@api_delete(
    router,
    "/{script_id}/users/{user_id}",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Delete"],
        "summary": "删除用户",
        "response_model": OutBase,
        "status_code": 200,
    },
)
async def delete_user(script_id: ScriptIdPath, user_id: UserIdPath) -> OutBase:
    await Config.del_user(script_id, user_id)
    return OutBase()


@api_post(
    router,
    "/{script_id}/users/{user_id}/actions/import-infrastructure",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Action"],
        "summary": "导入基建配置文件",
        "response_model": OutBase,
        "status_code": 200,
    },
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
    status_code=200,
)
async def get_user_infrastructure_options(
    script_id: ScriptIdPath, user_id: UserIdPath
) -> ComboBoxOut:
    try:
        raw_data = await Config.get_user_combox_infrastructure(script_id, user_id)
        data = COMBOBOX_ITEMS_ADAPTER.validate_python(raw_data or [])
    except Exception as e:
        return error_out(ComboBoxOut, e, data=[])
    return ComboBoxOut(data=data)


@api_get(
    router,
    "/{script_id}/users/{user_id}/webhooks",
    model_cls=WebhookGetOut,
    index=[],
    data={},
    route_kwargs={
        "tags": ["Get"],
        "summary": "查询用户下的全部 Webhook",
        "response_model": WebhookGetOut,
        "status_code": 200,
    },
)
async def list_user_webhooks(
    script_id: ScriptIdPath, user_id: UserIdPath
) -> WebhookGetOut:
    return await _build_webhook_collection_out(script_id, user_id)


@api_post(
    router,
    "/{script_id}/users/{user_id}/webhooks",
    model_cls=WebhookCreateOut,
    id="",
    data=WebhookRead(),
    route_kwargs={
        "tags": ["Add"],
        "summary": "创建用户 Webhook",
        "response_model": WebhookCreateOut,
        "status_code": 200,
    },
)
async def create_user_webhook(
    script_id: ScriptIdPath, user_id: UserIdPath
) -> WebhookCreateOut:
    uid, config = await Config.add_webhook(script_id, user_id)
    return WebhookCreateOut(
        id=str(uid),
        data=project_model(WebhookRead, await config.toDict()),
    )


@api_patch(
    router,
    "/{script_id}/users/{user_id}/webhooks/order",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Update"],
        "summary": "重新排序用户 Webhook",
        "response_model": OutBase,
        "status_code": 200,
    },
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
    status_code=200,
)
async def get_user_webhook(
    script_id: ScriptIdPath,
    user_id: UserIdPath,
    webhook_id: WebhookIdPath,
) -> WebhookDetailOut:
    try:
        return await _build_webhook_detail_out(script_id, user_id, webhook_id)
    except Exception as e:
        return error_out(WebhookDetailOut, e, data=WebhookRead())


@api_patch(
    router,
    "/{script_id}/users/{user_id}/webhooks/{webhook_id}",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Update"],
        "summary": "更新用户 Webhook",
        "response_model": OutBase,
        "status_code": 200,
    },
)
async def update_user_webhook(
    script_id: ScriptIdPath,
    user_id: UserIdPath,
    webhook_id: WebhookIdPath,
    data: WebhookPatch = Body(...),
) -> OutBase:
    await Config.update_webhook(
        script_id,
        user_id,
        webhook_id,
        data.model_dump(exclude_unset=True, exclude_none=True),
    )
    return OutBase()


@api_delete(
    router,
    "/{script_id}/users/{user_id}/webhooks/{webhook_id}",
    model_cls=OutBase,
    route_kwargs={
        "tags": ["Delete"],
        "summary": "删除用户 Webhook",
        "response_model": OutBase,
        "status_code": 200,
    },
)
async def delete_user_webhook(
    script_id: ScriptIdPath,
    user_id: UserIdPath,
    webhook_id: WebhookIdPath,
) -> OutBase:
    await Config.del_webhook(script_id, user_id, webhook_id)
    return OutBase()
