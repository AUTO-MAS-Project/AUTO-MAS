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


import asyncio
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Callable

from app.core import Config, EmulatorManager
from app.core.ws import Publisher, protocol
from app.models.config import SrcConfig, SrcUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, TaskExecuteBase, UserItem
from app.tools.game_sign_notify import (
    append_task_game_sign_summary,
    finalize_task_game_sign_notification,
)
from app.utils import ProcessManager, get_logger
from app.utils.constants import TASK_MODE_ZH

from .AutoProxy import AutoProxyTask
from .ScriptConfig import ScriptConfigTask
from .tools import (
    SrcConfigSnapshotState,
    SrcProcessState,
    has_committed_src_user_config_transaction,
    is_src_config_available,
    kill_src_processes,
    push_notification,
    read_src_config_snapshot_state,
    read_src_installation_id,
    read_src_process_state,
    recover_interrupted_src_config_swap,
    recover_src_user_config,
    save_src_user_config,
    validate_src_cleanup_paths,
    validate_src_installation,
    write_src_config_snapshot_state,
    write_src_process_state,
)

logger = get_logger("SRC 调度器")

_EMULATOR_CLOSE_TIMEOUT_SECONDS = 30
_NOTIFICATION_TIMEOUT_SECONDS = 30
_WEBSOCKET_REPORT_TIMEOUT_SECONDS = 5

METHOD_BOOK: dict[str, type[AutoProxyTask | ScriptConfigTask]] = {
    "AutoProxy": AutoProxyTask,
    "ScriptConfig": ScriptConfigTask,
}


