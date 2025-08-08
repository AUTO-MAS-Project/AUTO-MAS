#   AUTO_MAA:A MAA Multi Account Management and Automation Tool
#   Copyright © 2024-2025 DLmaster361

#   This file is part of AUTO_MAA.

#   AUTO_MAA is free software: you can redistribute it and/or modify
#   it under the terms of the GNU General Public License as published
#   by the Free Software Foundation, either version 3 of the License,
#   or (at your option) any later version.

#   AUTO_MAA is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU General Public License for more details.

#   You should have received a copy of the GNU General Public License
#   along with AUTO_MAA. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


import uuid
import asyncio
from fastapi import WebSocket
from typing import Dict, Optional

from .config import Config, MaaConfig, GeneralConfig, QueueConfig
from app.models.schema import TaskMessage
from app.utils import get_logger
from app.task import *


logger = get_logger("业务调度")


class _TaskManager:
    """业务调度器"""

    def __init__(self):
        super().__init__()

        self.task_dict: Dict[uuid.UUID, asyncio.Task] = {}
        self.connection_events: Dict[uuid.UUID, asyncio.Event] = {}
        self.websocket_dict: Dict[uuid.UUID, WebSocket] = {}

    async def add_task(self, mode: str, uid: str) -> uuid.UUID:
        """
        添加任务

        :param mode: 任务模式
        :param uid: 任务UID
        """

        actual_id = uuid.UUID(uid)

        if mode == "设置脚本":
            if actual_id in Config.ScriptConfig:
                task_id = actual_id
                actual_id = None
            else:
                for script_id, script in Config.ScriptConfig.items():
                    if (
                        isinstance(script, (MaaConfig | GeneralConfig))
                        and actual_id in script.UserData
                    ):
                        task_id = script_id
                        break
                else:
                    raise ValueError(
                        f"The task corresponding to UID {uid} could not be found."
                    )
        elif actual_id in Config.QueueConfig:
            task_id = actual_id
            actual_id = None
        elif actual_id in Config.ScriptConfig:
            task_id = uuid.uuid4()
        else:
            raise ValueError(f"The task corresponding to UID {uid} could not be found.")

        if task_id in self.task_dict:

            raise RuntimeError(f"The task {task_id} is already running.")

        logger.info(f"创建任务：{task_id}，模式：{mode}")

        # 创建任务实例并连接信号
        if task_id in self.connection_events:
            self.connection_events[task_id].clear()
        else:
            self.connection_events[task_id] = asyncio.Event()

        await self.connection_events[task_id].wait()

        if task_id not in self.websocket_dict:
            raise RuntimeError(f"The task {task_id} is not connected to a WebSocket.")

        logger.info(f"开始运行任务：{task_id}，模式：{mode}")

        self.task_dict[task_id] = asyncio.create_task(
            self.run_task(mode, task_id, actual_id)
        )
        self.task_dict[task_id].add_done_callback(
            lambda t: asyncio.create_task(self.remove_task(t, mode, task_id))
        )

        return task_id

    @logger.catch
    async def run_task(
        self, mode: str, task_id: uuid.UUID, actual_id: Optional[uuid.UUID]
    ):

        websocket = self.websocket_dict[task_id]

        if mode == "设置脚本":

            if isinstance(Config.ScriptConfig[task_id], MaaConfig):
                task_item = MaaManager(mode, task_id, actual_id, websocket)
            # elif isinstance(Config.ScriptConfig[task_id], GeneralConfig):
            #     task_item = GeneralManager(mode, task_id, actual_id, websocket)
            else:
                logger.error(
                    f"不支持的脚本类型：{Config.ScriptConfig[task_id].__class__.__name__}"
                )
                await websocket.send_json(
                    TaskMessage(
                        type="Info", data={"Error": "脚本类型不支持"}
                    ).model_dump()
                )
                return

            task = asyncio.create_task(task_item.run())
            task.add_done_callback(
                lambda t: asyncio.create_task(task_item.final_task(t))
            )

        else:

            if task_id in Config.QueueConfig:

                queue = Config.QueueConfig[task_id]
                if not isinstance(queue, QueueConfig):
                    logger.error(
                        f"不支持的队列类型：{Config.QueueConfig[task_id].__class__.__name__}"
                    )
                    await websocket.send_json(
                        TaskMessage(
                            type="Info", data={"Error": "队列类型不支持"}
                        ).model_dump()
                    )
                    return

                task_list = []
                for queue_item in queue.QueueItem.values():
                    uid = uuid.UUID(queue_item.get("Info", "ScriptId"))
                    task_list.append(
                        {
                            "script_id": str(uid),
                            "status": "等待",
                            "name": Config.ScriptConfig[uid].get("Info", "Name"),
                        }
                    )

            elif actual_id is not None and actual_id in Config.ScriptConfig:

                task_list = [{"script_id": str(actual_id), "status": "等待"}]

            for task in task_list:

                script_id = uuid.UUID(task["script_id"])

                # 检查任务是否在运行列表中
                if script_id in self.task_dict:

                    task["status"] = "跳过"
                    await websocket.send_json(
                        TaskMessage(
                            type="Update", data={"task_list": task_list}
                        ).model_dump()
                    )
                    logger.info(f"跳过任务：{script_id}，该任务已在运行列表中")
                    continue

                # 标记为运行中
                task["status"] = "运行"
                await websocket.send_json(
                    TaskMessage(
                        type="Update", data={"task_list": task_list}
                    ).model_dump()
                )
                logger.info(f"任务开始：{script_id}")

                if isinstance(Config.ScriptConfig[script_id], MaaConfig):
                    task_item = MaaManager(mode, script_id, None, websocket)
                # elif isinstance(Config.ScriptConfig[task_id], GeneralConfig):
                #     task_item = GeneralManager(mode, task_id, actual_id, websocket)
                else:
                    logger.error(
                        f"不支持的脚本类型：{Config.ScriptConfig[script_id].__class__.__name__}"
                    )
                    await websocket.send_json(
                        TaskMessage(
                            type="Info", data={"Error": "脚本类型不支持"}
                        ).model_dump()
                    )
                    continue

                task = asyncio.create_task(task_item.run())
                task.add_done_callback(
                    lambda t: asyncio.create_task(task_item.final_task(t))
                )

    async def stop_task(self, task_id: uuid.UUID) -> None:
        """
        中止任务

        :param task_id: 任务ID
        """

        logger.info(f"中止任务：{task_id}")

        if task_id not in self.task_dict:
            raise ValueError(f"The task {task_id} is not running.")

        self.task_dict[task_id].cancel()

    async def remove_task(
        self, task: asyncio.Task, mode: str, task_id: uuid.UUID
    ) -> None:
        """
        处理任务结束后的收尾工作

        Parameters
        ----------
        task : asyncio.Task
            任务对象
        mode : str
            任务模式
        task_id : uuid.UUID
            任务ID
        """

        logger.info(f"任务结束：{task_id}")

        # 从任务字典中移除任务
        try:
            await task
        except asyncio.CancelledError:
            logger.info(f"任务 {task_id} 已结束")
            self.task_dict.pop(task_id)

        websocket = self.websocket_dict.pop(task_id, None)
        if websocket:
            await websocket.send_json(
                TaskMessage(type="Signal", data={"Accomplish": "无描述"}).model_dump()
            )
            await websocket.close()


TaskManager = _TaskManager()
