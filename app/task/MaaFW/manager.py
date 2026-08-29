"""MaaFW 第一层外部运行编排。

本模块只负责把 MAS 中保存的 MaaFW 选择转换为 MFAAvalonia 的运行实例，
启动外壳并通过日志判断一轮任务的终态。MaaFW 内核和外壳映射保持在
``tools/core``、``tools/external``，这里不嵌入第二层 runner。
"""

from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.core import Config, EmulatorManager
from app.models.ConfigBase import MultipleConfig
from app.models.config import MaaFWConfig, MaaFWUserConfig
from app.models.emulator import DeviceBase, DeviceInfo
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase, UserItem
from app.services import Notify, System
from app.utils.constants import TASK_MODE_ZH, UTC4
from app.task.MaaFW.tools.config_write_guard import (
    atomic_write_maafw_config,
    read_maafw_config_snapshot,
)
from app.task.MaaFW.tools.controller.game_lifecycle import (
    MaaFWGameLaunchSpec,
    MaaFWOwnedGameProcess,
    close_owned_game,
    find_client_process,
    wait_for_client,
    launch_game,
    resolve_game_launch_spec,
    snapshot_matching_processes,
    validate_game_launch_spec,
)
from app.task.MaaFW.tools.core.automas_maafw_interface import (
    build_task_alias_index,
    load_interface_model_cached,
    normalize_task_options_by_task,
)
from app.task.MaaFW.tools.core.automas_maafw_interface.models import (
    is_pretask_task_name,
)
from app.task.MaaFW.tools.external import (
    InstanceOrchestration,
    ShellFamily,
    ShellMappingError,
    TaskSelection,
    ShellLogProfile,
    append_instance,
    build_instance_config,
    build_instance_entry,
    build_option_entries,
    default_instance_id,
    detect_shell_family,
    get_shell_log_profile,
    pick_latest_mxu_log,
    resolve_controller_code,
    resolve_log_relpath,
)
from app.task.MaaFW.tools.notify import push_notification
from app.utils import (
    LogMonitor,
    ProcessManager,
    ProcessRunner,
    activate_window_by_pid,
    get_logger,
    has_visible_window,
)


logger = get_logger("MFW 外部调度器")

_LOG_TIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"
_COMPLETION_MARKERS = ("任务已全部完成！", "All tasks completed")
_ABANDON_MARKER = "已放弃本次任务"
# 外壳报告**某个任务**失败的串，与完成串是同一个 Monitor 组件的孪生输出
# （两者都带 [src=Monitor][op=MonitorLog]）。
#
# 它**不是终止信号**：队列会不会因此停下来，取决于实例配置的
# ContinueRunningWhenError——M9A 在该项为真时会跳过失败任务继续跑后面的。
# 因此本串只用来把本轮终态从 success 降为 failed，绝不用它提前收口，
# 否则队列还在跑就会被 MAS 判死。
#
# MAS 侧恒把 ContinueRunningWhenError 写成 True（见 InstanceOrchestration），
# 这样外壳一定会走到「队列排空」并输出完成串，判定有稳定的落点。
# 判别性：靶子 14 份真实日志里共出现 3 次，**全部**带 op=MonitorLog。
_FAILURE_MARKERS = ("任务运行失败！",)
_STATE_DIR_NAME = "MaaFWExternal"
# MAS 在 MXU 容器里追加的实例显示名；外壳的 -i 参数按**显示名**匹配，
# 两者必须一致。
# interface.json 里控制 MXU 自动更新的键。见 _disable_shell_self_update。
_INTERFACE_UPDATE_KEYS = ("mirrorchyan_rid",)
_MXU_INSTANCE_NAME = "MAS"
# 起进程后等外壳把日志文件建出来的上界与探测节奏。
_SHELL_LOG_WAIT_SECONDS = 30
_SHELL_LOG_PROBE_INTERVAL_SECONDS = 1.0
_GAME_READY_PROBE_INTERVAL_SECONDS = 1.0

# 交接给外壳前等 adb 真正可用的上界与探测节奏。模拟器管理器只保证
# ldconsole/MuMuManager 报 ONLINE，Android 的 adbd 可能还要十几秒才服务。
_ADB_READY_TIMEOUT_SECONDS = 60
_ADB_READY_PROBE_INTERVAL_SECONDS = 1.0
_ADB_READY_PROBE_TIMEOUT_SECONDS = 10

# 项目根 appsettings.json 中描述实例集合与活动实例的键（.NET 平铺写法）。
# MAS 运行期会删光 instances/*.json 只留自己那个，外壳退出时据此收缩这几项；
# 它们在备份范围（config/）之外，必须单独快照与还原。
_APPSETTINGS_INSTANCE_KEYS = (
    "Instances.List",
    "Instances.Order",
    "Instances.LastActive",
    "Instances.LastActiveName",
)

# 外壳在控制器初始化失败后仍会输出完成串——该串由 MFA 的 Monitor 组件在任务
# 队列排空时发出，语义是「没有待办了」，而非「任务都成功了」。实测：控制器初始化
# 失败 21 毫秒后即出现「任务已全部完成！」，紧随其后的耗时行为 (用时 0h 0m 0s)，
# 真正选中的任务从未执行。因此控制器初始化失败必须**压过**完成串。
#
# 只取带 op=ExecuteTaskQueue 的判别性标记；同一份日志里还有「获取设备唯一标识
# 失败」（24 次）、「跨平台数据解密失败」（14 次）等与运行结果无关的噪音，不能采用。
_CONTROLLER_FAILURE_MARKERS = (
    "初始化控制器失败",
    "控制器初始化结果为空",
)

# 终态优先级：数值越大越不可被覆盖。未列出的按 1 处理。
# controller_failed 与 tasks_missing 都表示「选中的任务并没有真正执行」，同级压过
# success；同级之间按现有约定先到的结论稳定。
_TERMINAL_PRIORITY = {
    "controller_failed": 3,
    "tasks_missing": 3,
    # 外壳报告有任务失败。与前两者同级、压过 success：队列排空后若日志里出现过
    # 失败串，本轮就不是成功（沿用本层取舍——宁可误报失败也不误报成功）。
    "failed": 3,
    "success": 2,
}


def _remove_owned_path(path: Path) -> None:
    """删除本模块创建的临时路径。"""

    if path.is_symlink():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()


def _ensure_no_symlinks(root: Path) -> None:
    """拒绝备份或恢复路径中的符号链接，避免越出项目目录。"""

    if root.is_symlink():
        raise RuntimeError(f"MFW 配置路径不能是符号链接：{root}")
    if not root.is_dir():
        return
    for child in root.rglob("*"):
        if child.is_symlink():
            raise RuntimeError(f"MFW 配置包含符号链接，拒绝运行：{child}")


def _read_json_object(path: Path, *, label: str) -> dict[str, Any]:
    """读取 JSON 对象；不存在时返回空对象。"""

    if not path.exists():
        return {}
    if path.is_symlink() or not path.is_file():
        raise RuntimeError(f"{label} 不是普通文件：{path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"{label} 不可读取：{path}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"{label} 根节点必须是对象：{path}")
    return data


def _instance_has_adb_device(instance_config: dict[str, Any]) -> bool:
    """实例配置是否携带非空的 ADB 设备标识。

    设备连接字段属 C 类，由现有实例配置透传、映射层不生成（见 tools/external/
    mfaavalonia.py）。本函数只判断标识存在且非空，不校验其内部结构。判据只认
    顶层 ``AdbDevice``（字符串，或含非空 ``AdbSerial`` 的对象）。

    **刻意不认 ``Connect.Address``**：该键在参考包的全部真实实例样本里都不存在，
    是 MAS 自己写进去的（见 ``_write_runtime_config``）。把它纳入判据会让 MAS 上一轮
    留下的残留键骗过 MAS 自己这道启动前守卫——用户明明没在外壳侧连过设备，
    第二次运行却能放行，直到控制器初始化失败才暴露。守卫要看的是「用户真的连过
    一次设备」的证据，只有 ``AdbDevice`` 是。
    """

    adb_device = instance_config.get("AdbDevice")
    if isinstance(adb_device, str) and adb_device.strip():
        return True
    if isinstance(adb_device, dict):
        serial = adb_device.get("AdbSerial")
        if isinstance(serial, str) and serial.strip():
            return True

    return False


def _warn_if_adb_missing(adb_path: Path, emulator_label: str) -> None:
    """生成的 ADB 路径不存在时告警。

    check() 里的 ADB 存在性校验只覆盖「透传实例原有设备配置」那条路；MAS 按登记
    模拟器**生成**设备配置时是另一条路，此前生成什么就写什么、从不校验，路径失效时
    要等外壳控制器初始化失败才暴露。这里只告警不拒绝：模拟器可能尚未安装完成或
    路径大小写差异，直接拒绝会误伤既有可用配置。
    """

    if not adb_path.is_file():
        logger.warning(
            f"MFW 生成的 {emulator_label} ADB 程序不存在：{adb_path}，"
            "外壳可能无法连接设备"
        )


