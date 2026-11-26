"""L1 任务受理、运行登记、查询与终态留存。"""

from __future__ import annotations

import asyncio
import json
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable, Iterator, Mapping
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Any
from uuid import UUID
from weakref import ref

from blinker import Signal
from pydantic import TypeAdapter

from app.config import ConfigEntry, ConfigNode, config_manager
from app.core import Config, Publisher
from app.core.ws import protocol
from app.models.config import ScriptEntry, UserEntry
from app.models.schema import (
    TaskRequirements,
    TaskRuntimeSnapshot,
    TaskRuntimeSnapshotItem,
    TaskSelectionNode,
    TaskStatusOut,
    TaskTreeData,
    WSTaskCreatedData,
    WSTaskScriptIdentityData,
)
from app.models.task import (
    TaskItem,
    TaskMode,
    TaskScriptItem,
    TaskTriggerReason,
    TaskUserItem,
)
from app.task.registration import ManagerFactory
from app.task.script_expander import ScriptExpander
from app.utils import get_logger
from app.utils.common.log_flow.observation import (
    CloseReason,
    InvalidObservationCursor,
    Node,
    NodeObservation,
    ObservationCursor,
    public_log_node,
)
from app.utils.common.process.session import desktop_process_target
from app.utils.contracts.power import PowerSignal

logger = get_logger("任务调度")
_selection = TypeAdapter(dict[int, TaskSelectionNode])
_RECENT_ANALYSIS_BYTES = 16 * 1024 * 1024
_RECENT_ANALYSIS_HISTORY_BYTES = 16 * 1024 * 1024


@dataclass
class _RecentTask:
    ended_at: float
    tree: dict[str, Any]
    finished_at: str
    analysis_sizes: dict[tuple[str, str], int]
    observations: dict[tuple[str, str], NodeObservation]


@dataclass(frozen=True)
class TaskLogAnalysisRead:
    nodes: tuple[Node, ...]
    cursor: ObservationCursor | None
    has_more: bool
    close_reason: CloseReason | None


if TYPE_CHECKING:
    from app.models.config import QueueConfig, ScriptConfigType
    from app.models.task import TaskScriptItem
    from app.task.user_expander import UserExpander

type PluginExpander = Callable[[TaskScriptItem, ScriptConfigType], UserExpander | None]


class UnsupportedDesktopTask(ValueError):
    """所选任务包含尚不能在桌面分身执行的操作。"""

    def __init__(self, message, reason="unsupported_config"):
        super().__init__(message)
        self.reason = reason


def script_config_name(entry: ScriptConfigType) -> str:
    return entry.info.name if isinstance(entry, ScriptEntry) else entry.Info.Name


