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
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core import Config
from app.models.config import MaaFWConfig
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase, UserItem
from app.services import System
from app.task.MaaFW.tools.config_write_guard import atomic_write_maafw_config
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
)
from app.utils import LogMonitor, ProcessManager, get_logger


logger = get_logger("MaaFW 外部调度器")

_LOG_TIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"
_COMPLETION_MARKERS = ("任务已全部完成！", "All tasks completed")
_ABANDON_MARKER = "已放弃本次任务"
_STATE_DIR_NAME = "MaaFWExternal"


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

        self.virtual_user: UserItem | None = None
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
            controller_name = self._parse_single_selection(
                script_config.get("Selection", "Controller"), "controller"
            )
            resource_name = self._parse_single_selection(
                script_config.get("Selection", "Resource"), "resource"
            )
            task_names = self._parse_task_selection(
                script_config.get("Selection", "Tasks")
            )
            if controller_name not in {item.name for item in interface_model.controller}:
                raise ValueError(f"interface 未定义 controller：{controller_name}")
            if resource_name not in {item.name for item in interface_model.resource}:
                raise ValueError(f"interface 未定义 resource：{resource_name}")
            task_index = {item.name for item in interface_model.task}
            unknown_tasks = [name for name in task_names if name not in task_index]
            if unknown_tasks:
                raise ValueError(f"interface 未定义 task：{unknown_tasks[0]}")
        except (ValueError, ShellMappingError) as exc:
            return f"MaaFW 选择配置无效：{exc}"
        except Exception as exc:
            return f"MaaFW interface 读取失败：{exc}"

        exe_path = self._resolve_executable(project_root)
        if isinstance(exe_path, str):
            return exe_path

        config_dir = project_root / "config"
        if config_dir.exists() and not config_dir.is_dir():
            return f"MaaFW config 路径不是目录：{config_dir}"

        self.project_root = project_root
        self.config_dir = config_dir
        self.instances_dir = config_dir / "instances"
        self.instance_path = self.instances_dir / "default.json"
        self.config_json_path = config_dir / "config.json"
        self.exe_path = exe_path
        self.interface_model = interface_model
        self.controller_name = controller_name
        self.resource_name = resource_name
        self.task_selections = [TaskSelection(name=name) for name in task_names]
        self.log_path = project_root / "logs" / f"log-{datetime.now():%Y%m%d}.log"
        return "Pass"

    @staticmethod
    def _parse_json_list(value: Any, label: str) -> list[str]:
        """把 ConfigBase 中的 JSON 字符串解析为非空字符串列表。"""

        raw = value
        if isinstance(value, str):
            try:
                raw = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{label} 不是有效 JSON") from exc
        if not isinstance(raw, list) or not raw:
            raise ValueError(f"{label} 不能为空")
        if not all(isinstance(item, str) and item.strip() for item in raw):
            raise ValueError(f"{label} 必须是非空字符串数组")
        return [item.strip() for item in raw]

    @classmethod
    def _parse_single_selection(cls, value: Any, label: str) -> str:
        values = cls._parse_json_list(value, label)
        return values[0]

    @classmethod
    def _parse_task_selection(cls, value: Any) -> list[str]:
        values = cls._parse_json_list(value, "task")
        for task_name in values:
            if is_pretask_task_name(task_name):
                raise ValueError(f"task 不允许选择 pretask 伪任务：{task_name}")
        return values

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
        self._ensure_virtual_user()
        self.script_info.status = "运行"

        # 启动时先恢复上一次被强杀遗留的快照，再发布本轮有效备份。
        self.restored = False
        self.backup_published = False
        if self._has_residual_state():
            # 旧外壳可能仍在写 config；必须先按精确 exe 路径结束它，再恢复快照。
            if self.exe_path is None:
                raise RuntimeError("MaaFW 外壳路径未初始化")
            await System.kill_process(self.exe_path)
            logger.info(f"MaaFW 已结束残留外壳，准备恢复：{self.exe_path}")
        self._recover_residual_backup()
        self._backup_project_config()
        self._write_runtime_config()

    def _ensure_virtual_user(self) -> UserItem:
        if self.virtual_user is None:
            self.virtual_user = UserItem(
                user_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"maafw:{self.script_info.script_id}")),
                name=self.script_info.name or "MaaFW 项目",
                status="等待",
            )
        self.script_info.user_list = [self.virtual_user]
        return self.virtual_user

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

        base = _read_json_object(self.instance_path, label="MaaFW default 实例配置")
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
        if self.exe_path is None or self.log_path is None:
            raise RuntimeError("MaaFW 外壳路径未初始化")
        self.process_manager = ProcessManager()
        self.log_monitor = LogMonitor((1, 24), _LOG_TIME_FORMAT, self.check_log)
        self.terminal_event.clear()
        self.terminal_kind = None
        self.last_log_text = ""
        self.last_log_at = datetime.now()
        self.log_start_time = datetime.now()

        # MFAAvalonia 约定从 instances/default.json 读取运行任务，不传命令行参数。
        await self.process_manager.open_process(self.exe_path)
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
                if self._contains_completion(self.last_log_text):
                    self._mark_terminal("success", "Success!")
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

        # 完成串必须优先于放弃串，且累计日志中任一完成串都可收口。
        if self._contains_completion(log_text):
            self._mark_terminal("success", "Success!")
        elif _ABANDON_MARKER in log_text:
            self._mark_terminal("abandoned", f"MaaFW {_ABANDON_MARKER}")
        elif self.terminal_kind is None:
            self.current_log.status = "MaaFW 正常运行中"

    def _mark_terminal(self, kind: str, log_status: str) -> None:
        if kind == "success":
            self.terminal_kind = "success"
        elif self.terminal_kind == "success":
            return
        elif self.terminal_kind is None:
            self.terminal_kind = kind
        else:
            return

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

        if self.process_started and self.exe_path is not None:
            try:
                await System.kill_process(self.exe_path)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"强制结束外壳失败：{exc}")
                logger.opt(exception=True).warning(f"强制结束 MFAAvalonia.exe 失败：{exc}")

        if not self.restored and (self.backup_published or self.manifest_path.exists()):
            try:
                self._restore_backup_from_state()
            except Exception as exc:  # noqa: BLE001
                errors.append(f"恢复 MaaFW 配置失败：{exc}")
                logger.opt(exception=True).warning(f"恢复 MaaFW 配置失败：{exc}")

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

    async def main_task(self) -> None:
        """执行一轮 MaaFW 外部任务；所有运行期状态都在 finally 清理。"""

        self._ensure_virtual_user()
        self.check_result = await self.check()
        if self.check_result != "Pass":
            self.script_info.status = "异常"
            self.virtual_user.status = "异常"
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": self.check_result},
            )
            return

        try:
            await self.prepare()
            await self._run_external()
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

        if self.check_result == "Pass" and self.terminal_kind == "success" and not self.cleanup_error:
            self.script_info.status = "完成"
        else:
            self.script_info.status = "异常"
            if self.virtual_user is not None and self.virtual_user.status == "等待":
                self.virtual_user.status = "异常"

    async def on_crash(self, e: Exception) -> None:
        """异常处理必须自保护，不能阻断配置恢复。"""

        try:
            self.terminal_kind = self.terminal_kind or "error"
            self.script_info.status = "异常"
            if self.virtual_user is not None:
                self.virtual_user.status = "异常"
                if self.current_log is None:
                    self.current_log = LogRecord()
                    start_time = self.log_start_time or datetime.now()
                    self.virtual_user.log_record[start_time] = self.current_log
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
