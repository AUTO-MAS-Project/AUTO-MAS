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
from app.core.ws import Publisher, protocol
from app.models.schema import WSTaskNoticeData
from app.models.ConfigBase import MultipleConfig
from app.models.config import HSRConfig, HSRUserConfig
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase, UserItem
from app.services import Notify
from app.utils import get_logger
from app.utils.constants import TASK_MODE_ZH, UTC4, UTC8
from app.tools.game_sign_notify import (
    append_task_game_sign_summary,
    mark_task_game_sign_summary_consumed,
)
from .AutoProxy import HSRAutoProxyTask
from .tools.run_model import CompletionWriteback, HSRRuntimeState
from .task_mapping import HSR_TASK_MODULES, get_assigned_script, script_supports
from .tools import push_notification
from .tools.account_switch import (
    HSRAccountSwitcher,
    check_user_credentials,
    close_game_if_needed,
    is_game_management_enabled,
    restore_game_resolution_if_needed,
    resolve_game_executable_path,
    stop_external_processes,
    user_needs_account_switch,
)
from .tools.sra_runtime import (
    disable_sra_windows_notifications,
    get_sra_app_data_dir,
    load_sra_native_config,
)
from .tools.m7a_config import load_m7a_native_config
from .tools.native_control import (
    get_user_direct_config,
    native_provider,
    resolve_configured_engines,
    resolve_script_path,
    resolve_user_control,
)
from .tools.external_locks import (
    HSRExternalPathLockLease,
    acquire_external_path_locks,
    resolve_external_lock_paths,
)


logger = get_logger("HSR 调度器")

