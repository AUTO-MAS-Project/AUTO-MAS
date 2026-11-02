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
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from time import time_ns

import app.core.notify.formats.maaend as _format_maaend
import app.core.notify.report as _node_report
from app.config import ConfigCollection, config_manager
from app.core import Config, EmulatorManager, Notify, Publisher
from app.core.notify.task_content import screenshot_entries as screenshot_entries
from app.core.ws import protocol
from app.models.config import MaaEndConfig, MaaEndUserConfig, UserConfigType
from app.models.emulator import DeviceProvider
from app.models.notification.report import TaskResultReport, UserReportText
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, UserItem
from app.services import capture_adb, capture_win32
from app.services import endfield_launcher as _service_endfield_launcher
from app.task.emulator_core import close_emulator
from app.task.manager_base import ScriptManagerBase
from app.task.proxy_helpers import push_dispatch_log
from app.utils import (
    BASE_NATIVE,
    BASE_SHARED,
    BASE_SOURCE_LABELS,
    LOG_TYPE_ERROR,
    TASK_MODE_ZH,
    get_logger,
    log_box,
)
from app.utils import io as _utils_io

from .AutoProxy import AutoProxyTask
from .resource_loader import MaaEndResourceLoader, load_maaend_controller_protocol
from .ScriptConfig import ScriptConfigTask, maaend_config_base
from .tools.backup_archive import archive_native_backup
from .tools.update import ensure_game_updated
from .Update import EndfieldUpdateTask

logger = get_logger("MaaEnd 调度器")

METHOD_BOOK: dict[str, type[AutoProxyTask | ScriptConfigTask]] = {
    "AutoProxy": AutoProxyTask,
    "ScriptConfig": ScriptConfigTask,
}


