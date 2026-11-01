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
from pathlib import Path

import app.core.notify.formats.maa as _format_maa
from app.config import config_manager
from app.core import Config, EmulatorManager, Notify, Publisher
from app.core.notify.task_content import (
    NOTIFY_SCREENSHOT_LIMIT as NOTIFY_SCREENSHOT_LIMIT,
)
from app.core.notify.task_content import screenshot_entries as screenshot_entries
from app.core.ws import protocol
from app.models.config import MaaConfig, MaaUserConfig, UserConfigType
from app.models.emulator import DeviceProvider
from app.models.notification import NotificationImage
from app.models.notification.report import TaskResultReport
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, UserItem
from app.services import System, capture_adb
from app.task.emulator_core import close_emulator
from app.task.game_update import EmulatorGameUpdateTask
from app.task.MAA.stage import maa_stage_service
from app.task.manager_base import ScriptManagerBase
from app.task.proxy_helpers import (
    CONFIG_BASE_NATIVE,
    CONFIG_BASE_SHARED,
    read_config_base,
)
from app.utils import constants as _utils_constants
from app.utils import fluxdown_cli as _utils_fluxdown_cli
from app.utils import game_update as _utils_game_update
from app.utils import get_logger
from app.utils import io as _utils_io
from app.utils.common.config import archive as _utils_config_archive

from .AutoProxy import (
    AutoProxyTask,
    depot_cache_snapshot_dir,
    restore_depot_cache,
)
from .constants import ARKNIGHTS_PACKAGE_NAME
from .ScriptConfig import ScriptConfigTask
from .tools import update_maa
from .tools.backup_archive import (
    archive_native_backup,
    collect_native_files,
    native_backup_root,
)
from .tools.fluxdown_update import prepare_maa_fluxdown_update, query_latest_maa_version
from .tools.game_update import ensure_game_updated
from .tools.resource_update import (
    _run_write_thread,
    acquire_resource_access_lock,
    get_resource_write_lock,
    has_incomplete_resource_update,
    latest_resource_clock,
    prepare_install_resources,
    read_resource_clock,
)
from .tools.software_package import (
    clear_deferred_update,
    has_delegated_update_failure,
    load_deferred_update,
    read_pending_update,
    save_deferred_update,
    write_pending_update,
)
from .tools.software_update import (
    cancel_maa_software_update_precheck,
    compare_versions,
    parse_version,
    prepare_maa_software_before_run,
    read_installed_release,
)
from .tools.update_config import restore_maa_update_config
from .tools.update_credentials import (
    resolve_takeover_credentials,
    use_maa_github_update,
)
from .tools.update_errors import MaaUpdateUnsafeError
from .tools.UpdateMAA import MaaUpdaterRunningError

logger = get_logger("MAA 调度器")

METHOD_BOOK: dict[str, type[AutoProxyTask | ScriptConfigTask]] = {
    "AutoProxy": AutoProxyTask,
    "ScriptConfig": ScriptConfigTask,
}


