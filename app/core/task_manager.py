#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import uuid
import asyncio
import os
from pathlib import Path
from datetime import datetime
from typing import Dict, Literal

from .config import (
    Config,
    MaaConfig,
    SrcConfig,
    GeneralConfig,
    MaaEndConfig,
    M9AConfig,
    OkwwConfig,
    OkNteConfig,
    HSRConfig,
    BetterGIConfig,
)

# 延迟加载 System，避免 app.services 初始化期间触发循环导入；
# 绑定为模块级 LazyProxy（真实对象引用），函数体裸名 System 才能经
# LOAD_GLOBAL 正常解析（模块级 __getattr__ 只管属性访问、管不到裸名）。
from app.models.task import (
    ScriptItem,
    TaskExecuteBase,
    TaskItem,
    TaskTriggerSource,
    UserItem,
)
from app.utils import LazyProxy, get_logger
from app.task import (
    MaaManager,
    SrcManager,
    GeneralManager,
    MaaEndManager,
    M9AManager,
    OkwwManager,
    OkNteManager,
    HSRManager,
    BetterGIManager,
)
from app.utils.constants import POWER_SIGN_MAP

System = LazyProxy("app.services", "System")


logger = get_logger("业务调度")


class _ScriptTaskReservations:
    """为脚本任务提供原子、带所有者的进程内占用。"""

    def __init__(self) -> None:
        self._owners: dict[tuple[str, str], str] = {}
        self._owner_keys: dict[str, dict[uuid.UUID, set[tuple[str, str]]]] = {}
        self._src_root_paths: dict[str, Path] = {}

    @staticmethod
    def _resource_keys(
        script_uid: uuid.UUID,
        src_root_path: Path | None,
    ) -> set[tuple[str, str]]:
        keys = {("script", str(script_uid))}
        if src_root_path is not None:
            keys.add(("src-root", _normalize_src_root_path(src_root_path.resolve())))
        return keys

    def try_acquire(
        self,
        script_uid: uuid.UUID,
        owner: str,
        *,
        src_root_path: Path | None = None,
    ) -> bool:
        resolved_root_path = (
            src_root_path.resolve() if src_root_path is not None else None
        )
        keys = self._resource_keys(script_uid, resolved_root_path)
        if any(self._owners.get(key) not in (None, owner) for key in keys):
            return False

        root_key = next((key for key in keys if key[0] == "src-root"), None)
        if root_key is not None and resolved_root_path is not None:
            root_path = _normalize_src_root_path(resolved_root_path)
            for key, existing_owner in self._owners.items():
                if key[0] != "src-root" or existing_owner == owner:
                    continue
                existing_src_root_path = self._src_root_paths.get(key)
                if existing_src_root_path is None:
                    continue
                existing_root_path = _normalize_src_root_path(existing_src_root_path)
                if (
                    root_path == existing_root_path
                    or _is_relative_src_root(root_path, existing_root_path)
                    or _is_relative_src_root(existing_root_path, root_path)
                ):
                    return False

        for key in keys:
            self._owners[key] = owner
        self._owner_keys.setdefault(owner, {}).setdefault(script_uid, set()).update(keys)
        if root_key is not None and resolved_root_path is not None:
            self._src_root_paths[root_key] = resolved_root_path
        return True

    def release(self, script_uid: uuid.UUID, owner: str) -> bool:
        script_key = ("script", str(script_uid))
        if self._owners.get(script_key) != owner:
            return False
        keys = self._owner_keys.get(owner, {}).pop(script_uid, set())
        for key in keys:
            key_still_reserved = any(
                key in other_keys
                for other_keys in self._owner_keys.get(owner, {}).values()
            )
            if not key_still_reserved and self._owners.get(key) == owner:
                self._owners.pop(key)
            if key[0] == "src-root":
                if not key_still_reserved:
                    self._src_root_paths.pop(key, None)
        if not self._owner_keys.get(owner):
            self._owner_keys.pop(owner, None)
        return True


