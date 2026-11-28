"""托管、账号和计划共用的详情投影与局部更新契约。"""

from collections.abc import AsyncIterator, Callable
from typing import Any, Literal

from fastapi import Depends, HTTPException, Request

from app.config import ConfigEntry, DeclarativeBlock, HostBlock, PluginBlock
from app.config.wire import config_contract
from app.core import Plugin
from app.models.config import ScriptEntry, UserEntry
from app.models.schema import (
    BackupTargetHint,
    ConfigBlockOut,
    DeclarativeBlockOut,
    DeclarativeConfigUi,
    HostBlockOut,
    PluginBlockOut,
)
from app.models.task import TaskMode
from app.plugin.frontend import MountedFrontend
from app.utils import get_logger

logger = get_logger("插件配置面板")

# 托管是否进桌面分身改由全局清单管理，旧字段只为降级与已发布插件保留，不在表单里出现。
_DEPRECATED_FIELDS = frozenset({("Run", "ExecutionSession")})


def _config_blocks(entry: ConfigEntry) -> list[ConfigBlockOut] | None:
    blocks = type(entry).ui_blocks
    if blocks is None:
        return None
    pages = Plugin.frontend_block_pages(entry)
    projected: list[ConfigBlockOut] = []
    for block in blocks:
        match block:
            case HostBlock(name):
                projected.append(HostBlockOut(name=name))
            case DeclarativeBlock(groups):
                projected.append(DeclarativeBlockOut(groups=list(groups)))
            case PluginBlock(page_id, fallback_groups):
                projected.append(
                    PluginBlockOut(
                        pageId=page_id,
                        fallbackGroups=list(fallback_groups),
                        mount=pages.get(page_id),
                    )
                )
    return projected


async def config_detail_ui(
    entry: ConfigEntry,
    documents: dict[str, dict[str, Any]],
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
        frontendSurfaces=Plugin.resolve_frontend_surfaces(entry),
        blocks=_config_blocks(entry),
        locked=entry.is_locked,
        **documents[uid]["ui"],
    )
    ui.hints = {
        group: [
            hint
            for hint in hints
            if (group, hint.get("field")) not in _DEPRECATED_FIELDS
        ]
        for group, hints in ui.hints.items()
    }
    registration = Plugin.registered_script(record) if record is not None else None
    if registration is None or not isinstance(entry, (ScriptEntry, UserEntry)):
        return ui
    _, decl = registration
    if decl.read_panel_data is not None:
        for block in ui.blocks or ():
            if not isinstance(block, PluginBlockOut) or block.mount is None:
                continue
            mount = block.mount
            frontend = Plugin.validate_frontend_activation(
                mount.pluginName, mount.activationId
            )
            if frontend is not None:
                try:
                    with frontend.gate.active_call():
                        block.panelData = await decl.read_panel_data(
                            entry, block.pageId
                        )
                except Exception:
                    logger.exception(
                        f"插件区块数据读取失败: {mount.pluginName}/{block.pageId}"
                    )
                    block.mount = None
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


type FrontendWriteGuard = Callable[[ConfigEntry], None]


type FrontendSession = tuple[MountedFrontend, str, str]


async def frontend_session(
    request: Request,
) -> AsyncIterator[FrontendSession | None]:
    """宿主请求沿用原写入流程；面板请求在整个写入期间持有当前实例的调用门。"""
    provider = request.headers.get("x-plugin-ui-provider")
    activation = request.headers.get("x-plugin-ui-activation")
    page = request.headers.get("x-plugin-ui-page")
    if provider is None and activation is None and page is None:
        yield None
        return
    if not (provider and activation and page):
        raise HTTPException(status_code=403, detail="插件界面身份不完整")
    frontend = Plugin.validate_frontend_activation(provider, activation)
    if frontend is None:
        raise HTTPException(status_code=409, detail="插件界面已失效，请重新打开")

    with frontend.gate.active_call():
        yield frontend, provider, page


async def require_frontend_activation(
    session: FrontendSession | None = Depends(frontend_session, scope="function"),
) -> FrontendWriteGuard | None:
    if session is None:
        return None
    frontend, provider, page = session

    def authorize(entry: ConfigEntry) -> None:
        if any(
            mount is frontend and binding.page == page
            for _, mount, binding in Plugin.frontend_bindings(entry)
        ):
            return
        block = Plugin.frontend_block_pages(entry).get(page)
        if (
            block is not None
            and block.pluginName == provider
            and block.activationId == frontend.activation_id
        ):
            return
        raise HTTPException(status_code=403, detail="页面未绑定到此配置")

    return authorize


def config_update_data(
    entry: ConfigEntry, data: object, *, extra: Literal["ignore", "forbid"] = "ignore"
) -> dict[str, Any]:
    """在路由内按实际类型校验，以业务响应返回字段错误并保留局部更新语义。"""
    contract = config_contract(type(entry), mode="input", extra=extra)
    return contract.model_validate(data).model_dump(exclude_unset=True)
