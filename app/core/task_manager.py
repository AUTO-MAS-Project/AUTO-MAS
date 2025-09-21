#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361

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
from functools import partial
from typing import Dict, Optional, Literal

from .config import Config, MaaConfig, GeneralConfig, QueueConfig
from app.models.schema import WebSocketMessage
from app.utils import get_logger
from app.task import *


logger = get_logger("业务调度")


class _TaskManager:
    """业务调度器"""

    def __init__(self):
        super().__init__()

        self.task_dict: Dict[uuid.UUID, asyncio.Task] = {}

    async def add_task(
        self, mode: Literal["自动代理", "人工排查", "设置脚本"], uid: str
    ) -> uuid.UUID:
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
                    raise ValueError(f"任务 {uid} 无法找到对应脚本配置")
        elif actual_id in Config.QueueConfig:
            task_id = actual_id
            actual_id = None
        elif actual_id in Config.ScriptConfig:
            task_id = uuid.uuid4()
        else:
            raise ValueError(f"任务 {uid} 无法找到对应脚本配置")

        if task_id in self.task_dict or (
            actual_id is not None and actual_id in self.task_dict
        ):
            raise RuntimeError(f"任务 {task_id} 已在运行")

        logger.info(f"创建任务: {task_id}, 模式: {mode}")
        self.task_dict[task_id] = asyncio.create_task(
            self.run_task(mode, task_id, actual_id)
        )
        self.task_dict[task_id].add_done_callback(
            lambda t: asyncio.create_task(self.remove_task(t, mode, task_id))
        )

        return task_id

    # @logger.catch
    async def run_task(
        self, mode: str, task_id: uuid.UUID, actual_id: Optional[uuid.UUID]
    ):

        logger.info(f"开始运行任务: {task_id}, 模式: {mode}")

        if mode == "设置脚本":

            if isinstance(Config.ScriptConfig[task_id], MaaConfig):
                task_item = MaaManager(mode, task_id, actual_id, str(task_id))
            elif isinstance(Config.ScriptConfig[task_id], GeneralConfig):
                task_item = GeneralManager(mode, task_id, actual_id, str(task_id))
            else:
                logger.error(
                    f"不支持的脚本类型: {type(Config.ScriptConfig[task_id]).__name__}"
                )
                await Config.send_json(
                    WebSocketMessage(
                        id=str(task_id),
                        type="Info",
                        data={"Error": "脚本类型不支持"},
                    ).model_dump()
                )
                return

            uid = actual_id or uuid.uuid4()
            self.task_dict[uid] = asyncio.create_task(task_item.run())
            self.task_dict[uid].add_done_callback(
                lambda t: asyncio.create_task(task_item.final_task(t))
            )
            self.task_dict[uid].add_done_callback(partial(self.task_dict.pop, uid))
            await self.task_dict[uid]

        else:

            # 初始化任务列表
            if task_id in Config.QueueConfig:

                queue = Config.QueueConfig[task_id]
                if not isinstance(queue, QueueConfig):
                    return

                task_list = []
                for queue_item in queue.QueueItem.values():
                    if queue_item.get("Info", "ScriptId") == "-":
                        continue
                    script_id = uuid.UUID(queue_item.get("Info", "ScriptId"))
                    script = Config.ScriptConfig[script_id]
                    if not isinstance(script, (MaaConfig | GeneralConfig)):
                        logger.error(f"不支持的脚本类型: {type(script).__name__}")
                        continue
                    task_list.append(
                        {
                            "script_id": str(script_id),
                            "status": "等待",
                            "name": script.get("Info", "Name"),
                            "user_list": [
                                {
                                    "user_id": str(user_id),
                                    "status": "等待",
                                    "name": config.get("Info", "Name"),
                                }
                                for user_id, config in script.UserData.items()
                                if config.get("Info", "Status")
                                and config.get("Info", "RemainedDay") != 0
                            ],
                        }
                    )

            elif actual_id is not None and actual_id in Config.ScriptConfig:

                script = Config.ScriptConfig[actual_id]
                if not isinstance(script, (MaaConfig | GeneralConfig)):
                    logger.error(f"不支持的脚本类型: {type(script).__name__}")
                    return

                task_list = [
                    {
                        "script_id": str(actual_id),
                        "status": "等待",
                        "name": script.get("Info", "Name"),
                        "user_list": [
                            {
                                "user_id": str(user_id),
                                "status": "等待",
                                "name": config.get("Info", "Name"),
                            }
                            for user_id, config in script.UserData.items()
                            if config.get("Info", "Status")
                            and config.get("Info", "RemainedDay") != 0
                        ],
                    }
                ]

            await Config.send_json(
                WebSocketMessage(
                    id=str(task_id), type="Update", data={"task_dict": task_list}
                ).model_dump()
            )

            # 清理用户列表初值
            for task in task_list:
                task.pop("user_list", None)

            for task in task_list:

                script_id = uuid.UUID(task["script_id"])

                # 检查任务是否在运行列表中
                if script_id in self.task_dict:

                    task["status"] = "跳过"
                    await Config.send_json(
                        WebSocketMessage(
                            id=str(task_id),
                            type="Update",
                            data={"task_list": task_list},
                        ).model_dump()
                    )
                    logger.info(f"跳过任务: {script_id}, 该任务已在运行列表中")
                    continue

                # 检查任务对应脚本是否仍存在
                if script_id in self.task_dict:

                    task["status"] = "异常"
                    await Config.send_json(
                        WebSocketMessage(
                            id=str(task_id),
                            type="Update",
                            data={"task_list": task_list},
                        ).model_dump()
                    )
                    logger.info(f"跳过任务: {script_id}, 该任务对应脚本已被删除")
                    continue

                # 标记为运行中
                task["status"] = "运行"
                await Config.send_json(
                    WebSocketMessage(
                        id=str(task_id), type="Update", data={"task_list": task_list}
                    ).model_dump()
                )
                logger.info(f"任务开始: {script_id}")

                if isinstance(Config.ScriptConfig[script_id], MaaConfig):
                    task_item = MaaManager(mode, script_id, None, str(task_id))
                elif isinstance(Config.ScriptConfig[script_id], GeneralConfig):
                    task_item = GeneralManager(mode, script_id, actual_id, str(task_id))
                else:
                    logger.error(
                        f"不支持的脚本类型: {type(Config.ScriptConfig[script_id]).__name__}"
                    )
                    await Config.send_json(
                        WebSocketMessage(
                            id=str(task_id),
                            type="Info",
                            data={"Error": "脚本类型不支持"},
                        ).model_dump()
                    )
                    continue

                self.task_dict[script_id] = asyncio.create_task(task_item.run())
                self.task_dict[script_id].add_done_callback(
                    lambda t: asyncio.create_task(task_item.final_task(t))
                )
                self.task_dict[script_id].add_done_callback(
                    partial(self.task_dict.pop, script_id)
                )
                await self.task_dict[script_id]
                task["status"] = "完成"
                await Config.send_json(
                    WebSocketMessage(
                        id=str(task_id),
                        type="Update",
                        data={"task_list": task_list},
                    ).model_dump()
                )

    async def stop_task(self, task_id: str) -> None:
        """
        中止任务

        :param task_id: 任务ID
        """

        logger.info(f"中止任务: {task_id}")

        if task_id == "ALL":
            for task in self.task_dict.values():
                task.cancel()
        else:
            uid = uuid.UUID(task_id)
            if uid not in self.task_dict:
                raise ValueError(f"任务 {uid} 未在运行")
            self.task_dict[uid].cancel()

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

        logger.info(f"任务结束: {task_id}")

        # 从任务字典中移除任务
        try:
            await task
        except asyncio.CancelledError:
            logger.info(f"任务 {task_id} 已结束")
        self.task_dict.pop(task_id)

        await Config.send_json(
            WebSocketMessage(
                id=str(task_id), type="Signal", data={"Accomplish": "无描述"}
            ).model_dump()
        )

        if mode == "自动代理" and task_id in Config.QueueConfig:

            await Config.send_json(
                WebSocketMessage(
                    id=str(task_id),
                    type="Signal",
                    data={
                        "power": Config.QueueConfig[task_id].get(
                            "Info", "AfterAccomplish"
                        )
                    },
                ).model_dump()
            )

    async def start_startup_queue(self):
        """开始运行启动时运行的调度队列"""

        logger.info("开始运行启动时任务")
        for uid, queue in Config.QueueConfig.items():

            if queue.get("Info", "StartUpEnabled") and uid not in self.task_dict:
                logger.info(f"启动时需要运行的队列：{uid}")
                task_id = await TaskManager.add_task("自动代理", str(uid))
                await Config.send_json(
                    WebSocketMessage(
                        id="TaskManager", type="Signal", data={"newTask": str(task_id)}
                    ).model_dump()
                )

        logger.success("启动时任务开始运行")


TaskManager = _TaskManager()
