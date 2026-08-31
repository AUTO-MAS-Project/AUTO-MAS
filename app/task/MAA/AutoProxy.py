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
import calendar
import re
import uuid
import asyncio
import shutil
from copy import deepcopy
from pathlib import Path
from datetime import datetime

from app.core import Config
from app.core.ws import Publisher, protocol
from app.models.schema import WSTaskNoticeData
from app.models.task import TaskExecuteBase, ScriptItem, LogRecord
from app.models.ConfigBase import MultipleConfig
from app.models.config import MaaConfig, MaaUserConfig
from app.models.emulator import DeviceInfo, DeviceBase
from app.services import Notify, System
from app.utils import get_logger, LogMonitor, ProcessManager
from app.utils.io import read_file, write_file
from app.utils.constants import (
    UTC4,
    MAA_TASKS,
    MAA_TASKS_ZH,
    MAA_STAGE_KEY,
    MAA_ANNIHILATION_FIGHT_BASE,
    MAA_REMAIN_FIGHT_BASE,
    ARKNIGHTS_PACKAGE_NAME,
    MAA_RUN_MOOD_BOOK,
    MAA_TASK_TRANSITION_METHOD_BOOK,
)
from .tools import (
    push_notification,
    agree_bilibili,
    update_maa,
    ensure_game_updated,
)
from app.task.general.tools import execute_script_task

# OLD: 旧版 MAA（PR #17392 前）gui.json 的 ClientType 字符串 → 新版枚举整数映射
# 新版：Official=0, Bilibili=1, YoStarEN=2, YoStarJP=3, YoStarKR=4, txwy=5
_MAA_CLIENT_TYPE_TO_INT = {
    "Official": 0,
    "Bilibili": 1,
    "YoStarEN": 2,
    "YoStarJP": 3,
    "YoStarKR": 4,
    "txwy": 5,
}


logger = get_logger("MAA 自动代理")
_ANNIHILATION_PROGRESS_RE = re.compile(
    r"(?:剿灭模式|剿滅模式|Annihilation(?: Mode| weekly limit)|殲滅作戦|섬멸 모드)\s*[:：]\s*(\d+)\s*/\s*(\d+)",
    re.IGNORECASE,
)
_MAA_SANITY_COMPLETION_MARKERS = (
    "完成任务: 理智作战",
    "完成任务: 活动关优先",
    "完成任务: 库存保持",
    "完成任务: 剩余理智",
)
_MAA_FIGHT_COMPLETION_MARKER = "Completed Task Chain: Fight"


def _current_week_marker(now: datetime) -> str:
    """返回 ISO 周标记。"""

    iso_year, iso_week, _ = now.isocalendar()
    return f"{iso_year:04d}-W{iso_week:02d}"


def _should_run_annihilation(
    start_weekday: str,
    completed_week: str,
    now: datetime,
) -> bool:
    """判断当前用户本次是否应执行剿灭。"""

    if completed_week == _current_week_marker(now):
        return False
    return now.weekday() >= getattr(calendar, start_weekday.upper())


def _parse_annihilation_weekly_progress(log: str) -> tuple[int, int] | None:
    """解析 MAA 输出的剿灭周进度。"""

    matches = _ANNIHILATION_PROGRESS_RE.findall(log)
    if not matches:
        return None
    current, total = (int(value) for value in matches[-1])
    return (current, total) if total > 0 else None


def _has_completed_sanity_task(log_records: list[LogRecord]) -> bool:
    """判断日志记录中是否已经完成过体力任务。"""

    for log_record in log_records:
        lines = log_record.content
        if any(
            marker in line
            for line in lines
            for marker in _MAA_SANITY_COMPLETION_MARKERS
        ):
            return True

        for index, line in enumerate(lines):
            if _MAA_FIGHT_COMPLETION_MARKER not in line:
                continue
            previous_task = next(
                (item for item in reversed(lines[:index]) if "完成任务:" in item),
                "",
            )
            if "剿灭" in previous_task:
                continue
            if not previous_task and _ANNIHILATION_PROGRESS_RE.search(
                "".join(lines[max(0, index - 8) : index + 1])
            ):
                continue
            return True

    return False


def _merge_fight_task(source_task: dict, managed_task: dict) -> dict:
    """继承 MAA 原生配置，并以基础任务覆盖 MAS 托管字段。"""

    return {**deepcopy(source_task), **deepcopy(managed_task)}


def _find_task_source(task_queue: list[dict], name: str, task_type: str) -> dict | None:
    """优先按任务名称取原生配置，兼容旧配置中只有任务类型的情况。"""

    for task in task_queue:
        if (
            isinstance(task, dict)
            and task.get("TaskType") == task_type
            and task.get("Name") == name
        ):
            return deepcopy(task)
    for task in task_queue:
        if isinstance(task, dict) and task.get("TaskType") == task_type:
            return deepcopy(task)
    return None