class MaaEndManager(ScriptManagerBase):
    """MaaEnd 控制器"""

    maintenance_message = "终末地正在维护"

    def maintenance_game(self, user_config: UserConfigType) -> str | None:
        if (
            isinstance(user_config, MaaEndUserConfig)
            and user_config.Info.Resource == "官服"
        ):
            return "endfield"
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
        self.update_gate_failure: str | None = None
        self.controller_protocol = ""
        self.user_config: ConfigCollection[MaaEndUserConfig] | None = None
        self.maaend_config_dir: Path | None = None
        self.temp_path: Path | None = None
        self.had_original_script_config = False
        self.script_config_base = BASE_SHARED
        self._device_provider = device_provider
        self.error_image_start_ns: int | None = None
        self.error_screenshot_paths: list[Path] = []

    async def check(self) -> str:
        # Update 是「检查更新」按钮的一次性任务，不进 METHOD_BOOK——那张表按用户循环。
        if self.task_info.mode not in (*METHOD_BOOK, "Update"):
            return "不支持的任务模式, 请检查任务配置！"

        script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]

        if not isinstance(script_config, MaaEndConfig):
            return "脚本配置类型错误, 不是 MaaEnd 脚本类型"

        root_path = script_config.Info.Path
        if root_path is None or not (root_path / "MaaEnd.exe").exists():
            if self.task_info.mode == "Update":
                # 判「这是不是 PC 控制器」要读 MaaEnd 本体的资源
                return (
                    "确认控制器类型需要读取 MaaEnd 本体，请先在脚本里配好 MaaEnd 路径"
                    "（未找到 MaaEnd.exe），再来检查终末地客户端更新！"
                )
            return "MaaEnd.exe文件不存在, 请检查MaaEnd路径设置！"

        controller_name = str(script_config.Game.ControllerType or "").strip()
        if not controller_name:
            return "未选择 MaaEnd 控制器，请在脚本编辑页选择控制器！"

        try:
            self.controller_protocol = load_maaend_controller_protocol(
                root_path, controller_name
            )
        except (OSError, KeyError, ValueError) as error:
            return f"MaaEnd 控制器配置读取失败: {error}"

        if self.task_info.mode == "Update":
            # 只更新 PC 客户端：不读 mxu-MaaEnd.json，也不起模拟器。
            if self.controller_protocol != "Win32":
                return (
                    "终末地客户端更新仅支持 PC 控制器, 请检查脚本配置中的控制器设置！"
                )
            if not Path(str(script_config.Game.Path or "").strip()).is_file():
                return "未完成游戏配置, 请检查脚本配置中的游戏设置！"
            return "Pass"

        if self.controller_protocol == "Adb" and (
            script_config.Game.EmulatorId == "-"
            or script_config.Game.EmulatorIndex in ["", "-"]
        ):
            return "未完成模拟器配置, 请检查脚本配置中的模拟器设置！"
        elif self.controller_protocol == "Win32" and (
            not script_config.Game.Path or not script_config.Game.Path.exists()
        ):
            return "未完成游戏配置, 请检查脚本配置中的游戏设置！"
        if self.controller_protocol == "Win32" and self.task_info.mode == "AutoProxy":
            loader = MaaEndResourceLoader.get_loaded(Path(script_config.Info.Path))
            launch_mode = loader.resolve_launch_mode(
                script_config.Game.LaunchMode, controller_name
            )
            if launch_mode == "MaaEnd":
                if controller_name not in loader.pretask_controllers("LaunchGamePC"):
                    return "当前 MaaEnd 或控制器不支持「MaaEnd 启动」，请选择启动器启动或 MAS 启动"
                if script_config.Game.LauncherPath:
                    try:
                        _service_endfield_launcher.resolve_launcher_exe(
                            Path(str(script_config.Game.Path)),
                            str(script_config.Game.LauncherPath),
                        )
                    except ValueError as error:
                        return str(error)
            else:
                # MAS 两种启动方式需要有效启动器；原生模式由 MaaEnd 自行定位。
                client_exe = Path(str(script_config.Game.Path or "").strip())
                try:
                    launcher = _service_endfield_launcher.resolve_launcher_exe(
                        client_exe, str(script_config.Game.LauncherPath or "")
                    )
                except ValueError as error:
                    return str(error)
                if launcher is None:
                    return (
                        "未找到终末地官方启动器, 请选择鹰角官方启动器 "
                        "Launcher.exe 或 Games.exe！"
                    )
        if (
            self.task_info.mode == "AutoProxy"
            and not (
                Path(
                    Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].Info.Path
                )
                / "config/mxu-MaaEnd.json"
            ).exists()
        ):
            return "MaaEnd 配置文件不存在, 请检查 MaaEnd 路径设置或先启动 MaaEnd 完成配置文件生成！"

        return "Pass"

    async def prepare(self):

        # 锁定脚本配置并加载用户配置
        self.config_locks[
            Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].uid
        ] = await Config.ScriptConfig[uuid.UUID(self.script_info.script_id)].lock_x()
        self.script_config = Config.ScriptConfig[uuid.UUID(self.script_info.script_id)]

        if self.task_info.mode == "Update":
            # 只写 Game.Path 指向的游戏目录，不碰 MaaEnd 原生配置：不建快照、不归档、
            # 不解析 UserData。锁在这里取得、由 final_task() 释放。
            self.script_info.user_list = [
                UserItem(user_id="Default", name="终末地客户端更新", status="等待")
            ]
            logger.success(f"{self.script_info.script_id}已锁定, 进入手动更新会话")
            return

        if not isinstance(self.script_config, MaaEndConfig):
            raise TypeError("脚本配置类型错误")

        self.user_config = self.script_config.UserData
        logger.success(f"{self.script_info.script_id}已锁定, MAAEnd配置提取完成")

        root_path = self.script_config.Info.Path
        if root_path is None:
            raise ValueError("Path未配置，请检查路径设置")
        self.maaend_config_dir = root_path / "config"
        self.temp_path = Path.cwd() / f"data/{self.script_info.script_id}/Temp"

        # 初始化模拟器管理器
        if self.controller_protocol == "Adb":
            device_provider = (
                self._device_provider or EmulatorManager.get_emulator_instance
            )
            self.emulator_manager = await device_provider(
                str(self.script_config.Game.EmulatorId)
            )
        else:
            self.emulator_manager = None

        # 先处置上次崩溃残留的快照, 再备份原始配置。无条件清空会把崩溃后唯一
        # 一份原始配置副本删掉, 让注入污染的状态固化成「原始配置」。
        self._recover_previous_run()
        if _utils_io.commit_native_config_snapshot(
            self.temp_path,
            self.maaend_config_dir,
            script_id=self.script_info.script_id,
        ):
            self.had_original_script_config = True

        # 任务级一次性归档 MaaEnd 原生配置（项目级池，指纹去重，失败不阻断
        # 任务）：原生配置物理上跨用户共享，只代表「本轮任务动手前」的安装
        # 现场，必须在任何下发前归档这一次
        if self.maaend_config_dir.exists():
            with suppress(Exception):
                archive_native_backup(self.maaend_config_dir)

        # 构建用户列表
        if self.task_info.mode == "ScriptConfig":
            target_user_id = self.task_info.user_id or "Default"
            self.script_info.user_list = [
                UserItem(user_id=target_user_id, name="", status="等待")
            ]
            if target_user_id != "Default":
                self.script_config_base = maaend_config_base(
                    self.user_config[uuid.UUID(target_user_id)].Info.Base
                )
        else:
            self.script_info.user_list = self.build_proxy_user_list(
                self.user_config.items()
            )
        logger.info(
            f"用户列表加载完成, 已筛选用户数: {len(self.script_info.user_list)}"
        )

    async def _restore_script_config_from_temp(self) -> None:
        """恢复任务开始前的 MaaEnd working 配置。"""

        if (
            not self.temp_path
            or not self.temp_path.exists()
            or not self.maaend_config_dir
        ):
            return
        if not self.had_original_script_config:
            _utils_io.force_rmtree(self.maaend_config_dir)
            return

        logger.info(f"复原 MaaEnd 脚本配置文件: {self.temp_path}")
        _utils_io.swap_in_dir(self.temp_path, self.maaend_config_dir)

    def _recover_previous_run(self) -> None:
        """处置上次崩溃残留的原始配置快照。"""

        result = _utils_io.recover_native_config(
            self.temp_path,
            self.maaend_config_dir,
            expected_script_id=self.script_info.script_id,
        )
        if result == "restored":
            logger.info("已恢复上次中断前的 MaaEnd 原始配置")
        elif result == "legacy":
            logger.warning(
                "检测到上次中断残留的 MaaEnd 原生配置快照由旧版本生成, 已改名保留以便手动恢复"
            )
        elif result == "skipped":
            logger.warning(
                "检测到 MaaEnd 原生配置在中断后被改动, 已保留当前配置并丢弃旧快照"
            )

    def _cleanup_script_config_temp(self) -> None:
        if self.temp_path:
            _utils_io.clear_native_config_snapshot(self.temp_path)

    def _keep_script_config_changes(self) -> bool:
        """原生来源配置会话成功时保留 MaaEnd GUI 的写回。"""

        # 配置会话的唯一出口就是用户在配置窗口点「保存配置」发起的中止,
        # 因此这里不能把 stopped_manually 当作丢弃的依据, 否则原生来源模式下
        # MaaEnd GUI 的写回会被随后的配置复原抹掉。
        # viewOnly 查看会话不保留任何现场改动，结束后恢复任务前快照。
        return (
            self.task_info.mode == "ScriptConfig"
            and self.script_config_base == BASE_NATIVE
            and not self.task_info.view_only
            and bool(self.script_info.user_list)
            and self.script_info.user_list[0].status == "完成"
        )

    async def _ensure_game_client_updated(self) -> str | None:
        """任务启动前接管终末地 PC 客户端更新。

        更新对象是脚本级的 `Game.Path`，多用户与重试轮次都只该检查一次，所以要赶在本轮
        游戏被拉起来之前做完——那时才不存在覆盖正被占用文件的竞争。

        跨脚本互斥不在这里做：`add_task` 按脚本粒度挡重复派发，多账号是同一脚本内的
        `UserData`，同一目录不会被两个脚本并发更新。

        `ScriptConfig` 会话只是打开 MaaEnd 的配置界面，不该被关掉正在运行的游戏、
        再多等几 GB 的下载。

        Returns:
            str | None: 需要阻断本轮任务时返回给用户看的说明；``None`` 表示可以继续。
        """

        if self.task_info.mode == "ScriptConfig":
            return None
        script_config = self.script_config
        if not isinstance(script_config, MaaEndConfig):
            return None
        if (
            self.controller_protocol == "Win32"
            and str(script_config.Game.LaunchMode or "").strip() == "Launcher"
        ):
            # 启动器启动：游戏更新由官方启动器界面处理（MAS 只负责点按钮与等待），
            # 跳过 API 直下的更新接管，避免两套更新互相打架
            logger.info(
                "启动方式为「启动器启动」，游戏更新交由启动器处理，跳过更新接管"
            )
            return None
        if not script_config.Game.IfAutoUpdate:
            return None
        if self.controller_protocol != "Win32":
            # 改成模拟器后这个勾选会留着；静默跳过会被当成已生效，留一行可查的说明
            logger.info("终末地客户端更新仅支持 PC 控制器，当前控制器已跳过")
            return None
        game_exe = Path(str(script_config.Game.Path or "").strip())
        if not game_exe.is_file():
            # 路径填错或客户端被移走时留一行可查的说明，别让这道门静默消失
            logger.info(f"未找到终末地客户端，本轮不检查更新: {game_exe}")
            return None

        async def report(line: str) -> None:
            await push_dispatch_log(self.script_info, line)

        try:
            result = await ensure_game_updated(
                game_exe,
                time_limit_minutes=int(script_config.Game.UpdateTimeLimit),
                progress=report,
            )
        except Exception as error:
            # 能走到这里的只剩「已经开始写游戏目录之后」出的岔子：放行等于让脚本
            # 跑在半写入的客户端上，一律阻断。
            logger.opt(exception=True).error(
                f"终末地客户端更新接管异常，中止本轮任务: {error}"
            )
            return f"终末地客户端更新异常（{error}），已中止本轮任务"

        # 结论也要在调度台留一句：拦住本轮的那句之外，「已更新至 x」与「判不了所以放行」
        # 同样得看得见；UpToDate 每轮任务都会出，重复播没人看
        if result.status != "UpToDate":
            await push_dispatch_log(self.script_info, result.message)
        if result.status == "NeedManualUpdate":
            return result.message
        return None

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

        # 通知收图使用未取整的时间，避免带入同一秒内上一轮留下的截图。
        self.error_image_start_ns = time_ns()
        self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await self.prepare()

        if not isinstance(self.script_config, MaaEndConfig):
            raise RuntimeError("脚本配置类型错误, 不是 MaaEnd 脚本类型")

        if self.task_info.mode == "Update":
            # current_index 必须归零：子任务从 user_list[current_index] 取结论落点，
            # 而它的初值是 -1（未开始）。
            self.script_info.current_index = 0
            await self.spawn(EndfieldUpdateTask(self.script_info, self.script_config))
            return

        failure = await self._ensure_game_client_updated()
        if failure is not None:
            # 绝不能改 self.check_result：final_task 在它不是 Pass 时早退并跳过
            # unlock()，而此刻脚本配置已被 prepare() 锁上，写它就是永久泄锁。
            # 用户状态也不动：这些账号一个都没跑，逐个改状态会给每人排一次 OBS 回放，
            # 还把维护窗口里的账号一并报成失败。
            self.update_gate_failure = failure
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="error", message=failure),
            )
            return

        for self.script_info.current_index in range(len(self.script_info.user_list)):
            current_user = self.script_info.user_list[self.script_info.current_index]
            if self.task_info.mode == "AutoProxy":
                if not await self.check_user_before_run(
                    current_user, self.user_config[uuid.UUID(current_user.user_id)]
                ):
                    continue
            if self.task_info.mode != "ScriptConfig":
                current_config = self.user_config[uuid.UUID(current_user.user_id)]
                config_base = maaend_config_base(current_config.Info.Base)
                logger.info(
                    f"用户 {current_user.user_id} 配置来源: "
                    f"{BASE_SOURCE_LABELS.get(config_base, config_base)}"
                )
                if config_base == BASE_NATIVE:
                    await self._restore_script_config_from_temp()

            kwargs: dict = dict(
                script_info=self.script_info,
                script_config=self.script_config,
                user_config=self.user_config,
                emulator_manager=self.emulator_manager,
            )
            if self.task_info.mode == "ScriptConfig":
                # 查看会话（view_only）仅 ScriptConfig 模式支持：只读打开原生 GUI
                kwargs["view_only"] = self.task_info.view_only
            elif self.task_info.mode == "AutoProxy":
                kwargs["capture_adb"] = capture_adb
                kwargs["capture_win32"] = capture_win32
                kwargs["on_error_screenshot"] = self.error_screenshot_paths.append
            task = METHOD_BOOK[self.task_info.mode](**kwargs)
            try:
                await self.run_user_task(current_user, task)
            finally:
                if self.task_info.mode != "ScriptConfig":
                    await self._restore_script_config_from_temp()
            if isinstance(task, AutoProxyTask) and task.update_failed:
                # 安装状态未确认时，同一目录上的后续用户也不能继续执行。
                return

    async def final_task(self):

        try:
            if self.maintenance_only:
                return

            if self.check_result != "Pass":
                self.script_info.status = "异常"
                return

            logger.info("MaaEnd 主任务已结束, 开始执行后续操作")
            if self._keep_script_config_changes():
                logger.info("原生来源配置会话成功，保留 MaaEnd 原生配置")
            else:
                await self._restore_script_config_from_temp()
            self._cleanup_script_config_temp()

            if self.task_info.mode in ["AutoProxy"]:
                # 准备期间才开始维护时，未实际代理任何账号，不关闭原有模拟器。
                if self.has_proxy_run:
                    await close_emulator(
                        self, index=self.script_config.Game.EmulatorIndex
                    )
                await config_manager.flush()

                summary = self.collect_user_results()
                error_count = len(summary.failed)

                title = f"{datetime.now().strftime('%m-%d')} | {self.script_info.name or '空白'}的{TASK_MODE_ZH[self.task_info.mode]}任务报告"
                # 按用户交错组装「用户结果行 + 该用户节点详情」：
                # 开关关闭的用户未启 log_box，push_log 为空，自然只有结果行。
                has_uncompleted = summary.uncompleted_count > 0
                user_result_text = self._render_user_results(
                    has_uncompleted=has_uncompleted
                )
                # 报告正文整块镜像进调度台，未配置推送的用户也能看到节点详情
                if user_result_text:
                    self.script_info.log = (
                        f"{self.script_info.log}\n{user_result_text}"
                        if self.script_info.log
                        else user_result_text
                    )
                error_images = (
                    _format_maaend.collect_recent_error_images(
                        self.script_config.Info.Path,
                        started_at_ns=self.error_image_start_ns,
                        ended_at_ns=time_ns(),
                        diagnostic_paths=self.error_screenshot_paths,
                    )
                    if error_count and self.error_image_start_ns is not None
                    else ()
                )
                result = self.build_proxy_report(result_text=user_result_text)
                if error_images:
                    result["screenshots"] = screenshot_entries(
                        [(image.alt, image) for image in error_images]
                    )

                try:
                    if self.all_users_maintenance_skipped:
                        await self.notify_maintenance()
                    else:
                        await Notify.push_proxy_result(
                            title=title,
                            report=TaskResultReport.from_message(result),
                            task_info=self.task_info,
                            images=error_images,
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

            if (
                self.stopped_manually
                or self.update_gate_failure is not None
                or any(user.status == "异常" for user in self.script_info.user_list)
            ):
                self.script_info.status = "异常"
            elif self.all_users_maintenance_skipped:
                self.script_info.status = "跳过"
            else:
                self.script_info.status = "完成"
        finally:
            script_config = getattr(self, "script_config", None)
            if script_config is not None:
                ticket = self.config_locks.pop(script_config.uid, None)
                if ticket is not None:
                    await script_config.unlock(ticket)

    async def on_crash(self, e: Exception):
        self.script_info.status = "异常"
        logger.opt(exception=True).warning(f"MaaEnd任务出现异常: {e}")
        with suppress(Exception):
            await self._restore_script_config_from_temp()
        self._cleanup_script_config_temp()

        if self.task_info.mode in ("AutoProxy",) and self.user_config:
            with suppress(Exception):
                await config_manager.flush()

        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=f"MaaEnd任务出现异常: {e}"),
        )

    def _render_user_results(self, *, has_uncompleted: bool) -> str:
        """本专项选择报告条目和展示模式，公共服务只负责排版。"""
        _report_rows = []
        for _report_user in self.script_info.user_list:
            _entries = [
                item
                if isinstance(item, log_box.LogEntry)
                else log_box.LogEntry.from_legacy(item)
                for item in _report_user.push_log
                if (item.log_type if isinstance(item, log_box.LogEntry) else item[0])
                != LOG_TYPE_ERROR
                or has_uncompleted
            ]
            _mode = getattr(_report_user, "push_log_mode", "逐条")
            if _mode == "关闭":
                _details = []
            elif _mode == "汇总":
                _details = _node_report.render_aggregate_push_log(_entries)
            else:
                _details = _node_report.render_scatter_push_log(_entries)
            _report_rows.append(
                UserReportText(
                    name=_report_user.name,
                    result=_report_user.result,
                    detail_lines=tuple(_details),
                )
            )
        return _node_report.render_user_result_text(_report_rows)
