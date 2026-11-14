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


class PrefetchSession:
    def __init__(self, task, factories, *, downloads=None, check=None):
        """绑定本次 L2 任务及新旧专项检查入口，为本任务建立下载使用者身份和待释放 URL 记录。"""
        self.task = task
        self.factories = factories
        self.downloads = downloads or Downloads
        self.owner = f"task:{task.uid}"
        self.requests: dict[str, DownloadRequest] = {}
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
            snapshots = [
                self.downloads.query(request)
                for request in tuple(self.requests.values())
            ]
            if snapshots:
                active = any(
                    item.state in {"pending", "running", "retrying", "cancelling"}
                    for item in snapshots
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
                        target="本轮托管",
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
        callback = getattr(factory, "check_prefetch", None)
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

    async def _acquire(self, requests: list[DownloadRequest]) -> None:
        """逐项申请下载，忙时等待重试直到受理；登记待释放引用，并为本 L2 启动进度汇总任务。"""
        for request in requests:
            while not self.downloads.request(request, owner=self.owner):
                await asyncio.sleep(1)
            # 被拒绝的申请不计入；同一 URL 复查改变身份仍只保留一份引用。
            self.requests[request.url] = request
            if self._progress_group is None:
                self._progress_group = BackgroundTaskManager.register_group(
                    f"prefetch-progress:{self.task.uid}", max_running=1, max_retained=1
                )
                self._progress_group.spawn(self._report_progress, retain_result=False)

    async def start(self) -> None:
        """在获取专项配置锁前检查本次可执行脚本的预下载需求，收集完成后统一提交下载申请。"""
        collected: list[DownloadRequest] = []
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
                    collected.extend(requirements)
        await self._acquire(collected)

    async def prepare(self, script, entry) -> dict[str, str]:
        """在调用者已取得 X 锁后执行；不再需要的 URL 留到 L2 final 释放。"""
        requirements = await self._requirements(script, entry)
        if requirements is not None:
            await self._acquire(requirements)
        paths: dict[str, str] = {}
        for request in requirements or ():
            result = await self.downloads.wait(request)
            if result.writer_unconfirmed:
                raise FluxdownCancelUnconfirmed("预下载未确认停写，不能继续准备托管")
            if result.state == "succeeded" and result.path:
                paths[request.url] = result.path
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
        """停止进度汇总并清空任务显示，释放本 L2 取得的所有 URL 引用，停写未确认时保留错误。"""
        if self._progress_group is not None:
            await BackgroundTaskManager.unregister_group(self._progress_group)
            self._progress_group = None
        await self._set_progress(None)
        unsafe = False
        for url in tuple(self.requests):
            if await self.downloads.release(url, owner=self.owner):
                del self.requests[url]
            else:
                unsafe = True
        if unsafe:
            raise FluxdownCancelUnconfirmed("预下载清理未确认停写")