def _build_maa_preset_task_queue(source_queue: list[dict]) -> list[dict]:
    """复用 MAA 原生预设队列，补充 MAS 合成任务并移除生息演算。"""

    source_tasks = [deepcopy(task) for task in source_queue if isinstance(task, dict)]

    def source_or_default(name: str, task_type: str) -> dict:
        task = _find_task_source(source_tasks, name, task_type) or {
            "$type": f"{task_type}Task",
            "IsEnable": True,
        }
        task.update({"Name": name, "TaskType": task_type})
        return task

    fight_source = _find_task_source(source_tasks, "理智作战", "Fight") or {}
    annihilation = _merge_fight_task(
        _find_task_source(source_tasks, "剿灭作战", "Fight") or fight_source,
        MAA_ANNIHILATION_FIGHT_BASE,
    )
    activity = _build_activity_priority_fight(
        _find_task_source(source_tasks, "活动关优先", "Fight") or fight_source,
        "",
        0,
    )
    remain = _find_task_source(source_tasks, "剩余理智", "Fight")
    if remain is None:
        remain = _merge_fight_task(fight_source, MAA_REMAIN_FIGHT_BASE)
    remain.update({"Name": "剩余理智", "TaskType": "Fight", "IsEnable": True})
    depot = _find_task_source(source_tasks, "库存保持", "DepotMaintain")
    if depot is None:
        depot = _build_depot_maintain_task("[]")
    depot.update({"Name": "库存保持", "TaskType": "DepotMaintain", "IsEnable": True})

    queue = [
        source_or_default("开始唤醒", "StartUp"),
        annihilation,
        source_or_default("自动公招", "Recruit"),
        source_or_default("基建换班", "Infrast"),
        activity,
        depot,
        source_or_default("理智作战", "Fight"),
        remain,
        source_or_default("信用收支", "Mall"),
        source_or_default("领取奖励", "Award"),
    ]

    known_names = {task["Name"] for task in queue}
    queue.extend(
        deepcopy(task)
        for task in source_tasks
        if task.get("TaskType") != "Reclamation" and task.get("Name") not in known_names
    )
    return queue


def _build_depot_maintain_task(
    plans_json: str,
    source_task: dict | None = None,
) -> dict:
    """生成 MAA 库存保持任务配置。"""

    source_task = source_task or {}
    source_plans = source_task.get("PlanList") or []
    if not isinstance(source_plans, list):
        source_plans = []
    plans = []
    for plan in json.loads(plans_json):
        if (
            isinstance(plan, dict)
            and isinstance(plan.get("Stage"), str)
            and bool(plan["Stage"])
            and isinstance(plan.get("DropId"), str)
            and bool(plan["DropId"])
            and isinstance(plan.get("DropCount"), int)
            and not isinstance(plan.get("DropCount"), bool)
            and plan["DropCount"] > 0
        ):
            source_plan = next(
                (
                    item
                    for item in source_plans
                    if isinstance(item, dict)
                    and item.get("Stage") == plan["Stage"]
                    and item.get("DropId") == plan["DropId"]
                ),
                {},
            )
            plans.append(
                {
                    **deepcopy(source_plan),
                    "UseMedicine": False,
                    "MedicineCount": 0,
                    "UseStone": False,
                    "StoneCount": 0,
                    "Stage": plan["Stage"],
                    "DropId": plan["DropId"],
                    "DropCount": plan["DropCount"],
                }
            )

    return {
        "$type": source_task.get("$type", "DepotMaintainTask"),
        "Name": "库存保持",
        "IsEnable": True,
        "TaskType": "DepotMaintain",
        "UpdateDepot": source_task.get("UpdateDepot", True),
        "IsStageManually": source_task.get("IsStageManually", False),
        "SkipDuringActivity": source_task.get("SkipDuringActivity", False),
        "SkipDuringResourceCollection": source_task.get(
            "SkipDuringResourceCollection", False
        ),
        "UseAutoSeries": source_task.get("UseAutoSeries", True),
        "PlanList": plans,
    }


def _resolve_activity_stage(
    activity_stages: list[dict], configured_index: int
) -> str | None:
    """按序号选择当前活动材料关卡，序号失效时回退到第一项。"""

    stages = [
        stage["Value"]
        for stage in activity_stages
        if isinstance(stage, dict)
        and isinstance(stage.get("Value"), str)
        and stage["Value"]
    ]
    if not stages:
        return None
    return (
        stages[configured_index - 1] if configured_index <= len(stages) else stages[0]
    )


def _build_activity_priority_fight(
    fight_task: dict, activity_stage: str, medicine_numb: int
) -> dict:
    """生成 MAA 活动关优先任务，使用独立理智药额度。

    活动关优先与理智作战刻意保持为两个独立任务，分别使用各自的理智药
    额度（Task.ActivityMedicineNumb 与计划表 MedicineNumb），互不转移。
    """

    activity_fight = deepcopy(fight_task)
    activity_fight.update(
        {
            "Name": "活动关优先",
            "IsEnable": True,
            "StagePlan": [activity_stage],
            "IsStageManually": True,
            "UseOptionalStage": False,
            "UseWeeklySchedule": False,
            "EnableTargetDrop": False,
            "DropId": "",
            "DropCount": 0,
            "IsInventoryTarget": False,
            "EnableTimesLimit": False,
            "UseMedicine": medicine_numb > 0,
            "MedicineCount": medicine_numb,
        }
    )
    activity_fight.setdefault("$type", "FightTask")
    return activity_fight


