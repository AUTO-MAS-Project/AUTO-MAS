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
import io
import json
import re
import shlex
import sys
import tempfile
import uuid
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from time import time, time_ns
from typing import Any

import app.core.notify.formats.maaend as _format_maaend
from app.config import ConfigCollection
from app.core import Config, Notify, Publisher
from app.core.history import aggregate_data
from app.core.ws import protocol
from app.models.config import MaaEndConfig, MaaEndUserConfig
from app.models.emulator import DeviceBase, DeviceInfo
from app.models.notification import LocalNotice
from app.models.schema import HistoryAggregationItem, HistoryWrite, WSTaskNoticeData
from app.models.task import LogRecord, ScriptItem
from app.services import System
from app.services import endfield_launcher as _service_endfield_launcher
from app.services.common.maa_capture import AdbCapture, Win32Capture
from app.task.base import ScriptAutoProxyBase
from app.task.emulator_core import (
    close_emulator,
    resolve_device_ref,
    resolve_host_adb,
)
from app.task.failure_capture_core import FailureCapture
from app.task.MaaFW.tools.core.interface.loader import load_interface_model
from app.task.MaaFW.tools.core.interface.task_config import (
    build_task_option_maps,
    normalize_task_options_by_task,
)
from app.task.MaaFW.tools.core.runner.run_plan import (
    _build_pretask_plans,
    _select_resource,
)
from app.task.MaaFW.tools.embedded.shell_instances import _Labels, _mxu_option_values
from app.task.proxy_helpers import (
    CONFIG_BASE_NATIVE,
    append_push_log,
    kill_pids,
    push_dispatch_log,
)
from app.utils import (
    MAAEND_AUTO_COLLECT_TASK,
    MAAEND_DELIVERY_TASK,
    MAAEND_RUN_MOOD_BOOK,
    MAAEND_TASKS,
    UTC4,
    LogMonitor,
    ProcessManager,
    ProcessRunner,
    get_logger,
    is_process_running,
    log_box,
)
from app.utils import io as _utils_io
from app.utils.common.log import sources as log_source

from .inventory_report import INVENTORY_REPORT_RULE, InventoryReport, inventory_resolve
from .push_log import MAAEND_PUSH_RULES, maaend_resolve
from .resource_loader import (
    MaaEndResourceLoader,
    get_loaded_maaend_options,
    load_maaend_interface_i18n,
    load_maaend_task_i18n,
    maaend_task_option_supported,
    maaend_task_supported,
)
from .ScriptConfig import maaend_config_base, maaend_mas_config_dir
from .tools import replace_account_switch_task
from .tools.backup_archive import archive_mas_runtime_backup, read_overlay_values
from .tools.game_launcher import verify_launcher_signature
from .tools.launcher_start import (
    async_start_game_via_launcher,
    find_launcher_pids,
)
from .tools.log_bundle import export_failure_logs
from .tools.log_statistics import parse_maaend_failed_tasks, parse_maaend_statistics
from .update_takeover import (
    read_new_mxu_logs,
    snapshot_mxu_logs,
    update_maaend_after_stage,
)

logger = get_logger("MaaEnd 自动代理")

_MAAEND_ACCOUNT_SWITCH_TASK = "AccountSwitch"
_MAAEND_ANDROID_OPEN_GAME_TASK = "AndroidOpenGame"
_MAAEND_GAME_SETTING_PRETASK = "__MXU_PRETASK__GameSetting"
_MAAEND_LAUNCH_GAME_PRETASK = "__MXU_PRETASK__LaunchGamePC"
_MAAEND_CLOSE_GAME_TASK = "CloseGamePC"
_AUTOMAS_GAME_PRE_ACTION_ID = "automas-endfield"
# 终末地 PC 客户端进程名固定，MAS 接管启动前据此避免重复拉起
_MAAEND_CLIENT_PROCESS = "Endfield.exe"
# 启动器 UI 自动化（前台点击 + 全局鼠标）一次只能有一路：跨脚本按此锁串行
_LAUNCHER_AUTOMATION_LOCK = asyncio.Lock()
# 后一个启动会话接管同安装后，旧会话的延迟收尾不得关闭新会话的游戏或启动器。
_LAUNCHER_OWNERS: dict[Path, object] = {}
_MAAEND_SANITY_TASK_NAMES = {"ProtocolSpace", "AutoEssence"}
_MXU_TASKS_COMPLETED = re.compile(
    r"收到 state-changed，已刷新运行时状态,\s*kind:\s*tasks-completed\s*$"
)


def _game_launch_command(
    *,
    launcher_path: str,
    game_path: str,
    game_arguments: str,
    result_path: Path | None = None,
) -> list[str]:
    """两个切号入口共用同一个独立启动程序。"""
    command = [
        sys.executable,
        "-X",
        "utf8",
        str(Path(__file__).parent / "tools/game_launcher.py"),
        launcher_path,
        game_path,
        f"--arguments={game_arguments}",
    ]
    if result_path is not None:
        command.extend(["--result-file", str(result_path)])
    return command


def _describe_maaend_pretask_failure(
    task_name: str, *, output: str, returncode: int
) -> str:
    """将上游启动诊断转换为可操作提示，完整输出另行保留在日志中。"""

    if task_name == _MAAEND_LAUNCH_GAME_PRETASK:
        hints = (
            (
                "无法找到启动器",
                "MaaEnd 未能找到官方启动器，请在 MAS 游戏设置中手动选择 Launcher.exe 后重试。",
            ),
            (
                "填写的 launcher.exe 路径无效",
                "MaaEnd 启动器路径无效，请在 MAS 或 MaaEnd 原生配置中重新选择 Launcher.exe。",
            ),
            (
                "failed to find launcher install directory",
                "MaaEnd 未能找到官方启动器安装目录。请检查 MaaEnd 的区服选择和启动器安装记录，"
                "新版 MaaEnd 可在 MAS 中手动指定启动器路径，旧版请更新 MaaEnd。",
            ),
            (
                "failed to start launcher",
                "MaaEnd 未能打开官方启动器。请确认启动器能手动打开、文件存在且运行权限一致。",
            ),
            (
                "launcher window not found",
                "MaaEnd 未找到启动器窗口。请检查区服选择，以及启动器是否停留在更新、登录或确认弹窗。",
            ),
            (
                "failed to initialize maa framework",
                "MaaEnd 自动化组件初始化失败。请检查 MaaEnd 安装文件是否完整，或重新安装 MaaEnd。",
            ),
            (
                "game window not found after launching",
                "MaaEnd 等待游戏窗口超时。请检查游戏启动报错及启动器更新状态，或切换其他启动方式。",
            ),
            (
                "failed to run launcher pipeline",
                "MaaEnd 未能完成启动器操作。请检查启动器是否存在更新、登录或确认弹窗，"
                "或切换为「启动器启动」/「MAS 启动」。",
            ),
        )
        for marker, hint in hints:
            if marker in output.casefold():
                return hint
        action = "启动游戏"
    else:
        action = "应用游戏显示设置"
    return (
        f"MaaEnd {action}失败（退出码 {returncode}），尚未识别具体原因。"
        "请导出问题包排查，原始错误已保留在日志中。"
    )


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
        elif set(selected) - available:
            logger.warning(
                "MaaEnd 自动采集的部分已选项不再受当前版本支持，已忽略；"
                "请在自动采集配置中重新确认选择，旧路线不会自动转换为新物品"
            )
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
    launcher_path: str,
    game_path: str,
    game_arguments: str,
    result_path: Path,
    enabled: bool = True,
) -> None:
    """让 MXU 在 PI pretask 完成后调用 MAS 启动入口。

    启动器启动（Game.LaunchMode == "Launcher"）时由 MAS 自行经官方启动器
    拉起游戏，此处的直启入口以 ``enabled=False`` 移除，避免回退直启。
    """

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
    if not enabled:
        instance["preActions"] = pre_actions
        return
    command = _game_launch_command(
        launcher_path=launcher_path,
        game_path=game_path,
        game_arguments=game_arguments,
        result_path=result_path,
    )
    pre_actions.insert(
        0,
        {
            "id": _AUTOMAS_GAME_PRE_ACTION_ID,
            "customName": "AUTO-MAS 启动终末地",
            "enabled": True,
            "program": command[0],
            # MXU 使用 shell_words 拆参数，需 POSIX 引号保护 Windows 路径和原始参数。
            "args": shlex.join(command[1:]),
            # 等待启动入口完成；是否已有游戏由入口判断，不能按 Python 进程跳过。
            "waitForExit": True,
            "skipIfRunning": False,
            "useCmd": False,
        },
    )
    instance["preActions"] = pre_actions


