"""L2 的下载需求与引用；检查无锁，消费前由配置锁持有者复查。"""

from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import UUID

from app.core import BackgroundTaskManager, Config, Downloads, Plugin
from app.core.background_tasks import BackgroundTaskGroup
from app.models.schema import DownloadRequest
from app.models.task import TaskMode, WSTaskPrefetchData
from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed

PREFETCH_PATHS_KEY = "prefetch_paths"
_ACTIVE_STATES = {"pending", "running", "retrying", "cancelling"}


class PrefetchSession:
    def __init__(self, task, factories, *, downloads=None, check=None):
        """绑定本次 L2 及新旧检查入口，建立下载使用者身份和待释放资源键记录。"""
        self.task = task
        self.factories = factories
        self.downloads = downloads or Downloads
        self.owner = f"task:{task.uid}"
        self.requests: dict[str, DownloadRequest] = {}
        self._targets: dict[str, dict[str, None]] = {}
        self.check = check or self._check
        self._progress_group: BackgroundTaskGroup | None = None

    async def _set_progress(self, value: WSTaskPrefetchData | None) -> None:
        """仅在预下载汇总发生变化时更新并提交任务进度，避免重复推送相同状态。"""
        if self.task.current.prefetch != value:
            self.task.current.prefetch = value
            await self.task.commit()

    async def _report_progress(self) -> None:
        """只在所属协程提交展示字段，不让下载任务写任务树或创建文件运行节点。"""
        while True:
            transfers = [
                (request, self.downloads.query(request))
                for request in tuple(self.requests.values())
            ]
            if transfers:
                snapshots = [snapshot for _, snapshot in transfers]
                active = [
                    request
                    for request, snapshot in transfers
                    if snapshot.state in _ACTIVE_STATES
                ]
                displayed = active or [request for request, _ in transfers]
                targets = dict.fromkeys(
                    name
                    for request in displayed
                    for name in self._targets[request.cache_key]
                )
                methods = dict.fromkeys(
                    filter(None, map(self.downloads.transfer_method, displayed))
                )
                failed = any(
                    item.state in {"failed", "cancelled", "not_found"}
                    for item in snapshots
                )
                done = sum(item.state == "succeeded" for item in snapshots)
                downloaded = sum(item.downloaded for item in snapshots)
                total = sum(item.total for item in snapshots)
                speed = sum(item.speed for item in snapshots if item.state == "running")
                await self._set_progress(
                    WSTaskPrefetchData(
                        target="、".join(targets),
                        method=" / ".join(methods),
                        status="下载中"
                        if active
                        else "预下载失败，运行时重新准备"
                        if failed
                        else "检查／准备完成",
                        package=f"{done}/{len(snapshots)} 个文件",
                        progress=f"{min(downloaded / total, 1):.1%}"
                        if total > 0
                        else "",
                        size=f"{downloaded / 1024**2:.1f}/{total / 1024**2:.1f} MiB"
                        if total > 0
                        else f"{downloaded / 1024**2:.1f} MiB",
                        rate=f"{speed / 1024**2:.1f} MiB/s" if active else "",
                    )
                )
            await asyncio.sleep(1)

    async def _check(self, entry) -> list[DownloadRequest]:
        """按配置类型选择插件声明或旧专项固定方法检查预下载需求，无声明时返回空列表。"""
        from app.models.config import ScriptEntry

        if isinstance(entry, ScriptEntry):
            return await Plugin.check_prefetch(entry)
        factory = self.factories.get(type(entry))
        if factory is None:
            return []
        # 旧登记提供的是构造函数；用真实任务节点构造兼容运行器，再读取固定检查入口。
        script = next(
            item for item in self.task.script_list if item.script_id == str(entry.uid)
        )
        callback = getattr(factory(script), "check_prefetch", None)
        return await callback(entry) if callback is not None else []

    async def _requirements(self, script, entry) -> list[DownloadRequest] | None:
        """仅为自动代理任务检查预下载需求，普通检查失败时记录原因并允许后续运行自行准备。"""
        if self.task.info.mode != TaskMode.AUTO_PROXY:
            return []
        try:
            return await self.check(entry)
        except FluxdownCancelUnconfirmed:
            raise
        except Exception as error:
            await script.set_log(f"预下载检查失败，运行时将重新准备：{error}")
            return None

    async def _acquire(self, target: str, requests: list[DownloadRequest]) -> None:
        """逐项申请下载，忙时等待重试直到受理；登记待释放引用，并为本 L2 启动进度汇总任务。"""
        for request in requests:
            while not self.downloads.request(request, owner=self.owner):
                await asyncio.sleep(1)
            # 被拒绝的申请不计入；同一资源复查改变地址或身份仍只保留一份引用。
            key = request.cache_key
            previous = self.requests.get(key)
            if previous is None or previous.identity != request.identity:
                self._targets[key] = {}
            self.requests[key] = request
            self._targets[key][target] = None
            if self._progress_group is None:
                self._progress_group = BackgroundTaskManager.register_group(
                    f"prefetch-progress:{self.task.uid}", max_running=1, max_retained=1
                )
                self._progress_group.spawn(self._report_progress, retain_result=False)

    async def start(self) -> None:
        """在获取专项配置锁前检查本次可执行脚本的预下载需求，收集完成后统一提交下载申请。"""
        collected: list[tuple[str, list[DownloadRequest]]] = []
        for script in self.task.script_list:
            if (
                script._run_days is not None
                and datetime.now().astimezone().strftime("%A") not in script._run_days
            ):
                continue
            entry = Config.ScriptConfig.get(UUID(script.script_id))
            if entry is not None and (
                script._config_ref is None or script._config_ref() is entry
            ):
                requirements = await self._requirements(script, entry)
                if requirements is not None:
                    collected.append((script.info.name, requirements))
        for target, requests in collected:
            await self._acquire(target, requests)

    async def prepare(self, script, entry) -> dict[str, str]:
        """在调用者已取得 X 锁后复查并等待需求；不再需要的资源引用留到 L2 final 释放。"""
        requirements = await self._requirements(script, entry)
        if requirements is not None:
            await self._acquire(script.info.name, requirements)
        paths: dict[str, str] = {}
        for request in requirements or ():
            result = await self.downloads.wait(request)
            if result.writer_unconfirmed:
                raise FluxdownCancelUnconfirmed("预下载未确认停写，不能继续准备托管")
            if result.state == "succeeded" and result.path:
                paths[request.cache_key] = result.path
            else:
                await script.set_log(
                    f"预下载未完成（{result.state}），运行时将重新准备"
                )
        if (
            paths
            or requirements is None
            or requirements
            or PREFETCH_PATHS_KEY in script.info.params
        ):
            script.info.params = {**script.info.params, PREFETCH_PATHS_KEY: paths}
            await script.commit()
        return paths

    async def close(self) -> None:
        """停止进度汇总并清空显示，按资源键释放本 L2 的全部引用，停写未确认时保留错误。"""
        if self._progress_group is not None:
            await BackgroundTaskManager.unregister_group(self._progress_group)
            self._progress_group = None
        await self._set_progress(None)
        unsafe = False
        for url in tuple(self.requests):
            if await self.downloads.release(url, owner=self.owner):
                del self.requests[url]
                del self._targets[url]
            else:
                unsafe = True
        if unsafe:
            raise FluxdownCancelUnconfirmed("预下载清理未确认停写")
