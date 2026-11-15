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
import time
import uuid
from contextlib import ExitStack, suppress
from datetime import datetime
from functools import partial
from pathlib import Path

from auto_mas_core import TaskMode, UserExpander
from auto_mas_core.host.config import config_manager
from auto_mas_core.host.core import (
    Config,
    EmulatorManager,
    GameMaintenance,
    Notify,
    Publisher,
)
from auto_mas_core.host.core_notify_task_content import (
    NOTIFY_SCREENSHOT_LIMIT as NOTIFY_SCREENSHOT_LIMIT,
)
from auto_mas_core.host.core_notify_task_content import (
    push_maintenance_notice,
)
from auto_mas_core.host.core_notify_task_content import (
    screenshot_entries as screenshot_entries,
)

# TODO(脚本更新迁移)：安装编排随统一更新业务迁入 L2；当前复用宿主公共安装执行与恢复。
from auto_mas_core.host.core_script_update import (
    ScriptUpdateRequest,
    auto_recover_script_install,
    run_script_update,
)
from auto_mas_core.host.core_ws import protocol
from auto_mas_core.host.models_notification_report import (
    TaskResultData,
    TaskResultReport,
)
from auto_mas_core.host.models_schema import WSTaskNoticeData
from auto_mas_core.host.task_emulator_core import close_emulator
from auto_mas_core.host.task_game_update import EmulatorGameUpdateTask
from auto_mas_core.host.task_maintenance import get_user_maintenance
from auto_mas_core.host.task_proxy_helpers import (
    CONFIG_BASE_NATIVE,
    CONFIG_BASE_SHARED,
    read_config_base,
)
from auto_mas_core.host.utils import constants as _utils_constants
from auto_mas_core.host.utils import fluxdown_cli as _utils_fluxdown_cli
from auto_mas_core.host.utils import game_update as _utils_game_update
from auto_mas_core.host.utils import get_logger, process
from auto_mas_core.host.utils import io as _utils_io
from auto_mas_core.host.utils_common_config import archive as _utils_config_archive

from maa_adapter import notifications as _format_maa
from maa_adapter import stages as stage_service
from maa_adapter.config import UserConfigType
from maa_adapter.config.script import MaaConfig
from maa_adapter.config.user import MaaUserConfig
from maa_adapter.constants import ARKNIGHTS_PACKAGE_NAME
from maa_adapter.native.backup import (
    archive_native_backup,
    collect_native_files,
    native_backup_root,
)
from maa_adapter.native.depot_cache import depot_cache_snapshot_dir, restore_depot_cache
from maa_adapter.tasks.auto_proxy import AutoProxyTask
from maa_adapter.tasks.config_session import ScriptConfigTask
from maa_adapter.tasks.context import prefetched_scope
from maa_adapter.tasks.view_session import ScriptViewTask
from maa_adapter.updates.config import restore_maa_update_config
from maa_adapter.updates.credentials import (
    resolve_takeover_cdk,
    resolve_takeover_credentials,
    use_maa_github_update,
)
from maa_adapter.updates.errors import MaaUpdateUnsafeError
from maa_adapter.updates.fluxdown import (
    discard_prepared_update,
    prepare_maa_fluxdown_update,
    query_latest_maa_version,
)
from maa_adapter.updates.game import ensure_game_updated
from maa_adapter.updates.install import MaaUpdaterRunningError, update_maa
from maa_adapter.updates.managed_recovery import MAAInstallAdapter
from maa_adapter.updates.resources.service import (
    _run_write_thread,
    acquire_resource_access_lock,
    get_resource_write_lock,
    has_incomplete_resource_update,
    latest_resource_clock,
    prepare_install_resources,
    read_resource_clock,
)
from maa_adapter.updates.software.package import (
    clear_deferred_update,
    has_delegated_update_failure,
    load_deferred_update,
    read_pending_update,
    save_deferred_update,
    write_pending_update,
)
from maa_adapter.updates.software.service import (
    cancel_maa_software_update_precheck,
    compare_versions,
    parse_version,
    prepare_maa_software_before_run,
    read_installed_release,
)

logger = get_logger("MAA 调度器")

METHOD_BOOK: dict[str, type[AutoProxyTask | ScriptConfigTask]] = {
    "AutoProxy": AutoProxyTask,
    "ScriptConfig": ScriptConfigTask,
}