class _TaskManager:
    task_ended: Signal = Signal()

    @property
    def idle(self) -> bool:
        """真实执行器与受理流程均已结束，且不处于停止全部阶段。"""
        return not self._running and not self._creating and not self._stopping_all

    def __init__(self, *, plugin_expander: PluginExpander | None = None) -> None:
        """初始化执行能力、运行登记、终态缓存，以及创建与停止全部的同步状态。"""
        self.plugin_expander = plugin_expander
        self.manager_factories: Mapping[type[ConfigEntry], ManagerFactory | None] = (
            MappingProxyType({})
        )
        self._factories_bound = False
        self._running: dict[UUID, ScriptExpander] = {}
        self._recent: OrderedDict[UUID, _RecentTask] = OrderedDict()
        self._stopping_all = False
        self._restart_pending = False
        self._creating = 0
        self._idle = asyncio.Event()
        self._idle.set()
        self._stop_lock = asyncio.Lock()
        ScriptExpander.ended.connect(self.drop)

    def bind_manager_factories(
        self, factories: Mapping[type[ConfigEntry], ManagerFactory | None]
    ) -> None:
        """[兼容旧专项] 仅供现有宿主绑定旧 manager 工厂；新插件执行能力接入 L3/L4。

        复制为只读映射，且只允许装配一次，避免执行期间更换旧专项分派规则。
        """
        if self._factories_bound:
            raise RuntimeError("专项工厂只能在宿主装配时绑定一次")
        self.manager_factories = MappingProxyType(dict(factories))
        self._factories_bound = True

    @property
    def task_info(self) -> Mapping[UUID, TaskItem]:
        """[兼容旧调用方] 旧运行表视图；新查询使用 get_task() 或 get_runtime_snapshot()。

        排除旧手动更新任务；映射结构只读，值仍是当前任务模型。
        """
        return MappingProxyType(
            {
                uid: run.task_info
                for uid, run in self._running.items()
                if not run.maintenance
            }
        )

    @property
    def task_handler(self) -> dict[UUID, ScriptExpander]:
        """[兼容旧调用方] 旧执行器表视图；新代码通过 stop() 和任务查询接口操作。

        返回排除旧手动更新任务的字典副本，修改字典不会改变内部登记。
        """
        return {uid: run for uid, run in self._running.items() if not run.maintenance}

    def _check_accepting(self) -> None:
        """创建前检查停止全部、电源倒计时，并确认宿主已提供执行能力。"""
        from app.core import Power

        if self._restart_pending:
            raise RuntimeError("后端正在准备重启，暂不接受新任务")
        if self._stopping_all:
            raise RuntimeError("正在停止全部任务，暂不接受新任务")
        if Power.power_task is not None:
            raise RuntimeError("电源任务已进入倒计时，本次任务不再创建")
        if not self._factories_bound and self.plugin_expander is None:
            raise RuntimeError("宿主尚未绑定专项执行工厂")

    def prepare_restart(self) -> bool:
        """只在所有任务及受理流程结束后封闭新任务入口，不中断已有业务。"""
        if not self.idle:
            return False
        self._restart_pending = True
        return True

    def cancel_restart(self) -> None:
        """后端重启未执行时恢复任务受理，原停止全部状态保持不变。"""
        self._restart_pending = False

    async def start(
        self,
        mode: TaskMode,
        tasks: TaskRequirements,
        *,
        trigger: TaskTriggerReason = TaskTriggerReason.MANUAL,
    ) -> UUID:
        """按模式、单入口要求树和触发原因创建普通任务，返回运行 UUID。

        构造任务根及 L2 后交给 _launch；只等待受理完成，实际执行在后台继续。
        """
        self._check_accepting()
        info = TaskItem.build(
            payload={
                "info": {"mode": TaskMode(mode), "trigger": TaskTriggerReason(trigger)}
            }
        )
        return await self._launch(ScriptExpander(info, self), tasks)

    async def start_maintenance(self, target_id: str) -> UUID:
        """[兼容旧专项] 旧手动更新入口；普通任务使用 start()。

        目标由旧适配层解析，以 ScriptConfig 信息树承载隐藏的 Update 分支；
        共用创建与停止流程，不创建普通调度面板。

        TODO(插件迁移，#1845)：存量专项适配与未来维护任务标准均已推迟；
        操作归属、查询/日志、结果消费及取消停写契约尚未确认，不按草案改造此兼容链。
        """
        from app.task.legacy import maintenance_requirements

        self._check_accepting()
        info = TaskItem.build(payload={"info": {"mode": TaskMode.SCRIPT_CONFIG}})
        run = ScriptExpander(info, self)
        run.maintenance = True
        return await self._launch(run, maintenance_requirements(target_id))

    async def _launch(self, run: ScriptExpander, tasks: TaskRequirements) -> UUID:
        """L1：完整校验单入口要求树、建树和记时，随后登记、通知并启动 L2。

        短配置事务内解析队列项到托管、按序展开用户、提交唯一队列的触发时间。
        事务成功后才登记和发布创建通知；此后的失败清理执行器，已提交时间保留。
        创建计数覆盖登记与启动过程，成功、异常和取消都会结清停止全部的屏障。
        """
        raw = {key: value for key, value in tasks.items()}
        TaskSelectionNode.validate_indices(raw)
        if len(raw) != 1:
            raise ValueError("一次任务必须且只能指定一个顶层入口")
        node = _selection.validate_python(raw)[0]
        info = run.task_info
        desktop = desktop_process_target.get() is not None
        queue: QueueConfig | None = None

        def select(
            selected: Mapping[int, TaskSelectionNode], available: Iterable[UUID]
        ) -> Iterator[TaskSelectionNode]:
            """展开空选择，或沿原序列单向匹配非空选择，保持顺序及出现次数。"""
            # 空选择展开全部；非空选择沿配置序列单向匹配，拒绝逆序和超额重复。
            remaining = iter(available)
            if not selected:
                yield from (TaskSelectionNode(uid=str(uid)) for uid in remaining)
                return
            for node in selected.values():
                uid = UUID(node.uid)
                for candidate in remaining:
                    if candidate == uid:
                        yield node
                        break
                else:
                    raise ValueError(f"选择项不存在、次数超出或顺序不符：{node.uid}")

        self._creating += 1
        self._idle.clear()
        try:
            # 校验与建树在同一短事务完成；不再维护另一套中间规格。
            async with config_manager.transaction():
                await info.activate()
                session = info.info.mode in (
                    TaskMode.SCRIPT_CONFIG,
                    TaskMode.SCRIPT_VIEW,
                )
                if session and len(node.children) != 1:
                    raise ValueError(
                        "配置和查看会话必须指定一个托管及一个用户或 default"
                    )
                queue_id = None if session or node.uid == "-" else UUID(node.uid)
                queue = Config.QueueConfig.get(queue_id) if queue_id else None
                if queue_id and queue is None:
                    raise ValueError(f"队列不存在：{queue_id}")
                if (
                    desktop
                    and queue is not None
                    and queue.Info.AfterAccomplish != PowerSignal.NO_ACTION
                ):
                    raise UnsupportedDesktopTask("桌面分身不支持队列的电源操作")
                if not session and queue is None and not node.children:
                    raise ValueError("不选择队列时必须显式指定托管")
                if queue is None:
                    for child in node.children.values():
                        if Config.ScriptConfig.is_unresolved(child.uid):
                            raise ValueError(f"托管所属插件不可用：{child.uid}")
                selections = (
                    [node]
                    if session
                    else select(
                        node.children,
                        (
                            uid
                            for uid, item in queue.QueueItem.items()
                            if item.Info.ScriptId != "-"
                        )
                        if queue is not None
                        else Config.ScriptConfig.keys(),
                    )
                )
                script_classes = Config.script_classes
                for selected in selections:
                    item = queue.QueueItem[UUID(selected.uid)] if queue else None
                    script_id = item.Info.ScriptId if item else str(UUID(selected.uid))
                    if Config.ScriptConfig.is_unresolved(script_id):
                        # 托管原样保留着、等所属插件恢复：队列里跳过它，不拖累同队列的其他项。
                        if item is not None:
                            logger.warning(
                                f"队列项引用的托管所属插件不可用，已跳过：{script_id}"
                            )
                            continue
                        raise ValueError(f"托管所属插件不可用：{script_id}")
                    entry = Config.ScriptConfig.get(script_id)
                    if entry is None:
                        raise ValueError(f"托管不存在：{script_id}")
                    if desktop:
                        from app.core.desktop_session.lifecycle import (
                            require_task_support,
                        )

                        require_task_support(entry)
                    sid = info.scripts.add(
                        TaskScriptItem,
                        payload={
                            "info": {
                                "script_id": str(entry.uid),
                                "script_type": next(
                                    (
                                        name
                                        for name, cls in script_classes.items()
                                        if type(entry) is cls
                                    ),
                                    type(entry).__name__,
                                ),
                                "name": script_config_name(entry),
                                "params": deepcopy(selected.params),
                            }
                        },
                    )
                    await info.scripts.commit()
                    script = info.scripts[sid]
                    script._config_ref = ref(entry)
                    script._run_days = tuple(item.Schedule.Days) if item else None
                    user_configs = (
                        entry.users
                        if isinstance(entry, ScriptEntry)
                        else entry.UserData
                    )
                    users = (
                        selected.children.values()
                        if session
                        else select(selected.children, user_configs.keys())
                    )
                    for user in users:
                        if user.children:
                            raise ValueError("用户节点不能包含子项")
                        shared = session and user.uid == "default"
                        config = None if shared else user_configs.get(UUID(user.uid))
                        if not shared and config is None:
                            raise ValueError(f"用户不属于托管：{user.uid}")
                        uid = script.users.add(
                            TaskUserItem,
                            payload={
                                "info": {
                                    "user_id": "default"
                                    if shared
                                    else str(UUID(user.uid)),
                                    "name": (
                                        config.info.name
                                        if isinstance(config, UserEntry)
                                        else config.Info.Name
                                    )
                                    if config is not None
                                    else "共享配置",
                                    "params": deepcopy(user.params),
                                }
                            },
                        )
                        await script.users.commit()
                        script.users[uid]._config_ref = (
                            ref(config) if config is not None else None
                        )
                info.info.name = (
                    queue.Info.Name
                    if queue is not None
                    else "、".join(script.info.name for script in info.scripts.values())
                )
                if queue is not None:
                    # 队列只在 L1 读取；删改原配置不改变本轮附加动作。
                    info.execution.script_before = (
                        queue.Info.ScriptBeforeTask
                        if queue.Info.IfScriptBeforeTask
                        else None
                    )
                    info.execution.script_after = (
                        queue.Info.ScriptAfterTask
                        if queue.Info.IfScriptAfterTask
                        else None
                    )
                    info.execution.after_accomplish = queue.Info.AfterAccomplish
                    info.execution.after_accomplish_delay = (
                        queue.Info.AfterAccomplishDelay
                    )
                await info.commit()
                # 时间表示成功受理，不等执行开始或完成；与完整建树共用原子边界。
                now = datetime.now().astimezone()
                if queue is not None:
                    if Config.QueueConfig.get(queue.uid) is not queue:
                        raise ValueError("队列已删除或替换")
                    if info.info.trigger == TaskTriggerReason.STARTUP:
                        queue.Data.LastStartupTime = now
                    if info.info.trigger == TaskTriggerReason.TIMED:
                        queue.Data.LastTimedStart = now
                    if info.info.trigger == TaskTriggerReason.CYCLE:
                        queue.Cycle.LastRunAt = now
                    await queue.commit()
            if queue is not None:
                run.target_id = str(queue.uid)
            elif len(info.scripts) == 1:
                run.target_id = info.script_id
            self._running[info.uid] = run
            # 维护任务可按 ID 查询和停止，但不创建普通调度面板。
            if not run.maintenance:
                await Publisher.send(
                    id=protocol.ID_TASK_MANAGER,
                    type=protocol.TASK_CREATED,
                    data=WSTaskCreatedData(
                        taskId=str(info.uid),
                        mode=info.info.mode,
                        trigger=info.info.trigger,
                        taskName=info.info.name,
                        targetId=run.target_id,
                        scripts=[
                            WSTaskScriptIdentityData(
                                scriptId=script.info.script_id,
                                scriptType=script.info.script_type,
                            )
                            for script in info.scripts.values()
                        ],
                    ),
                )
            run.start()
            if info.info.status == "cancelled":
                await run.stop()
        except BaseException:
            if self._running.get(info.uid) is run:
                try:
                    await run.stop()
                finally:
                    self._running.pop(info.uid, None)
                    info.clear_log_cursor()
            raise
        finally:
            self._creating -= 1
            if not self._creating:
                self._idle.set()
        return info.uid

    async def stop_task(self, task_id: str | UUID) -> None:
        """[兼容旧调用方] 停止方法旧名；新代码直接调用 stop()。"""
        await self.stop(task_id)

    async def stop(self, task_id: str | UUID) -> None:
        """停止指定任务或 ALL，并等待对应执行器完成收尾。

        单个任务不存在时直接返回。ALL 串行处理：关闭新受理、取消待执行电源动作，
        等待创建流程结清，再停止当前全部执行器，最后解除受理屏障。
        """
        if task_id != "ALL":
            uid = UUID(str(task_id))
            run = self._running.get(uid)
            if run is not None:
                await run.stop()
            return
        async with self._stop_lock:
            self._stopping_all = True
            try:
                from app.core import Power

                await Power.cancel_power_task()
                await self._idle.wait()
                await asyncio.gather(
                    *(run.stop() for run in list(self._running.values()))
                )
            finally:
                self._stopping_all = False

    def _prune_recent(self) -> None:
        """按最旧记录优先清理最近终态，最多保留 200 项及结束后 30 分钟。

        由任务结束或查询触发，使用单调时钟计算年龄；与持久化执行历史分开。
        """
        while self._recent:
            task = next(iter(self._recent.values()))
            if len(self._recent) <= 200 and time.monotonic() - task.ended_at <= 1800:
                break
            self._recent.popitem(last=False)

        remaining = _RECENT_ANALYSIS_BYTES
        for task in reversed(self._recent.values()):
            for path in reversed(tuple(task.analysis_sizes)):
                size = task.analysis_sizes[path]
                if size <= remaining:
                    remaining -= size
                else:
                    script_id, user_id = path
                    task.tree["scripts"]["data"][script_id]["users"]["data"][
                        user_id
                    ].pop("log_analysis", None)
                    del task.analysis_sizes[path]

        history_remaining = _RECENT_ANALYSIS_HISTORY_BYTES
        for task in reversed(self._recent.values()):
            for path in reversed(tuple(task.observations)):
                size = task.observations[path].retained_bytes
                if size <= history_remaining:
                    history_remaining -= size
                else:
                    del task.observations[path]

    def read_log_analysis(
        self,
        task_id: UUID,
        *,
        script_run_id: UUID,
        user_run_id: UUID,
        after: ObservationCursor | None = None,
        limit: int = 50,
    ) -> TaskLogAnalysisRead | None:
        """按实际运行查询节点。变更历史淘汰后仍可返回保留的最终结果。"""
        if (run := self._running.get(task_id)) is not None:
            script = run.task_info.scripts.get(script_run_id)
            user = script.users.get(user_run_id) if script is not None else None
            if user is None:
                return None
            observation = user.log_analysis_observation
            final = (
                (user.log_analysis.nodes, user.log_analysis.close_reason)
                if user.log_analysis.close_reason is not None
                else None
            )
        else:
            self._prune_recent()
            recent = self._recent.get(task_id)
            if recent is None:
                return None
            script_id, user_id = str(script_run_id), str(user_run_id)
            observation = recent.observations.get((script_id, user_id))
            script_data = recent.tree["scripts"]["data"].get(script_id)
            user_data = (
                script_data["users"]["data"].get(user_id) if script_data else None
            )
            analysis = user_data.get("log_analysis") if user_data else None
            final = (
                (
                    tuple(Node.model_validate(node) for node in analysis["nodes"]),
                    analysis["close_reason"],
                )
                if analysis is not None and observation is None
                else None
            )
        if observation is None:
            if final is None:
                return None
            if after is not None:
                raise InvalidObservationCursor("日志变更历史已过期，请重新读取快照")
            nodes, close_reason = final
            return TaskLogAnalysisRead(nodes, None, False, close_reason)
        if after is None:
            snapshot = observation.capture()
            return TaskLogAnalysisRead(
                tuple(public_log_node(node) for node in snapshot.nodes),
                snapshot.cursor,
                False,
                snapshot.close_reason,
            )
        page = observation.read(after=after, limit=limit)
        return TaskLogAnalysisRead(
            tuple(public_log_node(node) for node in page.nodes),
            page.cursor,
            page.has_more,
            page.close_reason,
        )

    def describe_lock_holders(self, config: ConfigNode, *, cascade: bool) -> str:
        """只诊断当前冲突票据；从实际执行器查询占用者，不建立另一份锁登记。"""
        nodes = [config]
        if cascade:
            for node in nodes:
                nodes.extend(node.iter_children())
        # 配置框架未公开占用者查询；仅只读核对现有 token，不修改锁或凭证。
        tokens = {token for node in nodes for token in node._lock_s}
        tokens.update(node._lock_x for node in nodes if node._lock_x is not None)
        holders: list[str] = []
        for run in self._running.values():
            tickets = [run._script_ticket]
            if run._plugin is not None:
                tickets.append(run._plugin._user_ticket)
            if run._manager is not None:
                tickets.extend(run._manager.config_locks.values())
            matched = {
                ticket.token for ticket in tickets if ticket is not None
            } & tokens
            if matched:
                holders.append(
                    f"任务「{run.task_info.info.name}」（{run.task_info.task_id}）"
                )
                tokens.difference_update(matched)
        if tokens or not holders:
            holders.append("其他配置操作（占用者未知）")
        return "、".join(holders)

    @staticmethod
    def _export_task(
        info: TaskItem, *, include_log_analysis: bool = False
    ) -> dict[str, Any]:
        tree = info.model_dump()
        for script in tree["scripts"]["data"].values():
            for user in script["users"]["data"].values():
                analysis = user.get("log_analysis")
                if (
                    not include_log_analysis
                    or not analysis
                    or analysis["close_reason"] is None
                ):
                    user.pop("log_analysis", None)
        return tree

    @staticmethod
    def _omit_cached_analysis(tree: dict[str, Any]) -> dict[str, Any]:
        scripts = tree["scripts"]
        return {
            **tree,
            "scripts": {
                **scripts,
                "data": {
                    script_id: {
                        **script,
                        "users": {
                            **script["users"],
                            "data": {
                                user_id: {
                                    key: value
                                    for key, value in user.items()
                                    if key != "log_analysis"
                                }
                                for user_id, user in script["users"]["data"].items()
                            },
                        },
                    }
                    for script_id, script in scripts["data"].items()
                },
            },
        }

    def get_task(
        self, task_id: str | UUID, *, include_log_analysis: bool = False
    ) -> dict[str, Any] | None:
        """按运行 UUID 查询运行中或最近完成的任务树。"""
        uid = UUID(str(task_id))
        if (run := self._running.get(uid)) is not None:
            tree = self._export_task(
                run.task_info, include_log_analysis=include_log_analysis
            )
            return TaskTreeData.model_validate(tree).model_dump(mode="json")
        self._prune_recent()
        if (recent := self._recent.get(uid)) is None:
            return None
        return (
            recent.tree
            if include_log_analysis or not recent.analysis_sizes
            else self._omit_cached_analysis(recent.tree)
        )

    def get_task_status(self, task_id: str) -> TaskStatusOut | None:
        """从完整任务树生成轻量状态响应，将 pending 映射为 running。

        当前复用 get_task 导出完整树后提取状态、模式、触发原因与结果；未命中返回 None。
        """
        tree = self.get_task(task_id)
        if tree is None:
            return None
        info = tree["info"]
        # 与 get_task 一样按标准 UUID 取终态缓存，大写等合法写法也能取到结束时间。
        recent = self._recent.get(UUID(str(task_id)))
        return TaskStatusOut(
            taskId=str(task_id),
            status="running" if info["status"] == "pending" else info["status"],
            mode=info["mode"],
            trigger=info["trigger"],
            detail=info["result"],
            finishedAt=recent.finished_at
            if recent and info["status"] != "pending"
            else None,
        )

    def get_runtime_snapshot(self) -> TaskRuntimeSnapshot:
        """组装初次连接或重连快照：普通运行任务及完整日志基线。

        旧手动更新任务不出现在此列表；日志序号由模型判断能否作为追加基线。
        只读取实际运行树，不创建任务或更新排期时间。
        """
        items = []
        for run in self._running.values():
            info = run.task_info
            if run.maintenance:
                continue
            items.append(
                TaskRuntimeSnapshotItem.model_validate(
                    {
                        "taskId": info.task_id,
                        "mode": info.mode,
                        "trigger": info.info.trigger,
                        "scriptId": info.script_id,
                        "targetId": run.target_id,
                        "userId": info.user_id,
                        "stopping": run.cancelled,
                        "scripts": [
                            WSTaskScriptIdentityData(
                                scriptId=script.info.script_id,
                                scriptType=script.info.script_type,
                            )
                            for script in info.scripts.values()
                        ],
                        "task": self._export_task(info),
                        **info.get_log_snapshot(),
                    }
                )
            )
        return TaskRuntimeSnapshot(tasks=items)

    async def drop(self, run: ScriptExpander) -> None:
        """顶层 ended 后注销同一执行器、清理日志游标并缓存完整终态。

        重复或过期结束通知直接忽略；缓存随即按容量和年龄清理。
        注销及终态缓存完成后发出 task_ended，由 Power 等订阅者处理后续动作。
        """
        info = run.task_info
        registered = self._running.get(info.uid) is run
        if not registered:
            return
        self._running.pop(info.uid, None)
        info.clear_log_cursor()
        tree = TaskTreeData.model_validate(
            self._export_task(info, include_log_analysis=True)
        ).model_dump(mode="json")
        observations = {
            (str(script.uid), str(user.uid)): observation
            for script in info.scripts.values()
            for user in script.users.values()
            if (observation := user.log_analysis_observation) is not None
        }
        self._recent[info.uid] = _RecentTask(
            ended_at=time.monotonic(),
            tree=tree,
            finished_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            analysis_sizes={
                (script_id, user_id): len(
                    json.dumps(analysis, ensure_ascii=False).encode("utf-8")
                )
                for script_id, script in tree["scripts"]["data"].items()
                for user_id, user in script["users"]["data"].items()
                if (analysis := user.get("log_analysis")) is not None
            },
            observations=observations,
        )
        self._prune_recent()
        await self.task_ended.send_async(self, task=info)


TaskManager = _TaskManager()

__all__ = ["TaskManager"]
