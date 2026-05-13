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
import uuid
import asyncio
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
from .tools.notify import M9ALogAnalyzer
from .task_loader import M9ATaskLoader

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

        # 初始化任务加载器
        self.m9a_task_loader = M9ATaskLoader(self.m9a_root_path)
        self.template_path = self.m9a_root_path / "config/instances/default.json"


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
        )
        self.wait_event = asyncio.Event()
        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now()


    async def main_task(self):
        """自动代理模式主逻辑"""
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
        self.run_complete = False
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
                    self.script_config.get("Emulator", "Index"),
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
            # 等待 M9A 处理日志文件与初始化
            logger.info("等待 M9A 初始化...")
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
                self.run_complete = True
                break
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
        """向 M9A 目录写入运行配置文件，并保存 debug 备份"""
        logger.info("开始配置 M9A 运行参数")

        # 确保M9A进程已关闭
        await self.m9a_process_manager.kill()
        await System.kill_process(self.m9a_exe_path)

        # 使用 config_builder 构建完整配置
        try:
            emulator_id = self.script_config.get("Emulator", "Id")
            emulator_index = self.script_config.get("Emulator", "Index")
            
            config = await self.build_config(
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

        # Debug 备份：保存到 data/script_id 目录，按 testN.json 递增，保留最近 5 个
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
        
        # 清理旧备份，只保留最近 5 个
        existing_tests = list(debug_dir.glob("test*.json"))
        test_files_with_num = []
        for test_file in existing_tests:
            match = re.search(r"test(\d+)\.json", test_file.name)
            if match:
                test_files_with_num.append((int(match.group(1)), test_file))
        
        # 按编号排序，删除最旧的
        test_files_with_num.sort(key=lambda x: x[0])
        if len(test_files_with_num) > 5:
            files_to_delete = test_files_with_num[:-5]
            for num, file_path in files_to_delete:
                try:
                    file_path.unlink()
                    logger.debug(f"已删除旧备份文件：{file_path}")
                except Exception as e:
                    logger.warning(f"删除旧备份文件失败 {file_path}: {e}")


    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """M9A 日志回调：分析实时日志，判断任务执行状态

        策略说明：
        - log_content 由 LogMonitor 根据 log_start_time 过滤，仅包含本次启动后的日志
        - 不使用日志关键字做错误检测（M9A 在游戏加载时会输出大量 [ERR] 日志）
        - 仅依赖进程退出状态和超时来判断异常
        """

        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log

        if "任务已全部完成！" in log or "All tasks completed" in log:
            self.cur_user_log.status = "Success!"
        elif "已放弃本次任务" in log:
            self.cur_user_log.status = "M9A 已放弃本次任务"
        elif not await self.m9a_process_manager.is_running():
            if "任务已全部完成！" not in log and "All tasks completed" not in log:
                self.cur_user_log.status = "M9A 进程已异常结束"
            else:
                self.cur_user_log.status = "M9A 进程已结束"
        elif datetime.now() - latest_time > timedelta(
            minutes=self.script_config.get("Run", "RunTimeLimit")
        ):
            self.cur_user_log.status = "M9A 进程超时"
        else:
            self.cur_user_log.status = "M9A 正常运行中"

        logger.debug(f"M9A 日志分析结果：{self.cur_user_log.status}")
        if self.cur_user_log.status != "M9A 正常运行中":
            logger.info(f"M9A 任务结果：{self.cur_user_log.status}")
            self.wait_event.set()

    async def final_task(self):
        """任务收尾：停止监控、结束进程、关闭模拟器、保存记录并推送通知"""

        # 1) 停止日志监控（如果已启动）
        try:
            if hasattr(self, "m9a_log_monitor") and self.m9a_log_monitor is not None:
                await self.m9a_log_monitor.stop()
        except Exception as e:
            logger.warning(f"停止 M9A 日志监控失败: {e}")

        if self.check_result != "Pass":
            return

        # 2) 结束 M9A 进程
        try:
            await self.m9a_process_manager.kill()
        except Exception as e:
            logger.warning(f"结束 M9A 进程失败: {e}")
        try:
            await System.kill_process(self.m9a_exe_path)
        except Exception as e:
            logger.warning(f"强制结束 M9A.exe 失败: {e}")

        # 3) 关闭模拟器
        logger.info("用户任务结束，关闭模拟器")
        try:
            await self.emulator_manager.close(
                self.script_config.get("Emulator", "Index")
            )
        except Exception as e:
            logger.warning(f"关闭模拟器失败: {e}")

        # 保存历史记录并合并统计信息
        user_logs_list = []
        for t, log_item in self.cur_user_item.log_record.items():

            if log_item.status == "M9A 正常运行中":
                log_item.status = "任务被用户手动中止"

            dt = t.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone(UTC4)
            log_path = (
                Path.cwd()
                / f"history/{dt.strftime('%Y-%m-%d')}/{self.cur_user_item.name}/{dt.strftime('%H-%M-%S')}.log"
            )
            user_logs_list.append(log_path.with_suffix(".json"))

            await Config.save_maa_log(log_path, log_item.content, log_item.status)

        statistics = await Config.merge_statistic_info(user_logs_list)
        statistics["user_info"] = self.cur_user_item.name
        statistics["start_time"] = self.user_start_time.strftime("%Y-%m-%d %H:%M:%S")
        statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        statistics["user_result"] = (
            "代理任务全部完成"
            if self.run_complete
            else self.cur_user_item.result
        )

        # 分析运行日志，获取任务详情
        task_details_text = ""
        try:
            latest_log_path = self._get_latest_history_log()
            if latest_log_path and latest_log_path.exists():
                analysis = M9ALogAnalyzer.parse_log(latest_log_path)
                task_details_text = M9ALogAnalyzer.build_notification_text(analysis)
        except Exception as e:
            logger.exception(f"日志分析失败: {e}")
        statistics["task_details"] = task_details_text

        # 根据运行结果更新用户状态
        if self.cur_user_item.status == "运行":
            if self.run_complete:
                # 正常完成
                self.cur_user_item.status = "完成"
                
                # 如果是第一次代理，减少剩余天数
                if (
                    self.cur_user_config.get("Data", "ProxyTimes") == 0
                    and self.cur_user_config.get("Info", "RemainedDay") != -1
                ):
                    await self.cur_user_config.set(
                        "Info",
                        "RemainedDay",
                        self.cur_user_config.get("Info", "RemainedDay") - 1,
                    )
                
                # 增加代理次数
                await self.cur_user_config.set(
                    "Data", "ProxyTimes",
                    self.cur_user_config.get("Data", "ProxyTimes") + 1
                )
                
                logger.success(f"用户 {self.cur_user_uid} 的自动代理任务已完成")
                
                # 发送桌面通知
                await Notify.push_plyer(
                    "成功完成一个自动代理任务！",
                    f"已完成用户 {self.cur_user_item.name} 的自动代理任务",
                    f"已完成 {self.cur_user_item.name} 的自动代理任务",
                    3,
                )
            else:
                # 未检测到正常完成标志，置为异常
                self.cur_user_item.status = "异常"
                logger.warning(f"用户 {self.cur_user_uid} 的 M9A 任务异常结束: {self.cur_user_log.status}")
                logger.error(f"用户 {self.cur_user_uid} 的自动代理任务未完成")

        try:
            await push_notification(
                "统计信息",
                f"{datetime.now().strftime('%m-%d')} |{'√' if self.run_complete else 'X'}|  {self.cur_user_item.name} 的自动代理统计报告",
                statistics,
                self.cur_user_config,
            )
        except Exception as e:
            logger.exception(f"推送通知时出现异常: {e}")
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": f"推送通知时出现异常: {e}"},
            )


    async def build_config(
        self,
        queue: list[dict],
        task_loader: 'M9ATaskLoader',
        emulator_info: DeviceInfo | None = None,
        emulator_id: str | None = None,
        script_config: M9AConfig | None = None,
        emulator_index: str | None = None,
        emulator_manager = None
    ) -> dict:
        config = None

        if self.template_path.exists():
            try:
                config = json.loads(self.template_path.read_text(encoding="utf-8"))
                logger.info(f"使用配置模板：{self.template_path}")
            except Exception as e:
                logger.warning(f"读取模板 {self.template_path} 失败：{e}")

        if config is None:
            logger.warning("无法读取配置模板，使用最小默认配置")
            config = {
                "Resource": "官服",
                "CurrentTasks": [],
                "TaskItems": [],
                "AdbDevice": {
                    "InfoHandle": {"value": 0},
                    "Name": "",
                    "AdbPath": "",
                    "AdbSerial": "",
                    "ScreencapMethods": 0,
                    "InputMethods": 0,
                    "Config": "{}",
                    "AgentPath": "./MaaAgentBinary"
                },
                "ResourceOptionItems": {},
                "CurrentControllerName": "ADB",
                "Connect.Address": ""
            }

        all_tasks = task_loader.get_all_tasks_with_entry()
        config["CurrentTasks"] = [
            f"{task['name']}<|||>{task['entry']}"
            for task in all_tasks
        ]
        logger.info(f"M9A CurrentTasks：共 {len(config['CurrentTasks'])} 个任务")

        config["TaskItems"] = []
        skipped_standalone = 0

        for queue_item in queue:
            if isinstance(queue_item, str):
                task_name = queue_item
                task_options = None
            else:
                task_name = queue_item.get("name")
                task_options = queue_item.get("options")

            task_def = task_loader.get_full_definition(task_name)
            if not task_def:
                logger.warning(f"未找到任务定义：{task_name}，跳过")
                continue

            if "standalone" in task_def.get("group", []):
                logger.debug(f"跳过 standalone 任务：{task_name}")
                skipped_standalone += 1
                continue

            item = self._build_task_item(task_def, default_check=True, user_options=task_options)
            config["TaskItems"].append(item)

        logger.info(
            f"M9A TaskItems：共 {len(config['TaskItems'])} 个任务项"
            f"（已过滤 {skipped_standalone} 个 standalone 任务）"
        )

        if emulator_id and script_config and emulator_index and emulator_manager:
            try:
                adb_device_config = await self._build_adb_device_config(
                    emulator_info, emulator_id, script_config, emulator_index, emulator_manager
                )
                if adb_device_config:
                    config["AdbDevice"] = adb_device_config
                    logger.info("已应用特殊 AdbDevice 配置")
            except Exception as e:
                logger.warning(f"构建特殊 AdbDevice 配置失败，使用默认配置: {e}")

        if emulator_info and emulator_info.adb_address != "Unknown":
            config["Connect.Address"] = emulator_info.adb_address

        config["InstanceName"] = "MAS"

        if "BeforeTask" not in config:
            config["BeforeTask"] = "StartupSoftwareAndScript"
        if "AfterTask" not in config:
            config["AfterTask"] = "CloseEmulatorAndMFA"

        config["AutoConnectAfterRefresh"] = False
        config["AutoDetectOnConnectionFailed"] = False
        config["AllowAdbHardRestart"] = False
        config["AllowAdbRestart"] = False
        config["UseFingerprintMatching"] = False
        config["RememberAdb"] = True

        logger.info(
            f"M9A 配置构建完成：CurrentTasks={len(config['CurrentTasks'])} 个任务, "
            f"TaskItems={len(config['TaskItems'])} 个任务项"
        )
        return config

    @staticmethod
    def _build_option_list(option_names: list[str], option_definitions: dict) -> list[dict]:
        options = []
        for opt_name in option_names:
            opt_item = {"name": opt_name, "index": 0}

            opt_def = option_definitions.get(opt_name, {})
            if isinstance(opt_def, dict) and "cases" in opt_def:
                cases = opt_def.get("cases", [])
                if cases and len(cases) > 0:
                    current_case = cases[0]
                    if "option" in current_case:
                        sub_opts = AutoProxyTask._build_option_list(
                            current_case["option"], option_definitions
                        )
                        if sub_opts:
                            opt_item["sub_options"] = sub_opts

                if opt_def.get("type") == "checkbox":
                    default_case = opt_def.get("default_case", [])
                    if default_case:
                        opt_item["selected_cases"] = list(default_case)
                    else:
                        opt_item["selected_cases"] = [
                            c["name"] for c in cases if "name" in c
                        ]

            if isinstance(opt_def, dict) and opt_def.get("type") == "input" and "inputs" in opt_def:
                data = {}
                for input_def in opt_def["inputs"]:
                    input_name = input_def.get("name")
                    default_value = input_def.get("default")
                    if input_name and default_value is not None:
                        data[input_name] = default_value
                if data:
                    opt_item["data"] = data

            options.append(opt_item)

        return options

    @staticmethod
    def _build_option_list_from_user(user_options: list[dict], option_definitions: dict) -> list[dict]:
        options = []
        for user_opt in user_options:
            opt_name = user_opt.get("name")
            opt_index = user_opt.get("index", 0)
            opt_item = {"name": opt_name, "index": opt_index}

            opt_def = option_definitions.get(opt_name, {})
            if isinstance(opt_def, dict) and "cases" in opt_def:
                cases = opt_def.get("cases", [])
                if cases and len(cases) > opt_index:
                    current_case = cases[opt_index]
                    if "option" in current_case:
                        user_sub_opts = user_opt.get("sub_options", [])
                        sub_opts = AutoProxyTask._build_option_list_from_user(
                            user_sub_opts, option_definitions
                        )
                        if sub_opts:
                            opt_item["sub_options"] = sub_opts

                if opt_def.get("type") == "checkbox":
                    user_selected_cases = user_opt.get("selected_cases")
                    if user_selected_cases is not None:
                        opt_item["selected_cases"] = user_selected_cases

            user_data = user_opt.get("data") if "data" in user_opt else user_opt.get("input_values")

            if user_data is not None:
                opt_item["data"] = user_data
            elif isinstance(opt_def, dict) and opt_def.get("type") == "input" and "inputs" in opt_def:
                data = {}
                for input_def in opt_def["inputs"]:
                    input_name = input_def.get("name")
                    default_value = input_def.get("default")
                    if input_name and default_value is not None:
                        data[input_name] = default_value
                if data:
                    opt_item["data"] = data

            options.append(opt_item)

        return options

    def _build_task_item(self, task_def: dict, default_check: bool = True, user_options: list | None = None) -> dict:
        item = {
            "name": task_def["name"],
            "entry": task_def["entry"],
            "default_check": default_check,
        }

        if "group" in task_def:
            item["group"] = task_def["group"]

        if "description" in task_def:
            item["description"] = task_def["description"]

        if "controller" in task_def:
            item["controller"] = task_def["controller"]

        if user_options is not None and "_option_definitions" in task_def:
            item["option"] = self._build_option_list_from_user(
                user_options,
                task_def["_option_definitions"]
            )
        elif "option" in task_def and "_option_definitions" in task_def:
            item["option"] = self._build_option_list(
                task_def["option"],
                task_def["_option_definitions"]
            )

        if "pipeline_override" in task_def:
            item["pipeline_override"] = task_def["pipeline_override"]

        return item

    async def _build_adb_device_config(
        self,
        emulator_info: DeviceInfo,
        emulator_id: str,
        script_config: M9AConfig,
        emulator_index: str,
        emulator_manager
    ) -> dict | None:
        try:
            emulator_uid = uuid.UUID(emulator_id)
            emulator_config = Config.EmulatorConfig[emulator_uid]

            emulator_type = emulator_config.get("Info", "Type")
            emulator_path = Path(emulator_config.get("Info", "Path"))

            if emulator_type == "ldplayer":
                return await self._build_ldplayer_config(
                    emulator_info, emulator_path, emulator_index, emulator_manager
                )
            elif emulator_type == "mumu":
                return self._build_mumu_config(
                    emulator_info, emulator_path, emulator_index
                )
            else:
                logger.info(f"不支持的模拟器类型: {emulator_type}，使用默认配置")
                return None
        except Exception as e:
            logger.warning(f"构建 AdbDevice 配置时出错: {e}")
            return None

    async def _build_ldplayer_config(
        self,
        emulator_info: DeviceInfo,
        emulator_path: Path,
        emulator_index: str,
        emulator_manager
    ) -> dict:
        logger.info("构建雷电模拟器 AdbDevice 配置")

        ld_player_device = None
        try:
            devices = await emulator_manager.get_device_info(emulator_index)
            if emulator_index in devices:
                ld_player_device = devices[emulator_index]
                logger.info(f"成功获取雷电模拟器设备信息: idx={ld_player_device.idx}, pid={ld_player_device.pid}")
        except Exception as e:
            logger.warning(f"获取雷电模拟器设备信息失败: {e}")

        emulator_root = emulator_path.parent
        adb_path = emulator_root / "adb.exe"

        name = ld_player_device.title if ld_player_device else "雷电模拟器-LDPlayer"
        idx = ld_player_device.idx if ld_player_device else int(emulator_index)
        pid = ld_player_device.pid if ld_player_device else 0

        ld_extras = {
            "enable": True,
            "index": idx,
            "path": str(emulator_root).replace("\\", "/"),
            "pid": pid
        }

        config_json = json.dumps({"extras": {"ld": ld_extras}}, ensure_ascii=False)

        return {
            "Name": name,
            "AdbPath": str(adb_path).replace("\\", "/"),
            "AdbSerial": f"emulator-{5554 + idx * 2}",
            "ScreencapMethods": 64,
            "InputMethods": 18446744073709551607,
            "Config": config_json,
            "AgentPath": "./MaaAgentBinary"
        }

    def _build_mumu_config(
        self,
        emulator_info: DeviceInfo,
        emulator_path: Path,
        emulator_index: str
    ) -> dict:
        logger.info("构建 MuMu 模拟器 AdbDevice 配置")

        shell_dir = emulator_path.parent
        emulator_root = shell_dir.parent
        adb_path = shell_dir / "adb.exe"

        mumu_extras = {
            "enable": True,
            "index": int(emulator_index),
            "path": str(emulator_root).replace("\\", "/")
        }

        config_json = json.dumps({"extras": {"mumu": mumu_extras}}, ensure_ascii=False)

        return {
            "Name": "MuMu模拟器",
            "AdbPath": str(adb_path).replace("\\", "/"),
            "AdbSerial": emulator_info.adb_address,
            "ScreencapMethods": 64,
            "InputMethods": 18446744073709551607,
            "Config": config_json,
            "AgentPath": "./MaaAgentBinary"
        }

    def _get_latest_history_log(self) -> Path | None:
        history_dir = Path.cwd() / "history"
        if not history_dir.exists():
            return None

        log_files = sorted(
            history_dir.rglob(f"{self.cur_user_item.name}/*.log"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )
        return log_files[0] if log_files else None

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.exception(f"自动代理任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"自动代理任务出现异常: {e}"},
        )