class MaaManager(ScriptManagerBase):
    """MAA控制器"""

    maintenance_message = "明日方舟正在维护"

    def maintenance_game(self, user_config: UserConfigType) -> str | None:
        if isinstance(user_config, MaaUserConfig) and user_config.Info.Server in (
            "Official",
            "Bilibili",
        ):
            return "arknights"
        return None

    wait_for_finalizer_on_cancel = True

    def __init__(
        self,
        script_info: ScriptItem,
        *,
        device_provider: DeviceProvider | None = None,
    ):
        super().__init__()

        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.check_result = "-"
        self.prepared = False
        # 锁是否已建立必须独立于 prepared 记录：配置锁可能先建立，而置位
        # prepared 要等 prepare() 整体返回, 中途被取消或失败时 final_task
        # 靠这个标志解锁（对齐 SRC 的 config_lock_acquired）
        self.config_lock_acquired = False
        self._resource_access: ExitStack = ExitStack()
        self._device_provider = device_provider
        self.game_update_results: dict[str, _utils_game_update.GameUpdateResult] = {}
        self._game_update_tasks: list[EmulatorGameUpdateTask] = []
        self._update_config_dir: Path | None = None
        self._pending_update: tuple[str, str] | None = None
        self._active_proxy_task: AutoProxyTask | None = None
        self._updater_running: bool = False

    async def _finalize_task(self) -> None:
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
                await super()._finalize_task()
            finally:
                try:
                    if self.prepared and not self.maintenance_only:
                        if self._updater_running:
                            self.script_info.status = "异常"
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
                                script_id=self.script_info.script_id,
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
        script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        if not isinstance(script_config, MaaConfig):
            raise TypeError("脚本配置类型错误")
        selected = self.selected_user_configs(script_config.UserData.items())
        if not selected or not script_config.Run.IfCheckGameUpdate:
            return
        # 更新与代理分开执行，但更新期间仍保护设备配置，避免安装到变更后的实例。
        self.config_lock_acquired = True
        try:
            self.config_locks[script_config.uid] = await script_config.lock_s()
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
                await self.spawn(update_task)
                if update_task.result is not None:
                    self.game_update_results[server] = update_task.result
        except Exception as error:
            logger.warning(f"游戏更新准备失败，沿用原代理流程: {error}")
        finally:
            _config_ticket = self.config_locks.pop(script_config.uid, None)
            if _config_ticket is not None:
                await script_config.unlock(_config_ticket)
            self.config_lock_acquired = False

    async def check(self) -> str:
        """校验MAA配置是否可用"""
        if self.task_info.mode not in METHOD_BOOK:
            return "不支持的任务模式，请检查任务配置！"
        if not isinstance(
            Config.ScriptConfig[uuid.UUID(self.script_info.script_id)], MaaConfig
        ):
            return "脚本配置类型错误, 不是MAA脚本类型"
        if Config.ScriptConfig[
            uuid.UUID(self.script_info.script_id)
        ].Emulator.Id == "-" or Config.ScriptConfig[
            uuid.UUID(self.script_info.script_id)
        ].Emulator.Index in ["", "-"]:
            return "未完成模拟器配置, 请检查脚本配置中的模拟器设置！"
        root_path = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].Info.Path
        if root_path is None or not (root_path / "MAA.exe").exists():
            return "MAA.exe文件不存在, 请检查MAA路径设置！"
        if not (root_path / "config/gui.new.json").exists():
            return "MAA配置文件不存在, 请检查MAA路径设置或先启动MAA完成配置文件生成！"
        # 脚本级存档仅在确实有用户选择共享来源时需要；独立来源使用各自的
        # 用户目录，原生来源则直接使用 MAA 安装目录的原生配置。
        if (
            self.task_info.mode != "ScriptConfig"
            and self._has_script_config_user()
            and not (
                Path.cwd() / f"data/{self.script_info.script_id}/Default/ConfigFile"
            ).exists()
        ):
            return "未完成 MAA 全局设置, 请先设置 MAA！"
        return "Pass"

    def _has_script_config_user(self) -> bool:
        """目标用户里是否存在选择脚本级配置来源的用户。

        check() 先于 prepare() 执行，此时 self.user_config 尚未加载、user_list
        还是占位项；直接读脚本配置持久化的 UserData，按参与运行的用户（启用、
        剩余天数非 0、命中目标用户）判定。
        """

        return any(
            read_config_base(config, CONFIG_BASE_SHARED) == CONFIG_BASE_SHARED
            for uid, config in Config.ScriptConfig[
                uuid.UUID(self.script_info.script_id)
            ].UserData.items()
            if self.is_user_selected(uid, config)
        )

    async def prepare(self):
        """运行前准备"""

        # 锁定脚本配置并加载用户配置
        script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]
        # 配置会话不触发下载，启动前取得安装访问锁并持有至子任务结束；
        # 更新器跳过被占用的安装，两侧共用互斥，避免启动 GUI 与写入交错。
        while True:
            install = script_config.Info.Path
            if install is None:
                raise ValueError("Path未配置，请检查路径设置")
            async with get_resource_write_lock(install):
                access = await acquire_resource_access_lock(install)
                if access is not None:
                    self._resource_access.push(access)
                # 等写入期间配置还未锁定，用户可能改了路径，须按当前安装重等。
                if script_config.Info.Path != install:
                    self._resource_access.close()
                    continue
                if await System.is_process_running(install / "MAA.Updater.exe"):
                    raise MaaUpdaterRunningError(
                        "MAA 官方更新器仍在运行，请等待更新结束后重试"
                    )
                if not await System.kill_process(install / "MAA.exe"):
                    raise RuntimeError("无法关闭 MAA，暂不恢复或覆盖原生配置")
                self.config_locks[script_config.uid] = await script_config.lock_x()
                self.config_lock_acquired = True
                break
        self.script_config = script_config
        self.user_config = self.script_config.UserData
        logger.success(f"{self.script_info.script_id}已锁定, MAA配置提取完成")

        root_path = self.script_config.Info.Path
        if root_path is None:
            raise ValueError("Path未配置，请检查路径设置")
        self.maa_set_path = root_path / "config"
        self.temp_path = Path.cwd() / f"data/{self.script_info.script_id}/Temp"

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
        depot_snapshot = depot_cache_snapshot_dir(self.script_info.script_id)
        if depot_snapshot.is_dir():
            logger.info("检测到上次中断的 MAA 库存缓存存底, 先还原安装目录")
            restore_depot_cache(self.maa_set_path.parent, depot_snapshot)

        if _utils_io.commit_native_config_snapshot(
            self.temp_path,
            self.maa_set_path,
            script_id=self.script_info.script_id,
        ):
            self.had_original_script_config = True

        # 任务级一次性归档 MAA 原生配置（项目级池，指纹去重，失败不阻断
        # 任务）：原生配置物理上跨用户共享，只代表「本轮任务动手前」的安装
        # 现场——下发处按用户归档会把上一轮下发的 MAS 配置误当原生内容挤进
        # 保留池，必须在任何下发前归档这一次
        with suppress(Exception):
            archive_native_backup(self.maa_set_path)

        # 构建用户列表
        if self.task_info.mode == "ScriptConfig":
            self.script_info.user_list = [
                UserItem(
                    user_id=self.task_info.user_id or "Default", name="", status="等待"
                )
            ]
        else:
            self.script_info.user_list = self.build_proxy_user_list(
                self.user_config.items()
            )
        logger.info(
            f"用户列表加载完成, 已筛选用户数: {len(self.script_info.user_list)}"
        )

        # 活动关卡信息整个任务只刷新一次, 各用户注入配置时直接用缓存
        if self.task_info.mode == "AutoProxy":
            await maa_stage_service.get_stage(refresh=True)

    def _recover_previous_run(self) -> None:
        """处置上次崩溃残留的原始配置快照。"""

        # 指纹不匹配会保护现场并清理 Temp；先入原安装的备份池，保留原始内容。
        # 上次归档若失败，本次也必须归档成功后才允许清理，不能只记录告警继续。
        if (
            _utils_io.read_native_config_snapshot(
                self.temp_path, expected_script_id=self.script_info.script_id
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
            script_id=self.script_info.script_id,
        )
        result = _utils_io.recover_native_config(
            self.temp_path,
            self.maa_set_path,
            expected_script_id=self.script_info.script_id,
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
        用户刚在原生 GUI 里改的配置抹回会话前状态。脚本级（Default）与独立
        来源会话不豁免——它们的 GUI 改动已由 ``set_maa`` 收尾回写 MAS 目
        录，安装目录现场仍按任务前快照还原。viewOnly 查看会话不保留任何现
        场改动，结束后也还原任务前快照。
        """

        if self.task_info.mode != "ScriptConfig" or self.task_info.view_only:
            return False
        if not (
            self.script_info.user_list
            and self.script_info.user_list[0].status == "完成"
        ):
            return False
        user_id = self.script_info.user_list[0].user_id
        if user_id == "Default":
            return False
        try:
            base = read_config_base(
                self.user_config[uuid.UUID(user_id)], CONFIG_BASE_SHARED
            )
        except (KeyError, ValueError, TypeError):
            return False
        return base == CONFIG_BASE_NATIVE

    async def main_task(self):

        self.check_result = await self.check()
        if self.check_result != "Pass":
            logger.warning(f"未通过配置检查: {self.check_result}")
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=self.check_result),
            )
            return

        self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # 各用户失败画面（标签+图片）按序累积，供汇总「代理结果」带图
        self._rollup_image_pairs: list[tuple[str, NotificationImage]] = []
        await self.prepare()
        # prepare() 内每次 await 都可能被中止。只有它整体返回后，收尾依赖的
        # 配置锁、备份目录与模拟器实例才确实建立，此时才允许 final_task 收尾
        self.prepared = True

        if not isinstance(self.script_config, MaaConfig):
            raise RuntimeError("脚本配置类型错误, 不是MAA脚本类型")

        for self.script_info.current_index in range(len(self.script_info.user_list)):
            if self.task_info.mode == "AutoProxy":
                current_user = self.script_info.user_list[
                    self.script_info.current_index
                ]
                current_config = self.user_config[uuid.UUID(current_user.user_id)]
                update_result = self.game_update_results.get(current_config.Info.Server)
                if not await self.check_user_before_run(
                    current_user, current_config, game_update_result=update_result
                ):
                    continue
                # 单独运行是用户主动指定的一次性运行；上限为 0 时不限次数。
                curdate = _utils_constants.game_now(
                    current_config.Info.Server
                ).strftime("%Y-%m-%d")
                if current_config.Data.LastProxyDate.strftime("%Y-%m-%d") != curdate:
                    current_config.Data.LastProxyDate = _utils_constants.game_now(
                        current_config.Info.Server
                    )
                    await current_config.commit()
                    current_config.Data.ProxyTimes = 0
                    await current_config.commit()
                limit = self.script_config.Run.ProxyTimesLimit
                if (
                    self.task_info.is_queue_task
                    and limit != 0
                    and (current_config.Data.ProxyTimes >= limit)
                ):
                    await self.skip_user(
                        current_user, "今日代理次数已达上限, 跳过该用户"
                    )
                    continue
            kwargs: dict = dict(
                script_info=self.script_info,
                script_config=self.script_config,
                user_config=self.user_config,
                emulator_manager=self.emulator_manager,
            )
            if self.task_info.mode == "ScriptConfig":
                # 查看会话（view_only）仅 ScriptConfig 模式支持：只读打开原生 GUI
                kwargs["view_only"] = self.task_info.view_only
            else:
                kwargs["game_update_result"] = update_result
                kwargs["capture_adb"] = capture_adb
            task = METHOD_BOOK[self.task_info.mode](**kwargs)
            if isinstance(task, AutoProxyTask):
                self._active_proxy_task = task
                # 启动前尽力更新；失败沿用当前安装时，运行期间仍暂停原生更新。
                self._update_config_dir = task.update_config_dir
                await self._prepare_software_update(task)
            await self.run_user_task(
                self.script_info.user_list[self.script_info.current_index], task
            )
            if isinstance(task, AutoProxyTask):
                self._remember_pending_update()
            # AutoProxyTask 失败时在关模拟器前存有现场画面；ScriptConfig 会话没有
            if getattr(task, "report_image_pairs", None):
                self._rollup_image_pairs.extend(task.report_image_pairs)

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
            if self._updater_running or await System.is_process_running(
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
            self.script_info.log = message
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
            if (
                compare_versions(parse_version(release[0]), parse_version(latest)) == 0
                and clock >= target_clock
                and not has_incomplete_resource_update(self.maa_set_path.parent)
            ):
                self.script_info.log = "MAA 本体及资源均已是最新版本，开始运行"
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
            nonlocal last_log
            amount = f"{downloaded / 1024**2:.1f} MB"
            if total > 0:
                amount = f"{downloaded * 100 / total:.1f}% ({amount}/{total / 1024**2:.1f} MB)"
            line = f"MAA 更新下载: {amount}，{speed / 1024**2:.1f} MB/s"
            self.script_info.log = line
            if time.monotonic() - last_log >= 1 or downloaded == total:
                logger.info(line)
                last_log = time.monotonic()

        if github:
            target = await prepare_maa_fluxdown_update(
                self.maa_set_path.parent,
                config=self.script_config,
                config_dir=task.update_config_dir,
                progress=report,
            )
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
            self.script_info.log = line

        # 本体包可能覆盖 resource，资源必须在官方本体安装完成后再应用。
        await prepare_install_resources(
            self.maa_set_path.parent,
            cdk=cdk,
            github=github,
            progress=resource_progress,
        )
        return True

    async def _install_pending_software_update(
        self, *, target: str | None = None
    ) -> None:
        """复用官方安装入口；进程未退出或安装结果不明时阻止启动。"""
        self.script_info.log = "正在等待 MAA 官方更新器处理本地更新包"
        try:
            await update_maa(
                self.maa_set_path.parent,
                snapshot_path=self.temp_path,
                script_id=self.script_info.script_id,
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

    async def final_task(self):
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
                    self.script_info.status = "异常"
                return self.check_result

            if self.check_result != "Pass":
                self.script_info.status = "异常"
                return self.check_result

            logger.info("MAA 主任务已结束, 开始执行后续操作")
            self.config_lock_acquired = False

            if self.task_info.mode in ["AutoProxy"]:
                # 准备期间才开始维护时，未实际代理任何账号，不关闭原有模拟器。
                if self.has_proxy_run:
                    await close_emulator(self)
                await config_manager.flush()

                title = f"{datetime.now().strftime('%m-%d')} | {self.script_info.name or '空白'}的{_utils_constants.TASK_MODE_ZH[self.task_info.mode]}任务报告"
                result = self.build_proxy_report()

                try:
                    # 汇总带图（MaaFW 同款）：各失败用户的现场画面，多了取最后几张
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

            self.script_info.status = (
                "跳过" if self.all_users_maintenance_skipped else "完成"
            )
        finally:
            script_config = getattr(self, "script_config", None)
            if script_config is not None:
                ticket = self.config_locks.pop(script_config.uid, None)
                if ticket is not None:
                    await script_config.unlock(ticket)

    async def on_crash(self, e: Exception):

        self.script_info.status = "异常"
        logger.opt(exception=True).warning(f"MAA任务出现异常: {e}")
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"MAA任务出现异常: {e}"),
        )
