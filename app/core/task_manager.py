#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import uuid
import asyncio
from typing import Dict, Literal

from .config import Config, MaaConfig, GeneralConfig
from app.services import System
from app.models.task import TaskItem, ScriptItem, UserItem, TaskExecuteBase
from app.utils import get_logger
from app.task import MaaManager, GeneralManager
from app.utils.constants import POWER_SIGN_MAP


logger = get_logger("业务调度")


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

    def __init__(self, task_info: TaskInfo):
        super().__init__()
        self.task_info = task_info
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

        await self.prepare()

        logger.info(
            f"开始运行任务: {self.task_info.task_id}, 模式: {self.task_info.mode}"
        )

        # 依次运行任务
        for self.task_info.current_index, script_item in enumerate(
            self.task_info.script_list
        ):
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

            # 检查任务是否已被其他任务调度器锁定
            if Config.ScriptConfig[current_script_uid].is_locked:
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

            # 标记为运行中
            script_item.status = "运行"
            logger.info(f"任务开始: {current_script_uid}")

            if isinstance(Config.ScriptConfig[current_script_uid], MaaConfig):
                task_item = MaaManager(script_item)
            elif isinstance(Config.ScriptConfig[current_script_uid], GeneralConfig):
                task_item = GeneralManager(script_item)
            else:
                logger.error(
                    f"不支持的脚本类型: {type(Config.ScriptConfig[current_script_uid]).__name__}"
                )
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={"Error": "脚本类型不支持"},
                )
                continue

            # 运行任务
            await self.spawn(task_item)

    async def final_task(self) -> None:

        logger.info(f"任务结束: {self.task_info.task_id}")

        await Config.send_websocket_message(
            id=str(self.task_info.task_id),
            type="Signal",
            data={"Accomplish": self.task_info.result},
        )

        if self.task_info.mode == "AutoProxy" and self.task_info.queue_id is not None:

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

    async def add_task(
        self, mode: Literal["AutoProxy", "ManualReview", "ScriptConfig"], id: str
    ) -> uuid.UUID:
        """
        添加任务, 根据 id 值搜索实际指向的任务配置

        Args:
            mode (str): 任务模式
            id (str): 任务项对应的配置 ID

        Returns:
            uuid.UUID: 任务 UID
        """

        uid = uuid.UUID(id)

        if mode == "ScriptConfig":
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

        if script_uid is not None and Config.ScriptConfig[script_uid].is_locked:
            raise RuntimeError(
                f"任务 {Config.ScriptConfig[script_uid].get('Info', 'Name')} 已在运行"
            )

        logger.info(f"创建任务: {task_uid}, 模式: {mode}")
        self.task_info[task_uid] = TaskInfo(
            mode=mode,
            task_id=str(task_uid),
            queue_id=str(queue_id) if queue_id else None,
            script_id=str(script_uid) if script_uid else None,
            user_id=str(user_uid) if user_uid else None,
        )
        self.task_handler[task_uid] = Task(self.task_info[task_uid])
        self.task_handler[task_uid].execute()
        asyncio.create_task(self.clean_task(task_uid))

        return task_uid

    async def clean_task(self, task_uid: uuid.UUID) -> None:

        await self.task_handler[task_uid].accomplish.wait()
        power_enabled = bool(self.task_info[task_uid].mode != "ScriptConfig")
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
            for task_item in task_item_list:
                if not task_item.is_closing:
                    task_item.cancel()
                    task_item.is_closing = True
                    await task_item.accomplish.wait()
        else:
            uid = uuid.UUID(task_id)
            if uid not in self.task_handler:
                raise ValueError("未找到对应任务")
            if self.task_handler[uid].is_closing:
                raise RuntimeError("任务已在中止中")
            self.task_handler[uid].cancel()
            self.task_handler[uid].is_closing = True
            logger.info(f"等待任务 {task_id} 结束...")
            await self.task_handler[uid].accomplish.wait()
            logger.info(f"任务 {task_id} 已结束")

    async def start_startup_queue(self):
        """开始运行启动时运行的调度队列"""

        logger.info("开始运行启动时任务")
        for uid, queue in Config.QueueConfig.items():

            if queue.get("Info", "StartUpEnabled"):
                logger.info(f"启动时需要运行的队列：{uid}")
                task_id = await TaskManager.add_task("AutoProxy", str(uid))
                await Config.send_websocket_message(
                    id="TaskManager",
                    type="Signal",
                    data={
                        "newTask": str(task_id),
                        "queueId": str(uid),
                        "taskName": f"队列 - {queue.get('Info', 'Name')}",
                        "taskType": "启动时代理",
                    },
                )

        logger.success("启动时任务开始运行")


TaskManager = _TaskManager()
