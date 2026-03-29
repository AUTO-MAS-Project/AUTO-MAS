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
import json
import shutil
import asyncio
from pathlib import Path
from contextlib import suppress
from datetime import datetime, timedelta

from app.core import Config
from app.models.task import TaskExecuteBase, ScriptItem, LogRecord
from app.models import SrcConfig, SrcUserConfig, MultipleConfig
from app.models.emulator import DeviceBase, DeviceInfo
from app.services import Notify, System
from app.utils import get_logger, LogMonitor, ProcessManager, strptime
from app.utils.constants import STARRAIL_PACKAGE_NAME, UTC4
from .tools import login, push_notification, poor_yaml_read, poor_yaml_write

logger = get_logger("SRC脚本自动代理")


class AutoProxyTask(TaskExecuteBase):
    """自动代理模式"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: SrcConfig,
        user_config: MultipleConfig[SrcUserConfig],
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

    async def check(self) -> str:
        if self.script_config.get(
            "Run", "ProxyTimesLimit"
        ) != 0 and self.cur_user_config.get(
            "Data", "ProxyTimes"
        ) >= self.script_config.get("Run", "ProxyTimesLimit"):
            self.cur_user_item.status = "跳过"
            return "今日代理次数已达上限, 跳过该用户"

        if (
            self.cur_user_config.get("Info", "Mode") == "详细"
            and not (
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile"
            ).exists()
        ):
            self.cur_user_item.status = "异常"
            return "未找到用户的 SRC 配置文件，请先在用户配置页完成 「SRC配置」 步骤"
        return "Pass"

    async def prepare(self):
        self.src_process_manager = ProcessManager()
        self.src_log_monitor = LogMonitor(
            (0, 23), "%Y-%m-%d %H:%M:%S.%f", self.check_log
        )
        self.wait_event = asyncio.Event()
        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now()

        self.src_root_path = Path(self.script_config.get("Info", "Path"))
        self.src_exe_path = self.src_root_path / "src.exe"
        self.src_set_path = self.src_root_path / "config"
        self.src_log_path = self.src_root_path / "log/2000-01-01_src.txt"

        self.run_book = False

    async def main_task(self):
        """自动代理模式主逻辑"""

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
            if self.run_book:
                break
            logger.info(
                f"用户 {self.cur_user_item.name} - 尝试次数: {i + 1}/{self.script_config.get('Run', 'RunTimesLimit')}"
            )
            self.log_start_time = datetime.now()
            self.cur_user_item.log_record[self.log_start_time] = self.cur_user_log = (
                LogRecord()
            )

            self.script_info.log = "正在启动模拟器..."
            # 启动模拟器
            try:
                logger.info(
                    f"启动模拟器: {self.script_config.get('Emulator', 'Index')}"
                )
                emulator_info = await self.emulator_manager.open(
                    self.script_config.get("Emulator", "Index"),
                    STARRAIL_PACKAGE_NAME[self.cur_user_config.get("Info", "Server")],
                )
            except Exception as e:
                await self.handle_pre_src_error("模拟器启动失败", e)
                continue

            self.script_info.log = (
                "正在启动模拟器...\n模拟器启动成功\n正在登录「崩坏·星穹铁道」..."
            )

            if self.cur_user_config.get("Info", "Id") == "" or await login(
                emulator_info,
                STARRAIL_PACKAGE_NAME[self.cur_user_config.get("Info", "Server")],
                self.cur_user_config.get("Info", "Id"),
                self.cur_user_config.get("Info", "Password"),
            ):
                logger.info(f"用户 {self.cur_user_item.user_id} 登录成功")
            else:
                await self.handle_pre_src_error("「崩坏·星穹铁道」登录失败")
                continue

            self.script_info.log = "正在启动模拟器...\n模拟器启动成功\n正在登录「崩坏·星穹铁道」\n「崩坏·星穹铁道」登录成功"

            await self.set_src(emulator_info)

            logger.info(f"运行脚本任务: {self.src_exe_path}")
            self.wait_event.clear()
            t = datetime.now()
            await self.src_process_manager.open_process(self.src_exe_path)

            # 静默模式隐藏 SRC 窗口
            if Config.get("Function", "IfSilence"):
                while datetime.now() - t < timedelta(minutes=1):
                    if await self.src_process_manager.is_visible():
                        await self.src_process_manager.hide_window()
                        break
                    await asyncio.sleep(0.1)

            # 等待日志文件生成
            self.script_info.log = "正在启动模拟器...\n模拟器启动成功\n正在登录「崩坏·星穹铁道」\n「崩坏·星穹铁道」登录成功\n正在等待 SRC 日志文件生成"
            if_get_file = False
            while datetime.now() - t < timedelta(minutes=1):
                for log_file in self.src_log_path.parent.iterdir():
                    if log_file.is_file():
                        with suppress(ValueError):
                            if strptime(log_file.name, "%Y-%m-%d_src.txt", t) >= t:
                                self.src_log_path = log_file
                                logger.success(
                                    f"成功定位到日志文件: {self.src_log_path}"
                                )
                                if_get_file = True
                                break
                else:
                    await asyncio.sleep(1)

                if if_get_file:
                    break
            else:
                await self.handle_pre_src_error("未找到日志文件")
                continue

            await self.src_log_monitor.start_monitor_file(
                self.src_log_path, self.log_start_time
            )
            await self.wait_event.wait()
            await self.src_log_monitor.stop()

            if self.cur_user_log.status == "Success!":
                self.run_book = True
                logger.info(f"用户: {self.cur_user_uid} - SRC 脚本进程完成代理任务")
                self.script_info.log = (
                    "检测到 SRC 脚本进程完成代理任务\n正在等待相关程序结束"
                )

                # 中止相关程序
                await self.src_process_manager.kill()
                await System.kill_process(self.src_exe_path)

            else:
                logger.error(
                    f"用户: {self.cur_user_uid} - 代理任务异常: {self.cur_user_log.status}"
                )
                self.script_info.log = f"{self.cur_user_log.status}\n正在中止相关程序"

                # 中止相关程序
                await self.kill_managed_process()

                await Notify.push_plyer(
                    "用户自动代理出现异常！",
                    f"用户 {self.cur_user_item.name} 的自动代理出现一次异常",
                    f"{self.cur_user_item.name}的自动代理出现异常",
                    3,
                )

            await asyncio.sleep(10)
            # 更新脚本配置文件
            if self.cur_user_config.get("Info", "Mode") == "详细":
                shutil.copytree(
                    self.src_set_path,
                    Path.cwd()
                    / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile",
                    dirs_exist_ok=True,
                )
                logger.success("SRC 脚本配置文件已更新")

    async def handle_pre_src_error(
        self, error_message: str, e: Exception | None = None
    ):
        if e is None:
            logger.error(f"用户: {self.cur_user_uid} - {error_message}")
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": error_message},
            )
        else:
            logger.exception(f"用户: {self.cur_user_uid} - {error_message}: {e}")
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": f"{error_message}: {e}"},
            )
        self.cur_user_log.content = [f"{error_message}, 无日志记录"]
        self.cur_user_log.status = error_message

        await self.kill_managed_process()

        await Notify.push_plyer(
            "用户自动代理出现异常！",
            f"用户 {self.cur_user_item.name} 自动代理时{error_message}",
            f"{self.cur_user_item.name}的自动代理出现异常",
            3,
        )

    async def kill_managed_process(self) -> None:
        """中止关联进程"""

        try:
            logger.info(f"中止 SRC 进程: {self.src_exe_path}")
            await self.src_process_manager.kill()
            await System.kill_process(self.src_exe_path)
        except Exception as e:
            logger.exception(f"中止 SRC 进程失败: {e}")
        try:
            logger.info("中止模拟器进程")
            await self.emulator_manager.close(
                self.script_config.get("Emulator", "Index")
            )
        except Exception as e:
            logger.exception(f"关闭模拟器失败: {e}")

    async def set_src(self, emulator_info: DeviceInfo) -> None:
        """配置 SRC 脚本运行参数"""
        logger.info("开始配置 SRC 运行参数: 自动代理")

        # 配置前关闭可能未正常退出的脚本进程
        await self.src_process_manager.kill()
        await System.kill_process(self.src_exe_path)

        # 基础配置内容
        if self.cur_user_config.get("Info", "Mode") == "简洁":
            shutil.copytree(
                (Path.cwd() / f"data/{self.script_info.script_id}/Default/ConfigFile"),
                self.src_set_path,
                dirs_exist_ok=True,
            )
        elif self.cur_user_config.get("Info", "Mode") == "详细":
            shutil.copytree(
                (
                    Path.cwd()
                    / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile"
                ),
                self.src_set_path,
                dirs_exist_ok=True,
            )

        src_set = json.loads(
            (self.src_set_path / "src.json").read_text(encoding="utf-8")
        )
        deploy_set = poor_yaml_read(self.src_set_path / "deploy.yaml")

        # 直接运行任务
        deploy_set["Run"] = ["src"]

        # 模拟器基础配置
        if emulator_info.adb_address != "Unknown":
            src_set["Alas"]["Emulator"]["Serial"] = emulator_info.adb_address
        src_set["Alas"]["Emulator"]["GameClient"] = "android"
        src_set["Alas"]["Emulator"]["PackageName"] = self.cur_user_config.get(
            "Info", "Server"
        )
        src_set["Alas"]["Emulator"]["GameLanguage"] = "cn"
        src_set["Alas"]["Emulator"]["AdbRestart"] = True

        # 错误处理方式
        src_set["Alas"]["Error"]["Restart"] = "game"

        # 任务间切换方式
        src_set["Alas"]["Optimization"]["WhenTaskQueueEmpty"] = "close_game"

        # 养成规划
        src_set["Dungeon"]["PlannerTarget"]["Enable"] = False

        # 后备开拓力与燃料
        trailblaze_power = {
            "ExtractReservedTrailblazePower": self.cur_user_config.get(
                "Stage", "ExtractReservedTrailblazePower"
            ),
            "UseFuel": self.cur_user_config.get("Stage", "UseFuel"),
            "FuelOnlyPlanner": False,
            "FuelReserve": self.cur_user_config.get("Stage", "FuelReserve"),
        }
        src_set["Dungeon"]["TrailblazePower"] = trailblaze_power
        src_set["Ornament"]["TrailblazePower"] = trailblaze_power

        # 每日副本关卡配置
        src_set["Dungeon"]["Scheduler"]["Enable"] = True
        main_stage = self.cur_user_config.get(
            "Stage", self.cur_user_config.get("Stage", "Channel")
        )
        relic_stage = self.cur_user_config.get("Stage", "Relic")
        materials_stage = self.cur_user_config.get("Stage", "Materials")
        ornament_stage = self.cur_user_config.get("Stage", "Ornament")
        if (
            self.cur_user_config.get("Stage", "Channel") in ("Relic", "Materials")
            and main_stage != "-"
        ):
            src_set["Dungeon"]["Dungeon"]["Name"] = main_stage
        if (
            not str(self.cur_user_config.get("Stage", "Materials")).startswith(
                "Stagnant_Shadow"
            )
            and materials_stage != "-"
        ):
            src_set["Dungeon"]["Dungeon"]["NameAtDoubleCalyx"] = materials_stage
        if relic_stage != "-":
            src_set["Dungeon"]["Dungeon"]["NameAtDoubleRelic"] = relic_stage

        # 饰品提取关卡配置
        if self.cur_user_config.get("Stage", "Channel") == "Ornament":
            src_set["Ornament"]["Scheduler"]["Enable"] = True
            src_set["Ornament"]["Ornament"]["UseStamina"] = True
        else:
            src_set["Ornament"]["Ornament"]["UseStamina"] = False
        if ornament_stage != "-":
            src_set["Ornament"]["Ornament"]["Dungeon"] = ornament_stage

        # 历战余响关卡配置
        if self.cur_user_config.get("Stage", "EchoOfWar") == "-":
            src_set["Weekly"]["Scheduler"]["Enable"] = False
        else:
            src_set["Weekly"]["Scheduler"]["Enable"] = True
            src_set["Weekly"]["Weekly"]["Name"] = self.cur_user_config.get(
                "Stage", "EchoOfWar"
            )

        # 模拟宇宙关卡配置
        if self.cur_user_config.get("Stage", "SimulatedUniverseWorld") == "-":
            src_set["Rogue"]["Scheduler"]["Enable"] = False
        else:
            src_set["Rogue"]["Scheduler"]["Enable"] = True
            src_set["Rogue"]["RogueWorld"]["World"] = self.cur_user_config.get(
                "Stage", "SimulatedUniverseWorld"
            )

        (self.src_set_path / "src.json").write_text(
            json.dumps(src_set, ensure_ascii=False, indent=4), encoding="utf-8"
        )
        poor_yaml_write(
            deploy_set,
            self.src_set_path / "deploy.yaml",
            (
                self.src_set_path / "deploy.template-cn.yaml"
                if (self.src_set_path / "deploy.template-cn.yaml").exists()
                else None
            ),
        )
        logger.info(f"脚本运行参数配置完成: 自动代理")

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """日志回调"""

        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log

        if "Request human takeover" in log:
            self.cur_user_log.status = "SRC 无法继续执行任务, 需要用户接管"
        elif "Close game during wait" in log:
            self.cur_user_log.status = "Success!"
        elif "[src] exited" in log or not await self.src_process_manager.is_running():
            self.cur_user_log.status = "SRC 在完成任务前中止"
        elif "Please switch to a supported page before starting SRC" in log:
            self.cur_user_log.status = "SRC 启动时游戏停留在不支持的页面"
        elif "CRITICAL" in log:
            self.cur_user_log.status = "SRC 发生严重错误"
        elif datetime.now() - latest_time > timedelta(
            minutes=self.script_config.get("Run", "RunTimeLimit")
        ):
            self.cur_user_log.status = "SRC 进程超时"
        else:
            self.cur_user_log.status = "SRC 正常运行中"

        logger.debug(f"SRC 脚本日志分析结果: {self.cur_user_log.status}")
        if self.cur_user_log.status != "SRC 正常运行中":
            logger.info(f"SRC 脚本任务结果: {self.cur_user_log.status}, 日志锁已释放")
            self.wait_event.set()

    async def final_task(self):
        if self.check_result != "Pass":
            return

        # 结束各子任务
        await self.src_log_monitor.stop()
        await self.src_process_manager.kill()
        await System.kill_process(self.src_exe_path)
        if self.script_config.get("Run", "TaskTransitionMethod") == "ExitEmulator":
            logger.info("用户任务结束, 关闭模拟器")
            try:
                await self.emulator_manager.close(
                    self.script_config.get("Emulator", "Index")
                )
            except Exception as e:
                logger.exception(f"关闭模拟器失败: {e}")

        del self.src_process_manager
        del self.src_log_monitor

        user_logs_list = []
        for t, log_item in self.cur_user_item.log_record.items():
            dt = t.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone(UTC4)
            log_path = (
                Path.cwd()
                / f"history/{dt.strftime('%Y-%m-%d')}/{self.cur_user_item.name}/{dt.strftime('%H-%M-%S')}.log"
            )
            user_logs_list.append(log_path.with_suffix(".json"))

            if log_item.status == "SRC 正常运行中":
                log_item.status = "任务被用户手动中止"

            if len(log_item.content) == 0:
                log_item.content = ["未捕获到任何日志内容"]
                log_item.status = "未捕获到日志"

            await Config.save_src_log(log_path, log_item.content, log_item.status)

        statistics = await Config.merge_statistic_info(user_logs_list)
        statistics["user_info"] = self.cur_user_item.name
        statistics["start_time"] = self.user_start_time.strftime("%Y-%m-%d %H:%M:%S")
        statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        statistics["user_result"] = (
            "代理任务全部完成" if self.run_book else self.cur_user_item.result
        )

        # 判断是否成功
        success_symbol = "√" if self.run_book else "X"

        try:
            await push_notification(
                "统计信息",
                f"{datetime.now().strftime('%m-%d')} |{success_symbol}|  {self.cur_user_item.name} 的自动代理统计报告",
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

        if self.run_book:
            if (
                self.cur_user_config.get("Data", "ProxyTimes") == 0
                and self.cur_user_config.get("Info", "RemainedDay") != -1
            ):
                await self.cur_user_config.set(
                    "Info",
                    "RemainedDay",
                    self.cur_user_config.get("Info", "RemainedDay") - 1,
                )
            await self.cur_user_config.set(
                "Data",
                "ProxyTimes",
                self.cur_user_config.get("Data", "ProxyTimes") + 1,
            )
            self.cur_user_item.status = "完成"
            logger.success(f"用户 {self.cur_user_uid} 的自动代理任务已完成")
            await Notify.push_plyer(
                "成功完成一个自动代理任务！",
                f"已完成用户 {self.cur_user_item.name} 的自动代理任务",
                f"已完成 {self.cur_user_item.name} 的自动代理任务",
                3,
            )
        else:
            logger.error(f"用户 {self.cur_user_uid} 的自动代理任务未完成")
            self.cur_user_item.status = "异常"

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.exception(f"自动代理任务出现异常: {e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"自动代理任务出现异常: {e}"},
        )
