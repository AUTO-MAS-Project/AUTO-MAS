"""账号历史收尾管线；存储、附件采集与任务反馈由宿主注入。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from contextlib import suppress
from dataclasses import dataclass
from functools import cached_property, partial
from pathlib import Path
from typing import TYPE_CHECKING

from app.core import BackgroundTaskManager, Config, History, Publisher
from app.core.background_tasks import BackgroundTaskGroup, BackgroundTaskHandle
from app.core.ws import protocol
from app.models.schema import (
    HistoryAttachmentInput,
    HistoryRecord,
    HistoryWrite,
    WSTaskNoticeData,
)
from app.utils import get_logger

if TYPE_CHECKING:
    from app.models.task import ScriptItem, TaskItem, UserItem

logger = get_logger("任务历史")


@dataclass(frozen=True)
class UserHistoryDependencies:
    """绑定到本次账号执行的副作用，不持有任务或配置对象。"""

    record: Callable[[HistoryWrite], Awaitable[HistoryRecord]]
    collect_attachments: Callable[[], Awaitable[list[HistoryAttachmentInput]]]
    discard_capture: Callable[[], Awaitable[None]]
    report_failure: Callable[[str], Awaitable[None]]
    log_warning: Callable[[str], None]


async def save_user_history(
    records: Sequence[HistoryWrite], *, dependencies: UserHistoryDependencies
) -> None:
    """按原顺序保存历史，将采集附件追加到末条记录并最终释放采集副本。

    条目的判定、日志和已有附件由专项提供。本函数会追加末条记录的附件，
    不改变其余字段；附件或单条保存失败仍继续，取消向上传播且执行清理。
    空批次不采集、不落库，只释放已存在的采集副本。
    """

    try:
        if not records:
            return
        try:
            attachments = await dependencies.collect_attachments()
            records[-1].attachments.extend(attachments)
        except Exception as error:
            dependencies.log_warning(
                f"收集账号历史附件失败，继续保存日志与执行结果：{error}"
            )

        for record in records:
            try:
                await dependencies.record(record)
            except Exception as error:
                dependencies.log_warning(f"保存历史失败：{error}")
                try:
                    await dependencies.report_failure(f"历史记录保存失败：{error}")
                except Exception:
                    logger.opt(exception=True).warning("发送历史保存失败提示时出现异常")
    finally:
        await dependencies.discard_capture()


class TaskHistorySession:
    """一项任务的归档与回放归属；运行节点 UUID 就是轮次身份。"""

    def __init__(self, task: TaskItem) -> None:
        self.task = task
        self.cancelled = False
        self.closed = False
        self._captures: dict[tuple[str, str], BackgroundTaskHandle[Path]] = {}
        self._files: dict[tuple[str, str], Path] = {}
        self._seen: set[tuple[str, str]] = set()

    @cached_property
    def _capture_group(self) -> BackgroundTaskGroup:
        return BackgroundTaskManager.register_group(
            f"history-captures:{self.task.uid}", max_running=32, max_retained=64
        )

    def observe(self, script: ScriptItem) -> None:
        if (
            script.status != "异常"
            or self.task.mode != "AutoProxy"
            or (self.cancelled or self.closed)
        ):
            return
        run = str(script.uid)
        if any(key[0] == run for key in self._captures) or any(
            key[0] == run and key[1] != "diagnostic" for key in self._seen
        ):
            return
        self._request_unassigned_replay(script, reason="无对应用户执行轮次的任务异常")

    def begin_user_history_capture(
        self, script: ScriptItem, user: UserItem, *, failed: bool
    ) -> None:
        """专项确认最终失败后及时请求缓冲；此时只采集临时文件，不预建历史。"""
        if (
            not failed
            or self.task.mode != "AutoProxy"
            or (self.cancelled or self.closed)
            or not user.log_record
        ):
            return
        if not Config.setting.Replay.Enabled:
            return
        run = str(script.uid)
        key = (run, str(user.uid))
        if key in self._seen or key in self._captures:
            return
        from app.services import obs_replay as _service_obs_replay

        options = Config.obs_replay_options()

        async def capture_file() -> Path:
            path = await _service_obs_replay.ObsReplay.capture(options)
            # 文件所有权独立于结果缓存：即使结果过期或等待方取消，close 仍会清理。
            self._files[key] = path
            return path

        capture = self._capture_group.spawn(capture_file)
        if capture is not None:
            self._captures[key] = capture

    async def save_user_history(
        self,
        records: Sequence[HistoryWrite],
        *,
        script: ScriptItem,
        user: UserItem,
        log_warning: Callable[[str], None] | None = None,
    ) -> None:
        """为本次用户历史装配能力，专项只交出已判定的条目与诊断入口。"""

        await save_user_history(
            records,
            dependencies=UserHistoryDependencies(
                record=History.record,
                collect_attachments=partial(
                    self.collect_user_history_attachments, script=script, user=user
                ),
                discard_capture=partial(
                    self.discard_user_history_capture, script=script, user=user
                ),
                report_failure=self._report_history_save_failure,
                log_warning=log_warning
                if log_warning is not None
                else logger.opt(exception=True).warning,
            ),
        )

    async def _report_history_save_failure(self, message: str) -> None:
        await Publisher.send(
            id=self.task.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="warning", message=message),
        )

    async def collect_user_history_attachments(
        self, script: ScriptItem, user: UserItem
    ) -> list[HistoryAttachmentInput]:
        """保存前等待该用户已有采集，捕获故障不影响执行结论和其余记录。"""
        run = str(script.uid)
        key = (run, str(user.uid))
        if key in self._seen:
            return []
        self.begin_user_history_capture(script, user, failed=user.status == "异常")
        capture = self._captures.pop(key, None)
        if capture is None:
            return []
        self._seen.add(key)
        try:
            path = (await capture.wait_take()).unwrap()
            if (self.cancelled or self.closed) or user.status != "异常":
                await self._discard_history_capture_file(path)
                return []
            self._files[key] = path
            return [
                HistoryAttachmentInput(
                    path=path, kind="video", role="obs_replay", display_name=path.name
                )
            ]
        except Exception as error:
            logger.opt(exception=True).warning(f"用户失败回放未采集：{error}")
            with suppress(Exception):
                await Publisher.send(
                    id=self.task.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="warning", message=f"失败回放未采集：{error}"
                    ),
                )
            return []

    async def _discard_history_capture_file(self, path: Path) -> bool:
        from app.services import obs_replay

        return await obs_replay.ObsReplay.discard_temporary(path)

    async def discard_user_history_capture(
        self, script: ScriptItem, user: UserItem
    ) -> None:
        """归档返回后释放本用户的采集副本，包括配额拒收与复制回退留下的源。"""
        run = str(script.uid)
        key = (run, str(user.uid))
        path = self._files.get(key)
        if path is not None and await self._discard_history_capture_file(path):
            self._files.pop(key, None)

    async def close(self) -> None:
        """异常中断未交给用户历史的采集只能丢弃，不能在队列末尾补挂。"""
        self.closed = True
        if "_capture_group" in self.__dict__:
            await BackgroundTaskManager.unregister_group(self._capture_group)
        self._captures.clear()
        for key, path in list(self._files.items()):
            if await self._discard_history_capture_file(path):
                self._files.pop(key, None)

    def _request_unassigned_replay(self, script: ScriptItem, *, reason: str) -> None:
        """无用户归属的诊断只请求 OBS 原件，不创建 MAS 回放档案。"""
        if (
            self.task.mode != "AutoProxy"
            or (self.cancelled or self.closed)
            or not Config.setting.Replay.Enabled
        ):
            return
        run = str(script.uid)
        key = (run, "diagnostic")
        if key in self._seen:
            return
        self._seen.add(key)
        options = Config.obs_replay_options()

        async def capture() -> None:
            from app.services import obs_replay as _service_obs_replay

            try:
                path = await _service_obs_replay.ObsReplay.capture(
                    options, temporary_copy=False
                )
                message = f"{reason}；回放仅保留在 OBS 输出：{path}"
            except Exception as error:
                message = f"{reason}；诊断回放未采集：{error}"
            logger.warning(message)
            with suppress(Exception):
                await Publisher.send(
                    id=self.task.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(level="warning", message=message),
                )

        group = BackgroundTaskManager.get_group("obs-diagnostic-capture")
        if group is None:
            group = BackgroundTaskManager.register_group(
                "obs-diagnostic-capture", max_running=32, max_retained=32
            )
        group.spawn(capture, retain_result=False)
