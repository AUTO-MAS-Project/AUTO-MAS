#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""[兼容旧专项] 旧 manager 的更新、恢复与下载调用入口。

TODO(脚本更新迁移)：预下载已由 L2 的 PrefetchSession 统一管理；
检查、安装与恢复编排后续全部迁入 L2（app/task/script_update.py）。
此处只维持旧专项与临时复用旧 manager 的 MAA 测试插件，不作为新插件协议。
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import ParamSpec, TypeVar

import httpx

from app.core import Config
from app.core.downloads import download_file
from app.core.script_update_recovery import (
    DownloadRetryFailed,
    InstallInspection,
    RecoveryIncident,
    reconcile_installation,
    run_managed_installation,
)
from app.services.common.update.transport import BuiltinDownload, DownloadProgress
from app.task.script_update import record_recovery_event
from app.utils import get_logger
from app.utils.common.process.scope import current_process_scope

logger = get_logger("脚本更新")
P = ParamSpec("P")
T = TypeVar("T")


@dataclass(frozen=True)
class ScriptUpdateRequest:
    """[兼容旧专项] 旧更新入口的调度身份，不携带凭据、配置或已启动协程。"""

    script_id: str
    script_type: str
    engine: str | None = None


async def auto_recover_script_install(
    request: ScriptUpdateRequest,
    *,
    install_root: Path,
    inspect: Callable[[], Awaitable[InstallInspection]],
    acknowledge: Callable[[], Awaitable[None]],
    reinstall: Callable[[], Awaitable[None]],
) -> str:
    """[兼容旧专项] 执行旧 manager 的安装恢复回调，结果交给 L2 汇总。"""

    return await reconcile_installation(
        script_id=request.script_id,
        script_type=request.script_type,
        install_root=install_root,
        inspect=inspect,
        acknowledge=acknowledge,
        reinstall=reinstall,
        report=record_recovery_event,
    )


async def run_script_update(
    request: ScriptUpdateRequest,
    operation: Callable[P, Awaitable[T]],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """[兼容旧专项] 在更新进程作用域内直接等待旧 manager 的更新操作。

    不创建预下载队列、不另起后台执行，异常和取消交还所属任务。
    TODO(脚本更新迁移)：调用时机与更新编排后续统一迁入 L2。
    """
    logger.debug(f"开始脚本更新：{request.script_type} {request.engine or ''}")
    scope = current_process_scope.get()
    if scope is not None:
        with scope.updating():
            return await operation(*args, **kwargs)
    return await operation(*args, **kwargs)


def script_downloader(source: str) -> str:
    """[兼容旧专项] 读取原下载器策略，具体传输复用统一下载模块。"""
    return (
        "fluxdown"
        if source.casefold() == "github" and Config.setting.Update.FluxdownTakeoverAll
        else "builtin"
    )


async def download_script_package(
    url: str,
    destination: Path,
    *,
    source: str,
    timeout: float,
    proxy: httpx.Proxy | None = None,
    progress: DownloadProgress | None = None,
    http_download: BuiltinDownload | None = None,
) -> int:
    """[兼容旧专项] 复用统一下载模块和旧配置策略，取消后等待停写。

    来源在本次下载开始时冻结。Mirror 酱始终使用内置下载器；认证代理的
    安全回退仍由下载分发层处理。调用方只在本函数成功后校验、发布和安装。
    """
    return await download_file(
        url,
        destination,
        timeout=timeout,
        proxy=proxy if proxy is not None else Config.proxy,
        progress=progress,
        source=source,
        downloader=script_downloader(source),
        http_download=http_download,
    )


async def run_managed_script_install(
    request: ScriptUpdateRequest,
    *,
    install_root: Path,
    inspect: Callable[[], Awaitable[InstallInspection]],
    acknowledge: Callable[[], Awaitable[None]],
    install: Callable[[], Awaitable[None]],
    ensure_idle: Callable[[], Awaitable[None]],
    after_rollback: Callable[[], Awaitable[None]],
) -> str:
    """统一收发安装事务，决定备份、重试、回退、清理并汇总结果。

    专项只负责提供真实的健康证据、执行原生安装以及确认没有后台写盘。
    安装锁由调用方从开始到整个结果收束时一直持有。
    """
    return await run_script_update(
        request,
        run_managed_installation,
        script_id=request.script_id,
        script_type=request.script_type,
        install_root=install_root,
        inspect=inspect,
        acknowledge=acknowledge,
        install=install,
        ensure_idle=ensure_idle,
        after_rollback=after_rollback,
        report=record_recovery_event,
    )


async def run_script_update_with_safe_fallback(
    request: ScriptUpdateRequest,
    operation: Callable[P, Awaitable[str]],
    install_root: Path,
    inspect_previous: Callable[[], Awaitable[InstallInspection]],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> str:
    """更新下载失败时由公共层验证旧安装；结果汇总留到任务结束。

    专项只允许在任何安装写盘开始前的下载/包准备错误处抛
    DownloadRetryFailed。未知/已开始安装的错误不允许回退。
    """
    try:
        return await run_script_update(request, operation, *args, **kwargs)
    except DownloadRetryFailed as error:
        try:
            previous = await inspect_previous()
        except Exception as check_error:
            record_recovery_event(
                RecoveryIncident(
                    script_id=request.script_id,
                    script_type=request.script_type,
                    install_root=str(install_root.resolve()),
                    outcome="blocked",
                    source=error.source,
                    reason=f"下载失败且旧版健康检查异常（{type(check_error).__name__}）",
                )
            )
            raise
        if not previous.pending and previous.healthy and previous.previous_confirmed:
            record_recovery_event(
                RecoveryIncident(
                    script_id=request.script_id,
                    script_type=request.script_type,
                    install_root=str(install_root.resolve()),
                    outcome="old_version",
                    installed_version=previous.installed_version,
                    source=error.source,
                    reason=error.reason,
                )
            )
            return (
                f"脚本 {request.script_type} 下载失败，但旧版"
                f" {previous.installed_version or '未知'} 已验证可用，继续任务"
            )
        record_recovery_event(
            RecoveryIncident(
                script_id=request.script_id,
                script_type=request.script_type,
                install_root=str(install_root.resolve()),
                outcome="blocked",
                source=error.source,
                reason=f"下载失败：{error.reason}；旧安装未确认安全",
            )
        )
        raise