def _normalize_src_root_path(path: Path) -> str:
    return os.path.normcase(str(path)).casefold()


def _is_relative_src_root(path: Path | str, parent: Path | str) -> bool:
    path = str(path)
    parent = str(parent)
    return path.startswith(parent + os.sep)


def _get_src_root_path(script_config: object) -> Path | None:
    """返回需要跨配置互斥的 SRC 安装根目录。"""

    if not isinstance(script_config, SrcConfig):
        return None
    return Path(script_config.get("Info", "Path"))


class TaskInfo(TaskItem):

    async def on_change(self):
        await Config.send_websocket_message(
            id=self.task_id,
            type="Update",
            data={"task_info": self.asdict},
        )
        if self.current_index != -1:
            await Config.send_websocket_message(
                id=self.task_id,
                type="Update",
                data={"log": self.script_list[self.current_index].log},
            )


class Task(TaskExecuteBase):

    def __init__(
        self,
        task_info: TaskInfo,
        script_reservations: _ScriptTaskReservations | None = None,
    ):
        super().__init__()
        self.task_info = task_info
        self.script_reservations = script_reservations or _ScriptTaskReservations()
        self.is_closing = False

    async def prepare(self):

        # 初始化任务列表
        script_ids = (
            [
                queue_item.get("Info", "ScriptId")
                for queue_item in Config.QueueConfig[
                    uuid.UUID(self.task_info.queue_id)
                ].QueueItem.values()
                if queue_item.get("Info", "ScriptId") != "-"
            ]
            if self.task_info.script_id is None
            else [self.task_info.script_id]
        )

        self.task_info.script_list = [
            ScriptItem(
                script_id=script_id,
                status="等待",
                name=Config.ScriptConfig[uuid.UUID(script_id)].get("Info", "Name"),
                user_list=[
                    UserItem(user_id=str(uuid.uuid4()), name="暂未加载", status="等待")
                ],
            )
            for script_id in script_ids
        ]

        logger.success(
            f"任务 {self.task_info.task_id} 检索完成，包含 {len(self.task_info.script_list)} 个脚本项"
        )

    async def main_task(self):

        # MAS 调度触发的签到先完成，结果随本次脚本完成通知汇总；手动签到按钮不经过此处。
        if self.task_info.mode == "AutoProxy":
            from app.core.timer import MainTimer

            sign_source = {
                "scheduled_task": "task_scheduled",
                "manual_task": "task_manual",
                "startup_task": "task_startup",
            }.get(self.task_info.trigger_source, "task_manual")
            self.task_info.game_sign_results = (
                await MainTimer.try_game_sign_for_task(source=sign_source)
            )

        await self.prepare()

        logger.info(
            f"开始运行任务: {self.task_info.task_id}, 模式: {self.task_info.mode}"
        )

        # 可选：从指定脚本开始执行（仅队列任务）
        start_index = 0
        if (
            getattr(self.task_info, "resume_from_script_id", None)
            and self.task_info.queue_id is not None
        ):
            resume_id = str(self.task_info.resume_from_script_id)
            for idx, item in enumerate(self.task_info.script_list):
                if item.script_id == resume_id:
                    start_index = idx
                    break
            else:
                logger.warning(
                    f"未找到 resume_from_script_id={resume_id}，将从队列首项开始执行"
                )

        for i in range(start_index):
            self.task_info.script_list[i].status = "跳过"

        # 依次运行任务
        for self.task_info.current_index in range(
            start_index, len(self.task_info.script_list)
        ):
            script_item = self.task_info.script_list[self.task_info.current_index]
            current_script_uid = uuid.UUID(script_item.script_id)

            # 检查任务对应脚本是否仍存在
            if current_script_uid not in Config.ScriptConfig:
                script_item.status = "异常"
                logger.info(f"跳过任务: {current_script_uid}, 该任务对应脚本已被删除")
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={"Error": f"任务 {script_item.name} 对应脚本已被删除"},
                )
                continue

            # 原子占用脚本，避免两个调度器同时通过布尔锁前置检查。
            reservation_owner = self.task_info.task_id
            script_config = Config.ScriptConfig[current_script_uid]
            src_root_path = _get_src_root_path(script_config)
            if not self.script_reservations.try_acquire(
                current_script_uid,
                reservation_owner,
                src_root_path=src_root_path,
            ):
                script_item.status = "跳过"
                logger.info(
                    f"跳过任务: {current_script_uid}, 该任务已被其他任务调度器锁定"
                )
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={"Warning": f"任务 {script_item.name} 已被其他任务调度器锁定"},
                )
                continue

            try:
                if script_config.is_locked:
                    script_item.status = "跳过"
                    logger.info(f"跳过任务: {current_script_uid}, 该任务配置已被锁定")
                    await Config.send_websocket_message(
                        id=self.task_info.task_id,
                        type="Info",
                        data={"Warning": f"任务 {script_item.name} 已被锁定"},
                    )
                    continue

                # 标记为运行中
                script_item.status = "运行"
                logger.info(f"任务开始: {current_script_uid}")

                if isinstance(script_config, MaaConfig):
                    task_item = MaaManager(script_item)
                elif isinstance(script_config, SrcConfig):
                    if src_root_path is None:
                        raise RuntimeError("SRC 路径占用未初始化")
                    task_item = SrcManager(
                        script_item,
                        reserved_src_root_path=src_root_path,
                        reserve_src_root=lambda root_path,
                        script_uid=current_script_uid,
                        owner=reservation_owner: self.script_reservations.try_acquire(
                            script_uid,
                            owner,
                            src_root_path=root_path,
                        ),
                    )
                elif isinstance(script_config, GeneralConfig):
                    task_item = GeneralManager(script_item)
                elif isinstance(script_config, OkwwConfig):
                    task_item = OkwwManager(script_item)
                elif isinstance(script_config, OkNteConfig):
                    task_item = OkNteManager(script_item)
                elif isinstance(script_config, MaaEndConfig):
                    task_item = MaaEndManager(script_item)
                elif isinstance(script_config, M9AConfig):
                    task_item = M9AManager(script_item)
                elif isinstance(script_config, HSRConfig):
                    task_item = HSRManager(script_item)
                elif isinstance(script_config, BetterGIConfig):
                    task_item = BetterGIManager(script_item)
                else:
                    logger.error(
                        f"不支持的脚本类型: {type(script_config).__name__}"
                    )
                    await Config.send_websocket_message(
                        id=self.task_info.task_id,
                        type="Info",
                        data={"Error": "脚本类型不支持"},
                    )
                    continue

                # 运行任务
                await self.spawn(task_item)
            finally:
                self.script_reservations.release(current_script_uid, reservation_owner)

    async def final_task(self) -> None:

        logger.info(f"任务结束: {self.task_info.task_id}")

        await Config.send_websocket_message(
            id=str(self.task_info.task_id),
            type="Signal",
            data={"Accomplish": self.task_info.result},
        )

        if (
            not self.is_closing
            and self.task_info.mode == "AutoProxy"
            and self.task_info.queue_id is not None
        ):

            if Config.power_sign == "NoAction":
                Config.power_sign = Config.QueueConfig[
                    uuid.UUID(self.task_info.queue_id)
                ].get("Info", "AfterAccomplish")
                await Config.send_websocket_message(
                    id="Main", type="Update", data={"PowerSign": Config.power_sign}
                )

    async def on_crash(self, e: Exception) -> None:
        logger.exception(f"任务 {self.task_info.task_id} 出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"任务出现异常: {type(e).__name__}: {str(e)}"},
        )