class AutoProxyTask(ScriptAutoProxyBase[MaaEndConfig, MaaEndUserConfig]):
    """MaaEnd 自动代理模式"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: MaaEndConfig,
        user_config: ConfigCollection[MaaEndUserConfig],
        emulator_manager: DeviceBase | None,
        *,
        capture_adb: AdbCapture,
        capture_win32: Win32Capture,
        on_error_screenshot: Callable[[Path], None] | None = None,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        self.emulator_manager = emulator_manager
        self.emulator_info: DeviceInfo | None = None
        self.capture_adb = capture_adb
        self.capture_win32 = capture_win32
        self.on_error_screenshot = on_error_screenshot
        self._attempt_start_ns: int | None = None
        self._attempt_screenshot_paths: list[Path] = []
        # 失败日志包：MXU 每次启动都会清空 debug/（开启日志包时由 set_maaend 强制打开），
        # 所以取证时机只能是「一次尝试结束、MXU 已退出、下一次启动之前」。用启动次数与
        # 已归档次数比对判断是否还有未归档的现场，重复调用只会等同一个打包作业。
        self._mxu_launch_count = 0
        self._archived_launch_count = 0
        self._bundle_job: asyncio.Task | None = None
        # 打包失败过就不再强制 MXU 清日志：宁可下一轮日志混一点，也要留下现场再试一次。
        self._bundle_failed = False
        self._failure_capture = FailureCapture(stopped=lambda: self.stopped_manually)
        self.cur_user_item = self.script_info.user_list[self.script_info.current_index]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config = self.user_config[self.cur_user_uid]
        self.check_result = "-"
        self.account_switch_task_name = ""
        self.color_match_failed_message: str | None = None
        self.retryable = True
        self.update_failed: bool = False
        self.game_launch_result_path = (
            Path.cwd() / f"data/{script_info.script_id}/game-launch.json"
        )
        # 用户级「节点详情推送」开关（Notify.PushLogMode），prepare 时按配置启用
        self.push_log_enabled = False
        self.inventory_status_messages: set[str] = set()
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
        # 在首阶段预任务执行前读取，后续阶段复用同一份游戏显示设置。
        self.original_game_settings: tuple[int, int, str] | None = None
        self.original_game_settings_read = False
        self.launcher_game_setting_options: dict[str, Any] = {}
        self.launcher_runtime_path: Path | None = None
        self.launcher_owner: object = object()
        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        self.auto_collect_run_at: datetime | None = None
        self.auto_collect_routes: dict[str, list[str]] = {}

    def _account_switch_method(self) -> str:
        """读取账号切换方式；缺失或非法值沿用 MaaEnd 默认入口。"""

        method = str(self.script_config.Run.AccountSwitchMethod or "")
        return method if method in {"MAS", "MAAEND"} else "MAAEND"

    def _launch_mode(self) -> str:
        """旧 Client 配置按当前资源入口保留原行为，显式选择不自动切换。"""
        mode = self.script_config.Game.LaunchMode
        if mode == "Client":
            root_path = self._maaend_root_path()
            if root_path is None:
                raise ValueError("MaaEnd 路径未配置")
            loader = MaaEndResourceLoader.get_loaded(root_path)
            controller = str(self.script_config.Game.ControllerType)
            return loader.resolve_launch_mode(mode, controller)
        return mode

    def _game_setting_pretask(self) -> str | None:
        """MAS 两种启动方式只复用独立设置入口，避免附带启动游戏。"""
        root_path = self._maaend_root_path()
        if root_path is None:
            raise ValueError("MaaEnd 路径未配置")
        loader = MaaEndResourceLoader.get_loaded(root_path)
        controller = str(self.script_config.Game.ControllerType)
        if self._launch_mode() == "MaaEnd":
            if controller in loader.pretask_controllers("LaunchGamePC"):
                return _MAAEND_LAUNCH_GAME_PRETASK
            return None
        if controller in loader.pretask_controllers("GameSetting"):
            return _MAAEND_GAME_SETTING_PRETASK
        return None

    async def _start_game(self, *, preserve_running_game: bool = False) -> None:
        """首轮启动与更新重启共用用户选择，显示设置不支持时保留配置。"""
        mode = self._launch_mode()
        if (
            self.script_config.Game.SetResolution
            and self._game_setting_pretask() is None
        ):
            logger.warning("当前启动方式不支持启动时设置分辨率，本轮使用游戏现有设置")
        if mode == "Launcher":
            logger.info("启动方式为「启动器启动」")
            await self._mas_launch_game_via_launcher(
                preserve_running_game=preserve_running_game
            )
            return
        async with _LAUNCHER_AUTOMATION_LOCK:
            if mode == "MaaEnd":
                logger.info("启动方式为「MaaEnd 启动」")
                # 手选路径与上游启动入口共用；未指定时保留 MaaEnd 原生定位方式。
                if self.script_config.Game.LauncherPath:
                    launcher_path = self._launcher_path()
                else:
                    launcher_path = await asyncio.to_thread(
                        _service_endfield_launcher.discover_launcher_exe,
                        Path(str(self.script_config.Game.Path)),
                    )
                if launcher_path is not None:
                    self.launcher_runtime_path = launcher_path.resolve()
                    _LAUNCHER_OWNERS[self.launcher_runtime_path] = self.launcher_owner
                else:
                    logger.warning(
                        "无法从游戏目录确认 MaaEnd 使用的启动器位置，"
                        "任务结束时仅清理游戏，启动器需手动退出"
                    )
                await self._launch_game_via_maaend(
                    preserve_running_game=preserve_running_game
                )
                return
            logger.info("启动方式为「MAS 启动」")
            if (
                not preserve_running_game
                and self.mode == self.first_run_mode
                and self.script_config.Game.SetResolution
                and self._game_setting_pretask() is not None
            ):
                await self._apply_launcher_game_settings()
            launcher_path = self._launcher_path()
            if launcher_path is not None:
                self.launcher_runtime_path = launcher_path.resolve()
                _LAUNCHER_OWNERS[self.launcher_runtime_path] = self.launcher_owner
            await self._mas_launch_game_directly()

    def _launcher_path(self) -> Path | None:
        """自动与手动路径共用服务层校验；失效的手动路径明确报错。"""
        return _service_endfield_launcher.resolve_launcher_exe(
            Path(str(self.script_config.Game.Path or "")),
            str(self.script_config.Game.LauncherPath or ""),
        )

    def _launcher_path_text(self) -> str:
        """直接启动入口使用的启动器路径：手动配置优先，未配置时按游戏路径自动识别。

        check() 已在自动代理模式放行前校验过；这里再兜一层，避免未校验路径的
        会话进入时抛错。
        """

        try:
            launcher_path = self._launcher_path()
        except ValueError:
            launcher_path = None
        if launcher_path is not None:
            return str(launcher_path)
        return str(self.script_config.Game.LauncherPath or "")

    async def _apply_launcher_game_settings(
        self, *, preserve_running_game: bool = False
    ) -> None:
        """执行对应版本的上游预任务；新版同时负责启动游戏。"""
        task_name = self._game_setting_pretask()
        if task_name is None:
            raise RuntimeError("当前 MaaEnd 不支持所选启动方式的游戏设置入口")
        interface = load_interface_model(self.maaend_root_path)
        controller_name = str(self.script_config.Game.ControllerType)
        controller = next(
            (item for item in interface.controller if item.name == controller_name),
            None,
        )
        if controller is None:
            raise RuntimeError(
                f"MaaEnd 控制器 {controller_name} 在当前资源中不存在，请重新配置 MaaEnd"
            )
        resource = _select_resource(interface, "", controller)
        skipped: list[str] = []
        # 复用现有 MXU 选项转换与 PI 预任务命令解析，不复制上游显示设置逻辑。
        setting_options = self.launcher_game_setting_options.copy()
        if (
            task_name == _MAAEND_LAUNCH_GAME_PRETASK
            and self.script_config.Game.LauncherPath
        ):
            launcher_path = self._launcher_path()
            if launcher_path is not None:
                await asyncio.to_thread(verify_launcher_signature, launcher_path)
                # 仅覆盖传给上游的本轮参数，不固化到原生或 MAS 配置来源。
                setting_options["LaunchGamePCLauncherPath"] = {
                    "type": "select",
                    "value": "Manual",
                }
                setting_options["LaunchGamePCLauncherExe"] = {
                    "type": "input",
                    "values": {"LauncherExe": str(launcher_path)},
                }
        values = _mxu_option_values(
            setting_options,
            build_task_option_maps(interface)[task_name],
            "游戏启动设置",
            _Labels(interface, None),
            skipped,
        )
        if skipped:
            raise ValueError(
                f"游戏启动设置已失效，请重新配置 MaaEnd: {'、'.join(skipped)}"
            )
        options = normalize_task_options_by_task(
            {task_name: values},
            [task_name],
            interface,
            controller_name=controller.name,
            resource_name=resource.name,
        )
        plans = _build_pretask_plans(
            base_dir=self.maaend_root_path,
            interface_model=interface,
            controller=controller,
            resource=resource,
            selected_ids=[task_name],
            task_options=options,
            i18n_mapping={},
        )
        if not plans:
            raise RuntimeError(
                "当前 MaaEnd 不支持此控制器的游戏启动设置，请更新 MaaEnd"
            )
        if (
            not preserve_running_game
            and self.mode == self.first_run_mode
            and self.script_config.Game.SetResolution
        ):
            self._read_original_game_settings()
            # 路径、签名与预任务参数全部就绪后再关闭游戏，校验失败不打断现有游戏。
            # 新版检测游戏已运行会直接返回；调用方持有启动器锁，此处不能再次获取。
            await self._kill_game_process_unlocked()
        await push_dispatch_log(
            self.script_info,
            "正在由 MaaEnd 启动游戏..."
            if task_name == _MAAEND_LAUNCH_GAME_PRETASK
            else "正在应用 MaaEnd 游戏启动设置...",
        )
        plan = plans[0]
        launching = task_name == _MAAEND_LAUNCH_GAME_PRETASK
        action = "启动游戏" if launching else "应用游戏显示设置"
        # MaaEnd v2.35.0 的启动器和游戏窗口各可等待 300 秒，另留 300 秒
        # 给框架初始化、启动器操作与窗口稳定等待；整轮时限和用户取消仍生效。
        timeout = 900 if launching else 60
        try:
            result = await ProcessRunner.run_process(
                plan.executable,
                *plan.args,
                cwd=self.maaend_root_path,
                timeout=timeout,
                kill_tree_on_cancel=True,
            )
        except asyncio.TimeoutError as error:
            raise RuntimeError(
                f"MaaEnd {action}超时（{timeout} 秒）。请检查启动器和游戏是否正常响应，或切换其他启动方式。"
            ) from error
        except FileNotFoundError as error:
            raise RuntimeError(
                "MaaEnd 启动组件或安装目录不存在。请检查 MaaEnd 路径及安装文件是否完整。"
            ) from error
        except PermissionError as error:
            raise RuntimeError(
                "无法运行 MaaEnd 启动组件，访问被拒绝。请检查文件权限，以及 MAS 与 MaaEnd 的运行权限是否一致。"
            ) from error
        if result.returncode != 0:
            logger.error(
                f"MaaEnd 预任务 {task_name} 执行失败: {result.failure_detail()}"
            )
            raise RuntimeError(
                _describe_maaend_pretask_failure(
                    task_name,
                    output=f"{result.stdout}\n{result.stderr}",
                    returncode=result.returncode,
                )
            )

    async def _launch_game_via_maaend(
        self, *, preserve_running_game: bool = False
    ) -> None:
        """调用方持有启动器锁，由 MaaEnd 应用设置并启动游戏。"""
        needs_wait = not is_process_running(_MAAEND_CLIENT_PROCESS) or (
            not preserve_running_game
            and self.mode == self.first_run_mode
            and bool(self.script_config.Game.SetResolution)
        )
        await self._apply_launcher_game_settings(
            preserve_running_game=preserve_running_game
        )
        if needs_wait:
            await asyncio.sleep(int(self.script_config.Game.WaitTime))

    @staticmethod
    def _game_window_present() -> bool:
        """终末地客户端窗口是否真实存在：进程残留但窗口已消失时不能当作在运行。"""
        from app.utils import IS_WINDOWS

        if not IS_WINDOWS:
            return False
        import win32gui

        return bool(win32gui.FindWindow("UnityWndClass", "Endfield"))

    async def _mas_launch_game_directly(self) -> None:
        """通过现有直启入口拉起游戏，也用于更新确认后的重新启动。"""
        if is_process_running(_MAAEND_CLIENT_PROCESS) and self._game_window_present():
            logger.info("检测到终末地客户端已运行，准备由 MAS 执行账号切换")
            return
        # 进程残留但窗口已消失（如更新重启失败）：清掉残留后重新拉起
        await self.game_process_manager.kill()
        logger.info(f"启动终末地: {self.script_config.Game.Path}")
        command = _game_launch_command(
            launcher_path=self._launcher_path_text(),
            game_path=str(self.script_config.Game.Path),
            game_arguments=str(self.script_config.Game.Arguments),
        )
        result = await ProcessRunner.run_process(
            *command, timeout=60, kill_tree_on_cancel=True
        )
        if result.returncode != 0:
            raise RuntimeError(result.failure_detail())
        logger.info(result.stderr or result.stdout)
        await asyncio.sleep(self.script_config.Game.WaitTime)

    async def _restart_game_after_update(self) -> None:
        """游戏内确认更新后，只按用户选择的启动方式重新拉起。"""
        await self._start_game(preserve_running_game=True)

    async def _mas_launch_game_via_launcher(
        self, *, preserve_running_game: bool = False
    ) -> None:
        """由 MAS 经官方启动器拉起终末地。

        启动器模式下移除 MAS 注入的直接启动前置程序，避免任何直启回退。
        前台点击与全局鼠标一次只能有一路，跨脚本按 _LAUNCHER_AUTOMATION_LOCK 串行。
        """

        async with _LAUNCHER_AUTOMATION_LOCK:
            launcher_path = self._launcher_path()
            if launcher_path is None:
                raise RuntimeError(
                    "未找到终末地官方启动器，请重新选择启动器可执行文件（.exe）"
                )
            self.launcher_runtime_path = launcher_path.resolve()
            _LAUNCHER_OWNERS[self.launcher_runtime_path] = self.launcher_owner
            # 启动器模式只复用旧版独立设置任务，游戏始终由 MAS 经启动器拉起。
            if (
                not preserve_running_game
                and self.mode == self.first_run_mode
                and self.script_config.Game.SetResolution
                and self._game_setting_pretask() is not None
            ):
                await self._apply_launcher_game_settings()
            if (
                is_process_running(_MAAEND_CLIENT_PROCESS)
                and self._game_window_present()
            ):
                logger.info("检测到终末地客户端进程已在运行，跳过由 MAS 重复启动游戏")
                await push_dispatch_log(
                    self.script_info, "检测到客户端已在运行，跳过启动"
                )
                return
            # 拉起前校验官方签名：与直接启动（game_launcher）同一套校验口径
            await asyncio.to_thread(verify_launcher_signature, launcher_path)
            if await self.game_process_manager.is_running():
                # 阶段切换可能只关闭游戏；手动指定的常驻启动器仍由同一管理器持有。
                await push_dispatch_log(self.script_info, "复用仍在运行的终末地启动器")
            else:
                await push_dispatch_log(
                    self.script_info, f"正在拉起终末地启动器: {launcher_path.name}"
                )
                # 手选 Games.exe 也已解析到稳定入口，始终定位终末地页。
                await self.game_process_manager.open_process(
                    launcher_path, "--game=Endfield", "--reason=4"
                )
            # 启动器交互在后台线程内同步执行，on_log 契约是同步回调；push_dispatch_log
            # 是 async 函数，须经 run_coroutine_threadsafe 调度回事件循环
            launch_loop = asyncio.get_running_loop()

            def _push_launch_log(line: str) -> None:
                asyncio.run_coroutine_threadsafe(
                    push_dispatch_log(self.script_info, line), launch_loop
                )

            if not await async_start_game_via_launcher(
                launcher_path,
                on_log=_push_launch_log,
                on_error_screenshot=self._record_error_screenshot,
            ):
                raise RuntimeError("终末地启动器未能拉起游戏，请人工确认启动器状态")
            wait_time = int(self.script_config.Game.WaitTime)
            await push_dispatch_log(
                self.script_info,
                f"游戏窗口已出现，正在等待游戏完成启动（{wait_time}s）...",
            )
            await asyncio.sleep(wait_time)

    async def _kill_launcher_process(self) -> None:
        """持有启动器锁时，按进程家族与安装根目录树结束启动器。"""

        try:
            launcher_path = self.launcher_runtime_path
            if launcher_path is None and self._launch_mode() != "MaaEnd":
                launcher_path = self._launcher_path()
            if launcher_path is not None:
                pids = await asyncio.to_thread(find_launcher_pids, launcher_path)
                if pids:
                    await kill_pids(pids)
        except Exception as e:
            logger.opt(exception=True).warning(f"结束终末地启动器进程失败: {e}")

    async def check(self) -> str:
        """检查运行条件；拒绝运行时明确标记为异常或跳过。"""

        # 单独运行脚本是用户主动指定的一次性运行，不受单日代理次数上限约束
        if (
            self.task_info.is_queue_task
            and self.script_config.Run.ProxyTimesLimit != 0
            and (
                self.cur_user_config.Data.ProxyTimes
                >= self.script_config.Run.ProxyTimesLimit
            )
        ):
            self.cur_user_item.status = "跳过"
            return "今日代理次数已达上限, 跳过该用户"

        account_id = str(self.cur_user_config.Info.Id).strip()
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
                self.cur_user_item.status = "异常"
                return "MaaEnd 路径未配置"
            try:
                loader = MaaEndResourceLoader.get_loaded(root_path)
            except ValueError as error:
                self.cur_user_item.status = "异常"
                return f"MaaEnd 资源加载失败: {error}"
            if not (
                loader.has_pretask("GameSetting") or loader.has_pretask("LaunchGamePC")
            ) or not loader.has_task(_MAAEND_CLOSE_GAME_TASK):
                self.cur_user_item.status = "异常"
                return "当前 MaaEnd 版本不支持托管游戏启动，请更新 MaaEnd 后重试"
            if self._launch_mode() == "MaaEnd" and self._game_setting_pretask() is None:
                self.cur_user_item.status = "异常"
                return "当前 MaaEnd 或控制器不支持「MaaEnd 启动」，请选择启动器启动或 MAS 启动"
            if (
                account_switch_method == "MAAEND"
                and account_id
                and not loader.has_task(_MAAEND_ACCOUNT_SWITCH_TASK)
            ):
                self.cur_user_item.status = "异常"
                return "当前 MaaEnd 版本不支持内置账号切换，请更新 MaaEnd 后重试"

        config_base = maaend_config_base(self.cur_user_config.Info.Base)
        if config_base == CONFIG_BASE_NATIVE:
            config_file = (
                Path.cwd() / f"data/{self.script_info.script_id}/Temp/mxu-MaaEnd.json"
            )
        else:
            config_file = (
                maaend_mas_config_dir(
                    self.script_info.script_id,
                    str(self.cur_user_uid),
                    config_base,
                )
                / "mxu-MaaEnd.json"
            )
        self.maaend_config_file = config_file
        if not config_file.exists():
            self.cur_user_item.status = "异常"
            return "未找到 MaaEnd 配置文件, 请先完成「MaaEnd 配置」步骤"

        if self.cur_user_config.Info.IfQuickConfig:
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
        if (
            not self.cur_user_config.Info.IfQuickConfig
            or not self.cur_user_config.Task.IfAutoCollect
        ):
            return
        root_path = self._maaend_root_path()
        if root_path is None:
            raise ValueError("MaaEnd 路径未配置")
        groups = get_loaded_maaend_options(root_path)["autoCollectGroups"]
        if not groups:
            raise ValueError("MaaEnd 自动采集路线读取失败，请检查安装资源")
        auto_collect_mode = self.cur_user_config.Task.AutoCollectMode
        self.auto_collect_run_at = datetime.now(tz=UTC4)
        self.auto_collect_routes = _select_auto_collect_routes(
            auto_collect_mode,
            {
                key: getattr(self.cur_user_config.Task, key)
                for key in ("AutoCollectRoutes", "AutoCollectCommonRoutes")
            },
            groups,
            self.auto_collect_run_at,
        )

    def _daily_once_task_names(self) -> set[str]:
        # 独立送货、采集阶段固定每日一次，日常任务仍由用户选择。
        return {
            MAAEND_DELIVERY_TASK,
            MAAEND_AUTO_COLLECT_TASK,
            *_load_json_list(self.cur_user_config.Task.DailyOnceTasks),
        }

    def _daily_task_records(self) -> dict[str, str]:
        raw_records = _load_json_dict(self.cur_user_config.Data.PeriodTaskRecords)
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
        if self.cur_user_config.Info.SanityStrategy == "Inventory":
            return self._daily_once_task_done("ProtocolSpace")
        if self.cur_user_config.Info.SanityStrategy == "Native":
            tasks = self._source_maaend_tasks()
            sanity_tasks = [
                str(task["taskName"])
                for task in tasks or []
                if task.get("taskName") in _MAAEND_SANITY_TASK_NAMES
                and task.get("enabled", False)
            ]
            return bool(sanity_tasks) and all(
                self._daily_once_task_done(name) for name in sanity_tasks
            )
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

        records_data = _load_json_dict(self.cur_user_config.Data.PeriodTaskRecords)
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
            self.cur_user_config.Data.PeriodTaskRecords = json.dumps(
                records_data, ensure_ascii=False
            )
            await self.cur_user_config.commit()

    def _daily_once_skip_reason(self) -> str | None:
        """判断当前用户是否所有阶段都因每日一次规则而无需启动。"""

        mode_results = [self._mode_skip_reason(mode) for mode in MAAEND_RUN_MOOD_BOOK]
        if any(reason is None or missing for reason, missing in mode_results):
            return None
        daily_once_done = (
            self._quick_task_daily_once_done
            if self.cur_user_config.Info.IfQuickConfig
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
        self.log_start_time = datetime.now().astimezone()

        # ── 推送详情开关（在专项侧，不在 log_box）：关闭时不创建采集会话 ──
        # 该用户 push_log 保持为空，报告聚合自然只有结果行
        self.cur_user_item.push_log_mode = self.cur_user_config.Notify.PushLogMode
        self.push_log_enabled = self.cur_user_config.Notify.PushLogMode != "关闭"

        maaend_root_path = self.script_config.Info.Path
        if maaend_root_path is None:
            raise ValueError("Path未配置，请检查路径设置")
        self.maaend_root_path = maaend_root_path
        self.maaend_exe_path = self.maaend_root_path / "MaaEnd.exe"
        self.maaend_set_path = self.maaend_root_path / "config"
        self.maaend_log_path = self.maaend_root_path / "debug/maa.log"

        self.maaend_log_monitor = LogMonitor(
            (1, 23), "%Y-%m-%d %H:%M:%S.%f", self.check_log
        )

        if not self.cur_user_config.Info.IfQuickConfig:
            self.first_run_mode = "Routine"
            self.run_book = {mode: mode != "Routine" for mode in MAAEND_RUN_MOOD_BOOK}
            return

        self._prepare_auto_collect_routes()
        await self._refresh_stage_plan(list(MAAEND_RUN_MOOD_BOOK))

    async def _refresh_stage_plan(self, modes: list[str]) -> None:
        """重新评估指定的未完成阶段，保留已执行首阶段的前置任务身份。"""
        first_run_completed = (
            self.first_run_mode is not None and self.run_book[self.first_run_mode]
        )
        mode_skip_reasons: dict[str, str] = {}
        missing_task_modes: list[str] = []
        for mode in modes:
            reason, missing_task = self._mode_skip_reason(mode)
            self.run_book[mode] = reason is not None
            if reason is None:
                continue
            mode_skip_reasons[mode] = reason
            if missing_task:
                missing_task_modes.append(mode)
        if not first_run_completed:
            self.first_run_mode = next(
                (mode for mode in MAAEND_RUN_MOOD_BOOK if not self.run_book[mode]),
                None,
            )
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
            source_config = _utils_io.read_file(self.maaend_config_file)
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
        # 配置副本可能仍保留新版已移除的任务，阶段计划按当前 PI 声明判断。
        return [
            task
            for task in result
            if str(task.get("taskName", "")).startswith("__MXU_")
            or self._maaend_task_supported(str(task.get("taskName", ""))) is not False
        ]

    def _quick_config_base_skip_reason(self, mode: str) -> tuple[str | None, bool]:
        """快速配置下按 MAS 任务开关与 MaaEnd 配置判断阶段是否可执行。"""

        native_sanity = self.cur_user_config.Info.SanityStrategy == "Native"
        inventory_sanity = self.cur_user_config.Info.SanityStrategy == "Inventory"
        if mode == "Delivery":
            if not self.cur_user_config.Task.IfSeizeDeliveryJobs:
                return "快速配置未开启抢委托送货", False
            task_name = MAAEND_DELIVERY_TASK
            task_label = "抢委托送货"
        elif mode == "AutoCollect":
            if not self.cur_user_config.Task.IfAutoCollect:
                return "快速配置未开启自动采集", False
            if not any(self.auto_collect_routes.values()):
                return "今日采集周期无待执行路线", False
            task_name = MAAEND_AUTO_COLLECT_TASK
            task_label = "自动采集"
        else:
            sanity_enabled = bool(self.cur_user_config.Task.IfSanity) and (
                not self._quick_task_daily_once_done("Sanity")
            )
            if not (
                sanity_enabled
                or any(
                    (
                        bool(getattr(self.cur_user_config.Task, f"If{task_name}"))
                        and (not self._quick_task_daily_once_done(task_name))
                        for task_name in MAAEND_TASKS
                    )
                )
            ):
                return "快速配置未开启任何日常任务", False

            tasks = self._source_maaend_tasks()
            if tasks is None:
                return None, False

            # MaaEnd 2.28 的 AutoEssence 任务可能尚未出现在旧配置实例中；
            # set_maaend 会在临时运行配置中补齐任务，不能在这里提前跳过理智阶段。
            if (
                not native_sanity
                and self.cur_user_config.Task.IfSanity
                and not self._quick_task_daily_once_done("Sanity")
            ):
                target_sanity_task_name = "ProtocolSpace"
                if not inventory_sanity:
                    sanity_task_key, _ = (
                        self.cur_user_config.get_effective_sanity_task_key()
                    )
                    if sanity_task_key["SanityTaskType"] == "Essence":
                        target_sanity_task_name = "AutoEssence"
                if (
                    not any(
                        str(task.get("taskName", "")) == target_sanity_task_name
                        for task in tasks
                    )
                    and self._maaend_task_supported(target_sanity_task_name)
                    is not False
                ):
                    return None, False

            target_sanity_task_name: str | None = None
            for task in tasks:
                task_name = str(task.get("taskName", ""))
                if (
                    task_name == _MAAEND_ANDROID_OPEN_GAME_TASK
                    and str(self.script_config.Game.ControllerType) == "CloudADB"
                ):
                    continue
                if task_name.startswith("__MXU_") or task_name in {
                    _MAAEND_ACCOUNT_SWITCH_TASK,
                    _MAAEND_CLOSE_GAME_TASK,
                    MAAEND_DELIVERY_TASK,
                    MAAEND_AUTO_COLLECT_TASK,
                }:
                    continue
                if task_name in _MAAEND_SANITY_TASK_NAMES:
                    if not self.cur_user_config.Task.IfSanity:
                        continue
                    if native_sanity:
                        if task.get(
                            "enabled", False
                        ) and not self._daily_once_task_done(task_name):
                            return None, False
                        continue
                    if target_sanity_task_name is None:
                        target_sanity_task_name = "ProtocolSpace"
                        if not inventory_sanity:
                            sanity_task_key, _ = (
                                self.cur_user_config.get_effective_sanity_task_key()
                            )
                            if sanity_task_key["SanityTaskType"] == "Essence":
                                target_sanity_task_name = "AutoEssence"
                    if task_name == target_sanity_task_name:
                        if not self._quick_task_daily_once_done("Sanity"):
                            return None, False
                    continue
                if task_name in MAAEND_TASKS:
                    if getattr(self.cur_user_config.Task, f"If{task_name}") and (
                        not self._quick_task_daily_once_done(task_name)
                    ):
                        return None, False
                    continue
                if bool(task.get("enabled", False)):
                    return None, False
            return "MaaEnd 配置中没有可执行的日常任务", False

        if self._daily_once_task_done(task_name):
            return f"{task_label}任务今日已完成", False

        tasks = self._source_maaend_tasks()
        if tasks is None:
            return None, False
        if not any(str(task.get("taskName", "")) == task_name for task in tasks):
            return f"MaaEnd 配置中不存在{task_label}任务", True
        return None, False

    def _mode_skip_reason(self, mode: str) -> tuple[str | None, bool]:
        """判断某阶段是否无可执行任务，空阶段直接视为完成。

        Args:
            mode (str): MaaEnd 运行阶段。

        Returns:
            tuple[str | None, bool]: 跳过原因（None 表示该阶段有任务可执行），
                以及是否因阶段任务在 MaaEnd 配置中不存在导致跳过。
        """

        return self._quick_config_base_skip_reason(mode)

    async def _wait_maaend_stage(self, log_offsets: dict[Path, int]) -> None:
        """等待日志结果、进程退出或 MXU 队列结束，兜底完成后未退出的进程。"""
        process = self.maaend_process_manager.process
        if not isinstance(process, asyncio.subprocess.Process):
            self.cur_user_log.status = "MaaEnd 未启动可监控的进程"
            return

        async def wait_exit() -> None:
            # Process.wait() 也可能等待管道关闭；returncode 独立反映主进程退出。
            while process.returncode is None:
                await asyncio.sleep(0.2)

        async def wait_completed() -> None:
            # 与更新接管独立消费偏移，不能吃掉首阶段的下载记录。
            offsets = log_offsets.copy()
            while True:
                lines = await asyncio.to_thread(
                    read_new_mxu_logs, self.maaend_root_path, offsets
                )
                if any(_MXU_TASKS_COMPLETED.search(line) for line in lines):
                    return
                await asyncio.sleep(0.5)

        async def wait_launch_failure() -> str:
            # MXU 不透传前置程序输出，由 MAS 启动入口回传自己的启动结果。
            while True:
                if (
                    self.emulator_manager is None
                    and self.game_launch_result_path.is_file()
                ):
                    result = _utils_io.read_file(self.game_launch_result_path)
                    if result["error"] is not None:
                        return str(result["error"])
                await asyncio.sleep(0.5)

        await self.maaend_log_monitor.start_monitor_process(process, "stdout")
        monitor = self.maaend_log_monitor.task
        exit_task = asyncio.create_task(wait_exit())
        result_task = asyncio.create_task(self.wait_event.wait())
        completed_task = asyncio.create_task(wait_completed())
        launch_task = asyncio.create_task(wait_launch_failure())
        try:
            waiting = {monitor, exit_task, result_task, completed_task, launch_task}
            while True:
                done, _ = await asyncio.wait(
                    waiting, return_when=asyncio.FIRST_COMPLETED
                )
                if completed_task in done and completed_task.exception():
                    logger.warning(
                        f"MXU 队列结束日志读取失败，继续等待进程或超时: "
                        f"{completed_task.exception()}"
                    )
                    waiting.remove(completed_task)
                    done.remove(completed_task)
                if done:
                    break
            queue_completed = completed_task in done
            if exit_task in done or queue_completed:
                if queue_completed:
                    logger.info("MXU 已报告本轮队列结束，正在收齐任务日志")
                else:
                    logger.info(f"MaaEnd 主进程已退出，退出码: {process.returncode}")
                # 消费已经写入管道的尾部日志，但不无限等待继承管道的子进程。
                if not monitor.done():
                    try:
                        await asyncio.wait_for(asyncio.shield(monitor), timeout=2)
                    except asyncio.TimeoutError:
                        pass
                    except Exception as error:
                        logger.warning(f"MaaEnd 日志读取失败: {error}")
            if launch_task in done:
                error = launch_task.exception() or launch_task.result()
                logger.error(f"终末地启动失败: {error}")
                self.cur_user_log.status = f"游戏启动失败: {error}"
            elif monitor.done() and not monitor.cancelled() and monitor.exception():
                logger.warning(f"MaaEnd 日志读取失败: {monitor.exception()}")
                self.cur_user_log.status = "MaaEnd 日志读取失败"
            elif exit_task in done or monitor.done() or queue_completed:
                await self.maaend_log_monitor.stop()
                await self.check_log(
                    self.maaend_log_monitor.log_contents,
                    self.maaend_log_monitor.latest_time,
                    if_stream_end=True,
                )
            if queue_completed and process.returncode is None:
                # 队列结束不代表成功；先解析结果，再关掉挂起进程，避免更新接管继续等它。
                logger.warning("MaaEnd 队列已结束但进程未退出，正在中止脚本进程")
                await self.maaend_process_manager.kill()
        finally:
            exit_task.cancel()
            result_task.cancel()
            completed_task.cancel()
            launch_task.cancel()
            await asyncio.gather(
                exit_task,
                result_task,
                completed_task,
                launch_task,
                return_exceptions=True,
            )
            await self.maaend_log_monitor.stop()

    async def _update_after_first_stage(
        self, log_offsets: dict[Path, int], *, stage_label: str
    ) -> None:
        """按首阶段的下载记录更新，独立记录结果并保留已完成任务。"""
        root_path = self.maaend_exe_path.parent
        update_log: LogRecord | None = None

        async def before_update_session() -> bool:
            # 更新会话会重新启动 MXU：先把失败阶段的现场归档，否则「启动时清理日志」
            # 会在归档前把 debug/ 清掉。返回 False 表示现场没保存好，新会话要关掉清理。
            return await self._archive_failure_logs(label=f"{stage_label}阶段失败的")

        def after_update_session_launch() -> None:
            # 会话真的起来了才记一次启动：debug/ 从此归它，收尾据此判断要不要补归档。
            self._mxu_launch_count += 1

        def update_status(message: str) -> None:
            nonlocal update_log
            if update_log is None:
                update_log = LogRecord(phase="Update", status="MaaEnd 正在更新")
                self.cur_user_item.add_log_record(
                    datetime.now().astimezone(), update_log
                )
            update_log.content.append(message + "\n")
            self.script_info.log = message

        try:
            version = await update_maaend_after_stage(
                root_path,
                log_offsets,
                process=self.maaend_process_manager.process,
                on_status=update_status,
                on_before_session=before_update_session,
                on_session_launched=after_update_session_launch,
            )
            if version is not None:
                await asyncio.to_thread(
                    MaaEndResourceLoader.get_cached,
                    root_path,
                    force_reload=True,
                )
                self._source_tasks_cache = None
                self._prepare_auto_collect_routes()
                modes = list(MAAEND_RUN_MOOD_BOOK)
                next_index = modes.index(self.mode) + int(self.run_book[self.mode])
                await self._refresh_stage_plan(modes[next_index:])
                self.task_dict = None
            if update_log is not None:
                update_log.status = "Success!" if version is not None else "跳过更新"
        except asyncio.CancelledError:
            self.update_failed = True
            if update_log is not None:
                update_log.status = "MaaEnd 更新被中止"
            raise
        except Exception as error:
            self.update_failed = True
            message = f"MaaEnd 更新失败，已停止后续任务: {error}"
            update_status(message)
            if update_log is not None:
                update_log.status = message
            raise

    async def main_task(self):
        """自动代理模式主逻辑"""

        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        if self.cur_user_config.Data.LastProxyDate.strftime("%Y-%m-%d") != self.curdate:
            self.cur_user_config.Data.LastProxyDate = datetime.now(tz=UTC4)
            await self.cur_user_config.commit()
            self.cur_user_config.Data.ProxyTimes = 0
            await self.cur_user_config.commit()

        self.check_result = await self.check()
        if self.check_result != "Pass":
            self.cur_user_item.add_log_record(
                datetime.now().astimezone(), LogRecord(status=self.check_result)
            )
            message = f"用户 {self.cur_user_item.name} 检查未通过: {self.check_result}"
            self.script_info.log = message
            self.script_info.log_first_line = 1
            if self.cur_user_item.status == "异常":
                logger.warning(message)
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(level="error", message=message),
                )
            else:
                logger.info(message)
            return

        await self.prepare()

        logger.info(f"开始代理用户 {self.cur_user_uid}")
        self.cur_user_item.status = "运行"
        # 任务前脚本每用户一次，先于全部重试；后置脚本由收尾阶段成对执行
        await self.run_user_scripts_before()

        run_times_limit = self.script_config.Run.RunTimesLimit
        if_quick_config = self.cur_user_config.Info.IfQuickConfig
        i = 0
        mode_order = list(MAAEND_RUN_MOOD_BOOK)
        mode_index = 0
        keep_game_for_login_retry = False
        while mode_index < len(mode_order):
            self.mode = mode_order[mode_index]
            stage_label = (
                MAAEND_RUN_MOOD_BOOK[self.mode] if if_quick_config else "原配置"
            )
            if self.run_book[self.mode]:
                mode_index += 1
                i = 0
                self.task_dict = None
                continue
            if i >= run_times_limit:
                logger.warning(
                    f"用户: {self.cur_user_uid} - {stage_label}阶段重试次数已耗尽"
                )
                mode_index += 1
                i = 0
                self.task_dict = None
                continue
            i += 1
            self._attempt_start_ns = time_ns()
            self._attempt_screenshot_paths.clear()
            self._failure_capture.reset()
            self.emulator_info = None
            self.retryable = True
            logger.info(
                f"用户 {self.cur_user_item.name} - {stage_label}"
                f"阶段尝试次数: {i}/{run_times_limit}"
            )
            self.log_start_time = datetime.now().astimezone()
            self.cur_user_log = LogRecord(
                phase=self.mode if if_quick_config else "Source"
            )
            self.cur_user_item.add_log_record(self.log_start_time, self.cur_user_log)

            self.script_info.log = "正在启动游戏..."
            account_switch_method = self._account_switch_method()
            use_mas_account_switch = account_switch_method == "MAS"
            cloud_adb = str(self.script_config.Game.ControllerType) == "CloudADB"
            if cloud_adb and str(self.cur_user_config.Info.Id).strip():
                self.retryable = False
                await self.handle_pre_maaend_error(
                    "云终末地暂不支持自动切号，请清空账号并先登录游戏",
                    kill_game=False,
                )
                break
            # 三种 PC 启动方式均由 MAS 编排，游戏就绪后再进入账号切换与任务。
            try:
                if self.emulator_manager is None:
                    await self.set_maaend(None)
                    await self._start_game(
                        preserve_running_game=keep_game_for_login_retry
                    )
                else:
                    logger.info(f"启动模拟器: {self.script_config.Game.EmulatorIndex}")
                    self.emulator_info = await self.emulator_manager.open(
                        self.script_config.Game.EmulatorIndex,
                        "" if cloud_adb else "com.hypergryph.endfield",
                    )
            except Exception as e:
                # 启动阶段失败后游戏状态不再可信：清除保留标记，避免下一轮
                # 启动沿用 preserve_running_game 跳过启动器游戏设置
                keep_game_for_login_retry = False
                await self.handle_pre_maaend_error(
                    "游戏启动失败"
                    if self.emulator_manager is None
                    else "模拟器启动失败",
                    e,
                )
                continue

            account_id = str(self.cur_user_config.Info.Id).strip()
            if use_mas_account_switch and account_id:
                from .tools.login import LoginNotReadyError, login

                try:
                    self.script_info.log = "正在由 MAS 自建流程切换账号..."
                    await login(
                        account_id,
                        self.emulator_info,
                        restart_game=self._restart_game_after_update,
                        on_error_screenshot=self._record_error_screenshot,
                    )
                except Exception as error:
                    keep_game_for_login_retry = (
                        isinstance(error, LoginNotReadyError) and i < run_times_limit
                    )
                    await self.handle_pre_maaend_error(
                        "MAS 自建账号切换失败",
                        error,
                        kill_game=not keep_game_for_login_retry,
                    )
                    continue
                keep_game_for_login_retry = False
                logger.info(f"用户 {self.cur_user_item.user_id} MAS 自建账号切换成功")
                self.script_info.log = "MAS 自建账号切换完成"
            elif account_id:
                logger.info(
                    f"用户 {self.cur_user_item.user_id} 将由 MAAEND 内置任务切换账号"
                )
                self.script_info.log = "游戏已启动，等待 MaaEnd 执行账号切换"
            else:
                logger.info(
                    f"用户 {self.cur_user_item.user_id} 未配置账号，跳过账号切换"
                )
                self.script_info.log = (
                    "等待 MaaEnd 启动游戏"
                    if cloud_adb
                    else "游戏已启动，未配置账号，跳过账号切换"
                )

            if self.emulator_manager is not None:
                await self.set_maaend(self.emulator_info)

            if not any(
                any(tasks.values())
                for name, tasks in self.task_dict.items()
                if not cloud_adb
                or self.task_name_map.get(name) != _MAAEND_ANDROID_OPEN_GAME_TASK
            ):
                self.retryable = False
                await self.handle_pre_maaend_error(
                    "MaaEnd 没有可执行任务，请检查任务配置"
                )
                break

            logger.info(f"运行脚本任务: {self.maaend_exe_path}")
            # 下载与首阶段任务并行，阶段结束后才按需插入更新。
            stage_log_offsets = await asyncio.to_thread(
                snapshot_mxu_logs, self.maaend_root_path
            )
            update_log_offsets = (
                stage_log_offsets if self.mode == self.first_run_mode else None
            )
            self.wait_event.clear()
            await self.maaend_process_manager.open_process(
                self.maaend_exe_path,
                "--autostart",
                "--instance",
                self.maaend_instance_name,
                "--quit-after-run",
                stdout=asyncio.subprocess.PIPE,
            )
            # 只有进程真的起来了才算一次 MXU 启动；否则 debug/ 里还是上一轮的残留。
            self._mxu_launch_count += 1
            await asyncio.sleep(3)  # 等待 MaaEnd 启动完成
            # 静默模式隐藏 MaaEnd 窗口
            if Config.setting.Function.IfSilence:
                if await self.maaend_process_manager.minimize_window():
                    logger.success("静默模式: 成功隐藏 MaaEnd 窗口")
                else:
                    logger.warning("静默模式: 隐藏 MaaEnd 窗口失败")
            await asyncio.sleep(1)
            await self._wait_maaend_stage(stage_log_offsets)

            # 先保存首阶段结果，更新失败或取消不能抹掉已经完成的任务。
            if self.cur_user_log.status == "Success!":
                self.run_book[self.mode] = True
            else:
                # 更新接管和失败清理都可能结束游戏，先保留这次尝试的现场。
                await self._take_failure_shot()
            if update_log_offsets is not None:
                await self._update_after_first_stage(
                    update_log_offsets, stage_label=stage_label
                )

            if self.cur_user_log.status == "Success!":
                self.script_info.log = (
                    f"检测到 MaaEnd 完成{stage_label}任务\n正在等待相关程序结束"
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

                # MXU 已退出，这次尝试的现场要赶在更新接管或下一次重试启动 MXU
                # 之前取证，因为 MXU 一启动就会清空 debug/。
                await self._archive_failure_logs(
                    label=f"{stage_label}阶段第 {i} 次尝试"
                )

                try:
                    await Notify.send_notice(
                        LocalNotice(
                            title="用户自动代理出现异常！",
                            message=f"用户 {self.cur_user_item.name} 的自动代理出现一次异常",
                            ticker=f"{self.cur_user_item.name}的自动代理出现异常",
                            duration_seconds=3,
                        )
                    )
                except Exception:
                    pass

                if not self.retryable:
                    logger.info("检测到不可恢复的错误，跳过后续重试")
                    i = run_times_limit

    async def handle_pre_maaend_error(
        self, error_message: str, e: Exception | None = None, *, kill_game: bool = True
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

        await self._take_failure_shot()
        await self.kill_managed_process(kill_game=kill_game)

        try:
            await Notify.send_notice(
                LocalNotice(
                    title="用户自动代理出现异常！",
                    message=f"用户 {self.cur_user_item.name} 自动代理时{error_message}",
                    ticker=f"{self.cur_user_item.name}的自动代理出现异常",
                    duration_seconds=3,
                )
            )
        except Exception:
            pass

    async def kill_managed_process(self, kill_game: bool = True) -> None:
        """中止关联进程

        Args:
            kill_game (bool): 是否同时关闭游戏或模拟器；等待登录画面超时后
                重试时传 False，保留游戏进度。
        """

        try:
            logger.info(f"中止 MaaEnd 进程: {self.maaend_exe_path}")
            await self.maaend_process_manager.kill()
            await System.kill_process(self.maaend_exe_path)
        except Exception as e:
            logger.opt(exception=True).warning(f"中止 MaaEnd 进程失败: {e}")
        if not kill_game:
            logger.info("保留游戏进程及当前启动进度")
            # 保留承载游戏的启动器，避免清理进程树时连带结束游戏。
            return
        await self.kill_game_process()

    async def kill_game_process(self) -> None:
        """关闭游戏或模拟器进程（Win32 为终末地客户端，Adb 为模拟器）"""

        if self.emulator_manager is None:
            async with _LAUNCHER_AUTOMATION_LOCK:
                if (
                    self.launcher_runtime_path is not None
                    and _LAUNCHER_OWNERS.get(self.launcher_runtime_path)
                    is not self.launcher_owner
                    or self.launcher_runtime_path is None
                    and self._launch_mode() != "MaaEnd"
                ):
                    logger.info("启动器已由其他会话接管或尚未启动，跳过旧会话清理")
                    return
                await self._kill_game_process_unlocked()
            return
        await self._kill_game_process_unlocked()

    async def _kill_game_process_unlocked(self) -> None:
        """执行进程清理；启动器模式由调用方持锁并确认会话归属。"""

        if self.emulator_manager is None:
            logger.info("中止终末地进程")
            try:
                await self.game_process_manager.kill()
            except Exception as error:
                logger.opt(exception=True).warning(f"终末地进程管理器清理失败: {error}")
            try:
                await System.kill_process(self.script_config.Game.Path)
            except Exception as error:
                logger.opt(exception=True).warning(f"关闭终末地客户端失败: {error}")
            await self._kill_launcher_process()
        else:
            try:
                logger.info("中止模拟器进程")
                await close_emulator(
                    self,
                    index=self.script_config.Game.EmulatorIndex,
                )
            except Exception as e:
                logger.opt(exception=True).warning(f"关闭模拟器失败: {e}")

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
        path = str(script_config.Info.Path or "").strip()
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
            "id": f"automas-{task_name.lower()}",
            "taskName": task_name,
            "enabled": False,
            "enabledByController": {str(self.script_config.Game.ControllerType): True},
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
                "caseName": "UseMedication"
                if self.cur_user_config.Task.IfAutoUseSpMedication
                else "EndTask",
            }

        # 旧版曾把该字段写入任务选项；清掉后避免新版把它当成未知选项。
        option_values.pop("AutoEssenceSpecifiedLocation", None)

    def _configure_resolution_restore(
        self, tasks: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        """仅在最后一个实际阶段，通过 MaaEnd 关闭游戏任务恢复分辨率。"""
        resolution = self.script_config.Game.RestoreResolution
        if (
            not resolution
            or resolution == "Off"
            or (not self.script_config.Game.CloseOnFinish)
            or (self.emulator_manager is not None)
        ):
            return None
        original = (
            self._read_original_game_settings() if resolution == "Original" else None
        )
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
        if resolution == "Original" and original is None:
            logger.warning("无法读取启动前的终末地注册表显示设置，本轮跳过关闭时恢复")
            for task in close_tasks:
                task.setdefault("optionValues", {})["CloseGamePCApplyGameSetting"] = {
                    "type": "switch",
                    "value": False,
                }
            return None
        required_options = (
            "CloseGamePCApplyGameSetting",
            "CloseGamePCGameSettingDisplayType",
            "CloseGamePCGameSettingResolution",
        )
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
                    str(self.script_config.Game.ControllerType): True
                },
                "optionValues": {},
            }
        )
        tasks[:] = [task for task in tasks if task.get("taskName") != "CloseGamePC"]
        close_task["enabled"] = True
        close_task.setdefault("enabledByController", {})[
            str(self.script_config.Game.ControllerType)
        ] = True
        tasks.append(close_task)
        display_type = (
            original[2]
            if original is not None
            else str(self.script_config.Game.RestoreDisplayType or "Window")
        )
        if display_type not in {"Window", "Fullscreen"}:
            display_type = "Window"
        if resolution == "Original":
            assert original is not None
            width, height = str(original[0]), str(original[1])
        elif resolution == "Custom":
            width = str(self.script_config.Game.RestoreResolutionWidth)
            height = str(self.script_config.Game.RestoreResolutionHeight)
        else:
            width, height = resolution.split("x")
        values = close_task.setdefault("optionValues", {})
        values["CloseGamePCApplyGameSetting"] = {"type": "switch", "value": True}
        values["CloseGamePCGameSettingDisplayType"] = {
            "type": "select",
            "caseName": display_type,
        }
        values["CloseGamePCGameSettingResolution"] = {
            "type": "input",
            "values": {
                "CloseGamePCGameSettingResolutionWidth": width,
                "CloseGamePCGameSettingResolutionHeight": height,
            },
        }
        return close_task

    def _read_original_game_settings(self) -> tuple[int, int, str] | None:
        """读取并缓存本轮启动前的注册表分辨率和显示模式。"""

        if self.original_game_settings_read:
            return self.original_game_settings
        self.original_game_settings_read = True

        from app.task.MaaFW.tools.embedded.game_resolution import (
            read_unity_display_type,
            read_unity_resolution,
        )

        game_path = str(self.script_config.Game.Path or "").strip()
        if not game_path:
            return None
        exe_path = Path(game_path)
        resolution = read_unity_resolution(exe_path)
        display_type = read_unity_display_type(
            exe_path, preferred_value_name="video_full_screen_h1998742411"
        )
        if resolution is not None and display_type is not None:
            self.original_game_settings = (*resolution, display_type)
        return self.original_game_settings

    async def set_maaend(self, device_info: DeviceInfo | None) -> None:
        """写入 MaaEnd 运行前配置"""

        logger.info("开始配置 MaaEnd 运行参数: 自动代理")

        # 配置前关闭可能未正常退出的脚本进程
        await self.maaend_process_manager.kill()
        await System.kill_process(self.maaend_exe_path)

        maaend_local_config = None
        if (self.maaend_set_path / "mxu-MaaEnd.json").exists():
            maaend_local_config = _utils_io.read_file(
                self.maaend_set_path / "mxu-MaaEnd.json"
            )

        config_base = maaend_config_base(self.cur_user_config.Info.Base)
        maaend_config_path = (
            Path.cwd() / f"data/{self.script_info.script_id}/Temp"
            if config_base == CONFIG_BASE_NATIVE
            else maaend_mas_config_dir(
                self.script_info.script_id,
                str(self.cur_user_uid),
                config_base,
            )
        )
        maaend_config_file = maaend_config_path / "mxu-MaaEnd.json"
        if not maaend_config_file.exists():
            raise FileNotFoundError(
                "未找到 MaaEnd 配置文件, 请先完成「MaaEnd 配置」步骤"
            )

        # 下发前归档 MAS 配置到用户池（下发源；带快速配置覆盖层字段侧车，
        # 指纹去重，失败不阻断运行）。原生来源无 MAS 配置目录，不归档；native
        # 池由 manager.prepare 在任务级一次性归档
        if config_base != CONFIG_BASE_NATIVE:
            archive_mas_runtime_backup(
                self.script_info.script_id,
                str(self.cur_user_uid),
                maaend_config_path,
                overlay=read_overlay_values(self.cur_user_config),
                # 备份标注来源：tri_state 池跨来源恢复靠它切回
                base=config_base,
            )

        _utils_io.swap_in_dir(maaend_config_path, self.maaend_set_path)
        _utils_io.mark_native_config_injected(
            Path.cwd() / f"data/{self.script_info.script_id}/Temp",
            self.maaend_set_path,
            script_id=self.script_info.script_id,
        )
        maaend_set = _utils_io.read_file(self.maaend_set_path / "mxu-MaaEnd.json")
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
        if_quick_config = self.cur_user_config.Info.IfQuickConfig
        if if_quick_config:
            self._drop_removed_medication_task(maaend_tasks)

        account_id = str(self.cur_user_config.Info.Id).strip()
        if if_quick_config or account_id:
            replace_account_switch_task(
                tasks=maaend_tasks,
                account_id=account_id
                if self._account_switch_method() == "MAAEND"
                else "",
                controller_type=str(self.script_config.Game.ControllerType),
                task_id=f"mas{self.cur_user_uid.hex[:4]}",
            )

        cloud_launch_task = None
        if (
            device_info is not None
            and str(self.script_config.Game.ControllerType) == "CloudADB"
        ):
            maaend_instance["controllerName"] = "CloudADB"
            if self._maaend_task_supported(_MAAEND_ANDROID_OPEN_GAME_TASK) is not True:
                raise ValueError("当前 MaaEnd 不支持安卓启动游戏任务，请更新 MaaEnd")
            # 游戏启动由上游任务完成，其选项决定客户端；先于账号切换执行。
            cloud_launch_task = _place_managed_task(
                maaend_tasks,
                task_name=_MAAEND_ANDROID_OPEN_GAME_TASK,
                task_id="automas-android-open-game",
                controller_type="CloudADB",
                enabled=True,
                first=True,
            )

        if self.emulator_manager is None:
            controller_type = str(self.script_config.Game.ControllerType)
            setting_pretask = self._game_setting_pretask()
            if setting_pretask is not None:
                apply_settings = self.mode == self.first_run_mode and bool(
                    self.script_config.Game.SetResolution
                )
                # 保存的配置可能早于当前资源；先补齐入口，再覆写本轮托管开关。
                _place_managed_task(
                    maaend_tasks,
                    task_name=setting_pretask,
                    task_id=(
                        "automas-launch-game"
                        if setting_pretask == _MAAEND_LAUNCH_GAME_PRETASK
                        else "automas-gamesetting"
                    ),
                    controller_type=controller_type,
                    enabled=False,
                    first=True,
                )
                for task in maaend_tasks:
                    if task["taskName"] == _MAAEND_LAUNCH_GAME_PRETASK:
                        task["optionValues"]["LaunchGamePCGameSetting"] = {
                            "type": "switch",
                            "value": apply_settings,
                        }
                    if task["taskName"] == setting_pretask:
                        self.launcher_game_setting_options = task["optionValues"]
            # 上游预任务在 MXU 外按所选方式执行；保存的其他版本入口也必须禁用。
            for task in maaend_tasks:
                if task["taskName"] in {
                    _MAAEND_GAME_SETTING_PRETASK,
                    _MAAEND_LAUNCH_GAME_PRETASK,
                }:
                    task["enabled"] = False
            self.game_launch_result_path.unlink(missing_ok=True)
            _configure_game_pre_action(
                maaend_instance,
                launcher_path=self._launcher_path_text(),
                game_path=str(self.script_config.Game.Path),
                game_arguments=str(self.script_config.Game.Arguments),
                result_path=self.game_launch_result_path,
                enabled=False,
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
        self.inventory_status_messages.update(
            re.sub(r"<[^>]*>", "", message).strip()
            for key, message in maaend_interface_i18n.items()
            if key.startswith("task.ProtocolSpace.focus.supply_plan.")
        )
        self.account_switch_task_name = maaend_i18n["AccountSwitch"]
        self.color_match_failed_message = maaend_interface_i18n[
            "task.SceneManager.focus.color_match_failed_prefix"
        ]

        removed_task_names = (
            _disable_removed_tasks(maaend_tasks, maaend_i18n)
            if if_quick_config
            else set()
        )

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
        native_sanity = self.cur_user_config.Info.SanityStrategy == "Native"
        inventory_sanity = self.cur_user_config.Info.SanityStrategy == "Inventory"
        if if_quick_config and not native_sanity:
            target_task_name = "ProtocolSpace"
            if not inventory_sanity:
                sanity_task_key, _ = (
                    self.cur_user_config.get_effective_sanity_task_key()
                )
                sanity_task_type = sanity_task_key["SanityTaskType"]
                target_task_name = (
                    "AutoEssence" if sanity_task_type == "Essence" else "ProtocolSpace"
                )
            if self.cur_user_config.Task.IfSanity:
                self._ensure_sanity_task(maaend_tasks, target_task_name)

        # 补齐业务任务后再放置关闭游戏任务，避免理智任务落到关游戏之后。
        if self.emulator_manager is None:
            remaining_modes = list(MAAEND_RUN_MOOD_BOOK)[
                list(MAAEND_RUN_MOOD_BOOK).index(self.mode) + 1 :
            ]
            has_later_mode = any(not self.run_book[mode] for mode in remaining_modes)
            close_after_mode = (
                has_later_mode
                and self.script_config.Run.TaskTransitionMethod == "ExitGame"
                or (not has_later_mode and self.script_config.Game.CloseOnFinish)
            )
            if if_quick_config or close_after_mode:
                _place_managed_task(
                    maaend_tasks,
                    task_name=_MAAEND_CLOSE_GAME_TASK,
                    task_id="automas-close-game",
                    controller_type=str(self.script_config.Game.ControllerType),
                    enabled=close_after_mode,
                    first=False,
                )

        restore_task = self._configure_resolution_restore(maaend_tasks)

        if self.task_dict is None:
            # 首次运行时按 MAS 配置生成本轮任务表，后续重试只收束这张表
            self.task_dict = {}
            self.task_name_map = {}
            sanity_configured = False
            sanity_switch_enabled = (
                if_quick_config and self.cur_user_config.Task.IfSanity
            )
            target_sanity_task_exists = any(
                (
                    task.get("taskName") in _MAAEND_SANITY_TASK_NAMES
                    and task.get("enabled", False)
                    if native_sanity
                    else task.get("taskName") == target_task_name
                )
                for task in maaend_tasks
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
                        if native_sanity:
                            # 原生策略沿用已选任务，MAS 理智开关只控制整组是否运行。
                            task_enabled = task_enabled and sanity_switch_enabled
                        elif sanity_managed:
                            task_enabled = (
                                sanity_switch_enabled
                                and task_name_value == target_task_name
                                and not sanity_configured
                            )
                            if task_enabled:
                                sanity_configured = True
                    elif task_name_value == MAAEND_DELIVERY_TASK:
                        task_enabled = getattr(
                            self.cur_user_config.Task, f"If{MAAEND_DELIVERY_TASK}"
                        )
                    elif task_name_value == MAAEND_AUTO_COLLECT_TASK:
                        task_enabled = bool(
                            self.cur_user_config.Task.IfAutoCollect
                            and any(self.auto_collect_routes.values())
                        )
                    elif task_name_value in MAAEND_TASKS:
                        task_enabled = getattr(
                            self.cur_user_config.Task, f"If{task_name_value}"
                        )

                if if_quick_config:
                    task_enabled = _task_enabled_for_mode(
                        task_name_value, task_enabled, self.mode
                    )
                if (
                    task_name_value == _MAAEND_ACCOUNT_SWITCH_TASK
                    and self.mode != self.first_run_mode
                ):
                    task_enabled = False

                if if_quick_config and self._daily_once_task_done(task_name_value):
                    task_enabled = False

                task_name = get_task_book_name(task)
                self.task_name_map[task_name] = task_name_value
                if task_name not in self.task_dict:
                    self.task_dict[task_name] = {}
                self.task_dict[task_name][task["id"]] = task_enabled

            if sanity_missing:
                warning_message = (
                    f"用户 {self.cur_user_item.name} 未在 MaaEnd 配置中启用理智任务，"
                    "请在「配置库存目标」中启用协议空间或基质刷取"
                    if native_sanity
                    else f"用户 {self.cur_user_item.name} 当前 MaaEnd 配置中缺少 {target_task_name} 任务，"
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
            # 进程由 MAS 统一收尾，禁用 MXU 的结束进程任务。
            if task_name_value == "__MXU_KILLPROC__":
                task["enabled"] = False
            if task_name_value.startswith("__MXU_"):
                continue

            task_name = get_task_book_name(task)
            if str(task.get("taskName")) in removed_task_names:
                task["enabled"] = False
                if task_name in self.task_dict:
                    self.task_dict[task_name].pop(task["id"], None)
                continue

            if task_name_value != _MAAEND_CLOSE_GAME_TASK:
                task["enabled"] = self.task_dict.get(task_name, {}).get(
                    task["id"], False
                )

            if restore_task is task:
                # 独立送货/采集阶段也须在末尾执行恢复；重试时同样不能漏掉。
                task["enabled"] = True
                self.task_dict.setdefault(task_name, {})[task["id"]] = True
                self.task_name_map[task_name] = task_name_value

            if cloud_launch_task is task:
                # 模拟器可能在失败重试后重启，每轮都交由上游重新启动游戏。
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
                        "Reward": str(self.cur_user_config.Task.SeizeDeliveryJobsReward)
                    },
                }
                task["optionValues"]["SeizeDeliveryJobsCommissionSource"] = {
                    "type": "select",
                    "caseName": self.cur_user_config.Task.SeizeDeliveryJobsCommissionSource,
                }
            elif if_quick_config and task_name_value == MAAEND_AUTO_COLLECT_TASK:
                MaaEndResourceLoader.get_loaded(
                    self.maaend_root_path
                ).write_auto_collect_options(task, self.auto_collect_routes)
            elif (
                if_quick_config
                and inventory_sanity
                and task_name_value == "ProtocolSpace"
            ):
                MaaEndResourceLoader.get_loaded(
                    self.maaend_root_path
                ).write_inventory_options(
                    task=task,
                    limits=self.cur_user_config.Task.SupplyPlanLimits,
                    claim_mode=self.cur_user_config.Task.ProtocolSpaceObtainModeClaim,
                    use_medication=self.cur_user_config.Task.IfAutoUseSpMedication,
                )
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
                if sanity_task_type == "CrisisDrills":
                    MaaEndResourceLoader.get_loaded(
                        self.maaend_root_path
                    ).validate_crisis_drills(sanity_task_key["CrisisDrills"])
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
                        "caseName": "UseMedication"
                        if self.cur_user_config.Task.IfAutoUseSpMedication
                        else "EndTask",
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

        # 原生 CDK（含 MXU 加密值）优先；全局 CDK 仅作运行期补充，
        # 随 manager 的原生配置快照恢复，不写回脚本或用户配置来源。
        global_cdk = str(Config.setting.Update.MirrorChyanCDK or "").strip()
        if global_cdk:
            mirror_settings = settings.get("mirrorChyan")
            if mirror_settings is None:
                mirror_settings = {}
                settings["mirrorChyan"] = mirror_settings
            if not isinstance(mirror_settings, dict):
                raise ValueError("MaaEnd 镜像更新配置不是有效对象")
            if not any(
                str(mirror_settings.get(key) or "").strip()
                for key in ("cdk", "cdkEncrypted")
            ):
                mirror_settings["cdk"] = global_cdk

        # 失败日志包的取证时机取决于 MXU 是否每次启动都清空 debug/：要保存日志包时
        # 强制打开「启动时清理日志」，一次尝试的现场就只有这一轮。打包失败过则反过来
        # 强制关闭，宁可下一轮日志混一点，也要保住还没保存成功的现场。同样随 manager
        # 的原生配置快照恢复，不写回脚本或用户配置来源。
        if self.script_config.Run.IfSaveLogBundle:
            settings["autoClearLogsOnLaunch"] = not self._bundle_failed

        _utils_io.write_file(self.maaend_set_path / "mxu-MaaEnd.json", maaend_set)
        _utils_io.mark_native_config_injected(
            Path.cwd() / f"data/{self.script_info.script_id}/Temp",
            self.maaend_set_path,
            script_id=self.script_info.script_id,
        )
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
            # MXU 现行文案为「没有可执行的任务」，与旧文案并列；不用公共前缀，
            # 避免误命中「没有可执行路径点」「没有可执行的子任务」等运行期文案
            for message in (
                "没有可以启动的任务",
                "没有启用的任务",
                "没有可执行任务",
                "没有可执行的任务",
            )
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

                    if self.cur_user_config.Info.IfQuickConfig:
                        await self._mark_daily_once_tasks_completed(
                            completed_task_names
                        )

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
            latest_time, minutes=self.script_config.Run.RunTimeLimit
        ):
            self.cur_user_log.status = "MaaEnd 进程超时"
        else:
            self.cur_user_log.status = "MaaEnd 正常运行中"

        logger.debug(f"MaaEnd 日志分析结果: {self.cur_user_log.status}")
        if self.cur_user_log.status != "MaaEnd 正常运行中":
            logger.info(f"MaaEnd 任务结果: {self.cur_user_log.status}, 日志锁已释放")
            self.wait_event.set()

    def _record_error_screenshot(self, path: Path) -> None:
        self._attempt_screenshot_paths.append(path)
        if self.on_error_screenshot is not None:
            self.on_error_screenshot(path)

    async def _failure_window_handle(self) -> int | None:
        """按终末地既有主窗口标识确认目标，不把同进程弹窗计为另一个游戏。"""
        import psutil
        import win32gui
        import win32process

        game_path = Path(str(self.script_config.Game.Path or ""))

        def find() -> int | None:
            expected_path = game_path.resolve()
            if not expected_path.is_file():
                return None
            candidates: list[tuple[int, psutil.Process]] = []

            def collect(hwnd: int, _: int) -> bool:
                try:
                    if (
                        not win32gui.IsWindowVisible(hwnd)
                        or win32gui.GetClassName(hwnd) != "UnityWndClass"
                        or win32gui.GetWindowText(hwnd) != "Endfield"
                    ):
                        return True
                    _, pid = win32process.GetWindowThreadProcessId(hwnd)
                    process = psutil.Process(pid)
                    if Path(process.exe()).resolve() != expected_path:
                        return True
                    left, top, right, bottom = win32gui.GetClientRect(hwnd)
                    if right > left and bottom > top:
                        candidates.append((hwnd, process))
                except (OSError, psutil.Error):
                    pass
                return True

            win32gui.EnumWindows(collect, 0)
            if len(candidates) != 1:
                return None
            hwnd, process = candidates[0]
            if (
                not process.is_running()
                or not win32gui.IsWindow(hwnd)
                or win32process.GetWindowThreadProcessId(hwnd)[1] != process.pid
                or Path(process.exe()).resolve() != expected_path
            ):
                return None
            return hwnd

        return await asyncio.to_thread(find)

    async def _capture_failure_shot(self) -> Path | None:
        if self._attempt_start_ns is None:
            return None
        existing = await asyncio.to_thread(
            _format_maaend.collect_recent_error_images,
            self.maaend_root_path,
            started_at_ns=self._attempt_start_ns,
            ended_at_ns=time_ns(),
            diagnostic_paths=tuple(self._attempt_screenshot_paths),
        )
        if existing:
            return None

        if self.emulator_manager is None:
            hwnd = await self._failure_window_handle()
            if hwnd is None:
                return None
            image = await self.capture_win32(hwnd)
        else:
            if self.emulator_info is None:
                return None
            index = self.script_config.Game.EmulatorIndex
            host_adb = await resolve_host_adb(self, index=index)
            if host_adb is not None:
                from PIL import Image

                data = await host_adb.screencap_png()
                with Image.open(io.BytesIO(data)) as source:
                    image = source.convert("RGB")
            else:
                device_ref = resolve_device_ref(self.emulator_manager, index)
                if device_ref is not None and device_ref.emulator_type == "avd":
                    # 私有通道不可用时不能回落到共享 ADB server。
                    return None
                adb_path = self.emulator_manager.get_adb_path()
                if not adb_path:
                    return None
                image = await self.capture_adb(adb_path, self.emulator_info.adb_address)
        # 此后同步保存并回调，避免取消后后台保存线程交回迟到的图片。
        return self._failure_capture.save(image, dir_name="maaend-failure")

    async def _take_failure_shot(self) -> None:
        shot = await self._failure_capture.run(self._capture_failure_shot, once=True)
        if shot is not None:
            self._record_error_screenshot(shot)

    async def _archive_failure_logs(self, *, label: str) -> bool:
        """在 MXU 退出后、下次启动清日志前归档；重复调用等待同一作业。

        返回 False 表示现场未完整保存，后续会话必须关闭启动清理。
        取消只能停止等待，后台线程由收尾继续等待，不能提前清掉现场。
        """

        if not self.script_config.Run.IfSaveLogBundle:
            return True
        target_dir = self.script_config.Run.LogBundlePath or Path.cwd() / "debug/maaend"
        root_path = self.maaend_root_path
        if root_path is None:
            return True
        if self._bundle_job is None:
            if self._archived_launch_count >= self._mxu_launch_count:
                return True
            self._bundle_job = asyncio.create_task(
                self._run_bundle_job(
                    Path(target_dir),
                    root_path,
                    label=label,
                    launches=self._mxu_launch_count,
                )
            )
        job = self._bundle_job
        try:
            return await asyncio.shield(job)
        except Exception:
            return False  # 作业内部已记过日志
        finally:
            if job.done():
                self._bundle_job = None

    async def _run_bundle_job(
        self,
        target_dir: Path,
        root_path: Path,
        *,
        label: str,
        launches: int,
    ) -> bool:
        """打包作业本体：一次现场一份日志包，规则同 MXU 的日志导出。

        Returns:
            bool: 现场是否已经安全落盘。
        """

        try:
            export = await asyncio.to_thread(export_failure_logs, target_dir, root_path)
        except Exception as error:
            self._bundle_failed = True
            logger.opt(exception=True).warning(f"保存 MaaEnd 失败日志包失败: {error}")
            return False
        if export is None:
            # 这份现场确实没有可打包的内容，反复重试没有意义，记下已归档。
            self._archived_launch_count = launches
            logger.warning(f"MaaEnd {label}失败日志包没有可打包的内容")
            return True
        if export.failed_files:
            # 部分文件读不到时拿到的只是残缺包，不能当成「现场已保存」：既不消费这次
            # 待归档现场（收尾还能再取一次，把当时读不到的文件补进去），也让本轮后续
            # 启动不再清日志，免得漏包文件在安装目录里的唯一一份被删掉。
            self._bundle_failed = True
            message = (
                f"MaaEnd {label}失败日志包不完整: {export.directory}"
                f"（{len(export.volumes)} 卷，{export.failed_files} 个文件未能写入，"
                "本轮后续启动不再清理日志）"
            )
            logger.warning(message)
            await push_dispatch_log(self.script_info, message)
            return False
        self._archived_launch_count = launches
        message = (
            f"MaaEnd {label}失败日志包已保存: {export.directory}"
            f"（{len(export.volumes)} 卷）"
        )
        logger.success(message)
        await push_dispatch_log(self.script_info, message)
        return True

    async def final_task(self):

        if self.check_result != "Pass":
            return

        self.task_info.begin_user_history_capture(
            self.script_info,
            self.cur_user_item,
            failed=bool(self.cur_user_item.log_record)
            and not (all(self.run_book.values()) and not self.update_failed)
            and not self.stopped_manually,
        )

        completed = all(self.run_book.values()) and not self.update_failed
        await self.maaend_log_monitor.stop()
        if not completed:
            # 总时限或异常可能绕过主循环失败分支；必须赶在关游戏/模拟器之前。
            await self._take_failure_shot()
        if (
            self.script_info.current_index == len(self.script_info.user_list) - 1
            and completed
            and (not self.script_config.Game.CloseOnFinish)
        ):
            try:
                logger.info(f"中止 MaaEnd 进程: {self.maaend_exe_path}")
                await self.maaend_process_manager.kill()
                await System.kill_process(self.maaend_exe_path)
            except Exception as e:
                logger.opt(exception=True).warning(f"中止 MaaEnd 进程失败: {e}")
        else:
            # 开发与生产使用一致的停止清理流程，便于实机验证。
            await self.kill_managed_process(kill_game=True)

        # 失败日志包：主循环的失败分支已按尝试取证，这里补总时限、异常和更新会话这几条
        # 绕过主循环的收尾。必须排在后置脚本之前，脚本可能改动或删掉 debug/ 里的现场。
        if not completed:
            await self._archive_failure_logs(label="本轮")

        await self.run_user_scripts_after()

        history_records = []
        stage_log_paths = []
        stage_directory = None
        inventory_notify = (
            self.cur_user_config.Notify.Enabled
            and self.cur_user_config.Notify.IfSendInventory
        )
        if self.push_log_enabled or inventory_notify:
            try:
                stage_directory = tempfile.TemporaryDirectory(
                    prefix="mas-maaend-stage-"
                )
            except OSError as error:
                logger.warning(f"创建 MaaEnd 节点临时日志目录失败：{error}")
        for index, (t, log_item) in enumerate(self.cur_user_item.iter_history_logs()):
            if log_item.status == "MaaEnd 正常运行中" or (
                self.stopped_manually
                and log_item is self.cur_user_log
                and log_item.status == "未开始监看日志"
            ):
                log_item.status = "任务被用户手动中止"
            was_cancelled = (
                self.stopped_manually
                and log_item is self.cur_user_log
                and log_item.status == "任务被用户手动中止"
            ) or (log_item.phase == "Update" and log_item.status == "MaaEnd 更新被中止")
            was_skipped = log_item.phase == "Update" and log_item.status == "跳过更新"
            if not log_item.content:
                log_item.content = ["未捕获到任何日志内容"]
                if not was_cancelled and not was_skipped:
                    log_item.status = "未捕获到日志"
            data = {}
            message = log_item.status
            try:
                parsed = parse_maaend_statistics(log_item.content)
                data = {
                    key: {
                        "kind": (
                            "keyed_snapshot"
                            if key == "matrix_statistics"
                            else "snapshot"
                        ),
                        "value": value,
                    }
                    for key, value in parsed.items()
                }
                failed_tasks = parse_maaend_failed_tasks(log_item.content)
                if message == "MaaEnd 部分任务执行失败" and failed_tasks:
                    message += f": {'、'.join(failed_tasks)}"
            except Exception as error:
                diagnostic = f"MaaEnd 统计解析失败：{error}"
                logger.opt(exception=True).warning(diagnostic)
                log_item.content.append(f"\n{diagnostic}\n")
            phase = (
                "更新"
                if log_item.phase == "Update"
                else MAAEND_RUN_MOOD_BOOK.get(log_item.phase, "")
            )
            if phase:
                message = f"[{phase}] {message}"
            record = HistoryWrite(
                time=t.astimezone(UTC4),
                username=self.cur_user_item.name,
                script_name=self.script_info.name,
                status="success"
                if log_item.status == "Success!"
                else "cancelled"
                if was_cancelled
                else "skipped"
                if was_skipped
                else "error",
                message=message,
                logs="".join(log_item.content),
                data=data,
            )
            history_records.append(record)
            if stage_directory is not None:
                log_path = Path(stage_directory.name) / f"{index}.log"
                try:
                    await asyncio.to_thread(
                        log_path.write_text, record.logs, encoding="utf-8"
                    )
                    stage_log_paths.append(log_path)
                except OSError as error:
                    diagnostic = f"写入 MaaEnd 节点临时日志失败：{error}"
                    logger.warning(diagnostic)
                    record.logs += f"\n{diagnostic}\n"

        # ── log_box：节点采集推送（源 = 本次各阶段任务临时日志全文）──
        # MaaEnd 的任务级进度行只在 stdout，不落上游文件；任务临时日志即 stdout
        # 全文落盘产物，直接作为采集源（start_from_end=False 全文采集）。
        # 开关关闭时不创建采集会话；on_crash 后 final_task 仍会收尾落盘并
        # 采集，部分日志中的开始标记聚为失败节点；仅 check 未通过的提前返回
        # 场景无节点。
        if self.push_log_enabled and stage_log_paths:
            await self._append_stage_log_details(stage_log_paths)

        inventory_lines: list[str] = []
        if inventory_notify and stage_log_paths:
            try:
                report = InventoryReport(
                    task_names={
                        name
                        for name, task_name in self.task_name_map.items()
                        if task_name == "ProtocolSpace"
                    },
                    status_messages=self.inventory_status_messages,
                )

                def append_inventory(log_type: str, text: str, ts: float) -> None:
                    inventory_lines.append(
                        f"[{datetime.fromtimestamp(ts):%H:%M:%S}] {text}"
                    )
                    if self.push_log_enabled:
                        append_push_log(self.cur_user_item, log_type, text, ts)

                pipeline = log_box.LogPipeline()
                pipeline.preprocessors.append(report.select)
                pipeline.add_rule(*INVENTORY_REPORT_RULE)
                pipeline.postprocessors.append(inventory_resolve)
                for path in stage_log_paths:
                    source = log_source.LogSource(path, start_from_end=False)
                    source.open()
                    for line in source.read_new():
                        pipeline.feed(line, timestamp=time())
                for entry in pipeline.finish():
                    if entry.timestamp is None:
                        raise ValueError("材料状态报告缺少时间戳")
                    append_inventory(entry.log_type, entry.text, entry.timestamp)
            except Exception as e:
                logger.opt(exception=True).warning(f"MaaEnd 材料状态采集失败: {e}")

        if stage_directory is not None:
            try:
                stage_directory.cleanup()
            except OSError as error:
                logger.warning(f"清理 MaaEnd 节点临时日志失败：{error}")
        statistics = {
            key: value.value
            for key, value in aggregate_data(
                [
                    HistoryAggregationItem(time=record.time, data=record.data)
                    for record in history_records
                ]
            ).data.items()
        }
        statistics["inventory_report"] = inventory_lines
        statistics["user_info"] = self.cur_user_item.name
        statistics["start_time"] = self.user_start_time.strftime("%Y-%m-%d %H:%M:%S")
        statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        statistics["user_result"] = (
            "代理任务全部完成" if completed else self.cur_user_item.result
        )

        success_symbol = "√" if completed else "X"

        if inventory_notify and history_records:
            try:
                await Notify.send_user(
                    payload=_format_maaend.build_inventory_payload(
                        title=f"{datetime.now():%m-%d} | {self.cur_user_item.name} 的本轮材料收获",
                        message=statistics,
                    ),
                    user_config=self.cur_user_config,
                )
            except Exception as e:
                logger.opt(exception=True).warning(f"养成材料通知推送失败: {e}")

        if history_records:
            try:
                await Notify.push_statistics_report(
                    payload=_format_maaend.build_statistics_payload(
                        title=f"{datetime.now().strftime('%m-%d')} |{success_symbol}|  {self.cur_user_item.name} 的自动代理统计报告",
                        message=statistics,
                    ),
                    user_config=self.cur_user_config,
                    task_info=self.task_info,
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
        if completed:
            if (
                self.cur_user_config.Data.ProxyTimes == 0
                and self.cur_user_config.Info.RemainedDay != -1
            ):
                self.cur_user_config.Info.RemainedDay = (
                    self.cur_user_config.Info.RemainedDay - 1
                )
                await self.cur_user_config.commit()
            self.cur_user_config.Data.ProxyTimes = (
                self.cur_user_config.Data.ProxyTimes + 1
            )
            await self.cur_user_config.commit()
            self.cur_user_config.Data.LastProxyStatus = "成功"
            await self.cur_user_config.commit()
            self.cur_user_item.status = "完成"
            logger.success(f"用户 {self.cur_user_uid} 的自动代理任务已完成")
        else:
            self.cur_user_config.Data.LastProxyStatus = "失败"
            await self.cur_user_config.commit()
            logger.warning(f"用户 {self.cur_user_uid} 的自动代理任务未完成")
            self.cur_user_item.status = "异常"

        if history_records:
            await self.task_info.save_user_history(
                history_records,
                script=self.script_info,
                user=self.cur_user_item,
                log_warning=logger.opt(exception=True).warning,
            )

        if completed:
            await Notify.send_notice(
                LocalNotice(
                    title="成功完成一个自动代理任务！",
                    message=f"已完成用户 {self.cur_user_item.name} 的 MaaEnd 自动代理任务",
                    ticker=f"已完成 {self.cur_user_item.name} 的 MaaEnd 自动代理任务",
                    duration_seconds=3,
                )
            )

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        logger.opt(exception=True).warning(f"自动代理任务出现异常: {e}")
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"自动代理任务出现异常: {e}"),
        )

    async def _append_stage_log_details(self, paths: list[Path]) -> None:
        """阶段日志的读取、后台处理和用户交付归 MaaEnd 收尾流程。"""
        if not self.push_log_enabled or self.cur_user_item.push_log_mode == "关闭":
            return
        user = self.cur_user_item
        paths = list(paths)

        def read() -> list[log_box.LogEntry]:
            pipeline = log_box.LogPipeline()
            for rule in MAAEND_PUSH_RULES:
                pipeline.add_rule(*rule)
            pipeline.postprocessors.append(maaend_resolve)
            for path in paths:
                source = log_source.LogSource(path, start_from_end=False)
                source.open()
                for line in source.read_new():
                    pipeline.feed(line, timestamp=time())
            return pipeline.finish()

        async def deliver() -> None:
            try:
                entries = await asyncio.to_thread(read)
                for entry in entries:
                    user.push_log.append((entry.log_type, entry.text, entry.timestamp))
            except Exception:
                logger.opt(exception=True).warning("MaaEnd 节点采集推送失败")

        task = asyncio.create_task(deliver())
        cancelled = None
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError as error:
                cancelled = error
        task.result()
        if cancelled is not None:
            raise cancelled
