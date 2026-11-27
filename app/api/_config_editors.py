"""托管、账号和计划共用的详情投影与局部更新契约。"""

from collections.abc import AsyncIterator
from typing import Any, Literal

from fastapi import HTTPException, Request

from app.config import ConfigEntry
from app.config.wire import config_contract
from app.core import Plugin
from app.models.config import ScriptEntry, UserEntry
from app.models.schema import BackupTargetHint, DeclarativeConfigUi
from app.models.task import TaskMode


def config_detail_ui(
    entry: ConfigEntry,
    documents: dict[str, dict[str, Any]],
    *,
    parent_script_type: str | None = None,
) -> DeclarativeConfigUi:
    """复用同次 API 快照的显隐、掩码与选项，账号按所属托管解析插件。"""
    owner = Plugin.trigger_owner(entry)
    record = (
        next((item for item in Plugin.list_plugins() if item.uid == owner), None)
        if owner is not None
        else None
    )
    uid = str(entry.uid)
    ui = DeclarativeConfigUi(
        configUid=uid,
        pluginName=record.info.plugin_name if record is not None else None,
        i18nNamespace=(
            f"plugins.{record.info.plugin_name}.config" if record is not None else None
        ),
        frontendSurfaces=Plugin.resolve_frontend_surfaces(entry, parent_script_type),
        locked=entry.is_locked,
        **documents[uid]["ui"],
    )
    registration = Plugin.registered_script(record) if record is not None else None
    if registration is None or not isinstance(entry, (ScriptEntry, UserEntry)):
        return ui
    _, decl = registration
    scope = "script" if isinstance(entry, ScriptEntry) else "user"
    ui.backupTargets = [
        BackupTargetHint(key=pool.key, kind=pool.kind)
        for pool in decl.restore_pools
        if pool.editor_scope == scope
    ]
    modes = {"view": TaskMode.SCRIPT_VIEW, "config": TaskMode.SCRIPT_CONFIG}
    session = entry.ui_native_session
    if session is not None and modes[session] in decl.supported_modes:
        ui.nativeSession = session
    return ui


async def require_frontend_activation(request: Request) -> AsyncIterator[None]:
    """带插件界面来源的写入必须由当前挂载放行，停用时等待在途写入。"""
    x_plugin_ui_provider = request.headers.get("x-plugin-ui-provider")
    x_plugin_ui_activation = request.headers.get("x-plugin-ui-activation")
    if x_plugin_ui_provider is None and x_plugin_ui_activation is None:
        yield
        return
    if not x_plugin_ui_provider or not x_plugin_ui_activation:
        raise HTTPException(status_code=403, detail="插件界面来源或激活标识缺失")
    frontend = Plugin.validate_frontend_activation(
        x_plugin_ui_provider, x_plugin_ui_activation
    )
    if frontend is None:
        raise HTTPException(status_code=409, detail="插件界面已失效，请重新打开")
    with frontend.gate.active_call():
        yield


def config_update_data(
    entry: ConfigEntry, data: object, *, extra: Literal["ignore", "forbid"] = "ignore"
) -> dict[str, Any]:
    """在路由内按实际类型校验，以业务响应返回字段错误并保留局部更新语义。"""
    contract = config_contract(type(entry), mode="input", extra=extra)
    return contract.model_validate(data).model_dump(exclude_unset=True)
