#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""脚本更新的统一异步入口与下载策略；适配器负责版本判断和安装。"""

import asyncio
import time
from contextvars import ContextVar
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import ParamSpec, TypeVar
from uuid import UUID

import httpx

from app.core import Config, Publisher
from app.core.ws import protocol
from app.models.schema import WSTaskNoticeData
from app.core.script_update_recovery import (
    DownloadRetryFailed,
    InstallInspection,
    RecoveryIncident,
    reconcile_installation,
    run_managed_installation,
)
from app.core.script_update_queue import ScriptUpdateQueue
from app.core.update import download_file, download_method, download_observer
from app.models.config import CLASS_BOOK
from app.models.task import (
    TaskExecuteBase,
    TaskItem,
    TaskMode,
    TaskScriptItem,
    WSTaskPrefetchData,
)
from app.services.common.update.transport import BuiltinDownload, DownloadProgress
from app.utils import get_logger
from app.utils.common.process.scope import TaskProcessScope, current_process_scope

logger = get_logger("脚本更新")
P = ParamSpec("P")
T = TypeVar("T")


@dataclass(frozen=True)
class ScriptUpdateRequest:
    """一次更新操作的调度身份；不携带凭据、配置或预先启动的协程。"""

    script_id: str
    script_type: str
    engine: str | None = None


_current_recovery_session: ContextVar["ScriptUpdateSession | None"] = ContextVar(
    "current_script_update_recovery_session", default=None
)


def _record_recovery_event(event: RecoveryIncident) -> None:
    session = _current_recovery_session.get()
    if session is not None:
        session.record_recovery(event)
    else:
        logger.warning(
            f"脚本恢复报告未附着运行队列：{event.script_type} {event.outcome}"
        )


