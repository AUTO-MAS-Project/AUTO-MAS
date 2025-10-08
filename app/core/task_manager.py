#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 AUTO-MAS Team

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
from dataclasses import dataclass, field, asdict
from datetime import datetime

from .config import Config, MaaConfig, GeneralConfig
from app.services import System
from app.models.schema import WebSocketMessage
from app.utils import get_logger
from app.task import MaaManager, GeneralManager
from app.utils.constants import POWER_SIGN_MAP


logger = get_logger("业务调度")


@dataclass
class TaskInfo:
    """任务信息(可变对象)"""

    task_id: str
    script_id: str = ""
    mode: str = ""
    status: str = "初始化"
    progress: dict = field(default_factory=lambda: {"current": 0, "total": 0})
    current_user: Optional[dict] = None
    logs: list = field(default_factory=list)
    start_time: datetime = field(default_factory=datetime.now)
    update_time: datetime = field(default_factory=datetime.now)

    def update(self, **kwargs):
        """辅助更新方法,自动更新时间戳"""
        for key, value in kwargs.items():
            if hasattr(self, key):
                setattr(self, key, value)
        self.update_time = datetime.now()

    def to_dict(self):
        """转为可序列化的字典"""
        data = asdict(self)
        data["start_time"] = self.start_time.isoformat()
        data["update_time"] = self.update_time.isoformat()
        return data