class MaaManager(UserExpander[MaaConfig]):
    """MAA控制器"""

    maintenance_message = "明日方舟正在维护"

    def maintenance_game(self, user_config: UserConfigType) -> str | None:
        """按 MAA 账号服务器识别宿主维护公告对应的游戏键，不支持的服务器不参与维护判断。"""
        if isinstance(user_config, MaaUserConfig) and user_config.Info.Server in (
            "Official",
            "Bilibili",
        ):
            return "arknights"
        return None

    def __init__(self, script, config):
        """绑定 L3 专项上下文，初始化用户选择、维护跳过、更新准备、原生配置恢复与通知汇总状态。"""
        super().__init__(script, config)
        self.execution_mode = (
            "ScriptConfig"
            if self.task_info.mode == TaskMode.SCRIPT_VIEW
            else self.task_info.mode.value
        )
        self.user_config = config.users
        self.maintenance_only = False
        self._maintenance_skipped = set()
        self.has_proxy_run = False
        self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._rollup_image_pairs = []
        self._default_user = None
        self.check_result = "-"
        self.prepared = False
        # 锁是否已建立必须独立于 prepared 记录：配置锁可能先建立，而置位
        # prepared 要等 prepare() 整体返回, 中途被取消或失败时 final_task
        # 靠这个标志解锁（对齐 SRC 的 config_lock_acquired）
        self.config_lock_acquired = False
        self._resource_access: ExitStack = ExitStack()
        self._device_provider = None
        self.game_update_results: dict[str, _utils_game_update.GameUpdateResult] = {}
        self._game_update_tasks: list[EmulatorGameUpdateTask] = []
        self._update_config_dir: Path | None = None
        self._pending_update: tuple[str, str] | None = None
        self._active_proxy_task: AutoProxyTask | None = None
        self._updater_running: bool = False
        # 每批任务最多尝试一次更新；新 MaaManager 实例会重新检查。
        self._maa_update_checked = False

    async def finish(self) -> None:
        """停止更新预检查，登记待恢复安装并完成专项收尾，最后恢复临时配置和释放资源访问。"""
        try:
            # 预检查只属于本轮；主动中止或异常也必须回收，避免跨脚本后无法停止。
            if self._update_config_dir is not None:
                await cancel_maa_software_update_precheck(self.maa_set_path.parent)
        finally:
            try:
                if self._update_config_dir is not None and not self._updater_running:
                    try:
                        self._remember_pending_update()
                    except (OSError, ValueError) as error:
                        logger.warning(
                            f"MAA 本体更新: 保存恢复登记失败，仍尝试原生还原: {error}"
                        )
                await self._business_final()
            finally:
                try:
                    if self.prepared and not self.maintenance_only:
                        if self._updater_running:
                            await self.script_info.set_state(status="异常")
                            # 官方写盘后的配置可能无法按注入指纹自动恢复，原始内容留进已有备份池。
                            backup_path = await _run_write_thread(
                                _utils_config_archive.archive_files,
                                files=collect_native_files(self.temp_path),
                                store_root=native_backup_root(self.maa_set_path),
                                force=True,
                            )
                            logger.warning(
                                f"MAA 更新相关进程未能退出，任务前原生配置备份: {backup_path}；"
                                "请等待更新结束并退出 MAA 后，从原生配置备份恢复"
                            )
                        else:
                            restore_maa_update_config(
                                self.maa_set_path.parent,
                                snapshot_path=self.temp_path,
                                script_id=self.script_info.info.script_id,
                            )
                            # 通知、用户收尾异常或中止也必须恢复，再保留尚未安装的登记。
                            if (
                                self.temp_path.exists()
                                and not self._keep_script_config_changes()
                            ):
                                _utils_io.swap_in_dir(self.temp_path, self.maa_set_path)
                            await self._restore_pending_update()
                            _utils_io.clear_native_config_snapshot(self.temp_path)
                finally:
                    self._resource_access.close()

    def _remember_pending_update(self) -> None:
        """子任务被中止时也接回它保存的登记，再补读最后一次原生写盘。"""
        if (
            self._active_proxy_task is not None
            and self._active_proxy_task.pending_update
        ):
            self._pending_update = self._active_proxy_task.pending_update
        try:
            pending = read_pending_update(self.maa_set_path.parent)
        except (OSError, ValueError) as error:
            logger.warning(f"MAA 本体更新: 无法保留原生待更新登记: {error}")
            return
        if all(pending) and (self.maa_set_path.parent / pending[1]).is_file():
            self._pending_update = pending
            save_deferred_update(
                self.maa_set_path.parent, version=pending[0], package=pending[1]
            )

    async def _restore_pending_update(self) -> None:
        """恢复仍有包文件的登记；成功安装后已删除的包不重新登记。"""
        try:
            saved = load_deferred_update(self.maa_set_path.parent)
            if saved is not None:
                self._pending_update = saved
            if (
                self._pending_update is None
                or not (self.maa_set_path.parent / self._pending_update[1]).is_file()
            ):
                return
            release = read_installed_release(self.maa_set_path.parent)
            current = parse_version(release[0]) if release else None
            target = parse_version(self._pending_update[0])
            if current and target and compare_versions(target, current) <= 0:
                clear_deferred_update(self.maa_set_path.parent)
                self._pending_update = None
                return
            _, current_package = read_pending_update(self.maa_set_path.parent)
            if (
                not current_package
                or not (self.maa_set_path.parent / current_package).is_file()
            ):
                await _run_write_thread(
                    write_pending_update,
                    self.maa_set_path.parent,
                    version=self._pending_update[0],
                    package=self._pending_update[1],
                )
        except (OSError, ValueError) as error:
            logger.warning(f"MAA 本体更新: 无法恢复原生待更新登记: {error}")

    async def update_game_before_run(self) -> None:
        """更新游戏客户端，不执行代理或账号前后置脚本。"""
        script_config = Config.ScriptConfig[uuid.UUID(self.script_info.info.script_id)]
        if not isinstance(script_config, MaaConfig):
            raise TypeError("托管配置类型错误")
        selected = self.selected_user_configs()
        if not selected or not script_config.Run.IfCheckGameUpdate:
            return
        # 更新与代理分开执行，但更新期间仍保护设备配置，避免安装到变更后的实例。
        self.config_lock_acquired = True
        try:
            device_provider = (
                self._device_provider or EmulatorManager.get_emulator_instance
            )
            emulator = await device_provider(str(script_config.Emulator.Id))
            servers = dict.fromkeys((user.Info.Server for _, user in selected))
            for server in servers:
                update_task = EmulatorGameUpdateTask(
                    script_info=self.script_info,
                    script_config=script_config,
                    emulator_manager=emulator,
                    server=server,
                    package_name=ARKNIGHTS_PACKAGE_NAME[server],
                    checker=ensure_game_updated,
                    allow_mod_avd=True,
                )
                # 先登记，取消落在启动设备期间时收尾也能找到对应任务。
                self._game_update_tasks.append(update_task)
                await self._run_game_update(update_task)
                if update_task.result is not None:
                    self.game_update_results[server] = update_task.result
        except Exception as error:
            logger.warning(f"游戏更新准备失败，沿用原代理流程: {error}")
        finally:
            self.config_lock_acquired = True

    async def check(self) -> str | None:
        """执行托管级检查，将专项 Pass 结果转换为 L3 空值约定，其余内容作为失败原因。"""
        self.check_result = await self._business_check()
        return None if self.check_result == "Pass" else self.check_result

    async def _business_check(self) -> str:
        """校验MAA配置是否可用"""
        if self.execution_mode not in METHOD_BOOK:
            return "不支持的任务模式，请检查任务配置！"
        script_config = Config.ScriptConfig[uuid.UUID(self.script_info.info.script_id)]
        if not isinstance(script_config, MaaConfig):
            return "托管配置类型错误, 不是MAA托管类型"
        if script_config.Emulator.Id == "-" or script_config.Emulator.Index in [
            "",
            "-",
        ]:
            return "未完成模拟器配置, 请检查托管配置中的模拟器设置！"
        root_path = script_config.Info.Path
        if root_path is None or not root_path.is_dir():
            return "MAA.exe文件不存在, 请检查MAA路径设置！"
        if not (root_path / "MAA.exe").is_file():
            # 有真实官方失败记录时，先进入已持锁的恢复询问，再检查
            # 重装后的主程序；无标记的普通无效安装仍拒绝。
            flag = root_path / "pending-update-failure.txt"
            if not flag.is_file() or flag.is_symlink():
                return "MAA.exe文件不存在, 请检查MAA路径设置！"
        if not (root_path / "config/gui.new.json").exists():
            return "MAA配置文件不存在, 请检查MAA路径设置或先启动MAA完成配置文件生成！"
        # 托管级存档仅在确实有用户选择共享来源时需要；独立来源使用各自的
        # 用户目录，原生来源则直接使用 MAA 安装目录的原生配置。
        if (
            self.execution_mode != "ScriptConfig"
            and self._has_script_config_user()
            and not (
                Path.cwd()
                / f"data/{self.script_info.info.script_id}/Default/ConfigFile"
            ).exists()
        ):
            return "未完成 MAA 全局设置, 请先设置 MAA！"
        return "Pass"

    def _has_script_config_user(self) -> bool:
        """参与运行的账号中是否有使用共享配置的账号。

        check() 先于 prepare() 执行，此时 self.user_config 尚未加载、user_list
        还是占位项；直接读脚本配置持久化的 UserData，按参与运行的账号（启用、
        剩余天数非 0、命中目标账号）判定。
        """

        return any(
            read_config_base(config, CONFIG_BASE_SHARED) == CONFIG_BASE_SHARED
            for uid, config in self.script_config.UserData.items()
            if self.is_user_selected(uid)
        )

    async def prepare(self):
        """运行前准备"""

        script_config = self.script_config
        install = script_config.Info.Path
        if install is None:
            raise ValueError("MAA 路径未配置")
        write_lock = get_resource_write_lock(install)
        if write_lock.locked():
            await self.script_info.set_log("等待 MAA 安装资源写入完成。")
        async with write_lock:
            access = await acquire_resource_access_lock(
                install, progress=self.script_info.set_log
            )
            if access is not None:
                self._resource_access.push(access)
            if await process.is_process_running(install / "MAA.Updater.exe"):
                raise MaaUpdaterRunningError("MAA 官方更新器仍在运行")
            if not await process.kill_process(install / "MAA.exe"):
                raise RuntimeError("无法关闭 MAA，暂不恢复或覆盖原生配置")
        self.config_lock_acquired = True
        self.script_config = script_config
        self.user_config = self.script_config.UserData
        logger.success(f"{self.script_info.info.script_id}已锁定, MAA配置提取完成")

        root_path = self.script_config.Info.Path
        if root_path is None:
            raise ValueError("Path未配置，请检查路径设置")
        self.maa_set_path = root_path / "config"
        self.temp_path = Path.cwd() / f"data/{self.script_info.info.script_id}/Temp"

        # 初始化模拟器管理器
        device_provider = self._device_provider or EmulatorManager.get_emulator_instance
        self.emulator_manager = await device_provider(
            str(self.script_config.Emulator.Id)
        )

        # 先处置上次崩溃残留的快照, 再备份原始配置。无条件清空会把崩溃后唯一
        # 一份原始配置副本删掉, 让注入污染的状态固化成「原始配置」。
        self._recover_previous_run()
        await self._restore_pending_update()

        # overlay 层覆写的库存缓存同样先还原：存底还在说明上次运行（崩溃、强杀）
        # 没走完结束还原，不还原就会把上一账号的库存固化成这一次的「原始现场」。
        depot_snapshot = depot_cache_snapshot_dir(self.script_info.info.script_id)
        if depot_snapshot.is_dir():
            logger.info("检测到上次中断的 MAA 库存缓存存底, 先还原安装目录")
            restore_depot_cache(self.maa_set_path.parent, depot_snapshot)

        if _utils_io.commit_native_config_snapshot(
            self.temp_path,
            self.maa_set_path,
            script_id=self.script_info.info.script_id,
        ):
            self.had_original_script_config = True

        # 任务级一次性归档 MAA 原生配置（项目级池，指纹去重，失败不阻断
        # 任务）：原生配置物理上跨账号共享，只代表「本轮任务动手前」的安装
        # 现场——下发处按账号归档会把上一轮下发的 MAS 配置误当原生内容挤进
        # 保留池，必须在任何下发前归档这一次
        with suppress(Exception):
            archive_native_backup(self.maa_set_path)

        # 启用阶段已预热关卡缓存，任务开始时按有效期检查，各账号共享同一次刷新。
        if self.execution_mode == "AutoProxy":
            await stage_service.get_stage()

        self.prepared = True
        await self._recover_unconfirmed_update()
        if self.task_info.mode != TaskMode.AUTO_PROXY:
            await self._prepare_default_user()
        elif self.script_config.Run.IfCheckGameUpdate:
            await self.update_game_before_run()

    def _recover_previous_run(self) -> None:
        """处置上次崩溃残留的原始配置快照。"""

        # 指纹不匹配会保护现场并清理 Temp；先入原安装的备份池，保留原始内容。
        # 上次归档若失败，本次也必须归档成功后才允许清理，不能只记录告警继续。
        if (
            _utils_io.read_native_config_snapshot(
                self.temp_path, expected_script_id=self.script_info.info.script_id
            )
            is not None
        ):
            files = collect_native_files(self.temp_path)
            if files:
                _utils_config_archive.archive_files(
                    files=files,
                    store_root=native_backup_root(self.maa_set_path),
                )
        # prepare 已确认官方更新器退出；先撤销首次账号注入之前的安装配置。
        # 按字段比较注入值，其他现场修改仍交给原快照指纹保护。
        restore_maa_update_config(
            self.maa_set_path.parent,
            snapshot_path=self.temp_path,
            script_id=self.script_info.info.script_id,
        )
        result = _utils_io.recover_native_config(
            self.temp_path,
            self.maa_set_path,
            expected_script_id=self.script_info.info.script_id,
        )
        if result == "restored":
            logger.info("已恢复上次中断前的 MAA 原始配置")
        elif result == "legacy":
            logger.warning(
                "检测到上次中断残留的 MAA 原生配置快照由旧版本生成, 已改名保留以便手动恢复"
            )
        elif result == "skipped":
            logger.warning(
                "检测到 MAA 原生配置在中断后被改动, 已保留当前配置并丢弃旧快照"
            )

    def _keep_script_config_changes(self) -> bool:
        """原生来源配置会话成功时保留 MAA 原生 GUI 的写回（对齐 MaaEnd 豁免）。

        原生来源会话 MAS 零写入（ScriptConfig ``set_maa`` 原生分支直接 return），
        安装 config/ 由本体保存；若 final_task 无条件用任务前快照还原，会把
        用户刚在原生 GUI 里改的配置抹回会话前状态。托管级（Default）与独立
        来源会话不豁免——它们的 GUI 改动已由 ``set_maa`` 收尾回写 MAS 目
        录，安装目录现场仍按任务前快照还原。viewOnly 查看会话不保留任何现
        场改动，结束后也还原任务前快照。
        """

        if self.execution_mode != "ScriptConfig" or (
            self.task_info.mode == TaskMode.SCRIPT_VIEW
        ):
            return False
        if not (
            list(self.script_info.users.values())
            and list(self.script_info.users.values())[0].status == "完成"
        ):
            return False
        user_id = list(self.script_info.users.values())[0].user_id
        if user_id == "Default":
            return False
        try:
            base = read_config_base(
                self.user_config[uuid.UUID(user_id)], CONFIG_BASE_SHARED
            )
        except (KeyError, ValueError, TypeError):
            return False
        return base == CONFIG_BASE_NATIVE

    async def _recover_unconfirmed_update(self) -> None:
        """公共入口核验官方本体和资源标记，自动选择安全恢复路径。"""
        root = self.maa_set_path.parent
        software_flag = root / "pending-update-failure.txt"
        resource_flag = root / ".automas-resource-update.json"
        if not any(
            path.exists() or path.is_symlink()
            for path in (software_flag, resource_flag)
        ):
            return

        # prepare() 已拿到资源写入锁并确认官方更新器停写。
        adapter = MAAInstallAdapter(root)

        async def install_resources() -> None:
            """按当前托管凭据选择资源来源，准备恢复安装所需的 MAA 资源。"""
            cdk = resolve_takeover_cdk(
                str(self.script_config.Update.MirrorChyanCDK or "")
            )
            await prepare_install_resources(root, cdk=cdk or None, github=not bool(cdk))

        async def reinstall() -> None:
            """调用安装恢复适配器重装 MAA，并通过资源回调补齐安装资源。"""
            await adapter.reinstall(install_resources)

        outcome = await auto_recover_script_install(
            ScriptUpdateRequest(str(self.script_info.info.script_id), "MAA"),
            install_root=root,
            inspect=adapter.inspect,
            acknowledge=adapter.acknowledge,
            reinstall=reinstall,
        )
        await self.script_info.set_log(f"MAA 官方安装/资源状态已自动恢复：{outcome}")
        # 避免刚恢复后同一轮又执行二次升级，异常留给任务结束统一报告。
        self._maa_update_checked = True

    async def main_task(self):
        """先处理全部账号均处维护期的跳过情况，否则绑定预下载路径并运行 L3 用户调度。"""
        if self.task_info.mode == TaskMode.AUTO_PROXY:
            selected = self.selected_user_configs()
            windows = [await self._maintenance_window(config) for _, config in selected]
            if selected and all(window is not None for window in windows):
                self._entered = True
                self.maintenance_only = True
                for (uid, _), window in zip(selected, windows):
                    user = next(
                        user
                        for user in self.script_info.users.values()
                        if user.info.user_id == str(uid)
                    )
                    await self._skip_maintenance(user, window)
                await self.notify_maintenance()
                return
        with prefetched_scope(self.context.params.get("prefetch_paths", {})):
            await super().main_task()

    async def _maintenance_window(self, config):
        """按账号服务器查询宿主维护信息，返回当前账号适用的维护时段。"""
        return await get_user_maintenance(
            self.maintenance_game(config),
            lookup=partial(GameMaintenance.get_active, proxy=Config.proxy),
        )

    async def _skip_maintenance(self, user, window):
        """登记因维护跳过的账号，并向用户运行节点写入跳过状态和原因。"""
        self._maintenance_skipped.add(user.info.user_id)
        await self.record_user_state(user, status="跳过", reason=window.reason)

    @property
    def all_users_maintenance_skipped(self):
        """判断本次确有选中账号，且所有账号均已因维护被跳过。"""
        users = self.script_info.users.values()
        return bool(self.script_info.users) and all(
            user.info.user_id in self._maintenance_skipped for user in users
        )

    async def final_task(self):
        """执行 L3 公共收尾，全部账号因维护跳过且无错误或取消时将托管结果设为跳过。"""
        await super().final_task()
        if (
            self.all_users_maintenance_skipped
            and not self.cancelled
            and self.error is None
        ):
            await self.script_info.set_state(status="跳过")

    def selected_user_configs(self):
        """从当前托管用户集合筛选本次任务明确选中的账号配置。"""
        return [
            (uid, entry)
            for uid, entry in self.script_config.users.items()
            if self.is_user_selected(uid)
        ]

    def is_user_selected(self, uid):
        """根据任务用户节点判断指定账号是否属于本次执行范围。"""
        return any(
            user.info.user_id == str(uid) for user in self.script_info.users.values()
        )

    def can_run_user(self, entry):
        """按任务模式判断账号是否需要执行，自动代理同时要求账号启用且剩余天数不为零。"""
        assert isinstance(entry, MaaUserConfig)
        return self.task_info.mode != TaskMode.AUTO_PROXY or (
            entry.Info.Status and entry.Info.RemainedDay != 0
        )

    def worker_accounts(self, user, config):
        """为账号配置会话返回实际用户集合，为共享配置会话返回临时默认账号。"""
        if config is not None:
            return self.script_config.users
        return {"Default": self._default_user}

    async def _prepare_default_user(self):
        """创建并激活共享配置使用的临时默认账号，使其复用插件用户模型和配置会话流程。"""
        from maa_adapter.config.user import MaaUserConfig

        self._default_user = MaaUserConfig.build(
            Info={"Name": "共享配置", "Base": "shared", "IfQuickConfig": False}
        )
        await self._default_user.activate()

    def build_worker(self, user, config):
        """按任务模式创建自动代理、脚本配置或脚本查看 L4，并绑定当前用户及已锁配置。"""
        worker = {
            TaskMode.AUTO_PROXY: AutoProxyTask,
            TaskMode.SCRIPT_CONFIG: ScriptConfigTask,
            TaskMode.SCRIPT_VIEW: ScriptViewTask,
        }[self.task_info.mode](self, user, config)
        return worker

    async def spawn(self, child):
        """在 L4 执行前处理维护与手动更新限制，准备一次性更新，执行后汇总截图并登记待恢复状态。"""
        if isinstance(child, AutoProxyTask):
            window = await self._maintenance_window(child.user_config)
            if window is not None:
                await self._skip_maintenance(child.user_info, window)
                return
            result = child.game_update_result
            if result is not None and result.status == "NeedManualUpdate":
                await self.record_user_state(
                    child.user_info, status="异常", reason=result.message
                )
                return
            self.has_proxy_run = True
            self._active_proxy_task = child
            await self._prepare_software_update_once(child)
        try:
            await super().spawn(child)
        finally:
            if isinstance(child, AutoProxyTask):
                self._remember_pending_update()
            self._rollup_image_pairs.extend(getattr(child, "report_image_pairs", ()))

    def build_proxy_report(self) -> TaskResultData:
        """将本次账号完成数量、执行时间和结果摘要整理成托管自动代理报告。"""
        users = list(self.script_info.users.values())
        completed = sum(user.info.status == "完成" for user in users)
        return {
            "title": "自动代理任务报告",
            "script_name": self.script_info.info.name,
            "start_time": self.begin_time,
            "end_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "completed_count": completed,
            "uncompleted_count": len(users) - completed,
            "result": "\n".join(
                f"{user.info.name}: {user.info.result}" for user in users
            ),
        }

    async def notify_maintenance(self):
        """记录全部账号处于维护期的跳过原因，并通过宿主推送维护提示。"""
        await self.script_info.set_log("所选账号均处于游戏维护时段，本轮跳过")
        try:
            await push_maintenance_notice(
                message=self.maintenance_message, task_info=self.task_info
            )
        except Exception as error:
            logger.opt(exception=True).warning(f"推送维护通知失败: {error}")

    async def _prepare_software_update_once(self, task: AutoProxyTask) -> None:
        """首位实际运行账号做更新准备；同批后续账号仅执行本地安全检查。"""
        self._update_config_dir = task.update_config_dir
        if not self._maa_update_checked:
            await run_script_update(
                ScriptUpdateRequest(str(self.script_info.info.script_id), "MAA"),
                self._prepare_software_update,
                task,
            )
            # 普通更新失败且安全回退后也只尝试一次；异常不标记为完成。
            self._maa_update_checked = True
        else:
            await self._check_software_update_safety()

    async def _check_software_update_safety(self) -> None:
        """后续账号只检查本地安装是否安全，避免重复更新请求。"""
        root = self.maa_set_path.parent
        if self._updater_running or await process.is_process_running(
            root / "MAA.Updater.exe"
        ):
            self._updater_running = True
            raise MaaUpdaterRunningError("MAA 官方更新器仍在运行，不能启动后续账号任务")
        if has_incomplete_resource_update(root):
            raise MaaUpdateUnsafeError("MAA 资源更新未完成，不能安全启动后续账号任务")
        if has_delegated_update_failure(root):
            raise MaaUpdateUnsafeError(
                "MAA 官方更新器报告安装失败，不能安全启动后续账号任务"
            )
        if self.script_config.Update.TakeoverEnabled and (
            not (root / "MAA.exe").is_file()
            or (
                (release := read_installed_release(root)) is None
                or parse_version(release[0]) is None
            )
            or read_resource_clock(root) is None
        ):
            raise MaaUpdateUnsafeError(
                "MAA 当前安装或资源状态无法确认，不能安全启动后续账号任务"
            )

    async def _prepare_software_update(self, task: AutoProxyTask) -> bool:
        """启动前尽力更新；普通准备失败时沿用当前安装继续任务。"""
        if not self.script_config.Update.TakeoverEnabled:
            if has_incomplete_resource_update(self.maa_set_path.parent):
                raise MaaUpdateUnsafeError(
                    "MAA 资源更新未完成，请开启更新接管修复后重试"
                )
            return False
        try:
            return await self._prepare_software_update_strict(task)
        except (
            MaaUpdaterRunningError,
            MaaUpdateUnsafeError,
            _utils_fluxdown_cli.FluxdownCancelUnconfirmed,
        ):
            # 更新器仍在写盘或安装结果不明时，不能沿用当前安装启动任务。
            raise
        except Exception as error:
            # 用户主动取消由 CancelledError 向上传播，不当作普通更新失败。
            root = self.maa_set_path.parent
            if self._updater_running or await process.is_process_running(
                root / "MAA.Updater.exe"
            ):
                self._updater_running = True
                raise MaaUpdaterRunningError(
                    "MAA 官方更新器仍在运行，不能在写入期间启动任务"
                ) from error
            installed = read_installed_release(root)
            if (
                not (root / "MAA.exe").is_file()
                or installed is None
                or parse_version(installed[0]) is None
                or read_resource_clock(root) is None
                or has_delegated_update_failure(root)
                or has_incomplete_resource_update(root)
            ):
                raise MaaUpdateUnsafeError(
                    "MAA 当前安装或资源状态无法确认，不能安全沿用旧版运行"
                ) from error
            # 注入账号配置前保留待更新包登记，供结束后恢复。
            self._remember_pending_update()
            message = (
                "MAA 更新未完成，沿用当前本体和资源继续任务；本次托管运行仍禁用 MAA 自身更新。原因: "
                + str(error)
            )
            await self.script_info.set_log(message)
            logger.warning(message)
            # 通知发送失败不阻断沿用当前安装的任务。
            with suppress(Exception):
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(level="warning", message=message),
                )
            return False

    async def _prepare_software_update_strict(self, task: AutoProxyTask) -> bool:
        """更新后重新确认本体及资源版本，由调用方决定失败后的处理。"""
        for _ in range(3):
            if not await self._prepare_updates_once(task):
                return False
            release = read_installed_release(self.maa_set_path.parent)
            clock = read_resource_clock(self.maa_set_path.parent)
            if release is None or clock is None:
                raise RuntimeError("无法确认 MAA 本体或资源版本")
            github = use_maa_github_update(
                self.script_config,
                config_dirs=[task.update_config_dir, self.maa_set_path],
            )
            latest = await query_latest_maa_version(
                release[1], self.script_config.Update.Channel, github=github
            )
            target_clock = await latest_resource_clock(github=github, current=clock)
            enabled, _ = resolve_takeover_credentials(self.script_config)
            if not github and not enabled:
                raise RuntimeError("MAA 更新配置已变更，请重新运行")
            current_version = parse_version(release[0])
            latest_version = parse_version(latest)
            assert current_version is not None and latest_version is not None
            if (
                compare_versions(current_version, latest_version) == 0
                and clock >= target_clock
                and not has_incomplete_resource_update(self.maa_set_path.parent)
            ):
                await self.script_info.set_log("MAA 本体及资源均已是最新版本，开始运行")
                return True
        raise RuntimeError("MAA 更新期间上游版本持续变化，请稍后重新运行")

    async def _prepare_updates_once(self, task: AutoProxyTask) -> bool:
        """运行账号前下载更新，并等待官方安装链结束后才允许注入任务配置。"""
        github = use_maa_github_update(
            self.script_config,
            config_dirs=[task.update_config_dir, self.maa_set_path],
        )
        mirror_enabled, cdk = resolve_takeover_credentials(self.script_config)
        if not github and not mirror_enabled:
            if self.script_config.Update.TakeoverEnabled:
                raise RuntimeError(
                    "无法代理 MAA 原生 CDK 的启动前下载；请在此脚本的更新配置中填写 CDK"
                )
            return False
        # 上次下载后被中止或 MAA 原生下载留下的包先交还官方入口，不能让
        # 账号配置注入清掉它。消费后再查最新版本，不覆盖既有登记。
        pending_version, pending = read_pending_update(self.maa_set_path.parent)
        if pending and (self.maa_set_path.parent / pending).is_file():
            await self._install_pending_software_update(target=pending_version)
        last_log = 0.0

        async def report(downloaded: int, total: int, speed: float) -> None:
            """将更新下载字节和速度换算为任务进度文本，并按时间节流输出日志。"""
            nonlocal last_log
            amount = f"{downloaded / 1024**2:.1f} MB"
            if total > 0:
                amount = f"{downloaded * 100 / total:.1f}% ({amount}/{total / 1024**2:.1f} MB)"
            line = f"MAA 更新下载: {amount}，{speed / 1024**2:.1f} MB/s"
            await self.script_info.set_log(line)
            if time.monotonic() - last_log >= 1 or downloaded == total:
                logger.info(line)
                last_log = time.monotonic()

        if github:
            candidate = getattr(self, "_github_update_candidate", None)
            self._github_update_candidate = None
            try:
                target = await prepare_maa_fluxdown_update(
                    self.maa_set_path.parent,
                    config=self.script_config,
                    config_dir=task.update_config_dir,
                    progress=report,
                    prepared=candidate,
                )
            finally:
                # 候选只交接一次；安装后若又发现新版，下一轮必须重新查询下载。
                if candidate is not None:
                    discard_prepared_update(candidate)
        else:
            target = await prepare_maa_software_before_run(
                self.maa_set_path.parent,
                config=self.script_config,
                config_dir=task.update_config_dir,
            )
        if target is None:
            raise RuntimeError("MAA 更新设置在准备期间发生变化，请重新运行")
        await self._install_pending_software_update(target=target)

        async def resource_progress(line: str) -> None:
            """将资源更新阶段的进度文本同步到当前托管运行节点。"""
            await self.script_info.set_log(line)

        # 本体包可能覆盖 resource，资源必须在官方本体安装完成后再应用。
        await prepare_install_resources(
            self.maa_set_path.parent,
            cdk=cdk,
            github=github,
            progress=resource_progress,
            incremental=self.script_config.Update.PackageMode == "incremental",
        )
        return True

    async def _install_pending_software_update(
        self, *, target: str | None = None
    ) -> None:
        """复用官方安装入口；进程未退出或安装结果不明时阻止启动。"""
        await self.script_info.set_log("正在等待 MAA 官方更新器处理本地更新包")
        try:
            await update_maa(
                self.maa_set_path.parent,
                snapshot_path=self.temp_path,
                script_id=self.script_info.info.script_id,
            )
        except MaaUpdaterRunningError:
            self._updater_running = True
            raise
        except Exception as error:
            raise MaaUpdateUnsafeError(
                "MAA 官方安装过程异常，未确认安装可用，请先完成修复"
            ) from error
        if has_delegated_update_failure(self.maa_set_path.parent):
            raise MaaUpdateUnsafeError(
                "MAA 官方更新器报告安装失败，请先在 MAA 内完成修复"
            )
        if target is not None:
            installed = read_installed_release(self.maa_set_path.parent)
            actual = parse_version(installed[0]) if installed else None
            expected = parse_version(target)
            if not (actual and expected and compare_versions(actual, expected) >= 0):
                raise MaaUpdateUnsafeError(
                    "未确认 MAA 已完成更新，已停止后续账号任务，请先完成更新"
                )

    async def _business_final(self):
        """运行结束后的收尾工作"""
        try:
            if not self.prepared or not self.has_proxy_run:
                for update_task in self._game_update_tasks:
                    await update_task.close_owned_emulator()
            if self.maintenance_only:
                return

            if not self.prepared:
                # prepare() 未走完就结束：备份目录与模拟器实例可能还没建立，没有
                # 可收尾的资源。但若 prepare() 已建立配置锁，必须先释放，
                # 否则该脚本配置的读写与任务启动会一直被拒到进程重启。
                if self.config_lock_acquired:
                    self.config_lock_acquired = False
                # 此时收尾只应回报状态——主动停止不算异常，
                # 而 prepare() 自身的失败则要保留异常
                if not self.stopped_manually:
                    await self.script_info.set_state(status="异常")
                return self.check_result

            if self.check_result != "Pass":
                await self.script_info.set_state(status="异常")
                return self.check_result

            logger.info("MAA 主任务已结束, 开始执行后续操作")
            self.config_lock_acquired = False

            if self.execution_mode in ["AutoProxy"]:
                # 准备期间才开始维护时，未实际代理任何账号，不关闭原有模拟器。
                if self.has_proxy_run:
                    await close_emulator(self)
                await config_manager.flush()

                title = f"{datetime.now().strftime('%m-%d')} | {self.script_info.info.name or '空白'}的{_utils_constants.TASK_MODE_ZH[self.execution_mode]}任务报告"
                result = self.build_proxy_report()

                try:
                    # 汇总带图（MaaFW 同款）：各失败账号的现场画面，多了取最后几张
                    rollup_pairs = self._rollup_image_pairs[-NOTIFY_SCREENSHOT_LIMIT:]
                    if rollup_pairs:
                        result["screenshots"] = screenshot_entries(rollup_pairs)
                    if self.all_users_maintenance_skipped:
                        await self.notify_maintenance()
                    else:
                        await Notify.push_proxy_result(
                            title=title,
                            report=TaskResultReport.from_message(result),
                            task_info=self.task_info,
                            result_template="MAA_result.html",
                            signature_sep=_format_maa.SIGNATURE_SEP,
                            images=[image for _, image in rollup_pairs],
                        )
                except Exception as e:
                    logger.opt(exception=True).warning(f"推送代理结果时出现异常: {e}")
                    await Publisher.send(
                        id=self.task_info.task_id,
                        type=protocol.TASK_NOTICE,
                        data=WSTaskNoticeData(
                            level="error", message=f"推送代理结果时出现异常: {e}"
                        ),
                    )

            await self.script_info.set_state(
                status="跳过" if self.all_users_maintenance_skipped else "完成"
            )
        finally:
            # 配置锁始终由 L2 持有和归还；本层只释放 MAA 安装访问锁。
            self.config_lock_acquired = False

    async def on_crash(self, exc: BaseException):
        """标记托管运行异常，记录错误并向当前任务发布错误提示。"""
        await self.script_info.set_state(status="异常")
        logger.opt(exception=True).warning(f"MAA任务出现异常: {exc}")
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"MAA任务出现异常: {exc}"),
        )

    async def _run_game_update(self, operation):
        """执行既有游戏更新操作，并保证无论执行结果如何都调用其收尾入口。"""
        try:
            await operation.main_task()
        finally:
            await operation.final_task()

    @property
    def stopped_manually(self):
        """判断当前专项或整次任务是否已收到取消，用于区分主动停止与执行失败。"""
        return self.cancelled or self.task_info.info.status == "cancelled"
