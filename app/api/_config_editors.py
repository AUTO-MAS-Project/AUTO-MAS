"""托管、账号和计划共用的详情投影与局部更新契约。"""

from typing import Any, Literal

from app.config import ConfigEntry
from app.config.wire import config_contract
from app.core import Plugin
from app.models.config import ScriptEntry, UserEntry
from app.models.schema import BackupTargetHint, DeclarativeConfigUi
from app.models.task import TaskMode


def config_detail_ui(
    entry: ConfigEntry, documents: dict[str, dict[str, Any]]
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


def config_update_data(
    entry: ConfigEntry, data: object, *, extra: Literal["ignore", "forbid"] = "ignore"
) -> dict[str, Any]:
    """在路由内按实际类型校验，以业务响应返回字段错误并保留局部更新语义。"""
    contract = config_contract(type(entry), mode="input", extra=extra)
    return contract.model_validate(data).model_dump(exclude_unset=True)