class SrcManager(TaskExecuteBase):
    """SRC控制器"""

    wait_for_finalizer_on_cancel = True

    def __init__(
        self,
        script_info: ScriptItem,
        *,
        reserved_src_root_path: Path,
        reserve_src_root: Callable[[Path], bool],
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self._reserved_src_root_path = reserved_src_root_path.resolve()
        self._reserve_src_root = reserve_src_root
        self.check_result = "-"
        self.process_cleanup_success = True
        self.prepared = False
        self.config_lock_acquired = False
        self.recovery_context_initialized = False
        self.recovery_started = False
        self.recovery_completed = False
        self.current_cleanup_completed = False
        self._cleaned_src_roots: set[Path] = set()

    async def check(self) -> str:
        """校验SRC配置是否可用"""
        if self.task_info.mode not in METHOD_BOOK:
            return "不支持的任务模式，请检查任务配置！"
        if not isinstance(
            Config.ScriptConfig[uuid.UUID(self.script_info.script_id)], SrcConfig
        ):
            return "脚本配置类型错误, 不是SRC脚本类型"
        if Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
            "Emulator", "Id"
        ) == "-" or Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
            "Emulator", "Index"
        ) in (
            "",
            "-",
        ):
            return "未完成模拟器配置, 请检查脚本配置中的模拟器设置！"
        if not (
            Path(
                Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                    "Info", "Path"
                )
            )
            / "src.exe"
        ).exists():
            return "src.exe文件不存在, 请检查SRC路径设置！"
        src_set_path = (
            Path(
                Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].get(
                    "Info", "Path"
                )
            )
            / "config"
        )
        temp_path = Path.cwd() / f"data/{self.script_info.script_id}/Temp"
        temp_ready_path = temp_path.with_name(temp_path.name + ".ready")
        src_config_available = self._is_src_config_available(src_set_path)
        temp_config_available = (
            temp_ready_path.exists() and self._is_src_config_available(temp_path)
        )
        if not src_config_available and not temp_config_available:
            return "SRC配置文件不存在或已损坏, 请检查SRC路径设置或检查配置文件情况！"
        if (
            self.task_info.mode != "ScriptConfig"
            and not (
                Path.cwd() / f"data/{self.script_info.script_id}/Default/ConfigFile"
            ).exists()
        ):
            return "未完成 SRC 全局设置, 请先设置 SRC！"
        return "Pass"

    async def prepare(self):
        """运行前准备"""

        await self._recover_previous_run()

        # 加载用户配置
        self.user_config = MultipleConfig([SrcUserConfig])
        await self.user_config.load(await self.script_config.UserData.toDict())
        logger.success(f"{self.script_info.script_id}已锁定, SRC配置提取完成")

        # 初始化模拟器管理器和用户列表
        self.emulator_manager = await EmulatorManager.get_emulator_instance(
            self.script_config.get("Emulator", "Id")
        )
        if self.task_info.mode == "ScriptConfig":
            self.script_info.user_list = [
                UserItem(
                    user_id=self.task_info.user_id or "Default", name="", status="等待"
                )
            ]
        else:
            self.script_info.user_list = [
                UserItem(
                    user_id=str(uid), name=config.get("Info", "Name"), status="等待"
                )
                for uid, config in self.user_config.items()
                if config.get("Info", "Status")
                and config.get("Info", "RemainedDay") != 0
            ]
        logger.info(
            f"用户列表加载完成, 已筛选用户数: {len(self.script_info.user_list)}"
        )

        await self._cleanup_current_src_root()

        # 备份本次任务开始前的原始配置
        self._backup_src_config_to_temp()
        self.prepared = True

    async def _initialize_recovery_context(self) -> None:
        """锁定脚本并冻结本次恢复使用的路径。"""

        if getattr(self, "recovery_context_initialized", False):
            return

        script_config = getattr(self, "script_config", None)
        if script_config is None:
            script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
            self.script_config = script_config
        if not getattr(self, "config_lock_acquired", False):
            # ConfigBase.lock 会在首个 await 前置锁；先记录以便取消时仍能解锁。
            self.config_lock_acquired = True
        await script_config.lock()

        locked_root_path = Path(self.script_config.get("Info", "Path")).resolve()
        reserved_root_path = self._reserved_src_root_path
        if (
            reserved_root_path is None
            or locked_root_path != reserved_root_path.resolve()
        ):
            raise RuntimeError("SRC 路径在任务启动期间发生变化，请重试")

        self.src_root_path = locked_root_path
        self.src_exe_path = self.src_root_path / "src.exe"
        self.src_set_path = self.src_root_path / "config"
        self.temp_path = Path.cwd() / f"data/{self.script_info.script_id}/Temp"
        self.src_process_state_path = (
            Path.cwd() / f"data/{self.script_info.script_id}/Temp.process.json"
        )
        self.temp_ready_path = self.temp_path.with_name(self.temp_path.name + ".ready")
        self.recovery_context_initialized = True

    async def _recover_previous_run(self) -> None:
        """在当前配置检查前清理进程并处置上次快照。"""

        if getattr(self, "recovery_completed", False):
            return

        await self._initialize_recovery_context()
        self.recovery_started = True
        if not hasattr(self, "_cleaned_src_roots"):
            self._cleaned_src_roots = set()

        self._clear_uncommitted_config_snapshots()

        process_state = None
        process_state_error: Exception | None = None
        try:
            process_state = read_src_process_state(
                self.src_process_state_path,
                expected_script_id=self.script_info.script_id,
            )
        except (OSError, ValueError) as e:
            process_state_error = e

        snapshot_state: SrcConfigSnapshotState | None = None
        snapshot_root_path = None
        snapshot_error: Exception | None = None
        if self.temp_path.exists() and self.temp_ready_path.exists():
            try:
                snapshot_state = self._read_config_snapshot_state()
                snapshot_root_path = snapshot_state.src_root_path
            except (OSError, ValueError) as e:
                snapshot_error = e

        if (
            process_state is not None
            and snapshot_root_path is not None
            and (
                process_state.src_root_path != snapshot_root_path
                or process_state.installation_id != snapshot_state.installation_id
            )
        ):
            raise RuntimeError("SRC 进程状态与配置快照的安装实例不一致，拒绝自动清理")

        cleanup_targets: list[tuple[Path, int | None, str]] = []
        if process_state is not None:
            cleanup_targets.append(
                (
                    process_state.src_root_path,
                    process_state.webui_port,
                    process_state.installation_id,
                )
            )
        if snapshot_root_path is not None and all(
            root_path != snapshot_root_path for root_path, _, _ in cleanup_targets
        ):
            cleanup_targets.append(
                (
                    snapshot_root_path,
                    None,
                    snapshot_state.installation_id,
                )
            )

        self._reserve_recovery_roots([root_path for root_path, _, _ in cleanup_targets])
        self._assert_no_foreign_pending_snapshot(
            [
                self.src_root_path,
                *(root_path for root_path, _, _ in cleanup_targets),
            ]
        )
        if (
            process_state is None
            and snapshot_state is not None
            and (snapshot_state.src_root_path / "src.exe").is_file()
            and self._is_src_config_available(self.temp_path)
        ):
            try:
                validate_src_cleanup_paths(
                    snapshot_state.src_root_path,
                    snapshot_state.src_root_path / "src.exe",
                    snapshot_state.src_root_path / "config",
                    expected_installation_id=snapshot_state.installation_id,
                )
            except (OSError, ValueError) as e:
                raise RuntimeError(
                    "SRC 配置恢复事务的历史根目录范围不安全，拒绝自动回滚: "
                    f"{snapshot_state.src_root_path}"
                ) from e
            recover_interrupted_src_config_swap(
                snapshot_state.src_root_path / "config",
                expected_installation_id=snapshot_state.installation_id,
            )

        cleanup_success = True
        for (
            cleanup_root_path,
            webui_port,
            installation_id,
        ) in cleanup_targets:
            target_success = await kill_src_processes(
                ProcessManager(),
                src_exe_path=cleanup_root_path / "src.exe",
                src_root_path=cleanup_root_path,
                src_set_path=cleanup_root_path / "config",
                webui_port=webui_port,
                listener_wait_timeout=2.0,
                expected_installation_id=installation_id,
            )
            if not target_success:
                cleanup_success = False
            else:
                self._cleaned_src_roots.add(cleanup_root_path.resolve())
        self.process_cleanup_success = cleanup_success
        if not cleanup_success:
            raise RuntimeError("SRC 进程清理未完成，请关闭 SRC 后重试")
        if process_state_error is not None:
            raise RuntimeError(
                f"SRC 进程状态无法验证: {self.src_process_state_path}"
            ) from process_state_error
        if snapshot_error is not None:
            raise RuntimeError(
                f"SRC 配置快照状态无法验证: {self.temp_ready_path}"
            ) from snapshot_error

        if process_state is not None and process_state.config_user_id is not None:
            if (
                snapshot_state is None
                or snapshot_state.config_user_id != process_state.config_user_id
            ):
                raise RuntimeError(
                    "SRC 脚本设置会话归属无法由配置快照验证，已拒绝自动保存"
                )
            self._save_pending_config_session(process_state)

        # 上次异常收尾保留了原配置快照时，确认进程退出后再恢复。
        if self.temp_path.exists():
            if self.temp_ready_path.exists():
                snapshot_available = self._is_src_config_available(self.temp_path)
                if not snapshot_available and self._is_src_config_available(
                    self.src_set_path
                ):
                    self._quarantine_config_snapshot("快照内容不完整")
                elif not snapshot_available:
                    raise RuntimeError(
                        "SRC 当前配置和待恢复快照均不可用，"
                        f"请手动检查: {self.src_set_path}, {self.temp_path}"
                    )
                elif snapshot_root_path == self.src_root_path:
                    logger.warning(f"检测到待恢复的 SRC 配置快照: {self.temp_path}")
                    self._restore_src_config_from_temp(
                        expected_installation_id=snapshot_state.installation_id,
                    )
                    self._retire_src_config_snapshot()
                elif snapshot_root_path is not None and snapshot_root_path.exists():
                    logger.warning(
                        "SRC 路径已变更，正在把原配置恢复到旧根目录: "
                        f"{snapshot_root_path}"
                    )
                    self._restore_src_config_from_temp(
                        snapshot_root_path / "config",
                        expected_installation_id=snapshot_state.installation_id,
                    )
                    self._retire_src_config_snapshot()
                elif self._is_src_config_available(self.src_set_path):
                    self._quarantine_config_snapshot(
                        f"快照属于其他 SRC 根目录: {snapshot_root_path}"
                    )
                else:
                    raise RuntimeError(
                        "SRC 路径已变更且当前配置不可用，旧配置快照已保留，"
                        f"请手动检查: {self.temp_path}"
                    )
            elif self._is_src_config_available(self.src_set_path):
                self._quarantine_config_snapshot("快照未完成提交")
            else:
                raise RuntimeError(
                    f"检测到未完成的 SRC 配置快照，请手动检查: {self.temp_path}"
                )
        else:
            self.temp_ready_path.unlink(missing_ok=True)
            self.src_process_state_path.unlink(missing_ok=True)

        self.recovery_completed = True

    async def _cleanup_current_src_root(self) -> None:
        """在备份当前配置前确认当前 SRC 根目录已停止。"""

        current_root_path = self.src_root_path.resolve()
        installation_id = read_src_installation_id(current_root_path)
        if current_root_path not in self._cleaned_src_roots:
            cleanup_success = await kill_src_processes(
                ProcessManager(),
                src_exe_path=self.src_exe_path,
                src_root_path=self.src_root_path,
                src_set_path=self.src_set_path,
                webui_port=None,
                listener_wait_timeout=2.0,
                expected_installation_id=installation_id,
            )
            self.process_cleanup_success = cleanup_success
            if not cleanup_success:
                raise RuntimeError("SRC 进程清理未完成，请关闭 SRC 后重试")
            self._cleaned_src_roots.add(current_root_path)
        validate_src_installation(current_root_path, installation_id)
        self.src_installation_id = installation_id
        self.current_cleanup_completed = True

    def _reserve_recovery_roots(self, root_paths: list[Path]) -> None:
        """原子扩展本任务的占用到所有历史 SRC 根目录。"""

        reserve_src_root = getattr(self, "_reserve_src_root", None)
        for root_path in root_paths:
            resolved_root_path = root_path.resolve()
            if resolved_root_path == self.src_root_path:
                continue
            if reserve_src_root is None or not reserve_src_root(resolved_root_path):
                raise RuntimeError(
                    "SRC 历史路径已被其他任务占用，拒绝恢复或清理: "
                    f"{resolved_root_path}"
                )

    @staticmethod
    def _is_src_config_available(path: Path) -> bool:
        """判断目录是否包含可识别的 SRC 配置入口。"""

        return is_src_config_available(path)

    def _clear_uncommitted_config_snapshots(self) -> None:
        """清理不会被当作有效快照的中间目录。"""

        staging_path = self.temp_path.with_name(self.temp_path.name + ".tmp")
        discarded_path = self.temp_path.with_name(self.temp_path.name + ".discard")
        if staging_path.exists():
            shutil.rmtree(staging_path)
        if discarded_path.exists():
            # discard 只会在进程清理和配置恢复成功后生成；即使上次在删除
            # marker/state 前崩溃，也可以完成退休，避免孤立 state 再次授权清理。
            shutil.rmtree(discarded_path)
            self.temp_ready_path.unlink(missing_ok=True)
            self.src_process_state_path.unlink(missing_ok=True)
        if not self.temp_path.exists():
            self.temp_ready_path.unlink(missing_ok=True)

    def _recover_default_user_config_transaction(self) -> None:
        """在配置检查前恢复非设置任务依赖的默认用户配置。"""

        if self.task_info.mode == "ScriptConfig":
            return
        recover_src_user_config(
            Path.cwd() / f"data/{self.script_info.script_id}/Default/ConfigFile"
        )

    def _backup_src_config_to_temp(self) -> None:
        """完整复制配置后，再提交为可恢复的 Temp 快照。"""

        validate_src_installation(
            self.src_root_path,
            self.src_installation_id,
        )
        staging_path = self.temp_path.with_name(self.temp_path.name + ".tmp")
        if staging_path.exists():
            shutil.rmtree(staging_path)
        if self.temp_path.exists():
            raise RuntimeError(f"SRC 配置快照已存在: {self.temp_path}")

        staging_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(self.src_set_path, staging_path)
        if not self._is_src_config_available(staging_path):
            raise RuntimeError(f"SRC 配置快照副本不完整，拒绝提交: {staging_path}")
        validate_src_installation(
            self.src_root_path,
            self.src_installation_id,
        )
        staging_path.rename(self.temp_path)
        write_src_config_snapshot_state(
            self.temp_ready_path,
            script_id=self.script_info.script_id,
            src_root_path=self.src_root_path,
            installation_id=self.src_installation_id,
            config_user_id=None,
        )

    @staticmethod
    def _paths_overlap(first_path: Path, second_path: Path) -> bool:
        first_path = first_path.resolve()
        second_path = second_path.resolve()
        return (
            first_path == second_path
            or first_path.is_relative_to(second_path)
            or second_path.is_relative_to(first_path)
        )

    def _assert_no_foreign_pending_snapshot(
        self,
        protected_roots: list[Path] | None = None,
    ) -> None:
        """拒绝接管其他脚本尚未恢复的 SRC 根目录。"""

        data_path = Path.cwd() / "data"
        if not data_path.exists():
            return

        protected_roots = protected_roots or [self.src_root_path]
        own_ready_path = self.temp_ready_path.resolve()
        for ready_path in data_path.glob("*/Temp.ready"):
            if ready_path.resolve() == own_ready_path:
                continue
            snapshot_path = ready_path.with_name("Temp")
            if not snapshot_path.exists():
                continue
            try:
                snapshot_state = read_src_config_snapshot_state(
                    ready_path,
                    expected_script_id=ready_path.parent.name,
                )
                snapshot_root_path = snapshot_state.src_root_path
            except (AttributeError, OSError, ValueError) as e:
                raise RuntimeError(
                    f"无法验证其他 SRC 待恢复快照的占用范围，请先处理: {ready_path}"
                ) from e

            if any(
                self._paths_overlap(protected_root, snapshot_root_path)
                for protected_root in protected_roots
            ):
                raise RuntimeError(
                    "SRC 路径仍由其他脚本的待恢复快照占用，请先重试对应脚本: "
                    f"{ready_path.parent.name}"
                )

    def _save_pending_config_session(self, process_state: SrcProcessState) -> None:
        """进程确认退出后，先保存上次脚本设置会话再恢复原配置。"""

        user_id = process_state.config_user_id
        if user_id != "Default":
            try:
                user_id = str(uuid.UUID(user_id))
            except (TypeError, ValueError, AttributeError) as e:
                raise ValueError(f"SRC 脚本设置用户无效: {user_id}") from e

        config_path = (
            Path.cwd() / "data" / self.script_info.script_id / user_id / "ConfigFile"
        )
        if has_committed_src_user_config_transaction(config_path):
            recover_src_user_config(config_path, preserve_commit_marker=True)
        else:
            source_path = process_state.src_root_path / "config"
            if not source_path.parent.exists():
                raise RuntimeError(
                    f"SRC 脚本设置目录已不存在，已保留待恢复状态: {source_path}"
                )
            validate_src_installation(
                process_state.src_root_path,
                process_state.installation_id,
            )
            if not self._is_src_config_available(source_path):
                raise RuntimeError(f"SRC 脚本设置配置不存在或已损坏: {source_path}")
            save_src_user_config(
                source_path,
                config_path,
                preserve_commit_marker=True,
                expected_installation_id=process_state.installation_id,
            )
        write_src_process_state(
            self.src_process_state_path,
            script_id=self.script_info.script_id,
            src_root_path=process_state.src_root_path,
            webui_port=process_state.webui_port,
            installation_id=process_state.installation_id,
            config_user_id=None,
        )
        recover_src_user_config(config_path)
        logger.success(f"已保存上次中断的 SRC 脚本设置: {config_path}")

    def _read_config_snapshot_state(self) -> SrcConfigSnapshotState:
        """读取已提交配置快照的归属信息。"""

        return read_src_config_snapshot_state(
            self.temp_ready_path,
            expected_script_id=self.script_info.script_id,
        )

    def _read_config_snapshot_root(self) -> Path:
        """读取已提交配置快照所属的 SRC 根目录。"""

        return self._read_config_snapshot_state().src_root_path

    def _quarantine_config_snapshot(self, reason: str) -> None:
        """隔离不应自动恢复的快照，避免覆盖现场配置。"""

        quarantine_path = self.temp_path.with_name(
            f"{self.temp_path.name}.untrusted-{uuid.uuid4().hex}"
        )
        self.temp_path.rename(quarantine_path)
        self.temp_ready_path.unlink(missing_ok=True)
        self.src_process_state_path.unlink(missing_ok=True)
        logger.warning(f"已隔离 SRC 配置快照: {quarantine_path}, 原因: {reason}")

    def _restore_src_config_from_temp(
        self,
        src_set_path: Path | None = None,
        *,
        expected_installation_id: str | None = None,
    ) -> None:
        """使用 Temp 快照替换 SRC 配置目录。"""

        if not self.temp_path.exists():
            return

        src_set_path = src_set_path or self.src_set_path
        if expected_installation_id is not None:
            validate_src_installation(
                src_set_path.parent,
                expected_installation_id,
            )
        temporary_path = src_set_path.with_name(src_set_path.name + ".tmp")
        backup_path = src_set_path.with_name(src_set_path.name + ".old")
        shutil.rmtree(temporary_path, ignore_errors=True)
        shutil.copytree(self.temp_path, temporary_path)
        if not self._is_src_config_available(temporary_path):
            raise RuntimeError(
                f"SRC 配置恢复副本不完整，保留当前配置: {temporary_path}"
            )
        if expected_installation_id is not None:
            validate_src_installation(
                src_set_path.parent,
                expected_installation_id,
            )
        if backup_path.exists():
            if not src_set_path.exists():
                backup_path.rename(src_set_path)
            elif self._is_src_config_available(src_set_path):
                shutil.rmtree(backup_path)
            elif self._is_src_config_available(backup_path):
                failed_path = src_set_path.with_name(
                    f"{src_set_path.name}.untrusted-{uuid.uuid4().hex}"
                )
                src_set_path.rename(failed_path)
                backup_path.rename(src_set_path)
                logger.warning(
                    f"已回滚损坏的 SRC 配置目录并保留现场副本: {failed_path}"
                )
            else:
                raise RuntimeError(
                    "SRC 配置恢复事务存在冲突，已保留所有副本: "
                    f"{src_set_path}, {backup_path}"
                )
        if expected_installation_id is not None:
            validate_src_installation(
                src_set_path.parent,
                expected_installation_id,
            )
        temporary_stat = temporary_path.stat()
        if src_set_path.exists():
            src_set_path.rename(backup_path)
        try:
            temporary_path.rename(src_set_path)
            if expected_installation_id is not None:
                validate_src_installation(
                    src_set_path.parent,
                    expected_installation_id,
                )
        except BaseException:
            if src_set_path.exists():
                restored_stat = src_set_path.stat()
                if (
                    restored_stat.st_dev,
                    restored_stat.st_ino,
                ) == (
                    temporary_stat.st_dev,
                    temporary_stat.st_ino,
                ):
                    src_set_path.rename(temporary_path)
            if backup_path.exists() and not src_set_path.exists():
                backup_path.rename(src_set_path)
            raise
        if not self._is_src_config_available(src_set_path):
            failed_path = src_set_path.with_name(
                f"{src_set_path.name}.untrusted-{uuid.uuid4().hex}"
            )
            src_set_path.rename(failed_path)
            if backup_path.exists():
                backup_path.rename(src_set_path)
            raise RuntimeError(
                f"SRC 配置恢复结果不完整，已回滚现场配置并保留恢复副本: {failed_path}"
            )
        if backup_path.exists():
            shutil.rmtree(backup_path)

    def _retire_src_config_snapshot(self) -> None:
        """先移出有效快照路径，再清理已恢复的快照。"""

        if not self.temp_path.exists():
            self.temp_ready_path.unlink(missing_ok=True)
            self.src_process_state_path.unlink(missing_ok=True)
            return

        discarded_path = self.temp_path.with_name(self.temp_path.name + ".discard")
        if discarded_path.exists():
            shutil.rmtree(discarded_path)
        self.temp_path.rename(discarded_path)
        self.temp_ready_path.unlink(missing_ok=True)
        self.src_process_state_path.unlink(missing_ok=True)
        shutil.rmtree(discarded_path, ignore_errors=True)

    async def main_task(self):

        self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await self._recover_previous_run()
        self._recover_default_user_config_transaction()

        self.check_result = await self.check()
        if self.check_result != "Pass":
            logger.warning(f"未通过配置检查: {self.check_result}")
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=self.check_result),
            )
            return

        await self.prepare()

        if not isinstance(self.script_config, SrcConfig):
            raise RuntimeError("脚本配置类型错误, 不是 SRC 脚本类型")

        for self.script_info.current_index in range(len(self.script_info.user_list)):
            task = METHOD_BOOK[self.task_info.mode](
                self.script_info,
                self.script_config,
                self.user_config,
                self.emulator_manager,
                src_installation_id=self.src_installation_id,
            )
            try:
                await self.spawn(task)
            finally:
                if isinstance(task, (AutoProxyTask, ScriptConfigTask)):
                    self.process_cleanup_success = task.process_cleanup_success
            if not self.process_cleanup_success:
                break

    async def final_task(self):
        """运行结束后的收尾工作"""

        lock_acquired = getattr(
            self,
            "config_lock_acquired",
            getattr(self, "prepared", False),
        )
        if not lock_acquired:
            self.script_info.status = "异常"
            return self.check_result if self.check_result != "Pass" else None

        logger.info("SRC 主任务已结束, 开始执行后续操作")
        script_config = getattr(self, "script_config", None)
        if script_config is None:
            script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        should_notify = False
        try:
            if not self.prepared:
                if not getattr(self, "recovery_completed", False):
                    await self._recover_previous_run()
                if self.check_result == "Pass" and not getattr(
                    self, "current_cleanup_completed", False
                ):
                    await self._cleanup_current_src_root()
                self.script_info.status = "异常"
                return self.check_result if self.check_result != "Pass" else None

            # 持锁完成快照处置，避免下一任务与当前收尾交叉操作同一目录。
            if self.process_cleanup_success:
                if not self._is_src_config_available(self.temp_path):
                    raise RuntimeError(
                        f"SRC 配置快照不存在或已损坏，已保留当前配置: {self.temp_path}"
                    )
                self._restore_src_config_from_temp(
                    expected_installation_id=self.src_installation_id,
                )
                self._retire_src_config_snapshot()
            else:
                logger.warning(f"SRC 进程仍可能运行，保留配置快照: {self.temp_path}")
            if self.task_info.mode in ["AutoProxy"]:
                should_notify = await self._complete_locked_final_task()
        finally:
            await script_config.unlock()
            self.config_lock_acquired = False
            logger.success(f"已解锁脚本配置 {self.script_info.script_id}")

        if should_notify:
            await self._send_final_notification()

    async def _complete_locked_final_task(self) -> bool:
        """在脚本仍锁定时写回任务结果。"""

        if not self.process_cleanup_success or any(
            user.status == "异常" for user in self.script_info.user_list
        ):
            self.script_info.status = "异常"
        else:
            self.script_info.status = "完成"

        if self.task_info.mode not in ["AutoProxy"]:
            return False

        try:
            await asyncio.wait_for(
                self.emulator_manager.close(
                    self.script_config.get("Emulator", "Index")
                ),
                timeout=_EMULATOR_CLOSE_TIMEOUT_SECONDS,
            )
        except Exception as e:
            self.script_info.status = "异常"
            logger.opt(exception=True).warning(f"关闭模拟器时出现异常: {e}")

        # 根配置保持锁定以阻止外部编辑；仅临时开放内部用户集合写回。
        await self.script_config.UserData.unlock()
        await Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].UserData.load(
            await self.user_config.toDict()
        )
        await Config.ScriptConfig.save()
        return True

    async def _send_final_notification(self) -> None:
        """解锁配置后限时发送任务完成通知。"""

        error_count = sum(1 for u in self.script_info.user_list if u.status == "异常")
        over_count = sum(1 for u in self.script_info.user_list if u.status == "完成")
        wait_count = sum(1 for u in self.script_info.user_list if u.status == "等待")

        title = f"{datetime.now().strftime('%m-%d')} | {self.script_info.name or '空白'}的{TASK_MODE_ZH[self.task_info.mode]}任务报告"
        task_result = append_task_game_sign_summary(
            self.task_info, self.script_info.result
        )
        has_game_sign_summary = task_result != self.script_info.result
        result = {
            "title": f"{TASK_MODE_ZH[self.task_info.mode]}任务报告",
            "script_name": self.script_info.name or "空白",
            "start_time": self.begin_time,
            "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "completed_count": over_count,
            "uncompleted_count": error_count + wait_count,
            "result": task_result,
            "game_sign_summary": has_game_sign_summary,
        }

        completion_title = (
            title.replace("报告", "已完成！")
            if self.script_info.status == "完成"
            else title.replace("报告", "存在异常")
        )
        result = {**result, "system_title": completion_title}
        try:
            push_result = await asyncio.wait_for(
                push_notification(
                    mode="代理结果",
                    title=title,
                    message=result,
                    user_config=None,
                    task_info=self.task_info,
                ),
                timeout=_NOTIFICATION_TIMEOUT_SECONDS,
            )
            finalize_task_game_sign_notification(
                self.task_info, has_game_sign_summary, push_result
            )
        except Exception as e:
            await self._report_notification_error("推送代理结果", e)

    async def _report_notification_error(
        self, operation: str, error: Exception
    ) -> None:
        logger.opt(exception=True).warning(f"{operation}时出现异常: {error}")
        try:
            await asyncio.wait_for(
                Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error",
                        message=f"{operation}时出现异常: {error}",
                    ),
                ),
                timeout=_WEBSOCKET_REPORT_TIMEOUT_SECONDS,
            )
        except Exception as report_error:
            logger.opt(exception=True).warning(f"上报 SRC 通知异常失败: {report_error}")

    async def on_crash(self, e: Exception):

        self.script_info.status = "异常"
        logger.opt(exception=True).warning(f"SRC任务出现异常: {e}")
        try:
            await asyncio.wait_for(
                Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error", message=f"SRC任务出现异常: {e}"
                    ),
                ),
                timeout=_WEBSOCKET_REPORT_TIMEOUT_SECONDS,
            )
        except Exception as report_error:
            logger.opt(exception=True).warning(f"上报 SRC 任务异常失败: {report_error}")