async def auto_recover_script_install(
    request: ScriptUpdateRequest,
    *,
    install_root: Path,
    inspect: Callable[[], Awaitable[InstallInspection]],
    acknowledge: Callable[[], Awaitable[None]],
    reinstall: Callable[[], Awaitable[None]],
) -> str:
    """公共脚本更新入口统一编排恢复，不在专项适配器内发通知。"""

    return await reconcile_installation(
        script_id=request.script_id,
        script_type=request.script_type,
        install_root=install_root,
        inspect=inspect,
        acknowledge=acknowledge,
        reinstall=reinstall,
        report=_record_recovery_event,
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
        report=_record_recovery_event,
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
            _record_recovery_event(
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
        if (
            not previous.pending
            and previous.healthy
            and previous.previous_confirmed
        ):
            _record_recovery_event(
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
        _record_recovery_event(
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


async def run_script_update(
    request: ScriptUpdateRequest,
    operation: Callable[P, Awaitable[T]],
    /,
    *args: P.args,
    **kwargs: P.kwargs,
) -> T:
    """所有脚本更新共用的异步入口，完整等待检查、下载及安装结束。

    队列预取和启动前更新均通过此入口；预取只调用专项的下载阶段，安装阶段
    仍在专项原有的安装锁内执行。异常和取消原样交还调用方，后台任务由
    队列持有并等待收尾，不在此提前释放安装目录的使用权。
    """
    logger.debug(f"开始脚本更新：{request.script_type} {request.engine or ''}")
    scope = current_process_scope.get()
    if scope is not None:
        with scope.updating():
            return await operation(*args, **kwargs)
    return await operation(*args, **kwargs)


_SCRIPT_TYPE_BY_CLASS = {cls.__name__: key for key, cls in CLASS_BOOK.items()}


class ScriptUpdateSession:
    """第二层公共入口：只负责调度预下载、候选所有权和消费前校验。

    第三层各脚本适配器仍负责版本检查、下载、原有安装锁、校验与恢复。
    """

    def __init__(
        self,
        task_info: TaskItem,
        *,
        make_manager: Callable[[TaskScriptItem], TaskExecuteBase | None],
        process_scope: Callable[[], TaskProcessScope | None] | None = None,
        config=Config,
    ) -> None:
        self._task = task_info
        self._make_manager = make_manager
        self._process_scope = process_scope
        self._completed_at: float | None = None
        self._retrying = False
        self._config = config
        self._queue = ScriptUpdateQueue()
        self._pending: tuple[UUID, object, TaskExecuteBase] | None = None
        self._recovery_events: list[RecoveryIncident] = []
        self._recovery_reported = False

    def record_recovery(self, event: RecoveryIncident) -> None:
        """只记录当前任务的恢复结果，去重重复确认与后续账号复检。"""
        if event not in self._recovery_events:
            self._recovery_events.append(event)

    async def publish_recovery_summary(self) -> None:
        """在整轮任务完成时集中发一份报告，非脚本级即时弹窗。"""
        if self._recovery_reported:
            return
        self._recovery_reported = True
        if not self._recovery_events:
            return
        outcomes = {
            "verified": "已校验安装并自动清理残留记录",
            "installed": "更新成功，已验证并删除更新前备份",
            "deferred": "安装结果尚未确认，保留备份等待下次恢复",
            "reinstalled": "自动重装修复完成",
            "old_version": "重新下载失败，已验证旧版并继续运行",
            "blocked": "恢复失败，已保护安装现场并阻止启动",
        }
        lines = ["[脚本安装恢复汇总]"]
        for event in self._recovery_events:
            detail = f"；原因：{event.reason}" if event.reason else ""
            source = f"；来源：{event.source}" if event.source else ""
            version = (
                f"；当前版本：{event.installed_version}"
                if event.installed_version
                else ""
            )
            lines.append(
                f"- {event.script_type} ({event.script_id})："
                f"{outcomes[event.outcome]}{version}{source}{detail}"
                f"；目录：{event.install_root}"
            )
        message = "\n".join(lines)
        # TaskItem.current.log 是虚拟投影（不可写）；汇总保存在任务树自身
        # 的 recovery_summary 字段，再通过任务完成包和任务通知同时传递。
        self._task.current.recovery_summary = message
        await self._task.commit()
        try:
            await Publisher.send(
                id=self._task.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="warning"
                    if any(
                        e.outcome in ("old_version", "blocked", "deferred")
                        for e in self._recovery_events
                    )
                    else "info",
                    message=message,
                ),
            )
        except Exception:
            logger.warning("脚本恢复汇总已写入日志，但发送任务通知失败")

    async def _set_progress(
        self, text: str, details: WSTaskPrefetchData | None = None
    ) -> None:
        details = details or (WSTaskPrefetchData(status=text) if text else None)
        if self._task.current.prefetch != details:
            self._task.current.prefetch = details
            await self._task.commit()

    def mark_completed(self) -> None:
        """记录当前专项既有结果面的首次成功，不向公共树写专项子任务状态。"""
        if not self._retrying and self._completed_at is None:
            self._completed_at = time.monotonic()

    async def retry(self, current: TaskScriptItem, next_index: int | None) -> None:
        """专项失败重登：停写确认后重新等首次成功，不影响正常账号切换。"""
        self._retrying = True
        self._completed_at = None
        try:
            # 下载（含 FluxDown 和安装线程）的取消必须先确认；不能在重登时
            # 遗留旧下载，也不能沿用上一次尝试已经完成的候选。
            await self._queue.finish(cancelled=True)
            await self.discard()
            self.watch(current, next_index)
        finally:
            self._retrying = False

    def _eligible(self, index: int) -> bool:
        scripts = list(self._task.scripts.values())
        if self._task.info.mode != TaskMode.AUTO_PROXY or not 0 <= index < len(scripts):
            return False
        item = scripts[index]
        script_config = self._config.ScriptConfig.get(UUID(item.info.script_id))
        return (
            script_config is not None
            and (item._config_ref is None or item._config_ref() is script_config)
            and not script_config.is_locked
            and bool(item.users)
            and (
                item._run_days is None
                or datetime.now().astimezone().strftime("%A") in item._run_days
            )
        )

    def _identity(self, index: int) -> object | None:
        if not self._eligible(index):
            return None
        item = list(self._task.scripts.values())[index]
        config = self._config.ScriptConfig[UUID(item.info.script_id)]
        # 仅冻结更新策略与安装身份；下载历史、账号运行记录和展示字段
        # 都是可变输出，不能让刚下载好的候选自行失效。
        # ConfigEntry 的自定义导出器不传递 include，显式从导出值筛选。
        snapshot = config.model_dump(mode="python")
        selected = {}
        for group, fields in {
            "Info": {"Path", "RootPath", "M7APath", "SRAPath"},
            "Update": None,
            "Embedded": {"FollowSource", "Report"},
        }.items():
            if group in snapshot:
                selected[group] = (
                    snapshot[group]
                    if fields is None
                    else {
                        key: value
                        for key, value in snapshot[group].items()
                        if key in fields
                    }
                )
        return (
            item.info.script_id,
            type(config),
            selected,
            id(config),
            self._config.setting.Update.model_dump(
                mode="python",
                include={
                    "Downloader",
                    "FluxdownPath",
                    "FluxdownSegments",
                    "FluxdownServerMode",
                    "FluxdownTakeoverAll",
                    "GitHubMirror",
                    "MirrorChyanCDK",
                    "ProxyAddress",
                    "Source",
                },
            ),
        )

    def watch(self, current: TaskScriptItem, next_index: int | None) -> None:
        self._completed_at = None
        if next_index is None:
            return
        scripts = list(self._task.scripts.values())
        index = next(
            (i for i in range(next_index, len(scripts)) if self._eligible(i)), None
        )
        if index is None or scripts[index].info.script_id == current.info.script_id:
            return
        self._queue.watch(
            current,
            lambda: self._prefetch(index),
            completed_at=lambda: self._completed_at,
        )

    async def _prefetch(self, index: int) -> None:
        identity = self._identity(index)
        if identity is None:
            return
        item = list(self._task.scripts.values())[index]
        uid = UUID(item.info.script_id)
        config = self._config.ScriptConfig[uid]
        manager = self._make_manager(item)
        if manager is None:
            return
        label = f"[预下载 {item.info.name}]"
        last_report = float("-inf")
        last_path: Path | None = None
        last_bytes = 0
        last_method = ""
        active = True

        def report(path: Path, downloaded: int, total: int, speed: float) -> None:
            nonlocal last_report, last_path, last_bytes, last_method
            method = download_method.get()
            now = time.monotonic()
            if not active or (now - last_report < 1 and method == last_method):
                return
            if speed <= 0 and last_path == path and now > last_report:
                speed = max(0, downloaded - last_bytes) / (now - last_report)
            last_report = now
            last_method = method
            last_path, last_bytes = path, downloaded
            size = f"{downloaded / 1024**2:.1f} MiB"
            if total > 0:
                size = (
                    f"{min(downloaded / total, 1):.1%} · "
                    f"{downloaded / 1024**2:.1f}/{total / 1024**2:.1f} MiB"
                )
            manager.callbacks.submit(
                self._set_progress(
                    f"{label} [{method}] 当前包 {path.name} · {size} · {speed / 1024**2:.1f} MiB/s",
                    WSTaskPrefetchData(
                        target=item.info.name,
                        status="下载中",
                        package=path.name,
                        method=method,
                        progress=f"{min(downloaded / total, 1):.1%}"
                        if total > 0
                        else "",
                        size=f"{downloaded / 1024**2:.1f}/{total / 1024**2:.1f} MiB"
                        if total > 0
                        else f"{downloaded / 1024**2:.1f} MiB",
                        rate=f"{speed / 1024**2:.1f} MiB/s",
                    ),
                )
            )

        ticket = await config.try_lock_x(cascade=False)
        if ticket is None:
            await manager.callbacks.close()
            return
        scope_token = current_process_scope.set(
            self._process_scope() if self._process_scope is not None else None
        )
        token = download_observer.set(report)
        try:
            await self._set_progress(f"{label} 检查／准备中")
            await run_script_update(
                ScriptUpdateRequest(
                    item.info.script_id,
                    _SCRIPT_TYPE_BY_CLASS.get(type(config).__name__, "unknown"),
                ),
                manager.prefetch_script_update,
            )
            await manager.callbacks.drain()
        except BaseException as error:
            active = False
            await manager.callbacks.drain()
            state = (
                "已取消" if isinstance(error, asyncio.CancelledError) else "准备失败"
            )
            await self._set_progress(f"{label} {state}")
            await manager.discard_prefetched_update()
            await manager.callbacks.close()
            raise
        finally:
            active = False
            download_observer.reset(token)
            current_process_scope.reset(scope_token)
            await config.unlock(ticket)
        if self._identity(index) != identity:
            # 下载期间配置或安装身份变化，不允许旧候选被应用。
            await manager.discard_prefetched_update()
            await manager.callbacks.close()
            await self._set_progress(f"{label} 配置已变化，已丢弃")
            return
        await self.discard()
        self._pending = (item.uid, identity, manager)
        await self._set_progress(f"{label} 检查／准备完成")

    async def take(self, script_uid: UUID) -> TaskExecuteBase | None:
        await self._set_progress("")
        pending, self._pending = self._pending, None
        if pending is None:
            return None
        index = next(
            (
                i
                for i, script in enumerate(self._task.scripts.values())
                if script.uid == script_uid
            ),
            None,
        )
        if (
            pending[0] == script_uid
            and index is not None
            and self._identity(index) == pending[1]
        ):
            return pending[2]
        await pending[2].discard_prefetched_update()
        await pending[2].callbacks.close()
        return None

    async def discard(self) -> None:
        await self._set_progress("")
        pending, self._pending = self._pending, None
        if pending is not None:
            await pending[2].discard_prefetched_update()
            await pending[2].callbacks.close()

    async def finish(self, *, cancelled: bool = False) -> None:
        # 只有收敛后的下载候选才能移交；异常退出还必须清除已完成的候选。
        try:
            await self._queue.finish(cancelled=cancelled)
        finally:
            if cancelled:
                await self.discard()

    async def close(self) -> None:
        await self.finish(cancelled=True)


def script_downloader(source: str) -> str:
    """FluxDown 只决定 GitHub 包的下载方式，不决定是否接管更新。"""
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
    """复用 MAS 下载器与网络代理，取消后等待后台写入权收敛。

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
