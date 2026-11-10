#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""脚本更新的统一异步入口与下载策略；适配器负责版本判断和安装。"""

from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import ParamSpec, TypeVar
from uuid import UUID

import httpx

from app.core import Config
from app.core.script_update_queue import ScriptUpdateQueue
from app.core.script_update_recovery import (
    DownloadRetryFailed,
    InstallInspection,
    RecoveryIncident,
    reconcile_installation,
    run_managed_installation,
)
from app.core.update import download_file
from app.models.config import CLASS_BOOK
from app.models.task import ScriptItem, TaskExecuteBase, TaskItem
from app.services.common.update.transport import BuiltinDownload, DownloadProgress
from app.utils import get_logger
from app.utils.common.process.scope import current_process_scope

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
        if not previous.pending and previous.healthy and previous.previous_confirmed:
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
        make_manager: Callable[..., TaskExecuteBase | None],
        resources: Callable[[object], tuple[tuple[Path, ...], str | None]],
        scheduled: Callable[[int], bool],
        config=Config,
    ) -> None:
        self._task = task_info
        self._make_manager = make_manager
        self._resources = resources
        self._scheduled = scheduled
        self._config = config
        self._queue = ScriptUpdateQueue()
        self._pending: tuple[int, object, TaskExecuteBase] | None = None
        self._recovery_events: list[RecoveryIncident] = []
        self._recovery_reported = False

    def record_recovery(self, event: RecoveryIncident) -> None:
        if event not in self._recovery_events:
            self._recovery_events.append(event)

    async def publish_recovery_summary(self) -> None:
        """旧版调度器兼容：任务结束时只发送一份恢复事件汇总。"""
        if self._recovery_reported:
            return
        self._recovery_reported = True
        if not self._recovery_events:
            return
        labels = {
            "verified": "安装状态已验证",
            "installed": "更新成功，旧备份已删除",
            "deferred": "更新未确认，备份留待下次恢复",
            "reinstalled": "官方安装已自动修复",
            "old_version": "已安全恢复/继续使用旧版",
            "blocked": "安装存在风险，已阻断启动并保留现场",
        }
        lines = ["[脚本安装恢复汇总]"]
        for event in self._recovery_events:
            extra = f"；原因：{event.reason}" if event.reason else ""
            source = f"；来源：{event.source}" if event.source else ""
            version = (
                f"；版本：{event.installed_version}" if event.installed_version else ""
            )
            lines.append(
                f"- {event.script_type}（{event.script_id}）："
                f"{labels[event.outcome]}{version}{source}{extra}"
                f"；目录：{event.install_root}"
            )
        message = "\n".join(lines)
        warning = any(
            x.outcome in {"old_version", "blocked", "deferred"}
            for x in self._recovery_events
        )
        if warning:
            logger.warning(message)
        else:
            logger.info(message)
        # release 的 TaskItem 仍是旧数据模型，不写入仅在 dev 存在的
        # recovery_summary 字段，直接通过既有 TASK_NOTICE 协议发送。
        try:
            await self._task.send_notice(
                level="warning" if warning else "info",
                message=message,
            )
        except Exception:
            logger.warning("脚本恢复汇总已写入后端日志，任务通知发送失败")

    def _eligible(self, index: int) -> bool:
        if self._task.mode != "AutoProxy" or not 0 <= index < len(
            self._task.script_list
        ):
            return False
        item = self._task.script_list[index]
        try:
            script_config = self._config.ScriptConfig.get(UUID(item.script_id))
        except (TypeError, ValueError):
            return False
        if script_config is None or script_config.is_locked:
            return False
        scope = self._task.script_user_scope(item.script_id)
        return (scope is None or bool(scope)) and (
            self._task.is_cycle or self._scheduled(index)
        )

    def _identity(self, index: int) -> object | None:
        if not self._eligible(index):
            return None
        item = self._task.script_list[index]
        config = self._config.ScriptConfig[UUID(item.script_id)]
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
            item.script_id,
            type(config),
            selected,
            self._resources(config),
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

    def _next_target(self, start_index: int) -> int | None:
        if self._task.is_cycle:
            # 循环模式只允许调度器指定本轮已到期的下一项，不扫描其它条目。
            return start_index if self._eligible(start_index) else None
        # 顺序模式看下一实际可运行项，而不只是下一行配置。
        return next(
            (
                index
                for index in range(start_index, len(self._task.script_list))
                if self._eligible(index)
            ),
            None,
        )

    def watch(self, current: ScriptItem, next_index: int | None) -> None:
        if next_index is None:
            return
        index = self._next_target(next_index)
        if (
            index is None
            or self._task.script_list[index].script_id == current.script_id
        ):
            # 当前脚本的不同账号及紧邻的同一脚本不重复预下载。
            return
        self._queue.watch(current, lambda: self._prefetch(index))

    async def _prefetch(self, index: int) -> None:
        identity = self._identity(index)
        if identity is None:
            return
        item = self._task.script_list[index]
        uid = UUID(item.script_id)
        config = self._config.ScriptConfig[uid]
        roots, emulator_key = self._resources(config)
        manager = self._make_manager(
            item,
            config,
            script_uid=uid,
            reservation_owner=self._task.task_id,
            root_paths=roots,
            emulator_key=emulator_key,
        )
        if manager is None:
            return
        try:
            await run_script_update(
                ScriptUpdateRequest(
                    item.script_id,
                    _SCRIPT_TYPE_BY_CLASS.get(type(config).__name__, "unknown"),
                ),
                manager.prefetch_script_update,
            )
        except BaseException:
            await manager.discard_prefetched_update()
            raise
        if self._identity(index) != identity:
            # 下载期间配置或安装身份变化，不允许旧候选被应用。
            await manager.discard_prefetched_update()
            return
        await self.discard()
        self._pending = (index, identity, manager)

    async def take(self, index: int) -> TaskExecuteBase | None:
        pending, self._pending = self._pending, None
        if pending is None:
            return None
        if pending[0] == index and self._identity(index) == pending[1]:
            return pending[2]
        await pending[2].discard_prefetched_update()
        return None

    async def discard(self) -> None:
        pending, self._pending = self._pending, None
        if pending is not None:
            await pending[2].discard_prefetched_update()

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
