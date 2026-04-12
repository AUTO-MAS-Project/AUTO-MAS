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


import json
import queue
import uuid
import asyncio
import shutil
import re
from pathlib import Path
from datetime import datetime, timedelta

from app.core import Config
from app.models.task import TaskExecuteBase, ScriptItem, LogRecord
from app.models.ConfigBase import MultipleConfig
from app.models.config import M9AConfig, M9AUserConfig
from app.models.emulator import DeviceInfo, DeviceBase
from app.services import Notify, System
from app.utils import get_logger, LogMonitor, ProcessManager
from app.utils.constants import UTC4,UTC8
from .tools import push_notification
from .task_loader import M9ATaskLoader
from .config_builder import M9AConfigBuilder

logger = get_logger("M9A 自动代理")


class AutoProxyTask(TaskExecuteBase):
    """自动代理模式"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: M9AConfig,
        user_config: MultipleConfig[M9AUserConfig],
        emulator_manager: DeviceBase,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.emulator_manager = emulator_manager
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config = self.user_config[self.cur_user_uid]
        self.check_result = "-"

        # 初始化路径
        self.m9a_root_path = Path(self.script_config.get("Info", "Path"))
        self.m9a_config_path = self.m9a_root_path / "config"
        today_date = datetime.now().strftime("%Y%m%d")
        self.m9a_log_path = self.m9a_root_path / f"logs/log-{today_date}.log"
        self.m9a_exe_path = self.m9a_root_path / "M9A.exe"
        self.m9a_tasks_path = self.m9a_config_path / "instances/default.json"

        # 初始化任务加载器和配置构建器
        self.m9a_task_loader = M9ATaskLoader(self.m9a_root_path)
        self.m9a_config_builder = M9AConfigBuilder(self.m9a_root_path)

        # 初始化任务加载器和配置构建器
        self.m9a_task_loader = M9ATaskLoader(self.m9a_root_path)
        self.m9a_config_builder = M9AConfigBuilder(self.m9a_root_path)

    async def check(self) -> str:

        if self.script_config.get(
            "Run", "ProxyTimesLimit"
        ) != 0 and self.cur_user_config.get(
            "Data", "ProxyTimes"
        ) >= self.script_config.get(
            "Run", "ProxyTimesLimit"
        ):
            self.cur_user_item.status = "跳过"
            return "今日代理次数已达上限, 跳过该用户"
        return "Pass"

    async def prepare(self):

        self.m9a_process_manager = ProcessManager()
        self.m9a_log_monitor = LogMonitor(
            (1, 24),
            "%Y-%m-%d %H:%M:%S.%f",
            self.check_log,
            except_logs=["如果长时间无进一步日志更新，可能需要手动干预。"],
        )
        self.wait_event = asyncio.Event()
        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now()
        self.mode = "AutoProxy"  # M9A 暂时不需要这个，但先占位

        self.m9a_root_path = Path(self.script_config.get("Info", "Path"))
        self.m9a_config_path = self.m9a_root_path / "config"
        today_date = datetime.now().strftime("%Y%m%d")
        self.m9a_log_path = self.m9a_root_path / f"logs/log-{today_date}.log"
        self.m9a_exe_path = self.m9a_root_path / "M9A.exe"
        self.m9a_tasks_path = self.m9a_config_path / "instances/default.json"


    async def main_task(self):
        """自动代理模式主逻辑"""
        # 任务完成记录
        self.task_dict = {}

        # 初始化每日代理状态
        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        if self.cur_user_config.get("Data", "LastProxyDate") != self.curdate:
            await self.cur_user_config.set("Data", "LastProxyDate", self.curdate)
            await self.cur_user_config.set("Data", "ProxyTimes", 0)

        self.check_result = await self.check()
        if self.check_result != "Pass":
            if self.cur_user_item.status == "异常":
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={
                        "Error": f"用户 {self.cur_user_item.name} 检查未通过: {self.check_result}"
                    },
                )
            return

        await self.prepare()

        logger.info(f"开始代理用户: {self.cur_user_uid}")
        self.cur_user_item.status = "运行"
        for i in range(self.script_config.get("Run", "RunTimesLimit")):
            logger.info(
                f"用户 {self.cur_user_item.name} 自动代理模式 - 尝试次数: {i + 1}/{self.script_config.get('Run', 'RunTimesLimit')}"
            )
            self.log_start_time = datetime.now()
            self.cur_user_item.log_record[self.log_start_time] = (
                self.cur_user_log
            ) = LogRecord()

            try:
                self.script_info.log = "正在启动模拟器"
                emulator_info = await self.emulator_manager.open(
                    self.script_config.get("Emulator", "Index"), None, 
                )
            except Exception as e:
                logger.exception(f"用户: {self.cur_user_uid} - 模拟器启动失败: {e}")
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={"Error": f"启动模拟器时出现异常: {e}"},
                )
                self.cur_user_log.content = [
                    "模拟器启动失败, M9A 未实际运行, 无日志记录"
                ]
                self.cur_user_log.status = "模拟器启动失败"

                try:
                    await self.emulator_manager.close(
                        self.script_config.get("Emulator", "Index")
                    )
                except Exception as e:
                    logger.exception(f"关闭模拟器失败: {e}")

                await Notify.push_plyer(
                    "用户自动代理出现异常！",
                    f"{self.cur_user_item.name}出现异常",
                    "异常",
                    3,
                )
                continue

            if Config.get("Function", "IfSilence"):
                try:
                    await self.emulator_manager.setVisible(
                        self.script_config.get("Emulator", "Index"), False
                    )
                except Exception as e:
                    logger.exception(f"模拟器隐藏失败: {e}")

            # 读取用户队列
            queue = self.cur_user_config.get("Task", "Queue")
            logger.info(f"用户 {self.cur_user_uid} 的任务队列 (原始): {queue}, 类型: {type(queue)}")

            # 确保 queue 是列表
            if isinstance(queue, str):
                import json
                try:
                    queue = json.loads(queue)
                    logger.info(f"任务队列已从 JSON 字符串解析: {queue}")
                except Exception as e:
                    logger.error(f"任务队列 JSON 解析失败: {e}")
                    queue = []

            if not queue:
                logger.warning(f"用户 {self.cur_user_uid} 未配置任务队列或队列为空")
                self.cur_user_item.status = "异常"
                return

            logger.info(f"用户 {self.cur_user_uid} 将执行 {len(queue)} 个任务: {queue}")

            # 写入M9A配置
            await self.write_m9a_config(queue, emulator_info)

            # 启动 M9A
            logger.info(f"启动 M9A 进程：{self.m9a_exe_path}")
            self.wait_event.clear()
            await self.m9a_process_manager.open_process(self.m9a_exe_path)
            await asyncio.sleep(1)  # 等待 M9A 处理日志文件

            # 等待一段时间让 M9A 初始化
            logger.info("等待 M9A 初始化连接...")
            await asyncio.sleep(5)
            
            # 检查 M9A 进程是否还在运行
            if not await self.m9a_process_manager.is_running():
                logger.error("M9A 进程启动后立即退出，可能是 ADB 连接或模拟器问题")
                raise RuntimeError("M9A 进程启动失败，请检查模拟器和 ADB 连接")
            
            logger.info("M9A 进程正常运行中...")
            await self.m9a_log_monitor.start_monitor_file(
                self.m9a_log_path, self.log_start_time
            )
            await self.wait_event.wait()
            await self.m9a_log_monitor.stop()

            if self.cur_user_log.status == "Success!":
                logger.info(f"用户: {self.cur_user_uid} - M9A进程完成代理任务")
                self.script_info.log = (
                    "检测到 M9A 完成代理任务\n正在等待相关程序结束"
                )
            else:
                logger.error(
                    f"用户: {self.cur_user_uid} - 代理任务异常: {self.cur_user_log.status}"
                )
                self.script_info.log = (
                    f"{self.cur_user_log.status}\n正在中止相关程序"
                )

                await self.m9a_process_manager.kill()
                try:
                    await self.emulator_manager.close(
                        self.script_config.get("Emulator", "Index")
                    )
                except Exception as e:
                    logger.exception(f"关闭模拟器失败: {e}")
                await System.kill_process(self.m9a_exe_path)

                await Notify.push_plyer(
                    "用户自动代理出现异常！",
                    f"{self.cur_user_item.name}出现异常",
                    "异常",
                    3,
                )        

                await asyncio.sleep(3)

    async def write_m9a_config(self, queue: list, emulator_info: DeviceInfo):
        """写入M9A配置文件 - 后端兜底模式"""
        logger.info(f"开始配置M9A运行参数")

        # 确保M9A进程已关闭
        await self.m9a_process_manager.kill()
        await System.kill_process(self.m9a_exe_path)

        # 使用 config_builder 构建完整配置
        try:
            emulator_id = self.script_config.get("Emulator", "Id")
            emulator_index = self.script_config.get("Emulator", "Index")
            
            config = await self.m9a_config_builder.build_config(
                queue=queue,
                task_loader=self.m9a_task_loader,
                emulator_info=emulator_info,
                emulator_id=emulator_id,
                script_config=self.script_config,
                emulator_index=emulator_index,
                emulator_manager=self.emulator_manager
            )
        except Exception as e:
            logger.error(f"构建 M9A 配置失败: {e}")
            raise

        # 保存配置到 M9A 目录
        self.m9a_tasks_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        logger.info(f"已写入 M9A 配置：{self.m9a_tasks_path}")

        # ==================== Debug 备份功能 ====================
        # 保存到 data/script_id 目录，按 test1.json, test2.json 递增
        debug_dir = Path("data") / self.script_info.script_id
        debug_dir.mkdir(parents=True, exist_ok=True)
        
        # 查找现有 test*.json 文件，获取下一个编号
        existing_tests = list(debug_dir.glob("test*.json"))
        test_numbers = []
        for test_file in existing_tests:
            match = re.search(r"test(\d+)\.json", test_file.name)
            if match:
                test_numbers.append(int(match.group(1)))
        
        next_num = max(test_numbers) + 1 if test_numbers else 1
        backup_path = debug_dir / f"test{next_num}.json"
        
        # 保存备份
        backup_path.write_text(
            json.dumps(config, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        logger.info(f"Debug 备份已保存：{backup_path}")
        # =======================================================


    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """日志回调 - M9A 专用版本（禁用敏感的错误检测，避免在游戏加载时误判）
        
        重要：log_content 只包含本次启动后的日志（由 LogMonitor 根据 log_start_time 过滤）
        因此不会误检测到之前运行的日志内容
        """

        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log

        # 判断任务完成 - 检测"任务已全部完成！"（带感叹号）
        # 注意：只检测本次启动后的日志，不会误判之前的运行
        if "任务已全部完成！" in log or "All tasks completed" in log:
            self.cur_user_log.status = "Success!"
        # 注意：禁用基于日志关键字的错误检测，因为 M9A 在游戏加载时会输出大量 [ERR] 日志
        # 改为只检测进程是否真的退出，或等待超时
        elif not await self.m9a_process_manager.is_running():
            # 进程已结束但未检测到正常完成标志，置为异常完成
            # 注意：只检查本次启动后的日志
            if "任务已全部完成！" not in log and "All tasks completed" not in log:
                self.cur_user_log.status = "M9A 进程已异常结束"
            else:
                self.cur_user_log.status = "M9A 进程已结束"
        elif datetime.now() - latest_time > timedelta(
            minutes=self.script_config.get("Run", "RunTimeLimit") or 10
        ):
            self.cur_user_log.status = "M9A 进程超时"
        else:
            self.cur_user_log.status = "M9A 正常运行中"

        logger.debug(f"M9A 日志分析结果：{self.cur_user_log.status}")
        if self.cur_user_log.status != "M9A 正常运行中":
            logger.info(f"M9A 任务结果：{self.cur_user_log.status}")
            self.wait_event.set()

    async def final_task(self):

        if self.check_result != "Pass":
            return

        await self.m9a_process_manager.kill()
        await System.kill_process(self.m9a_exe_path)  

        logger.info("用户任务结束, 关闭模拟器")
        # 2. 关闭模拟器
        try:
            await self.emulator_manager.close(
                self.script_config.get("Emulator", "Index")
            )
        except Exception as e:
            logger.exception(f"关闭模拟器失败：{e}")

        # 3. 更新用户状态 - 根据日志结果判断
        if self.cur_user_item.status == "运行":
            # 检查是否正常完成
            if self.cur_user_log.status == "Success!":
                self.cur_user_item.status = "完成"
                await self.cur_user_config.set(
                    "Data", "ProxyTimes",
                    self.cur_user_config.get("Data", "ProxyTimes") + 1
                )
                logger.success(f"用户 {self.cur_user_uid} 的 M9A 任务已完成")
            else:
                # 未检测到正常完成标志，置为异常
                self.cur_user_item.status = "异常"
                logger.warning(f"用户 {self.cur_user_uid} 的 M9A 任务异常结束: {self.cur_user_log.status}")






    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.exception(f"自动代理任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"自动代理任务出现异常: {e}"},
        )
