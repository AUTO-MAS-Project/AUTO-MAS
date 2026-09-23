#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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


import asyncio
import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core import Config
from app.core.ws import Publisher, protocol
from app.log_box import log_box
from app.models.config import MaaEndConfig, MaaEndUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.emulator import DeviceBase, DeviceInfo
from app.models.schema import WSTaskNoticeData
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase
from app.services import Notify, System
from app.task.emulator_core import close_emulator
from app.task.general.tools import execute_script_task
from app.task.proxy_helpers import append_push_log
from app.utils import (
    LogMonitor,
    ProcessManager,
    get_logger,
    is_backend_dev_mode,
    is_process_running,
)
from app.utils.constants import (
    MAAEND_AUTO_COLLECT_TASK,
    MAAEND_DELIVERY_TASK,
    MAAEND_RUN_MOOD_BOOK,
    MAAEND_TASKS,
    UTC4,
)
from app.utils.io import (
    mark_native_config_injected,
    read_file,
    swap_in_dir,
    write_file,
)

from .push_log import MAAEND_PUSH_RULES, maaend_resolve
from .resource_loader import (
    MaaEndResourceLoader,
    get_loaded_maaend_options,
    load_maaend_interface_i18n,
    load_maaend_task_i18n,
    maaend_task_option_supported,
    maaend_task_supported,
)
from .ScriptConfig import maaend_config_mode, maaend_mas_config_dir
from .tools import push_notification, replace_account_switch_task
from .tools.backup_archive import archive_mas_runtime_backup, read_overlay_values

logger = get_logger("MaaEnd 自动代理")

_MAAEND_ACCOUNT_SWITCH_TASK = "AccountSwitch"
_MAAEND_GAME_SETTING_PRETASK = "__MXU_PRETASK__GameSetting"
_MAAEND_CLOSE_GAME_TASK = "CloseGamePC"
_AUTOMAS_GAME_PRE_ACTION_ID = "automas-endfield"
_MAAEND_SANITY_TASK_NAMES = {"ProtocolSpace", "AutoEssence"}


def _load_json_dict(value: object) -> dict[str, object]:
    """读取配置中的 JSON 对象，兼容运行时直接传入字典。"""

    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(data, dict):
            return data
    return {}


def _load_json_list(value: object) -> list[str]:
    """读取配置中的 JSON 字符串列表。"""

    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(data, list):
            return [str(item) for item in data if str(item).strip()]
    return []


def _task_enabled_for_mode(task_name: object, enabled: object, mode: str) -> bool:
    """按送货/日常/自动采集阶段筛选 MaaEnd 任务。"""

    name = str(task_name)
    if mode == "Delivery":
        return bool(enabled) and name in {
            MAAEND_DELIVERY_TASK,
            _MAAEND_ACCOUNT_SWITCH_TASK,
        }
    if mode == "AutoCollect":
        return bool(enabled) and name in {
            MAAEND_AUTO_COLLECT_TASK,
            _MAAEND_ACCOUNT_SWITCH_TASK,
        }
    if mode == "Routine":
        return bool(enabled) and name not in {
            MAAEND_DELIVERY_TASK,
            MAAEND_AUTO_COLLECT_TASK,
        }
    raise ValueError(f"未知 MaaEnd 运行模式: {mode}")


def _select_auto_collect_routes(
    mode: str,
    selections: dict[str, list[str] | None],
    groups: list[dict[str, Any]],
    now: datetime,
) -> dict[str, list[str]]:
    """按东四区三日周期选择路线，沿用路线编号顺序以保持已有排程。"""
    cycle_index = now.date().toordinal() % 3
    selected_by_key = {}
    for key in ("AutoCollectRoutes", "AutoCollectCommonRoutes"):
        category_groups = [group for group in groups if group["configKey"] == key]
        available = {
            option["value"] for group in category_groups for option in group["options"]
        }
        # 自然排序使 Route16 排在 Route15 后，新增地区分组不会重排原路线。
        ordered = sorted(
            available,
            key=lambda name: (
                name.rstrip("0123456789"),
                int(name[len(name.rstrip("0123456789")) :] or 0),
            ),
        )
        selected = selections[key]
        if selected is None:
            selected = [
                value for group in category_groups for value in group["defaultCases"]
            ]
        selected_by_key[key] = {
            route
            for index, route in enumerate(ordered)
            if route in selected
            and (
                mode == "Concentrated"
                and cycle_index == 0
                or mode == "Distributed"
                and index % 3 == cycle_index
            )
        }
    return {
        group["value"]: [
            option["value"]
            for option in group["options"]
            if option["value"] in selected_by_key[group["configKey"]]
        ]
        for group in groups
    }


def _disable_removed_tasks(
    maaend_tasks: list[dict[str, object]],
    task_i18n: dict[str, str],
) -> set[str]:
    """禁用当前 MaaEnd 版本已移除的任务条目，返回被移除的任务名。

    MaaEnd 更新可能删除或合并旧任务，其加载配置时会静默移除无效条目；
    若注入的运行配置里只剩这类条目，MaaEnd 会以“没有启用的任务”拒绝启动，
    自动代理也会因该任务永不回报完成而反复重试。
    """

    removed_names: set[str] = set()
    for task in maaend_tasks:
        task_name = str(task.get("taskName"))
        if task_name.startswith("__MXU_") or task_name in task_i18n:
            continue
        task["enabled"] = False
        removed_names.add(task_name)
    return removed_names


def _place_managed_task(
    tasks: list[dict[str, object]],
    *,
    task_name: str,
    task_id: str,
    controller_type: str,
    enabled: bool,
    first: bool,
) -> dict[str, object]:
    """补齐 MAS 托管的上游任务，并固定在任务列表首尾。"""

    matching = [task for task in tasks if task.get("taskName") == task_name]
    task = (
        matching[0]
        if matching
        else {
            "id": task_id,
            "taskName": task_name,
            "expanded": False,
            "optionValues": {},
        }
    )
    task["enabled"] = enabled
    enabled_by_controller = task.setdefault("enabledByController", {})
    if isinstance(enabled_by_controller, dict):
        enabled_by_controller[controller_type] = True

    tasks[:] = [item for item in tasks if item.get("taskName") != task_name]
    if first:
        tasks.insert(0, task)
    else:
        tasks.append(task)
    return task


def _configure_game_pre_action(
    instance: dict[str, object],
    *,
    game_path: str,
    game_arguments: str,
) -> None:
    """让 MXU 在 PI pretask 完成后启动 Endfield。"""

    pre_actions = instance.get("preActions")
    if not isinstance(pre_actions, list):
        pre_actions = []
    pre_actions = [
        action
        for action in pre_actions
        if not (
            isinstance(action, dict) and action.get("id") == _AUTOMAS_GAME_PRE_ACTION_ID
        )
    ]
    pre_actions.insert(
        0,
        {
            "id": _AUTOMAS_GAME_PRE_ACTION_ID,
            "customName": "AUTO-MAS 启动终末地",
            "enabled": True,
            "program": game_path,
            "args": game_arguments,
            "waitForExit": False,
            "skipIfRunning": True,
            "useCmd": False,
        },
    )
    instance["preActions"] = pre_actions