class AutoProxyTask(TaskExecuteBase):
    """自动代理模式"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: MaaConfig,
        user_config: MultipleConfig[MaaUserConfig],
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
        self._annihilation_weekly_completion_recorded = False

    async def check(self) -> str:

        # 单独运行脚本是用户主动指定的一次性运行，不受单日代理次数上限约束
        if (
            self.task_info.is_queue_task
            and self.script_config.get("Run", "ProxyTimesLimit") != 0
            and self.cur_user_config.get("Data", "ProxyTimes")
            >= self.script_config.get("Run", "ProxyTimesLimit")
        ):
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
            return "未找到用户的 MAA 配置文件，请先在用户配置页完成 「MAA配置」 步骤"
        return "Pass"

    async def prepare(self):

        self.maa_process_manager = ProcessManager()
        self.maa_log_monitor = LogMonitor(
            (1, 20),
            "%Y-%m-%d %H:%M:%S",
            self.check_log,
            except_logs=["如果长时间无进一步日志更新，可能需要手动干预。"],
        )
        self.wait_event = asyncio.Event()
        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now()
        self.if_game_hot_update = False
        self.pending_res_version = ""

        self.maa_root_path = Path(self.script_config.get("Info", "Path"))
        self.maa_set_path = self.maa_root_path / "config"
        self.maa_log_path = self.maa_root_path / "debug/gui.log"
        self.maa_exe_path = self.maa_root_path / "MAA.exe"
        self.maa_tasks_path = self.maa_root_path / "resource/tasks/tasks.json"

        self.run_book = {
            "Annihilation": self.cur_user_config.get("Info", "Annihilation") == "Close",
            "Routine": False,
        }

        if not self.run_book["Annihilation"]:
            now = datetime.now(tz=UTC4)
            start_weekday = self.cur_user_config.get("Info", "AnnihilationStartWeekday")

            if not _should_run_annihilation(
                start_weekday,
                self.cur_user_config.get("Data", "AnnihilationCompletedWeek"),
                now,
            ):
                self.run_book["Annihilation"] = True
                logger.info(
                    f"用户 {self.cur_user_item.name} 本次跳过剿灭："
                    f"开始日={start_weekday}，本周记录="
                    f"{self.cur_user_config.get('Data', 'AnnihilationCompletedWeek')}"
                )

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
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error",
                        message=f"用户 {self.cur_user_item.name} 检查未通过: {self.check_result}",
                    ),
                )
            return

        await self.prepare()

        logger.info(f"开始代理用户: {self.cur_user_uid}")
        self.cur_user_item.status = "运行"

        # 执行任务前脚本（每用户仅一次）
        if self.cur_user_config.get("Info", "IfScriptBeforeTask"):
            await execute_script_task(
                Path(self.cur_user_config.get("Info", "ScriptBeforeTask")),
                "脚本前任务",
            )

        # 执行剿灭 + 日常
        for self.mode in ["Annihilation", "Routine"]:
            if self.run_book[self.mode]:
                continue

            self.cur_user_item.status = f"运行 - {MAA_RUN_MOOD_BOOK[self.mode]}"

            if self.mode == "Routine":
                self.task_dict = {
                    task: self.cur_user_config.get("Task", f"If{task}")
                    for task in MAA_TASKS
                }
                if self.cur_user_config.get("Info", "StageMode") != "Fixed":
                    self.task_dict["DepotMaintain"] = False
            else:  # Annihilation
                self.task_dict = {
                    task: bool(task in ("StartUp", "Fight")) for task in MAA_TASKS
                }

            logger.info(
                f"用户 {self.cur_user_item.name} - 模式: {self.mode} - 任务列表: {list(self.task_dict.values())}"
            )

            for i in range(self.script_config.get("Run", "RunTimesLimit")):
                if self.run_book[self.mode]:
                    break
                logger.info(
                    f"用户 {self.cur_user_item.name} - 模式: {self.mode} - 尝试次数: {i + 1}/{self.script_config.get('Run', 'RunTimesLimit')}"
                )
                self.log_start_time = datetime.now()
                self.cur_user_item.log_record[self.log_start_time] = (
                    self.cur_user_log
                ) = LogRecord()

                try:
                    self.script_info.log = "正在启动模拟器"
                    emulator_info = await self.emulator_manager.open(
                        self.script_config.get("Emulator", "Index"),
                        ARKNIGHTS_PACKAGE_NAME[
                            self.cur_user_config.get("Info", "Server")
                        ],
                    )
                except Exception as e:
                    logger.opt(exception=True).warning(
                        f"用户: {self.cur_user_uid} - 模拟器启动失败: {e}"
                    )
                    await Publisher.send(
                        id=self.task_info.task_id,
                        type=protocol.TASK_NOTICE,
                        data=WSTaskNoticeData(
                            level="error",
                            message=f"启动模拟器时出现异常: {e}",
                        ),
                    )
                    self.cur_user_log.content = [
                        "模拟器启动失败, MAA 未实际运行, 无日志记录"
                    ]
                    self.cur_user_log.status = "模拟器启动失败"

                    try:
                        await self.emulator_manager.close(
                            self.script_config.get("Emulator", "Index")
                        )
                    except Exception as e:
                        logger.opt(exception=True).warning(f"关闭模拟器失败: {e}")

                    await Notify.push_plyer(
                        "用户自动代理出现异常！",
                        f"用户 {self.cur_user_item.name} 的{MAA_RUN_MOOD_BOOK[self.mode]}部分出现一次异常",
                        f"{self.cur_user_item.name}的{MAA_RUN_MOOD_BOOK[self.mode]}出现异常",
                        3,
                    )
                    continue

                if Config.get("Function", "IfSilence"):
                    try:
                        await self.emulator_manager.setVisible(
                            self.script_config.get("Emulator", "Index"), False
                        )
                    except Exception as e:
                        logger.opt(exception=True).warning(f"模拟器隐藏失败: {e}")

                # 需要用户手动更新游戏时重试无意义，直接结束本模式的重试
                if self.script_config.get(
                    "Run", "IfCheckGameUpdate"
                ) and not await self.handle_game_update(emulator_info):
                    break

                await self.set_maa(emulator_info)

                logger.info(f"启动MAA进程: {self.maa_exe_path}")
                self.wait_event.clear()
                await self.maa_process_manager.open_process(self.maa_exe_path)
                await asyncio.sleep(1)  # 等待 MAA 处理日志文件
                await self.maa_log_monitor.start_monitor_file(
                    self.maa_log_path, self.log_start_time
                )
                await self.wait_event.wait()
                await self.maa_log_monitor.stop()

                if self.cur_user_log.status == "Success!":
                    self.run_book[self.mode] = True
                    logger.info(f"用户: {self.cur_user_uid} - MAA进程完成代理任务")
                    self.script_info.log = (
                        "检测到 MAA 完成代理任务\n正在等待相关程序结束"
                    )
                    if self.pending_res_version:
                        # 代理成功说明资源热更新已走完，记录版本供下次比对
                        await self.cur_user_config.set(
                            "Data", "LastResVersion", self.pending_res_version
                        )
                        self.if_game_hot_update = False
                else:
                    logger.warning(
                        f"用户: {self.cur_user_uid} - 代理任务异常: {self.cur_user_log.status}"
                    )
                    self.script_info.log = (
                        f"{self.cur_user_log.status}\n正在中止相关程序"
                    )

                    await self.maa_process_manager.kill()
                    try:
                        await self.emulator_manager.close(
                            self.script_config.get("Emulator", "Index")
                        )
                    except Exception as e:
                        logger.opt(exception=True).warning(f"关闭模拟器失败: {e}")
                    await System.kill_process(self.maa_exe_path)

                    await Notify.push_plyer(
                        "用户自动代理出现异常！",
                        f"用户 {self.cur_user_item.name} 的{MAA_RUN_MOOD_BOOK[self.mode]}部分出现一次异常",
                        f"{self.cur_user_item.name}的{MAA_RUN_MOOD_BOOK[self.mode]}出现异常",
                        3,
                    )

                await update_maa(self.maa_root_path)
                await asyncio.sleep(3)

        # 执行任务后脚本（每用户仅一次）
        if self.cur_user_config.get("Info", "IfScriptAfterTask"):
            await execute_script_task(
                Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
                "脚本后任务",
            )

    async def set_maa(self, emulator_info: DeviceInfo):
        """配置MAA运行参数"""

        logger.info(f"开始配置MAA运行参数: {self.mode}")

        await self.maa_process_manager.kill()
        await System.kill_process(self.maa_exe_path)

        # 哔哩哔哩用户协议
        if self.cur_user_config.get("Info", "Server") == "Bilibili":
            await agree_bilibili(self.maa_tasks_path, True)
        else:
            await agree_bilibili(self.maa_tasks_path, False)

        # 基础配置内容
        if self.cur_user_config.get("Info", "Mode") == "简洁":
            shutil.copytree(
                (Path.cwd() / f"data/{self.script_info.script_id}/Default/ConfigFile"),
                self.maa_set_path,
                dirs_exist_ok=True,
            )
        elif self.cur_user_config.get("Info", "Mode") == "详细":
            shutil.copytree(
                (
                    Path.cwd()
                    / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile"
                ),
                self.maa_set_path,
                dirs_exist_ok=True,
            )

        gui_set = read_file(self.maa_set_path / "gui.json")
        gui_new_set = read_file(self.maa_set_path / "gui.new.json")

        # 多配置使用默认配置
        if gui_set["Current"] != "Default":
            gui_set["Configurations"]["Default"] = gui_set["Configurations"][
                gui_set["Current"]
            ]
            gui_new_set["Configurations"]["Default"] = gui_new_set["Configurations"][
                gui_set["Current"]
            ]
            gui_set["Current"] = "Default"

        # 各配置部分的引用
        global_set = gui_set["Global"]
        default_set = gui_set["Configurations"]["Default"]

        # 使用简体中文
        global_set["GUI.Localization"] = "zh-cn"  # OLD: 即将移除
        gui_new_set.setdefault("Gui", {})["Localization"] = "zh-cn"

        task_set = {}
        source_queue = gui_new_set["Configurations"]["Default"].get("TaskQueue", [])
        if not isinstance(source_queue, list):
            source_queue = []
        activity_stage = None
        if (
            self.mode == "Routine"
            and self.task_dict["Fight"]
            and self.cur_user_config.get("Task", "IfActivityFirst")
        ):
            stage_info = await Config.get_stage_info(
                "Info",
                server=self.cur_user_config.get("Info", "Server"),
                refresh=True,
            )
            activity_stage = _resolve_activity_stage(
                stage_info.get("Activity", []),
                self.cur_user_config.get("Task", "ActivityStageIndex"),
            )

        # 优先按任务名称匹配，确保多个 Fight 任务各自继承原生高级配置。
        for en_task, zh_task in zip(MAA_TASKS, MAA_TASKS_ZH):
            # 默认关闭时不写入新任务，兼容尚未支持库存保持的 MAA 版本
            if en_task == "DepotMaintain" and not self.task_dict[en_task]:
                continue

            task_set[en_task] = _find_task_source(source_queue, zh_task, en_task) or {
                "$type": f"{en_task}Task",
                "Name": zh_task,
                "IsEnable": False,
                "TaskType": en_task,
            }

        annihilation_source = _find_task_source(source_queue, "剿灭作战", "Fight")
        activity_source = _find_task_source(source_queue, "活动关优先", "Fight")
        remain_source = _find_task_source(source_queue, "剩余理智", "Fight")

        if "DepotMaintain" in task_set:
            task_set["DepotMaintain"] = _build_depot_maintain_task(
                self.cur_user_config.get("Task", "DepotMaintainPlans"),
                source_task=task_set["DepotMaintain"],
            )

        # 关闭所有定时
        for i in range(1, 9):
            global_set[f"Timer.Timer{i}"] = "False"  # OLD: 即将移除
        # NEW: Timers.List[*].IsEnabled = false
        if "Timers" not in gui_new_set:
            gui_new_set["Timers"] = {}
        if "List" not in gui_new_set["Timers"]:
            gui_new_set["Timers"]["List"] = []
        for timer in gui_new_set["Timers"].get("List", []):
            if isinstance(timer, dict):
                timer["IsEnabled"] = False

        # 矫正 ADB 地址
        if emulator_info.adb_address != "Unknown":
            default_set["Connect.Address"] = emulator_info.adb_address  # OLD: 即将移除
            gui_new_set.setdefault("Configurations", {}).setdefault(
                "Default", {}
            ).setdefault("Gui", {}).setdefault("ConnectSettings", {})[
                "Address"
            ] = emulator_info.adb_address

        # 任务间切换方式
        post_actions_str = MAA_TASK_TRANSITION_METHOD_BOOK[
            self.script_config.get("Run", "TaskTransitionMethod")
        ]
        default_set["MainFunction.PostActions"] = post_actions_str  # OLD: 即将移除
        # NEW: PostActions [Flags] 枚举整数 (None=0, ExitSelf=8, ExitArknights=1, ExitEmulator=4)
        gui_new_set.setdefault("Configurations", {}).setdefault(
            "Default", {}
        ).setdefault("Gui", {})["PostActions"] = int(post_actions_str)

        # 直接运行任务
        default_set["Start.StartGame"] = "True"  # OLD: 即将移除
        default_set["Start.RunDirectly"] = "True"  # OLD: 即将移除
        default_set["Start.OpenEmulatorAfterLaunch"] = "False"  # OLD: 即将移除
        # NEW:
        gui_new_set.setdefault("Configurations", {}).setdefault(
            "Default", {}
        ).setdefault("Gui", {}).setdefault("RuntimeSettings", {})["StartGame"] = True
        gui_new_set.setdefault("Configurations", {}).setdefault(
            "Default", {}
        ).setdefault("Gui", {}).setdefault("StartUpSettings", {})["RunDirectly"] = True
        gui_new_set.setdefault("Configurations", {}).setdefault(
            "Default", {}
        ).setdefault("Gui", {}).setdefault("StartUpSettings", {})[
            "StartEmulator"
        ] = False

        # 更新配置
        global_set["VersionUpdate.ScheduledUpdateCheck"] = "False"  # OLD: 即将移除
        global_set["VersionUpdate.AutoDownloadUpdatePackage"] = "True"  # OLD: 即将移除
        global_set["VersionUpdate.AutoInstallUpdatePackage"] = "False"  # OLD: 即将移除
        # NEW:
        gui_new_set.setdefault("Update", {})["CheckOnSchedule"] = False
        gui_new_set.setdefault("Update", {})["AutoDownloadUpdatePackage"] = True
        gui_new_set.setdefault("Update", {})["AutoInstallUpdatePackage"] = False

        # 静默模式相关配置
        if Config.get("Function", "IfSilence"):
            global_set["GUI.UseTray"] = "True"  # OLD: 即将移除
            global_set["GUI.MinimizeToTray"] = "True"  # OLD: 即将移除
            global_set["Start.MinimizeDirectly"] = "True"  # OLD: 即将移除
            # NEW:
            gui_new_set.setdefault("Gui", {})["UseTray"] = True
            gui_new_set.setdefault("Gui", {})["MinimizeToTray"] = True
            gui_new_set.setdefault("Gui", {})["MinimizeOnStartup"] = True

        # 服务器与账号切换
        default_set["Start.ClientType"] = self.cur_user_config.get(
            "Info", "Server"
        )  # OLD: 即将移除
        # NEW: ClientType 枚举整数 (Official=0, Bilibili=1, ...)
        gui_new_set.setdefault("Configurations", {}).setdefault(
            "Default", {}
        ).setdefault("Gui", {}).setdefault("RuntimeSettings", {})[
            "ClientType"
        ] = _MAA_CLIENT_TYPE_TO_INT.get(self.cur_user_config.get("Info", "Server"), 0)
        if self.cur_user_config.get("Info", "Server") == "Official":
            task_set["StartUp"]["AccountName"] = (
                f"{self.cur_user_config.get('Info', 'Id')[:3]}****{self.cur_user_config.get('Info', 'Id')[7:]}"
                if len(self.cur_user_config.get("Info", "Id")) == 11
                else self.cur_user_config.get("Info", "Id")
            )
        elif self.cur_user_config.get("Info", "Server") == "Bilibili":
            task_set["StartUp"]["AccountName"] = self.cur_user_config.get("Info", "Id")

        # 加载关卡号配置
        if self.cur_user_config.get("Info", "StageMode") == "Fixed":
            plan_data = {
                stage_key: self.cur_user_config.get("Info", stage_key)
                for stage_key in MAA_STAGE_KEY
            }
        else:
            plan = Config.PlanConfig[
                uuid.UUID(self.cur_user_config.get("Info", "StageMode"))
            ]
            plan_data = {
                stage_key: plan.get_current_info(stage_key).getValue()
                for stage_key in MAA_STAGE_KEY
            }

        fight_source = deepcopy(task_set["Fight"])

        # 理智作战相关配置项
        if self.mode == "Annihilation":
            # 关卡配置
            task_set["Fight"] = _merge_fight_task(
                annihilation_source or fight_source, MAA_ANNIHILATION_FIGHT_BASE
            )
            task_set["Fight"]["UseMedicine"] = bool(
                plan_data.get("MedicineNumb", 0) != 0
            )
            task_set["Fight"]["MedicineCount"] = plan_data.get("MedicineNumb", 0)
            task_set["Fight"]["AnnihilationStage"] = self.cur_user_config.get(
                "Info", "Annihilation"
            )

        elif self.mode == "Routine":
            # 理智药配置
            task_set["Fight"]["UseMedicine"] = bool(
                plan_data.get("MedicineNumb", 0) != 0
            )
            task_set["Fight"]["MedicineCount"] = plan_data.get("MedicineNumb", 0)
            # 关卡配置
            task_set["Fight"]["Series"] = int(plan_data.get("SeriesNumb", "0"))
            task_set["Fight"]["StagePlan"] = [
                (
                    ""
                    if plan_data.get(stage_key, "-") == "*"
                    else plan_data.get(stage_key, "-")
                )
                for stage_key in ("Stage", "Stage_1", "Stage_2", "Stage_3")
                if plan_data.get(stage_key, "-") != "-"
            ]
            task_set["Fight"]["IsStageManually"] = True
            task_set["Fight"]["UseOptionalStage"] = True
            task_set["Fight"]["UseWeeklySchedule"] = False

            # 简洁模式下托管的配置
            if self.cur_user_config.get("Info", "Mode") == "简洁":
                task_set["Fight"]["EnableTimesLimit"] = False
                task_set["Fight"]["EnableTargetDrop"] = False
                fight_source = deepcopy(task_set["Fight"])

            # 基建配置
            if self.cur_user_config.get("Info", "InfrastMode") == "Custom":
                infrast_path = (
                    Path.cwd()
                    / f"data/{self.script_info.script_id}/{self.cur_user_uid}/Infrastructure/infrastructure.json"
                )
                if self.cur_user_config.get("Info", "InfrastIndex") != "-1":
                    infrast_path.parent.mkdir(parents=True, exist_ok=True)
                    infrast_path.write_text(
                        self.cur_user_config.get("Data", "CustomInfrast"),
                        encoding="utf-8",
                    )
                    task_set["Infrast"]["Mode"] = "Custom"
                    task_set["Infrast"]["Filename"] = str(infrast_path)
                    task_set["Infrast"]["InfrastPlan"] = [
                        {
                            "Index": index,
                            "Name": infrast.get("name", f"第 {index + 1} 班"),
                            "Description": infrast.get("description", ""),
                            "DescriptionPost": infrast.get("description_post", ""),
                            "Period": infrast.get("period", []),
                        }
                        for index, infrast in enumerate(
                            json.loads(
                                self.cur_user_config.get("Data", "CustomInfrast")
                            ).get("plans", [])
                        )
                    ]
                    task_set["Infrast"]["PlanSelect"] = int(
                        self.cur_user_config.get("Info", "InfrastIndex")
                    )
                else:
                    logger.warning(
                        f"用户 {self.cur_user_item.name} 的自定义基建配置文件解析失败, 将使用普通基建模式"
                    )
                    await Publisher.send(
                        id=self.task_info.task_id,
                        type=protocol.TASK_NOTICE,
                        data=WSTaskNoticeData(
                            level="warning",
                            message=f"未能解析用户 {self.cur_user_item.name} 的自定义基建配置文件",
                        ),
                    )
                    task_set["Infrast"]["Mode"] = "Normal"
            else:
                task_set["Infrast"]["Mode"] = self.cur_user_config.get(
                    "Info", "InfrastMode"
                )

        activity_fight = None
        if self.mode == "Routine" and activity_stage:
            activity_medicine_numb = self.cur_user_config.get(
                "Task", "ActivityMedicineNumb"
            )
            activity_fight = _build_activity_priority_fight(
                activity_source or fight_source, activity_stage, activity_medicine_numb
            )

        # 导出任务配置
        self.task_dict["StartUp"] = True
        task_queue = gui_new_set["Configurations"]["Default"]["TaskQueue"] = []
        for task_type in MAA_TASKS:
            if task_type not in task_set:
                continue

            task_set[task_type]["IsEnable"] = self.task_dict[task_type]
            task_queue.append(task_set[task_type])

            if task_type == "StartUp" and activity_fight:
                task_queue.append(activity_fight)

            # 剩余理智关卡配置
            if (
                self.mode == "Routine"
                and task_type == "Fight"
                and self.task_dict["Fight"]
                and plan_data.get("Stage_Remain", "-") != "-"
            ):
                remain_fight = _merge_fight_task(
                    remain_source or fight_source, MAA_REMAIN_FIGHT_BASE
                )
                remain_fight["StagePlan"] = [
                    (
                        ""
                        if plan_data.get("Stage_Remain", "-") == "*"
                        else plan_data.get("Stage_Remain", "-")
                    )
                ]
                remain_fight["Series"] = int(plan_data.get("SeriesNumb", "0"))
                task_queue.append(remain_fight)

        (self.maa_set_path / "gui.json").write_text(  # OLD: 即将移除
            json.dumps(gui_set, ensure_ascii=False, indent=4),
            encoding="utf-8",  # OLD: 即将移除
        )  # OLD: 即将移除
        write_file(self.maa_set_path / "gui.new.json", gui_new_set)

        logger.success(f"MAA运行参数配置完成: {self.mode}")

    async def handle_game_update(self, emulator_info: DeviceInfo) -> bool:
        """启动 MAA 前接管游戏更新。

        Returns:
            bool: 是否可以继续本次代理；``False`` 表示需要用户手动更新游戏。
        """

        self.script_info.log = "正在检查游戏更新"

        async def report(text: str) -> None:
            self.script_info.log = text

        try:
            result = await ensure_game_updated(
                adb_path=self.emulator_manager.get_adb_path(),
                adb_address=emulator_info.adb_address,
                server=self.cur_user_config.get("Info", "Server"),
                package_name=ARKNIGHTS_PACKAGE_NAME[
                    self.cur_user_config.get("Info", "Server")
                ],
                apk_dir=Path.cwd() / "data/GameApk",
                if_auto_install=self.script_config.get("Run", "IfAutoInstallGameApk"),
                time_limit=self.script_config.get("Run", "GameUpdateTimeLimit"),
                progress=report,
            )
        except Exception as e:
            # 检查本身异常不应阻断代理，交回 MAA 原有流程判定
            logger.opt(exception=True).warning(f"游戏更新检查异常: {e}")
            return True

        logger.info(f"游戏更新检查结果: {result.status} - {result.message}")

        # 服务端资源版本与上次成功代理时不一致，说明本次开始唤醒会触发资源热更新
        if result.resource_version:
            self.pending_res_version = result.resource_version
            self.if_game_hot_update = (
                result.resource_version
                != self.cur_user_config.get("Data", "LastResVersion")
            )
            if self.if_game_hot_update:
                logger.info(
                    f"检测到待下载的游戏资源热更新: {result.resource_version}，"
                    f"本次超时限制放宽至 {self.script_config.get('Run', 'GameUpdateTimeLimit')} 分钟"
                )

        if result.status != "NeedManualUpdate":
            return True

        self.cur_user_log.content = [result.message]
        self.cur_user_log.status = "游戏需要手动更新"
        self.script_info.log = result.message

        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=result.message),
        )
        try:
            await self.emulator_manager.close(
                self.script_config.get("Emulator", "Index")
            )
        except Exception as e:
            logger.opt(exception=True).warning(f"关闭模拟器失败: {e}")

        await Notify.push_plyer(
            "游戏需要手动更新！",
            result.message,
            f"{self.cur_user_item.name}的游戏需要手动更新",
            3,
        )
        return False

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """日志回调"""

        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log

        if self.mode == "Annihilation":
            progress = _parse_annihilation_weekly_progress(log)
            completed = progress and progress[0] >= progress[1]
            completed = completed or "完成任务: 剿灭作战" in log
            if completed:
                self.task_dict["Fight"] = False
                self.run_book["Annihilation"] = True
                if not self._annihilation_weekly_completion_recorded:
                    await self.cur_user_config.set(
                        "Data",
                        "AnnihilationCompletedWeek",
                        _current_week_marker(datetime.now(tz=UTC4)),
                    )
                    self._annihilation_weekly_completion_recorded = True
                    progress_text = (
                        f"{progress[0]}/{progress[1]}" if progress else "完成任务日志"
                    )
                    logger.info(
                        f"用户 {self.cur_user_item.name} 剿灭已达到本周上限："
                        f"{progress_text}"
                    )

        if "未选择任务" in log:
            self.cur_user_log.status = "MAA 未选择任何任务"
        elif "任务出错: 开始唤醒" in log:
            self.cur_user_log.status = "MAA 未能正确登录 PRTS"
        elif "任务已全部完成！" in log:
            for en_task, zh_task in zip(MAA_TASKS, MAA_TASKS_ZH):
                if f"完成任务: {zh_task}" in log or f"{zh_task} 任务跳过" in log:
                    self.task_dict[en_task] = False

            if self.mode == "Routine" and (
                "任务出错: 理智作战" in log
                or any(
                    f"理智作战: {task_name} 添加任务失败" in log
                    for task_name in ("活动关优先", "理智作战", "剩余理智")
                )
            ):
                self.task_dict["Fight"] = True

            if any(self.task_dict.values()):
                self.cur_user_log.status = "MAA 部分任务执行失败"
            else:
                self.cur_user_log.status = "Success!"

        elif "请 ｢检查连接设置｣ → ｢尝试重启模拟器与 ADB｣ → ｢重启电脑｣" in log:
            self.cur_user_log.status = "MAA 的 ADB 连接异常"
        elif "未检测到任何模拟器" in log:
            self.cur_user_log.status = "MAA 未检测到任何模拟器"
        elif "已停止" in log:
            self.cur_user_log.status = "MAA 在完成任务前中止"
        elif (
            "MaaAssistantArknights GUI exited" in log
            or not await self.maa_process_manager.is_running()
        ):
            self.cur_user_log.status = "MAA 在完成任务前退出"
        elif self.is_log_stalled(
            latest_time,
            minutes=(
                # 本次开始唤醒会触发资源热更新时放宽超时，避免把正常更新误判为卡死
                max(
                    self.script_config.get("Run", f"{self.mode}TimeLimit"),
                    self.script_config.get("Run", "GameUpdateTimeLimit"),
                )
                if self.if_game_hot_update
                else self.script_config.get("Run", f"{self.mode}TimeLimit")
            ),
        ):
            self.cur_user_log.status = "MAA 进程超时"
        else:
            self.cur_user_log.status = "MAA 正常运行中"

        logger.debug(f"MAA 日志分析结果: {self.cur_user_log.status}")
        if self.cur_user_log.status != "MAA 正常运行中":
            logger.info(f"MAA 任务结果: {self.cur_user_log.status}, 日志锁已释放")
            self.wait_event.set()

    async def final_task(self):

        if self.check_result != "Pass":
            return

        await self.maa_log_monitor.stop()
        await self.maa_process_manager.kill()
        await System.kill_process(self.maa_exe_path)
        await agree_bilibili(self.maa_tasks_path, False)
        if self.script_config.get("Run", "TaskTransitionMethod") == "ExitEmulator":
            logger.info("用户任务结束, 关闭模拟器")
            try:
                await self.emulator_manager.close(
                    self.script_config.get("Emulator", "Index")
                )
            except Exception as e:
                logger.opt(exception=True).warning(f"关闭模拟器失败: {e}")

        user_logs_list = []
        if_six_star = False
        for t, log_item in self.cur_user_item.log_record.items():
            if log_item.status == "MAA 正常运行中":
                log_item.status = "任务被用户手动中止"

            dt = t.astimezone(UTC4)
            log_path = Config.build_history_log_path(
                script_name=self.script_info.name,
                user_name=self.cur_user_item.name,
                log_time=dt,
            )
            user_logs_list.append(log_path.with_suffix(".json"))

            if await Config.save_maa_log(log_path, log_item.content, log_item.status):
                if_six_star = True

        statistics = await Config.merge_statistic_info(user_logs_list)
        statistics["user_info"] = self.cur_user_item.name
        statistics["start_time"] = self.user_start_time.strftime("%Y-%m-%d %H:%M:%S")
        statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        statistics["maa_result"] = (
            "代理任务全部完成"
            if (self.run_book["Annihilation"] and self.run_book["Routine"])
            else self.cur_user_item.result
        )

        # 判断是否成功
        if_success = self.run_book["Annihilation"] and self.run_book["Routine"]
        success_symbol = "√" if if_success else "X"

        # 任务被中止时，只要日志中已经完成过体力任务，也应发送掉落统计。
        should_send_statistics = if_success or _has_completed_sanity_task(
            list(self.cur_user_item.log_record.values())
        )
        if should_send_statistics:
            try:
                await push_notification(
                    "统计信息",
                    f"{datetime.now().strftime('%m-%d')} |{success_symbol}|  {self.cur_user_item.name} 的自动代理统计报告",
                    statistics,
                    self.cur_user_config,
                )
            except Exception as e:
                logger.opt(exception=True).warning(f"推送统计通知时出现异常: {e}")
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error", message=f"推送统计通知时出现异常: {e}"
                    ),
                )

        # 六星通知独立处理，避免单个通知异常阻断掉落统计。
        if if_six_star:
            try:
                await push_notification(
                    "公招六星",
                    f"喜报: 用户 {self.cur_user_item.name} 公招出六星啦！",
                    {"user_name": self.cur_user_item.name},
                    self.cur_user_config,
                )
            except Exception as e:
                logger.opt(exception=True).warning(f"推送六星通知时出现异常: {e}")
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error", message=f"推送六星通知时出现异常: {e}"
                    ),
                )

        if self.run_book["Annihilation"] and self.run_book["Routine"]:
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

            if self.cur_user_config.get("Info", "InfrastIndex") != "-1":
                await self.cur_user_config.set(
                    "Data",
                    "InfrastIndex",
                    str(
                        (int(self.cur_user_config.get("Info", "InfrastIndex")) + 1)
                        % len(
                            json.loads(
                                self.cur_user_config.get("Data", "CustomInfrast")
                            ).get("plans", [])
                        )
                    ),
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
            logger.warning(f"用户 {self.cur_user_uid} 的自动代理任务未完成")
            self.cur_user_item.status = "异常"

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"自动代理任务出现异常: {e}")
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"自动代理任务出现异常: {e}"),
        )
