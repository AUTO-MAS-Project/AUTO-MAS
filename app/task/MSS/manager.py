#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""MSS 托管的脚本级流程（管理器）。

写法照通用 MFW 的管理器（``MaaFW/embedded_manager``）逐段对应：运行前检查（打开项目、拿 X 锁、筛账号、
运行池自检）→ 运行前更新与运行环境确认 → 逐个账号建 ``account_run.MSSAccountRun`` 直接调 ``main_task`` →
收尾（保存账号配置并解锁、收尾项目、信号通知、代理结果）。差别只在：只认确切类型 ``MSSConfig``；项目会话
的请求经 MSS 自己的属主入口 ``read_managed`` 取记录组装（属主名 ``mss_adapter``）；遥测的上报名是 ``MSS``。

X 锁照旧直接 ``try_lock_x()``，不走 ``lock_script_config``；拿到锁、确认有可运行账号后照通用 MFW 调 L2 挂的
``after_config_lock``（选定游戏会话、复查预下载），账号循环里再按账号选定、跑完交回账号覆盖的目标。
项目会话、运行池路由与自检、归档、遥测、通知正文都调 ``MaaFW/tools/embedded`` 里的叶子；读写配置一律经
``config_view``。账号流程模块经 runner 包 import maa（导入即打开 DLL），只在账号开跑前延迟导入。
"""

from __future__ import annotations

import asyncio
import time
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from app.config import config_manager
from app.core import Notify, Publisher
from app.core.notify.lifecycle import NotificationTaskBase
from app.core.notify.task_content import (
    NOTIFY_SCREENSHOT_LIMIT,
    prepare_screenshot_images,
    screenshot_entries,
)
from app.core.ws import protocol
from app.models.emulator import DeviceBase, DeviceProvider
from app.models.notification.report import TaskResultData, TaskResultReport
from app.models.schema import WSTaskNoticeData
from app.models.task import ScriptItem, UserItem
from app.task.game import current_game_session
from app.task.MaaFW.tools.backup_archive import (
    archive_mas_runtime_backup,
    archive_native_backup,
)
from app.task.MaaFW.tools.core.native.architecture import (
    describe_unsupported_architecture,
)
from app.task.MaaFW.tools.embedded import owners
from app.task.MaaFW.tools.embedded.owners import RecordPatch, write_managed_record
from app.task.MaaFW.tools.embedded.project_session import (
    BENIGN_SKIPS,
    SKIP_OCCUPIED,
    MaaFWProjectDownload,
    MaaFWProjectEvent,
    MaaFWProjectLease,
    MaaFWProjectLog,
    MaaFWProjectNotice,
    MaaFWProjectPoint,
    MaaFWProjectRequest,
    MaaFWProjectSession,
    current_siblings,
    describe_open_failure,
    discover_prefetch,
    project_request_from_record,
)
from app.task.MaaFW.tools.embedded.proxy_quota import proxy_today
from app.task.MaaFW.tools.embedded.run_messages import update_log_lines
from app.task.MaaFW.tools.embedded.run_notices import (
    proxy_result_body,
    signal_summary_title,
    user_results_text,
)
from app.task.MaaFW.tools.embedded.runtime_check import describe_unusable_runtime
from app.task.MaaFW.tools.embedded.runtime_route import resolve_runtime_pool_route
from app.task.MaaFW.tools.embedded.signal_notice import (
    SERVER_MAINTENANCE,
    MaaFWSignalTracker,
    push_signal_notices,
)
from app.task.MaaFW.tools.embedded.telemetry_project import record_project_run
from app.task.MaaFW.tools.embedded.update_credentials import AutoUpdateMode
from app.task.MSS import config_view
from app.task.run_flow import point
from app.utils import TASK_MODE_ZH, get_logger

if TYPE_CHECKING:  # pragma: no cover - 仅供类型检查，运行期不导入 maa
    from app.task.MSS.account_run import MSSAccountRun

# 与通用 MFW 的管理器同名：app.log 的检索习惯不变
logger = get_logger("MFW 内置运行")

# 遥测里的专项上报名（telemetry_project.record_project_run）
_TELEMETRY_SCRIPT_TYPE = "MSS"


def _owner_entry() -> Any:
    """MSS 自己的托管属主入口（``registration``），每次现取。"""

    from app.task.MSS.registration import _resolve_owner

    return _resolve_owner()


def _owner_name() -> str:
    from app.task.MSS.registration import MSS_OWNER

    return MSS_OWNER


class _ManagedRecordMissing(RuntimeError):
    """MSS 属主读不到这个托管（多半是运行中被删了）。"""


def _managed_record(script_id: str) -> owners.ManagedRecord:
    """经 MSS 的属主入口读这个托管的记录（配置原值）。读不到时抛 :class:`_ManagedRecordMissing`。"""

    found = _owner_entry().read_managed(script_id)
    if found.record is None:
        raise _ManagedRecordMissing(f"MSS 属主读不到托管 {script_id}：{found.status}")
    return found.record


class MSSManager(NotificationTaskBase):
    """MSS 托管的脚本级管理器：装配脚本配置、账号配置和模拟器实例，逐个账号交给
    ``MSSAccountRun``。"""

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
        self.check_result: str = "-"
        self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 托管配置与账号配置只当句柄，读写经 config_view
        self.script_config: Any = None
        self.user_config: Any = None
        self.runnable_user_uids: list[uuid.UUID] = []
        self.emulator_manager: DeviceBase | None = None
        self._device_provider = device_provider
        # check() 获取 X 锁，运行及用户收尾直接修改原配置，最后释放。
        self._script_locked = False
        # 当前正在跑的那一位用户的账号任务；每个账号各建一个。
        self.inner_task: "MSSAccountRun | None" = None
        self._inner_finalized = True
        self._report_finalized = False
        # 各账号跑完攒下的失败截图（带账号名称的标签, 内容），最后随「代理结果」发出。
        self._failure_screenshots: list[tuple[str, bytes]] = []
        # 各账号队列里的失效任务，随「代理结果」发出
        self._missing_task_notices: list[str] = []
        self._missing_task_user_ids: set[str] = set()
        # 各账号被原地打转检测 / 单任务时限停下过的任务（只在该账号最后没成功时列）
        self._run_incident_notices: list[str] = []
        # 各账号在「代理结果」里的那一行（账号 id → 结果）
        self._user_report_lines: dict[str, str] = {}
        # 本轮项目信号的账，各账号共用一份
        self.signal_tracker = MaaFWSignalTracker()
        # 项目更新的日志行（已带时间戳）；运行前更新的会并入第一位用户的日志。
        self.project_update_logs: list[str] = []
        self._auto_update_mode: AutoUpdateMode = "Off"
        # 项目会话（打开 / 更新 / 环境确认 / 收尾 / 预下载）：过程输出经 _on_project_event 回来
        self._project = MaaFWProjectSession(
            self._on_project_event,
            members=self._group_members,
            display_name=self._script_display_name,
        )
        # 打开项目成功时的租约（视图路径等），运行前自检用。
        self._project_lease: MaaFWProjectLease | None = None
        # 只有 main_task 正常跑完全部用户才置位；取消/崩溃路径不跑运行后更新。
        self._users_completed = False
        # 运行前检查时视图标记显示还欠一次运行环境确认：main_task 据此在账号任务之前确认。
        self._env_confirm_needed = False
        # 本轮开始时刻：收尾时只清在它之前轮转出来的原生日志备份。
        self._round_started_at = time.time()
        self._view_maintained = False
        # 收尾组同步切了版本、还欠一次运行环境确认：放到代理结果推送之后再做。
        self._post_run_env_confirm = False

    # ------------------------------------------------------------------
    # 运行前检查
    # ------------------------------------------------------------------

    async def check(self) -> str:
        """校验运行的前置条件，返回 ``"Pass"`` 或用户可读的原因（没通过也记一行后端日志）。"""

        # 预取会提前构造管理器；报告与本轮日志清理从真正开始运行前检查时计时。
        self.begin_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._round_started_at = time.time()
        result = await self._check()
        if result != "Pass":
            logger.info(
                f"MFW 内置运行前检查未通过（{self.script_info.name}）：{result}"
            )
        return result

    async def _check(self) -> str:
        if self.execution_mode != "AutoProxy":
            return "MFW 内置运行当前仅支持自动代理模式"

        try:
            script_uid = uuid.UUID(self.script_info.script_id)
        except (ValueError, AttributeError, TypeError):
            return "MFW 托管 ID 无效，请刷新后重试"

        try:
            script_config = config_view.lookup_script(script_uid)
        except (KeyError, ValueError):
            return "MFW 托管配置不存在，请刷新后重试"

        # 按确切类型认（不靠继承）：这个管理器只跑 MSS 托管。
        if not config_view.is_mss_script(script_config):
            return "托管配置类型错误，不是 MFW 托管类型"
        self.script_config = script_config

        # 只支持 x64：不是就在导入、更新、准备运行环境之前说一次，本轮整个脚本不跑。
        unsupported = await asyncio.to_thread(describe_unsupported_architecture)
        if unsupported:
            return unsupported

        script_id = str(self.script_info.script_id)
        # 打开项目：导入期间持有项目预约，拿不到就整脚本良性跳过。
        skipped = await self._project.reserve(script_id)
        if skipped is not None:
            return skipped.reason

        async def prepare_before_lock() -> str | None:
            opened = await self._project.prepare(
                self._project_request(with_siblings=True)
            )
            if opened.record is not None:
                # 视图已变，取消时也先把导入报告写完，再交回项目预约。写回经托管的属主。
                await write_managed_record(
                    script_id,
                    RecordPatch(
                        report=opened.record.report,
                        source_version=opened.record.source_version,
                        imported_at=opened.record.imported_at,
                    ),
                )
            if self._project.stopping:
                return None
            self._env_confirm_needed = opened.env_confirm_needed
            if opened.kind != "opened":
                return opened.reason
            self._project_lease = opened.lease
            # 新账号的默认队列也会在线程里读取视图，继续持预约直到取到 X。
            await config_view.fill_default_snapshots(script_id, script_config)
            return None

        # 用户停止时项目会话等这一整段做完（有限宽限）再交回预约，见 hold()。
        work = asyncio.create_task(prepare_before_lock())
        try:
            if problem := await self._project.hold(work):
                return problem
            # X 票留在管理器任务上下文；取得后才释放项目预约，两者连续交接。
            # 照旧直接 try_lock_x()，不走 lock_script_config。
            ticket = await script_config.try_lock_x()
            if ticket is None:
                return SKIP_OCCUPIED
            self.config_locks[config_view.script_uid(script_config)] = ticket
            self._script_locked = True
        except Exception as exc:  # noqa: BLE001 - OSError 之类也要给用户一句话
            return describe_open_failure(script_id, exc)
        finally:
            await self._project.release()
        assert self._project_lease is not None
        project_root = self._project_lease.view_path
        user_config = config_view.user_collection(script_config)
        self.user_config = user_config

        # 只跑「已启用且剩余天数未耗尽」的用户；单独运行指定了用户时只保留该账号。
        self.runnable_user_uids = [
            uid
            for uid, cfg in config_view.user_items(user_config)
            if config_view.runnable(cfg) and self.task_info.is_target_user(str(uid))
        ]
        if not self.runnable_user_uids:
            return "MFW 没有可运行的账号，请在账号管理页添加并启用至少一个账号"

        # 与旧专项 lock_script_config 同一约定：拿到托管锁后由 L2 选定游戏会话（游戏 /
        # 模拟器）、复查预下载；不调的话整轮读不到绑定的游戏与模拟器。放在项目预约交回
        # 之后（选定可能要等串行游戏），也放在确认有可运行账号之后（没有账号就不先占
        # 游戏、不排队），失败时还锁、照实说原因。
        callback = getattr(self, "after_config_lock", None)
        if callback is not None:
            try:
                await callback(script_config)
            except BaseException as exc:
                from app.utils.common.fluxdown_cli import FluxdownCancelUnconfirmed

                ticket = self.config_locks.pop(
                    config_view.script_uid(script_config), None
                )
                self._script_locked = False
                if ticket is not None:
                    await script_config.unlock(ticket)
                if not isinstance(exc, Exception) or isinstance(
                    exc, FluxdownCancelUnconfirmed
                ):
                    raise
                logger.opt(exception=True).warning(
                    f"MFW 取得托管锁后准备运行失败（{script_id}）：{exc}"
                )
                return str(exc) or type(exc).__name__

        self.emulator_manager = await self._resolve_emulator_manager(script_config)

        # 自检看的是有效根：内嵌脚本的运行池版本钉在副本的投影标记上，不在来源目录。
        environment_problem = await asyncio.to_thread(
            describe_unusable_runtime, project_root
        )
        if environment_problem:
            return environment_problem

        return "Pass"

    async def _resolve_emulator_manager(self, script_config: Any) -> DeviceBase | None:
        """按托管级模拟器配置取实例；未配置时返回 None（ADB 缺模拟器由账号流程报）。"""

        emulator_id = str(config_view.emulator_target(script_config) or "").strip()
        if not emulator_id or emulator_id == "-":
            return None

        from app.core import GameManager

        device_provider = self._device_provider or GameManager.get_emulator_instance
        try:
            return await device_provider(emulator_id)
        except Exception as exc:  # noqa: BLE001 - 缺模拟器不该拦住 Win32 项目
            logger.warning(f"MFW 内置运行取模拟器实例失败，将按无模拟器继续：{exc}")
            return None

    def _build_inner_task(self, route: Any) -> "MSSAccountRun":
        """``route`` 是运行池路由（``resolve_runtime_pool_route``），调用方在工作线程里取。"""

        # 延迟导入：账号流程经 runner 包 import maa，导入即打开 DLL。
        from app.task.MSS.account_run import MSSAccountRun

        assert self.script_config is not None
        assert self.user_config is not None
        task = MSSAccountRun(
            self.script_info,
            self.script_config,
            config_view.user_entries(self.user_config),
            self.emulator_manager,
            # 运行前更新的日志只并入第一位用户；取走后列表清空，后续账号不重复。
            project_update_logs=self._take_project_update_logs(),
            signal_tracker=self.signal_tracker,
        )
        task.history = self.history
        task.callbacks = self.callbacks
        task.maafw_runtime_pool_root = route.root
        task.maafw_runtime_pool_id = route.pool_id
        return task

    # ------------------------------------------------------------------
    # 项目会话
    # ------------------------------------------------------------------

    @staticmethod
    async def check_prefetch(config) -> list:
        """按项目更新模式和凭据发现可用更新，跳过跟随源码的项目并返回发行文件下载需求。"""

        return await discover_prefetch(
            project_request_from_record(
                _managed_record(str(config_view.script_uid(config))),
                owner=_owner_name(),
            )
        )

    def _take_project_update_logs(self) -> list[str]:
        logs, self.project_update_logs = self.project_update_logs, []
        return logs

    def _append_update_log(self, message: str) -> None:
        """记一行更新日志：后端日志 + 脚本实时日志 + 待并入账号日志的缓冲。"""

        logger.info(f"MFW 项目更新：{message}")
        lines = update_log_lines(message, datetime.now().astimezone())
        if lines is None:
            # 详情行只进后端日志，不上界面与账号日志。
            return
        self.project_update_logs.extend(lines)
        self.callbacks.submit(
            self.script_info.set_log("".join(self.project_update_logs))
        )

    def _on_project_event(self, event: MaaFWProjectEvent) -> None:
        """项目会话的事件出口：日志行进项目更新日志，进度点以管理器为 owner 上报，预下载的
        字节进度转给下载观察者。"""

        if isinstance(event, MaaFWProjectLog):
            self._append_update_log(event.message)
        elif isinstance(event, MaaFWProjectPoint):
            point(self, event.stage, state=event.state, key=event.key)
        elif isinstance(event, MaaFWProjectDownload):
            from app.core.downloads import download_observer

            observer = download_observer.get()
            if observer is not None:
                observer(Path("项目更新包"), event.downloaded, event.total, 0.0)

    def _project_request(self, *, with_siblings: bool = False) -> MaaFWProjectRequest:
        """本脚本此刻的项目会话入参：经 MSS 的属主入口现取记录（与通用 MFW 每次现取配置同一时机）。
        ``with_siblings``：带上同来源重建的候选（打开项目要）。"""

        siblings = current_siblings() if with_siblings else ()
        return project_request_from_record(
            _managed_record(str(self.script_info.script_id)),
            owner=_owner_name(),
            script_name=str(self.script_info.name or ""),
            params=self.script_info.info.params,
            round_started_at=self._round_started_at,
            siblings=siblings,
        )

    async def _notify_update(
        self, level: Literal["info", "warning", "error"], message: str
    ) -> None:
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level=level, message=message),
        )

    def _on_finalize_cancel_requested(self) -> None:
        """收尾期间用户点了停止：让运行后更新 / 环境确认按停止处理（项目会话的 stop()）。"""

        self._project.stop()
        if self.inner_task is not None and not self._inner_finalized:
            self.inner_task.stopped_manually = True
            self.inner_task._on_finalize_cancel_requested()

    def _stop_seen(self) -> bool:
        """用户已经要求停止（停在主任务里，或收尾进行中又点了停止）。"""

        return self.stopped_manually or self._project.stop_requested

    def _script_display_name(self, script_id: str) -> str:
        """``latest.by`` / ``switchedBy`` 记的脚本 → 名字（经属主登记现查）。"""

        try:
            config = config_view.lookup_script(uuid.UUID(str(script_id)))
            return str(config_view.script_name(config) or str(script_id)[:8])
        except (KeyError, ValueError, TypeError, AttributeError):
            return "迁移" if str(script_id) == "迁移" else str(script_id)[:8] or "未知"

    async def _post_run_view_maintenance(self) -> None:
        """收尾项目：组同步（只在账号全部正常跑完时做）、写穿巡检、原生日志备份清理。"""

        assert self.script_config is not None
        sync_group = self._users_completed and not self._stop_seen()
        outcome = await self._project.close(
            self._project_request(), sync_group=sync_group
        )
        if sync_group:
            # 切了版本要确认一次运行环境，放到代理结果推送之后由 final_task 做。
            self._post_run_env_confirm = outcome.env_confirm_needed

    def _group_members(self) -> list[Any]:
        """同组候选：属主名下的其它托管（运行中的标 ``busy``，不被中途切换）。"""

        return owners.group_members(exclude=str(self.script_info.script_id))

    async def _run_project_update(self, phase: AutoUpdateMode) -> None:
        """按时机更新项目目录（项目会话做）。任何失败都只记日志 + 通知，不抛出。"""

        assert self.script_config is not None
        notice = await self._project.update(self._project_request(), phase)
        await self._send_project_notice(notice)

    async def _ensure_project_environment(self, phase: AutoUpdateMode) -> None:
        """更新之后确认一次运行环境（项目会话做）。任何失败都只记日志 + 通知，不抛出。"""

        assert self.script_config is not None
        notice = await self._project.confirm_environment(self._project_request(), phase)
        await self._send_project_notice(notice)

    async def _send_project_notice(self, notice: MaaFWProjectNotice | None) -> None:
        if notice is not None:
            await self._notify_update(notice.level, notice.message)

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------

    async def main_task(self) -> None:
        self.check_result = await self.check()
        if self.check_result != "Pass":
            benign = self.check_result in BENIGN_SKIPS
            await self.script_info.set_state(status="跳过" if benign else "异常")
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="warning" if benign else "error", message=self.check_result
                ),
            )
            return

        # AutoProxy 的实际账号列表在这里加载。
        assert self.user_config is not None
        assert self.script_config is not None
        await self.script_info.set_users(
            [
                UserItem(
                    user_id=str(uid),
                    name=config_view.user_name(self.user_config[uid]),
                    status="等待",
                )
                for uid in self.runnable_user_uids
            ]
        )
        await self.script_info.set_state(status="运行")
        logger.info(
            f"MFW 内置运行账号列表加载完成，已筛选账号数: "
            f"{len(self.script_info.user_list)}"
        )

        # 运行前归档项目配置（config/），归档的是有效根；失败不阻断任务。
        try:
            archive_native_backup(
                self.script_info.script_id,
                config_view.project_root(
                    str(self.script_info.script_id), self.script_config
                ),
            )
        except Exception:
            logger.opt(exception=True).warning(
                "MaaFW 运行前项目配置归档失败，已跳过（不阻断任务）"
            )

        # 运行前更新：整个脚本一次，在第一位用户的账号任务建起来之前；更新完接着确认运行环境。
        # 账号全都今日代理次数已满时这一轮谁也不会跑：两步都不做、不联网。
        self._auto_update_mode = config_view.auto_update_mode(self.script_config)
        today = proxy_today()
        if all(
            config_view.proxy_times_used_up(
                self.user_config[uid], self.script_config, today
            )
            for uid in self.runnable_user_uids
        ):
            logger.info(
                f"MFW 本轮账号今日代理次数都已达上限（{self.script_info.name}），"
                "跳过运行前更新与运行环境确认"
            )
        elif self._auto_update_mode == "BeforeRun":
            await self._run_project_update("BeforeRun")
            await self._ensure_project_environment("BeforeRun")
        elif self._env_confirm_needed:
            # 视图挂的版本还没确认过运行环境：在账号任务之前把环境备好。
            await self._ensure_project_environment("BeforeRun")

        await self._record_project_run()

        # main_task / final_task 都是按账号的，因此每个账号各建一个。
        for index in range(len(self.runnable_user_uids)):
            await self.script_info.set_current_index(index)
            user_id = self.runnable_user_uids[index]
            # 物化前归档本账号 MAS 字段侧车（失败只记日志不阻断任务）
            try:
                archive_mas_runtime_backup(
                    self.script_info.script_id,
                    str(user_id),
                    overlay=config_view.overlay_values(self.user_config[user_id]),
                )
            except Exception:
                logger.opt(exception=True).warning(
                    "MaaFW 运行前字段侧车归档失败，已跳过（不阻断任务）"
                )
            # 按账号选定游戏会话，包住该账号的全部尝试与收尾（关游戏、关模拟器都在
            # _finalize_inner_task 里），账号另绑的目标跑完当场交回。
            try:
                try:
                    selected = await self._select_account_game(index, user_id)
                except asyncio.CancelledError:
                    self.stopped_manually = True
                    raise
                if not selected:
                    continue
                route = await asyncio.to_thread(resolve_runtime_pool_route)
                self.inner_task = self._build_inner_task(route)
                self._inner_finalized = False
                try:
                    await self.inner_task.main_task()
                except asyncio.CancelledError:
                    self.stopped_manually = True
                    raise
                # 只截 Exception：CancelledError 属 BaseException，必须继续外抛。
                except Exception as exc:  # noqa: BLE001
                    await self.inner_task.on_crash(exc)
                finally:
                    await self._finalize_inner_task()
                    self._reclaim_unused_update_logs()
            finally:
                session = current_game_session.get()
                if session is not None:
                    await session.release_account()
        self._users_completed = True

    async def _select_account_game(self, index: int, user_id: uuid.UUID) -> bool:
        """按账号选定游戏会话；选定失败时只把这个账号记异常并说明原因，返回 False。

        与旧专项 ``TaskExecuteBase.spawn`` 同一约定：账号绑定为「-」时沿用托管级目标
        （目标没变，``select`` 直接返回）；另绑了目标就换成它的，失败交回会话、继续下一个
        账号。选定之后重取模拟器：账号任务开关模拟器、取 ADB 都要用这次选定的那台，
        留底的实例不能还是托管级或上一个账号的。
        """

        session = current_game_session.get()
        if session is None:
            return True
        assert self.user_config is not None
        assert self.script_config is not None
        owner = self.user_config[user_id]
        if self._account_emulator_without_device(owner):
            # 另绑了模拟器却没选实例：会话只订阅游戏、没有设备，之后设备会回落到托管的，
            # 运行前检查放行、到取 ADB 才报错并把用户指向托管页，这里直接按选定失败处理。
            await session.release()
            await self._fail_account_game(
                index,
                user_id,
                "账号绑定的模拟器未选择实例，请在账号的「账号绑定」里选择设备",
            )
            return False
        try:
            await session.select(owner)
        except Exception as exc:  # noqa: BLE001 - 目标已删、设备失效、绑定被拒
            await session.release()
            await self._fail_account_game(
                index, user_id, str(exc) or type(exc).__name__
            )
            return False
        self.emulator_manager = await self._resolve_emulator_manager(self.script_config)
        return True

    @staticmethod
    def _account_emulator_without_device(owner: Any) -> bool:
        """账号另绑了模拟器目标、设备却是「-」；目标已不存在时不拦，留给 select 报原因。"""

        return config_view.account_emulator_without_device(owner)

    async def _fail_account_game(
        self, index: int, user_id: uuid.UUID, reason: str
    ) -> None:
        """账号游戏目标不可用：只把这个账号记异常、写明原因，其余账号照常运行。"""

        user_item = self.script_info.user_list[index]
        logger.warning(
            f"MFW 账号游戏目标不可用（{self.script_info.name} / {user_item.name}）："
            f"{reason}"
        )
        message = f"账号 {user_item.name} 未运行，游戏目标不可用：{reason}"
        await user_item.set_state(status="异常")
        self._user_report_lines[user_item.user_id] = f"游戏目标不可用：{reason}"
        # 选定中途失败会停在「等待」：其余账号照常运行
        if self.script_info.status == "等待":
            await self.script_info.set_state(status="运行")
        await self.script_info.set_log(message)
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="error", message=message),
        )

    def _reclaim_unused_update_logs(self) -> None:
        """这位用户没进入运行时，运行前更新的日志拿回来交给下一位用户。"""

        inner = self.inner_task
        if inner is None:
            return
        logs = list(getattr(inner, "project_update_logs", None) or [])
        user_item = getattr(inner, "cur_user_item", None)
        if not logs or user_item is None or getattr(user_item, "log_record", None):
            return
        self.project_update_logs = logs + self.project_update_logs

    async def _record_project_run(self) -> None:
        """记一次项目运行（``telemetry_project.record_project_run``）；遥测失败不影响任务。"""

        assert self.script_config is not None
        project_path: Path | None
        try:
            project_path = config_view.project_root(
                str(self.script_info.script_id), self.script_config
            ).resolve()
        except Exception:  # noqa: BLE001 - 遥测失败不影响任务，项目记 other
            project_path = None
        await record_project_run(project_path, script_type=_TELEMETRY_SCRIPT_TYPE)

    async def _finalize_inner_task(self) -> None:
        """收尾当前账号的账号任务；对同一个任务只做一次。"""

        if self.inner_task is None or self._inner_finalized:
            return
        self._inner_finalized = True
        self.inner_task.stopped_manually = self.stopped_manually
        try:
            await self.inner_task._run_final_task()
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(f"MFW 内置运行收尾异常：{exc}")
        finally:
            # 基座会在收尾完成后重新抛出取消；已冻结的用户报告仍须归入脚本报告。
            with suppress(Exception):
                self._failure_screenshots.extend(self.inner_task.report_screenshots())
            with suppress(Exception):
                notice = self.inner_task.missing_task_notice()
                if notice:
                    user_item = self.inner_task.cur_user_item
                    self._missing_task_notices.append(f"{user_item.name}: {notice}")
                    self._missing_task_user_ids.add(user_item.user_id)
            with suppress(Exception):
                line = self.inner_task.proxy_report_line()
                if line is not None:
                    user_item = self.inner_task.cur_user_item
                    self._user_report_lines[user_item.user_id] = line
            with suppress(Exception):
                incidents = self.inner_task.run_incident_notice()
                if incidents:
                    user_item = self.inner_task.cur_user_item
                    self._run_incident_notices.extend(
                        f"{user_item.name}: {line}" for line in incidents.splitlines()
                    )

    async def _commit_user_data(self) -> None:
        """保存已提交的运行状态，并在异常或取消时也释放 X 锁。"""
        if not self._script_locked:
            return
        assert self.script_config is not None
        try:
            await config_manager.flush()
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(f"MFW 账号配置保存失败：{exc}")
        finally:
            ticket = self.config_locks.pop(
                config_view.script_uid(self.script_config), None
            )
            if ticket is not None:
                await self.script_config.unlock(ticket)
            self._script_locked = False

    async def final_task(self) -> None:
        # 正常路径下每个账号跑完就已收尾；这里只兜取消与异常路径的最后一位用户。
        try:
            await self._finalize_inner_task()
        finally:
            # 最后一位用户收尾后保存状态；取消与崩溃路径也从这里释放锁。
            await self._commit_user_data()
        # 手动停止时还没轮到的用户保留「等待」，只有正在跑的那位按中断记「异常」。
        for user in self.script_info.user_list:
            if user.status == "运行" or (
                user.status == "等待" and not self.stopped_manually
            ):
                await user.set_state(status="异常")
        waiting_users = [
            user for user in self.script_info.user_list if user.status == "等待"
        ]

        # 脚本终态必须在这里落定。
        error_users = [
            user for user in self.script_info.user_list if user.status == "异常"
        ]
        completed_users = [
            user for user in self.script_info.user_list if user.status == "完成"
        ]
        # 因停服维护跳过的账号：不算完成，也不算异常
        maintenance_ids = self.signal_tracker.user_ids(SERVER_MAINTENANCE)
        maintenance_users = [
            user
            for user in self.script_info.user_list
            if user.status == "跳过" and user.user_id in maintenance_ids
        ]
        if self.check_result in BENIGN_SKIPS:
            # 项目被暂时占着、整脚本跳过：不是故障。
            await self.script_info.set_state(status="跳过")
        elif self.check_result == "Pass" and not error_users and not waiting_users:
            # 全员因维护跳过时不能显示成「完成」
            await self.script_info.set_state(
                status="跳过" if maintenance_users and not completed_users else "完成"
            )
        else:
            await self.script_info.set_state(status="异常")

        if self.check_result != "Pass":
            return
        # 账号状态已保存、脚本已解锁：收尾项目，只做一次（final_task 可能被取消路径再调）。
        if not self._view_maintained:
            self._view_maintained = True
            try:
                await self._post_run_view_maintenance()
            except Exception as exc:  # noqa: BLE001
                logger.opt(exception=True).warning(f"MFW 收尾维护失败：{exc}")
        if self._report_finalized:
            return
        self._report_finalized = True

        await self._push_signal_notices()

        # 全员都因停服维护跳过：信号通知已经说清楚了，不再发「代理结果」汇总。
        if maintenance_users and len(maintenance_users) == len(
            self.script_info.user_list
        ):
            logger.info(
                f"MFW 本轮账号全部因停服维护跳过（{self.script_info.name}），"
                "只发信号通知，不发代理结果汇总"
            )
        else:
            await self._push_proxy_report(
                error_users=error_users,
                completed_users=completed_users,
                maintenance_users=maintenance_users,
                waiting_users=waiting_users,
            )

        # 收尾组同步可能切到兄弟脚本已经更新的版本，报告发出后补充确认环境。
        if not self._users_completed or self._stop_seen():
            return
        if self._post_run_env_confirm:
            try:
                await self._ensure_project_environment("AfterRun")
            except _ManagedRecordMissing as exc:
                # 收尾在保存账号配置并解锁之后：托管这时被删了，记一行、跳过这一步，不把本轮
                # 结果改成异常（运行阶段读不到照旧抛）。旧路径拿手里的配置对象照常确认。
                logger.warning(f"MFW 收尾时托管已不在，跳过运行环境确认：{exc}")

    async def _push_proxy_report(
        self,
        *,
        error_users: list[UserItem],
        completed_users: list[UserItem],
        maintenance_users: list[UserItem],
        waiting_users: list[UserItem] | None = None,
    ) -> None:
        """推送本轮的「代理结果」汇总。``waiting_users``：手动停止时还没轮到的用户。"""

        # 跑完了但队列里有失效任务的账号：汇总里算未完成
        attention_users = [
            user
            for user in completed_users
            if user.user_id in self._missing_task_user_ids
        ]
        completed_users = [
            user for user in completed_users if user not in attention_users
        ]
        mode_zh = TASK_MODE_ZH[self.execution_mode]
        script_name = self.script_info.name or "空白"
        title = f"{datetime.now().strftime('%m-%d')} | {script_name}的{mode_zh}任务报告"
        end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        results_text = user_results_text(
            [
                (user.user_id, user.name, user.result)
                for user in self.script_info.user_list
            ],
            self._user_report_lines,
            self.script_info.result,
        )
        result = cast(
            TaskResultData,
            proxy_result_body(
                mode_zh=mode_zh,
                script_name=script_name,
                begin_time=self.begin_time,
                end_time=end_time,
                completed=len(completed_users),
                uncompleted=(
                    len(error_users)
                    + len(maintenance_users)
                    + len(attention_users)
                    + len(waiting_users or [])
                ),
                results_text=results_text,
                incident_lines=self._run_incident_notices,
                missing_lines=self._missing_task_notices,
                summary_title=signal_summary_title(
                    title,
                    {record.signal for record in self.signal_tracker.records()},
                    has_error=bool(error_users),
                    has_completed=bool(completed_users),
                ),
            ),
        )
        try:
            images = await prepare_screenshot_images(
                self._failure_screenshots[-NOTIFY_SCREENSHOT_LIMIT:],
                image_id_prefix="maafw",
            )
            result["screenshots"] = screenshot_entries(images)
            await Notify.push_proxy_result(
                title=title,
                report=TaskResultReport.from_message(result),
                task_info=self.task_info,
                images=[image for _, image in images],
                include_system=not self.signal_tracker.records(),
            )
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(f"推送 MFW 代理结果时出现异常: {exc}")
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="error", message=f"推送 MFW 代理结果时出现异常: {exc}"
                ),
            )

    async def _push_signal_notices(self) -> None:
        """本轮撞上的停服维护 / 需要更新客户端，每个「信号 + 资源」发一条通知。"""

        if not self.signal_tracker.records():
            return
        user_config = self.user_config

        def user_config_for(user_id: str) -> Any | None:
            if user_config is None:
                return None
            try:
                return user_config[uuid.UUID(user_id)]
            except (KeyError, ValueError):
                return None

        try:
            await push_signal_notices(
                self.signal_tracker,
                script_name=self.script_info.name or "空白",
                user_config_for=user_config_for,
            )
        except Exception as exc:  # noqa: BLE001
            logger.opt(exception=True).warning(f"推送 MFW 信号通知时出现异常: {exc}")

    async def on_crash(self, e: Exception) -> None:
        logger.exception(f"MFW 内置运行异常：{e}")
        if self.inner_task is not None and not self._inner_finalized:
            await self.inner_task.on_crash(e)
            return
        await self.script_info.set_state(status="异常")


__all__ = ["MSSManager"]
