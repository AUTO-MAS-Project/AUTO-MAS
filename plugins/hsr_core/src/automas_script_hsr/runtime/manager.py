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
from typing import Any

from app.core import Config
from app.models.ConfigBase import MultipleConfig
from app.models.plugin_script_config import PluginScriptConfig
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase, UserItem
from app.plugins.script_config_store import ScriptConfigStore
from app.services import Notify
from app.utils import get_logger
from app.utils.constants import TASK_MODE_ZH, UTC4, UTC8
from .autoproxy import HSRAutoProxyTask
from .manual_review import HSRManualReviewTask
from .models import CompletionWriteback, HSRRuntimeState
from .tasks import (
    HSR_TASK_MODULES,
    get_assigned_script,
    module_is_available,
    script_supports,
)
from .notify import push_notification
from .locks import acquire_external_path_locks, release_external_path_locks
from .game import (
    check_user_credentials,
    close_game_if_needed,
    resolve_game_executable_path,
    stop_external_processes,
)
logger = get_logger("HSR 调度器")

METHOD_BOOK: dict[str, type[HSRAutoProxyTask | HSRManualReviewTask]] = {
    "AutoProxy": HSRAutoProxyTask,
    "ManualReview": HSRManualReviewTask,
}


def _resolve_external_lock_paths(
    script_config: Any,
    effective_engines: tuple[str, ...],
) -> list[str | Path]:
    """返回本轮 HSR 运行会修改的全部外部路径。"""

    paths: list[str | Path] = [
        script_config.get(engine, "Path")
        for engine in effective_engines
        if script_config.get(engine, "Path")
    ]
    if "SRA" in effective_engines:
        from automas_hsr_adapter_sra.runner import get_sra_app_data_dir

        paths.append(get_sra_app_data_dir())
    return paths


def _remove_path(path: Path) -> None:
    """删除文件或目录，供原子恢复前清理临时路径。"""

    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink()


def _restore_path_from_backup(label: str, source: Path, backup: Path) -> None:
    """用 tmp + rename 恢复一个外部配置路径。"""

    if not backup.exists():
        raise RuntimeError(f"备份路径不存在：{backup}")

    source.parent.mkdir(parents=True, exist_ok=True)
    temp_source = source.with_name(f"{source.name}.tmp")
    _remove_path(temp_source)

    if backup.is_dir():
        shutil.copytree(backup, temp_source)
    else:
        shutil.copy2(backup, temp_source)

    _remove_path(source)
    temp_source.rename(source)
    logger.info(f"{label} 已恢复：{source}")