class _TaskManager:
    """业务调度器"""

    def __init__(self):
        super().__init__()

        self.task_info: Dict[uuid.UUID, TaskInfo] = {}
        self.task_handler: Dict[uuid.UUID, Task] = {}
        self._script_reservations = _ScriptTaskReservations()
        self._startup_queue_started = False
        self._startup_queue_running = False

    async def add_task(
        self,
        mode: Literal["AutoProxy", "ScriptConfig", "Update"],
        id: str,
        new_task_info: dict | None = None,
        resume_from_script_id: str | None = None,
        trigger_source: TaskTriggerSource = "manual_task",
    ) -> uuid.UUID:
        """
        添加任务, 根据 id 值搜索实际指向的任务配置

        Args:
            mode (str): 任务模式
            id (str): 任务项对应的配置 ID
            new_task_info (dict): 新任务项信息. Defaults to {}.
            trigger_source: MAS 任务触发来源，API 手动启动默认 manual_task。

        Returns:
            uuid.UUID: 任务 UID
        """

        uid = uuid.UUID(id)

        if mode in ("ScriptConfig", "Update"):
            if uid in Config.ScriptConfig:
                task_uid = uuid.uuid4()
                queue_id = None
                script_uid = uid
                user_uid = "Default"
            else:
                for script_id, script in Config.ScriptConfig.items():
                    if uid in script.UserData:
                        task_uid = uuid.uuid4()
                        queue_id = None
                        script_uid = script_id
                        user_uid = uid
                        break
                else:
                    raise ValueError(f"任务 {uid} 无法找到对应脚本配置")
        elif uid in Config.QueueConfig:
            task_uid = uuid.uuid4()
            queue_id = uid
            script_uid = None
            user_uid = None
        elif uid in Config.ScriptConfig:
            task_uid = uuid.uuid4()
            queue_id = None
            script_uid = uid
            user_uid = None
        else:
            raise ValueError(f"任务 {uid} 无法找到对应脚本配置")

        reservation_owner = str(task_uid)
        reservation_acquired = False
        if script_uid is not None:
            script_config = Config.ScriptConfig[script_uid]
            if script_config.is_locked or not self._script_reservations.try_acquire(
                script_uid,
                reservation_owner,
                src_root_path=_get_src_root_path(script_config),
            ):
                raise RuntimeError(f"任务 {script_config.get('Info', 'Name')} 已在运行")
            reservation_acquired = True

        try:
            logger.info(
                f"创建任务: {task_uid}, 模式: {mode}, 触发来源: {trigger_source}"
            )
            if new_task_info:
                new_task_info["newTask"] = str(task_uid)
                await Config.send_websocket_message(
                    id="TaskManager", type="Signal", data=new_task_info
                )
            self.task_info[task_uid] = TaskInfo(
                mode=mode,
                task_id=str(task_uid),
                queue_id=str(queue_id) if queue_id else None,
                script_id=str(script_uid) if script_uid else None,
                user_id=str(user_uid) if user_uid else None,
                resume_from_script_id=resume_from_script_id,
                trigger_source=trigger_source,
            )
            self.task_handler[task_uid] = Task(
                self.task_info[task_uid], self._script_reservations
            )
            self.task_handler[task_uid].execute()
            asyncio.create_task(self.clean_task(task_uid))
        except BaseException:
            if reservation_acquired and script_uid is not None:
                self._script_reservations.release(script_uid, reservation_owner)
            self.task_handler.pop(task_uid, None)
            self.task_info.pop(task_uid, None)
            raise

        return task_uid

    async def clean_task(self, task_uid: uuid.UUID) -> None:

        task_info = self.task_info[task_uid]
        try:
            await self.task_handler[task_uid].accomplish.wait()
        finally:
            if task_info.script_id is not None:
                self._script_reservations.release(
                    uuid.UUID(task_info.script_id), task_info.task_id
                )

        power_enabled = bool(task_info.mode != "ScriptConfig")
        self.task_info.pop(task_uid, None)
        self.task_handler.pop(task_uid, None)

        if (
            power_enabled
            and len(self.task_handler) == 0
            and Config.power_sign != "NoAction"
        ):
            logger.info(f"所有任务已结束，准备执行电源操作: {Config.power_sign}")
            await Config.send_websocket_message(
                id="Main",
                type="Message",
                data={
                    "type": "Countdown",
                    "title": f"{POWER_SIGN_MAP[Config.power_sign]}倒计时",
                    "message": f"程序将在倒计时结束后执行 {POWER_SIGN_MAP[Config.power_sign]} 操作",
                },
            )
            await System.start_power_task()

    async def stop_task(self, task_id: str) -> None:
        """
        中止任务

        :param task_id: 任务ID
        """

        logger.info(f"中止任务: {task_id}")

        if task_id == "ALL":
            task_item_list = list(self.task_handler.values())

            # 主动停止全部任务时，禁止触发队列完成后的电源操作
            Config.power_sign = "NoAction"
            for task_item in task_item_list:
                if not task_item.is_closing:
                    task_item.is_closing = True
                    task_item.cancel()

            if System.power_task is not None and not System.power_task.done():
                await System.cancel_power_task()

            await asyncio.gather(
                *(task_item.accomplish.wait() for task_item in task_item_list)
            )
            await Config.send_websocket_message(
                id="Main", type="Update", data={"PowerSign": Config.power_sign}
            )
        else:
            uid = uuid.UUID(task_id)
            if uid not in self.task_handler:
                # 任务已经结束时，中止操作仍视为成功。
                return
            if self.task_handler[uid].is_closing:
                raise RuntimeError("任务已在中止中")
            self.task_handler[uid].is_closing = True
            self.task_handler[uid].cancel()
            logger.info(f"等待任务 {task_id} 结束...")
            await self.task_handler[uid].accomplish.wait()
            logger.info(f"任务 {task_id} 已结束")

    async def start_startup_queue(self):
        """开始运行启动时运行的调度队列"""

        if self._startup_queue_started:
            logger.info("启动时任务已触发，跳过重复运行")
            return
        if self._startup_queue_running:
            logger.info("启动时任务正在等待运行，跳过重复触发")
            return

        self._startup_queue_running = True
        curday = datetime.now().strftime("%Y-%m-%d")

        try:
            await asyncio.sleep(10)

            if Config.websocket is None:
                logger.info("主 WebSocket 已断开，启动时任务等待下次连接后运行")
                return

            self._startup_queue_started = True
            logger.info("开始运行启动时任务")
            for uid, queue in Config.QueueConfig.items():

                StartUpMode = queue.get("Info", "StartUpMode")
                if StartUpMode == "Always":
                    logger.info(f"启动时需要运行的队列：{uid}")
                    await TaskManager.add_task(
                        "AutoProxy",
                        str(uid),
                        new_task_info={
                            "queueId": str(uid),
                            "taskName": f"队列 - {queue.get('Info', 'Name')}",
                            "taskType": "启动时代理",
                        },
                        trigger_source="startup_task",
                    )
                    await queue.set("Data", "LastStartupTime", curday)

                elif StartUpMode == "DailyFirst":
                    # 检查 DailyFirst 模式是否已在今日运行过
                    if queue.get("Data", "LastStartupTime") == curday:
                        logger.info(
                            f"队列 {uid} 已在今日运行过，跳过该次运行"
                        )
                        continue

                    logger.info(f"启动时需要运行的队列：{uid}")
                    await TaskManager.add_task(
                        "AutoProxy",
                        str(uid),
                        new_task_info={
                            "queueId": str(uid),
                            "taskName": f"队列 - {queue.get('Info', 'Name')}",
                            "taskType": "启动时代理",
                        },
                        trigger_source="startup_task",
                    )
                    await queue.set("Data", "LastStartupTime", curday)
                
        finally:
            self._startup_queue_running = False

        logger.success("启动时任务开始运行")


TaskManager = _TaskManager()