class _TaskManager:
    """业务调度器"""

    def __init__(self):
        super().__init__()

        self.task_dict: Dict[uuid.UUID, asyncio.Task] = {}
        self.task_info_dict: Dict[uuid.UUID, TaskInfo] = {}

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
                    if actual_id in script.UserData:
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

    @logger.catch
    async def run_task(
        self, mode: str, task_id: uuid.UUID, actual_id: Optional[uuid.UUID]
    ):
        logger.info(f"开始运行任务: {task_id}, 模式: {mode}")

        # 初始化任务信息
        task_info = TaskInfo(
            task_id=str(task_id),
            script_id=str(actual_id or task_id),
            mode=mode,
            status="初始化",
        )
        self.task_info_dict[task_id] = task_info

        if mode == "设置脚本":
            if isinstance(Config.ScriptConfig[task_id], MaaConfig):
                task_item = MaaManager(
                    mode, task_id, actual_id, str(task_id), task_info
                )
            elif isinstance(Config.ScriptConfig[task_id], GeneralConfig):
                task_item = GeneralManager(
                    mode, task_id, actual_id, str(task_id), task_info
                )
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
            try:
                await self.task_dict[uid]
            except Exception as e:
                logger.error(f"任务 {task_id} 运行出错: {type(e).__name__}: {str(e)}")
                await Config.send_json(
                    WebSocketMessage(
                        id=str(task_id),
                        type="Info",
                        data={"Error": f"任务运行时出错 {type(e).__name__}: {str(e)}"},
                    ).model_dump()
                )

        else:
            # 初始化任务列表
            if task_id in Config.QueueConfig:
                task_list = []
                for queue_item in Config.QueueConfig[task_id].QueueItem.values():
                    if queue_item.get("Info", "ScriptId") == "-":
                        continue
                    script_uid = uuid.UUID(queue_item.get("Info", "ScriptId"))

                    task_list.append(
                        {
                            "script_id": str(script_uid),
                            "status": "等待",
                            "name": Config.ScriptConfig[script_uid].get("Info", "Name"),
                            "user_list": [
                                {
                                    "user_id": str(user_id),
                                    "status": "等待",
                                    "name": config.get("Info", "Name"),
                                }
                                for user_id, config in Config.ScriptConfig[
                                    script_uid
                                ].UserData.items()
                                if config.get("Info", "Status")
                                and config.get("Info", "RemainedDay") != 0
                            ],
                        }
                    )

            elif actual_id is not None and actual_id in Config.ScriptConfig:
                task_list = [
                    {
                        "script_id": str(actual_id),
                        "status": "等待",
                        "name": Config.ScriptConfig[actual_id].get("Info", "Name"),
                        "user_list": [
                            {
                                "user_id": str(user_id),
                                "status": "等待",
                                "name": config.get("Info", "Name"),
                            }
                            for user_id, config in Config.ScriptConfig[
                                actual_id
                            ].UserData.items()
                            if config.get("Info", "Status")
                            and config.get("Info", "RemainedDay") != 0
                        ],
                    }
                ]
            else:
                task_list = []

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

                # 为子任务创建独立的任务信息
                sub_task_info = TaskInfo(
                    task_id=str(script_id),
                    script_id=str(script_id),
                    mode=mode,
                    status="运行",
                )
                self.task_info_dict[script_id] = sub_task_info

                if isinstance(Config.ScriptConfig[script_id], MaaConfig):
                    task_item = MaaManager(
                        mode, script_id, None, str(task_id), sub_task_info
                    )
                elif isinstance(Config.ScriptConfig[script_id], GeneralConfig):
                    task_item = GeneralManager(
                        mode, script_id, actual_id, str(task_id), sub_task_info
                    )
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
                try:
                    await self.task_dict[script_id]
                    task["status"] = "完成"
                except Exception as e:
                    logger.error(
                        f"任务 {script_id} 运行出错: {type(e).__name__}: {str(e)}"
                    )
                    await Config.send_json(
                        WebSocketMessage(
                            id=str(task_id),
                            type="Info",
                            data={
                                "Error": f"任务运行时出错 {type(e).__name__}: {str(e)}"
                            },
                        ).model_dump()
                    )
                    task["status"] = "异常"
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
                raise ValueError("任务未在运行")
            self.task_dict[uid].cancel()

    def get_task_info(self, task_id: uuid.UUID) -> Optional[dict]:
        """
        获取任务信息

        :param task_id: 任务ID
        :return: 任务信息字典,如果任务不存在则返回None
        """
        info = self.task_info_dict.get(task_id)
        return info.to_dict() if info else None

    def get_all_task_info(self) -> Dict[str, dict]:
        """
        获取所有任务信息

        :return: 所有任务信息字典
        """
        return {
            str(task_id): info.to_dict()
            for task_id, info in self.task_info_dict.items()
        }

    async def _cleanup_task_info(self, task_id: uuid.UUID, delay: int = 300):
        """
        延迟清理任务信息(可选)

        :param task_id: 任务ID
        :param delay: 延迟时间(秒),默认5分钟
        """
        await asyncio.sleep(delay)
        self.task_info_dict.pop(task_id, None)
        logger.debug(f"已清理任务信息: {task_id}")

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
        self.task_dict.pop(task_id, None)

        # 清理任务信息
        if task_id in self.task_info_dict:
            self.task_info_dict[task_id].update(status="已完成")
            # 可选:延迟删除或保留一段时间供查询
            # asyncio.create_task(self._cleanup_task_info(task_id, delay=300))

        await Config.send_json(
            WebSocketMessage(
                id=str(task_id), type="Signal", data={"Accomplish": "无描述"}
            ).model_dump()
        )

        if mode == "自动代理" and task_id in Config.QueueConfig:
            if Config.power_sign == "NoAction":
                Config.power_sign = Config.QueueConfig[task_id].get(
                    "Info", "AfterAccomplish"
                )
                await Config.send_json(
                    WebSocketMessage(
                        id="Main", type="Update", data={"PowerSign": Config.power_sign}
                    ).model_dump()
                )

            if len(self.task_dict) == 0 and Config.power_sign != "NoAction":
                logger.info(f"所有任务已结束，准备执行电源操作: {Config.power_sign}")
                await Config.send_json(
                    WebSocketMessage(
                        id="Main",
                        type="Message",
                        data={
                            "type": "Countdown",
                            "title": f"{POWER_SIGN_MAP[Config.power_sign]}倒计时",
                            "message": f"程序将在倒计时结束后执行 {POWER_SIGN_MAP[Config.power_sign]} 操作",
                        },
                    ).model_dump()
                )
                await System.start_power_task()

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
