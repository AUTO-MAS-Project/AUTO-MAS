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
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core import Config, EmulatorManager
from app.models.ConfigBase import MultipleConfig
from app.models.config import MaaFWConfig, MaaFWUserConfig
from app.models.emulator import DeviceBase, DeviceInfo
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase, UserItem
from app.services import System
from app.utils.constants import UTC4
from app.task.MaaFW.tools.config_write_guard import atomic_write_maafw_config
from app.task.MaaFW.tools.controller.game_lifecycle import (
    MaaFWGameLaunchSpec,
    MaaFWOwnedGameProcess,
    close_owned_game,
    find_client_process,
    launch_game,
    resolve_game_launch_spec,
    snapshot_matching_processes,
    validate_game_launch_spec,
)
from app.task.MaaFW.tools.core.automas_maafw_interface import load_interface_model
from app.task.MaaFW.tools.core.automas_maafw_interface.models import (
    is_pretask_task_name,
)
from app.task.MaaFW.tools.external import (
    InstanceOrchestration,
    ShellFamily,
    ShellMappingError,
    TaskSelection,
    build_instance_config,
    detect_shell_family,
    resolve_controller_code,
)
from app.utils import LogMonitor, ProcessManager, get_logger


logger = get_logger("MaaFW 外部调度器")

