"""L1 任务受理、运行登记、查询与终态留存。"""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Callable, Iterable, Iterator, Mapping
from copy import deepcopy
from datetime import datetime
from types import MappingProxyType
from typing import TYPE_CHECKING, Any
from uuid import UUID
from weakref import ref

from pydantic import TypeAdapter

from app.config import ConfigEntry, ConfigNode, config_manager
from app.core import Config, Publisher
from app.core.ws import protocol
from app.models.config import CLASS_BOOK
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

logger = get_logger("任务调度")
_selection = TypeAdapter(dict[int, TaskSelectionNode])

if TYPE_CHECKING:
    from app.models.config import QueueConfig, ScriptConfigType
    from app.models.task import TaskScriptItem
    from app.task.user_expander import UserExpander

type PluginExpander = Callable[[TaskScriptItem, ScriptConfigType], UserExpander | None]


class _TaskManager:
    def __init__(self, *, plugin_expander: PluginExpander | None = None) -> None:
        """初始化执行能力、运行登记、终态缓存，以及创建与停止全部的同步状态。"""
        self.plugin_expander = plugin_expander
        self.manager_factories: Mapping[type[ConfigEntry], ManagerFactory | None] = (
            MappingProxyType({})
        )
        self._factories_bound = False
        self._running: dict[UUID, ScriptExpander] = {}
        self._recent: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self._stopping_all = False
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
        """创建前检查停止全部屏障，并确认宿主已提供旧工厂或插件解析能力。"""
        if self._stopping_all:
            raise RuntimeError("正在停止全部任务，暂不接受新任务")
        if not self._factories_bound and self.plugin_expander is None:
            raise RuntimeError("宿主尚未绑定专项执行工厂")

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
        """[兼容旧专项] 旧手动更新入口；普通任务使用 start()，新专项维护能力放在专项业务入口。

        目标由旧适配层解析，以 ScriptConfig 信息树承载隐藏的 Update 分支；
        共用创建与停止流程，不创建普通调度面板。
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
                if not session and queue is None and not node.children:
                    raise ValueError("不选择队列时必须显式指定托管")
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
                for selected in selections:
                    item = queue.QueueItem[UUID(selected.uid)] if queue else None
                    script_id = item.Info.ScriptId if item else str(UUID(selected.uid))
                    entry = Config.ScriptConfig.get(script_id)
                    if entry is None:
                        raise ValueError(f"托管不存在：{script_id}")
                    sid = info.scripts.add(
                        TaskScriptItem,
                        payload={
                            "info": {
                                "script_id": str(entry.uid),
                                "script_type": next(
                                    (
                                        name
                                        for name, cls in CLASS_BOOK.items()
                                        if type(entry) is cls
                                    ),
                                    "unknown",
                                ),
                                "name": entry.Info.Name,
                                "params": deepcopy(selected.params),
                            }
                        },
                    )
                    await info.scripts.commit()
                    script = info.scripts[sid]
                    script._config_ref = ref(entry)
                    script._run_days = tuple(item.Schedule.Days) if item else None
                    users = (
                        selected.children.values()
                        if session
                        else select(selected.children, entry.UserData.keys())
                    )
                    for user in users:
                        if user.children:
                            raise ValueError("用户节点不能包含子项")
                        shared = session and user.uid == "default"
                        config = None if shared else entry.UserData.get(UUID(user.uid))
                        if not shared and config is None:
                            raise ValueError(f"用户不属于托管：{user.uid}")
                        uid = script.users.add(
                            TaskUserItem,
                            payload={
                                "info": {
                                    "user_id": "default"
                                    if shared
                                    else str(UUID(user.uid)),
                                    "name": config.Info.Name
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
                    queue.Data.LastStartTime = now
                    if info.info.trigger == TaskTriggerReason.STARTUP:
                        queue.Data.LastStartupTime = now
                    if info.info.trigger == TaskTriggerReason.TIMED:
                        queue.Data.LastTimedStart = now
                    if info.info.trigger == TaskTriggerReason.CYCLE:
                        queue.Cycle.LastRunAt = now
                    await queue.commit()
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
                from app.services import System

                Config.power_sign = "NoAction"
                Config.power_delay = 0
                await System.cancel_pending_power_task()
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
            _, (at, _) = next(iter(self._recent.items()))
            if len(self._recent) <= 200 and time.monotonic() - at <= 1800:
                break
            self._recent.popitem(last=False)

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

    def get_task(self, task_id: str | UUID) -> dict[str, Any] | None:
        """按运行 UUID 查询完整任务树，包含全部日志；找不到时返回 None。

        优先读取运行中的热态树，再查询尚未过期的最近终态；非法 UUID 向外报错。
        """
        uid = UUID(str(task_id))
        run = self._running.get(uid)
        if run is not None:
            return TaskTreeData.model_validate(run.task_info.model_dump()).model_dump(
                mode="json"
            )
        self._prune_recent()
        recent = self._recent.get(str(uid))
        return recent[1] if recent else None

    def get_task_status(self, task_id: str) -> TaskStatusOut | None:
        """从完整任务树生成轻量状态响应，将 pending 映射为 running。

        当前复用 get_task 导出完整树后提取状态、模式、触发原因与结果；未命中返回 None。
        """
        tree = self.get_task(task_id)
        if tree is None:
            return None
        info = tree["info"]
        return TaskStatusOut(
            taskId=str(task_id),
            status="running" if info["status"] == "pending" else info["status"],
            mode=info["mode"],
            trigger=info["trigger"],
            detail=info["result"],
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
                        "userId": info.user_id,
                        "stopping": run.cancelled,
                        "scripts": [
                            WSTaskScriptIdentityData(
                                scriptId=script.info.script_id,
                                scriptType=script.info.script_type,
                            )
                            for script in info.scripts.values()
                        ],
                        "task": info.model_dump(),
                        **info.get_log_snapshot(),
                    }
                )
            )
        return TaskRuntimeSnapshot(tasks=items)

    async def drop(self, run: ScriptExpander) -> None:
        """顶层 ended 后注销同一执行器、清理日志游标并缓存完整终态。

        重复或过期结束通知直接忽略；缓存随即按容量和年龄清理。
        最后一个普通任务结束且满足设置时，先结清社区工作，再执行全局电源动作。
        """
        info = run.task_info
        registered = self._running.get(info.uid) is run
        if not registered:
            return
        self._running.pop(info.uid, None)
        info.clear_log_cursor()
        self._recent[info.task_id] = (
            time.monotonic(),
            TaskTreeData.model_validate(info.model_dump()).model_dump(mode="json"),
        )
        self._prune_recent()
        if (
            not self.task_info
            and not self._stopping_all
            and info.mode == TaskMode.AUTO_PROXY
            and Config.power_sign != "NoAction"
        ):
            from app.core import MainTimer
            from app.services import System

            await System.start_power_task(before_power=MainTimer.drain_community_tasks)


TaskManager = _TaskManager()


__all__ = ["TaskManager"]
