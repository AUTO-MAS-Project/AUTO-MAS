#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""脚本更新的统一异步入口与下载策略；适配器负责版本判断和安装。"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import ParamSpec, TypeVar
from uuid import UUID

import httpx

from app.core import Config
from app.core.script_update_queue import ScriptUpdateQueue
from app.core.update import download_file
from app.models.config import CLASS_BOOK
from app.models.task import ScriptItem, TaskExecuteBase, TaskItem
from app.services.common.update.transport import BuiltinDownload, DownloadProgress
from app.utils import get_logger

logger = get_logger("脚本更新")
P = ParamSpec("P")
T = TypeVar("T")


@dataclass(frozen=True)
class ScriptUpdateRequest:
    """一次更新操作的调度身份；不携带凭据、配置或预先启动的协程。"""

    script_id: str
    script_type: str
    engine: str | None = None


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
    return await operation(*args, **kwargs)


_SCRIPT_TYPE_BY_CLASS = {cls.__name__: key for key, cls in CLASS_BOOK.items()}


class ScriptUpdateSession:
    """第二层公共入口：只负责调度预下载、候选所有权和消费前校验。

    TODO(插件迁移，#1845)：保留 dev 的预取基础能力，当前 L2 不创建此会话；
    旧 TaskItem 范围和目录预约接口需在插件接入时重新适配。
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