def _resolve_active_instance_path(instances_dir: Path, project_root: Path) -> Path:
    """定位 MFAAvalonia 当前活动实例文件。

    MFAAvalonia 的实例文件按实例 ID 命名，活动实例记在项目根
    ``appsettings.json`` 的 ``Instances.LastActive``（.NET 平铺键，也兼容
    ``Instances`` 嵌套对象）。MaaKes 恰好叫 ``default``，M9A 那份是随机 ID。
    读不到活动实例、键值非法、或对应文件不存在时，回退到 ``default.json``。
    """

    default_path = instances_dir / "default.json"

    settings_path = project_root / "appsettings.json"
    if not settings_path.is_file():
        return default_path
    try:
        settings = json.loads(settings_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return default_path
    if not isinstance(settings, dict):
        return default_path

    last_active = settings.get("Instances.LastActive")
    if last_active is None:
        nested = settings.get("Instances")
        if isinstance(nested, dict):
            last_active = nested.get("LastActive")
    if not isinstance(last_active, str) or not last_active.strip():
        return default_path

    name = last_active.strip()
    candidate = instances_dir / f"{name}.json"
    # 拒绝越界文件名（含分隔符或 ..），只接受 instances_dir 下的直接子文件。
    if candidate.parent != instances_dir or candidate.name != f"{name}.json":
        return default_path
    return candidate if candidate.is_file() else default_path


def _load_json_dict(value: Any) -> dict[str, Any]:
    """把 ConfigBase 中的 JSON 字符串或裸 dict 收敛成 dict。"""

    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        with suppress(json.JSONDecodeError):
            data = json.loads(value)
            if isinstance(data, dict):
                return data
    return {}


def _load_json_list(value: Any) -> list[str]:
    """把 ConfigBase 中的 JSON 字符串或裸 list 收敛成非空字符串列表。"""

    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        with suppress(json.JSONDecodeError):
            data = json.loads(value)
            if isinstance(data, list):
                return [str(item) for item in data if str(item).strip()]
    return []


def _current_period_keys() -> tuple[str, str, str]:
    """返回当前 (日, 周, 月) 的周期键，与 mfwa tools/AutoProxy.py 语义一致。"""

    now = datetime.now(tz=UTC4)
    iso_year, iso_week, _ = now.date().isocalendar()
    return now.strftime("%Y-%m-%d"), f"{iso_year}-W{iso_week:02d}", now.strftime("%Y-%m")


def _checked_task_names_from_snapshot(snapshot: dict[str, Any]) -> list[str]:
    """从用户任务快照的 taskOrder / taskChecked 取按序勾选的任务名。

    结构为 ``{"taskOrder": [...], "taskChecked": {...}, "taskOptions": {...}}``。
    pretask 伪任务由 ``is_pretask_task_name`` 过滤掉，绝不进入运行范围。
    """

    order = snapshot.get("taskOrder")
    checked = snapshot.get("taskChecked")
    if not isinstance(order, list) or not isinstance(checked, dict):
        return []
    names: list[str] = []
    for name in order:
        if not isinstance(name, str) or not name.strip():
            continue
        if not checked.get(name):
            continue
        if is_pretask_task_name(name):
            continue
        if name not in names:
            names.append(name)
    return names


class MaaFWManager(TaskExecuteBase):
    """MaaFW MFAAvalonia 外部运行管理器。"""

    wait_for_finalizer_on_cancel = True

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.check_result: str = "-"
        self.begin_time: datetime | None = None

        # 跨 main_task/final_task/on_crash 使用的配置、路径和生命周期状态。
        self.script_config: MaaFWConfig | None = None
        self.project_root: Path | None = None
        self.config_dir: Path | None = None
        self.instances_dir: Path | None = None
        self.instance_path: Path | None = None
        # 外壳家族与其日志画像：两者在 check() 里确定，之后所有家族相关分支都读它，
        # 不再散落模块级常量。
        self.shell_family: ShellFamily = ShellFamily.UNKNOWN
        self.log_profile: ShellLogProfile | None = None
        # MXU：单文件容器 config/mxu-<项目名>.json，MAS 追加自己的实例条目。
        self.mxu_container_path: Path | None = None
        self.mxu_instance_id: str | None = None
        self.config_json_path: Path | None = None
        self.exe_path: Path | None = None
        self.log_path: Path | None = None
        self.log_start_time: datetime | None = None

        self.interface_model: Any | None = None
        self.controller_name: str | None = None
        self.resource_name: str | None = None
        self.task_selections: list[TaskSelection] = []
        # 任务名 → 全部可能写法（含各语言 label），见 _task_alias_index。
        self._alias_index: dict[str, tuple[str, ...]] = {}
        self._alias_index_token: tuple[str, int] | None = None

        self.state_dir = Path.cwd() / "data" / str(script_info.script_id) / _STATE_DIR_NAME
        self.temp_path = self.state_dir
        self.backup_path = self.state_dir / "config"
        self.manifest_path = self.state_dir / "manifest.json"
        self.backup_published = False
        self.config_existed = False
        self.restored = False
        self.cleanup_done = False
        self.cleanup_error: str | None = None
        self.cleanup_task: asyncio.Task | None = None

        self.process_manager: ProcessManager | None = None
        self.log_monitor: LogMonitor | None = None
        self.process_started = False
        self.process_pid: int | None = None
        self.monitor_started = False

        # 运行前启动准备（Adb 起模拟器 / Win32 起 PC 游戏）跨用户复用的句柄与状态。
        self.emulator_manager: DeviceBase | None = None
        self.emulator_info: DeviceInfo | None = None
        # MaaFramework 枚举出来的本轮设备（maa.toolkit.AdbDevice）。MXU 外壳按
        # MaaFW 的设备名匹配，本层拿不到就只能让外壳瞎猜，见 _resolve_maafw_device。
        self.maafw_device: Any | None = None
        self.generated_adb_device: dict[str, Any] | None = None
        self.emulator_opened = False
        self.emulator_index: str = ""
        self.game_launch_spec: MaaFWGameLaunchSpec | None = None
        self.game_owned_process: MaaFWOwnedGameProcess | None = None
        # AttachOnly 模式下已在跑的游戏进程 pid：_prepare_desktop_game 扫到后
        # 记下来，置前时直接用，避免再做一次全进程扫描。
        self.game_attached_pid: int | None = None

        # 用户层运行：任务队列属于用户，遍历真实用户而非单个虚拟用户。
        self.user_config: MultipleConfig[MaaFWUserConfig] | None = None
        self.runnable_user_uids: list[uuid.UUID] = []
        self.current_user_item: UserItem | None = None
        self.current_user_uid: uuid.UUID | None = None
        self.current_user_config: MaaFWUserConfig | None = None
        self._fallback_user: UserItem | None = None
        self.user_terminal: dict[str, str | None] = {}
        self.curdate: str = ""

        self.current_log: LogRecord | None = None
        self.terminal_event = asyncio.Event()
        self.terminal_kind: str | None = None
        self.last_log_text = ""
        self.last_log_at: datetime | None = None

        # LogRecord 的变化不触发任何前端通知（UserItem.__setattr__ 只监听
        # user_id / name / status）。这是事实而非缺陷：它在 _write_history_records
        # 落历史盘、在 _push_run_report 计数两处被真正读取，不是死字段。
        # **绝不要给 LogRecord 加 __setattr__ 通知钩子**——_mark_terminal 与 on_crash
        # 都会写 current_log.status，加钩子等于给受保护函数引入广播副作用。
        # 历史记录与任务报告各只写/发一次（final_task 幂等、可能被多路径调用）。
        self.history_written = False
        self.report_pushed = False

    async def check(self) -> str:
        """校验 MaaFW 配置、外壳、选择项和可运行文件。"""

        if self.task_info.mode != "AutoProxy":
            return "MFW 当前仅支持外部自动运行模式"

        try:
            script_uid = uuid.UUID(self.script_info.script_id)
        except (ValueError, AttributeError, TypeError):
            return "MFW 脚本 ID 无效，请刷新后重试"

        try:
            script_config = Config.ScriptConfig[script_uid]
        except (KeyError, ValueError):
            return "MFW 脚本配置不存在，请刷新后重试"

        if not isinstance(script_config, MaaFWConfig):
            return "脚本配置类型错误，不是 MFW 脚本类型"
        self.script_config = script_config

        project_value = str(script_config.get("Info", "Path") or "").strip()
        if not project_value:
            return "请设置 MFW 项目路径"
        project_root = Path(project_value).resolve()
        if not project_root.is_dir():
            return "请设置包含 interface.json 的 MFW 项目目录"

        if script_config.get("Run", "Engine") != "external":
            return "MFW 当前仅支持 external 运行引擎"

        shell_family = detect_shell_family(project_root)
        log_profile = get_shell_log_profile(shell_family)
        if log_profile is None:
            # 未登记的外壳家族：这是**能力边界**而不是故障，文案要让用户看得懂
            # 下一步，不要引导他去导出问题包。
            return (
                f"这个项目使用 {shell_family.value} 外壳，MFW 专项暂不支持。"
                "当前支持 MFAAvalonia（如 M9A、MaaKes）与 MXU（如 MaaEnd、MaaYYs）"
                "两类外壳的项目。"
            )

        try:
            interface_model = load_interface_model_cached(project_root)
        except Exception as exc:
            return f"MFW interface 读取失败：{exc}"

        # 用户层：controller / resource 走 Info.*（用户级留空回退脚本级），
        # 运行范围走用户 Task.TaskSnapshot；不再从脚本级 Selection.* 读取。
        user_config: MultipleConfig[MaaFWUserConfig] = MultipleConfig([MaaFWUserConfig])
        await user_config.load(await script_config.UserData.toDict())
        runnable_uids = [
            uid
            for uid, cfg in user_config.items()
            if cfg.get("Info", "Status") and cfg.get("Info", "RemainedDay") != 0
        ]
        if not runnable_uids:
            return "MFW 没有可运行的用户，请在用户管理页添加并启用至少一个用户"

        controller_index = {item.name for item in interface_model.controller}
        resource_index = {item.name for item in interface_model.resource}
        task_index = {item.name for item in interface_model.task}

        # 至少要有一个用户排了任务；单个用户没排任务只让该用户跳过，不拖垮整脚本。
        users_with_tasks = 0
        try:
            for uid in runnable_uids:
                cfg = user_config[uid]
                user_name = cfg.get("Info", "Name")
                controller_name = self._resolve_controller_name(cfg, script_config)
                if not controller_name:
                    raise ValueError(
                        f"用户 {user_name} 未确定 MFW controller，"
                        "请在脚本编辑页或用户配置中选择"
                    )
                if controller_name not in controller_index:
                    raise ValueError(f"interface 未定义 controller：{controller_name}")
                resource_name = self._resolve_resource_name(
                    cfg, script_config, interface_model, controller_name
                )
                if not resource_name:
                    raise ValueError(f"用户 {user_name} 未确定 MFW resource")
                if resource_name not in resource_index:
                    raise ValueError(f"interface 未定义 resource：{resource_name}")
                task_names = self._parse_snapshot_task_selection(
                    cfg.get("Task", "TaskSnapshot")
                )
                unknown_tasks = [name for name in task_names if name not in task_index]
                if unknown_tasks:
                    raise ValueError(f"interface 未定义 task：{unknown_tasks[0]}")
                if task_names:
                    users_with_tasks += 1
        except (ValueError, ShellMappingError) as exc:
            return f"MFW 选择配置无效：{exc}"
        except Exception as exc:
            return f"MFW interface 读取失败：{exc}"

        if users_with_tasks == 0:
            return "MFW 没有任何启用用户排入任务，请在用户编辑页配置任务队列"

        # 供下方启动前设备校验使用的代表性 controller / resource：取首个可运行用户。
        first_cfg = user_config[runnable_uids[0]]
        controller_name = self._resolve_controller_name(first_cfg, script_config)
        resource_name = self._resolve_resource_name(
            first_cfg, script_config, interface_model, controller_name
        )

        # 启动前自洽校验：登记了 MAS 模拟器时，本轮会在启动后生成 AdbDevice；
        # 未登记时才沿用活动实例里的设备字段，并提前拒绝确定无效的透传配置。
        emulator_selection = self._get_emulator_selection(script_config)
        controller_type = next(
            (
                item.type
                for item in interface_model.controller
                if item.name == controller_name
            ),
            None,
        )
        is_mfaavalonia = shell_family is ShellFamily.MFAAVALONIA
        if is_mfaavalonia and controller_type == "Adb" and emulator_selection is None:
            # 必须校验 MAS 实际会写入的那个实例文件。MFAAvalonia 的实例文件按实例 ID
            # 命名（MaaKes 恰好叫 default，M9A 那份是随机 ID），此前这里硬编码
            # default.json，与 _write_runtime_config 的写入目标不一致：对只有
            # <随机id>.json 的项目会误拒，反之也可能误放行。
            try:
                instance_base = _read_json_object(
                    _resolve_active_instance_path(
                        project_root / "config" / "instances", project_root
                    ),
                    label="MFW 活动实例配置",
                )
            except RuntimeError as exc:
                return f"MFW 实例配置无法读取：{exc}"
            if not _instance_has_adb_device(instance_base):
                return (
                    "未配置模拟器设备，MFW 无法连接：实例配置缺少 AdbDevice，"
                    "请先在外壳侧连接一次模拟器"
                )
            adb_device = instance_base.get("AdbDevice")
            if isinstance(adb_device, dict):
                adb_path_value = str(adb_device.get("AdbPath") or "").strip()
                adb_path = Path(adb_path_value)
                if (
                    adb_path_value
                    and adb_path.is_absolute()
                    and not adb_path.is_file()
                ):
                    return (
                        f"MFW 实例配置中的 ADB 程序不存在：{adb_path_value}。"
                        "请在 MAS 中选择当前模拟器，或先在外壳侧重新连接设备"
                    )
        elif (
            is_mfaavalonia
            and controller_type
            and resolve_controller_code(controller_type) is None
        ):
            # 向映射层求证，而非在此硬编码「只支持 Adb」：CONTROLLER_TYPE_CODES 是
            # CurrentController 枚举的单一真源（当前只登记 Adb=2，已在 M9A / MaaKes /
            # Maa_bbb 三个项目交叉确认；Win32 等取值在 reference 的全部实例样本中都
            # 不存在，映射层按设计 fail-closed 而非猜测）。日后有人补上某个类型的枚举，
            # 这条拒绝会自动失效，无需改动两处。
            #
            # 提前拒绝的意义：否则 _prepare_launch_for_user 会先把游戏／模拟器起起来，
            # 随后 _write_runtime_config 抛 UnknownControllerTypeError——结果正确但白
            # 起一次进程。这里在加锁与备份之前就明确告知用户。
            return (
                f"MFW 外部运行暂不支持 {controller_type} 控制器："
                "该类型的 CurrentController 取值尚未确认，"
                "请改用 Adb 控制器，或在外壳侧手动运行"
            )

        exe_path = self._resolve_executable(project_root, shell_family)
        if isinstance(exe_path, str):
            return exe_path

        config_dir = project_root / "config"
        if config_dir.exists() and not config_dir.is_dir():
            return f"MFW config 路径不是目录：{config_dir}"

        self.project_root = project_root
        self.config_dir = config_dir
        self.shell_family = shell_family
        self.log_profile = log_profile
        if shell_family is ShellFamily.MXU:
            # MXU 是「单文件容器 + 内嵌 instances[]」，没有 instances/ 目录，
            # 也没有 MFAAvalonia 那份 config.json。容器文件名含项目名，用 glob 定位。
            containers = sorted((config_dir).glob("mxu-*.json"))
            if not containers:
                return f"未找到 MXU 容器配置：{config_dir} 下的 mxu-*.json"
            if len(containers) > 1:
                names = "、".join(path.name for path in containers)
                return f"MFW config 下存在多个 MXU 容器配置，无法消歧：{names}"
            self.mxu_container_path = containers[0]
            self.instances_dir = None
            self.instance_path = None
            self.config_json_path = None
        else:
            self.mxu_container_path = None
            self.instances_dir = config_dir / "instances"
            self.instance_path = _resolve_active_instance_path(
                self.instances_dir, project_root
            )
            self.config_json_path = config_dir / "config.json"
        self.exe_path = exe_path
        self.interface_model = interface_model
        self.controller_name = controller_name
        self.resource_name = resource_name
        # 运行范围按用户在运行循环里逐个解析并写入 self.task_selections。
        self.task_selections = []
        self.user_config = user_config
        self.runnable_user_uids = runnable_uids
        # check() 阶段的日志路径只用于「路径已初始化」这一前置守卫；真正监控哪个
        # 文件由 _run_external 按开跑时刻重算（见 _resolve_log_path）。
        self.log_path = self._resolve_log_path()
        return "Pass"

    @staticmethod
    def _parse_snapshot_task_selection(value: Any) -> list[str]:
        """用户 Task.TaskSnapshot → 按序勾选的任务名列表（pretask 已滤除）。

        空列表是合法结果：新建用户默认 ``Info.Status=True`` 且
        ``Task.TaskSnapshot="{ }"``，此前在此抛错会让 check() 整体拒绝运行，
        导致「新建一个用户 → 整个脚本连同已配好的用户一起跑不了」。
        现改为返回空列表，由调用方按「该用户跳过」处理；只有**全部**可运行用户
        都没有任务时才在 check() 判失败。
        """

        return _checked_task_names_from_snapshot(_load_json_dict(value))

    def _build_task_selections(
        self,
        task_names: list[str],
        raw_task_options: dict[str, Any],
        *,
        controller_name: str,
        resource_name: str,
    ) -> list[TaskSelection]:
        """把任务名 + 用户选项值组装成运行范围。

        此前只构造 ``TaskSelection(name=...)``，于是映射层走 interface 默认值分支，
        把用户在任务编辑页选的选项**静默替换成每项的第 0 个 case**。这里补上
        选项值：先由内核 ``normalize_task_options_by_task`` 按 interface 声明校验、
        补默认值并按 controller / resource 过滤，再经 ``build_option_entries``
        转成外壳的 option 条目形状。

        选项为空的任务仍传 ``options=None``，让映射层维持「任务没有选项就不写
        option 键」的既有行为，避免多出一个空列表。
        """

        if self.interface_model is None:
            raise RuntimeError("MFW interface 未加载")

        normalized = normalize_task_options_by_task(
            raw_task_options,
            task_names,
            self.interface_model,
            controller_name=controller_name,
            resource_name=resource_name,
        )
        task_index = {task.name: task for task in self.interface_model.task}

        selections: list[TaskSelection] = []
        for name in task_names:
            task = task_index.get(name)
            if task is None:
                selections.append(TaskSelection(name=name))
                continue
            # 只写用户**真正设过**的选项。normalize 会把 interface 声明的默认值一并
            # 填进来，若照单全写就会改变既有行为：M9A 实测下「心相观测」会多出
            # selected_cases: []、「使用兑换码」会把 interface 的占位串 "占位" 当成
            # 兑换码写进实例配置——用户根本没碰过这两项。
            # 用户没设的选项退回 {"name": …, "index": 0}，与本次修复前逐字节一致。
            raw_for_task = raw_task_options.get(name)
            touched = set(raw_for_task) if isinstance(raw_for_task, dict) else set()
            values = {
                key: value
                for key, value in (normalized.get(name) or {}).items()
                if key in touched
            }
            entries = build_option_entries(self.interface_model, task, values)
            selections.append(
                TaskSelection(name=name, options=entries if entries else None)
            )
        return selections

    @staticmethod
    def _parse_snapshot_task_options(value: Any) -> dict[str, Any]:
        """用户 Task.TaskSnapshot → 原始 taskOptions（``{任务名: {选项名: 值}}``）。

        取出的是**未归一化**的原始值，交由内核
        ``normalize_task_options_by_task`` 按 interface 声明校验并补默认值。
        """

        raw = _load_json_dict(value).get("taskOptions")
        return raw if isinstance(raw, dict) else {}

    @staticmethod
    def _resolve_controller_name(
        user_config: MaaFWUserConfig,
        script_config: MaaFWConfig,
    ) -> str:
        """controller 走简单 or 回退：用户级留空则取脚本级默认。"""

        return str(
            user_config.get("Info", "Controller")
            or script_config.get("Info", "Controller")
            or ""
        ).strip()

    @staticmethod
    def _resolve_resource_name(
        user_config: MaaFWUserConfig,
        script_config: MaaFWConfig,
        interface_model: Any,
        controller_name: str,
    ) -> str:
        """resource 走简单 or 回退；两级都留空时取首个匹配 controller 的 resource。"""

        configured = str(
            user_config.get("Info", "Resource")
            or script_config.get("Info", "Resource")
            or ""
        ).strip()
        if configured:
            return configured
        for resource in interface_model.resource:
            controllers = getattr(resource, "controller", None) or []
            if not controllers or controller_name in controllers:
                return resource.name
        return ""

    @staticmethod
    def _resolve_executable(
        project_root: Path, family: ShellFamily = ShellFamily.MFAAVALONIA
    ) -> Path | str:
        """定位外壳可执行文件。

        MFAAvalonia 优先用根目录同名 exe，再兼容旧的 project 子目录。
        MXU 的 exe 名**不统一**（MaaYYs 是 mxu.exe、MaaEnd 是 MaaEnd.exe），
        没有可依赖的固定名，故先试已知名再退回「根目录恰好一个 exe」。
        两者最后都走同一条唯一性兜底：多个候选时拒绝，绝不猜。
        """

        if family is ShellFamily.MXU:
            known = ("mxu.exe", "MaaEnd.exe")
            label = "MXU 外壳"
        else:
            known = ("MFAAvalonia.exe",)
            label = "MFAAvalonia.exe"

        for name in known:
            candidate = project_root / name
            if candidate.is_file():
                return candidate
        if family is ShellFamily.MFAAVALONIA:
            compatibility = project_root / "project" / "MFAAvalonia.exe"
            if compatibility.is_file():
                return compatibility

        root_executables = [path for path in project_root.glob("*.exe") if path.is_file()]
        if len(root_executables) == 1:
            return root_executables[0]
        if not root_executables:
            return f"{label} 不存在，请检查 MFW 项目目录"
        return f"MFW 项目根目录存在多个 exe，无法安全选择 {label}"

    async def prepare(self) -> None:
        """锁定 MAS 配置，恢复残留快照并制作本轮配置备份。"""

        if self.script_config is None or self.project_root is None:
            raise RuntimeError("MFW 配置检查尚未通过")

        script_uid = uuid.UUID(self.script_info.script_id)
        script_config = Config.ScriptConfig[script_uid]
        if not isinstance(script_config, MaaFWConfig):
            raise TypeError("脚本配置类型错误，不是 MFW 脚本类型")
        self.script_config = script_config
        await script_config.lock()
        logger.success(f"{self.script_info.script_id} 已锁定，MFW 配置提取完成")

        self.begin_time = datetime.now()
        if self.user_config is None:
            raise RuntimeError("MFW 用户配置未加载")
        self.script_info.user_list = [
            UserItem(
                user_id=str(uid),
                name=self.user_config[uid].get("Info", "Name"),
                status="等待",
            )
            for uid in self.runnable_user_uids
        ]
        logger.info(
            f"MFW 用户列表加载完成，已筛选用户数: {len(self.script_info.user_list)}"
        )
        self.script_info.status = "运行"

        # 启动时先恢复上一次被强杀遗留的快照，再发布本轮有效备份。
        self.restored = False
        self.backup_published = False
        if self._has_residual_state():
            # 旧外壳可能仍在写 config；必须先按精确 exe 路径结束它，再恢复快照。
            if self.exe_path is None:
                raise RuntimeError("MFW 外壳路径未初始化")
            if not await System.kill_process(self.exe_path):
                raise RuntimeError(
                    "MFW 残留外壳无法确认已结束，已保留备份并拒绝恢复 config"
                )
            logger.info(f"MFW 已结束残留外壳，准备恢复：{self.exe_path}")
        # copytree / rmtree / rglob 是同步阻塞调用，项目目录可达数百 MB；直接跑在
        # 事件循环上会卡住整个后端（含 WebSocket 心跳与其他脚本的调度）。
        await asyncio.to_thread(self._recover_residual_backup)
        await asyncio.to_thread(self._backup_project_config)
        # 运行配置按用户在运行循环里逐个写入，备份只发布一次。

    def _ensure_virtual_user(self) -> UserItem:
        """返回当前正在执行的用户项；运行循环外（检查失败等）退回一个占位用户。

        ``_mark_terminal`` / ``check_log`` 等终态代码调用本方法拿「当前用户」，
        因此签名和返回类型保持不变。
        """

        if self.current_user_item is not None:
            return self.current_user_item
        if self._fallback_user is None:
            self._fallback_user = UserItem(
                user_id=str(
                    uuid.uuid5(uuid.NAMESPACE_URL, f"maafw:{self.script_info.script_id}")
                ),
                name=self.script_info.name or "MFW 项目",
                status="等待",
            )
            self.script_info.user_list = [self._fallback_user]
        return self._fallback_user

    def _backup_project_config(self) -> None:
        if self.project_root is None or self.config_dir is None:
            raise RuntimeError("MFW 项目路径未初始化")
        self.state_dir.parent.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        if self.config_dir.exists() and not self.config_dir.is_dir():
            raise RuntimeError(f"MFW config 路径不是目录：{self.config_dir}")
        self.config_existed = self.config_dir.exists()
        if self.config_existed:
            _ensure_no_symlinks(self.config_dir)

        temporary_backup = self.state_dir / "config.tmp"
        _remove_owned_path(temporary_backup)
        if self.config_existed:
            shutil.copytree(self.config_dir, temporary_backup)
        else:
            temporary_backup.mkdir(parents=True, exist_ok=True)

        # 备份目录准备完毕后再发布；manifest 是恢复时的唯一可信入口。
        _remove_owned_path(self.backup_path)
        temporary_backup.rename(self.backup_path)
        manifest = {
            "version": 1,
            "script_id": str(self.script_info.script_id),
            "project_path": str(self.project_root.resolve()),
            "config_exists": self.config_existed,
            # 备份范围只有 config/，但外壳会改写项目根 appsettings.json 里的实例
            # 指针（MAS 删光 instances/*.json 只留自己那个，外壳退出时把 List /
            # Order 收缩成单项、LastActive 指向 MAS 实例）。这四键不还原的话，
            # 用户的实例集合在外壳 UI 里会永久变成只剩 MAS 一个。存进 manifest
            # 而不是另开文件：manifest 是崩溃恢复的唯一可信入口，也是原子写。
            "appsettings_instances": self._snapshot_appsettings_instance_keys(),
            # 同理，MXU 的自动更新闸门读的是项目根 interface.json，不是外壳
            # 设置，故这里也只快照那几个键，跑完还原。
            "interface_update_keys": self._snapshot_interface_update_keys(),
        }
        atomic_write_maafw_config(self.manifest_path, manifest, journal=False)
        self.backup_published = True
        self.restored = False
        logger.info(f"MFW config 已备份到 MAS 数据目录：{self.backup_path}")

    def _snapshot_appsettings_instance_keys(self) -> dict[str, Any]:
        """快照项目根 ``appsettings.json`` 里的实例指针键。

        只取 ``_APPSETTINGS_INSTANCE_KEYS`` 这几项，不整文件快照——外壳在运行期
        还会写窗口位置、公告已读等与本层无关的设置，整文件还原会把用户这些改动
        一并回滚。缺失的键不进快照，还原时按「原本就没有」处理并删除。
        """

        if self.project_root is None:
            return {}
        path = self.project_root / "appsettings.json"
        try:
            settings = _read_json_object(path, label="MFW appsettings")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"MFW 读取 appsettings.json 失败，跳过实例指针快照：{exc}")
            return {}
        return {key: settings[key] for key in _APPSETTINGS_INSTANCE_KEYS if key in settings}

    def _snapshot_interface_update_keys(self) -> dict[str, Any]:
        """快照项目根 ``interface.json`` 里控制外壳自动更新的键。

        与 appsettings 那份同理：只取需要的键，不整文件快照。
        """

        if self.project_root is None:
            return {}
        path = self.project_root / "interface.json"
        try:
            data = _read_json_object(path, label="MFW interface")
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"MFW 读取 interface.json 失败，跳过更新键快照：{exc}")
            return {}
        return {key: data[key] for key in _INTERFACE_UPDATE_KEYS if key in data}

    def _disable_shell_self_update(self) -> None:
        """摘掉 MXU 的自动更新闸门键，让本轮运行不去检查/下载更新。

        更新必须由 MAS 统一编排，外壳自己更新会把这一轮任务顶掉：MXU 的自动
        运行是**排在更新检查之后**的，一旦开始下载就把待跑任务挂起，等安装重启
        后才执行（MXU src/App.tsx 的 autoStartTasksPending → pendingAutoTasksRef）。
        2026-08-29 真机实测就是这样：外壳已经匹配到 MAS 实例、连上 Win32 控制器，
        随后开始下载 v2.27.0-beta.1，整轮再没出现过「开始执行任务」。

        闸门条件是 ``interface.mirrorchyan_rid && interface.version``（两者都来自
        项目根 interface.json，不是外壳设置——所以 MXU 的 UI 里根本没有这个开关）。
        这里摘 ``mirrorchyan_rid``：它只服务于更新，摘掉整段检查都不会执行；而
        ``version`` 还要参与界面显示与遥测，动它副作用更大。

        MFAAvalonia 家族走的是另一条路——写 config.json 的 EnableCheckVersion 等
        三个开关，见 _write_mfaavalonia_runtime_config。
        """

        if self.project_root is None:
            return
        path = self.project_root / "interface.json"
        if not path.is_file():
            return
        try:
            data = _read_json_object(path, label="MFW interface")
            removed = [key for key in _INTERFACE_UPDATE_KEYS if key in data]
            if not removed:
                return
            for key in removed:
                del data[key]
            atomic_write_maafw_config(path, data, journal=False)
            logger.info(f"MFW 已关闭外壳自动更新：移除 interface.json 的 {removed}")
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(
                f"MFW 关闭外壳自动更新失败，本轮可能被外壳更新顶掉：{exc}"
            )

    def _restore_interface_update_keys(self, snapshot: Any) -> None:
        """把 interface.json 的更新键还原成本轮运行前的样子。

        ``snapshot`` 为 ``None`` 说明 manifest 由旧版本写出，按既有行为跳过。
        自保护：还原失败不应阻断 config 目录本身的还原结果。
        """

        if not isinstance(snapshot, dict) or self.project_root is None:
            return
        path = self.project_root / "interface.json"
        if not path.is_file():
            return
        try:
            data = _read_json_object(path, label="MFW interface")
            changed = False
            for key in _INTERFACE_UPDATE_KEYS:
                if key in snapshot:
                    if data.get(key) != snapshot[key]:
                        data[key] = snapshot[key]
                        changed = True
                elif key in data:
                    del data[key]
                    changed = True
            if changed:
                atomic_write_maafw_config(path, data, journal=False)
                logger.info("MFW 已还原 interface.json 的自动更新键")
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(
                f"MFW 还原 interface.json 更新键失败：{exc}"
            )

    def _restore_appsettings_instance_keys(self, snapshot: Any) -> None:
        """把实例指针键还原成本轮运行前的样子。

        ``snapshot`` 为 ``None`` 时说明这份 manifest 由旧版本写出（不含该字段），
        按既有行为跳过，不报错。整个过程自保护：还原实例指针失败不应阻断 config
        目录本身的还原结果。
        """

        if not isinstance(snapshot, dict) or self.project_root is None:
            return
        path = self.project_root / "appsettings.json"
        if not path.is_file():
            return
        try:
            settings = _read_json_object(path, label="MFW appsettings")
            changed = False
            for key in _APPSETTINGS_INSTANCE_KEYS:
                if key in snapshot:
                    if settings.get(key) != snapshot[key]:
                        settings[key] = snapshot[key]
                        changed = True
                elif key in settings:
                    # 本轮运行前没有这个键，是外壳新写的，删回去。
                    del settings[key]
                    changed = True
            if changed:
                atomic_write_maafw_config(path, settings, journal=False)
                logger.info("MFW 已还原 appsettings.json 的实例指针")
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(
                f"MFW 还原 appsettings.json 实例指针失败：{exc}"
            )

    def _has_residual_state(self) -> bool:
        """返回是否存在本模块留下的、需要启动前处理的状态。"""

        if self.state_dir.is_symlink():
            raise RuntimeError("MFW 残留备份目录无效，拒绝运行")
        if not self.state_dir.exists():
            return False
        if not self.state_dir.is_dir():
            raise RuntimeError("MFW 残留备份目录无效，拒绝运行")
        return any(self.state_dir.iterdir())

    def _load_backup_manifest(self) -> dict[str, Any]:
        if self.project_root is None:
            raise RuntimeError("MFW 项目路径未初始化")
        if self.manifest_path.is_symlink() or not self.manifest_path.is_file():
            raise RuntimeError("MFW 残留备份 manifest 缺失或不是普通文件")
        manifest = _read_json_object(self.manifest_path, label="MFW 残留备份 manifest")
        if manifest.get("version") != 1:
            raise RuntimeError("MFW 残留备份版本不受支持")
        if manifest.get("script_id") != str(self.script_info.script_id):
            raise RuntimeError("MFW 残留备份脚本 ID 不匹配，拒绝恢复")
        manifest_path = manifest.get("project_path")
        if not isinstance(manifest_path, str) or not Path(manifest_path).is_absolute():
            raise RuntimeError("MFW 残留备份项目路径无效，拒绝恢复")
        if Path(manifest_path).resolve() != self.project_root.resolve():
            raise RuntimeError("MFW 残留备份项目路径不匹配，拒绝恢复")
        if not isinstance(manifest.get("config_exists"), bool):
            raise RuntimeError("MFW 残留备份缺少 config_exists，拒绝恢复")
        if self.backup_path.is_symlink() or not self.backup_path.is_dir():
            raise RuntimeError("MFW 残留备份 config 不完整，拒绝恢复")
        _ensure_no_symlinks(self.backup_path)
        if not manifest["config_exists"] and any(self.backup_path.iterdir()):
            raise RuntimeError("MFW 残留备份标记与 config 内容不一致，拒绝恢复")
        return manifest

    def _recover_residual_backup(self) -> None:
        if self.state_dir.is_symlink():
            raise RuntimeError("MFW 残留备份目录无效，拒绝运行")
        if not self.state_dir.exists():
            return
        if not self.state_dir.is_dir():
            raise RuntimeError("MFW 残留备份目录无效，拒绝运行")
        entries = list(self.state_dir.iterdir())
        if not entries:
            self.state_dir.rmdir()
            return
        # copytree 已完成但 manifest 尚未发布时，config.tmp 不是有效备份；
        # 它完全位于 MAS data 目录，安全清理后继续，绝不覆盖 live config。
        if (
            not self.manifest_path.exists()
            and len(entries) == 1
            and entries[0].name == "config.tmp"
        ):
            temporary_backup = entries[0]
            if temporary_backup.is_symlink() or not temporary_backup.is_dir():
                raise RuntimeError("MFW 未发布备份 config.tmp 无效，拒绝运行")
            _remove_owned_path(temporary_backup)
            self.state_dir.rmdir()
            logger.info("MFW 已清理未发布的 config.tmp 残留")
            return
        self._restore_backup_from_state()
        logger.info("MFW 已自动恢复上次未完成任务的残留配置")

    def _restore_backup_from_state(self) -> None:
        if self.config_dir is None:
            raise RuntimeError("MFW config 路径未初始化")
        manifest = self._load_backup_manifest()
        config_existed = manifest["config_exists"]
        temporary_restore = self.config_dir.with_name(self.config_dir.name + ".restore.tmp")
        _remove_owned_path(temporary_restore)

        if self.config_dir.is_symlink() or (
            self.config_dir.exists() and not self.config_dir.is_dir()
        ):
            raise RuntimeError(f"MFW config 路径不是安全目录：{self.config_dir}")

        if config_existed:
            shutil.copytree(self.backup_path, temporary_restore)

        _remove_owned_path(self.config_dir)
        if config_existed:
            temporary_restore.rename(self.config_dir)

        self._restore_appsettings_instance_keys(manifest.get("appsettings_instances"))
        self._restore_interface_update_keys(manifest.get("interface_update_keys"))

        _remove_owned_path(self.state_dir)
        self.restored = True
        self.backup_published = False
        logger.info(f"MFW config 已恢复：{self.config_dir}")

    def _write_runtime_config(self) -> None:
        """把本轮运行范围写进外壳能识别的配置，按外壳家族分派。"""

        if self.shell_family is ShellFamily.MXU:
            self._write_mxu_runtime_config()
            self._disable_shell_self_update()
            return
        self._write_mfaavalonia_runtime_config()

    def _write_mxu_runtime_config(self) -> None:
        """MXU：向单文件容器**追加**一个 MAS 实例，并指向它。

        与 MFAAvalonia 路径的关键差异：绝不删除用户已有实例。容器里同时存着
        用户的全部配置，删了就没了；append_instance 保证原有条目逐字段不变、
        其余顶层键零触碰。

        base 取当前活动实例：为的是继承 savedDevice（MXU 的设备是按名存的，
        不继承就没有连接目标）。但**显式清掉 preActions**——那是外壳自己的
        「起程序」钩子，继承下来外壳会重复启动游戏/模拟器，与 MFAAvalonia 路径上
        靠 SoftwarePath="" 防的是同一类问题（本层集中管理生命周期）。
        """

        if (
            self.interface_model is None
            or self.mxu_container_path is None
            or self.controller_name is None
            or self.resource_name is None
        ):
            raise RuntimeError("MFW MXU 运行配置路径或选择未初始化")

        backup_container = self.backup_path / self.mxu_container_path.name
        source = (
            backup_container if backup_container.is_file() else self.mxu_container_path
        )
        container = _read_json_object(source, label="MFW MXU 容器配置")

        base = None
        active_id = container.get("lastActiveInstanceId")
        for item in container.get("instances", []) or []:
            if isinstance(item, dict) and item.get("id") == active_id:
                base = dict(item)
                break
        if base is not None:
            base.pop("preActions", None)
            self._apply_mxu_saved_device(base)

        entry = build_instance_entry(
            self.interface_model,
            controller_name=self.controller_name,
            resource_name=self.resource_name,
            selected_tasks=self.task_selections,
            name=_MXU_INSTANCE_NAME,
            base=base,
            instance_id=default_instance_id(),
        )
        # 同名就地替换：MXU 的 --instance 按显示名匹配，重名时取先出现的那个。
        # 每轮都追加一个叫 MAS 的新实例，只要有残留就会被匹配到旧的。
        before = len(container.get("instances", []) or [])
        updated = append_instance(
            container, entry, set_active=True, replace_same_name=True
        )
        self._write_shell_config(self.mxu_container_path, updated, label="MXU 容器配置")
        # 同名替换会沿用被替换者的 id，所以要读**写回去的那份**，不能读 entry；
        # 读 entry 会把日志里的实例 id 报成一个根本没落盘的值。
        self.mxu_instance_id = str(updated.get("lastActiveInstanceId") or "")
        after = len(updated.get("instances", []) or [])
        action = "已替换同名实例" if after == before else "已追加"
        logger.info(
            f"MFW MXU 运行配置{action}：{self.mxu_container_path.name}"
            f"（实例 {self.mxu_instance_id}，容器内共 {after} 个）"
        )

    def _apply_mxu_saved_device(self, base: dict[str, Any]) -> None:
        """把本轮实际起的设备写进 MXU 实例的 ``savedDevice``。

        此前本层只是从活动实例整个继承 ``savedDevice``，而老配置里往往只有一个
        过期的 ``adbDeviceName``：2026-08-29 真机实测，外壳扫到的是
        ``ldplayer-LDPlayer``，继承来的名字却是 ``雷电模拟器-LDPlayer``，于是
        「未找到设备」，自动运行直接失败。

        名字必须写对，不能省。MaaYYs v3.14.8 内置的那版外壳没有
        ``adbDeviceAddress`` 字段，只按名字匹配，且逻辑是硬的::

            savedDevice.adbDeviceName
              ? findAdbDevices().find(d => d.name === savedDevice.adbDeviceName)
              : findAdbDevices()[0]          // 有几个设备就自动选第一个

        所以名字缺席时外壳会自动选中枚举出的第一个设备 —— 装了多个模拟器就必然
        选错（实测本层起的是雷电 ``emulator-5554``，外壳自动连上了 MuMu）。而
        MaaFramework 枚举的是**已安装**的模拟器，关掉别的也不管用。

        名字由 ``_resolve_maafw_device`` 用 MaaFramework 自己的枚举解析（见那里）。
        地址一并写上：新版外壳的 ``findMatchingAdbDevice`` 是地址优先、名字兜底，
        写两个在新旧外壳上都精确。两个值都取自同一条 ``AdbDevice``，不会互相打架。

        解析不到时退回只写地址，并**清掉继承来的名字** —— 留着一个过期名字是硬
        失败，清掉至少还剩「自动选第一个」这条路，且新版外壳仍能按地址精确匹配。

        Adb 之外的控制方式（Win32 / PlayCover 等）没有 adb 地址，原样跳过。
        """

        info = self.emulator_info
        if info is None or not info.adb_address or info.adb_address == "Unknown":
            return

        device = self.maafw_device
        if device is not None:
            # 与 MaaEnd 专项一致：整体替换，不继承旧键。savedDevice 里的
            # windowName / wlrSocketPath / playcoverAddress 同样参与匹配，
            # 继承过来只会让外壳在别的控制方式上认错目标。
            base["savedDevice"] = {
                "adbDeviceName": device.name,
                "adbDeviceAddress": device.address,
            }
            logger.info(
                f"MFW 已写入 MXU 连接目标：{device.name}（{device.address}）"
            )
            return

        saved = base.get("savedDevice")
        saved = dict(saved) if isinstance(saved, dict) else {}
        stale_name = saved.pop("adbDeviceName", None)
        saved["adbDeviceAddress"] = info.adb_address
        base["savedDevice"] = saved
        logger.warning(
            f"MFW 未解析出 MaaFramework 设备名，仅写入地址 {info.adb_address}："
            "旧版外壳只按名字匹配，装有多个模拟器时可能连错"
        )
        if stale_name:
            logger.info(
                f"MFW 已清除继承的 MXU 设备名 {stale_name!r}：过期名字会让外壳直接报「未找到设备」"
            )

    def _write_mfaavalonia_runtime_config(self) -> None:
        if (
            self.interface_model is None
            or self.instances_dir is None
            or self.instance_path is None
            or self.config_json_path is None
            or self.controller_name is None
            or self.resource_name is None
        ):
            raise RuntimeError("MFW 运行配置路径或选择未初始化")

        # 多用户逐个写入：base 始终取本轮备份里的原始实例配置，避免上一个用户
        # 写入的 controller / TaskItems 漏进下一个用户。登记了 MAS 模拟器时覆盖
        # AdbDevice；否则继续透传实例原值。
        backup_instance = (
            self.backup_path / "instances" / self.instance_path.name
        )
        base_path = backup_instance if backup_instance.is_file() else self.instance_path
        base = _read_json_object(base_path, label="MFW default 实例配置")
        if self.generated_adb_device is not None:
            base["AdbDevice"] = self.generated_adb_device
            logger.info("MFW 已按 MAS 模拟器配置覆盖 AdbDevice")
        # 归因更正（2026-08-29 静态审计）：本键在参考包的六份真实实例样本中都不存在，
        # 三份 MFAAvalonia.Core.dll 里也搜不到该字面量——「外壳的连接目标取自
        # Connect.Address」这一说法证据不足。当初加它是为了修「未选择连接目标」，
        # 但同一轮实测证明真正生效的是 BeforeTask=StartupSoftwareAndScript（见
        # 上方运行编排注释），本键很可能自始至终对外壳惰性。
        # 暂不删除：静态审计无法排除外壳在运行期以字符串拼接读取该键，删除属改变
        # 已验证通过的运行路径。待一次「只写 AdbDevice、不写本键」的真机对照后再定。
        # 已同步收紧的是 _instance_has_adb_device——它不再把本键当作设备标识，
        # 否则 MAS 自己写的残留键会骗过 MAS 自己的启动前守卫。
        if self.emulator_info is not None and self.emulator_info.adb_address != "Unknown":
            base["Connect.Address"] = self.emulator_info.adb_address
            logger.info(f"MFW 已写入连接目标：{self.emulator_info.adb_address}")

        instance_config = build_instance_config(
            self.interface_model,
            controller_name=self.controller_name,
            resource_name=self.resource_name,
            selected_tasks=self.task_selections,
            base=base,
            # 「摘取+适配」自 M9A AutoProxy.build_config（AutoProxy.py:983-986）：
            # BeforeTask=StartupSoftwareAndScript 让外壳自行完成「连接设备 → 跑队列」。
            # 实测（D:/MAS/tmp/m9a-test）：BeforeTask="None" 时 --autostart 触发的
            # op=StartTask 在设备未选中前即被拒（「未选择连接目标」，device=<none>）；
            # 改为 StartupSoftwareAndScript 后同样参数进入 op=ExecuteTaskQueue，
            # 由外壳自行连接。SoftwarePath 恒为空串——模拟器归 MAS 的 EmulatorManager
            # 管，不让外壳重复启动（外壳日志：「已跳过启动程序，因为 SoftwarePath 为空」）。
            # AfterTask 仍用 "None"（默认）：本层集中管理外壳/模拟器生命周期，
            # 让外壳自关会与 _wait_for_terminal 的日志判定、_teardown_* 的模拟器
            # 归属产生竞态与冲突，故不采用 M9A 的 CloseEmulatorAndMFA。
            orchestration=InstanceOrchestration(
                instance_name="MAS",
                before_task="StartupSoftwareAndScript",
                software_path="",
            ),
        )

        self.instances_dir.mkdir(parents=True, exist_ok=True)
        for json_file in self.instances_dir.glob("*.json"):
            if json_file.is_symlink() or not json_file.is_file():
                raise RuntimeError(f"MFW instances 条目不是普通文件：{json_file}")
            json_file.unlink()
        self._write_shell_config(self.instance_path, instance_config, label="实例配置")

        shell_config = _read_json_object(self.config_json_path, label="MFW config.json")
        shell_config.update(
            {
                # 静默：不让外壳窗口抢焦点。
                "AutoMinimize": True,
                "AutoHide": True,
                "ShouldMinimizeToTray": True,
                # 关掉外壳自己的更新：更新归 MAS 控制（本层已有
                # POST /api/scripts/maafw/update），外壳同时更新会与之抢同一批文件，
                # 还会把运行时间拖长、失败时污染判定——2026-08-29 真机日志里就有
                # 「获取资源包下载信息失败：来源=Mirror」直接抛异常那一段。
                # 键名取自靶子真实 config.json：EnableCheckVersion 对应「自动检测
                # 更新」、EnableAutoUpdateResource 对应「自动更新资源」，
                # EnableAutoUpdateMFA 是外壳自更新（样本里已为 False，仍显式压住）。
                # 无需显式恢复：整个 config/ 目录在收尾时按备份还原，比 M9A 专项
                # 的 _set_m9a_auto_update(True) 更准——后者会把用户原本关着的开关
                # 无条件打开。
                "EnableCheckVersion": False,
                "EnableAutoUpdateResource": False,
                "EnableAutoUpdateMFA": False,
                # 关掉外壳自己的外部通知：通知归 MAS（本层跑完会发运行报告），
                # 留着外壳那份就是同一轮发两遍。真机上它还必然报错——这个字段存
                # 的是 provider 名（样本里是 CustomWebhook），URL 走 DPAPI 加密，
                # 而 DPAPI 绑用户+机器，项目目录一旦换过位置就解不开，收尾必然
                # 抛「通用Webhook URL不能为空」（2026-08-29 真机日志里就有）。
                # 未配置过的外壳压根没有这个键（MaaKes 参考包即如此），故空串就是
                # 「没有选择任何 provider」。同样无需显式恢复：整个 config/ 目录在
                # 收尾时按备份还原。
                "ExternalNotificationEnabled": "",
            }
        )
        self._write_shell_config(self.config_json_path, shell_config, label="外壳 config.json")
        logger.info(f"MFW 运行配置已写入：{self.instance_path}")

    def _write_shell_config(self, path: Path, payload: dict, *, label: str) -> None:
        """写外壳配置并**回读确认**落盘。

        外壳启动后会自己写同一批文件；真机上出现过外壳
        「配置保存失败：default.json ... being used by another process」。本层这边
        用的是 mkstemp + os.replace，句柄都随 with 关闭，起壳之后也不再碰
        config/ —— 但「我这边没问题」是推断，不是证据。回读一次把它变成证据：
        确认替换已经落地、文件此刻可读、且内容就是刚写进去的那份。

        对不上不抛异常：配置已经写出去了，外壳多半能正常读到；这里只留一条告警，
        免得把一次本可以跑完的运行判死在一个存疑的自检上。
        """

        snapshot = atomic_write_maafw_config(path, payload, journal=False)
        try:
            verified = read_maafw_config_snapshot(path)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"MFW {label} 写入后回读失败：{exc}")
            return
        if verified.revision != snapshot.revision:
            logger.warning(f"MFW {label} 写入后回读内容不一致：{path}")

    async def _run_external(self) -> None:
        profile = self.log_profile
        if self.exe_path is None or profile is None:
            raise RuntimeError("MFW 外壳路径或日志画像未初始化")

        # 按「本用户开跑的时刻」重算日志路径：队列跨零点后外壳会写到新的
        # log-<新日期>.log，而此前整轮沿用 check() 那一次算出的旧文件名，
        # LogMonitor 只会盯着昨天那个不再增长的文件空转 → last_log_at 冻结 →
        # RunTimeLimit 分钟后把一次正在正常干活的运行误判成超时并杀掉外壳。
        # MXU 的日志文件名带当日启动序号，启动前不可知，故此处可能是 None，
        # 起进程之后再解析（见下方 _resolve_mxu_log_path）。
        self.log_path = self._resolve_log_path()
        self.process_manager = ProcessManager()
        self.log_monitor = LogMonitor(
            profile.time_stamp_range, profile.time_format, self.check_log
        )
        self.terminal_event.clear()
        self.terminal_kind = None
        self.last_log_text = ""
        self.last_log_at = datetime.now()
        self.log_start_time = datetime.now()

        # 自退型外壳（MXU）的运行日志走进程 stdout，故必须接管这条流。
        # MXU 的 log_to_stdout 命令注释写得很直白：「将前端 UI 日志转发到后端
        # stdout，便于终端调试和第三方调度工具读取」—— 它是专门给外部调度器
        # 准备的通道，比盯文件可靠得多：不受日志改名、启动时 auto-clear 清档、
        # 两套日志子系统并存的影响，流结束本身还直接就是「跑完了」。
        stream_stdout = profile.exits_after_run
        await self.process_manager.open_process(
            *self._build_launch_argv(),
            **({"stdout": asyncio.subprocess.PIPE} if stream_stdout else {}),
        )
        self.process_started = True
        self.process_pid = self.process_manager.main_pid
        logger.info(
            f"{self.shell_family.value} 外壳已启动，PID: {self.process_pid}"
        )

        await asyncio.sleep(5)
        if not await self.process_manager.is_running():
            self._mark_terminal("exit", "MFW 进程已异常退出")
            return

        await self._arrange_windows_after_launch()

        if stream_stdout:
            process = self.process_manager.main_process
            if isinstance(process, asyncio.subprocess.Process):
                await self.log_monitor.start_monitor_process(process, "stdout")
                self.monitor_started = True
                await self._wait_for_terminal()
                return
            logger.warning("MFW 未能接管外壳 stdout，回退到日志文件监控")

        if self.log_path is None or not self.log_path.is_file():
            resolved = await self._await_shell_log_path()
            if resolved is not None:
                self.log_path = resolved
        if self.log_path is None:
            # 拿不到日志不再直接判死：外壳已经在跑，且 MXU 带 -q 时进程退出本身
            # 就是完成信号。降级为「只靠进程状态判终态」，把日志当增益而非前提。
            logger.warning("MFW 未能定位外壳日志，改为仅按进程状态判定终态")
            await self._wait_for_terminal()
            return

        await self.log_monitor.start_monitor_file(self.log_path, self.log_start_time)
        self.monitor_started = True
        await self._wait_for_terminal()

    async def _wait_for_terminal(self) -> None:
        if self.process_manager is None:
            raise RuntimeError("MFW 进程管理器未初始化")
        runtime_limit = self._runtime_limit_seconds()
        while not self.terminal_event.is_set():
            if not await self.process_manager.is_running():
                # 让并发中的 monitor callback 有机会先提交完成标记；完成优先于退出。
                await asyncio.sleep(0)
                if self._contains_controller_failure(self.last_log_text):
                    self._mark_controller_failure()
                elif self._contains_completion(self.last_log_text):
                    self._mark_completion(self.last_log_text)
                elif (
                    self.log_profile is not None
                    and self.log_profile.exits_after_run
                ):
                    # MXU 带 -q：跑完自行退出，进程退出**就是**完成信号。
                    # 不能像 MFAAvalonia 那样判「异常退出」——那个家族的外壳
                    # 永不自退，退出确实意味着出事；这个家族反过来。
                    # 仍要过「选中任务是否露过面」这道关，避免空跑被判成功。
                    self._mark_completion(
                        self.last_log_text, evidence="外壳已自行退出"
                    )
                elif any(
                    m in self.last_log_text
                    for m in self._profile_markers("abandon_markers")
                ):
                    self._mark_terminal("abandoned", f"MFW {_ABANDON_MARKER}")
                else:
                    self._mark_terminal("exit", "MFW 进程已异常退出")
                break

            if runtime_limit <= 0 or (
                self.last_log_at is not None
                and (datetime.now() - self.last_log_at).total_seconds() >= runtime_limit
            ):
                self._mark_terminal("timeout", "MFW 进程超时")
                break
            await asyncio.sleep(1)

    def _profile_markers(self, field: str) -> tuple[str, ...]:
        """取当前外壳家族的判据串；画像缺失时退回 MFAAvalonia 的模块常量。"""

        profile = self.log_profile
        if profile is None:
            return {
                "completion_markers": _COMPLETION_MARKERS,
                "abandon_markers": (_ABANDON_MARKER,),
                "controller_failure_markers": _CONTROLLER_FAILURE_MARKERS,
                "failure_markers": _FAILURE_MARKERS,
            }.get(field, ())
        return tuple(getattr(profile, field, ()) or ())

    def _contains_completion(self, text: str) -> bool:
        return any(marker in text for marker in self._profile_markers("completion_markers"))

    def _contains_failure(self, text: str) -> bool:
        """外壳判定本次运行失败并停掉队列。

        与完成串同源（都由 MFA 的 Monitor 组件在 op=MonitorLog 下发出），
        语义却相反：完成串是「队列排空」，本串是「跑失败了，不再往下跑」。
        """

        return any(marker in text for marker in self._profile_markers("failure_markers"))

    def _contains_controller_failure(self, text: str) -> bool:
        """控制器初始化失败——外壳未能真正开始执行选中的任务。"""

        return any(
            marker in text
            for marker in self._profile_markers("controller_failure_markers")
        )

    def _mark_controller_failure(self) -> None:
        self._mark_terminal(
            "controller_failed",
            "MFW 控制器初始化失败，任务未实际执行",
        )

    def _mark_completion(self, log_text: str, *, evidence: str = "输出完成串") -> None:
        """完成信号出现时收口：选中任务全部在日志里露过面才判成功。

        弱形式的逐任务校验——只回答「选中的事到底有没有被尝试」。实测的假成功里
        选中任务在整份日志出现 0 次，完成串却存在。不解析逐任务成功/失败：没有一次
        成功运行的样本，任何日志格式假设都是臆造。

        ``evidence`` 是「凭什么认为跑完了」的说法，会进用户可见的报错。自退型外壳
        （MXU 带 -q）走的是「进程干净退出」这条证据，日志里并没有完成串；沿用默认
        说法会把用户引向错误的排查方向。
        """

        absent = self._selected_tasks_absent(log_text)
        if absent:
            self._mark_terminal(
                "tasks_missing",
                f"MFW {evidence}，但选中任务未出现：{'、'.join(absent)}",
            )
        elif self._contains_failure(log_text):
            # 队列跑到了排空，但中途有任务失败（ContinueRunningWhenError=True 时
            # 外壳会跳过失败任务继续跑）。选中任务都露过面，只是没全成——
            # 这不是成功。
            self._mark_terminal("failed", "MFW 队列已跑完，但其中有任务失败")
        else:
            self._mark_terminal("success", "Success!")

    def _selected_tasks_absent(self, log_text: str) -> list[str]:
        """按外壳家族选择「选中任务是否露过面」的判据。

        MFAAvalonia 的 UI 日志打的是任务**显示名**（「开始任务：启动游戏」），
        走受保护的 _selected_tasks_absent_from。

        MXU 两种都会遇到：stdout 上是显示名（「任务开始: CreditShoppingN2」），
        落盘那份打的是 entry（「任务[0]: entry=CreditShoppingMain」）。两者常常
        不同——实测 MaaYYs 只有 10/27、MaaEnd 只有 6/41 的 name 与 entry 相同——
        所以只认一种都会误判，走两者取或的版本。
        """

        if self.shell_family is ShellFamily.MXU:
            return self._selected_entries_absent_from(log_text)
        return self._selected_tasks_absent_from(log_text)

    def _selected_entries_absent_from(self, log_text: str) -> list[str]:
        """选中任务的**任何一种写法**都没在日志里出现过的那些（MXU 用）。

        与显示名版同构：只回答「选中的事有没有被尝试」，不解析逐任务成败。

        为什么要收集多种写法：外壳按自己的界面语言打任务名。中文界面是
        「任务开始: 信用点购物」，英文界面是「Task started: 🛍️ Credit Shopping」，
        落盘的调试行又打 entry（`任务[0]: entry=CreditShoppingMain`），而 MAS 手里
        存的是 name（`CreditShoppingN2`）—— 四者互不相同。只认一种，换个界面语言
        就会把跑成功的运行误判成「选中任务未出现」（2026-08-29 真机实测，外壳跑
        的是英文界面）。

        别名表由本层从 interface 与**全部**语言文件算出，不必猜外壳当前用哪种语言。
        算不出别名（无 interface / 语言文件缺失）时退回只比任务名，不静默跳过。
        """

        aliases = self._task_alias_index()
        absent: list[str] = []
        for selection in self.task_selections:
            name = selection.name.strip() if isinstance(selection.name, str) else ""
            if not name:
                continue
            probes = aliases.get(name) or (name,)
            if not any(probe in log_text for probe in probes):
                absent.append(name)
        return absent

    def _task_alias_index(self) -> dict[str, tuple[str, ...]]:
        """任务名 → 全部可能写法，按项目缓存一次。

        要读全部语言文件，比逐次现算便宜；interface 换了（换项目/重载）就重建。
        失败一律退回空表，由调用方按「只比任务名」处理。
        """

        if self.interface_model is None or self.project_root is None:
            return {}
        token = (str(self.project_root), id(self.interface_model))
        if self._alias_index_token != token:
            try:
                self._alias_index = build_task_alias_index(
                    self.project_root, self.interface_model
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"MFW 任务别名表构建失败，退回按任务名匹配：{exc}")
                self._alias_index = {}
            self._alias_index_token = token
        return self._alias_index

    def _selected_tasks_absent_from(self, log_text: str) -> list[str]:
        """选中任务名里在整份日志中从未以子串形式出现过的那些。

        空串或非字符串的异常选择项跳过，不纳入判断也不崩溃。
        """

        absent: list[str] = []
        for selection in self.task_selections:
            name = selection.name.strip() if isinstance(selection.name, str) else ""
            if name and name not in log_text:
                absent.append(name)
        return absent

    def _runtime_limit_seconds(self) -> float:
        if self.script_config is None:
            return 0
        value = self.script_config.get("Run", "RunTimeLimit")
        try:
            return float(value) * 60
        except (TypeError, ValueError):
            return 0

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """保存实际日志，并按稳定完成/放弃串更新终态。"""

        current_user = self._ensure_virtual_user()
        if self.current_log is None:
            self.current_log = LogRecord()
            start_time = self.log_start_time or datetime.now()
            current_user.log_record[start_time] = self.current_log

        lines = list(log_content)
        log_text = "".join(lines)
        self.current_log.content = lines
        self.script_info.log = log_text
        if log_text != self.last_log_text:
            # 空闲时钟只认「有实质新增」，不认外壳的周期性自娱自乐行。
            # upstream issue #388：MFA 的内存清理会让 UI 日志持续滚动，此前任何
            # 一行新日志都会重置空闲时钟，RunTimeLimit 超时因而形同虚设。
            # 只改这一处：展示（script_info.log）与终态判定（下方受保护分支）
            # 仍吃完整 log_text，两路互不污染。
            if self._has_substantive_progress(self.last_log_text, log_text):
                self.last_log_at = datetime.now()
            self.last_log_text = log_text

        # 控制器初始化失败压过完成串：外壳排空队列时照样输出完成串，但选中的任务
        # 从未执行，此时判成功是假成功。完成串本身还要过 _mark_completion 里「选中
        # 任务是否露过面」这道关，都通过才判成功。其次完成串优先于放弃串。
        if self._contains_controller_failure(log_text):
            self._mark_controller_failure()
        elif self._contains_completion(log_text):
            self._mark_completion(log_text)
        elif any(m in log_text for m in self._profile_markers("abandon_markers")):
            self._mark_terminal("abandoned", f"MFW {_ABANDON_MARKER}")
        elif self.terminal_kind is None:
            self.current_log.status = "MFW 正常运行中"

    @staticmethod
    def _has_substantive_progress(previous: str, current: str) -> bool:
        """本次新增的日志里，是否有不属于外壳周期性噪音的行。

        噪音串取自画像表的 ``idle_noise_markers``（MFAAvalonia 已按真实 M9A 日志
        登记内存清理与热键 IPC 两类；MXU 无真机样本，留空即退化为「任何新增都算
        实质进展」，与本次修复前的行为一致）。

        日志文件被轮转或截断时（新内容不以旧内容为前缀）无法可靠取增量，
        一律按有实质进展处理——宁可少判一次超时，也不要把正在干活的运行杀掉。
        """

        profile = get_shell_log_profile(ShellFamily.MFAAVALONIA)
        markers = profile.idle_noise_markers if profile is not None else ()
        if not markers:
            return True
        if not current.startswith(previous):
            return True
        added = current[len(previous):]
        return any(
            line.strip() and not any(marker in line for marker in markers)
            for line in added.splitlines()
        )

    def _mark_terminal(self, kind: str, log_status: str) -> None:
        # 按优先级收口：controller_failed > success > 其余。同级或更低不覆盖已有终态，
        # 保证先到的结论稳定；更高优先级可以推翻已提交的结论（假成功必须能被纠正）。
        if self.terminal_kind is not None and _TERMINAL_PRIORITY.get(
            kind, 1
        ) <= _TERMINAL_PRIORITY.get(self.terminal_kind, 1):
            return
        self.terminal_kind = kind

        current_user = self._ensure_virtual_user()
        if self.current_log is None:
            self.current_log = LogRecord()
            start_time = self.log_start_time or datetime.now()
            current_user.log_record[start_time] = self.current_log
        self.current_log.status = log_status
        current_user.status = "完成" if self.terminal_kind == "success" else "异常"
        self.terminal_event.set()
        logger.info(f"MFW 任务终态：{self.terminal_kind} ({log_status})")

    async def _cleanup(self) -> None:
        """幂等清理：停 monitor、杀进程、恢复项目配置、解锁 MAS 配置。"""

        if self.cleanup_done and self.restored:
            return
        errors: list[str] = []

        if self.log_monitor is not None:
            try:
                await self.log_monitor.stop()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"停止日志监控失败：{exc}")
                logger.opt(exception=True).warning(f"停止 MFW 日志监控失败：{exc}")
            self.monitor_started = False

        if self.process_manager is not None:
            try:
                await self.process_manager.kill()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"结束进程管理器失败：{exc}")
                logger.opt(exception=True).warning(f"结束 MFW 进程失败：{exc}")

        needs_restore = not self.restored and (
            self.backup_published or self.manifest_path.exists()
        )
        process_stopped = True
        if (self.process_started or needs_restore) and self.exe_path is not None:
            try:
                process_stopped = await System.kill_process(self.exe_path)
                if not process_stopped:
                    errors.append("强制结束外壳失败：无法确认目标进程已结束")
            except Exception as exc:  # noqa: BLE001
                process_stopped = False
                errors.append(f"强制结束外壳失败：{exc}")
                logger.opt(exception=True).warning(f"强制结束 MFAAvalonia.exe 失败：{exc}")

        if needs_restore and process_stopped:
            try:
                await asyncio.to_thread(self._restore_backup_from_state)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"恢复 MFW 配置失败：{exc}")
                logger.opt(exception=True).warning(f"恢复 MFW 配置失败：{exc}")
        elif needs_restore:
            errors.append("外壳仍可能运行；为避免并发写入，已保留 MFW 配置备份")

        script_config = self.script_config
        if script_config is not None and script_config.is_locked:
            try:
                await script_config.unlock()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"解锁 MFW 配置失败：{exc}")
                logger.opt(exception=True).warning(f"解锁 MFW 配置失败：{exc}")

        self.cleanup_error = "；".join(errors) if errors else None
        self.cleanup_done = not errors and self.restored

    async def _await_cleanup(self) -> None:
        """等待独立清理任务，即使父任务正在取消也不提前返回。"""

        if self.cleanup_task is None or (
            self.cleanup_task.done() and not self.cleanup_done
        ):
            self.cleanup_task = asyncio.create_task(self._cleanup())

        current_task = asyncio.current_task()
        if current_task is None:
            raise RuntimeError("无法获取当前任务")

        cancellation: asyncio.CancelledError | None = None
        while not self.cleanup_task.done():
            try:
                await asyncio.shield(self.cleanup_task)
            except asyncio.CancelledError as exc:
                cancellation = exc
                while current_task.cancelling():
                    current_task.uncancel()

        self.cleanup_task.result()
        if cancellation is not None:
            raise cancellation

    # ---- 周期性跳过：语义照搬 mfwa tools/AutoProxy.py ----

    def _load_period_task_records(self) -> dict[str, dict[str, str]]:
        """读取当前用户的 Data.PeriodTaskRecords，规整为 daily/weekly/monthly 三段。"""

        raw_records = _load_json_dict(
            self.current_user_config.get("Data", "PeriodTaskRecords")
            if self.current_user_config is not None
            else None
        )
        records: dict[str, dict[str, str]] = {"daily": {}, "weekly": {}, "monthly": {}}
        for period in records:
            raw_period_records = raw_records.get(period, {})
            if isinstance(raw_period_records, dict):
                records[period] = {
                    str(task_name): str(period_key)
                    for task_name, period_key in raw_period_records.items()
                }
        return records

    def _filter_period_once_tasks(
        self, task_names: list[str]
    ) -> tuple[list[str], list[str]]:
        """按脚本级 每日/每周/每月 一次配置与用户级完成记录过滤任务。

        返回 (runnable, skipped)：与 mfwa ``_filter_period_once_tasks`` 同语义，
        本层作用于任务名列表而非 run plan。
        """

        daily_tasks = set(
            _load_json_list(self.script_config.get("Run", "DailyOnceTasks"))
        )
        weekly_tasks = set(
            _load_json_list(self.script_config.get("Run", "WeeklyOnceTasks"))
        )
        monthly_tasks = set(
            _load_json_list(self.script_config.get("Run", "MonthlyOnceTasks"))
        )
        if not daily_tasks and not weekly_tasks and not monthly_tasks:
            return list(task_names), []

        daily_key, weekly_key, monthly_key = _current_period_keys()
        records = self._load_period_task_records()
        runnable: list[str] = []
        skipped: list[str] = []
        for name in task_names:
            daily_done = (
                name in daily_tasks and records["daily"].get(name) == daily_key
            )
            weekly_done = (
                name in weekly_tasks and records["weekly"].get(name) == weekly_key
            )
            monthly_done = (
                name in monthly_tasks and records["monthly"].get(name) == monthly_key
            )
            if daily_done or weekly_done or monthly_done:
                skipped.append(name)
            else:
                runnable.append(name)
        return runnable, skipped

    async def _mark_period_tasks_completed(self, completed_tasks: list[str]) -> None:
        """把本次正常完成的任务写入用户级 Data.PeriodTaskRecords。"""

        if not completed_tasks or self.current_user_config is None:
            return

        daily_tasks = set(
            _load_json_list(self.script_config.get("Run", "DailyOnceTasks"))
        )
        weekly_tasks = set(
            _load_json_list(self.script_config.get("Run", "WeeklyOnceTasks"))
        )
        monthly_tasks = set(
            _load_json_list(self.script_config.get("Run", "MonthlyOnceTasks"))
        )
        if not daily_tasks and not weekly_tasks and not monthly_tasks:
            return

        daily_key, weekly_key, monthly_key = _current_period_keys()
        completed_task_names = set(completed_tasks)
        records = self._load_period_task_records()
        changed = False

        for task_name in completed_task_names.intersection(daily_tasks):
            if records["daily"].get(task_name) != daily_key:
                records["daily"][task_name] = daily_key
                changed = True
        for task_name in completed_task_names.intersection(weekly_tasks):
            if records["weekly"].get(task_name) != weekly_key:
                records["weekly"][task_name] = weekly_key
                changed = True
        for task_name in completed_task_names.intersection(monthly_tasks):
            if records["monthly"].get(task_name) != monthly_key:
                records["monthly"][task_name] = monthly_key
                changed = True

        if changed:
            await self.current_user_config.set(
                "Data",
                "PeriodTaskRecords",
                json.dumps(records, ensure_ascii=False),
            )

    def _build_launch_argv(self) -> list[Any]:
        """按外壳家族拼启动参数。

        MFAAvalonia：只指定活动实例，**不传 --autostart**。实测（m9a-test，
        非提权 MuMu）该参数走 StartCommandLineAutoRun 直接 StartTask()，跳过
        TryReadAdbDeviceFromConfig / WaitSoftware，Config.AdbDevice 永不填充，
        控制器初始化即报 AdbSerial 为空。自动运行由实例配置的
        BeforeTask=StartupSoftwareAndScript 驱动。

        MXU：反过来，命令行才是可靠入口。外壳内嵌帮助文本与前端判定逻辑显示
        自动执行的门是 ``(传了 --autostart || settings.autoRunOnLaunch) &&
        (匹配到的实例 || settings.autoStartInstanceId)``；``-i`` 按**实例显示名**
        匹配且仅在 ``--autostart`` 下生效，``-q`` 让外壳在任务完成后自行退出——
        进程退出因此成为本家族最硬的终态信号。
        """

        if self.exe_path is None:
            raise RuntimeError("MFW 外壳可执行文件未初始化")
        if self.shell_family is ShellFamily.MXU:
            return [
                self.exe_path,
                "--autostart",
                "-i",
                _MXU_INSTANCE_NAME,
                "-q",
            ]
        if self.instance_path is None:
            raise RuntimeError("MFW 活动实例未初始化")
        return [self.exe_path, "--instance", self.instance_path.stem]

    async def _arrange_windows_after_launch(self) -> None:
        """外壳起来之后整理窗口：静默则收起外壳，PC 游戏则把游戏顶到前台。

        顺序与 MaaEnd 专项一致（AutoProxy.py:267-278）：起游戏 → 起外壳 →
        把游戏窗口置前。Win32 控制器是对着窗口截图与操作的，外壳自己的窗口刚
        弹出来会压在游戏上面；专项就是靠这一步保证被操作的是游戏而不是外壳。
        模拟器路径不需要——那条链路的可见性由 EmulatorManager.setVisible 管。

        整段自保护：窗口调度失败不影响任务本身，只告警。
        """

        with suppress(Exception):
            if Config.get("Function", "IfSilence") and self.process_manager is not None:
                if await self.process_manager.minimize_window():
                    logger.info("MFW 静默模式：已收起外壳窗口")

        if self.game_launch_spec is None:
            return
        try:
            pid = self._resolve_game_pid()
            if pid is None:
                logger.warning("MFW 未能定位 PC 游戏进程，跳过窗口置前")
                return
            # 不下沉到工作线程：AttachThreadInput 是按调用线程生效的，
            # 与 ProcessManager.activate_window 保持同一线程语义（MaaEnd
            # 专项就是这么用的）。EnumWindows 只遍历顶层窗口，毫秒级。
            if activate_window_by_pid(pid):
                logger.info(f"MFW 已将 PC 游戏窗口置前：pid={pid}")
            else:
                logger.warning(f"MFW 置前 PC 游戏窗口失败：pid={pid}")
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(f"MFW 整理窗口时出错：{exc}")

    def _resolve_game_pid(self) -> int | None:
        """取「实际游戏」进程 pid。

        启动器模式下 MAS 起的是启动器，真正要置前的是它拉起来的游戏本体，
        故优先用 client_identity；AttachOnly 模式用 ``_prepare_desktop_game``
        扫描时记下的 pid。

        刻意**不**在这里再调一次 ``find_client_process``：那是一次全进程枚举
        （每个进程都要取 exe 路径），启动准备阶段刚做过，重复一遍既慢又没有
        新信息。拿不到就返回 None，由调用方降级为「不置前」。
        """

        owned = self.game_owned_process
        if owned is not None:
            if owned.client_identity:
                return int(owned.client_identity[0])
            if owned.pid:
                return int(owned.pid)
        return self.game_attached_pid

    async def _await_shell_log_path(self) -> Path | None:
        """外壳起来之后再定位日志文件，并等它出现。

        必须**等**而不是一次性探：外壳创建日志需要时间，起进程后立刻去找会扑空，
        而扑空一次就让整个用户失败（2026-08-29 实测 MaaEnd 就是这样炸的）。

        MXU 有两种命名并存，同一个安装目录里都可能碰到：
        - 当前版本（MXU@2.4.1）：固定名 ``debug/mxu-tauri.log``
        - 旧版：``debug/<日期>-<序号>.log``，序号是当日启动序号，启动前不可知

        轮询按**次数**计而不是墙钟 deadline：本仓测试统一把 ``asyncio.sleep`` 打成
        空转，墙钟写法会让每个用例真的空转满 30 秒（一次改动就把 external_manager
        那 82 个用例从秒级拖到半小时）。按次数计则在测试里瞬间走完，生产里仍是
        ``间隔 × 次数`` 的真实等待。
        """

        profile = self.log_profile
        if self.project_root is None or profile is None:
            return None

        fallback: Path | None = None
        if profile.log_relpath_strftime:
            fallback = self.project_root / resolve_log_relpath(profile, datetime.now())
        log_dir = (
            self.project_root / profile.log_glob_dir if profile.log_glob_dir else None
        )

        attempts = max(
            1, int(_SHELL_LOG_WAIT_SECONDS / _SHELL_LOG_PROBE_INTERVAL_SECONDS)
        )
        for attempt in range(attempts):
            # glob 优先：登记了 glob 目录的家族（MXU），判据串只出现在那份按当日
            # 启动序号命名的日志里；确定性路径那份是另一个子系统写的，没有判据串。
            # 没登记 glob 目录的家族（MFAAvalonia）直接落到确定性路径，行为不变。
            if log_dir is not None and log_dir.is_dir():
                today = datetime.now().strftime("%Y-%m-%d")
                picked = pick_latest_mxu_log(
                    [path.name for path in log_dir.glob("*.log")], today
                )
                if picked is not None:
                    logger.info(f"MFW 已定位外壳日志：{picked}")
                    self._apply_fallback_log_timestamps()
                    return log_dir / picked
            if fallback is not None and fallback.is_file():
                logger.info(f"MFW 已定位外壳日志（兜底）：{fallback.name}")
                self._apply_fallback_log_timestamps()
                return fallback
            if attempt + 1 < attempts:
                await asyncio.sleep(_SHELL_LOG_PROBE_INTERVAL_SECONDS)

        logger.warning(
            f"MFW 等待外壳日志超时（{_SHELL_LOG_WAIT_SECONDS}s）："
            f"{log_dir if log_dir is not None else fallback}"
        )
        return None

    def _apply_fallback_log_timestamps(self) -> None:
        """落到日志文件时，把 LogMonitor 的时间切片换成文件那套格式。

        自退型外壳的首选来源是进程 stdout，行首是 `[日期 时间.毫秒]`；落盘的那份
        由另一个子系统写，行首无方括号无毫秒。不换切片的话一行都解析不出来，
        ``if_log_start`` 永远为假 —— 外壳明明在跑，MAS 却读不到任何一行。

        画像没登记这对字段的家族（MFAAvalonia）是空操作。
        """

        profile = self.log_profile
        if profile is None or self.log_monitor is None:
            return
        if profile.fallback_time_stamp_range is None or not profile.fallback_time_format:
            return
        self.log_monitor.time_start = profile.fallback_time_stamp_range[0]
        self.log_monitor.time_end = profile.fallback_time_stamp_range[1]
        self.log_monitor.time_format = profile.fallback_time_format

    def _resolve_log_path(self) -> Path | None:
        """按当前时刻解析外壳日志文件路径。

        走 ``profile.resolve_log_relpath``，让「日志布局」这件事只有画像表一个
        事实来源；MFAAvalonia 是按日期确定的 ``logs/log-%Y%m%d.log``，
        MXU 那类需启动后 glob 的外壳返回 ``None``，由 ``_resolve_mxu_log_path``
        在起进程之后补上。

        必须**按用户开跑时刻**调用，不能整轮复用 check() 那一次的结果：队列跨零点
        后外壳写的是新日期的文件。
        """

        if self.project_root is None:
            return None
        profile = self.log_profile or get_shell_log_profile(ShellFamily.MFAAVALONIA)
        if profile is None:
            return None
        relpath = resolve_log_relpath(profile, datetime.now())
        return None if relpath is None else self.project_root / relpath

    async def _mark_user_run_crashed(self, index: int, exc: Exception) -> None:
        """单个用户运行中途抛异常时，把失败收敛到该用户身上。

        此前用户循环没有任何 try/except：``_write_runtime_config`` 的
        ``RuntimeError`` / ``ShellMappingError`` / ``PermissionError``、或
        ``_run_external`` 起进程的 ``OSError`` 一旦逃逸，就会中止**剩余全部用户**
        并落进 ``on_crash``，未跑过的用户再被 ``final_task`` 从「等待」统一改判
        「异常」。这与 ``_run_user`` 内已有的三条「单用户失败只跳过该用户」出口
        自相矛盾，本函数把两者对齐。

        刻意不走 ``_mark_terminal``：未登记的 kind 按优先级 1 处理、无法覆盖已
        存在的 ``terminal_kind``，异常若发生在终态已定之后会被静默丢弃；而且那
        一组函数经两轮加固并有变异测试守护，不应为本路径改动。这里直接写用户级
        状态与 ``LogRecord``，让历史记录与任务报告都能看到这次失败。
        """

        user_item = (
            self.script_info.user_list[index]
            if index < len(self.script_info.user_list)
            else self.current_user_item
        )
        logger.opt(exception=True).warning(
            f"MFW 用户 {getattr(user_item, 'name', '?')} 运行异常，"
            f"跳过该用户继续后续队列：{exc}"
        )
        if user_item is None:
            return

        user_item.status = "异常"
        if self.current_log is None:
            self.current_log = LogRecord()
            start_time = self.log_start_time or datetime.now()
            user_item.log_record[start_time] = self.current_log
        self.current_log.status = f"MFW 用户运行异常：{exc}"

        with suppress(Exception):
            if self.current_user_config is not None:
                await self.current_user_config.set("Data", "LastProxyStatus", "失败")
        with suppress(Exception):
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": f"MFW 用户 {user_item.name} 运行异常：{exc}"},
            )

    async def _mark_run_started(self) -> None:
        """写入用户级本次运行的 LastProxyDate / ProxyTimes / LastProxyStatus。"""

        if self.current_user_config is None:
            return
        if self.current_user_config.get("Data", "LastProxyDate") != self.curdate:
            await self.current_user_config.set("Data", "LastProxyDate", self.curdate)
            await self.current_user_config.set("Data", "ProxyTimes", 0)
        await self.current_user_config.set("Data", "LastProxyStatus", "运行中")

    # ---- 逐用户运行 ----

    def _reset_user_run_state(self) -> None:
        """清掉上一个用户遗留的单轮运行状态。"""

        self.current_log = None
        self.terminal_kind = None
        self.process_manager = None
        self.log_monitor = None
        self.process_started = False
        self.process_pid = None
        self.monitor_started = False
        self.last_log_text = ""

    async def _teardown_shell_between_users(self) -> None:
        """结束当前用户的外壳与日志监控，给下一个用户留干净环境。"""

        if self.log_monitor is not None:
            with suppress(Exception):
                await self.log_monitor.stop()
            self.monitor_started = False
        if self.process_manager is not None:
            with suppress(Exception):
                await self.process_manager.kill()
        if self.process_started and self.exe_path is not None:
            # 按路径杀是全产品统一约定（MAA / M9A / HSR / General 皆同），也是本层
            # 唯一的孤儿外壳兜底，行为不改；但返回值此前被整段丢弃，下一个用户可能
            # 在外壳还没停住的情况下开跑，且无迹可循。这里只补可观测性。
            try:
                if not await System.kill_process(self.exe_path):
                    logger.warning(
                        f"MFW 用户间收尾未能确认外壳已停止：{self.exe_path}，"
                        "下一个用户可能与残留外壳争用同一份配置"
                    )
            except Exception as exc:  # noqa: BLE001
                logger.opt(exception=True).warning(f"MFW 用户间收尾杀进程异常：{exc}")
        await self._teardown_launch_preparation()

    # ---- 运行前启动准备：按控制器类型起模拟器 / PC 游戏 ----

    def _controller_type(self, controller_name: str | None) -> str | None:
        """从 interface 取该 controller 的类型（Adb / Win32 / ...）。"""

        if self.interface_model is None or not controller_name:
            return None
        return next(
            (
                item.type
                for item in self.interface_model.controller
                if item.name == controller_name
            ),
            None,
        )

    @staticmethod
    def _get_emulator_selection(
        script_config: MaaFWConfig | None,
    ) -> tuple[str, str] | None:
        """返回完整的 MAS 模拟器选择；未完整登记时返回 ``None``。"""

        if script_config is None:
            return None
        emulator_id = str(script_config.get("Emulator", "Id") or "").strip()
        emulator_index = str(script_config.get("Emulator", "Index") or "").strip()
        if emulator_id in ("", "-") or emulator_index in ("", "-"):
            return None
        return emulator_id, emulator_index

    async def _prepare_launch_for_user(self, controller_name: str | None) -> str | None:
        """启动外壳之前的启动准备。

        返回 ``None`` 表示已就绪、可进外壳；返回字符串表示失败原因，调用点据此把
        用户标记为异常并跳过外壳启动（绝不落到 controller_failed）。

        - ``Adb``   → 起脚本级模拟器（``EmulatorManager.open``），摘自 M9A 专项
        - ``Win32`` → ``resolve_game_launch_spec`` → ``validate_game_launch_spec``
          → ``launch_game``，复用已迁入的 ``game_lifecycle``
        - 其他控制器类型 → 不做启动准备，直接进外壳（保持现有行为）
        """

        controller_type = self._controller_type(controller_name)
        if controller_type == "Adb":
            return await self._prepare_emulator()
        if controller_type == "Win32":
            return await self._prepare_desktop_game()
        return None

    async def _prepare_emulator(self) -> str | None:
        """Adb 控制器：起脚本级模拟器。摘自 M9A ``AutoProxy.py`` 并适配本层。"""

        if self.script_config is None:
            return "MFW 脚本配置未加载"
        emulator_selection = self._get_emulator_selection(self.script_config)
        if emulator_selection is None:
            # 未配置 MAS 模拟器。check() 中受保护的启动前 Adb 设备校验已确认活动
            # 实例带有设备标识（AdbDevice）——缺标识的情况早在
            # check() 就被明确拒绝。这里是「用户自行在外壳侧连接、自行管理模拟器」
            # 的既有放行场景：不是静默跳过，显式记录后沿用实例已有连接。
            logger.info(
                "MFW 未配置 MAS 模拟器，跳过自动启动，沿用活动实例已有的设备连接"
            )
            self.emulator_info = None
            self.maafw_device = None
            self.generated_adb_device = None
            return None
        emulator_id, emulator_index = emulator_selection

        try:
            if self.emulator_manager is None:
                self.emulator_manager = await EmulatorManager.get_emulator_instance(
                    emulator_id
                )
            self.script_info.log = "正在启动模拟器"
            self.emulator_info = await self.emulator_manager.open(emulator_index)
            self.emulator_opened = True
            self.emulator_index = emulator_index
            self.generated_adb_device = await self._build_adb_device_config(
                self.emulator_info,
                emulator_id,
                emulator_index,
                self.emulator_manager,
            )
            await self._wait_for_adb_ready(self.generated_adb_device)
            await self._resolve_maafw_device()
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(f"MFW 模拟器启动失败：{exc}")
            with suppress(Exception):
                if self.emulator_manager is not None:
                    await self.emulator_manager.close(emulator_index)
            self.emulator_opened = False
            self.emulator_info = None
            self.maafw_device = None
            self.generated_adb_device = None
            return f"模拟器启动失败：{exc}"

        if Config.get("Function", "IfSilence"):
            with suppress(Exception):
                await self.emulator_manager.setVisible(emulator_index, False)
        return None

    async def _resolve_maafw_device(self) -> None:
        """用 MaaFramework 自己的枚举，把本轮模拟器解析成一条 ``AdbDevice``。

        MXU 外壳连设备时比的是 **MaaFramework 枚举出来的设备名**（``ldplayer-LDPlayer``、
        ``MuMu安卓设备-MuMuPlayer v5+``），不是本层的模拟器类型串，也不是 adb 地址。
        本层手上只有地址，两者之间的换算是现成的：``MaaFWManager.convert_adb``
        按端口号把 MAS 的 ``DeviceInfo`` 对到 ``Toolkit.find_adb_devices()`` 的结果上
        （``127.0.0.1:5555`` 与 ``emulator-5554`` 归一到同一个端口）。MaaEnd 专项
        (``MaaEnd/AutoProxy.py``) 写 ``savedDevice`` 用的就是这条路径，本层照用。

        放在 ``_wait_for_adb_ready`` 之后：枚举要求设备已经在线，早了扫不到。
        只有 MXU 家族需要这个名字，别的家族不必为此付一次全量枚举的时间。

        这不违反本层「不加载项目 DLL」的约束：枚举 adb 设备用的是 MAS 自带的
        MaaFramework 绑定（M9A、MaaEnd 专项一直在用），碰的是设备而不是项目的
        resource/agent。

        拿不到不是致命错误：清空 ``maafw_device``，由 ``_apply_mxu_saved_device``
        决定降级行为并把原因写进日志。
        """

        self.maafw_device = None
        if self.shell_family is not ShellFamily.MXU:
            return
        info = self.emulator_info
        if info is None or not info.adb_address or info.adb_address == "Unknown":
            return

        from app.core import MaaFWManager

        try:
            self.maafw_device = await MaaFWManager.convert_adb(info)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"MFW 未能把模拟器 {info.adb_address} 解析成 MaaFramework 设备：{exc}"
            )
            return
        logger.info(
            f"MFW 已解析 MaaFramework 设备：{self.maafw_device.name}"
            f"（{self.maafw_device.address}）"
        )

    async def _wait_for_adb_ready(self, adb_device: dict[str, Any] | None) -> None:
        """等到 adb 真的能跑 shell 再把控制权交给外壳。

        模拟器管理器只等到 ldconsole / MuMuManager 报「ONLINE」再 sleep 几秒，
        而那只说明虚拟机起来了，不代表 Android 的 adbd 已经能服务——启动中的
        设备在 ``adb devices`` 里是列得出来的（``offline`` 状态），能枚举、不能
        shell。本层紧接着就裸启动外壳，外壳建控制器时执行
        ``adb -s <serial> shell settings get secure android_id``，拿到非 0 退出码
        就直接判连接失败，而且它的「重连」只隔 200 毫秒，等于没等。

        2026-08-29 真机实测：MAS 交接后 4 秒外壳开连，adb shell **28 毫秒**返回
        退出码 1，两次重试都在同一秒内失败，整轮判 controller_failed。

        因此在交接前自己确认一次。探测失败只告警不拒绝：探测本身可能因 adb 路径
        差异等原因不可用，不该因此挡住原本能跑的运行——真连不上时外壳仍会给出
        controller_failed，判定链路不受影响。
        """

        if not isinstance(adb_device, dict):
            return
        adb_path = str(adb_device.get("AdbPath") or "").strip()
        serial = str(adb_device.get("AdbSerial") or "").strip()
        if not adb_path or not serial:
            return

        deadline = datetime.now() + timedelta(seconds=_ADB_READY_TIMEOUT_SECONDS)
        attempt = 0
        while datetime.now() < deadline:
            attempt += 1
            try:
                result = await ProcessRunner.run_process(
                    adb_path,
                    "-s",
                    serial,
                    "shell",
                    "echo",
                    "maafw-ready",
                    timeout=_ADB_READY_PROBE_TIMEOUT_SECONDS,
                    if_merge_std=True,
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"MFW adb 就绪探测不可用，跳过等待：{exc}")
                return
            if result.returncode == 0 and "maafw-ready" in (result.stdout or ""):
                if attempt > 1:
                    logger.info(f"MFW adb 已就绪（第 {attempt} 次探测）：{serial}")
                return
            await asyncio.sleep(_ADB_READY_PROBE_INTERVAL_SECONDS)

        logger.warning(
            f"MFW 等待 adb 就绪超时（{_ADB_READY_TIMEOUT_SECONDS}s）：{serial}，"
            "仍继续启动外壳；若外壳报控制器初始化失败，多半是模拟器尚未完全启动"
        )

    async def _build_adb_device_config(
        self,
        emulator_info: DeviceInfo,
        emulator_id: str,
        emulator_index: str,
        emulator_manager: Any,
    ) -> dict[str, Any] | None:
        """按 MAS 登记的模拟器类型生成 MFAAvalonia AdbDevice。"""

        try:
            emulator_uid = uuid.UUID(emulator_id)
            emulator_config = Config.EmulatorConfig[emulator_uid]

            emulator_type = emulator_config.get("Info", "Type")
            emulator_path = Path(emulator_config.get("Info", "Path"))

            if emulator_type == "ldplayer":
                return await self._build_ldplayer_config(
                    emulator_info,
                    emulator_path,
                    emulator_index,
                    emulator_manager,
                )
            if emulator_type == "mumu":
                return self._build_mumu_config(
                    emulator_info,
                    emulator_path,
                    emulator_index,
                )
            # 注意这不是罕见分支：EmulatorConfig 的默认类型是 general，而 MaaFW 的
            # 模拟器下拉不按类型过滤，所以「登记了模拟器却生成不出设备配置」是可达的
            # 常规路径。此时沿用实例原有设备字段，而 check() 的设备有效性校验被
            # `emulator_selection is None` 门在外面——即这条路上设备字段全程无人校验，
            # 必须让用户看得见。
            logger.warning(
                f"MFW 无法按模拟器类型 {emulator_type!r} 生成设备配置，"
                "改为沿用实例原有的 AdbDevice；若外壳侧从未连接过设备，"
                "本次运行会在控制器初始化阶段失败"
            )
            return None
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(
                f"MFW 构建 AdbDevice 配置出错，改为沿用实例原有设备字段："
                f"{exc}；该路径不经 check() 的设备校验"
            )
            return None

    async def _build_ldplayer_config(
        self,
        emulator_info: DeviceInfo,
        emulator_path: Path,
        emulator_index: str,
        emulator_manager: Any,
    ) -> dict[str, Any]:
        """构建雷电模拟器 AdbDevice。整体回收自 M9A 专项。"""

        logger.info("构建雷电模拟器 AdbDevice 配置")

        ld_player_device = None
        try:
            devices = await emulator_manager.get_device_info(emulator_index)
            if emulator_index in devices:
                ld_player_device = devices[emulator_index]
                logger.info(
                    "成功获取雷电模拟器设备信息: "
                    f"idx={ld_player_device.idx}, pid={ld_player_device.pid}"
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"获取雷电模拟器设备信息失败: {exc}")

        emulator_root = emulator_path.parent
        adb_path = emulator_root / "adb.exe"
        _warn_if_adb_missing(adb_path, "雷电")

        name = ld_player_device.title if ld_player_device else "雷电模拟器-LDPlayer"
        idx = ld_player_device.idx if ld_player_device else int(emulator_index)
        pid = ld_player_device.pid if ld_player_device else 0

        ld_extras = {
            "enable": True,
            "index": idx,
            "path": str(emulator_root).replace("\\", "/"),
            "pid": pid,
        }

        config_json = json.dumps({"extras": {"ld": ld_extras}}, ensure_ascii=False)

        return {
            "Name": name,
            "AdbPath": str(adb_path).replace("\\", "/"),
            "AdbSerial": f"emulator-{5554 + idx * 2}",
            "ScreencapMethods": 64,
            "InputMethods": 18446744073709551607,
            "Config": config_json,
            "AgentPath": "./MaaAgentBinary",
        }

    def _build_mumu_config(
        self,
        emulator_info: DeviceInfo,
        emulator_path: Path,
        emulator_index: str,
    ) -> dict[str, Any]:
        """构建 MuMu 模拟器 AdbDevice。摘取+适配自 M9A 专项。

        Name 取 ``emulator_info.title``（MuMu 实例真实标题，来自
        ``app/utils/emulator/mumu.py`` ``getInfo``：``name = value["name"]``，
        由 ``MuMuManager.exe info`` 返回），把 MuMu 路径对齐到
        ``_build_ldplayer_config`` 用 ``ld_player_device.title`` 的做法——一致性
        改进：MAS 本就握有真实名字，没有理由在 MuMu 分支硬编码
        ``"MuMu模拟器"``。外壳写入 ``instances/*.json`` 的设备指纹里 Name 段随之
        变为真实标题；这不改变外壳按 Name/Index/Address/Port 多项匹配的语义，
        也不单独承担「外壳连不上设备」的修复。
        """

        logger.info("构建 MuMu 模拟器 AdbDevice 配置")

        shell_dir = emulator_path.parent
        emulator_root = shell_dir.parent
        adb_path = shell_dir / "adb.exe"
        _warn_if_adb_missing(adb_path, "MuMu")

        # MuMuManager 正常必然返回实例名；title 为空/缺失属异常兜底。
        # 不退回硬编码 "MuMu模拟器"——它与雷电分支不一致且丢失实例信息；改用
        # ADB 地址兜底（与另一种枚举名 "127.0.0.1:16384-MuMuPlayer12 …" 同形），
        # 地址不可用时再退到带多开号的名字，并明确告警。
        name = (emulator_info.title or "").strip()
        if not name:
            if emulator_info.adb_address and emulator_info.adb_address != "Unknown":
                name = emulator_info.adb_address
            else:
                name = f"MuMu模拟器-{emulator_index}"
            logger.warning(f"MuMu 实例标题为空，AdbDevice.Name 兜底为 {name}")

        mumu_extras = {
            "enable": True,
            "index": int(emulator_index),
            "path": str(emulator_root).replace("\\", "/"),
        }

        config_json = json.dumps(
            {"extras": {"mumu": mumu_extras}}, ensure_ascii=False
        )

        return {
            "Name": name,
            "AdbPath": str(adb_path).replace("\\", "/"),
            "AdbSerial": emulator_info.adb_address,
            "ScreencapMethods": 64,
            "InputMethods": 18446744073709551607,
            "Config": config_json,
            "AgentPath": "./MaaAgentBinary",
        }

    async def _prepare_desktop_game(self) -> str | None:
        """Win32 控制器：按 ``Game.LaunchMode`` 起 PC 游戏，复用 ``game_lifecycle``。"""

        if self.script_config is None:
            return "MFW 脚本配置未加载"
        try:
            spec = resolve_game_launch_spec(self.script_config)
            validate_game_launch_spec(spec)
        except (TypeError, ValueError) as exc:
            return f"PC 游戏启动配置无效：{exc}"
        self.game_launch_spec = spec

        if spec.mode == "AttachOnly":
            # AttachOnly 不启动进程，但客户端必须已在运行，否则外壳照样连不上窗口
            # → 又一次控制器初始化失败。摘自 mfwa AutoProxy 的 AttachOnly 分支。
            existing = await asyncio.to_thread(find_client_process, spec)
            if existing is None:
                return "PC 游戏 AttachOnly 模式未匹配到已运行的客户端进程，请先启动游戏"
            self.game_attached_pid = existing.pid
            return None

        try:
            preexisting = await asyncio.to_thread(snapshot_matching_processes, spec)
            self.game_owned_process = await launch_game(spec, preexisting=preexisting)
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(f"MFW PC 游戏启动失败：{exc}")
            return f"PC 游戏启动失败：{exc}"
        if not await self._await_game_ready(spec):
            return (
                f"PC 游戏窗口在 {spec.wait_time}s 内没有出现，外壳无法连接到游戏。"
                "请调大「等待时间」，或先手动把游戏开到能操作再跑"
            )
        return None

    async def _await_game_ready(self, spec: MaaFWGameLaunchSpec) -> bool:
        """按「等待时间」等实际游戏进程/窗口出现，再放外壳进场。

        UI 对这个字段的承诺原文就是「启动目标后等待实际游戏进程/窗口出现的时间」，
        但此前 ``wait_time`` 只被解析进 spec，没有任何调用点 —— 起完 exe 立刻就去
        起外壳了。进程创建远早于窗口出现，Endfield 这类游戏中间隔着几十秒。

        **等不到必须判死。** 这条等待是硬门槛，不是尽力而为：本层会摘掉外壳实例的
        ``preActions``（防止外壳重复启动游戏），而外壳那套「等待窗口就绪」循环恰恰
        挂在 preAction 分支上——摘掉之后外壳会直接去连窗口，连不到就一句
        「未找到窗口 X」放弃，不重试。等窗口这件事已经整个落到本层头上，这里放行
        等于让外壳空跑一轮（2026-08-29 真机实测就是这样白跑的）。

        启动器模式还要多一步：MAS 起的是启动器，真正要等的是它拉起来的游戏本体。
        顺手把身份记进 ``client_identity`` —— 窗口置前和结束收尾都按它来，此前这
        个字段从没被赋过值，启动器模式下游戏本体既不会被置前也不会被关闭。

        Returns:
            窗口是否已就绪。``AttachOnly`` / ``URL`` / 等待时间为 0 时视为就绪
            （用户显式放弃了这道门槛）。
        """

        if spec.mode in {"AttachOnly", "URL"} or spec.wait_time <= 0:
            return True
        owned = self.game_owned_process
        if owned is None:
            return True

        started = datetime.now()
        pid = owned.pid
        if spec.mode == "LauncherExe":
            client = await asyncio.to_thread(
                wait_for_client, spec, spec.wait_time, preexisting=owned.preexisting
            )
            if client is None:
                logger.warning(f"MFW 等待游戏本体进程超时（{spec.wait_time}s）")
                return False
            with suppress(Exception):
                owned.client_identity = (client.pid, client.create_time())
            pid = client.pid
            logger.info(f"MFW 已定位游戏本体进程：pid={pid}")

        # 与日志等待同理，按次数计而不是墙钟 deadline：测试里 asyncio.sleep 被打成
        # 空转，墙钟写法会变成真的忙等满 wait_time 秒。
        elapsed = (datetime.now() - started).total_seconds()
        remaining = max(0.0, spec.wait_time - elapsed)
        attempts = max(1, int(remaining / _GAME_READY_PROBE_INTERVAL_SECONDS))
        for attempt in range(attempts):
            if has_visible_window(pid):
                logger.info(f"MFW PC 游戏窗口已就绪：pid={pid}")
                return True
            if attempt + 1 < attempts:
                await asyncio.sleep(_GAME_READY_PROBE_INTERVAL_SECONDS)
        logger.warning(f"MFW 等待 PC 游戏窗口超时（{spec.wait_time}s）：pid={pid}")
        return False

    async def _teardown_launch_preparation(self) -> None:
        """收尾：关闭本层启动准备起来的模拟器 / PC 游戏。幂等，可多路径调用。"""

        if self.emulator_opened and self.emulator_manager is not None:
            try:
                await self.emulator_manager.close(self.emulator_index)
            except Exception as exc:  # noqa: BLE001
                logger.opt(exception=True).warning(f"MFW 关闭模拟器失败：{exc}")
            finally:
                self.emulator_opened = False
                self.emulator_info = None
                self.generated_adb_device = None

        if self.game_owned_process is not None:
            spec = self.game_launch_spec
            if spec is None:
                with suppress(Exception):
                    spec = resolve_game_launch_spec(self.script_config)
            # 只关 MAS 可证明拥有的进程：close_owned_game 内部按 PID/create_time
            # 身份核对，拒绝 preexisting 与 URL 启动。
            if spec is not None and spec.close_on_finish:
                with suppress(Exception):
                    await asyncio.to_thread(close_owned_game, self.game_owned_process)
            self.game_owned_process = None
        self.game_attached_pid = None

    async def _run_user(self, index: int, uid: uuid.UUID) -> None:
        """执行单个用户：解析范围 → 周期过滤 → 写配置 → 起外壳 → 判终态。"""

        if self.user_config is None or self.interface_model is None:
            raise RuntimeError("MFW 运行前置状态未初始化")

        self.current_user_uid = uid
        self.current_user_config = self.user_config[uid]
        self.current_user_item = self.script_info.user_list[index]
        self._reset_user_run_state()
        self.current_user_item.status = "运行"

        user_name = self.current_user_item.name
        controller_name = self._resolve_controller_name(
            self.current_user_config, self.script_config
        )
        resource_name = self._resolve_resource_name(
            self.current_user_config,
            self.script_config,
            self.interface_model,
            controller_name,
        )
        snapshot = self.current_user_config.get("Task", "TaskSnapshot")
        task_names = self._parse_snapshot_task_selection(snapshot)
        if not task_names:
            # 用户没排任务（新建用户的默认状态）：只跳过该用户，其余用户照常跑。
            self.current_user_item.status = "跳过"
            self.script_info.log = f"用户 {user_name} 未配置任务队列，跳过本次运行"
            logger.info(self.script_info.log)
            return

        runnable, skipped = self._filter_period_once_tasks(task_names)
        if skipped:
            logger.info(f"用户 {user_name} 周期跳过任务：{'、'.join(skipped)}")
        if not runnable:
            self.current_user_item.status = "跳过"
            self.script_info.log = (
                f"用户 {user_name} 的选中任务本周期均已正常完成，跳过本次运行"
            )
            logger.info(self.script_info.log)
            return

        self.controller_name = controller_name
        self.resource_name = resource_name
        self.task_selections = self._build_task_selections(
            runnable,
            self._parse_snapshot_task_options(snapshot),
            controller_name=controller_name,
            resource_name=resource_name,
        )

        await self._mark_run_started()

        # 启动外壳之前先做启动准备：Adb 起模拟器 / Win32 起 PC 游戏。失败则记明确的
        # 用户级状态并跳过外壳，绝不让它走到 controller_failed。
        launch_error = await self._prepare_launch_for_user(controller_name)
        if launch_error is not None:
            self._mark_terminal("launch_failed", f"MFW {launch_error}")
            self.user_terminal[str(uid)] = self.terminal_kind
            with suppress(Exception):
                await self.current_user_config.set("Data", "LastProxyStatus", "失败")
            return

        self._write_runtime_config()
        logger.info(f"开始代理用户 {user_name}（{uid}）")
        await self._run_external()

        self.user_terminal[str(uid)] = self.terminal_kind
        if self.terminal_kind == "success":
            await self._mark_period_tasks_completed(runnable)
            with suppress(Exception):
                if (
                    self.current_user_config.get("Data", "ProxyTimes") == 0
                    and self.current_user_config.get("Info", "RemainedDay") != -1
                ):
                    await self.current_user_config.set(
                        "Info",
                        "RemainedDay",
                        self.current_user_config.get("Info", "RemainedDay") - 1,
                    )
                await self.current_user_config.set(
                    "Data",
                    "ProxyTimes",
                    self.current_user_config.get("Data", "ProxyTimes") + 1,
                )
                await self.current_user_config.set("Data", "LastProxyStatus", "成功")
        else:
            with suppress(Exception):
                await self.current_user_config.set("Data", "LastProxyStatus", "失败")

    async def _persist_user_config(self) -> None:
        """把本次运行对用户配置的写入回写到脚本配置并落盘。"""

        if self.user_config is None:
            return
        try:
            script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
            await script_config.UserData.load(await self.user_config.toDict())
            save = getattr(Config.ScriptConfig, "save", None)
            if callable(save):
                await save()
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(f"MFW 用户配置回写失败：{exc}")

    async def main_task(self) -> None:
        """执行一轮 MaaFW 外部任务；所有运行期状态都在 finally 清理。"""

        self._ensure_virtual_user()
        self.check_result = await self.check()
        if self.check_result != "Pass":
            self.script_info.status = "异常"
            self._ensure_virtual_user().status = "异常"
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": self.check_result},
            )
            return

        try:
            await self.prepare()
            self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
            user_uids = list(self.runnable_user_uids)
            for index, uid in enumerate(user_uids):
                self.script_info.current_index = index
                try:
                    await self._run_user(index, uid)
                # 只截 Exception：CancelledError 属 BaseException，必须继续外抛，
                # 否则基类的取消路径与 _await_cleanup 的收尾保证一起失效。
                except Exception as exc:  # noqa: BLE001
                    await self._mark_user_run_crashed(index, exc)
                finally:
                    # 用户间：先结束当前外壳；最后一个用户的收尾交给 _cleanup。
                    # 放在 finally 里，异常路径也不会把上一个用户的外壳 / 模拟器
                    # 留给下一个用户。
                    if index < len(user_uids) - 1:
                        await self._teardown_shell_between_users()
        finally:
            # TaskExecuteBase 在取消路径也会等待 final_task；这里先做一次显式保护。
            await self._await_cleanup()

    async def final_task(self) -> None:
        """任务结束后的幂等收尾，供正常、异常和取消路径共同调用。"""

        try:
            await self._await_cleanup()
        except Exception as exc:  # noqa: BLE001
            self.cleanup_error = str(exc)
            logger.opt(exception=True).warning(f"MFW 收尾清理异常：{exc}")

        # 外壳已由 _cleanup 结束；再关闭本层启动准备起来的模拟器 / PC 游戏
        # （顺序与 M9A 一致：先停外壳，后关模拟器）。所有路径都会经过 final_task。
        await self._teardown_launch_preparation()

        await self._persist_user_config()

        for user in self.script_info.user_list:
            if user.status in ("等待", "运行"):
                user.status = "异常"

        await self._write_history_records()

        error_users = [
            user
            for user in self.script_info.user_list
            if user.status not in ("完成", "跳过")
        ]
        if (
            self.check_result == "Pass"
            and not self.cleanup_error
            and not error_users
        ):
            self.script_info.status = "完成"
        else:
            self.script_info.status = "异常"

        await self._push_run_report()

    async def _push_run_report(self) -> None:
        """按全局通知配置推送脚本级任务报告。

        「摘取+适配」自 general ``manager.py`` ``final_task`` 的报告块：沿用其
        标题构成、完成/未完成计数与桌面提醒 + 渠道推送的组合。适配点：

        - general 在 check 失败时提前 return 不发报告；本层 ``final_task``
          无提前返回，故在此处按 ``check_result`` 与空用户列表自行跳过。
        - MaaFW 无游戏签到摘要与推送日志采集，报告只含计数与用户结果串；
          用户级「统计信息」与统计合并未接线（属独立能力）。
        - 整体自保护：报告失败只告警与上报 websocket，不得中断收尾链路。
        """

        if self.report_pushed:
            return
        self.report_pushed = True

        if self.check_result != "Pass" or not self.script_info.user_list:
            return

        completed = [
            user
            for user in self.script_info.user_list
            if user.status in ("完成", "跳过")
        ]
        uncompleted_count = len(self.script_info.user_list) - len(completed)
        title = (
            f"{datetime.now().strftime('%m-%d')} | "
            f"{self.script_info.name or '空白'}的"
            f"{TASK_MODE_ZH[self.task_info.mode]}任务报告"
        )
        begin_time = self.begin_time or datetime.now()
        message = {
            "title": title,
            "script_name": self.script_info.name or "空白",
            "start_time": begin_time.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "completed_count": len(completed),
            "uncompleted_count": uncompleted_count,
            "result": self.script_info.result,
        }
        try:
            await Notify.push_plyer(
                title.replace("报告", "已完成！"),
                f"已完成用户数: {len(completed)}, 未完成用户数: {uncompleted_count}",
                f"已完成用户数: {len(completed)}, 未完成用户数: {uncompleted_count}",
                10,
            )
            await push_notification("代理结果", title, message)
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(f"推送 MFW 任务报告失败：{exc}")
            with suppress(Exception):
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={"Error": f"推送 MFW 任务报告失败：{exc}"},
                )

    async def _write_history_records(self) -> None:
        """把每个用户的运行日志写入 MAS 历史记录目录，供「历史记录」页检索。

        「摘取+适配」自 M9A ``AutoProxy.final_task``（AutoProxy.py:765-789）：
        沿用其路径构成（``Config.build_history_log_path`` 取 脚本名 / 用户名 /
        本地时区→UTC4 的开始时间）、「正常运行中」收尾串归一、逐条 ``log_record``
        写入的时机与内容。适配点：

        - M9A 的 ``AutoProxy`` 每用户一实例、``final_task`` 只处理当前用户；本层是
          单 manager 跑完全部用户，故遍历 ``script_info.user_list`` 逐用户逐条写。
        - M9A 用 ``Config.save_maa_log``（明日方舟专用：理智 / 公招 / 掉落解析）；
          MaaFW 是引擎无关的通用 MaaFW GUI，改用 ``Config.save_general_log``
          （与 General / OkNte / Okww 一致），只落 ``{"general_result": <状态>}``。
        - 统计合并 / 推送通知未接：本层尚无通知基础设施，属独立能力，本次只保证
          「运行可被历史记录检索」。
        """

        if self.history_written:
            return
        self.history_written = True

        local_tz = datetime.now().astimezone().tzinfo
        for user in self.script_info.user_list:
            for start_time, log_item in sorted(
                user.log_record.items(), key=lambda item: item[0]
            ):
                try:
                    status = log_item.status
                    if status == "MFW 正常运行中":
                        status = "任务被用户手动中止"
                    content = list(log_item.content)
                    if not content:
                        content = ["未捕获到任何日志内容"]
                        status = "未捕获到日志"
                    log_time = start_time.replace(tzinfo=local_tz).astimezone(UTC4)
                    log_path = Config.build_history_log_path(
                        script_name=self.script_info.name,
                        user_name=user.name,
                        log_time=log_time,
                    )
                    await Config.save_general_log(
                        log_path, content, status or "未知结果"
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.opt(exception=True).warning(
                        f"MFW 写入历史记录失败（用户 {user.name}）：{exc}"
                    )

    async def on_crash(self, e: Exception) -> None:
        """异常处理必须自保护，不能阻断配置恢复。"""

        try:
            self.terminal_kind = self.terminal_kind or "error"
            self.script_info.status = "异常"
            crash_user = self.current_user_item or self._ensure_virtual_user()
            crash_user.status = "异常"
            if self.current_log is None:
                self.current_log = LogRecord()
                start_time = self.log_start_time or datetime.now()
                crash_user.log_record[start_time] = self.current_log
            self.current_log.status = f"MFW 运行异常：{e}"
            logger.opt(exception=True).warning(f"MFW 外部任务出现异常：{e}")
            try:
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={"Error": f"MFW 外部任务出现异常：{e}"},
                )
            except Exception as notify_exc:  # noqa: BLE001
                logger.warning(f"发送 MFW 异常通知失败：{notify_exc}")
            await self._await_cleanup()
        except Exception as cleanup_exc:  # noqa: BLE001
            logger.opt(exception=True).warning(f"MFW 异常处理失败：{cleanup_exc}")


__all__ = ["MaaFWManager"]