_LOG_TIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"
_COMPLETION_MARKERS = ("任务已全部完成！", "All tasks completed")
_ABANDON_MARKER = "已放弃本次任务"
_STATE_DIR_NAME = "MaaFWExternal"

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
        raise RuntimeError(f"MaaFW 配置路径不能是符号链接：{root}")
    if not root.is_dir():
        return
    for child in root.rglob("*"):
        if child.is_symlink():
            raise RuntimeError(f"MaaFW 配置包含符号链接，拒绝运行：{child}")


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
    mfaavalonia.py）。本函数只判断标识存在且非空，不校验其内部结构。已知两种写法：
    顶层 ``AdbDevice``（字符串，或含非空 ``AdbSerial`` 的对象），或 ``Connect.Address``
    （点号平铺键，或 ``Connect`` 嵌套对象的 ``Address``）。缺少成功运行样本，不臆造
    更多字段。
    """

    adb_device = instance_config.get("AdbDevice")
    if isinstance(adb_device, str) and adb_device.strip():
        return True
    if isinstance(adb_device, dict):
        serial = adb_device.get("AdbSerial")
        if isinstance(serial, str) and serial.strip():
            return True

    flat_address = instance_config.get("Connect.Address")
    if isinstance(flat_address, str) and flat_address.strip():
        return True

    connect = instance_config.get("Connect")
    if isinstance(connect, dict):
        address = connect.get("Address")
        if isinstance(address, str) and address.strip():
            return True

    return False


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
        self.config_json_path: Path | None = None
        self.exe_path: Path | None = None
        self.log_path: Path | None = None
        self.log_start_time: datetime | None = None

        self.interface_model: Any | None = None
        self.controller_name: str | None = None
        self.resource_name: str | None = None
        self.task_selections: list[TaskSelection] = []

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
        self.generated_adb_device: dict[str, Any] | None = None
        self.emulator_opened = False
        self.emulator_index: str = ""
        self.game_launch_spec: MaaFWGameLaunchSpec | None = None
        self.game_owned_process: MaaFWOwnedGameProcess | None = None

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

    async def check(self) -> str:
        """校验 MaaFW 配置、外壳、选择项和可运行文件。"""

        if self.task_info.mode != "AutoProxy":
            return "MaaFW 当前仅支持外部自动运行模式"

        try:
            script_uid = uuid.UUID(self.script_info.script_id)
        except (ValueError, AttributeError, TypeError):
            return "MaaFW 脚本 ID 无效，请刷新后重试"

        try:
            script_config = Config.ScriptConfig[script_uid]
        except (KeyError, ValueError):
            return "MaaFW 脚本配置不存在，请刷新后重试"

        if not isinstance(script_config, MaaFWConfig):
            return "脚本配置类型错误，不是 MaaFW 脚本类型"
        self.script_config = script_config

        project_value = str(script_config.get("Info", "Path") or "").strip()
        if not project_value:
            return "请设置 MaaFW 项目路径"
        project_root = Path(project_value).resolve()
        if not project_root.is_dir():
            return "请设置包含 interface.json 的 MaaFW 项目目录"

        if script_config.get("Run", "Engine") != "external":
            return "MaaFW 当前仅支持 external 运行引擎"

        shell_family = detect_shell_family(project_root)
        if shell_family != ShellFamily.MFAAVALONIA:
            return (
                f"MaaFW 外壳 {shell_family.value} 暂不支持，"
                "当前仅支持 MFAAvalonia"
            )

        try:
            interface_model = load_interface_model(project_root)
        except Exception as exc:
            return f"MaaFW interface 读取失败：{exc}"

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
            return "MaaFW 没有可运行的用户，请在用户管理页添加并启用至少一个用户"

        controller_index = {item.name for item in interface_model.controller}
        resource_index = {item.name for item in interface_model.resource}
        task_index = {item.name for item in interface_model.task}

        try:
            for uid in runnable_uids:
                cfg = user_config[uid]
                user_name = cfg.get("Info", "Name")
                controller_name = self._resolve_controller_name(cfg, script_config)
                if not controller_name:
                    raise ValueError(
                        f"用户 {user_name} 未确定 MaaFW controller，"
                        "请在脚本编辑页或用户配置中选择"
                    )
                if controller_name not in controller_index:
                    raise ValueError(f"interface 未定义 controller：{controller_name}")
                resource_name = self._resolve_resource_name(
                    cfg, script_config, interface_model, controller_name
                )
                if not resource_name:
                    raise ValueError(f"用户 {user_name} 未确定 MaaFW resource")
                if resource_name not in resource_index:
                    raise ValueError(f"interface 未定义 resource：{resource_name}")
                task_names = self._parse_snapshot_task_selection(
                    cfg.get("Task", "TaskSnapshot")
                )
                unknown_tasks = [name for name in task_names if name not in task_index]
                if unknown_tasks:
                    raise ValueError(f"interface 未定义 task：{unknown_tasks[0]}")
        except (ValueError, ShellMappingError) as exc:
            return f"MaaFW 选择配置无效：{exc}"
        except Exception as exc:
            return f"MaaFW interface 读取失败：{exc}"

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
        if controller_type == "Adb" and emulator_selection is None:
            # 必须校验 MAS 实际会写入的那个实例文件。MFAAvalonia 的实例文件按实例 ID
            # 命名（MaaKes 恰好叫 default，M9A 那份是随机 ID），此前这里硬编码
            # default.json，与 _write_runtime_config 的写入目标不一致：对只有
            # <随机id>.json 的项目会误拒，反之也可能误放行。
            try:
                instance_base = _read_json_object(
                    _resolve_active_instance_path(
                        project_root / "config" / "instances", project_root
                    ),
                    label="MaaFW 活动实例配置",
                )
            except RuntimeError as exc:
                return f"MaaFW 实例配置无法读取：{exc}"
            if not _instance_has_adb_device(instance_base):
                return (
                    "未配置模拟器设备，MaaFW 无法连接："
                    "实例配置缺少 AdbDevice / Connect.Address，"
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
                        f"MaaFW 实例配置中的 ADB 程序不存在：{adb_path_value}。"
                        "请在 MAS 中选择当前模拟器，或先在外壳侧重新连接设备"
                    )
        elif controller_type and resolve_controller_code(controller_type) is None:
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
                f"MaaFW 外部运行暂不支持 {controller_type} 控制器："
                "该类型的 CurrentController 取值尚未确认，"
                "请改用 Adb 控制器，或在外壳侧手动运行"
            )

        exe_path = self._resolve_executable(project_root)
        if isinstance(exe_path, str):
            return exe_path

        config_dir = project_root / "config"
        if config_dir.exists() and not config_dir.is_dir():
            return f"MaaFW config 路径不是目录：{config_dir}"

        self.project_root = project_root
        self.config_dir = config_dir
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
        self.log_path = project_root / "logs" / f"log-{datetime.now():%Y%m%d}.log"
        return "Pass"

    @staticmethod
    def _parse_snapshot_task_selection(value: Any) -> list[str]:
        """用户 Task.TaskSnapshot → 按序勾选的任务名列表（pretask 已滤除）。"""

        names = _checked_task_names_from_snapshot(_load_json_dict(value))
        if not names:
            raise ValueError("task 不能为空")
        return names

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
    def _resolve_executable(project_root: Path) -> Path | str:
        """优先使用根目录 MFAAvalonia.exe，再兼容旧的 project 子目录。"""

        preferred = project_root / "MFAAvalonia.exe"
        if preferred.is_file():
            return preferred
        compatibility = project_root / "project" / "MFAAvalonia.exe"
        if compatibility.is_file():
            return compatibility
        root_executables = [path for path in project_root.glob("*.exe") if path.is_file()]
        if len(root_executables) == 1:
            return root_executables[0]
        if not root_executables:
            return "MFAAvalonia.exe 不存在，请检查 MaaFW 项目目录"
        return "MaaFW 项目根目录存在多个 exe，无法安全选择 MFAAvalonia.exe"

    async def prepare(self) -> None:
        """锁定 MAS 配置，恢复残留快照并制作本轮配置备份。"""

        if self.script_config is None or self.project_root is None:
            raise RuntimeError("MaaFW 配置检查尚未通过")

        script_uid = uuid.UUID(self.script_info.script_id)
        script_config = Config.ScriptConfig[script_uid]
        if not isinstance(script_config, MaaFWConfig):
            raise TypeError("脚本配置类型错误，不是 MaaFW 脚本类型")
        self.script_config = script_config
        await script_config.lock()
        logger.success(f"{self.script_info.script_id} 已锁定，MaaFW 配置提取完成")

        self.begin_time = datetime.now()
        if self.user_config is None:
            raise RuntimeError("MaaFW 用户配置未加载")
        self.script_info.user_list = [
            UserItem(
                user_id=str(uid),
                name=self.user_config[uid].get("Info", "Name"),
                status="等待",
            )
            for uid in self.runnable_user_uids
        ]
        logger.info(
            f"MaaFW 用户列表加载完成，已筛选用户数: {len(self.script_info.user_list)}"
        )
        self.script_info.status = "运行"

        # 启动时先恢复上一次被强杀遗留的快照，再发布本轮有效备份。
        self.restored = False
        self.backup_published = False
        if self._has_residual_state():
            # 旧外壳可能仍在写 config；必须先按精确 exe 路径结束它，再恢复快照。
            if self.exe_path is None:
                raise RuntimeError("MaaFW 外壳路径未初始化")
            if not await System.kill_process(self.exe_path):
                raise RuntimeError(
                    "MaaFW 残留外壳无法确认已结束，已保留备份并拒绝恢复 config"
                )
            logger.info(f"MaaFW 已结束残留外壳，准备恢复：{self.exe_path}")
        self._recover_residual_backup()
        self._backup_project_config()
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
                name=self.script_info.name or "MaaFW 项目",
                status="等待",
            )
            self.script_info.user_list = [self._fallback_user]
        return self._fallback_user

    def _backup_project_config(self) -> None:
        if self.project_root is None or self.config_dir is None:
            raise RuntimeError("MaaFW 项目路径未初始化")
        self.state_dir.parent.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)

        if self.config_dir.exists() and not self.config_dir.is_dir():
            raise RuntimeError(f"MaaFW config 路径不是目录：{self.config_dir}")
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
        }
        atomic_write_maafw_config(self.manifest_path, manifest, journal=False)
        self.backup_published = True
        self.restored = False
        logger.info(f"MaaFW config 已备份到 MAS 数据目录：{self.backup_path}")

    def _has_residual_state(self) -> bool:
        """返回是否存在本模块留下的、需要启动前处理的状态。"""

        if self.state_dir.is_symlink():
            raise RuntimeError("MaaFW 残留备份目录无效，拒绝运行")
        if not self.state_dir.exists():
            return False
        if not self.state_dir.is_dir():
            raise RuntimeError("MaaFW 残留备份目录无效，拒绝运行")
        return any(self.state_dir.iterdir())

    def _load_backup_manifest(self) -> dict[str, Any]:
        if self.project_root is None:
            raise RuntimeError("MaaFW 项目路径未初始化")
        if self.manifest_path.is_symlink() or not self.manifest_path.is_file():
            raise RuntimeError("MaaFW 残留备份 manifest 缺失或不是普通文件")
        manifest = _read_json_object(self.manifest_path, label="MaaFW 残留备份 manifest")
        if manifest.get("version") != 1:
            raise RuntimeError("MaaFW 残留备份版本不受支持")
        if manifest.get("script_id") != str(self.script_info.script_id):
            raise RuntimeError("MaaFW 残留备份脚本 ID 不匹配，拒绝恢复")
        manifest_path = manifest.get("project_path")
        if not isinstance(manifest_path, str) or not Path(manifest_path).is_absolute():
            raise RuntimeError("MaaFW 残留备份项目路径无效，拒绝恢复")
        if Path(manifest_path).resolve() != self.project_root.resolve():
            raise RuntimeError("MaaFW 残留备份项目路径不匹配，拒绝恢复")
        if not isinstance(manifest.get("config_exists"), bool):
            raise RuntimeError("MaaFW 残留备份缺少 config_exists，拒绝恢复")
        if self.backup_path.is_symlink() or not self.backup_path.is_dir():
            raise RuntimeError("MaaFW 残留备份 config 不完整，拒绝恢复")
        _ensure_no_symlinks(self.backup_path)
        if not manifest["config_exists"] and any(self.backup_path.iterdir()):
            raise RuntimeError("MaaFW 残留备份标记与 config 内容不一致，拒绝恢复")
        return manifest

    def _recover_residual_backup(self) -> None:
        if self.state_dir.is_symlink():
            raise RuntimeError("MaaFW 残留备份目录无效，拒绝运行")
        if not self.state_dir.exists():
            return
        if not self.state_dir.is_dir():
            raise RuntimeError("MaaFW 残留备份目录无效，拒绝运行")
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
                raise RuntimeError("MaaFW 未发布备份 config.tmp 无效，拒绝运行")
            _remove_owned_path(temporary_backup)
            self.state_dir.rmdir()
            logger.info("MaaFW 已清理未发布的 config.tmp 残留")
            return
        self._restore_backup_from_state()
        logger.info("MaaFW 已自动恢复上次未完成任务的残留配置")

    def _restore_backup_from_state(self) -> None:
        if self.config_dir is None:
            raise RuntimeError("MaaFW config 路径未初始化")
        manifest = self._load_backup_manifest()
        config_existed = manifest["config_exists"]
        temporary_restore = self.config_dir.with_name(self.config_dir.name + ".restore.tmp")
        _remove_owned_path(temporary_restore)

        if self.config_dir.is_symlink() or (
            self.config_dir.exists() and not self.config_dir.is_dir()
        ):
            raise RuntimeError(f"MaaFW config 路径不是安全目录：{self.config_dir}")

        if config_existed:
            shutil.copytree(self.backup_path, temporary_restore)

        _remove_owned_path(self.config_dir)
        if config_existed:
            temporary_restore.rename(self.config_dir)

        _remove_owned_path(self.state_dir)
        self.restored = True
        self.backup_published = False
        logger.info(f"MaaFW config 已恢复：{self.config_dir}")

    def _write_runtime_config(self) -> None:
        if (
            self.interface_model is None
            or self.instances_dir is None
            or self.instance_path is None
            or self.config_json_path is None
            or self.controller_name is None
            or self.resource_name is None
        ):
            raise RuntimeError("MaaFW 运行配置路径或选择未初始化")

        # 多用户逐个写入：base 始终取本轮备份里的原始实例配置，避免上一个用户
        # 写入的 controller / TaskItems 漏进下一个用户。登记了 MAS 模拟器时覆盖
        # AdbDevice；否则继续透传实例原值。
        backup_instance = (
            self.backup_path / "instances" / self.instance_path.name
        )
        base_path = backup_instance if backup_instance.is_file() else self.instance_path
        base = _read_json_object(base_path, label="MaaFW default 实例配置")
        if self.generated_adb_device is not None:
            base["AdbDevice"] = self.generated_adb_device
            logger.info("MaaFW 已按 MAS 模拟器配置覆盖 AdbDevice")

        instance_config = build_instance_config(
            self.interface_model,
            controller_name=self.controller_name,
            resource_name=self.resource_name,
            selected_tasks=self.task_selections,
            base=base,
            orchestration=InstanceOrchestration(instance_name="MAS"),
        )

        self.instances_dir.mkdir(parents=True, exist_ok=True)
        for json_file in self.instances_dir.glob("*.json"):
            if json_file.is_symlink() or not json_file.is_file():
                raise RuntimeError(f"MaaFW instances 条目不是普通文件：{json_file}")
            json_file.unlink()
        atomic_write_maafw_config(self.instance_path, instance_config, journal=False)

        shell_config = _read_json_object(self.config_json_path, label="MaaFW config.json")
        shell_config.update(
            {
                "AutoMinimize": True,
                "AutoHide": True,
                "ShouldMinimizeToTray": True,
            }
        )
        atomic_write_maafw_config(self.config_json_path, shell_config, journal=False)
        logger.info(f"MaaFW 运行配置已写入：{self.instance_path}")

    async def _run_external(self) -> None:
        if (
            self.exe_path is None
            or self.instance_path is None
            or self.log_path is None
        ):
            raise RuntimeError("MaaFW 外壳路径、实例或日志路径未初始化")
        self.process_manager = ProcessManager()
        self.log_monitor = LogMonitor((1, 24), _LOG_TIME_FORMAT, self.check_log)
        self.terminal_event.clear()
        self.terminal_kind = None
        self.last_log_text = ""
        self.last_log_at = datetime.now()
        self.log_start_time = datetime.now()

        # MFAAvalonia 需显式请求自动运行，任务队列仍从 MAS 写入的活动实例读取。
        await self.process_manager.open_process(
            self.exe_path,
            "--autostart",
            "--instance",
            self.instance_path.stem,
        )
        self.process_started = True
        self.process_pid = self.process_manager.main_pid
        logger.info(f"MFAAvalonia 外壳已启动，PID: {self.process_pid}")

        await asyncio.sleep(5)
        if not await self.process_manager.is_running():
            self._mark_terminal("exit", "MaaFW 进程已异常退出")
            return

        await self.log_monitor.start_monitor_file(self.log_path, self.log_start_time)
        self.monitor_started = True
        await self._wait_for_terminal()

    async def _wait_for_terminal(self) -> None:
        if self.process_manager is None:
            raise RuntimeError("MaaFW 进程管理器未初始化")
        runtime_limit = self._runtime_limit_seconds()
        while not self.terminal_event.is_set():
            if not await self.process_manager.is_running():
                # 让并发中的 monitor callback 有机会先提交完成标记；完成优先于退出。
                await asyncio.sleep(0)
                if self._contains_controller_failure(self.last_log_text):
                    self._mark_controller_failure()
                elif self._contains_completion(self.last_log_text):
                    self._mark_completion(self.last_log_text)
                elif _ABANDON_MARKER in self.last_log_text:
                    self._mark_terminal("abandoned", f"MaaFW {_ABANDON_MARKER}")
                else:
                    self._mark_terminal("exit", "MaaFW 进程已异常退出")
                break

            if runtime_limit <= 0 or (
                self.last_log_at is not None
                and (datetime.now() - self.last_log_at).total_seconds() >= runtime_limit
            ):
                self._mark_terminal("timeout", "MaaFW 进程超时")
                break
            await asyncio.sleep(1)

    @staticmethod
    def _contains_completion(text: str) -> bool:
        return any(marker in text for marker in _COMPLETION_MARKERS)

    @staticmethod
    def _contains_controller_failure(text: str) -> bool:
        """控制器初始化失败——外壳未能真正开始执行选中的任务。"""

        return any(marker in text for marker in _CONTROLLER_FAILURE_MARKERS)

    def _mark_controller_failure(self) -> None:
        self._mark_terminal(
            "controller_failed",
            "MaaFW 控制器初始化失败，任务未实际执行",
        )

    def _mark_completion(self, log_text: str) -> None:
        """完成串出现时收口：选中任务全部在日志里露过面才判成功。

        弱形式的逐任务校验——只回答「选中的事到底有没有被尝试」。实测的假成功里
        选中任务在整份日志出现 0 次，完成串却存在。不解析逐任务成功/失败：没有一次
        成功运行的样本，任何日志格式假设都是臆造。
        """

        absent = self._selected_tasks_absent_from(log_text)
        if absent:
            self._mark_terminal(
                "tasks_missing",
                f"MaaFW 输出完成串，但选中任务未出现：{'、'.join(absent)}",
            )
        else:
            self._mark_terminal("success", "Success!")

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
            self.last_log_text = log_text
            self.last_log_at = datetime.now()

        # 控制器初始化失败压过完成串：外壳排空队列时照样输出完成串，但选中的任务
        # 从未执行，此时判成功是假成功。完成串本身还要过 _mark_completion 里「选中
        # 任务是否露过面」这道关，都通过才判成功。其次完成串优先于放弃串。
        if self._contains_controller_failure(log_text):
            self._mark_controller_failure()
        elif self._contains_completion(log_text):
            self._mark_completion(log_text)
        elif _ABANDON_MARKER in log_text:
            self._mark_terminal("abandoned", f"MaaFW {_ABANDON_MARKER}")
        elif self.terminal_kind is None:
            self.current_log.status = "MaaFW 正常运行中"

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
        logger.info(f"MaaFW 任务终态：{self.terminal_kind} ({log_status})")

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
                logger.opt(exception=True).warning(f"停止 MaaFW 日志监控失败：{exc}")
            self.monitor_started = False

        if self.process_manager is not None:
            try:
                await self.process_manager.kill()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"结束进程管理器失败：{exc}")
                logger.opt(exception=True).warning(f"结束 MaaFW 进程失败：{exc}")

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
                self._restore_backup_from_state()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"恢复 MaaFW 配置失败：{exc}")
                logger.opt(exception=True).warning(f"恢复 MaaFW 配置失败：{exc}")
        elif needs_restore:
            errors.append("外壳仍可能运行；为避免并发写入，已保留 MaaFW 配置备份")

        script_config = self.script_config
        if script_config is not None and script_config.is_locked:
            try:
                await script_config.unlock()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"解锁 MaaFW 配置失败：{exc}")
                logger.opt(exception=True).warning(f"解锁 MaaFW 配置失败：{exc}")

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
            with suppress(Exception):
                await System.kill_process(self.exe_path)
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
            return "MaaFW 脚本配置未加载"
        emulator_selection = self._get_emulator_selection(self.script_config)
        if emulator_selection is None:
            # 未配置 MAS 模拟器。check() 中受保护的启动前 Adb 设备校验已确认活动
            # 实例带有设备标识（AdbDevice / Connect.Address）——缺标识的情况早在
            # check() 就被明确拒绝。这里是「用户自行在外壳侧连接、自行管理模拟器」
            # 的既有放行场景：不是静默跳过，显式记录后沿用实例已有连接。
            logger.info(
                "MaaFW 未配置 MAS 模拟器，跳过自动启动，沿用活动实例已有的设备连接"
            )
            self.emulator_info = None
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
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(f"MaaFW 模拟器启动失败：{exc}")
            with suppress(Exception):
                if self.emulator_manager is not None:
                    await self.emulator_manager.close(emulator_index)
            self.emulator_opened = False
            self.emulator_info = None
            self.generated_adb_device = None
            return f"模拟器启动失败：{exc}"

        if Config.get("Function", "IfSilence"):
            with suppress(Exception):
                await self.emulator_manager.setVisible(emulator_index, False)
        return None

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
            logger.info(f"不支持的模拟器类型: {emulator_type}，使用实例原配置")
            return None
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"构建 AdbDevice 配置时出错，使用实例原配置: {exc}")
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
        """构建 MuMu 模拟器 AdbDevice。整体回收自 M9A 专项。"""

        logger.info("构建 MuMu 模拟器 AdbDevice 配置")

        shell_dir = emulator_path.parent
        emulator_root = shell_dir.parent
        adb_path = shell_dir / "adb.exe"

        mumu_extras = {
            "enable": True,
            "index": int(emulator_index),
            "path": str(emulator_root).replace("\\", "/"),
        }

        config_json = json.dumps(
            {"extras": {"mumu": mumu_extras}}, ensure_ascii=False
        )

        return {
            "Name": "MuMu模拟器",
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
            return "MaaFW 脚本配置未加载"
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
            return None

        try:
            preexisting = await asyncio.to_thread(snapshot_matching_processes, spec)
            self.game_owned_process = await launch_game(spec, preexisting=preexisting)
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(f"MaaFW PC 游戏启动失败：{exc}")
            return f"PC 游戏启动失败：{exc}"
        return None

    async def _teardown_launch_preparation(self) -> None:
        """收尾：关闭本层启动准备起来的模拟器 / PC 游戏。幂等，可多路径调用。"""

        if self.emulator_opened and self.emulator_manager is not None:
            try:
                await self.emulator_manager.close(self.emulator_index)
            except Exception as exc:  # noqa: BLE001
                logger.opt(exception=True).warning(f"MaaFW 关闭模拟器失败：{exc}")
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

    async def _run_user(self, index: int, uid: uuid.UUID) -> None:
        """执行单个用户：解析范围 → 周期过滤 → 写配置 → 起外壳 → 判终态。"""

        if self.user_config is None or self.interface_model is None:
            raise RuntimeError("MaaFW 运行前置状态未初始化")

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
        task_names = self._parse_snapshot_task_selection(
            self.current_user_config.get("Task", "TaskSnapshot")
        )
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
        self.task_selections = [TaskSelection(name=name) for name in runnable]

        await self._mark_run_started()

        # 启动外壳之前先做启动准备：Adb 起模拟器 / Win32 起 PC 游戏。失败则记明确的
        # 用户级状态并跳过外壳，绝不让它走到 controller_failed。
        launch_error = await self._prepare_launch_for_user(controller_name)
        if launch_error is not None:
            self._mark_terminal("launch_failed", f"MaaFW {launch_error}")
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
            logger.opt(exception=True).warning(f"MaaFW 用户配置回写失败：{exc}")

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
                await self._run_user(index, uid)
                # 用户间：先结束当前外壳；最后一个用户的收尾交给 _cleanup。
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
            logger.opt(exception=True).warning(f"MaaFW 收尾清理异常：{exc}")

        # 外壳已由 _cleanup 结束；再关闭本层启动准备起来的模拟器 / PC 游戏
        # （顺序与 M9A 一致：先停外壳，后关模拟器）。所有路径都会经过 final_task。
        await self._teardown_launch_preparation()

        await self._persist_user_config()

        for user in self.script_info.user_list:
            if user.status in ("等待", "运行"):
                user.status = "异常"

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
            self.current_log.status = f"MaaFW 运行异常：{e}"
            logger.opt(exception=True).warning(f"MaaFW 外部任务出现异常：{e}")
            try:
                await Config.send_websocket_message(
                    id=self.task_info.task_id,
                    type="Info",
                    data={"Error": f"MaaFW 外部任务出现异常：{e}"},
                )
            except Exception as notify_exc:  # noqa: BLE001
                logger.warning(f"发送 MaaFW 异常通知失败：{notify_exc}")
            await self._await_cleanup()
        except Exception as cleanup_exc:  # noqa: BLE001
            logger.opt(exception=True).warning(f"MaaFW 异常处理失败：{cleanup_exc}")


__all__ = ["MaaFWManager"]