class HSRManager(TaskExecuteBase):
    """HSR 调度器，管理星穹铁道 M7A/SRA 双脚本任务。"""

    def __init__(self, script_info: ScriptItem, *, provider: Any, registry: Any):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.provider = provider
        self.registry = registry
        self.check_result: str = "-"
        self.begin_time: str = ""
        self.crashed: bool = False
        self.script_config: Any | None = None
        self.user_config: MultipleConfig[Any] | None = None
        self.store: ScriptConfigStore | None = None
        self.effective_engines: tuple[str, ...] = ()
        # 真实执行成功后的完成态写回队列。执行链路只登记意图，等待 final_task()
        # 确认整轮正常结束、脚本配置解锁后，再写回真实 UserData。
        self._completion_writebacks: list[CompletionWriteback] = []
        self._log_lines: list[str] = []
        self._runtime: HSRRuntimeState = HSRRuntimeState(
            log_lines=self._log_lines,
            completion_writebacks=self._completion_writebacks,
            registry=registry,
        )
        self.temp_path: Path = Path.cwd() / f"data/{self.script_info.script_id}/Temp"
        self._external_config_targets: list[tuple[str, Path, Path, bool]] = []
        self._external_path_locks: list[asyncio.Lock] = []

    def _backup_external_configs(self) -> None:
        """运行前备份 M7A/SRA 的真实配置文件。"""

        if self.script_config is None:
            return

        backup_root = self.temp_path / "ExternalConfig"
        shutil.rmtree(backup_root, ignore_errors=True)
        backup_root.mkdir(parents=True, exist_ok=True)
        self._external_config_targets = []

        def backup_path(label: str, source: Path, backup: Path) -> None:
            existed = source.exists()
            self._external_config_targets.append((label, source, backup, existed))
            if not existed:
                logger.info(f"{label} 原配置不存在，记录为缺失：{source}")
                return

            backup.parent.mkdir(parents=True, exist_ok=True)
            if source.is_dir():
                shutil.copytree(source, backup, dirs_exist_ok=True)
            elif source.is_file():
                shutil.copy2(source, backup)
            else:
                raise RuntimeError(f"{label} 既不是文件也不是目录：{source}")
            logger.info(f"{label} 已备份：{source} -> {backup}")

        m7a_path = self.script_config.get("M7A", "Path")
        if m7a_path and "M7A" in self.effective_engines:
            backup_path(
                "M7A config.yaml",
                Path(str(m7a_path)) / "config.yaml",
                backup_root / "M7A" / "config.yaml",
            )

        sra_path = self.script_config.get("SRA", "Path")
        if sra_path and "SRA" in self.effective_engines:
            from automas_hsr_adapter_sra.runner import get_sra_app_data_dir

            sra_app_data = get_sra_app_data_dir()
            backup_path(
                "SRA settings.json",
                sra_app_data / "settings.json",
                backup_root / "SRA" / "settings.json",
            )
            backup_path(
                "SRA cache.json",
                sra_app_data / "cache.json",
                backup_root / "SRA" / "cache.json",
            )
            backup_path(
                "SRA configs",
                sra_app_data / "configs",
                backup_root / "SRA" / "configs",
            )

        logger.info(
            f"HSR 外部配置备份完成，共 {len(self._external_config_targets)} 项"
        )

    def _restore_external_config_targets(self) -> None:
        """运行后恢复 M7A/SRA 配置，并清理备份目录。"""

        targets = list(self._external_config_targets)
        if not targets:
            return

        errors: list[str] = []
        for label, source, backup, existed in reversed(targets):
            try:
                if not existed:
                    if source.is_dir():
                        shutil.rmtree(source, ignore_errors=True)
                    elif source.exists():
                        source.unlink()
                    logger.info(f"{label} 原配置不存在，已清理任务期新增路径：{source}")
                    continue

                _restore_path_from_backup(label, source, backup)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{label}: {e}")
                logger.exception(f"恢复 HSR 外部配置失败：{label}: {e}")

        shutil.rmtree(self.temp_path / "ExternalConfig", ignore_errors=True)
        try:
            if self.temp_path.exists() and not any(self.temp_path.iterdir()):
                self.temp_path.rmdir()
        except OSError:
            pass

        self._external_config_targets = []
        if errors:
            raise RuntimeError("；".join(errors))

        logger.info("HSR 外部配置已恢复")

    def _append_log(self, message: str, *, max_lines: int = 500) -> None:
        """向调度台日志追加一行 HSR 运行信息。"""

        text = str(message).strip()
        if not text:
            return
        now_text = datetime.now(tz=UTC8).strftime("%H:%M:%S")
        for line in text.splitlines():
            line = line.strip()
            if line:
                formatted = f"[{now_text}] {line}"
                self._log_lines.append(formatted)
        if len(self._log_lines) > max_lines:
            del self._log_lines[:-max_lines]
        self.script_info.log = "\n".join(self._log_lines)

    async def _stop_external_processes(self) -> None:
        """停止当前仍在运行的 SRA/M7A 子进程。"""

        await stop_external_processes(
            self._runtime,
            self._append_log,
            self.script_config,
        )

    async def _close_game_if_needed(self) -> None:
        """任务结束后关闭由 MAS 本次启动的游戏。"""

        if self.script_config is None:
            return

        await close_game_if_needed(
            self._runtime,
            self.script_config,
            self._append_log,
        )

    async def check(self) -> str:
        """校验 HSR 配置是否可用，返回 'Pass' 或错误描述"""

        if self.task_info.mode not in METHOD_BOOK:
            return "HSR 暂不支持该任务模式，请检查任务配置"

        script_id = uuid.UUID(self.script_info.script_id)
        if script_id not in Config.ScriptConfig:
            return "脚本配置不存在，可能已被删除"

        storage_config = Config.ScriptConfig[script_id]
        if not isinstance(storage_config, PluginScriptConfig):
            return "脚本配置类型错误，不是 HSR 插件脚本类型"

        self.store = ScriptConfigStore(
            provider=self.provider,
            storage_script_config=storage_config,
        )
        self.script_config = await self.store.load_script_model()
        self.user_config = await self.store.load_user_collection()
        snapshot = self.registry.snapshot(
            script_config=self.script_config,
        )
        if not snapshot.available:
            return snapshot.unavailable_reason or "当前 HSR 脚本没有有效引擎"
        if self.task_info.mode not in snapshot.supported_modes:
            return f"当前 HSR 引擎组合不支持任务模式 {self.task_info.mode}"
        self.effective_engines = tuple(snapshot.effective_engines)
        object.__setattr__(
            self.script_config,
            "_hsr_effective_engines",
            self.effective_engines,
        )
        script_config = self.script_config

        for adapter in snapshot.adapters:
            if adapter.get("ready") is False:
                return str(adapter.get("ready_reason") or "HSR 引擎未就绪")

        if self.task_info.mode == "ManualReview":
            return self._check_manual_review(script_config)

        for module in HSR_TASK_MODULES:
            if not module_is_available(module, script_config):
                continue
            raw_assigned = script_config._config_item_index["TaskMapping"][module.key].value
            if len(self.effective_engines) > 1 and not script_supports(
                module.key, raw_assigned
            ):
                return (
                    f"模块「{module.name}」的分配脚本 '{raw_assigned}' "
                    f"不被该模块支持（仅支持：{'、'.join(module.supported_scripts)}）"
                )

        has_executable_user = False
        enabled_module_keys: set[str] = set()

        assert self.user_config is not None
        for _uid, user_config in self.user_config.items():
            if not user_config.get("Info", "Status"):
                continue
            if user_config.get("Info", "RemainedDay") == 0:
                continue
            has_executable_user = True

            for module in HSR_TASK_MODULES:
                if (
                    module_is_available(module, script_config)
                    and user_config.get("TaskSwitch", module.key)
                ):
                    enabled_module_keys.add(module.key)

        if not has_executable_user:
            return "未找到任何可执行用户，请确保至少有一个启用且剩余天数不为 0 的用户"

        if enabled_module_keys:
            game_exe_path = resolve_game_executable_path(script_config)
            if not game_exe_path.exists():
                return f"游戏启动文件不存在：{game_exe_path}"

        if "SRA" in self.effective_engines:
            return self._validate_sra_user_credentials(
                script_config,
                only_sra_needed=False,
            )

        return "Pass"

    @staticmethod
    def _is_executable_user(user_config) -> bool:
        """判断用户是否处于本轮可执行状态。"""

        return (
            bool(user_config.get("Info", "Status"))
            and user_config.get("Info", "RemainedDay") != 0
        )

    def _m7a_only_skip_reason(self, executable_user_index: int) -> str | None:
        """Return the explicit skip reason after the first M7A-only account."""

        if self.effective_engines == ("M7A",) and executable_user_index > 0:
            return "M7A-only 仅支持当前登录账号"
        return None

    @staticmethod
    def _user_needs_sra(user_config, script_config: Any) -> bool:
        """判断用户是否需要 SRA StartGame 登录/切号。"""

        for module in HSR_TASK_MODULES:
            if not user_config.get("TaskSwitch", module.key):
                continue
            if (
                get_assigned_script(module, script_config) == "SRA"
            ):
                return True
        return False

    def _validate_sra_user_credentials(
        self,
        script_config: Any,
        *,
        only_sra_needed: bool,
    ) -> str:
        """校验启用用户的 SRA 登录/切号凭证。"""

        if self.user_config is None:
            return "HSR 用户配置尚未加载"
        for _uid, user_config in self.user_config.items():
            if not self._is_executable_user(user_config):
                continue
            if (
                only_sra_needed
                and not self._user_needs_sra(user_config, script_config)
            ):
                continue

            user_name = user_config.get("Info", "Name")
            result = check_user_credentials(user_config, user_name)
            if result != "Pass":
                return result

        return "Pass"

    def _check_manual_review(self, script_config: Any) -> str:
        """校验 HSR 人工检查需要的 SRA 切号配置。"""

        if "SRA" not in self.effective_engines:
            return "人工排查仅在当前脚本启用 SRA 时可用"

        sra_path = script_config.get("SRA", "Path")
        if not sra_path:
            return "人工排查需要先设置 SRA 路径"

        sra_exe = Path(sra_path) / "SRA-cli.exe"
        if not sra_exe.exists():
            return f"SRA 路径中未找到 SRA-cli.exe：{sra_exe}"

        game_exe_path = resolve_game_executable_path(script_config)
        if not game_exe_path.exists():
            return f"游戏启动文件不存在：{game_exe_path}"

        has_executable_user = False
        if self.user_config is None:
            return "HSR 用户配置尚未加载"
        for _uid, user_config in self.user_config.items():
            if not self._is_executable_user(user_config):
                continue

            has_executable_user = True

        if not has_executable_user:
            return "未找到任何可检查用户，请确保至少有一个启用且剩余天数不为 0 的用户"

        return self._validate_sra_user_credentials(
            script_config,
            only_sra_needed=False,
        )

    async def _apply_completion_writebacks(self) -> None:
        """在配置解锁后，把真实成功的完成态写回用户 Data。"""

        pending = list(self._completion_writebacks)
        if not pending:
            return

        if self.store is None:
            raise RuntimeError("HSR 配置存储尚未初始化")
        for item in pending:
            update: dict[str, dict[str, object]] = {}
            for group, key, value in item.fields:
                update.setdefault(group, {})[key] = value
            await self.store.update_user_data(item.user_id, update)
            logger.success(
                f"用户「{item.user_name}」HSR 完成态已写回：{item.reason}"
            )

        await Config.ScriptConfig.save()
        self._completion_writebacks.clear()

    async def prepare(self):
        """锁定配置、加载用户列表（不启动外部程序）"""

        if self.store is None:
            raise RuntimeError("HSR 配置存储尚未初始化")
        await self.store.lock()
        self.script_config = await self.store.load_script_model()
        self.user_config = await self.store.load_user_collection()
        object.__setattr__(
            self.script_config,
            "_hsr_effective_engines",
            self.effective_engines,
        )

        logger.success(f"{self.script_info.script_id} 已锁定，HSR 配置提取完成")

        external_roots = _resolve_external_lock_paths(
            self.script_config,
            self.effective_engines,
        )
        self._external_path_locks = await acquire_external_path_locks(external_roots)
        self._append_log("HSR 外部脚本目录运行锁已获取")

        self._backup_external_configs()
        self._append_log("HSR 外部脚本配置已备份")
        if "SRA" in self.effective_engines:
            try:
                from automas_hsr_adapter_sra.runner import (
                    disable_sra_windows_notifications,
                )

                disable_sra_windows_notifications()
                self._append_log("SRA 本体 Windows 通知已临时关闭")
            except Exception as e:  # noqa: BLE001
                logger.warning(f"SRA 本体 Windows 通知关闭失败：{e}")
                self._append_log(f"SRA 本体 Windows 通知关闭失败，将继续执行：{e}")

        self.script_info.user_list = [
            UserItem(
                user_id=str(uid),
                name=config.get("Info", "Name"),
                status="等待",
            )
            for uid, config in self.user_config.items()
            if config.get("Info", "Status")
            and config.get("Info", "RemainedDay") != 0
        ]
        logger.info(
            f"HSR 用户列表加载完成，已筛选用户数：{len(self.script_info.user_list)}"
        )
        self._append_log(
            f"HSR 配置已加载，可执行用户数：{len(self.script_info.user_list)}"
        )

    async def main_task(self):
        """主任务入口。"""

        self._append_log("开始 HSR 配置检查")
        self.check_result = await self.check()
        if self.check_result != "Pass":
            logger.error(f"HSR 配置检查未通过：{self.check_result}")
            self._append_log(f"HSR 配置检查未通过：{self.check_result}")
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": self.check_result},
            )
            return

        self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await self.prepare()

        if self.script_config is None or self.user_config is None:
            raise RuntimeError("HSR 插件配置加载失败")

        if not self.script_info.user_list:
            logger.warning("HSR 无可用用户，跳过执行")
            self._append_log("HSR 无可用用户，跳过执行")
            self.script_info.status = "完成"
            return

        task_cls = METHOD_BOOK[self.task_info.mode]
        steps_count = 0
        user_errors: list[str] = []
        try:
            for user_index, user_item in enumerate(self.script_info.user_list):
                self.script_info.current_index = user_index
                m7a_skip_reason = self._m7a_only_skip_reason(user_index)
                if m7a_skip_reason is not None:
                    user_item.status = "跳过"
                    user_item.log_record[datetime.now()] = LogRecord(
                        status=f"跳过：{m7a_skip_reason}",
                        content=["M7A-only 只执行持久化顺序中第一个可用账号。\n"],
                    )
                    self._append_log(
                        f"用户「{user_item.name}」跳过：{m7a_skip_reason}"
                    )
                    continue
                proxy = None
                try:
                    proxy = task_cls(
                        self.script_info,
                        self.script_config,
                        self.user_config,
                        user_item,
                        self._runtime,
                    )
                    await self.spawn(proxy)
                    steps_count += getattr(proxy, "steps_count", 0)
                except asyncio.CancelledError:
                    raise
                except Exception as e:  # noqa: BLE001
                    user_item.status = "异常"
                    if user_item.log_record:
                        latest_time = max(user_item.log_record)
                        user_log = user_item.log_record[latest_time]
                    else:
                        user_log = LogRecord()
                        user_item.log_record[datetime.now()] = user_log
                    user_log.status = f"HSR 执行异常: {e}"
                    user_log.content.append(str(e))
                    user_errors.append(f"用户「{user_item.name}」执行异常：{e}")
                    logger.exception(f"HSR 用户「{user_item.name}」执行异常，继续后续用户：{e}")
                    self._append_log(
                        f"用户「{user_item.name}」执行异常，继续处理后续用户：{e}"
                    )
                    continue

                if proxy.crashed:
                    error_message = proxy.error_message or "HSR 用户任务异常"
                    user_errors.append(f"用户「{user_item.name}」执行异常：{error_message}")
                    logger.error(
                        f"HSR 用户「{user_item.name}」执行异常，继续后续用户："
                        f"{error_message}"
                    )
                    self._append_log(
                        f"用户「{user_item.name}」执行异常，继续处理后续用户："
                        f"{error_message}"
                    )
        except asyncio.CancelledError:
            self.crashed = True
            self._append_log("HSR 任务收到停止请求，正在终止 SRA/M7A")
            await self._stop_external_processes()
            raise

        if user_errors:
            self._append_log(
                "HSR 部分用户执行异常，已继续处理后续用户："
                + "；".join(user_errors)
            )

        if self.task_info.mode == "AutoProxy" and steps_count == 0 and not user_errors:
            logger.info("HSR 无模块需要执行，所有用户跳过")
            self._append_log("HSR 无模块需要执行，所有用户跳过")
            self.script_info.status = "完成"
            return

        logger.info(
            "HSR 执行计划处理完毕，"
            f"共 {len(self.script_info.user_list)} 个用户，"
            f"共 {steps_count} 个步骤"
        )
        self._append_log(
            f"HSR 执行计划处理完成：{len(self.script_info.user_list)} 个用户，"
            f"{steps_count} 个步骤"
        )

    async def _persist_user_logs(self) -> None:
        """将 HSR 用户日志写入历史记录。"""

        for user_item in self.script_info.user_list:
            for start_time, log_item in user_item.log_record.items():
                if log_item.status == "HSR 正常运行中":
                    log_item.status = (
                        "任务被用户手动中止"
                        if self.crashed
                        else "HSR 任务结束"
                    )
                if not log_item.content:
                    log_item.content = ["未捕获到任何 HSR 日志内容\n"]
                    if log_item.status in ("未开始监看日志", "HSR 正常运行中"):
                        log_item.status = "未捕获到日志"

                dt = start_time.replace(
                    tzinfo=datetime.now().astimezone().tzinfo
                ).astimezone(UTC4)
                log_path = (
                    Path.cwd()
                    / f"history/{dt.strftime('%Y-%m-%d')}"
                    / user_item.name
                    / f"{dt.strftime('%H-%M-%S')}.log"
                )
                await Config.save_hsr_log(
                    log_path, log_item.content, log_item.status
                )

    async def _restore_external_configs(self) -> str:
        """恢复 SRA / M7A 外部配置，返回错误文本或空串。"""

        if not self._external_config_targets:
            return ""

        try:
            self._restore_external_config_targets()
            self._append_log("HSR 外部脚本配置已恢复")
            return ""
        except Exception as e:  # noqa: BLE001
            logger.exception(f"HSR 外部脚本配置恢复失败：{e}")
            self._append_log(f"HSR 外部脚本配置恢复失败：{e}")
            return f"HSR 外部脚本配置恢复失败：{e}"

    async def _sync_manual_review_user_data(self) -> None:
        """人工检查模式下，把本轮检查结果写回真实 UserData。"""

        if self.task_info.mode != "ManualReview" or self.user_config is None:
            return

        if self.store is None:
            return
        await self.store.save_user_models(self.user_config)
        await Config.ScriptConfig.save()
        logger.success("HSR 人工检查结果已写回用户配置")

    async def _unlock_script_config(self) -> bool:
        """解锁当前 HSR 脚本配置；配置已不存在时跳过。"""

        if self.store is None:
            logger.warning(f"HSR 脚本配置不存在，跳过解锁：{self.script_info.script_id}")
            return False

        await self.store.unlock()
        return True

    async def _push_result_notification(self) -> None:
        """推送 HSR 脚本级任务结果。"""

        if not self.script_info.user_list:
            return

        over_user = [
            u.name for u in self.script_info.user_list if u.status == "完成"
        ]
        unfinished_user = [
            u.name for u in self.script_info.user_list if u.status != "完成"
        ]
        uncompleted_count = len(unfinished_user)
        task_mode = TASK_MODE_ZH.get(self.task_info.mode, self.task_info.mode)
        title = (
            f"{datetime.now().strftime('%m-%d')} | "
            f"{self.script_info.name or '空白'}的{task_mode}任务报告"
        )
        result = {
            "title": f"{task_mode}任务报告",
            "script_name": self.script_info.name or "空白",
            "start_time": self.begin_time,
            "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "completed_count": len(over_user),
            "uncompleted_count": uncompleted_count,
            "result": self.script_info.result,
        }

        try:
            await Notify.push_plyer(
                title.replace("报告", "已完成！"),
                f"已完成用户数: {len(over_user)}, 未完成用户数: {uncompleted_count}",
                f"已完成用户数: {len(over_user)}, 未完成用户数: {uncompleted_count}",
                10,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception(f"推送 HSR 系统通知时出现异常: {e}")
            await self._send_notification_error(
                f"推送 HSR 系统通知时出现异常: {e}"
            )

        try:
            await push_notification("代理结果", title, result, None)
        except Exception as e:  # noqa: BLE001
            logger.exception(f"推送 HSR 代理结果时出现异常: {e}")
            await self._send_notification_error(
                f"推送 HSR 代理结果时出现异常: {e}"
            )

    async def _send_notification_error(self, message: str) -> None:
        """通知失败时尽量提示前端；提示失败不影响任务收尾。"""

        try:
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": message},
            )
        except Exception as e:  # noqa: BLE001
            logger.warning(f"发送 HSR 通知错误提示失败：{e}")

    async def final_task(self):
        """解锁配置、恢复外部配置并落盘日志。"""

        final_errors: list[str] = []
        try:
            await self._stop_external_processes()
        except Exception as e:  # noqa: BLE001
            msg = f"停止 SRA/M7A 外部进程失败：{e}"
            logger.exception(msg)
            self._append_log(msg)
            final_errors.append(msg)

        try:
            await self._close_game_if_needed()
        except Exception as e:  # noqa: BLE001
            msg = f"关闭 HSR 游戏进程失败：{e}"
            logger.exception(msg)
            self._append_log(msg)
            final_errors.append(msg)

        restore_error = await self._restore_external_configs()
        if restore_error:
            final_errors.append(restore_error)

        release_external_path_locks(self._external_path_locks)
        self._external_path_locks = []

        if final_errors:
            self.crashed = True

        if self.check_result != "Pass" or self.crashed:
            self.script_info.status = "异常"
            self._append_log("HSR 异常或中止结束，开始解锁配置")
            logger.info("HSR 异常结束，开始解锁配置")
            if await self._unlock_script_config():
                logger.info(f"已解锁脚本配置 {self.script_info.script_id}（异常结束）")
                self._append_log("HSR 配置已解锁（异常或中止结束）")
            try:
                if self.task_info.mode == "AutoProxy":
                    await self._apply_completion_writebacks()
                else:
                    await self._sync_manual_review_user_data()
            except Exception as e:  # noqa: BLE001
                msg = f"HSR 已完成模块状态写回失败：{e}"
                logger.exception(msg)
                self._append_log(msg)
                final_errors.append(msg)
            await self._persist_user_logs()
            await self._push_result_notification()
            return "；".join(final_errors) or self.check_result

        logger.info("HSR 主任务已结束，开始解锁配置")
        self._append_log("HSR 主任务已结束，开始解锁配置")
        if await self._unlock_script_config():
            logger.success(f"已解锁脚本配置 {self.script_info.script_id}")
            self._append_log("HSR 配置已解锁")

        try:
            if self.task_info.mode == "AutoProxy":
                await self._apply_completion_writebacks()
            else:
                await self._sync_manual_review_user_data()
        except Exception as e:
            self.script_info.status = "异常"
            logger.exception(f"HSR 用户数据写回失败：{e}")
            self._append_log(f"HSR 用户数据写回失败：{e}")
            return f"HSR 用户数据写回失败：{e}"

        if any(user.status == "异常" for user in self.script_info.user_list):
            self.script_info.status = "异常"
        else:
            self.script_info.status = "完成"
        self._append_log("HSR 任务完成")
        await self._persist_user_logs()
        await self._push_result_notification()

    async def on_crash(self, e: Exception):
        """任务异常处理"""

        self.crashed = True
        self.script_info.status = "异常"
        logger.exception(f"HSR 任务出现异常：{e}")
        self._append_log(f"HSR 任务出现异常：{e}")
        await Config.send_websocket_message(
            id=self.task_info.task_id,
            type="Info",
            data={"Error": f"HSR 任务出现异常：{e}"},
        )