METHOD_BOOK: dict[str, type[HSRAutoProxyTask]] = {
    "AutoProxy": HSRAutoProxyTask,
}


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

    def __init__(self, script_info: ScriptItem):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.check_result: str = "-"
        self.begin_time: str = ""
        self.crashed: bool = False
        self.script_config: HSRConfig | None = None
        self.user_config: MultipleConfig[HSRUserConfig] | None = None
        # 真实执行成功后的完成态写回队列。执行链路只登记意图，等待 final_task()
        # 确认整轮正常结束、脚本配置解锁后，再写回真实 UserData。
        self._completion_writebacks: list[CompletionWriteback] = []
        self._log_lines: list[str] = []
        self._runtime: HSRRuntimeState = HSRRuntimeState(
            log_lines=self._log_lines,
            completion_writebacks=self._completion_writebacks,
        )
        self.temp_path: Path = Path.cwd() / f"data/{self.script_info.script_id}/Temp"
        self._external_config_targets: list[tuple[str, Path, Path, bool]] = []
        # 同一上游 M7A/SRA 路径可能被多个 HSR 脚本共享；持有至恢复完成。
        self._external_path_lock: HSRExternalPathLockLease | None = None
        # 旧 dev 没有插件 registry；由调度器独占本轮直控会话并在停止时取消。
        self._direct_sessions: dict[str, Any] = {}

    def _release_external_path_lock(self) -> None:
        lease = self._external_path_lock
        self._external_path_lock = None
        if lease is not None:
            lease.release()

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

        m7a_path = resolve_script_path(self.script_config, "M7A")
        if m7a_path:
            backup_path(
                "M7A config.yaml",
                Path(str(m7a_path)) / "config.yaml",
                backup_root / "M7A" / "config.yaml",
            )

        sra_path = resolve_script_path(self.script_config, "SRA")
        if sra_path:
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
                logger.opt(exception=True).warning(f"恢复 HSR 外部配置失败：{label}: {e}")

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

        for engine, session in reversed(list(self._direct_sessions.items())):
            try:
                await session.cancel()
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"终止 HSR {engine} 直控会话失败：{exc}")
                self._append_log(f"终止 HSR {engine} 直控会话失败：{exc}")

        await stop_external_processes(
            self._runtime,
            self._append_log,
            self.script_config,
        )

    async def _close_game_if_needed(self) -> None:
        """任务结束后关闭由 MAS 本次启动的游戏。"""

        if not isinstance(self.script_config, HSRConfig):
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

        script_config = Config.ScriptConfig[script_id]
        if not isinstance(script_config, HSRConfig):
            return "脚本配置类型错误，不是 HSR 脚本类型"

        game_management_enabled = is_game_management_enabled(script_config)

        m7a_path = resolve_script_path(script_config, "M7A")
        sra_path = resolve_script_path(script_config, "SRA")
        effective_engines = resolve_configured_engines(script_config)

        if not m7a_path and not sra_path:
            return "未配置任何脚本路径，请至少填写 M7A 或 SRA 路径"

        for module in HSR_TASK_MODULES:
            raw_assigned = script_config._config_item_index["TaskMapping"][module.key].value
            if not script_supports(module.key, raw_assigned):
                return (
                    f"模块「{module.name}」的分配脚本 '{raw_assigned}' "
                    f"不被该模块支持（仅支持：{'、'.join(module.supported_scripts)}）"
                )

        m7a_available = False
        sra_available = False

        if m7a_path:
            m7a_exe = Path(m7a_path) / "March7th Assistant.exe"
            if not m7a_exe.exists():
                return f"M7A 路径中未找到 March7th Assistant.exe：{m7a_exe}"
            m7a_available = True

        if sra_path:
            sra_exe = Path(sra_path) / "SRA-cli.exe"
            if not sra_exe.exists():
                return f"SRA 路径中未找到 SRA-cli.exe：{sra_exe}"
            sra_available = True

        has_executable_user = False
        has_direct_user = False
        m7a_needed = False
        sra_needed = False
        managed_user_count = 0
        managed_users_with_credentials = 0
        enabled_module_keys: set[str] = set()

        for uid, user_config in script_config.UserData.items():
            if not user_config.get("Info", "Status"):
                continue
            if user_config.get("Info", "RemainedDay") == 0:
                continue
            has_executable_user = True

            control = resolve_user_control(user_config, script_config=script_config)
            user_name = str(user_config.get("Info", "Name") or uid)
            if control.mode == "direct":
                has_direct_user = True
                if self.task_info.mode != "AutoProxy":
                    return f"用户「{user_name}」启用了脚本直控，但直控仅支持自动代理"
                if not control.engines:
                    return f"用户「{user_name}」尚未启用任何直控脚本"
                for engine in control.engines:
                    # 已导入快照可脱离当前原生配置文件运行；这里只要求
                    # 当前 CLI/Assistant 可执行，避免配置器改名后误阻断直控。
                    script_root = resolve_script_path(script_config, engine)
                    if not script_root:
                        return f"用户「{user_name}」{engine} 直控不可用：未配置原生脚本路径"
                    executable = (
                        Path(script_root)
                        / ("SRA-cli.exe" if engine == "SRA" else "March7th Assistant.exe")
                    )
                    if not executable.is_file():
                        return (
                            f"用户「{user_name}」{engine} 直控不可用："
                            f"原生执行文件不存在：{executable}"
                        )
                    if not get_user_direct_config(user_config, engine).strip():
                        return f"用户「{user_name}」尚未导入 {engine} 原生配置快照"
                # 直控快照包含完整原生计划，跳过 MAS 模块队列和凭证检查。
                continue

            managed_user_count += 1
            if user_needs_account_switch(user_config):
                managed_users_with_credentials += 1

            for module in HSR_TASK_MODULES:
                if user_config.get("TaskSwitch", module.key):
                    enabled_module_keys.add(module.key)
                    assigned = get_assigned_script(
                        module,
                        script_config,
                        user_config=user_config,
                        effective_engines=effective_engines,
                    )
                    if assigned == "SRA":
                        sra_needed = True
                    if assigned == "M7A":
                        m7a_needed = True
                    if assigned == "M7A" and not m7a_available:
                        return f"用户「{user_name}」模块「{module.name}」分配给了 M7A，但 M7A 路径不可用"
                    if assigned == "SRA" and not sra_available:
                        return f"用户「{user_name}」模块「{module.name}」分配给了 SRA，但 SRA 路径不可用"

        if not has_executable_user:
            return "未找到任何可执行用户，请确保至少有一个启用且剩余天数不为 0 的用户"

        if game_management_enabled and (enabled_module_keys or has_direct_user):
            if not str(script_config.get("Game", "Path") or "").strip():
                return "请设置游戏路径"
            game_exe_path = resolve_game_executable_path(script_config)
            if not game_exe_path.exists():
                return f"游戏启动文件不存在：{game_exe_path}"

        # 切号只能通过 SRA StartGame 完成（M7A 原生配置里不写账号密码）。
        # 缺少 SRA 路径时 _build_login_plan 会直接回落到 m7a_fallback，队列里
        # 不再插入 StartGame，而游戏已在运行时启动环节又会跳过——于是切号被
        # 静默跳过，多个用户全跑在同一个已登录账号上，还各自写回完成态。
        # 只在确实配了账密时才管：没配账密的用户本来就依赖当前登录态，
        # 有没有 SRA 都是同一个账号，不该被这条拦住。
        if not sra_available and managed_users_with_credentials:
            if managed_user_count > 1:
                return (
                    f"有 {managed_users_with_credentials} 个启用的托管用户配置了账号密码，"
                    "但未配置 SRA 路径。切换账号只能通过 SRA 完成，"
                    "否则所有用户都会跑在同一个已登录账号上。"
                    "请填写 SRA 路径，或只保留一个启用的托管用户"
                )
            self._append_log(
                "未配置 SRA 路径，本轮不会登录到所填账号，"
                "将直接使用游戏当前已登录的账号"
            )

        try:
            if m7a_needed:
                load_m7a_native_config(script_config)
            if sra_needed:
                load_sra_native_config(script_config)
        except (FileNotFoundError, OSError, ValueError) as exc:
            return f"HSR 原生配置不可用：{exc}"

        if sra_available:
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

    @staticmethod
    def _user_needs_sra(user_config, script_config: HSRConfig) -> bool:
        """判断用户是否需要 SRA StartGame 登录/切号。"""

        effective_engines = resolve_configured_engines(script_config)
        for module in HSR_TASK_MODULES:
            if not user_config.get("TaskSwitch", module.key):
                continue
            if get_assigned_script(
                module,
                script_config,
                user_config=user_config,
                effective_engines=effective_engines,
            ) == "SRA":
                return True
        return False

    def _validate_sra_user_credentials(
        self,
        script_config: HSRConfig,
        *,
        only_sra_needed: bool,
    ) -> str:
        """校验启用用户的 SRA 登录/切号凭证。"""

        for _uid, user_config in script_config.UserData.items():
            if not self._is_executable_user(user_config):
                continue
            if resolve_user_control(
                user_config,
                script_config=script_config,
            ).mode == "direct":
                continue
            if only_sra_needed and not self._user_needs_sra(user_config, script_config):
                continue

            user_name = user_config.get("Info", "Name")
            result = check_user_credentials(user_config, user_name)
            if result != "Pass":
                return result

        return "Pass"

    async def _apply_completion_writebacks(self) -> None:
        """在配置解锁后，把真实成功的完成态写回用户 Data。"""

        pending = list(self._completion_writebacks)
        if not pending:
            return

        script_id = uuid.UUID(self.script_info.script_id)
        script_config = Config.ScriptConfig[script_id]
        for item in pending:
            user_uuid = uuid.UUID(item.user_id)
            user_config = script_config.UserData[user_uuid]
            for group, key, value in item.fields:
                await user_config.set(group, key, value)
            logger.success(
                f"用户「{item.user_name}」HSR 完成态已写回：{item.reason}"
            )

        self._completion_writebacks.clear()

    async def prepare(self):
        """锁定配置、加载用户列表（不启动外部程序）"""

        script_id = uuid.UUID(self.script_info.script_id)
        await Config.ScriptConfig[script_id].lock()
        self.script_config = Config.ScriptConfig[script_id]
        self.user_config = MultipleConfig([HSRUserConfig])
        await self.user_config.load(
            await self.script_config.UserData.toDict(if_decrypt=False)
        )

        logger.success(f"{self.script_info.script_id} 已锁定，HSR 配置提取完成")

        try:
            external_paths = resolve_external_lock_paths(
                self.script_config,
                ("SRA", "M7A"),
            )
            self._external_path_lock = await acquire_external_path_locks(
                external_paths,
                wait=False,
            )
            self._append_log("HSR 外部脚本目录运行锁已获取")

            self._backup_external_configs()
            self._append_log("HSR 外部脚本配置已备份")
            if resolve_script_path(self.script_config, "SRA"):
                try:
                    disable_sra_windows_notifications()
                    self._append_log("SRA 本体 Windows 通知已临时关闭")
                except Exception as e:  # noqa: BLE001
                    logger.warning(f"SRA 本体 Windows 通知关闭失败：{e}")
                    self._append_log(f"SRA 本体 Windows 通知关闭失败，将继续执行：{e}")
        except BaseException:
            # 若备份已登记目标，交给 final_task 在恢复后释放；否则没有
            # 关键区需要收尾，可以立即释放空/已获取的 lease。
            if not self._external_config_targets:
                self._release_external_path_lock()
            raise

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
            logger.warning(f"HSR 配置检查未通过：{self.check_result}")
            self._append_log(f"HSR 配置检查未通过：{self.check_result}")
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=self.check_result),
            )
            return

        self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await self.prepare()

        if not isinstance(self.script_config, HSRConfig) or self.user_config is None:
            raise RuntimeError("脚本配置类型错误，不是 HSR 脚本类型")

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
                proxy = None
                try:
                    user_config = self.user_config[uuid.UUID(user_item.user_id)]
                    control = resolve_user_control(
                        user_config,
                        script_config=self.script_config,
                    )
                    if control.mode == "direct":
                        steps_count += await self._run_direct_user(
                            user_item,
                            user_config,
                        )
                    else:
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
                    logger.opt(exception=True).warning(f"HSR 用户「{user_item.name}」执行异常，继续后续用户：{e}")
                    self._append_log(
                        f"用户「{user_item.name}」执行异常，继续处理后续用户：{e}"
                    )
                    continue

                if proxy is not None and proxy.crashed:
                    error_message = proxy.error_message or "HSR 用户任务异常"
                    user_errors.append(f"用户「{user_item.name}」执行异常：{error_message}")
                    logger.warning(
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

    async def _run_direct_user(self, user_item: UserItem, user_config: Any) -> int:
        """运行一个用户导入的原生 SRA/M7A 快照。

        直控只把外部配置交给对应 CLI；MAS 是否管理游戏启停由脚本开关决定，
        日志、取消和会话收尾始终由 MAS 负责。没有新 ``Control``/``Direct``
        字段时不会进入此路径。
        """

        if self.script_config is None:
            raise RuntimeError("HSR 脚本配置尚未加载")
        control = resolve_user_control(user_config, script_config=self.script_config)
        user_name = str(user_config.get("Info", "Name") or user_item.name)
        started_at = datetime.now()
        log_item = LogRecord(status="HSR 脚本直控运行中")
        user_item.log_record[started_at] = log_item
        user_item.status = "运行"
        log_start = len(self._log_lines)

        switcher = HSRAccountSwitcher(
            script_config=self.script_config,
            runtime=self._runtime,
            append_log=self._append_log,
        )
        self._runtime.game_launch_checked = False
        await switcher.ensure_game_started_by_mas()
        if is_game_management_enabled(self.script_config):
            self._append_log(
                f"用户「{user_name}」进入脚本直控；MAS 负责先启动游戏并跟踪脚本进程，"
                f"原生配置原样执行：{'、'.join(control.engines)}"
            )
        else:
            self._append_log(
                f"用户「{user_name}」进入脚本直控；MAS 不管理游戏，"
                f"仅运行原生配置并跟踪脚本进程：{'、'.join(control.engines)}"
            )

        summaries: list[str] = []
        try:
            for engine in control.engines:
                # 复用旧脚本切号的等待/切换语义。
                await switcher.wait_before_external_script(engine, user_name)
                provider = native_provider(engine)
                session = await provider.open_direct_session(
                    script_config=self.script_config,
                    config_content=get_user_direct_config(user_config, engine),
                    session_id=user_item.user_id,
                    log=self._append_log,
                )
                self._direct_sessions[engine] = session
                try:
                    result = await session.run(control.timeout_seconds)
                    if not result.success:
                        raise RuntimeError(result.error or f"{engine} 用户配置快照执行失败")
                    summary = result.summary or f"{engine} 用户配置快照执行完成"
                    summaries.append(summary)
                    self._append_log(f"用户「{user_name}」{summary}")
                except asyncio.CancelledError:
                    await session.cancel()
                    raise
                finally:
                    try:
                        await session.close()
                    finally:
                        if self._direct_sessions.get(engine) is session:
                            self._direct_sessions.pop(engine, None)
        except Exception:
            user_item.status = "异常"
            log_item.status = "HSR 脚本直控异常"
            log_item.content.extend(f"{line}\n" for line in self._log_lines[log_start:])
            raise

        user_item.status = "完成"
        log_item.status = "HSR 脚本直控完成"
        log_item.content.extend(f"{line}\n" for line in self._log_lines[log_start:])
        return len(control.engines)

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

                dt = start_time.astimezone(UTC4)
                log_path = Config.build_history_log_path(
                    script_name=self.script_info.name,
                    user_name=user_item.name,
                    log_time=dt,
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
            logger.opt(exception=True).warning(f"HSR 外部脚本配置恢复失败：{e}")
            self._append_log(f"HSR 外部脚本配置恢复失败：{e}")
            return f"HSR 外部脚本配置恢复失败：{e}"

    async def _unlock_script_config(self) -> bool:
        """解锁当前 HSR 脚本配置；配置已不存在时跳过。"""

        script_id = uuid.UUID(self.script_info.script_id)
        if script_id not in Config.ScriptConfig:
            logger.warning(f"HSR 脚本配置不存在，跳过解锁：{self.script_info.script_id}")
            return False

        await Config.ScriptConfig[script_id].unlock()
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
        task_result = append_task_game_sign_summary(
            self.task_info, self.script_info.result
        )
        has_game_sign_summary = task_result != self.script_info.result
        result = {
            "title": f"{task_mode}任务报告",
            "script_name": self.script_info.name or "空白",
            "start_time": self.begin_time,
            "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "completed_count": len(over_user),
            "uncompleted_count": uncompleted_count,
            "result": task_result,
            "game_sign_summary": has_game_sign_summary,
        }

        try:
            await Notify.push_plyer(
                title.replace("报告", "已完成！"),
                f"已完成用户数: {len(over_user)}, 未完成用户数: {uncompleted_count}",
                f"已完成用户数: {len(over_user)}, 未完成用户数: {uncompleted_count}",
                10,
            )
        except Exception as e:  # noqa: BLE001
            logger.opt(exception=True).warning(f"推送 HSR 系统通知时出现异常: {e}")
            await self._send_notification_error(
                f"推送 HSR 系统通知时出现异常: {e}"
            )

        try:
            await push_notification("代理结果", title, result, None)
            if has_game_sign_summary:
                mark_task_game_sign_summary_consumed(self.task_info)
        except Exception as e:  # noqa: BLE001
            logger.opt(exception=True).warning(f"推送 HSR 代理结果时出现异常: {e}")
            await self._send_notification_error(
                f"推送 HSR 代理结果时出现异常: {e}"
            )

    async def _send_notification_error(self, message: str) -> None:
        """通知失败时尽量提示前端；提示失败不影响任务收尾。"""

        try:
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=message),
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
            logger.opt(exception=True).warning(msg)
            self._append_log(msg)
            final_errors.append(msg)

        try:
            await self._close_game_if_needed()
        except Exception as e:  # noqa: BLE001
            msg = f"关闭 HSR 游戏进程失败：{e}"
            logger.opt(exception=True).warning(msg)
            self._append_log(msg)
            final_errors.append(msg)

        try:
            # 分辨率注册表只在游戏关闭后恢复，且放在 final_task 中保证
            # TaskExecuteBase 的取消/异常 finally 路径也不会遗留临时值。
            if is_game_management_enabled(self.script_config):
                restore_game_resolution_if_needed(
                    self._runtime,
                    self._append_log,
                )
        except Exception as e:  # noqa: BLE001
            msg = f"恢复星铁分辨率注册表失败：{e}"
            logger.opt(exception=True).warning(msg)
            self._append_log(msg)
            final_errors.append(msg)

        try:
            restore_error = await self._restore_external_configs()
        finally:
            # 备份/运行/恢复是同一关键区；配置解锁与通知在锁释放后进行。
            self._release_external_path_lock()
        if restore_error:
            final_errors.append(restore_error)

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
            except Exception as e:  # noqa: BLE001
                msg = f"HSR 已完成模块状态写回失败：{e}"
                logger.opt(exception=True).warning(msg)
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
        except Exception as e:
            self.script_info.status = "异常"
            logger.opt(exception=True).warning(f"HSR 用户数据写回失败：{e}")
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
        logger.opt(exception=True).warning(f"HSR 任务出现异常：{e}")
        self._append_log(f"HSR 任务出现异常：{e}")
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"HSR 任务出现异常：{e}"),
        )