class AutoProxyTask(TaskExecuteBase):
    """MaaEnd 自动代理模式"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: MaaEndConfig,
        user_config: MultipleConfig[MaaEndUserConfig],
        emulator_manager: DeviceBase | None,
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
        self.account_switch_task_name = ""
        self.color_match_failed_message: str | None = None
        self.retryable = True
        # 用户级「节点详情推送」开关（Notify.PushLogMode），prepare 时按配置启用
        self.push_log_enabled = False
        self.mode = "Routine"
        self.run_book: dict[str, bool] = {mode: False for mode in MAAEND_RUN_MOOD_BOOK}
        self.task_dict: dict[str, dict[str, bool]] | None = None
        self.task_name_map: dict[str, str] = {}
        self.unique_task: dict[str, str] = {}
        self.maaend_config_file: Path | None = None
        self.maaend_root_path: Path | None = None
        # 一轮运行内 check/prepare 会多次读同一份 mxu-MaaEnd.json，按文件签名缓存解析结果
        self._source_tasks_cache: (
            tuple[tuple, list[dict[str, object]] | None] | None
        ) = None
        self.first_run_mode: str | None = None
        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        self.auto_collect_run_at: datetime | None = None
        self.auto_collect_routes: dict[str, list[str]] = {}

    def _account_switch_method(self) -> str:
        """读取账号切换方式；缺失或非法值沿用 MaaEnd 默认入口。"""

        method = str(self.script_config.get("Run", "AccountSwitchMethod") or "")
        return method if method in {"MAS", "MAAEND"} else "MAAEND"

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

        account_id = str(self.cur_user_config.get("Info", "Id")).strip()
        account_switch_method = self._account_switch_method()
        if (
            account_switch_method == "MAS"
            and account_id
            and self.emulator_manager is not None
        ):
            self.cur_user_item.status = "异常"
            return "MAS 自建账号切换暂不支持模拟器，请改用 MAAEND 内置账号切换"
        if account_switch_method == "MAAEND" and account_id:
            if len(account_id) < 4 or not account_id[-4:].isdigit():
                self.cur_user_item.status = "异常"
                return "MAAEND 内置账号切换需要账号末四位为数字，请检查账号ID"

        if self.emulator_manager is None:
            root_path = self._maaend_root_path()
            if root_path is None:
                return "MaaEnd 路径未配置"
            try:
                loader = MaaEndResourceLoader.get_loaded(root_path)
            except ValueError as error:
                return f"MaaEnd 资源加载失败: {error}"
            if not loader.has_pretask("GameSetting") or not loader.has_task(
                _MAAEND_CLOSE_GAME_TASK
            ):
                return "当前 MaaEnd 版本不支持托管游戏启动，请更新 MaaEnd 后重试"
            if (
                account_switch_method == "MAAEND"
                and account_id
                and not loader.has_task(_MAAEND_ACCOUNT_SWITCH_TASK)
            ):
                return "当前 MaaEnd 版本不支持内置账号切换，请更新 MaaEnd 后重试"

        config_mode = maaend_config_mode(self.cur_user_config.get("Info", "Mode"))
        if config_mode == "直控":
            config_file = (
                Path.cwd() / f"data/{self.script_info.script_id}/Temp/mxu-MaaEnd.json"
            )
        else:
            config_file = (
                maaend_mas_config_dir(
                    self.script_info.script_id,
                    str(self.cur_user_uid),
                    config_mode,
                )
                / "mxu-MaaEnd.json"
            )
        self.maaend_config_file = config_file
        if not config_file.exists():
            self.cur_user_item.status = "异常"
            return "未找到 MaaEnd 配置文件, 请先完成「MaaEnd 配置」步骤"

        self._prepare_auto_collect_routes()
        daily_once_skip_reason = self._daily_once_skip_reason()
        if daily_once_skip_reason is not None:
            self.cur_user_item.status = "跳过"
            return daily_once_skip_reason

        return "Pass"

    def _prepare_auto_collect_routes(self) -> None:
        """按当前日期准备自动采集路线。"""

        self.auto_collect_routes = {}
        self.auto_collect_run_at = None
        if not self.cur_user_config.get(
            "Info", "IfQuickConfig"
        ) or not self.cur_user_config.get("Task", "IfAutoCollect"):
            return
        root_path = self._maaend_root_path()
        if root_path is None:
            raise ValueError("MaaEnd 路径未配置")
        groups = get_loaded_maaend_options(root_path)["autoCollectGroups"]
        if not groups:
            raise ValueError("MaaEnd 自动采集路线读取失败，请检查安装资源")
        auto_collect_mode = self.cur_user_config.get("Task", "AutoCollectMode")
        self.auto_collect_run_at = datetime.now(tz=UTC4)
        self.auto_collect_routes = _select_auto_collect_routes(
            auto_collect_mode,
            {
                key: self.cur_user_config.get("Task", key)
                for key in ("AutoCollectRoutes", "AutoCollectCommonRoutes")
            },
            groups,
            self.auto_collect_run_at,
        )

    def _daily_once_task_names(self) -> set[str]:
        return {
            task_name
            for task_name in _load_json_list(
                self.cur_user_config.get("Task", "DailyOnceTasks")
            )
            if task_name != MAAEND_AUTO_COLLECT_TASK
        }

    def _daily_task_records(self) -> dict[str, str]:
        raw_records = _load_json_dict(
            self.cur_user_config.get("Data", "PeriodTaskRecords")
        )
        daily_records = raw_records.get("daily", {})
        if not isinstance(daily_records, dict):
            return {}
        return {
            str(task_name): str(period_key)
            for task_name, period_key in daily_records.items()
            if str(task_name).strip() and str(period_key).strip()
        }

    def _daily_once_task_done(self, task_name: object) -> bool:
        """判断任务是否已在当天正常完成。"""

        name = str(task_name)
        selected_tasks = self._daily_once_task_names()
        if name not in selected_tasks and not (
            name in _MAAEND_SANITY_TASK_NAMES and "Sanity" in selected_tasks
        ):
            return False

        records = self._daily_task_records()
        if records.get(name) == self.curdate:
            return True
        return (
            name in _MAAEND_SANITY_TASK_NAMES and records.get("Sanity") == self.curdate
        )

    def _quick_task_daily_once_done(self, task_name: str) -> bool:
        """判断快速配置中的逻辑任务是否已在当天完成。"""

        if task_name != "Sanity":
            return self._daily_once_task_done(task_name)
        if self._daily_once_task_done(task_name):
            return True
        try:
            sanity_task_key, _ = self.cur_user_config.get_effective_sanity_task_key()
        except ValueError:
            return False
        target_task_name = (
            "AutoEssence"
            if sanity_task_key["SanityTaskType"] == "Essence"
            else "ProtocolSpace"
        )
        return self._daily_once_task_done(target_task_name)

    async def _mark_daily_once_tasks_completed(
        self, completed_task_names: set[str]
    ) -> None:
        """记录当天已正常完成的每日一次任务。"""

        selected_tasks = self._daily_once_task_names()
        if not selected_tasks or not completed_task_names:
            return

        records_data = _load_json_dict(
            self.cur_user_config.get("Data", "PeriodTaskRecords")
        )
        records = self._daily_task_records()
        changed = False
        for task_name in completed_task_names:
            keys = {str(task_name)}
            if str(task_name) in _MAAEND_SANITY_TASK_NAMES:
                keys.add("Sanity")
            for key in keys.intersection(selected_tasks):
                if records.get(key) != self.curdate:
                    records[key] = self.curdate
                    changed = True

        if changed:
            records_data["daily"] = records
            await self.cur_user_config.set(
                "Data",
                "PeriodTaskRecords",
                json.dumps(records_data, ensure_ascii=False),
            )

    def _daily_once_skip_reason(self) -> str | None:
        """判断当前用户是否所有阶段都因每日一次规则而无需启动。"""

        mode_results = [self._mode_skip_reason(mode) for mode in MAAEND_RUN_MOOD_BOOK]
        if any(reason is None or missing for reason, missing in mode_results):
            return None
        daily_once_done = (
            self._quick_task_daily_once_done
            if self.cur_user_config.get("Info", "IfQuickConfig")
            else self._daily_once_task_done
        )
        if not any(
            daily_once_done(task_name) for task_name in self._daily_once_task_names()
        ):
            return None
        return "每日仅执行一次的任务今日已完成，跳过该用户"

    async def prepare(self):

        self.maaend_process_manager = ProcessManager()
        if self.emulator_manager is None:
            self.game_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()
        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now()

        # ── 推送详情开关（在专项侧，不在 log_box）：关闭时不创建采集会话 ──
        # 该用户 push_log 保持为空，报告聚合自然只有结果行
        self.cur_user_item.push_log_mode = self.cur_user_config.get(
            "Notify", "PushLogMode"
        )
        self.push_log_enabled = (
            self.cur_user_config.get("Notify", "PushLogMode") != "关闭"
        )

        self.maaend_root_path = Path(self.script_config.get("Info", "Path"))
        self.maaend_exe_path = self.maaend_root_path / "MaaEnd.exe"
        self.maaend_set_path = self.maaend_root_path / "config"
        self.maaend_log_path = self.maaend_root_path / "debug/maa.log"

        self.maaend_log_monitor = LogMonitor(
            (1, 23), "%Y-%m-%d %H:%M:%S.%f", self.check_log
        )

        self._prepare_auto_collect_routes()

        mode_skip_reasons: dict[str, str] = {}
        missing_task_modes: list[str] = []
        for mode in MAAEND_RUN_MOOD_BOOK:
            reason, missing_task = self._mode_skip_reason(mode)
            if reason is None:
                continue
            mode_skip_reasons[mode] = reason
            if missing_task:
                missing_task_modes.append(mode)
        self.first_run_mode = next(
            (mode for mode in MAAEND_RUN_MOOD_BOOK if mode not in mode_skip_reasons),
            None,
        )
        self.run_book = {
            mode: mode in mode_skip_reasons for mode in MAAEND_RUN_MOOD_BOOK
        }
        for mode, reason in mode_skip_reasons.items():
            logger.info(
                f"用户 {self.cur_user_item.name} 跳过{MAAEND_RUN_MOOD_BOOK[mode]}阶段: {reason}"
            )
        for mode in missing_task_modes:
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="warning",
                    message=(
                        f"用户 {self.cur_user_item.name} 当前 MaaEnd 配置中不存在"
                        f"{MAAEND_RUN_MOOD_BOOK[mode]}阶段所需任务，已跳过该阶段，"
                        "请在 MaaEnd 中添加并启用对应任务"
                    ),
                ),
            )

    def _source_maaend_tasks(self) -> list[dict[str, object]] | None:
        """读取当前用户所选 MaaEnd 实例的任务列表（文件未变时复用上次解析结果）。"""

        if self.maaend_config_file is None:
            return None
        try:
            stat = self.maaend_config_file.stat()
            signature = (str(self.maaend_config_file), stat.st_mtime_ns, stat.st_size)
        except OSError:
            return None
        if (
            self._source_tasks_cache is not None
            and self._source_tasks_cache[0] == signature
        ):
            return self._source_tasks_cache[1]
        tasks = self._parse_source_maaend_tasks()
        self._source_tasks_cache = (signature, tasks)
        return tasks

    def _parse_source_maaend_tasks(self) -> list[dict[str, object]] | None:
        if self.maaend_config_file is None:
            return None
        try:
            source_config = read_file(self.maaend_config_file)
        except (OSError, TypeError, ValueError):
            return None
        if not isinstance(source_config, dict):
            return None

        instances = source_config.get("instances")
        if not isinstance(instances, list) or not instances:
            return None

        selected_instance = None
        for instance in instances:
            if not isinstance(instance, dict):
                continue
            if instance.get("id") == "automas" or instance.get("name") == "AUTO-MAS":
                selected_instance = instance
                break
            if instance.get("id") == source_config.get("lastActiveInstanceId"):
                selected_instance = instance
                break
        if selected_instance is None:
            selected_instance = instances[0]
        tasks = selected_instance.get("tasks")
        if not isinstance(tasks, list):
            return None
        result = [task for task in tasks if isinstance(task, dict)]
        self._drop_removed_medication_task(result)
        return result

    def _source_mode_skip_reason(self, mode: str) -> tuple[str | None, bool]:
        """非快速配置下按 MaaEnd 配置判断阶段是否可执行。"""

        tasks = self._source_maaend_tasks()
        if tasks is None:
            # 配置读取失败时交给 MaaEnd 执行并由日志判定，避免误跳过用户任务。
            return None, False

        def has_task(task_name: str, *, enabled_only: bool = False) -> bool:
            return any(
                str(task.get("taskName", "")) == task_name
                and (not enabled_only or bool(task.get("enabled", False)))
                for task in tasks
            )

        if mode == "Delivery":
            if not has_task(MAAEND_DELIVERY_TASK):
                return "MaaEnd 配置中不存在抢委托送货任务", True
            if not has_task(MAAEND_DELIVERY_TASK, enabled_only=True):
                return "抢委托送货任务未启用", False
            if self._daily_once_task_done(MAAEND_DELIVERY_TASK):
                return "抢委托送货任务今日已完成", False
            return None, False
        if mode == "AutoCollect":
            if not has_task(MAAEND_AUTO_COLLECT_TASK):
                return "MaaEnd 配置中不存在自动采集任务", True
            if not has_task(MAAEND_AUTO_COLLECT_TASK, enabled_only=True):
                return "自动采集任务未启用", False
            return None, False
        if not any(
            _task_enabled_for_mode(
                task.get("taskName"), task.get("enabled", False), mode
            )
            for task in tasks
            if not str(task.get("taskName", "")).startswith("__MXU_")
            and str(task.get("taskName", ""))
            not in {_MAAEND_ACCOUNT_SWITCH_TASK, _MAAEND_CLOSE_GAME_TASK}
            and not self._daily_once_task_done(task.get("taskName"))
        ):
            return "MaaEnd 配置中没有已启用的日常任务", False
        return None, False

    def _quick_config_mode_skip_reason(self, mode: str) -> tuple[str | None, bool]:
        """快速配置下按 MAS 任务开关与 MaaEnd 配置判断阶段是否可执行。"""

        if mode == "Delivery":
            if not self.cur_user_config.get("Task", "IfSeizeDeliveryJobs"):
                return "快速配置未开启抢委托送货", False
            task_name = MAAEND_DELIVERY_TASK
            task_label = "抢委托送货"
        elif mode == "AutoCollect":
            if not self.cur_user_config.get("Task", "IfAutoCollect"):
                return "快速配置未开启自动采集", False
            if not any(self.auto_collect_routes.values()):
                return "今日采集周期无待执行路线", False
            task_name = MAAEND_AUTO_COLLECT_TASK
            task_label = "自动采集"
        else:
            sanity_enabled = bool(
                self.cur_user_config.get("Task", "IfSanity")
            ) and not (self._quick_task_daily_once_done("Sanity"))
            if not (
                sanity_enabled
                or any(
                    bool(self.cur_user_config.get("Task", f"If{task_name}"))
                    and not self._quick_task_daily_once_done(task_name)
                    for task_name in MAAEND_TASKS
                )
            ):
                return "快速配置未开启任何日常任务", False

            tasks = self._source_maaend_tasks()
            if tasks is None:
                return None, False

            # MaaEnd 2.28 的 AutoEssence 任务可能尚未出现在旧配置实例中；
            # set_maaend 会在临时运行配置中补齐任务，不能在这里提前跳过理智阶段。
            if self.cur_user_config.get(
                "Task", "IfSanity"
            ) and not self._quick_task_daily_once_done("Sanity"):
                sanity_task_key, _ = (
                    self.cur_user_config.get_effective_sanity_task_key()
                )
                target_sanity_task_name = (
                    "AutoEssence"
                    if sanity_task_key["SanityTaskType"] == "Essence"
                    else "ProtocolSpace"
                )
                if not any(
                    str(task.get("taskName", "")) == target_sanity_task_name
                    for task in tasks
                ):
                    return None, False

            target_sanity_task_name: str | None = None
            for task in tasks:
                task_name = str(task.get("taskName", ""))
                if task_name.startswith("__MXU_") or task_name in {
                    _MAAEND_ACCOUNT_SWITCH_TASK,
                    _MAAEND_CLOSE_GAME_TASK,
                    MAAEND_DELIVERY_TASK,
                    MAAEND_AUTO_COLLECT_TASK,
                }:
                    continue
                if task_name in _MAAEND_SANITY_TASK_NAMES:
                    if not self.cur_user_config.get("Task", "IfSanity"):
                        continue
                    if target_sanity_task_name is None:
                        sanity_task_key, _ = (
                            self.cur_user_config.get_effective_sanity_task_key()
                        )
                        target_sanity_task_name = (
                            "AutoEssence"
                            if sanity_task_key["SanityTaskType"] == "Essence"
                            else "ProtocolSpace"
                        )
                    if task_name == target_sanity_task_name:
                        if not self._quick_task_daily_once_done("Sanity"):
                            return None, False
                    continue
                if task_name in MAAEND_TASKS:
                    if self.cur_user_config.get(
                        "Task", f"If{task_name}"
                    ) and not self._quick_task_daily_once_done(task_name):
                        return None, False
                    continue
                if bool(task.get("enabled", False)):
                    return None, False
            return "MaaEnd 配置中没有可执行的日常任务", False

        tasks = self._source_maaend_tasks()
        if tasks is None:
            return None, False
        if not any(str(task.get("taskName", "")) == task_name for task in tasks):
            return f"MaaEnd 配置中不存在{task_label}任务", True
        if mode == "Delivery" and self._daily_once_task_done(task_name):
            return f"{task_label}任务今日已完成", False
        return None, False

    def _mode_skip_reason(self, mode: str) -> tuple[str | None, bool]:
        """判断某阶段是否无可执行任务，空阶段直接视为完成。

        Args:
            mode (str): MaaEnd 运行阶段。

        Returns:
            tuple[str | None, bool]: 跳过原因（None 表示该阶段有任务可执行），
                以及是否因阶段任务在 MaaEnd 配置中不存在导致跳过。
        """

        if self.cur_user_config.get("Info", "IfQuickConfig"):
            return self._quick_config_mode_skip_reason(mode)
        return self._source_mode_skip_reason(mode)

    async def _wait_maaend_stage(self) -> None:
        """同时等待日志结果与进程退出，避免子进程持有 stdout 导致阶段卡住。"""
        process = self.maaend_process_manager.process
        if not isinstance(process, asyncio.subprocess.Process):
            self.cur_user_log.status = "MaaEnd 未启动可监控的进程"
            return

        async def wait_exit() -> None:
            # Process.wait() 也可能等待管道关闭；returncode 独立反映主进程退出。
            while process.returncode is None:
                await asyncio.sleep(0.2)

        await self.maaend_log_monitor.start_monitor_process(process, "stdout")
        monitor = self.maaend_log_monitor.task
        exit_task = asyncio.create_task(wait_exit())
        result_task = asyncio.create_task(self.wait_event.wait())
        try:
            done, _ = await asyncio.wait(
                {monitor, exit_task, result_task}, return_when=asyncio.FIRST_COMPLETED
            )
            if exit_task in done and not monitor.done():
                logger.info(f"MaaEnd 主进程已退出，退出码: {process.returncode}")
                # 消费已经写入管道的尾部日志，但不无限等待继承管道的子进程。
                try:
                    await asyncio.wait_for(asyncio.shield(monitor), timeout=2)
                except asyncio.TimeoutError:
                    pass
                except Exception as error:
                    logger.warning(f"MaaEnd 日志读取失败: {error}")
            if monitor.done() and not monitor.cancelled() and monitor.exception():
                logger.warning(f"MaaEnd 日志读取失败: {monitor.exception()}")
                self.cur_user_log.status = "MaaEnd 日志读取失败"
            elif exit_task in done or monitor.done():
                await self.maaend_log_monitor.stop()
                await self.check_log(
                    self.maaend_log_monitor.log_contents,
                    self.maaend_log_monitor.latest_time,
                    if_stream_end=True,
                )
        finally:
            exit_task.cancel()
            result_task.cancel()
            await asyncio.gather(exit_task, result_task, return_exceptions=True)
            await self.maaend_log_monitor.stop()

    async def main_task(self):
        """自动代理模式主逻辑"""

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

        logger.info(f"开始代理用户 {self.cur_user_uid}")
        self.cur_user_item.status = "运行"

        run_times_limit = self.script_config.get("Run", "RunTimesLimit")
        i = 0
        mode_order = list(MAAEND_RUN_MOOD_BOOK)
        mode_index = 0
        while mode_index < len(mode_order):
            self.mode = mode_order[mode_index]
            if self.run_book[self.mode]:
                mode_index += 1
                i = 0
                self.task_dict = None
                continue
            if i >= run_times_limit:
                logger.warning(
                    f"用户: {self.cur_user_uid} - {MAAEND_RUN_MOOD_BOOK[self.mode]}阶段重试次数已耗尽"
                )
                mode_index += 1
                i = 0
                self.task_dict = None
                continue
            i += 1
            self.retryable = True
            logger.info(
                f"用户 {self.cur_user_item.name} - {MAAEND_RUN_MOOD_BOOK[self.mode]}"
                f"阶段尝试次数: {i}/{run_times_limit}"
            )
            self.log_start_time = datetime.now()
            self.cur_user_log = LogRecord(phase=self.mode)
            self.cur_user_item.log_record[self.log_start_time] = self.cur_user_log

            # 执行任务前脚本
            if self.cur_user_config.get("Info", "IfScriptBeforeTask"):
                await execute_script_task(
                    Path(self.cur_user_config.get("Info", "ScriptBeforeTask")),
                    "脚本前任务",
                )

            self.script_info.log = "正在启动游戏..."
            account_switch_method = self._account_switch_method()
            use_mas_account_switch = account_switch_method == "MAS"
            # MAAEND 入口由 MXU 的 GameSetting pretask 启动游戏；MAS 兼容入口
            # 必须先让游戏进入可交互状态，再交给旧的游戏内登录流程。
            try:
                if self.emulator_manager is None:
                    if use_mas_account_switch:
                        if is_process_running("Endfield.exe"):
                            logger.info(
                                "检测到终末地客户端已运行，准备由 MAS 执行账号切换"
                            )
                        else:
                            await self.game_process_manager.kill()
                            logger.info(
                                f"启动终末地: {self.script_config.get('Game', 'Path')}"
                            )
                            await self.game_process_manager.open_process(
                                self.script_config.get("Game", "Path"),
                                *str(self.script_config.get("Game", "Arguments")).split(
                                    " "
                                ),
                            )
                            await asyncio.sleep(
                                self.script_config.get("Game", "WaitTime")
                            )
                    else:
                        # Win32 游戏由 MXU 在 GameSetting pretask 完成后作为前置程序启动。
                        if self.mode == self.first_run_mode and is_process_running(
                            "Endfield.exe"
                        ):
                            logger.info(
                                "关闭已运行的终末地，准备执行 MaaEnd 游戏设置预任务"
                            )
                            await self.kill_game_process()
                        logger.info("终末地将由 MaaEnd 前置程序启动")
                    emulator_info = None
                else:
                    logger.info(
                        f"启动模拟器: {self.script_config.get('Game', 'EmulatorIndex')}"
                    )
                    emulator_info = await self.emulator_manager.open(
                        self.script_config.get("Game", "EmulatorIndex"),
                        "com.hypergryph.endfield",
                    )
            except Exception as e:
                await self.handle_pre_maaend_error(
                    "游戏启动失败"
                    if self.emulator_manager is None
                    else "模拟器启动失败",
                    e,
                )
                continue

            account_id = str(self.cur_user_config.get("Info", "Id")).strip()
            if use_mas_account_switch and account_id:
                try:
                    from .tools.login import login

                    self.script_info.log = "正在由 MAS 自建流程切换账号..."
                    await login(account_id, emulator_info)
                except Exception as error:
                    await self.handle_pre_maaend_error("MAS 自建账号切换失败", error)
                    continue
                logger.info(f"用户 {self.cur_user_item.user_id} MAS 自建账号切换成功")
                self.script_info.log = "MAS 自建账号切换完成"
            elif account_id:
                logger.info(
                    f"用户 {self.cur_user_item.user_id} 将由 MAAEND 内置任务切换账号"
                )
                self.script_info.log = "将由 MAAEND 启动游戏并执行账号切换"
            else:
                logger.info(
                    f"用户 {self.cur_user_item.user_id} 未配置账号，跳过账号切换"
                )
                self.script_info.log = (
                    "将由 MAS 启动游戏，未配置账号，跳过账号切换"
                    if use_mas_account_switch
                    else "将由 MAAEND 启动游戏，未配置账号，跳过账号切换"
                )

            await self.set_maaend(emulator_info)

            if not any(any(tasks.values()) for tasks in self.task_dict.values()):
                self.retryable = False
                await self.handle_pre_maaend_error(
                    "MaaEnd 没有可执行任务，请检查任务配置"
                )
                break

            logger.info(f"运行脚本任务: {self.maaend_exe_path}")
            self.wait_event.clear()
            await self.maaend_process_manager.open_process(
                self.maaend_exe_path,
                "--autostart",
                "--instance",
                self.maaend_instance_name,
                "--quit-after-run",
                stdout=asyncio.subprocess.PIPE,
            )
            await asyncio.sleep(3)  # 等待 MaaEnd 启动完成
            # 静默模式隐藏 MaaEnd 窗口
            if Config.get("Function", "IfSilence"):
                if await self.maaend_process_manager.minimize_window():
                    logger.success("静默模式: 成功隐藏 MaaEnd 窗口")
                else:
                    logger.warning("静默模式: 隐藏 MaaEnd 窗口失败")
            await asyncio.sleep(1)
            await self._wait_maaend_stage()

            if self.cur_user_log.status == "Success!":
                self.run_book[self.mode] = True
                self.script_info.log = (
                    f"检测到 MaaEnd 完成{MAAEND_RUN_MOOD_BOOK[self.mode]}任务\n"
                    "正在等待相关程序结束"
                )

                # 中止相关程序
                await self.maaend_process_manager.kill()
                await System.kill_process(self.maaend_exe_path)
                mode_index += 1
                i = 0
                self.task_dict = None

            else:
                logger.warning(
                    f"用户: {self.cur_user_uid} - 代理任务异常: {self.cur_user_log.status}"
                )
                self.script_info.log = f"{self.cur_user_log.status}\n正在中止相关程序"

                # 中止相关程序
                await self.kill_managed_process()

                try:
                    await Notify.push_plyer(
                        "用户自动代理出现异常！",
                        f"用户 {self.cur_user_item.name} 的自动代理出现一次异常",
                        f"{self.cur_user_item.name}的自动代理出现异常",
                        3,
                    )
                except Exception:
                    pass

                if not self.retryable:
                    logger.info("检测到不可恢复的错误，跳过后续重试")
                    i = run_times_limit

        if self.cur_user_config.get("Info", "IfScriptAfterTask"):
            await execute_script_task(
                Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
                "脚本后任务",
            )

    async def handle_pre_maaend_error(
        self, error_message: str, e: Exception | None = None
    ):

        if e is None:
            logger.warning(f"用户: {self.cur_user_uid} - {error_message}")
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=error_message),
            )
        else:
            logger.opt(exception=True).warning(
                f"用户: {self.cur_user_uid} - {error_message}: {e}"
            )
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=f"{error_message}: {e}"),
            )
        self.cur_user_log.content = [f"{error_message}, 无日志记录"]
        self.cur_user_log.status = error_message

        await self.kill_managed_process()

        try:
            await Notify.push_plyer(
                "用户自动代理出现异常！",
                f"用户 {self.cur_user_item.name} 自动代理时{error_message}",
                f"{self.cur_user_item.name}的自动代理出现异常",
                3,
            )
        except Exception:
            pass

    async def kill_managed_process(self, kill_game: bool = True) -> None:
        """中止关联进程

        Args:
            kill_game (bool): 是否同时关闭游戏或模拟器；开发模式下手动中止
                任务时传 False，保留游戏便于继续调试。
        """

        try:
            logger.info(f"中止 MaaEnd 进程: {self.maaend_exe_path}")
            await self.maaend_process_manager.kill()
            await System.kill_process(self.maaend_exe_path)
        except Exception as e:
            logger.opt(exception=True).warning(f"中止 MaaEnd 进程失败: {e}")
        if not kill_game:
            logger.info("开发模式下手动中止任务，保留游戏进程")
            return
        await self.kill_game_process()

    async def kill_game_process(self) -> None:
        """关闭游戏或模拟器进程（Win32 为终末地客户端，Adb 为模拟器）"""

        try:
            if self.emulator_manager is None:
                logger.info("中止终末地进程")
                await self.game_process_manager.kill()
                await System.kill_process(self.script_config.get("Game", "Path"))
            else:
                logger.info("中止模拟器进程")
                await close_emulator(
                    self,
                    index=self.script_config.get("Game", "EmulatorIndex"),
                )
        except Exception as e:
            logger.opt(exception=True).warning(f"关闭游戏或模拟器失败: {e}")

    def _maaend_task_option_supported(self, task_name: str, option_name: str) -> bool:
        """读取当前安装的 MaaEnd 是否声明了指定配置项。"""

        root_path = self._maaend_root_path()
        if root_path is None:
            return False
        try:
            return maaend_task_option_supported(root_path, task_name, option_name)
        except (OSError, KeyError, TypeError, ValueError) as error:
            logger.debug(f"读取 MaaEnd 选项声明失败 {task_name}.{option_name}: {error}")
            return False

    def _maaend_task_supported(self, task_name: str) -> bool | None:
        """读取当前安装的 MaaEnd 是否声明了指定任务。

        资源不可读时返回 None（未知），调用方据此不做移除判断。
        """

        root_path = self._maaend_root_path()
        if root_path is None:
            return None
        try:
            return maaend_task_supported(root_path, task_name)
        except (OSError, KeyError, TypeError, ValueError) as error:
            logger.debug(f"读取 MaaEnd 任务声明失败 {task_name}: {error}")
            return None

    def _maaend_root_path(self) -> Path | None:
        """获取 MaaEnd 安装目录；未完成 prepare 时回退到脚本配置。"""

        root_path = getattr(self, "maaend_root_path", None)
        if root_path is not None:
            return root_path
        script_config = getattr(self, "script_config", None)
        if script_config is None:
            return None
        path = str(script_config.get("Info", "Path")).strip()
        return Path(path) if path else None

    def _drop_removed_medication_task(self, tasks: list[dict[str, object]]) -> None:
        """新版 MaaEnd 将应急理智加强剂并入理智任务，移除旧独立任务。"""

        if self._maaend_task_supported("AutoUseSpMedication") is not False:
            return
        kept_tasks = [
            task
            for task in tasks
            if str(task.get("taskName", "")) != "AutoUseSpMedication"
        ]
        if len(kept_tasks) == len(tasks):
            return
        tasks[:] = kept_tasks
        logger.info("MaaEnd 当前版本已移除应急理智加强剂独立任务，改用理智任务内置选项")

    def _ensure_sanity_task(
        self, tasks: list[dict[str, object]], task_name: str
    ) -> dict[str, object] | None:
        """为新版拆分资源补齐旧配置实例中缺失的理智任务。"""

        for task in tasks:
            if str(task.get("taskName", "")) == task_name:
                return task

        task = {
            # 运行失败重试时会从源配置重新复制任务列表；固定 ID 才能让首轮
            # 生成的 task_dict 继续匹配这条补齐任务并保持其启用状态。
            "id": f"automas-{task_name.lower()}",
            "taskName": task_name,
            "enabled": False,
            # 与 MaaEnd 自己保存的任务条目保持同样的字段形状
            "enabledByController": {
                str(self.script_config.get("Game", "ControllerType")): True
            },
            "expanded": False,
            "optionValues": {},
        }
        tasks.append(task)
        logger.info(f"MaaEnd 配置实例缺少 {task_name}，已在运行副本中补齐任务")
        return task

    def _write_auto_essence_options(
        self,
        task: dict[str, object],
        sanity_task_key: dict[str, object],
    ) -> None:
        """按 MaaEnd 旧版/2.28+ 字段写入基质刷取任务。"""

        option_values = task.setdefault("optionValues", {})
        if not isinstance(option_values, dict):
            option_values = {}
            task["optionValues"] = option_values

        location = sanity_task_key.get("AutoEssenceSpecifiedLocation")
        location = location if isinstance(location, str) else ""
        target_weapons = _load_json_list(
            sanity_task_key.get("AutoEssenceTargetWeapons")
        )
        menu = sanity_task_key.get("AutoEssenceMenu")
        if menu not in {"Random", "Location", "Target"}:
            menu = "Target" if target_weapons else "Location"
        root_path = self._maaend_root_path()

        has_menu = self._maaend_task_option_supported("AutoEssence", "AutoEssenceMenu")
        if has_menu:
            option_values["AutoEssenceMenu"] = {
                "type": "select",
                "caseName": menu,
            }
            option_values.pop("AutoEssenceChooseLocation", None)
            option_values.pop("AutoEssenceSelectLocation", None)
        else:
            # 旧版只有 ChooseLocation checkbox；Target/Location 均退化为指定地点。
            option_values.pop("AutoEssenceMenu", None)

        def clear_target_options() -> None:
            """清除上一轮写入的目标武器选项，组名由 MaaEnd 资源决定。"""

            for key in [
                name
                for name in option_values
                if name.startswith(("AutoEssenceWeapons", "AutoEssenceWeaponType"))
            ]:
                option_values.pop(key, None)

        if menu != "Target" or not has_menu:
            clear_target_options()
            option_values.pop("AutoEssenceObtainModeClaimOnlyForcedFilter", None)

        if menu == "Target" and has_menu:
            # 未限制目标时保留 MaaEnd 资源声明的默认值（各武器类型全选），
            # 清除上一次目标模式留下的覆盖项即可表达“不限武器”。
            clear_target_options()
            try:
                target_groups = (
                    get_loaded_maaend_options(root_path).get(
                        "essenceTargetWeaponGroups", []
                    )
                    if root_path is not None
                    else []
                )
            except (OSError, KeyError, TypeError, ValueError) as error:
                logger.debug(f"读取 MaaEnd 目标武器分组失败: {error}")
                target_groups = []

            selected = set(target_weapons)
            matched_targets: set[str] = set()
            for group in target_groups:
                if not isinstance(group, dict):
                    continue
                group_value = group.get("value")
                options = group.get("options")
                if not isinstance(group_value, str) or not isinstance(options, list):
                    continue
                option_name = f"AutoEssenceWeapons{group_value}"
                switch_name = f"AutoEssenceWeaponType{group_value}"
                group_values = {
                    str(option.get("value"))
                    for option in options
                    if isinstance(option, dict) and option.get("value") is not None
                }
                selected_group_values = [
                    str(option.get("value"))
                    for option in options
                    if isinstance(option, dict) and option.get("value") in selected
                ]
                if not selected:
                    continue
                if selected_group_values:
                    matched_targets.update(selected_group_values)
                if self._maaend_task_option_supported("AutoEssence", option_name):
                    option_values[option_name] = {
                        "type": "checkbox",
                        "caseNames": selected_group_values,
                    }
                if self._maaend_task_option_supported("AutoEssence", switch_name):
                    option_values[switch_name] = {
                        "type": "switch",
                        "value": bool(selected.intersection(group_values)),
                    }

            unknown_targets = selected - matched_targets
            if unknown_targets:
                logger.warning(
                    "MaaEnd 目标武器配置包含当前资源不存在的选项，已忽略: "
                    + ", ".join(sorted(unknown_targets))
                )

            if self._maaend_task_option_supported(
                "AutoEssence", "AutoEssenceObtainModeClaimOnlyForcedFilter"
            ):
                option_values["AutoEssenceObtainModeClaimOnlyForcedFilter"] = {
                    "type": "select",
                    "caseName": "ObtainScaling2",
                }
        elif has_menu and menu == "Location":
            if location and self._maaend_task_option_supported(
                "AutoEssence", "AutoEssenceSelectLocation"
            ):
                option_values["AutoEssenceSelectLocation"] = {
                    "type": "select",
                    "caseName": location,
                }
        elif self._maaend_task_option_supported(
            "AutoEssence", "AutoEssenceChooseLocation"
        ):
            if location:
                option_values["AutoEssenceChooseLocation"] = {
                    "type": "checkbox",
                    "caseNames": [location],
                }
            else:
                # 空地点表示沿用 MaaEnd 默认地点集合，不写入空 checkbox。
                option_values.pop("AutoEssenceChooseLocation", None)

        if self._maaend_task_option_supported("AutoEssence", "AutoUseSpMedication"):
            option_values["AutoUseSpMedication"] = {
                "type": "select",
                "caseName": (
                    "UseMedication"
                    if self.cur_user_config.get("Task", "IfAutoUseSpMedication")
                    else "EndTask"
                ),
            }

        # 旧版曾把该字段写入任务选项；清掉后避免新版把它当成未知选项。
        option_values.pop("AutoEssenceSpecifiedLocation", None)

    def _configure_resolution_restore(
        self, tasks: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """仅在最后一个实际阶段，通过 MaaEnd 关闭游戏任务恢复分辨率。"""
        resolution = self.script_config.get("Game", "RestoreResolution")
        if (
            not resolution
            or resolution == "Off"
            or not self.script_config.get("Game", "CloseOnFinish")
            or self.emulator_manager is not None
        ):
            return None
        stages = list(MAAEND_RUN_MOOD_BOOK)
        is_last_stage = all(
            self.run_book[stage] for stage in stages[stages.index(self.mode) + 1 :]
        )
        close_tasks = [task for task in tasks if task.get("taskName") == "CloseGamePC"]
        if not is_last_stage:
            # 保留阶段切换要求的关闭游戏，但不要提前恢复游戏设置。
            for task in close_tasks:
                task.setdefault("optionValues", {})["CloseGamePCApplyGameSetting"] = {
                    "type": "switch",
                    "value": False,
                }
            return None
        required_options = (
            "CloseGamePCApplyGameSetting",
            "CloseGamePCGameSettingResolution",
        )
        if resolution == "Fullscreen":
            required_options += ("CloseGamePCGameSettingDisplayType",)
        if self._maaend_task_supported("CloseGamePC") is not True or not all(
            self._maaend_task_option_supported("CloseGamePC", name)
            for name in required_options
        ):
            raise ValueError(
                "当前 MaaEnd 不支持关闭游戏时恢复分辨率，请更新 MaaEnd 或关闭此设置"
            )
        close_task = (
            close_tasks[0]
            if close_tasks
            else {
                "id": "automas-restore-resolution",
                "taskName": "CloseGamePC",
                "enabledByController": {
                    str(self.script_config.get("Game", "ControllerType")): True
                },
                "optionValues": {},
            }
        )
        tasks[:] = [task for task in tasks if task.get("taskName") != "CloseGamePC"]
        close_task["enabled"] = True
        close_task.setdefault("enabledByController", {})[
            str(self.script_config.get("Game", "ControllerType"))
        ] = True
        tasks.append(close_task)
        if resolution == "Custom":
            width = str(self.script_config.get("Game", "RestoreResolutionWidth"))
            height = str(self.script_config.get("Game", "RestoreResolutionHeight"))
        elif resolution == "Fullscreen":
            width, height = "1920", "1080"
        else:
            width, height = resolution.split("x")
        values = close_task.setdefault("optionValues", {})
        values["CloseGamePCApplyGameSetting"] = {"type": "switch", "value": True}
        if resolution == "Fullscreen":
            values["CloseGamePCGameSettingDisplayType"] = {
                "type": "select",
                "caseName": "Fullscreen",
            }
        else:
            # 固定或自定义分辨率沿用 MaaEnd 默认的窗口模式，避免残留旧的全屏选项。
            values.pop("CloseGamePCGameSettingDisplayType", None)
        values["CloseGamePCGameSettingResolution"] = {
            "type": "input",
            "values": {
                "CloseGamePCGameSettingResolutionWidth": width,
                "CloseGamePCGameSettingResolutionHeight": height,
            },
        }
        return close_task

    async def set_maaend(self, device_info: DeviceInfo | None) -> None:
        """写入 MaaEnd 运行前配置"""

        logger.info("开始配置 MaaEnd 运行参数: 自动代理")

        # 配置前关闭可能未正常退出的脚本进程
        await self.maaend_process_manager.kill()
        await System.kill_process(self.maaend_exe_path)

        maaend_local_config = None
        if (self.maaend_set_path / "mxu-MaaEnd.json").exists():
            maaend_local_config = read_file(self.maaend_set_path / "mxu-MaaEnd.json")

        config_mode = maaend_config_mode(self.cur_user_config.get("Info", "Mode"))
        maaend_config_path = (
            Path.cwd() / f"data/{self.script_info.script_id}/Temp"
            if config_mode == "直控"
            else maaend_mas_config_dir(
                self.script_info.script_id,
                str(self.cur_user_uid),
                config_mode,
            )
        )
        maaend_config_file = maaend_config_path / "mxu-MaaEnd.json"
        if not maaend_config_file.exists():
            raise FileNotFoundError(
                "未找到 MaaEnd 配置文件, 请先完成「MaaEnd 配置」步骤"
            )

        # 下发前归档 MAS 配置到用户池（下发源；带快速配置覆盖层字段侧车，
        # 指纹去重，失败不阻断运行）。直控无 MAS 配置目录，不归档；native
        # 池由 manager.prepare 在任务级一次性归档
        if config_mode != "直控":
            archive_mas_runtime_backup(
                self.script_info.script_id,
                str(self.cur_user_uid),
                maaend_config_path,
                overlay=read_overlay_values(self.cur_user_config),
                # 备份标注来源：tri_state 池跨来源恢复靠它切回
                mode=config_mode,
            )

        swap_in_dir(maaend_config_path, self.maaend_set_path)
        mark_native_config_injected(
            Path.cwd() / f"data/{self.script_info.script_id}/Temp",
            self.maaend_set_path,
            script_id=self.script_info.script_id,
        )
        maaend_set = read_file(self.maaend_set_path / "mxu-MaaEnd.json")
        for field in ("version", "interfaceTaskSnapshot"):
            maaend_set.pop(field, None)
            if maaend_local_config is not None and field in maaend_local_config:
                maaend_set[field] = maaend_local_config[field]

        settings = maaend_set.get("settings")
        if isinstance(settings, dict):
            settings.pop("welcomeShownHash", None)

        if maaend_local_config is not None:
            local_settings = maaend_local_config.get("settings")
            if (
                isinstance(local_settings, dict)
                and "welcomeShownHash" in local_settings
            ):
                maaend_set.setdefault("settings", {})["welcomeShownHash"] = (
                    local_settings["welcomeShownHash"]
                )

        instances = maaend_set.get("instances")
        if not isinstance(instances, list) or len(instances) == 0:
            raise ValueError(
                "MaaEnd 配置文件中未找到可运行实例，请先完成「MaaEnd 配置」步骤"
            )

        maaend_instance = None
        for instance in instances:
            if instance.get("id") == "automas" or instance.get("name") == "AUTO-MAS":
                maaend_instance = instance
                break
            if instance.get("id") == maaend_set.get("lastActiveInstanceId"):
                maaend_instance = instance
                break
        if maaend_instance is None:
            maaend_instance = instances[0]
        self.maaend_instance_name = (
            maaend_instance.get("name")
            or maaend_instance.get("customName")
            or "AUTO-MAS"
        )
        if device_info is not None:
            from app.core import MaaFWManager

            maaend_instance["savedDevice"] = {
                "adbDeviceName": (await MaaFWManager.convert_adb(device_info)).name
            }
        maaend_tasks = maaend_instance.get("tasks")
        if not isinstance(maaend_tasks, list):
            raise ValueError("MaaEnd 配置实例中未找到任务列表")
        self._drop_removed_medication_task(maaend_tasks)

        account_id = str(self.cur_user_config.get("Info", "Id")).strip()
        replace_account_switch_task(
            tasks=maaend_tasks,
            account_id=(
                account_id if self._account_switch_method() == "MAAEND" else ""
            ),
            controller_type=str(self.script_config.get("Game", "ControllerType")),
            task_id=f"mas{self.cur_user_uid.hex[:4]}",
        )

        if self.emulator_manager is None:
            controller_type = str(self.script_config.get("Game", "ControllerType"))
            remaining_modes = list(MAAEND_RUN_MOOD_BOOK)[
                list(MAAEND_RUN_MOOD_BOOK).index(self.mode) + 1 :
            ]
            has_later_mode = any(not self.run_book[mode] for mode in remaining_modes)
            close_after_mode = (
                has_later_mode
                and self.script_config.get("Run", "TaskTransitionMethod") == "ExitGame"
                or not has_later_mode
                and self.script_config.get("Game", "CloseOnFinish")
            )
            _place_managed_task(
                maaend_tasks,
                task_name=_MAAEND_GAME_SETTING_PRETASK,
                task_id="automas-gamesetting",
                controller_type=controller_type,
                enabled=(
                    self.mode == self.first_run_mode
                    and bool(self.script_config.get("Game", "SetResolution"))
                ),
                first=True,
            )
            _place_managed_task(
                maaend_tasks,
                task_name=_MAAEND_CLOSE_GAME_TASK,
                task_id="automas-close-game",
                controller_type=controller_type,
                enabled=close_after_mode,
                first=False,
            )
            _configure_game_pre_action(
                maaend_instance,
                game_path=str(self.script_config.get("Game", "Path")),
                game_arguments=str(self.script_config.get("Game", "Arguments")),
            )

        # 加载 i18n 配置
        settings = maaend_set["settings"]
        if settings["language"] == "system":
            settings["language"] = "zh-CN"
        maaend_i18n = await asyncio.to_thread(
            load_maaend_task_i18n,
            self.maaend_root_path,
            str(settings["language"]),
        )
        maaend_interface_i18n = await asyncio.to_thread(
            load_maaend_interface_i18n,
            self.maaend_root_path,
            str(settings["language"]),
        )
        self.account_switch_task_name = maaend_i18n["AccountSwitch"]
        self.color_match_failed_message = maaend_interface_i18n[
            "task.SceneManager.focus.color_match_failed_prefix"
        ]

        removed_task_names = _disable_removed_tasks(maaend_tasks, maaend_i18n)

        if_quick_config = self.cur_user_config.get("Info", "IfQuickConfig")

        def get_task_book_name(task: dict[str, object]) -> str:
            if not if_quick_config:
                return str(
                    task.get("customName")
                    or maaend_i18n.get(str(task["taskName"]), str(task["taskName"]))
                )
            return maaend_i18n.get(str(task["taskName"]), str(task["taskName"]))

        sanity_task_key = {}
        sanity_task_type = ""
        target_task_name = ""
        if if_quick_config:
            sanity_task_key, _ = self.cur_user_config.get_effective_sanity_task_key()
            sanity_task_type = sanity_task_key["SanityTaskType"]
            target_task_name = (
                "AutoEssence" if sanity_task_type == "Essence" else "ProtocolSpace"
            )
            if self.cur_user_config.get("Task", "IfSanity"):
                self._ensure_sanity_task(maaend_tasks, target_task_name)

        restore_task = self._configure_resolution_restore(maaend_tasks)

        if self.task_dict is None:
            # 首次运行时按 MAS 配置生成本轮任务表，后续重试只收束这张表
            self.task_dict = {}
            self.task_name_map = {}
            sanity_configured = False
            sanity_switch_enabled = if_quick_config and self.cur_user_config.get(
                "Task", "IfSanity"
            )
            target_sanity_task_exists = any(
                task.get("taskName") == target_task_name for task in maaend_tasks
            )
            sanity_missing = sanity_switch_enabled and not target_sanity_task_exists
            sanity_managed = if_quick_config and (
                not sanity_switch_enabled or target_sanity_task_exists
            )

            for task in maaend_tasks:
                task_name_value = str(task.get("taskName"))
                if task_name_value.startswith("__MXU_") or task_name_value == (
                    _MAAEND_CLOSE_GAME_TASK
                ):
                    continue

                if task_name_value in removed_task_names:
                    continue

                task_enabled = bool(task.get("enabled", False))
                if if_quick_config:
                    if task_name_value in ("ProtocolSpace", "AutoEssence"):
                        if sanity_managed:
                            task_enabled = (
                                sanity_switch_enabled
                                and task_name_value == target_task_name
                                and not sanity_configured
                            )
                            if task_enabled:
                                sanity_configured = True
                    elif task_name_value == MAAEND_DELIVERY_TASK:
                        task_enabled = self.cur_user_config.get(
                            "Task", f"If{MAAEND_DELIVERY_TASK}"
                        )
                    elif task_name_value == MAAEND_AUTO_COLLECT_TASK:
                        task_enabled = bool(
                            self.cur_user_config.get("Task", "IfAutoCollect")
                            and any(self.auto_collect_routes.values())
                        )
                    elif task_name_value in MAAEND_TASKS:
                        task_enabled = self.cur_user_config.get(
                            "Task", f"If{task_name_value}"
                        )

                task_enabled = _task_enabled_for_mode(
                    task_name_value, task_enabled, self.mode
                )
                if (
                    task_name_value == _MAAEND_ACCOUNT_SWITCH_TASK
                    and self.mode != self.first_run_mode
                ):
                    task_enabled = False

                if self._daily_once_task_done(task_name_value):
                    task_enabled = False

                task_name = get_task_book_name(task)
                self.task_name_map[task_name] = task_name_value
                if task_name not in self.task_dict:
                    self.task_dict[task_name] = {}
                self.task_dict[task_name][task["id"]] = task_enabled

            if sanity_missing:
                warning_message = (
                    f"用户 {self.cur_user_item.name} 当前 MaaEnd 配置中缺少 {target_task_name} 任务，"
                    "已跳过理智任务快速配置"
                )
                logger.warning(warning_message)
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(level="warning", message=warning_message),
                )

            if removed_task_names:
                warning_message = (
                    f"用户 {self.cur_user_item.name} 的 MaaEnd 配置中存在"
                    f"当前版本已移除的任务：{'、'.join(sorted(removed_task_names))}，"
                    "已自动跳过，请重做「MaaEnd 配置」以同步最新任务列表"
                )
                logger.warning(warning_message)
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(level="warning", message=warning_message),
                )

        # 按本轮任务表写回 MaaEnd 运行配置
        for task in maaend_tasks:
            task_name_value = str(task.get("taskName"))
            if task_name_value.startswith("__MXU_"):
                continue

            task_name = get_task_book_name(task)
            if str(task.get("taskName")) in removed_task_names:
                task["enabled"] = False
                if task_name in self.task_dict:
                    self.task_dict[task_name].pop(task["id"], None)
                continue

            if task_name_value != _MAAEND_CLOSE_GAME_TASK:
                task["enabled"] = self.task_dict.get(task_name, {}).get(task["id"], False)

            if restore_task is task:
                # 独立送货/采集阶段也须在末尾执行恢复；重试时同样不能漏掉。
                task["enabled"] = True
                self.task_dict.setdefault(task_name, {})[task["id"]] = True
                self.task_name_map[task_name] = task_name_value

            if not task.get("enabled", False):
                continue

            if if_quick_config and task_name_value == MAAEND_DELIVERY_TASK:
                task.setdefault("optionValues", {})
                task["optionValues"]["SeizeDeliveryJobsReward"] = {
                    "type": "input",
                    "values": {
                        "Reward": str(
                            self.cur_user_config.get("Task", "SeizeDeliveryJobsReward")
                        )
                    },
                }
                task["optionValues"]["SeizeDeliveryJobsCommissionSource"] = {
                    "type": "select",
                    "caseName": self.cur_user_config.get(
                        "Task", "SeizeDeliveryJobsCommissionSource"
                    ),
                }
            elif if_quick_config and task_name_value == MAAEND_AUTO_COLLECT_TASK:
                MaaEndResourceLoader.get_loaded(
                    self.maaend_root_path
                ).write_auto_collect_options(task, self.auto_collect_routes)
            elif (
                if_quick_config
                and task_name_value == target_task_name
                and target_task_name == "ProtocolSpace"
            ):
                task.setdefault("optionValues", {})
                # 指定关卡属于 ByCount 分支，避免原生库存目标模式屏蔽计划表关卡。
                if self._maaend_task_option_supported(
                    "ProtocolSpace", "ProtocolSpaceMode"
                ):
                    task["optionValues"]["ProtocolSpaceMode"] = {
                        "type": "select",
                        "caseName": "ByCount",
                    }
                # MaaEnd 2.28 重命名了领取方式字段；新资源存在时切换到新字段，
                # 旧资源则保留源配置中的旧字段。
                supports_obtain_mode = self._maaend_task_option_supported(
                    "ProtocolSpace", "ProtocolSpaceObtainMode"
                )
                supports_obtain_mode_claim = self._maaend_task_option_supported(
                    "ProtocolSpace", "ProtocolSpaceObtainModeClaim"
                )
                if supports_obtain_mode:
                    task["optionValues"].pop("ProtocolSpaceSuccessAction", None)
                if supports_obtain_mode_claim:
                    task["optionValues"].pop("ProtocolSpaceUsePermit", None)
                if supports_obtain_mode:
                    task["optionValues"]["ProtocolSpaceObtainMode"] = {
                        "type": "select",
                        "caseName": "ObtainScaling2",
                    }
                if supports_obtain_mode_claim:
                    task["optionValues"]["ProtocolSpaceObtainModeClaim"] = {
                        "type": "select",
                        "caseName": "ObtainScaling2",
                    }
                task["optionValues"]["ProtocolSpaceTab"] = {
                    "type": "select",
                    "caseName": sanity_task_type,
                }
                for option in (
                    "OperatorProgression",
                    "WeaponProgression",
                    "CrisisDrills",
                ):
                    task["optionValues"][option] = {
                        "type": "select",
                        "caseName": sanity_task_key[option],
                    }
                if self._maaend_task_option_supported(
                    "ProtocolSpace", "ProtocolSpaceUseSpMedication"
                ):
                    task["optionValues"]["ProtocolSpaceUseSpMedication"] = {
                        "type": "select",
                        "caseName": (
                            "UseMedication"
                            if self.cur_user_config.get("Task", "IfAutoUseSpMedication")
                            else "EndTask"
                        ),
                    }
                reward_option = sanity_task_key.get("RewardsSetOption")
                if reward_option == "RewardsSetA":
                    if sanity_task_type == "OperatorProgression":
                        if sanity_task_key["OperatorProgression"] == "OperatorEXP":
                            task["optionValues"]["OperatorEXPRewardsSetOption"] = {
                                "type": "select",
                                "caseName": "CognitiveCarriers",
                            }
                        elif sanity_task_key["OperatorProgression"] == "Promotions":
                            task["optionValues"]["PromotionsRewardsSetOption"] = {
                                "type": "select",
                                "caseName": "Protoset",
                            }
                        elif sanity_task_key["OperatorProgression"] == "SkillUp":
                            task["optionValues"]["SkillUpRewardsSetOption"] = {
                                "type": "select",
                                "caseName": "Protohedron",
                            }
                    elif (
                        sanity_task_type == "WeaponProgression"
                        and sanity_task_key["WeaponProgression"] == "WeaponTune"
                    ):
                        task["optionValues"]["WeaponTuneRewardsSetOption"] = {
                            "type": "select",
                            "caseName": "HeavyCastDie",
                        }
                elif reward_option == "RewardsSetB":
                    if sanity_task_type == "OperatorProgression":
                        if sanity_task_key["OperatorProgression"] == "OperatorEXP":
                            task["optionValues"]["OperatorEXPRewardsSetOption"] = {
                                "type": "select",
                                "caseName": "AdvancedCombatRecord",
                            }
                        elif sanity_task_key["OperatorProgression"] == "Promotions":
                            task["optionValues"]["PromotionsRewardsSetOption"] = {
                                "type": "select",
                                "caseName": "Protodisk",
                            }
                        elif sanity_task_key["OperatorProgression"] == "SkillUp":
                            task["optionValues"]["SkillUpRewardsSetOption"] = {
                                "type": "select",
                                "caseName": "Protoprism",
                            }
                    elif (
                        sanity_task_type == "WeaponProgression"
                        and sanity_task_key["WeaponProgression"] == "WeaponTune"
                    ):
                        task["optionValues"]["WeaponTuneRewardsSetOption"] = {
                            "type": "select",
                            "caseName": "CastDie",
                        }
            elif (
                if_quick_config
                and task_name_value == target_task_name
                and target_task_name == "AutoEssence"
            ):
                self._write_auto_essence_options(task, sanity_task_key)

        # 只跟踪本轮实际启用的任务，避免禁用条目占用同名任务的结果位置。
        enabled_ids = {
            task["id"] for task in maaend_tasks if task.get("enabled", False)
        }
        self.task_dict = {
            name: {task_id: True for task_id in tasks if task_id in enabled_ids}
            for name, tasks in self.task_dict.items()
            if any(task_id in enabled_ids for task_id in tasks)
        }

        write_file(self.maaend_set_path / "mxu-MaaEnd.json", maaend_set)
        logger.success("MaaEnd 运行参数配置完成: 自动代理")

    async def check_log(
        self,
        log_content: list[str],
        latest_time: datetime,
        if_stream_end: bool = False,
    ) -> None:
        """日志回调"""

        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log
        if "资源加载失败" in log:
            # 资源文件损坏/缺失，重启脚本也不会好：不再重试
            self.cur_user_log.status = "MaaEnd 资源加载失败"
            self.retryable = False
        elif any(
            message in log
            for message in ("没有可以启动的任务", "没有启用的任务", "没有可执行任务")
        ):
            self.cur_user_log.status = "MaaEnd 没有可执行任务，请检查任务配置"
            self.retryable = False
        elif "快捷键开始任务：失败" in log or "任务启动失败" in log:
            self.cur_user_log.status = "MaaEnd 任务启动失败"
        elif "resolution check failed" in log:
            self.cur_user_log.status = "游戏分辨率设置错误，请重设分辨率比例为16:9"
            self.retryable = False
        elif self.color_match_failed_message and self.color_match_failed_message in log:
            self.cur_user_log.status = "MaaEnd 颜色识别失败，请关闭滤镜或 HDR"
            self.retryable = False
        elif f"任务失败: {self.account_switch_task_name}" in log:
            self.cur_user_log.status = "MaaEnd 账号切换失败"
        elif if_stream_end:
            if self.task_dict is None:
                self.cur_user_log.status = "MaaEnd 未加载任何任务"
            else:
                try:
                    task_name = ""
                    completed_task_names: set[str] = set()
                    task_index = {
                        k: {"index": 0, "list": list(v.keys())}
                        for k, v in self.task_dict.items()
                    }
                    for log_line in self.cur_user_log.content:
                        match = re.search(r"任务开始:\s*(.+)", log_line)
                        task_name = match.group(1) if match else task_name
                        if (
                            task_name in self.task_dict
                            and f"任务完成: {task_name}" in log_line
                        ):
                            self.task_dict[task_name][
                                task_index[task_name]["list"][
                                    task_index[task_name]["index"]
                                ]
                            ] = False
                            completed_task_names.add(
                                self.task_name_map.get(task_name, task_name)
                            )
                            task_index[task_name]["index"] += 1
                        elif (
                            task_name in task_index
                            and f"任务失败: {task_name}" in log_line
                        ):
                            task_index[task_name]["index"] += 1

                    await self._mark_daily_once_tasks_completed(completed_task_names)

                    unfinished_tasks = {}
                    for task_name, task_status in self.task_dict.items():
                        task_ids = [
                            task_id
                            for task_id, enabled in task_status.items()
                            if enabled
                        ]
                        if task_ids:
                            unfinished_tasks[task_name] = task_ids

                    if unfinished_tasks:
                        logger.info(f"MaaEnd 未完成任务列表: {unfinished_tasks}")
                        self.cur_user_log.status = (
                            f"MaaEnd 部分任务执行失败: {'、'.join(unfinished_tasks)}"
                        )
                    else:
                        self.cur_user_log.status = "Success!"
                except Exception as e:
                    logger.opt(exception=True).warning(
                        f"MaaEnd 任务执行情况解析失败: {e}"
                    )
                    self.cur_user_log.status = "MaaEnd 任务执行情况解析失败"

        elif self.is_log_stalled(
            latest_time, minutes=self.script_config.get("Run", "RunTimeLimit")
        ):
            self.cur_user_log.status = "MaaEnd 进程超时"
        else:
            self.cur_user_log.status = "MaaEnd 正常运行中"

        logger.debug(f"MaaEnd 日志分析结果: {self.cur_user_log.status}")
        if self.cur_user_log.status != "MaaEnd 正常运行中":
            logger.info(f"MaaEnd 任务结果: {self.cur_user_log.status}, 日志锁已释放")
            self.wait_event.set()

    async def final_task(self):

        if self.check_result != "Pass":
            return

        await self.maaend_log_monitor.stop()
        if (
            self.script_info.current_index == len(self.script_info.user_list) - 1
            and all(self.run_book.values())
            and not self.script_config.get("Game", "CloseOnFinish")
        ):
            try:
                logger.info(f"中止 MaaEnd 进程: {self.maaend_exe_path}")
                await self.maaend_process_manager.kill()
                await System.kill_process(self.maaend_exe_path)
            except Exception as e:
                logger.opt(exception=True).warning(f"中止 MaaEnd 进程失败: {e}")
        else:
            # 开发模式下手动中止任务时保留游戏进程，便于继续调试
            keep_game = is_backend_dev_mode() and self.stopped_manually
            await self.kill_managed_process(kill_game=not keep_game)

        user_logs_list = []
        stage_log_paths = []
        for t, log_item in self.cur_user_item.log_record.items():
            dt = t.astimezone(UTC4)
            log_path = Config.build_history_log_path(
                script_name=self.script_info.name,
                user_name=self.cur_user_item.name,
                log_time=dt,
            )

            if log_item.status == "MaaEnd 正常运行中":
                log_item.status = "任务被用户手动中止"

            if len(log_item.content) == 0:
                log_item.content = ["未捕获到任何日志内容"]
                log_item.status = "未捕获到日志"

            await Config.save_maaend_log(
                log_path,
                log_item.content,
                log_item.status,
                phase_label=MAAEND_RUN_MOOD_BOOK.get(log_item.phase, ""),
            )
            user_logs_list.append(log_path.with_suffix(".json"))
            stage_log_paths.append(log_path.with_suffix(".log"))

        # ── log_box：节点采集推送（源 = 本次各阶段历史日志全文）──
        # MaaEnd 的任务级进度行只在 stdout，不落上游文件；历史日志即 stdout
        # 全文落盘产物，直接作为采集源（start_from_end=False 全文采集）。
        # 开关关闭时不创建采集会话；on_crash 后 final_task 仍会收尾落盘并
        # 采集，部分日志中的开始标记聚为失败节点；仅 check 未通过的提前返回
        # 场景无节点。
        if self.push_log_enabled and stage_log_paths:
            try:
                log_collect = log_box.get_collect(
                    paths=stage_log_paths,
                    sink=lambda log_type, text, ts: append_push_log(
                        self.cur_user_item, log_type, text, ts
                    ),
                    start_from_end=False,
                )
                for rule in MAAEND_PUSH_RULES:
                    log_collect.collect(*rule)
                log_collect.close(maaend_resolve)
            except Exception as e:
                logger.opt(exception=True).warning(f"MaaEnd 节点采集推送失败: {e}")

        statistics = await Config.merge_statistic_info(user_logs_list)
        statistics["user_info"] = self.cur_user_item.name
        statistics["start_time"] = self.user_start_time.strftime("%Y-%m-%d %H:%M:%S")
        statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        statistics["user_result"] = (
            "代理任务全部完成"
            if all(self.run_book.values())
            else self.cur_user_item.result
        )

        success_symbol = "√" if all(self.run_book.values()) else "X"

        if user_logs_list:
            try:
                await push_notification(
                    "统计信息",
                    f"{datetime.now().strftime('%m-%d')} |{success_symbol}|  {self.cur_user_item.name} 的自动代理统计报告",
                    statistics,
                    self.cur_user_config,
                )
            except Exception as e:
                logger.opt(exception=True).warning(f"推送通知时出现异常: {e}")
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error", message=f"推送通知时出现异常: {e}"
                    ),
                )

        if all(self.run_book.values()):
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
            await self.cur_user_config.set("Data", "LastProxyStatus", "成功")
            self.cur_user_item.status = "完成"
            logger.success(f"用户 {self.cur_user_uid} 的自动代理任务已完成")
            await Notify.push_plyer(
                "成功完成一个自动代理任务！",
                f"已完成用户 {self.cur_user_item.name} 的 MaaEnd 自动代理任务",
                f"已完成 {self.cur_user_item.name} 的 MaaEnd 自动代理任务",
                3,
            )
        else:
            await self.cur_user_config.set("Data", "LastProxyStatus", "失败")
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
