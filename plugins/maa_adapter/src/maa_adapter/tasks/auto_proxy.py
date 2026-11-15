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
import json
import re
import shutil
import time
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import cast

from auto_mas_core import AutoProxyWorker, TaskMode
from auto_mas_core.host.core import Config, Notify, Publisher
from auto_mas_core.host.core_history import aggregate_data
from auto_mas_core.host.core_notify_task_content import (
    prepare_screenshot_images as prepare_screenshot_images,
)
from auto_mas_core.host.core_notify_task_content import (
    screenshot_entries as screenshot_entries,
)
from auto_mas_core.host.core_ws import protocol
from auto_mas_core.host.models_emulator import DeviceInfo
from auto_mas_core.host.models_notification import LocalNotice, NotificationImage
from auto_mas_core.host.models_schema import (
    HistoryAggregationItem,
    HistoryAttachmentInput,
    HistoryCounterStatistic,
    HistorySnapshotStatistic,
    HistoryStatistic,
    HistoryWrite,
    WSTaskNoticeData,
)
from auto_mas_core.host.models_task import LogRecord
from auto_mas_core.host.task_emulator_core import (
    close_emulator,
    mod_avd_open_kwargs,
    resolve_device_ref,
    resolve_host_adb,
    script_process_env,
)
from auto_mas_core.host.task_failure_capture_core import FailureCapture
from auto_mas_core.host.task_proxy_helpers import (
    CONFIG_BASE_INDEPENDENT,
    CONFIG_BASE_NATIVE,
    CONFIG_BASE_SHARED,
    resolve_config_base,
)
from auto_mas_core.host.utils import LogMonitor, ProcessManager, get_logger, process
from auto_mas_core.host.utils import constants as _utils_constants
from auto_mas_core.host.utils import emulator2 as _utils_emulator2
from auto_mas_core.host.utils import io as _utils_io

from maa_adapter import notifications as _format_maa
from maa_adapter import stages as stage_service
from maa_adapter.config.plan import MaaPlanConfig
from maa_adapter.constants import (
    _MAA_CULTIVATE_TASK_NAME,
    ARKNIGHTS_PACKAGE_NAME,
    MAA_MODE_TIME_LIMIT_BOOK,
    MAA_RUN_MOOD_BOOK,
    MAA_STAGE_KEY,
    MAA_TASKS,
    MAA_TASKS_ZH,
    game_now,
)
from maa_adapter.cultivate import (
    CultivatePlan,
    OperatorTarget,
    ProviderContext,
    YituliuDataError,
    append_owned_cultivate_targets,
    apply_achievements,
    depot_cultivate_service,
    filter_observed_cultivate_targets,
    get_certifying_chain,
    get_progression_chain,
    judge_achievements,
    load_oper_box_names,
    parse_cultivate_targets,
    parse_depot_payload,
    resolve_progression,
    summarize_achievements,
    takeover_notice_patch_value,
)
from maa_adapter.cultivate import editor as maa_api
from maa_adapter.cultivate.task_builder import (
    _MAA_AUTO_CULTIVATE_TASK_NAME,
    _MAA_DATA_UPDATE_TASK_NAME,
    _MAA_DEPOT_CHAIN_COMPLETION_MARKERS,
    _MAA_OPER_BOX_CHAIN_COMPLETION_MARKERS,
    _apply_depot_quota_override,
    _build_auto_cultivate_task,
    _build_cultivate_task,
    _build_data_update_task,
    _build_depot_maintain_task,
    _build_event_depot_maintain_task,
    _build_stock_cultivate_task,
    _merge_cultivate_target_updates,
)
from maa_adapter.logs import statistics as log_statistics
from maa_adapter.logs.parsing import (
    _MAA_SANITY_TASK_NAMES,
    _failed_maa_sanity_tasks,
    _failed_maa_task_names,
    _has_completed_annihilation_week,
    _has_completed_sanity_task,
    _has_maa_task_failure,
    _parse_annihilation_weekly_progress,
    _should_retry_maa,
)
from maa_adapter.logs.screenshot import capture_current_image, collect_maa_failure_image
from maa_adapter.native.avd import (
    build_maa_connect_settings,
    ensure_mumu_shim,
    screencap_fallback_status,
)
from maa_adapter.native.backup import (
    archive_mas_runtime_backup,
    read_overlay_values,
    task_type_of,
)
from maa_adapter.native.bilibili import agree_bilibili
from maa_adapter.native.config import (
    infrast_plan_mode,
    load_infrast_plans,
    maa_scheme_name,
)
from maa_adapter.native.depot_cache import (
    depot_cache_snapshot_dir,
    restore_depot_cache,
    snapshot_depot_cache,
)
from maa_adapter.native.guide import MAA_GUIDE_SKIP_VALUES
from maa_adapter.native.presets import (
    MAA_STAMINA_LEGACY_FILENAME,
    ensure_maa_default_configuration,
    get_maa_base_preset,
    seed_maa_base_config,
)
from maa_adapter.native.runtime_config import (
    _MAA_CLIENT_TYPE_TO_INT,
    _MAA_CONFIG_FILES,
    _MAA_DEPOT_ARCHIVE_NAME,
    _MAA_DEPOT_QUOTA_KEYS,
    _MAA_OPER_BOX_ARCHIVE_NAME,
    _MAA_OUT_OF_MEMORY_MARKER,
    _MAA_STALL_NOTICE_MARKERS,
    _MAA_TASK_KEYS_NOT_MERGED,
    _find_task_source,
    _merge_fight_task,
    _merge_maa_config_file,
    _repair_maa_task_queue,
    _without_maa_update_changes,
    read_maa_config_with_fallback,
)
from maa_adapter.native.task_templates import (
    MAA_ANNIHILATION_FIGHT_BASE,
    MAA_GREEN_TICKET_STORE_TASK,
    MAA_TASK_TRANSITION_METHOD_BOOK,
)
from maa_adapter.stages.activity import _maa_activity_state
from maa_adapter.tasks.context import MaaWorkerContext
from maa_adapter.tasks.policy import (
    _current_month_marker,
    _current_week_marker,
    _should_run_annihilation,
)
from maa_adapter.updates.software.package import (
    read_pending_update,
    save_deferred_update,
)
from maa_adapter.updates.software.service import (
    compare_versions,
    parse_version,
    read_installed_release,
)

logger = get_logger("MAA")


class AutoProxyTask(MaaWorkerContext, AutoProxyWorker):
    """自动代理模式"""

    # 养成采集状态：prepare() 每轮重置；类级默认保证未跑 prepare 的
    # 实例（如单测直接构造）调用 check_log 时不炸
    _cultivate_collected_depot: bool = False
    _cultivate_collected_oper_box: bool = False
    _cultivate_auto_raise_injected: bool = False
    # 每轮重新判断来源参与条件；数据不可用或触发跳过时同时暂停自动培养。
    _cultivate_round_paused: bool = True
    _cultivate_execution_targets: tuple[OperatorTarget, ...] = ()
    _cultivate_progress_synced: bool = False
    # 完成活动阶段后，其他任务重试不能重新领取该阶段药石额度。
    _event_depot_completed: bool = False
    # 普通库存重试时仍下发目标，已执行过的阶段不再领取药石额度。
    _stock_depot_completed: bool = False

    mode = TaskMode.AUTO_PROXY

    def __init__(self, expander, user, config):
        """绑定托管、账号、模拟器与历史能力，初始化自动代理的失败截图及养成记录状态。"""
        super().__init__(expander, user, config)
        from auto_mas_core.host.services import capture_adb

        self.script_config = expander.script_config
        self.accounts = expander.script_config.users
        self.emulator_manager = expander.emulator_manager
        self.capture_adb = capture_adb
        self.history = expander.history
        self.game_update_result = expander.game_update_results.get(config.Info.Server)
        self._failure_capture = FailureCapture(stopped=lambda: self.stopped_manually)
        self.cur_user_item = self.user_info
        self.cur_user_uid = uuid.UUID(self.user_info.info.user_id)
        self.cur_user_config = config
        # base 来源三态与独立的覆写常规配置开关：来源决定是否下发 MAS 托管配置，
        # 覆写常规配置决定是否把面板值写进 MAA 原生配置（两段互不替代）。
        self.config_base, self.native_base = resolve_config_base(
            self.cur_user_config, CONFIG_BASE_SHARED
        )
        self.check_result = "-"
        self.maa_root_path: Path | None = None
        self.pending_update: tuple[str, str] | None = None
        self._annihilation_weekly_completion_recorded = False
        self._failed_sanity_tasks: set[str] = set()
        self._failed_extra_tasks: set[str] = set()
        self._non_sanity_retry = False
        # 无时段排班表本轮注入的班次：同一账号的多次重试都注入这一个值，
        # 基建换班完成后只把账号配置里的指针推进一次
        self._infrast_plan_index: int | None = None
        self._infrast_plan_count = 0
        self._infrast_plan_advanced = False
        self._cultivate_archive_positions: dict[str, int] = {}
        self._cultivate_archive_versions: dict[str, tuple[int, int, int]] = {}

    async def check(self) -> str | None:
        """执行账号运行前检查，将专项检查结果转换为 L4 约定的空值或失败原因。"""
        self.check_result = await self._business_check()
        return None if self.check_result == "Pass" else self.check_result

    async def _business_check(self) -> str:
        """检查当前账号选定的配置来源是否已有可用 MAA 配置文件，缺失时标记异常并返回原因。"""
        if (
            self.config_base == CONFIG_BASE_INDEPENDENT
            and not (
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile"
            ).exists()
        ):
            await self.cur_user_item.set_state(status="异常")
            return "未找到账号的 MAA 配置文件，请先在账号配置页完成 「MAA配置」 步骤"
        return "Pass"

    async def prepare(self):
        """准备进程管理、日志观察、账号执行状态和 MAA 运行路径，装配本次自动代理所需上下文。"""
        self.maa_process_manager = ProcessManager()
        # 本轮打开的模拟器信息；收尾补截失败画面时取 adb 地址用
        self.emulator_info: DeviceInfo | None = None
        # 失败尝试在关模拟器前补截的现场画面；收尾组装通知时消费
        self._failure_shot: Path | None = None
        # 本账号的失败画面资源（标签+图片），manager 汇总「代理结果」时收集
        self.report_image_pairs: list[tuple[str, NotificationImage]] = []
        self.maa_log_monitor = LogMonitor(
            (1, 20),
            "%Y-%m-%d %H:%M:%S",
            self.queue_log,
            except_logs=list(_MAA_STALL_NOTICE_MARKERS),
        )
        self.wait_event = asyncio.Event()
        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now().astimezone()
        self.if_game_hot_update = False
        self.pending_res_version = ""
        # 更新阶段只提供资源版本信号；资源热更新仍由 MAA 原生开始唤醒执行。
        if (
            self.game_update_result is not None
            and self.game_update_result.resource_version
        ):
            self.pending_res_version = self.game_update_result.resource_version
            self.if_game_hot_update = (
                self.pending_res_version != self.cur_user_config.Data.LastResVersion
            )
        self._maa_config_baseline: dict[str, dict] | None = None
        # 养成采集：本轮是否采到过识别数据（每类以最后一次标记为准覆盖档案，
        # 见 _collect_cultivate_archive）；
        # 达成文案供 final_task 的统计信息报告，按 (干员, 档位) 去重累积
        self._cultivate_collected_depot = False
        self._cultivate_collected_oper_box = False
        self._cultivate_auto_raise_injected = False
        self._cultivate_round_paused = True
        self._cultivate_progress_synced = False
        self._cultivate_achievement_summary: list[str] = []
        # 已提示过的「找不到原生任务」：重试轮每次都重新合成队列，同一条只提示一次
        self._missing_task_source_warned: set[str] = set()

        maa_root_path = self.script_config.Info.Path
        if maa_root_path is None:
            raise ValueError("Path未配置，请检查路径设置")
        self.maa_root_path = maa_root_path
        self.maa_set_path = maa_root_path / "config"
        self.maa_log_path = maa_root_path / "debug/gui.log"
        self.maa_exe_path = maa_root_path / "MAA.exe"
        self.maa_tasks_path = maa_root_path / "resource/tasks/tasks.json"

        quick_config = self.cur_user_config.Info.IfQuickConfig
        self.run_book = {
            "GreenTicketStore": not quick_config
            or not self.cur_user_config.Task.IfGreenTicketStore,
            "Annihilation": not quick_config
            or self.cur_user_config.Task.Annihilation == "Close",
            "Routine": False,
        }

        if not self.run_book["GreenTicketStore"]:
            completed_at = self.cur_user_config.Data.GreenTicketStoreMonth

            if completed_at is not None and _current_month_marker(
                completed_at
            ) == _current_month_marker(datetime.now(tz=_utils_constants.UTC4)):
                self.run_book["GreenTicketStore"] = True
                logger.info(
                    f"账号 {self.cur_user_item.name} 本次跳过绿票商店："
                    f"本月记录={completed_at}"
                )

        if not self.run_book["Annihilation"]:
            now = game_now(self.cur_user_config.Info.Server)
            start_weekday = self.cur_user_config.Task.AnnihilationStartWeekday

            if not _should_run_annihilation(
                start_weekday, self.cur_user_config.Data.AnnihilationCompletedWeek, now
            ):
                self.run_book["Annihilation"] = True
                logger.info(
                    f"账号 {self.cur_user_item.name} 本次跳过剿灭：开始日={start_weekday}，本周记录={self.cur_user_config.Data.AnnihilationCompletedWeek}"
                )

    def _resolve_log_file_path(self) -> Path:
        """返回本次自动代理观察的 MAA 日志文件路径。"""
        return self.maa_log_path

    async def _business_main(self):
        """自动代理模式主逻辑"""

        logger.info(f"开始代理账号: {self.cur_user_uid}")
        await self.cur_user_item.set_state(status="运行")

        # 任务前脚本每账号一次，先于全部重试；后置脚本由收尾阶段成对执行
        await self.run_user_scripts_before(self.cur_user_config)

        # 执行绿票商店 + 剿灭 + 日常
        # 绿票商店的任务链只认主界面、跑完也停在商店页，放在最前面由后续模式的开始唤醒收拾界面
        for self.phase in ["GreenTicketStore", "Annihilation", "Routine"]:
            if self.run_book[self.phase]:
                continue

            self._event_depot_completed = False
            self._stock_depot_completed = False
            self._failed_sanity_tasks.clear()
            self._failed_extra_tasks.clear()
            self._non_sanity_retry = False
            await self.cur_user_item.set_state(
                status=f"运行 - {MAA_RUN_MOOD_BOOK[self.phase]}"
            )

            if not self.cur_user_config.Info.IfQuickConfig:
                # 来源队列整体交给 MAA 执行，不从隐藏面板推导任务或拆分阶段。
                self.task_dict = {}
            elif self.phase == "Routine":
                self.task_dict = {
                    task: getattr(self.cur_user_config.Task, f"If{task}")
                    for task in MAA_TASKS
                }
            elif self.phase == "Annihilation":
                self.task_dict = {
                    task: bool(task in ("StartUp", "Fight")) for task in MAA_TASKS
                }
            else:  # GreenTicketStore
                self.task_dict = {task: task == "StartUp" for task in MAA_TASKS}

            logger.info(
                f"账号 {self.cur_user_item.name} - 模式: {self.phase} - 任务列表: {list(self.task_dict.values())}"
            )

            for i in range(self.script_config.Run.RunTimesLimit):
                if self.run_book[self.phase]:
                    break
                if i:
                    # 仅同一模式的真实失败重登触发；正常切号继续沿用首次
                    # 成功时刻。必须先确认预下载停写，才能再次启动模拟器。
                    from auto_mas_core.host.core_script_update_queue import (
                        report_script_task_retrying,
                    )

                    await report_script_task_retrying()
                logger.info(
                    f"账号 {self.cur_user_item.name} - 模式: {self.phase} - 尝试次数: {i + 1}/{self.script_config.Run.RunTimesLimit}"
                )
                self.log_start_time = datetime.now().astimezone()
                self._cultivate_archive_positions.clear()
                self._cultivate_archive_versions.clear()
                # 当前来源是账号记录；登记时提交启动提示，使其覆盖整个模拟器启动等待。
                self.cur_user_log = LogRecord(content=["正在启动模拟器\n"])
                self.cur_user_log = await self.add_log(
                    self.log_start_time, self.cur_user_log
                )

                try:
                    emulator_info = await self.emulator_manager.open(
                        self.script_config.Emulator.Index,
                        ARKNIGHTS_PACKAGE_NAME[self.cur_user_config.Info.Server],
                        **mod_avd_open_kwargs(self.emulator_manager, allowed=True),
                    )
                    self.emulator_info = emulator_info
                except Exception as e:
                    logger.opt(exception=True).warning(
                        f"账号: {self.cur_user_uid} - 模拟器启动失败: {e}"
                    )
                    await Publisher.send(
                        id=self.task_info.task_id,
                        type=protocol.TASK_NOTICE,
                        data=WSTaskNoticeData(
                            level="error",
                            message=f"启动模拟器时出现异常: {e}",
                        ),
                    )
                    await self.cur_user_log.set_state(
                        content=["模拟器启动失败, MAA 未实际运行, 无日志记录"]
                    )
                    await self.cur_user_log.set_state(status="模拟器启动失败")

                    await close_emulator(self)

                    await Notify.send_notice(
                        LocalNotice(
                            title="账号自动代理出现异常！",
                            message=f"账号 {self.cur_user_item.name} 的{MAA_RUN_MOOD_BOOK[self.phase]}部分出现一次异常",
                            ticker=f"{self.cur_user_item.name}的{MAA_RUN_MOOD_BOOK[self.phase]}出现异常",
                            duration_seconds=3,
                        )
                    )
                    continue

                logger.info(
                    f"模拟器启动完成: 账号 {self.cur_user_uid} - 模式 {self.phase} - 实例 {self.script_config.Emulator.Index} - ADB {emulator_info.adb_address}"
                )

                if Config.setting.Function.IfSilence:
                    try:
                        await self.emulator_manager.setVisible(
                            self.script_config.Emulator.Index, False
                        )
                    except Exception as e:
                        logger.opt(exception=True).warning(f"模拟器隐藏失败: {e}")

                await self.set_maa(emulator_info)

                # 本轮 MAA 的日志从启动前的文件末尾开始读：gui.log 追加写且跨
                # 运行保留，历史内容里带完成/失败标志的旧行（时间戳闸门分辨不出
                # 它们的「未来」时间戳）会被整段当成本轮日志，MAA 刚启动就被判
                # 失败，随后反复重启模拟器（#19）。
                log_offset = (
                    self.maa_log_path.stat().st_size
                    if self.maa_log_path.is_file()
                    else 0
                )
                logger.info(f"启动MAA进程: {self.maa_exe_path}")
                self.wait_event.clear()
                await self.maa_process_manager.open_process(
                    self.maa_exe_path, env=await self._maa_process_env()
                )
                # 启动提示保持至 MAA 进程创建完成，再清空并由本次 MAA 日志接管显示。
                await self.cur_user_log.set_state(content=[])
                logger.info(
                    f"MAA 进程已创建: {self.maa_exe_path} - "
                    f"PID: {self.maa_process_manager.main_pid}"
                )
                await asyncio.sleep(1)  # 等待 MAA 处理日志文件
                logger.info(
                    "MAA 进程等待日志文件后状态: "
                    f"running={await self.maa_process_manager.is_running()}"
                )
                await self.maa_log_monitor.start_monitor_file(
                    self._resolve_log_file_path,
                    self.log_start_time,
                    initial_offset=log_offset,
                )
                await self.wait_logs(self.check_log)
                await self.maa_log_monitor.stop()

                maa_log = "".join(self.cur_user_log.content)
                managed_tasks = (
                    not self.native_base and self.cur_user_config.Info.IfQuickConfig
                )
                if (
                    managed_tasks
                    and self.cur_user_log.status == "MAA 部分任务执行失败"
                    and _has_maa_task_failure(maa_log)
                ):
                    # MAA 已结束本轮队列，后续只补跑非体力任务，不重新授予药石额度。
                    self._non_sanity_retry = True
                    failed_sanity = _failed_maa_sanity_tasks(maa_log)
                    self._failed_sanity_tasks.update(failed_sanity)
                    for task in failed_sanity:
                        self.task_dict[task] = False

                if self.cur_user_log.status == "Success!":
                    # 剩余任务成功不覆盖此前明确失败且没有重试的体力任务。
                    self.run_book[self.phase] = not self._failed_sanity_tasks
                    logger.info(f"账号: {self.cur_user_uid} - MAA进程完成代理任务")
                    await self.script_info.set_log(
                        "检测到 MAA 完成代理任务\n正在等待相关程序结束"
                    )
                    if self.pending_res_version:
                        # 代理成功说明资源热更新已走完，记录版本供下次比对
                        self.cur_user_config.Data.LastResVersion = (
                            self.pending_res_version
                        )
                        await self.cur_user_config.commit()
                        self.if_game_hot_update = False
                else:
                    logger.warning(
                        f"账号: {self.cur_user_uid} - 代理任务异常: {self.cur_user_log.status}"
                    )
                    await self.script_info.set_log(
                        f"{self.cur_user_log.status}\n正在中止相关程序"
                    )

                    await self.maa_process_manager.kill()
                    # 关模拟器之前把现场画面留下来：模拟器一关 adb 就补不到了。
                    # 每次失败尝试都刷新，最后一次失败的画面才是最终现场。
                    self._failure_shot = await self._take_failure_shot()
                    await close_emulator(self)
                    await process.kill_process(self.maa_exe_path)

                    # 绿票商店每月顺手买一次，失败不重试也不惊动用户，月份没写回下次调度自会再来
                    if self.phase == "GreenTicketStore":
                        self.run_book[self.phase] = True
                    else:
                        await Notify.send_notice(
                            LocalNotice(
                                title="账号自动代理出现异常！",
                                message=f"账号 {self.cur_user_item.name} 的{MAA_RUN_MOOD_BOOK[self.phase]}部分出现一次异常",
                                ticker=f"{self.cur_user_item.name}的{MAA_RUN_MOOD_BOOK[self.phase]}出现异常",
                                duration_seconds=3,
                            )
                        )

                if self.cur_user_config.Info.IfQuickConfig:
                    self._collect_cultivate_archive(maa_log, finalizing=True)
                    await self._finish_cultivate_round()
                await self._sync_maa_config_updates()

                if not _should_retry_maa(
                    self.cur_user_log.status,
                    maa_log,
                    managed=managed_tasks,
                    pending_tasks=self.task_dict,
                ):
                    if self.cur_user_log.status != "Success!":
                        logger.warning(
                            f"账号 {self.cur_user_item.name} 的"
                            f"{MAA_RUN_MOOD_BOOK[self.phase]}没有可单独重试的非体力任务，停止重试"
                        )
                    break

    def _cultivate_archive_dir(self) -> Path:
        """当前账号的识别数据档案目录（方案决策 31：归属以写入时的
        cur_user_uid 为准；查询、缺口判定与养成注入只读档案。安装目录那份
        DepotData 是 MAA 的工作缓存，只有 overlay 层才按账号覆写它，见
        _apply_depot_context）。"""

        return Path.cwd() / f"data/{self.script_info.script_id}/{self.cur_user_uid}"

    def _apply_depot_context(self, gui_new_set: dict) -> None:
        """overlay 层：把当前账号档案的库存缓存覆写进 MAA 安装目录。

        安装目录那份 DepotData 是 MAA 的工作缓存，物理上跨账号共用；开启覆写
        常规配置时按本账号档案覆写，覆写前键级存底，任务结束在 _finalize_task
        里还原。覆写失败宁可关掉本轮库存保持任务，也不让 MAA 读到别的账号
        留下的库存。
        """

        queue = gui_new_set["Configurations"]["Default"].get("TaskQueue") or []
        depot_tasks = [
            task
            for task in queue
            if isinstance(task, dict)
            and task.get("IsEnable")
            and task_type_of(task) == "DepotMaintain"
        ]
        if not depot_tasks:
            return

        assert self.maa_root_path is not None  # prepare 已确认安装目录
        snapshot_dir = depot_cache_snapshot_dir(self.script_info.script_id)
        archive = self._cultivate_archive_dir() / _MAA_DEPOT_ARCHIVE_NAME
        target = self.maa_root_path / "data" / _MAA_DEPOT_ARCHIVE_NAME
        if snapshot_depot_cache(self.maa_root_path, snapshot_dir):
            try:
                if archive.is_file():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(archive, target)
                    logger.info(
                        f"账号 {self.cur_user_item.name} 的库存缓存已覆写进 MAA 安装目录"
                    )
                else:
                    # 本账号还没有档案：清掉安装目录里的旧缓存让 MAA 重新识别，
                    # 不拿上一个账号的库存充当本账号的
                    target.unlink(missing_ok=True)
                return
            except OSError:
                logger.opt(exception=True).warning(
                    f"账号 {self.cur_user_item.name} 覆写 MAA 库存缓存失败"
                )

        for task in depot_tasks:
            task["IsEnable"] = False
        self.task_dict["DepotMaintain"] = False
        self.task_dict["EventDepotMaintain"] = False
        logger.warning(
            f"账号 {self.cur_user_item.name} 本轮跳过库存保持/养成执行, "
            "请检查 MAA 数据目录的写入权限"
        )

    async def _restore_depot_after_run(self) -> None:
        """收尾：全部收尾动作结束后，还原 overlay 覆写的库存缓存。

        挂在 _finalize_task（收尾主体，由 _run_final_task 放进屏蔽取消的
        独立任务里执行）上，而不是 final_task：收尾被取消或异常中断时它仍会
        执行（wait_for_finalizer_on_cancel）。正常路径在后置脚本后、保存前已还原，
        此处幂等兜底仅覆盖提前异常退出。
        """

        try:
            await self._business_final()
        finally:
            if self.maa_root_path is not None:
                restore_depot_cache(
                    self.maa_root_path,
                    depot_cache_snapshot_dir(self.script_info.script_id),
                )

    def _archive_recognition_file(
        self, name: str, *, require_fresh_sync_time: bool = False
    ) -> bool:
        """把 MAA 安装目录的识别结果只读复制进当前账号档案（T1.17）。

        整份原子覆盖；已归档且源文件未变化时跳过，读取期间仍在写入时
        留待收尾补存，保留此前有效档案。

        Args:
            name: 识别数据文件名（DepotData.json / OperBoxData.json）。
            require_fresh_sync_time: 是否校验 syncTime 不早于本轮开始
                （DepotData 有该字段；OperBoxData 无时间字段，靠会话归因）。

        Returns:
            是否更新档案；跳过或失败时返回 False，不撤销此前成功采集。
        """

        assert self.maa_root_path is not None  # 日志采集在 prepare 后进入
        source = self.maa_root_path / "data" / name
        try:
            source_stat = source.stat()
            version = (
                source_stat.st_ino,
                source_stat.st_mtime_ns,
                source_stat.st_size,
            )
            if self._cultivate_archive_versions.get(name) == version:
                return False
            payload = _utils_io.read_dict_file(source)
            source_stat = source.stat()
            if version != (
                source_stat.st_ino,
                source_stat.st_mtime_ns,
                source_stat.st_size,
            ):
                logger.warning(f"识别数据仍在更新, 留待收尾采集: {name}")
                return False
            if require_fresh_sync_time:
                try:
                    _, sync_time = parse_depot_payload(payload)
                except AttributeError as e:
                    raise _utils_io.ConfigCorruptedError(source) from e
                if sync_time < int(self.log_start_time.timestamp()):
                    logger.warning(
                        f"账号 {self.cur_user_item.name} 的 {name} syncTime 早于本轮开始, 弃用本次采集"
                    )
                    return False
            archive_dir = self._cultivate_archive_dir()
            archive_dir.mkdir(parents=True, exist_ok=True)
            _utils_io.write_file(archive_dir / name, payload)
            self._cultivate_archive_versions[name] = version
            logger.info(f"账号 {self.cur_user_item.name} 的识别数据已落档案: {name}")
            return True
        except (OSError, ValueError, TypeError):
            logger.opt(exception=True).warning(
                f"账号 {self.cur_user_item.name} 采集识别数据失败: {name}"
            )
            return False

    def _collect_cultivate_archive(self, log: str, *, finalizing: bool = False) -> None:
        """新的识别完成标记采集一次完整快照，后续缓存变化在收尾归档。

        归因依据"该链运行在当前账号的 MAA 会话内"（串行调度 + StartUp 已
        切号）；每类数据每轮以最后一次识别标记为准并覆盖档案——队列里养成
        计划（刷取前）与更新数据（刷取后）各有一条仓库识别，取后者下一轮
        缺口判定才用得上刷取后的库存，否则补齐材料后仍会多接管一轮。

        Args:
            log: 当前这次 MAA 运行的累计日志。
            finalizing: 是否在收尾检查已识别文件的变化并补存失败采集。
        """

        for name, markers in (
            (_MAA_DEPOT_ARCHIVE_NAME, _MAA_DEPOT_CHAIN_COMPLETION_MARKERS),
            (_MAA_OPER_BOX_ARCHIVE_NAME, _MAA_OPER_BOX_CHAIN_COMPLETION_MARKERS),
        ):
            position = max(log.rfind(marker) for marker in markers)
            if position < 0:
                continue
            if not finalizing and position <= self._cultivate_archive_positions.get(
                name, -1
            ):
                continue
            # 失败也消费本次标记，普通日志更新不反复尝试，收尾统一补存。
            self._cultivate_archive_positions[name] = position
            if self._archive_recognition_file(
                name, require_fresh_sync_time=name == _MAA_DEPOT_ARCHIVE_NAME
            ):
                if name == _MAA_DEPOT_ARCHIVE_NAME:
                    self._cultivate_collected_depot = True
                else:
                    self._cultivate_collected_oper_box = True

    async def _finish_cultivate_round(self) -> None:
        """采集识别数据或注入自动培养后，刷新达成状态并持久化。

        未采集也未注入时空转；取消时保留标记，交给 final_task 兜底。
        判定只用可自证链，异常只记日志，档案留待下一轮注入前拦截兜底。
        """

        auto_raise_injected = self._cultivate_auto_raise_injected
        if not (
            self._cultivate_collected_depot
            or self._cultivate_collected_oper_box
            or auto_raise_injected
        ):
            return
        self._cultivate_progress_synced = False
        try:
            raw_targets = json.loads(self.cur_user_config.Task.CultivateTargets)
            targets = parse_cultivate_targets(raw_targets)
            if not targets:
                self._cultivate_collected_depot = False
                self._cultivate_collected_oper_box = False
                self._cultivate_auto_raise_injected = False
                return
            # 培养会改变练度，必须重新查询，不能复用培养前的快照。
            # 仅刷材料时沿用 TTL 缓存，保持既有请求次数。
            skland = await maa_api.get_cultivate_skland_progression(
                str(self.script_info.script_id),
                str(self.cur_user_uid),
                force=auto_raise_injected,
            )
            skland_bound = bool(
                self.cur_user_config.Task.CultivateSklandAccount.strip()
                and self.cur_user_config.Task.CultivateSklandUid.strip()
            )
            if skland_bound and not (skland and skland[0]):
                logger.warning(
                    f"账号 {self.cur_user_item.name} 森空岛练度刷新失败, 保留养成目标"
                )
                self._cultivate_collected_depot = False
                self._cultivate_collected_oper_box = False
                self._cultivate_auto_raise_injected = False
                return
            # 库存识别不代表练度已更新；缺少本轮干员识别时保留原计划。
            if not (skland and skland[0]) and not self._cultivate_collected_oper_box:
                return
            context = ProviderContext(
                maa_data_dir=self._cultivate_archive_dir(),
                skland_progressions=skland[0] if skland else {},
                skland_captured_at=skland[1] if skland else 0,
            )
            snapshots = {
                target.operator_id: resolve_progression(
                    operator_id=target.operator_id,
                    chain=get_progression_chain(),
                    context=context,
                )
                for target in targets
            }
            ready_targets, deferred = filter_observed_cultivate_targets(
                targets, snapshots
            )
            certifying_snapshots = {
                target.operator_id: resolve_progression(
                    operator_id=target.operator_id,
                    chain=get_certifying_chain(),
                    context=context,
                )
                for target in ready_targets
            }
            achievements = judge_achievements(ready_targets, certifying_snapshots)
            updated = apply_achievements(ready_targets, achievements)
            if updated != ready_targets:
                names = load_oper_box_names(context)
                # 森空岛可直接确认达成，无干员识别档案时从展示目录补齐名称。
                if any(
                    achievement.achieved
                    and achievement.confident
                    and achievement.operator_id not in names
                    for achievement in achievements
                ):
                    try:
                        catalog = await depot_cultivate_service.operator_catalog(
                            config_path=Config.config_path, proxy=Config.proxy
                        )
                    except YituliuDataError as e:
                        logger.warning(f"养成达成干员名称查询失败, 使用干员编号: {e}")
                    else:
                        names = {
                            operator["value"]: operator["label"] for operator in catalog
                        } | names
                merged_payload = _merge_cultivate_target_updates(
                    raw_targets=raw_targets,
                    updated_targets=updated,
                    deferred_targets=deferred,
                )
                self.cur_user_config.Task.CultivateTargets = json.dumps(
                    merged_payload, ensure_ascii=False
                )
                await self.cur_user_config.commit()
                # 最后一个目标达成被移除后目标清空：接管已不可能，残留的接管
                # 提示要一并清掉——这条路不经过账号配置写入漏斗
                if not merged_payload:
                    await self._set_cultivate_notice("")
                removed = summarize_achievements(
                    targets=ready_targets, achievements=achievements, names=names
                )
                for line in removed:
                    if line not in self._cultivate_achievement_summary:
                        self._cultivate_achievement_summary.append(line)
            self._cultivate_progress_synced = not deferred
        except Exception as e:
            logger.opt(exception=True).warning(
                f"账号 {self.cur_user_item.name} 养成达成刷新失败: {e}"
            )
        # 刷新被取消时不会执行到这里，收尾仍可重试本轮尚未完成的刷新。
        self._cultivate_collected_depot = False
        self._cultivate_collected_oper_box = False
        self._cultivate_auto_raise_injected = False

    async def _set_cultivate_notice(self, notice: str) -> None:
        """写养成状态提示；值未变化时避免重复写盘。"""

        if self.cur_user_config.Data.CultivateNotice == notice:
            return
        self.cur_user_config.Data.CultivateNotice = notice
        await self.cur_user_config.commit()

    async def _prepare_cultivate_injection(
        self,
        source_queue: list[dict],
        *,
        skip_this_round: bool = False,
        skip_farming: bool = False,
    ) -> tuple[dict | None, bool, CultivatePlan | None]:
        """准备当轮养成计划；刷取未跳过时保留完整消耗供库存预留。

        仅在开关开启且目标非空或托管全部干员时生效（Routine 门控由调用方负责）；数据集、
        练度、库存不可用时暂停本轮养成，保留普通库存及后续理智任务。
        绑定森空岛后拉取失败时暂停自动培养，
        不使用缺少本轮识别保障的旧练度档案。

        Returns:
            (养成刷取任务, 是否存在原始目标, 本轮有效养成计划)
        """

        # 开关关闭或无有效目标时，不让保存的旧目标参与本轮备料与培养。
        self._cultivate_round_paused = True
        self._cultivate_execution_targets = ()
        self._cultivate_progress_synced = False
        raw_targets: list
        try:
            raw_targets = json.loads(self.cur_user_config.Task.CultivateTargets)
        except (TypeError, ValueError):
            raw_targets = []
        notice = takeover_notice_patch_value(
            self.cur_user_config.Task.IfCultivate, raw_targets
        )
        manage_owned = self.cur_user_config.Task.CultivateAllOwned
        if notice is not None and not (
            self.cur_user_config.Task.IfCultivate and manage_owned
        ):
            await self._set_cultivate_notice(notice)
            return None, False, None
        if skip_this_round:
            await self._set_cultivate_notice("")
            return None, True, None
        skland_bound = bool(
            self.cur_user_config.Task.CultivateSklandAccount.strip()
            and self.cur_user_config.Task.CultivateSklandUid.strip()
        )
        try:
            # 注入前强刷；未绑定时沿用本地识别，绑定失败时暂停本轮养成。
            skland = await maa_api.get_cultivate_skland_progression(
                str(self.script_info.script_id), str(self.cur_user_uid), force=True
            )
        except Exception as e:
            logger.opt(exception=True).warning(
                f"账号 {self.cur_user_item.name} 森空岛练度查询失败: {e}"
            )
            skland = None
        if (skland_bound or manage_owned) and not (skland and skland[0]):
            await self._set_cultivate_notice("")
            message = (
                "森空岛练度同步失败，本轮养成已暂停；请检查网络或重新绑定森空岛，"
                "日常与库存保持照常执行"
            )
            logger.warning(f"账号 {self.cur_user_item.name} {message}")
            if message not in self._missing_task_source_warned:
                self._missing_task_source_warned.add(message)
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="warning",
                        message=message,
                        messageKey="core.edit.maaCultivateSklandSyncFailed",
                    ),
                )
            return None, True, None

        try:
            if manage_owned and skland:
                catalog = await depot_cultivate_service.operator_catalog(
                    config_path=Config.config_path, proxy=Config.proxy
                )
                merged_targets = append_owned_cultivate_targets(
                    raw_targets, catalog=catalog, progressions=skland[0]
                )
                if merged_targets != raw_targets:
                    raw_targets = merged_targets
                    self.cur_user_config.Task.CultivateTargets = json.dumps(
                        raw_targets, ensure_ascii=False
                    )
                    await self.cur_user_config.commit()
            original_targets = parse_cultivate_targets(raw_targets)
            context = ProviderContext(
                maa_data_dir=self._cultivate_archive_dir(),
                skland_progressions=skland[0] if skland else {},
                skland_captured_at=skland[1] if skland else 0,
            )
            snapshots = {
                target.operator_id: resolve_progression(
                    operator_id=target.operator_id,
                    chain=get_progression_chain(),
                    context=context,
                )
                for target in original_targets
            }
            targets, deferred = filter_observed_cultivate_targets(
                original_targets, snapshots
            )
            self._cultivate_progress_synced = (
                bool(skland and skland[0]) and not deferred
            )
            if deferred:
                logger.warning(
                    f"账号 {self.cur_user_item.name} 本轮延期 {len(deferred)} 个缺少练度数据的养成目标: "
                    + ", ".join(target.operator_id for target in deferred)
                )
                message = (
                    "缺少所需练度数据的养成目标本轮暂缓并保留，其他有效目标继续执行；"
                    "可同步森空岛练度后重试。"
                )
                if message not in self._missing_task_source_warned:
                    self._missing_task_source_warned.add(message)
                    await Publisher.send(
                        id=self.task_info.task_id,
                        type=protocol.TASK_NOTICE,
                        data=WSTaskNoticeData(
                            level="warning",
                            message=message,
                            messageKey="core.edit.maaCultivateTargetsDeferred",
                        ),
                    )
            if not targets:
                await self._set_cultivate_notice("")
                return None, True, None
            (
                updated_targets,
                plan,
                _,
                auto_targets,
            ) = await depot_cultivate_service.prepare_cultivate(
                targets=targets,
                maa_data_dir=self._cultivate_archive_dir(),
                config_path=Config.config_path,
                proxy=Config.proxy,
                today=game_now(self.cur_user_config.Info.Server).date(),
                context=context,
                require_observations=True,
                auto_raise=self.cur_user_config.Task.CultivateAutoRaise,
            )
        except Exception as e:
            logger.opt(exception=True).warning(
                f"账号 {self.cur_user_item.name} 养成数据准备失败, 本轮跳过养成注入: {e}"
            )
            await self._set_cultivate_notice("")
            message = "养成数据暂时不可用，本轮养成已暂停；库存保持与理智任务继续执行"
            if message not in self._missing_task_source_warned:
                self._missing_task_source_warned.add(message)
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="warning",
                        message=message,
                        messageKey="core.edit.maaCultivatePreparationUnavailable",
                    ),
                )
            return None, True, None

        # 达成拦截后把目标状态写回档案：可自证达成的目标已移除（方案 §7.6）；
        # 状态无变化时跳过，避免每轮无谓写盘
        if updated_targets != targets:
            merged_payload = _merge_cultivate_target_updates(
                raw_targets=raw_targets,
                updated_targets=updated_targets,
                deferred_targets=deferred,
            )
            self.cur_user_config.Task.CultivateTargets = json.dumps(
                merged_payload, ensure_ascii=False
            )
            await self.cur_user_config.commit()
        # 旧接管提示清空；养成不再暂停普通库存。
        await self._set_cultivate_notice("")
        if plan is None or not plan.reservations:
            return None, True, None
        self._cultivate_round_paused = False
        self._cultivate_execution_targets = auto_targets

        if skip_farming:
            # 不把预留量合并进普通库存目标，避免间接刷取养成材料。
            logger.info(f"账号 {self.cur_user_item.name} 本轮跳过养成材料刷取")
            return None, True, None

        cultivate_task = None
        if plan.entries:
            cultivate_task = _build_cultivate_task(
                plan,
                _find_task_source(
                    source_queue, _MAA_CULTIVATE_TASK_NAME, "DepotMaintain"
                )
                or _find_task_source(
                    source_queue, "库存保持与干员养成", "DepotMaintain"
                ),
                skip_during_activity=False,
                skip_during_resource_collection=False,
            )
        return cultivate_task, True, plan

    async def _prepare_auto_cultivate_injection(
        self, source_queue: list[dict]
    ) -> dict | None:
        """自动培养独立门控；关闭或森空岛同步失败时不查询目录。"""

        # 附加任务只在实际下发时登记；False 表示本轮已由 MAA 确认完成。
        if self.task_dict.get(_MAA_AUTO_CULTIVATE_TASK_NAME) is False:
            return None
        if self._cultivate_round_paused or not (
            self.cur_user_config.Task.IfCultivate
            and self.cur_user_config.Task.CultivateAutoRaise
        ):
            return None
        targets = self._cultivate_execution_targets
        if not any(
            goal.kind != "module" and goal.state not in ("achieved", "pending_confirm")
            for target in targets
            for goal in target.goals
        ):
            return None

        source = _find_task_source(
            source_queue, _MAA_AUTO_CULTIVATE_TASK_NAME, "OperProgress"
        )
        assert self.maa_root_path is not None
        release = read_installed_release(self.maa_root_path)
        installed_version = parse_version(release[0]) if release else None
        minimum_version = parse_version("v6.19.0-beta.1")
        assert minimum_version is not None
        # 版本无法确认时仅复用已经存在的原生培养入口，旧版不注入未知任务类型。
        if (
            installed_version is not None
            and compare_versions(installed_version, minimum_version) < 0
        ) or (installed_version is None and source is None):
            message = (
                "自动培养未注入：请使用 MAA v6.19.0-beta.1 或更新版本，"
                "并确认 MAA 中有「干员培养」任务；材料刷取照常执行"
            )
            if message not in self._missing_task_source_warned:
                self._missing_task_source_warned.add(message)
                logger.warning(message)
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="warning",
                        message=message,
                        messageKey="core.edit.maaCultivateAutoRaiseUnsupported",
                    ),
                )
            return None
        try:
            catalog = await depot_cultivate_service.operator_catalog(
                config_path=Config.config_path, proxy=Config.proxy
            )
            return _build_auto_cultivate_task(
                targets=targets, catalog=catalog, source_task=source
            )
        except Exception as e:
            logger.opt(exception=True).warning(
                f"账号 {self.cur_user_item.name} 自动培养准备失败, 本轮不注入: {e}"
            )
            message = "自动培养未注入：培养数据暂时不可用，请刷新干员目录后重试；材料刷取照常执行"
            if message not in self._missing_task_source_warned:
                self._missing_task_source_warned.add(message)
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="warning",
                        message=message,
                        messageKey="core.edit.maaCultivateAutoRaiseDataUnavailable",
                    ),
                )
            return None

    async def _warn_missing_task_source(self, source_name: str, affected: str) -> None:
        """提示 MAA 任务队列里认不出某个原生任务，受影响的任务将按默认值运行。

        认不出有两种情况：队列里没有这类任务；或同类任务有多个、名字又都对不上，
        按 ``_find_task_source`` 的约定不猜，免得串用别的任务的配置。

        Args:
            source_name: MAA 任务队列里认不出的任务名。
            affected: 因此按默认值运行的任务，多个用顿号连接。
        """

        message = (
            f"账号 {self.cur_user_item.name} 的 MAA 任务队列里认不出「{source_name}」"
            f"任务（队列里没有，或有多个同类任务且名字都对不上），{affected}本次按"
            f"默认设置运行，在 MAA 里为它设置的选项不会生效"
        )
        if message in self._missing_task_source_warned:
            return
        self._missing_task_source_warned.add(message)

        logger.warning(message)
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="warning", message=message),
        )

    async def set_maa(self, emulator_info: DeviceInfo):
        """配置MAA运行参数"""

        logger.info(f"开始配置MAA运行参数: {self.phase}")

        await self.maa_process_manager.kill()
        await process.kill_process(self.maa_exe_path)
        self._remember_pending_update()

        # 哔哩哔哩用户协议
        if self.cur_user_config.Info.Server == "Bilibili":
            await agree_bilibili(self.maa_tasks_path, True)
        else:
            await agree_bilibili(self.maa_tasks_path, False)

        # 下发前归档 MAS 配置到账号池（下发源，运行回写 _sync_maa_config_updates
        # 会覆盖它；带页面任务字段侧车，指纹去重，失败不阻断运行）。目标路径
        # 按来源 owner（共享来源共享 Default 目录，原生来源无 MAS 配置目录不归档）。
        # native 池由 manager prepare 在任务级一次性归档
        archive_dir = self._config_archive_dir()
        if archive_dir is not None:
            seed_maa_base_config(archive_dir)
            archive_mas_runtime_backup(
                self.script_info.script_id,
                str(self.cur_user_uid),
                archive_dir,
                overlay=read_overlay_values(self.cur_user_config),
                # 备份标注来源：tri_state 池跨来源恢复靠它切回
                base=self.config_base,
            )

        # ── 第一段：来源落盘 ──────────────────────────────────────────
        # 用 MAS 托管配置覆盖 MAA 原生配置目录。原生来源跳过这一段——
        # 原生来源的事实源是 MAA 安装目录里现有的原生配置。
        # 来源目录可能不存在（新建托管/用户首次运行，或用户删掉专项重建）：
        # 此时保持安装目录现有的 MAA 配置不动，它天然是可运行的默认配置。
        if self.config_base == CONFIG_BASE_SHARED:
            self._copy_source_config(
                Path.cwd() / f"data/{self.script_info.script_id}/Default/ConfigFile"
            )
        elif self.config_base == CONFIG_BASE_INDEPENDENT:
            self._copy_source_config(
                Path.cwd()
                / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile"
            )
        elif self.native_base:
            # 原生来源从本轮原生快照开始，不能继承上一账号或上一阶段的覆写常规配置。
            source = Path.cwd() / f"data/{self.script_info.script_id}/Temp"
            if source.is_dir():
                shutil.copytree(
                    source,
                    self.maa_set_path,
                    dirs_exist_ok=True,
                    ignore=shutil.ignore_patterns(MAA_STAMINA_LEGACY_FILENAME),
                )

        # base 缺失/损坏时退回 MAA 自带 .bak 或随包预设；引导在运行写盘前跳过。
        gui_new_set = read_maa_config_with_fallback(self.maa_set_path)
        self._remember_pending_update()

        # Default 本身可能缺失——原生来源/沿用安装目录配置时该文件不由 MAS 生成，
        # 兜底必须无条件执行。
        ensure_maa_default_configuration(gui_new_set)

        # 非原生来源才由 MAS 修正队列条目；原生来源的 TaskQueue 完全由用户维护。
        if not self.native_base:
            for configurations in (gui_new_set.get("Configurations") or {}).values():
                if isinstance(configurations, dict):
                    queue = configurations.get("TaskQueue")
                    if isinstance(queue, list):
                        configurations["TaskQueue"] = _repair_maa_task_queue(queue)

        # 使用简体中文
        gui_new_set["Gui"]["Localization"] = "zh-cn"

        # 原生来源的 TaskQueue 由用户在 MAA 原生界面维护；仅保留下方运行期 overlay。
        if not self.native_base and self.cur_user_config.Info.IfQuickConfig:
            await self._apply_maa_quick_config(gui_new_set)

        # 库存缓存按账号隔离属 overlay 层行为，与上方面板覆写同一个开关：
        # 关闭覆写常规配置时不读不写安装目录那份缓存，原样留给 MAA。
        if self.cur_user_config.Info.IfQuickConfig:
            self._apply_depot_context(gui_new_set)

        self._configure_maa_runtime(
            gui_new_set=gui_new_set,
            emulator_info=emulator_info,
            avd=await self._resolve_avd_device(),
        )
        # 待更新包已保留；本次任务启动不再触发安装，结束后恢复登记。
        gui_new_set.setdefault("Update", {})["UpdatePackage"] = ""

        gui_new_set["Gui"].update(MAA_GUIDE_SKIP_VALUES)
        _utils_io.write_file(self.maa_set_path / "gui.new.json", gui_new_set)
        self._snapshot_maa_config()
        _utils_io.mark_native_config_injected(
            Path.cwd() / f"data/{self.script_info.script_id}/Temp",
            self.maa_set_path,
            script_id=self.script_info.script_id,
        )
        logger.success(f"MAA运行参数配置完成: {self.phase}")

    def _copy_source_config(self, source: Path) -> None:
        """把 MAS 托管配置覆盖进 MAA 配置目录；来源不存在时保持现状。

        来源目录缺失是正常情形（新建托管、新建账号、删除专项后重建），此时
        MAA 安装目录里的现有配置就是可运行的事实源，直接沿用即可，不必也无法
        从空目录拷贝。
        """

        if not source.is_dir():
            logger.info("MAS 配置目录尚未建立, 沿用 MAA 安装目录现有配置")
            return
        shutil.copytree(
            source,
            self.maa_set_path,
            dirs_exist_ok=True,
            ignore=shutil.ignore_patterns(MAA_STAMINA_LEGACY_FILENAME),
        )

    async def _apply_maa_quick_config(self, gui_new_set: dict) -> None:
        """仅开启覆写常规配置时构造面板任务，来源导入与启动设置留在外层。"""

        # 运行异常只说明曾经入队，重新规划时移除本次未再下发的旧等待标记；
        # MAA 已明确判失败的附加任务仍需保留，不能被空队列成功覆盖。
        for name in (_MAA_AUTO_CULTIVATE_TASK_NAME, _MAA_DATA_UPDATE_TASK_NAME):
            if self.task_dict.get(name) and name not in self._failed_extra_tasks:
                del self.task_dict[name]

        if self._non_sanity_retry:
            self.task_dict["Fight"] = False

        task_set = {}
        source_queue = gui_new_set["Configurations"]["Default"].get("TaskQueue", [])
        if not isinstance(source_queue, list):
            source_queue = []
        # 存档队列里缺的任务（用户在 MAA 原生界面删掉过它）由随包预设补齐，
        # 见下方 MAA_TASKS 装配循环
        preset_queue = get_maa_base_preset()["Configurations"]["Default"]["TaskQueue"]
        # 活动目标每轮解析；旧活动优先已在配置加载时迁入这一逻辑阶段。
        self.task_dict["EventDepotMaintain"] = False
        activity_stages = []
        if self.phase == "Routine":
            # 运行异常可按当轮数据重建；MAA 已收尾后只补跑非体力任务。
            self.task_dict["DepotMaintain"] = (
                self.cur_user_config.Task.IfDepotMaintain
                and "DepotMaintain" not in self._failed_sanity_tasks
                and not self._non_sanity_retry
            )
            # 活动关卡信息已在 MaaManager.prepare 里刷新过一次, 这里直接用缓存
            stage_info = await stage_service.get_stage_info(
                "Info", server=self.cur_user_config.Info.Server
            )
            activity_stages = stage_info.get("Activity", [])

        # 来源各自判断跳过条件，不能让一方的整段设置跳过另一方。
        activity_open = resource_collection_open = False
        if self.phase == "Routine":
            try:
                activity_open, resource_collection_open = _maa_activity_state(
                    json.loads(await stage_service.get_stage()),
                    self.cur_user_config.Info.Server,
                    now=datetime.now(timezone.utc),
                )
            except (KeyError, TypeError, ValueError, AttributeError) as e:
                logger.warning(f"活动时段数据不可用，本轮不按活动条件跳过: {e}")

        # 养成仅在常规轮注入；暂时缺数据时继续普通库存与理智任务。
        cultivate_task = None
        cultivate_plan = None
        auto_cultivate_task = None
        update_task = None
        skland_bound = bool(
            self.cur_user_config.Task.CultivateSklandAccount.strip()
            and self.cur_user_config.Task.CultivateSklandUid.strip()
        )
        if self.phase == "Routine":
            (
                cultivate_task,
                has_targets,
                cultivate_plan,
            ) = await self._prepare_cultivate_injection(
                source_queue,
                skip_farming=(
                    activity_open
                    and self.cur_user_config.Task.CultivateSkipDuringActivity
                )
                or "DepotMaintain" in self._failed_sanity_tasks
                or self._non_sanity_retry,
                skip_this_round=(
                    resource_collection_open
                    and self.cur_user_config.Task.CultivateSkipDuringResourceCollection
                ),
            )
            auto_cultivate_task = await self._prepare_auto_cultivate_injection(
                source_queue
            )
            if (
                has_targets or self.task_dict.get(_MAA_DATA_UPDATE_TASK_NAME)
            ) and self.task_dict.get(_MAA_DATA_UPDATE_TASK_NAME) is not False:
                # 更新数据紧跟养成/库存保持注入（方案决策 30），为下一轮
                # 提供归属正确的识别数据
                update_task = _build_data_update_task(
                    _find_task_source(
                        source_queue, _MAA_DATA_UPDATE_TASK_NAME, "UserDataUpdate"
                    ),
                    # 已绑定森空岛时直接使用其练度，省去游戏内干员识别。
                    update_oper_box=not skland_bound,
                )

        # 优先按任务名称匹配，确保多个 Fight 任务各自继承原生高级配置。
        missing_sources: set[str] = set()
        for en_task, zh_task in zip(MAA_TASKS, MAA_TASKS_ZH):
            # 默认关闭时不写入新任务，兼容尚未支持该任务类型的 MAA 版本
            # （库存保持、更换主题；更换主题需 MAA v6.17.3+，旧版无法反序列化未知任务类型）
            if (
                en_task in ("DepotMaintain", "SwitchTheme")
                and not self.task_dict[en_task]
            ):
                continue

            source = _find_task_source(source_queue, zh_task, en_task)
            if source is None:
                missing_sources.add(en_task)
                # 缺了就补随包预设的同名任务，不能塞空壳：MAA 反序列化缺字段的
                # 任务会回填它自己的占位默认值（信用收支落成
                # {{ HighPriorityDefault }} / {{ BlacklistDefault }}）并落盘，
                # 用户之后在 MAA 里再也改不回来
                source = _find_task_source(preset_queue, zh_task, en_task)
            task_set[en_task] = source or {
                "$type": f"{en_task}Task",
                "Name": zh_task,
                "IsEnable": False,
                "TaskType": en_task,
            }

        annihilation_source = _find_task_source(source_queue, "剿灭作战", "Fight")
        # 吃药 / 碎石类任务取不到原生配置就只剩默认值，用户在 MAA 里设的选项
        # 全部失效却看不出来，必须提示。剿灭作战没有同名任务时本就
        # 沿用理智作战，只有理智作战也缺失才会落到默认值
        if "DepotMaintain" in missing_sources:
            await self._warn_missing_task_source(
                "库存保持与干员养成", "库存保持与干员养成"
            )
        if "Fight" in missing_sources:
            affected = []
            if self.task_dict["Fight"] and self.phase == "Routine":
                affected.append("理智任务")
            if (
                self.task_dict["Fight"]
                and self.phase == "Annihilation"
                and annihilation_source is None
            ):
                affected.append("剿灭作战")
            if affected:
                await self._warn_missing_task_source("理智任务", "、".join(affected))

        # 养成组本轮已花掉的额度不影响库存计划，反之亦然，两组各按自己的设置覆盖。
        _apply_depot_quota_override(
            cultivate_task,
            medicine=self.cur_user_config.Task.CultivateMedicineNumb,
            stone=self.cur_user_config.Task.CultivateStoneNumb,
        )
        # 库存保持计划：MAS 覆写常规配置面板维护的计划写回原生 PlanList。只覆盖
        # MAS 管理的三项（Stage/DropId/DropCount），其余原生字段（含用户在 MAA 里
        # 设的药/石开关）整条透传，不按 #927 前的口径硬编码 UseMedicine/UseStone。
        if "DepotMaintain" in task_set:
            task_set["DepotMaintain"] = _build_depot_maintain_task(
                self.cur_user_config.Task.DepotMaintainPlans,
                source_task=task_set["DepotMaintain"],
            )
            stock_task = task_set["DepotMaintain"]
            if self._stock_depot_completed:
                # 重试保留库存目标，但不重新领取已执行阶段的药石额度。
                stock_task.update({gate: False for gate, _ in _MAA_DEPOT_QUOTA_KEYS})
            else:
                _apply_depot_quota_override(
                    stock_task,
                    medicine=self.cur_user_config.Task.DepotMaintainMedicineNumb,
                    stone=self.cur_user_config.Task.DepotMaintainStoneNumb,
                )
            stock_skipped = (
                activity_open and stock_task.get("SkipDuringActivity", False)
            ) or (
                resource_collection_open
                and stock_task.get("SkipDuringResourceCollection", False)
            )
            if stock_skipped:
                conditions = []
                if activity_open and stock_task.get("SkipDuringActivity", False):
                    conditions.append("活动期间跳过")
                if resource_collection_open and stock_task.get(
                    "SkipDuringResourceCollection", False
                ):
                    conditions.append("资源全开放期间跳过")
                logger.info(
                    f"账号 {self.cur_user_item.name} 普通库存本轮暂停，命中来源设置: "
                    + "、".join(conditions)
                )
                del task_set["DepotMaintain"]
                self.task_dict["DepotMaintain"] = False
            elif cultivate_plan is not None and stock_task["PlanList"]:
                task_set["DepotMaintain"] = _build_stock_cultivate_task(
                    stock_task, cultivate_task, cultivate_plan
                )
                cultivate_task = None

        # 加载关卡号配置
        if self.cur_user_config.Stage.StageMode == "Fixed":
            plan_data = {
                stage_key: getattr(self.cur_user_config.Stage, stage_key)
                for stage_key in MAA_STAGE_KEY
            }
        else:
            # StageMode 的 ref 已将类型域限定为 MaaPlanConfig。
            plan = cast(
                MaaPlanConfig, Config.PlanConfig[self.cur_user_config.Stage.StageMode]
            )
            plan_data = {
                stage_key: plan.get_current_info(
                    stage_key, server=self.cur_user_config.Info.Server
                )
                for stage_key in MAA_STAGE_KEY
            }

        fight_source = deepcopy(task_set["Fight"])

        # 理智作战相关配置项
        if self.phase == "Annihilation":
            # 关卡配置
            task_set["Fight"] = _merge_fight_task(
                annihilation_source or fight_source, MAA_ANNIHILATION_FIGHT_BASE
            )
            task_set["Fight"]["UseMedicine"] = bool(
                plan_data.get("MedicineNumb", 0) != 0
            )
            task_set["Fight"]["MedicineCount"] = plan_data.get("MedicineNumb", 0)
            task_set["Fight"]["AnnihilationStage"] = (
                self.cur_user_config.Task.Annihilation
            )

        elif self.phase == "Routine":
            # 普通理智作战不能继承剿灭任务的语义字段。
            task_set["Fight"].update(
                {
                    "Name": "理智任务",
                    "TaskType": "Fight",
                    "UseCustomAnnihilation": False,
                }
            )
            # 理智药配置
            task_set["Fight"]["UseMedicine"] = bool(
                plan_data.get("MedicineNumb", 0) != 0
            )
            task_set["Fight"]["MedicineCount"] = plan_data.get("MedicineNumb", 0)
            # 关卡配置
            task_set["Fight"]["Series"] = int(plan_data.get("SeriesNumb", "0"))
            task_set["Fight"]["StagePlan"] = [
                (
                    ""
                    if plan_data.get(stage_key, "-") == "*"
                    else plan_data.get(stage_key, "-")
                )
                for stage_key in ("Stage", "Stage_1", "Stage_2", "Stage_3")
                if plan_data.get(stage_key, "-") != "-"
            ]
            task_set["Fight"]["IsStageManually"] = True
            task_set["Fight"]["UseOptionalStage"] = True
            task_set["Fight"]["UseWeeklySchedule"] = False

            # 共享来源下托管的配置
            if self.config_base == CONFIG_BASE_SHARED:
                task_set["Fight"]["EnableTimesLimit"] = False
                task_set["Fight"]["EnableTargetDrop"] = False
                fight_source = deepcopy(task_set["Fight"])

            # 基建配置
            if self.cur_user_config.Task.InfrastMode == "Custom":
                infrast_path = (
                    Path.cwd()
                    / f"data/{self.script_info.script_id}/{self.cur_user_uid}/Infrastructure/infrastructure.json"
                )
                infrast_plans, infrast_problem = load_infrast_plans(
                    self.cur_user_config.Data.CustomInfrast
                )
                if infrast_problem is None:
                    infrast_path.parent.mkdir(parents=True, exist_ok=True)
                    infrast_path.write_text(
                        self.cur_user_config.Data.CustomInfrast, encoding="utf-8"
                    )
                    task_set["Infrast"]["Mode"] = "Custom"
                    task_set["Infrast"]["Filename"] = str(infrast_path)
                    task_set["Infrast"]["InfrastPlan"] = [
                        {
                            "Index": index,
                            "Name": infrast.get("name", f"第 {index + 1} 班"),
                            "Description": infrast.get("description", ""),
                            "DescriptionPost": infrast.get("description_post", ""),
                            "Period": infrast.get("period", []),
                        }
                        for index, infrast in enumerate(infrast_plans)
                    ]
                    # PlanSelect 不沿用存档: 脚本模式下存档是全脚本共用的, MAA 每跑完
                    # 一次基建就 ++PlanSelect, 多个自定义基建用户会互相拨对方的班次。
                    # 带时段表 → -1, 时间语义整个交给 MAA 按时段选班(-1 不推进);
                    # 无时段表 → 注入用户自己的指针, 一轮里重试几次都是同一个值,
                    # 基建换班完成后由 check_log 推进一次
                    if infrast_plan_mode(infrast_plans) == "rotate":
                        if self._infrast_plan_index is None:
                            self._infrast_plan_count = len(infrast_plans)
                            self._infrast_plan_index = (
                                int(self.cur_user_config.Data.InfrastPlanIndex)
                                % self._infrast_plan_count
                            )
                        task_set["Infrast"]["PlanSelect"] = self._infrast_plan_index
                    else:
                        task_set["Infrast"]["PlanSelect"] = -1
                else:
                    logger.warning(
                        f"账号 {self.cur_user_item.name} 的{infrast_problem}, 将使用普通基建模式"
                    )
                    await Publisher.send(
                        id=self.task_info.task_id,
                        type=protocol.TASK_NOTICE,
                        data=WSTaskNoticeData(
                            level="warning",
                            message=(
                                f"账号 {self.cur_user_item.name} 的{infrast_problem}，"
                                f"将使用普通基建模式"
                            ),
                        ),
                    )
                    task_set["Infrast"]["Mode"] = "Normal"
            else:
                task_set["Infrast"]["Mode"] = self.cur_user_config.Task.InfrastMode

        event_depot_task = None
        if (
            self.phase == "Routine"
            and (not self._event_depot_completed)
            and "EventDepotMaintain" not in self._failed_sanity_tasks
            and not self._non_sanity_retry
            and self.cur_user_config.Task.IfEventDepotMaintain
        ):
            event_depot_source = _find_task_source(
                task_queue=source_queue,
                name="活动关均衡理智",
                task_type="DepotMaintain",
            ) or _find_task_source(
                task_queue=preset_queue,
                name="活动关均衡理智",
                task_type="DepotMaintain",
            )
            event_depot_task, activity_notices = _build_event_depot_maintain_task(
                self.cur_user_config.Task.EventDepotMaintainPlans,
                activity_stages,
                source_task=event_depot_source,
            )
            _apply_depot_quota_override(
                event_depot_task,
                medicine=self.cur_user_config.Task.EventDepotMaintainMedicineNumb,
                stone=self.cur_user_config.Task.EventDepotMaintainStoneNumb,
            )
            for notice_key, notice in activity_notices:
                logger.warning(notice)
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="warning",
                        message=notice,
                        messageKey=notice_key,
                    ),
                )
            self.task_dict["EventDepotMaintain"] = event_depot_task is not None
            if event_depot_task is None:
                logger.info("活动关均衡理智没有当前活动的有效材料计划，本轮跳过")

        # 导出任务配置
        self.task_dict["StartUp"] = True
        task_queue = gui_new_set["Configurations"]["Default"]["TaskQueue"] = []
        for task_type in MAA_TASKS:
            if task_type not in task_set:
                continue

            task_set[task_type]["IsEnable"] = self.task_dict[task_type]
            if task_type == "Fight":
                # 养成刷取或库存保持结束后立即培养、更新数据，再执行日常任务。
                if auto_cultivate_task is not None:
                    task_queue.append(auto_cultivate_task)
                    self.task_dict[_MAA_AUTO_CULTIVATE_TASK_NAME] = True
                    self._cultivate_auto_raise_injected = True
                    self._cultivate_progress_synced = False
                if update_task is not None:
                    task_queue.append(update_task)
                    self.task_dict[_MAA_DATA_UPDATE_TASK_NAME] = True
                    if not skland_bound:
                        self._cultivate_progress_synced = False
            task_queue.append(task_set[task_type])

            if task_type == "StartUp" and event_depot_task is not None:
                task_queue.append(event_depot_task)
            if task_type == "StartUp" and cultivate_task is not None:
                # 没有普通库存参与时，养成备料仍位于活动阶段之后。
                task_queue.append(cultivate_task)

        # 绿票商店走 MAA 的自定义任务，本模式下队列里只有它和开始唤醒
        if self.phase == "GreenTicketStore":
            task_queue.append(dict(MAA_GREEN_TICKET_STORE_TASK))

        # 非原生来源队列严格等于 MAS 合成结果：来源队列里的未知任务(自动肉鸽、
        # 生息演算、用户自定义任务等)不透传带回——用户自定义任务队列只在原生
        # 来源存在(MAS 零写入, 安装目录原生配置即现场)。

    async def _resolve_avd_device(self) -> tuple[Path, int, str] | None:
        """这次用的设备是 ModAVD 实例时返回 ``(根目录, 控制台端口, SDK 的 adb)``，否则 ``None``。

        控制台端口和 adb 都问 modavd（``modavd list``；根目录可以设 ``portBase`` 换一段端口），假 MuMu
        截图组件按控制台端口找共享内存。
        """
        index = self.script_config.Emulator.Index
        device_ref = resolve_device_ref(self.emulator_manager, index)
        if device_ref is None or device_ref.emulator_type != "avd":
            return None
        adb_info = await self.emulator_manager.avd_adb_info(index)
        if adb_info is None:
            raise RuntimeError(f"设备 {index} 不是 ModAVD 实例")
        return (
            _utils_emulator2.avd.components.root_from_manager_exe(
                device_ref.manager_path
            ),
            adb_info.ports.console,
            adb_info.adb_exe,
        )

    async def _maa_process_env(self) -> dict[str, str] | None:
        """MAA 进程的环境变量。ModAVD 实例上把它（连同 MaaCore 起的 adb）指到脚本专用的 adb
        server（``modavd servers`` 报的 ``script_adb_server_port``，默认 20049），不落到 5037；其余模拟器返回 ``None``，
        照旧继承 MAS 的环境。"""
        return await script_process_env(
            self.emulator_manager, self.script_config.Emulator.Index
        )

    def _configure_maa_runtime(
        self,
        gui_new_set: dict,
        emulator_info: DeviceInfo,
        avd: tuple[Path, int, str] | None = None,
    ) -> None:
        """两种覆写常规配置状态均需的启动、模拟器和账号设置，不改任务选择。

        ``avd`` 是 :meth:`_resolve_avd_device` 的结果：ModAVD 实例的 ``(根目录, 控制台端口, SDK 的 adb)``。
        """

        current_gui = gui_new_set["Configurations"]["Default"]["Gui"]

        # 关闭定时，避免与 MAS 调度重叠。
        for timer in gui_new_set.setdefault("Timers", {}).setdefault("List", []):
            if isinstance(timer, dict):
                timer["IsEnabled"] = False

        if emulator_info.adb_address != "Unknown":
            current_gui["ConnectSettings"]["Address"] = emulator_info.adb_address

        # ModAVD 实例：MAA 走假 MuMu 截图通道（MuMu 12 预设 + 桥接 + 实例号 = 控制台端口），
        # 雷电 / MuMu 实例不经过这里。这些键和上面的地址一样，由原生配置快照在任务结束后还原。
        self._avd_screencap_guard = avd is not None
        if avd is not None:
            avd_root, avd_console, avd_adb = avd
            ensure_mumu_shim(avd_root)
            current_gui["ConnectSettings"] = build_maa_connect_settings(
                avd_root, avd_console, current_gui.get("ConnectSettings"), avd_adb
            )
            logger.info(
                f"ModAVD 实例（控制台端口 {avd_console}）：MAA 截图走假 MuMu 通道"
            )
        else:
            # 先按所选实例解析安装，避免多安装管理器沿用上一次命中的 ADB。
            device_ref = resolve_device_ref(
                self.emulator_manager, self.script_config.Emulator.Index
            )
            # 自定义管理器可无专用引用，多安装管理器仍须解析所选安装。
            if device_ref is None and isinstance(
                self.emulator_manager, _utils_emulator2.facade.Emulator2Manager
            ):
                raise ValueError("无法解析所选模拟器实例，请检查模拟器配置")
            connect_settings = current_gui["ConnectSettings"]
            adb_path = self.emulator_manager.get_adb_path()
            if (
                adb_path is None
                and device_ref is not None
                and device_ref.emulator_type == "general"
            ):
                configured_adb = str(connect_settings.get("AdbPath") or "").strip()
                if configured_adb:
                    adb_path = Path(configured_adb)
                    if not adb_path.is_absolute():
                        adb_path = self.maa_set_path.parent / adb_path
            if adb_path is None or not adb_path.is_file():
                raise ValueError("未找到可用的 ADB，请检查模拟器或 MAA 的连接设置")
            address = emulator_info.adb_address.strip()
            if not address or address == "Unknown":
                raise ValueError("无法获取所选模拟器的 ADB 地址，请检查模拟器连接")
            connect_settings.update(
                {
                    "AdbPath": str(adb_path),
                    "Address": address,
                    "AutoDetect": False,
                    "AlwaysAutoDetect": False,
                }
            )

        post_actions = MAA_TASK_TRANSITION_METHOD_BOOK[
            self.script_config.Run.TaskTransitionMethod
        ]
        current_gui["PostActions"] = int(post_actions)
        current_gui["RuntimeSettings"]["StartGame"] = True
        current_gui["StartUpSettings"].update(
            {"RunDirectly": True, "StartEmulator": False}
        )
        update_settings = gui_new_set.setdefault("Update", {})
        update_settings.update(
            {
                "CheckOnSchedule": False,
                "AutoDownloadUpdatePackage": True,
                "AutoInstallUpdatePackage": False,
            }
        )
        # 接管开启即暂停原生更新，不因本轮更新失败而重新启用。
        # GitHub 资源源仅支持手动下载，临时选择随快照恢复，不改变 CDK。
        if self.script_config.Update.TakeoverEnabled:
            update_settings["CheckOnStartup"] = False
            update_settings["AutoDownloadUpdatePackage"] = False
            update_settings["UpdateSource"] = "GitHub"
        if Config.setting.Function.IfSilence:
            # 启动即最小化是同一开关的新键，新 MAA 只读 gui.new.json。
            gui_new_set["Gui"].update(
                {"UseTray": True, "MinimizeToTray": True, "MinimizeOnStartup": True}
            )
            # 无人值守运行，公告与更新后首启的版本说明弹窗一并关闭
            gui_new_set.setdefault("AnnouncementInfo", {})["DoNotShow"] = True
            update_settings["DoNotShowUpdate"] = True

        server = self.cur_user_config.Info.Server
        account = self.cur_user_config.Info.Id
        current_gui["RuntimeSettings"]["ClientType"] = _MAA_CLIENT_TYPE_TO_INT.get(
            server, 0
        )
        # 账号属于基本信息；关闭覆写常规配置时只更新来源中已有的开始唤醒任务。
        for task in gui_new_set["Configurations"]["Default"].get("TaskQueue", []):
            if task.get("TaskType") != "StartUp" or server not in (
                "Official",
                "Bilibili",
            ):
                continue
            task["AccountName"] = (
                f"{account[:3]}****{account[7:]}"
                if server == "Official" and len(account) == 11
                else account
            )
            # MAA 账号切换需要独立开关，空账号仍由 MAA 沿用登录态。
            task["AccountSwitchEnabled"] = True

    def _snapshot_maa_config(self) -> None:
        """记录托管注入完成后的 MAA 配置基线, 供任务结束后甄别 MAA 自身的写盘变更。"""

        try:
            self._maa_config_baseline = {
                name: deepcopy(_utils_io.read_dict_file(self.maa_set_path / name))
                for name in _MAA_CONFIG_FILES
            }
        except Exception as e:
            logger.opt(exception=True).warning(
                f"记录 MAA 配置基线失败, 本次运行跳过配置回写: {e}"
            )
            self._maa_config_baseline = None

    def _config_archive_dir(self) -> Path | None:
        """当前账号的 MAA 配置来源存档目录, 与 set_maa 的导入路径对称。

        原生来源账号没有 MAS 托管配置目录（对齐 MaaEnd 的「原生来源无 mas 池」），
        返回 ``None``：不下发前归档、运行产出也不回写——安装目录现场由
        任务结束的原生配置快照恢复机制管理。
        """

        if self.config_base == CONFIG_BASE_NATIVE:
            return None
        if self.config_base == CONFIG_BASE_SHARED:
            return Path.cwd() / f"data/{self.script_info.script_id}/Default/ConfigFile"
        return (
            Path.cwd()
            / f"data/{self.script_info.script_id}/{self.cur_user_uid}/ConfigFile"
        )

    @property
    def update_config_dir(self) -> Path:
        """当前账号的配置来源目录，用于保留其原生更新来源选择。"""
        return self._config_archive_dir() or (
            Path.cwd() / f"data/{self.script_info.script_id}/Temp"
        )

    def _remember_pending_update(self) -> None:
        """保留原生下载登记，供下次启动前交还官方更新入口。"""
        assert self.maa_root_path is not None
        try:
            pending = read_pending_update(self.maa_root_path)
        except (OSError, ValueError) as error:
            logger.warning(f"MAA 本体更新: 无法保留原生待更新登记: {error}")
            return
        if all(pending) and (self.maa_root_path / pending[1]).is_file():
            self.pending_update = pending
            # 保存失败必须向上传播，不能清空唯一登记后继续启动下一阶段。
            save_deferred_update(
                self.maa_root_path, version=pending[0], package=pending[1]
            )

    async def _sync_maa_config_updates(self) -> None:
        """把 MAA 运行期写盘的配置变更(相对本模式基线)回写到配置来源存档。

        MAA 原生的每日状态(如借战/访问好友的最近执行日期)因此能跨托管会话
        存活, 下次托管 MAA 读到自己的记录后自行去重; 失败只记日志不抛出。
        """

        self._remember_pending_update()
        if self.native_base:
            return
        baseline = self._maa_config_baseline
        if baseline is None:
            return
        archive_dir = self._config_archive_dir()
        if archive_dir is None or not archive_dir.is_dir():
            return

        for name in _MAA_CONFIG_FILES:
            if not baseline.get(name):
                continue
            try:
                current = _utils_io.read_dict_file(self.maa_set_path / name)
                current = _without_maa_update_changes(current, baseline[name], name)
                archive = _utils_io.read_dict_file(archive_dir / name)
            except Exception as e:
                logger.opt(exception=True).warning(
                    f"读取 MAA 配置以对比回写失败({name}): {e}"
                )
                continue
            if not current or not archive:
                # MAA 写盘半截或存档缺失时不回写, 宁可下次多跑一次
                continue

            archive_new = deepcopy(archive)
            # 运行期写盘的是归一后的 Default 方案, 生效方案不是 Default 时合并回该方案键
            if not _merge_maa_config_file(
                archive_new,
                baseline[name],
                current,
                maa_scheme_name(archive),
                ignore_keys=_MAA_TASK_KEYS_NOT_MERGED
                if self.cur_user_config.Info.IfQuickConfig
                else frozenset(),
            ):
                continue
            _utils_io.write_file(archive_dir / name, archive_new)
            logger.info(
                f"账号 {self.cur_user_item.name} 的 MAA 配置变更已回写存档: {name}"
            )

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """日志回调"""

        log = "".join(log_content)
        await self.cur_user_log.set_state(content=log_content)
        await self.script_info.set_log(log)

        if self.phase == "Annihilation":
            progress = _parse_annihilation_weekly_progress(log)
            completed = _has_completed_annihilation_week(log)
            if completed:
                self.task_dict["Fight"] = False
                self.run_book["Annihilation"] = True
                if not self._annihilation_weekly_completion_recorded:
                    self.cur_user_config.Data.AnnihilationCompletedWeek = (
                        _current_week_marker(game_now(self.cur_user_config.Info.Server))
                    )
                    await self.cur_user_config.commit()
                    self._annihilation_weekly_completion_recorded = True
                    progress_text = (
                        f"{progress[0]}/{progress[1]}" if progress else "完成任务日志"
                    )
                    logger.info(
                        f"账号 {self.cur_user_item.name} 剿灭已达到本周上限："
                        f"{progress_text}"
                    )

        # MAA 完成自定义任务时打印的是队列项名称，据此记录本月已购买
        if (
            self.phase == "GreenTicketStore"
            and not self.run_book["GreenTicketStore"]
            and f"完成任务: {MAA_GREEN_TICKET_STORE_TASK['Name']}" in log
        ):
            self.run_book["GreenTicketStore"] = True
            self.cur_user_config.Data.GreenTicketStoreMonth = datetime.now(
                tz=_utils_constants.UTC4
            )
            await self.cur_user_config.commit()
            logger.info(f"账号 {self.cur_user_item.name} 已完成本月绿票商店购买")

        # 无时段排班表: 基建换班完成即推进用户自己的班次指针, 一轮内只推一次;
        # 后续重试注入的仍是本轮的班次, 不会把下一班提前换上
        if (
            self.phase == "Routine"
            and self._infrast_plan_index is not None
            and not self._infrast_plan_advanced
            and "完成任务: 基建换班" in log
        ):
            self._infrast_plan_advanced = True
            next_index = (self._infrast_plan_index + 1) % self._infrast_plan_count
            self.cur_user_config.Data.InfrastPlanIndex = next_index
            await self.cur_user_config.commit()
            logger.info(
                f"账号 {self.cur_user_item.name} 基建换班已完成第 "
                f"{self._infrast_plan_index + 1} 班, 下次从第 {next_index + 1} 班开始"
            )

        # 养成采集：识别链完成标记 → 立即读安装目录识别数据落用户档案
        # （方案 §4.2/决策 31，T1.17；无标记时不读不采）
        if self.cur_user_config.Info.IfQuickConfig:
            self._collect_cultivate_archive(log)

        # ModAVD 实例上截图不许回落到普通 adb（约 250 ms，账号 09-26 定「不如不做」）
        avd_fallback = (
            screencap_fallback_status(log)
            if getattr(self, "_avd_screencap_guard", False)
            else None
        )
        # 整份脚本日志可达数 MB，check_log 又每秒轮询一次，收尾判定只扫一遍。
        if re.search(r"完成任务:\s*[^\r\n]+", log):
            from auto_mas_core.host.core_script_update_queue import (
                report_script_task_completed,
            )

            report_script_task_completed()
        completed_log = "任务已全部完成！" in log
        failed_log = _has_maa_task_failure(log)
        if avd_fallback is not None:
            await self.cur_user_log.set_state(status=avd_fallback)
        elif "未选择任务" in log:
            await self.cur_user_log.set_state(status="MAA 未选择任何任务")
        elif "任务出错: 开始唤醒" in log:
            await self.cur_user_log.set_state(status="MAA 未能正确登录 PRTS")
        elif completed_log or failed_log:
            # 常规任务的完成状态取自 MAA 本轮输出。
            for en_task, zh_task in zip(MAA_TASKS, MAA_TASKS_ZH):
                names = {zh_task}
                names.update(_MAA_SANITY_TASK_NAMES.get(en_task, ()))
                task_completed = any(f"完成任务: {name}" in log for name in names)
                if task_completed or any(f"{name} 任务跳过" in log for name in names):
                    if (
                        en_task == "DepotMaintain"
                        and self.task_dict.get(en_task)
                        and task_completed
                    ):
                        self._stock_depot_completed = True
                    self.task_dict[en_task] = False

            failed_names = _failed_maa_task_names(log)
            for name in (_MAA_AUTO_CULTIVATE_TASK_NAME, _MAA_DATA_UPDATE_TASK_NAME):
                if name not in self.task_dict:
                    continue
                task_failed = any(
                    failed == name or failed.startswith((f"{name} (", f"{name} #"))
                    for failed in failed_names
                )
                if task_failed:
                    self._failed_extra_tasks.add(name)
                elif f"完成任务: {name}" in log or f"{name} 任务跳过" in log:
                    self.task_dict[name] = False
                    self._failed_extra_tasks.discard(name)

            if self.task_dict.get("EventDepotMaintain"):
                event_names = ("活动关均衡理智", "活动库存保持")
                # 新版 MAA 收尾明确列出失败的队列名称；识别链或某条 #N 成功
                # 不能覆盖同阶段其他计划的失败，不读取原生 TaskId 等内部状态。
                error_summaries = re.findall(
                    r"任务已结束，以下任务出现错误[:：]\s*([^\r\n]+)", log
                )
                event_failed = any(
                    name in error_summary
                    for name in event_names
                    for error_summary in error_summaries
                ) or any(
                    re.search(
                        rf"任务出错:\s*{re.escape(name)}(?:\s+#\d+| \(仓库识别\))?\s*$",
                        log,
                        re.M,
                    )
                    for name in event_names
                )
                event_completed = re.search(
                    r"完成任务: (?:活动关均衡理智|活动库存保持)(?:\s+#\d+| \(仓库识别\))?\s*$",
                    log,
                    re.M,
                )
                # 旧版只有「部分失败」标题，无法归属失败阶段时仍允许重试。
                completion_known = completed_log or bool(error_summaries)
                if event_completed and not event_failed and completion_known:
                    # 库存充足时只有仓库识别，也由 MAA 收尾确认为整段完成。
                    self.task_dict["EventDepotMaintain"] = False
                    self._event_depot_completed = True
                elif not event_failed and any(
                    f"{name} 任务跳过" in log for name in event_names
                ):
                    # 来源时段跳过只结束本次尝试，下一次仍重新判断条件。
                    self.task_dict["EventDepotMaintain"] = False

            # 培养目标未完成不算整轮错误，不根据培养失败计数触发重试。
            # 最终失败结论以 MAA 收尾日志为准，已完成的仓库识别或刷关子链不能覆盖它。
            if (
                failed_log
                or any(self.task_dict.values())
                or any(
                    log.rfind(f"任务出错: {name}") > log.rfind(f"完成任务: {name}")
                    for name in re.findall(r"任务出错: ([^\r\n]+)", log)
                )
            ):
                await self.cur_user_log.set_state(status="MAA 部分任务执行失败")
            else:
                await self.cur_user_log.set_state(status="Success!")

        elif "请 ｢检查连接设置｣ → ｢尝试重启模拟器与 ADB｣ → ｢重启电脑｣" in log:
            await self.cur_user_log.set_state(status="MAA 的 ADB 连接异常")
        elif "未检测到任何模拟器" in log:
            await self.cur_user_log.set_state(status="MAA 未检测到任何模拟器")
        elif _MAA_OUT_OF_MEMORY_MARKER in log:
            await self.cur_user_log.set_state(
                status="MAA 因内存不足停止，请关闭部分程序后重试"
            )
        elif "已停止" in log:
            await self.cur_user_log.set_state(status="MAA 在完成任务前中止")
        elif (
            "MaaAssistantArknights GUI exited" in log
            or not await self.maa_process_manager.is_running()
        ):
            await self.cur_user_log.set_state(status="MAA 在完成任务前退出")
        elif self.is_log_stalled(
            latest_time,
            minutes=max(
                getattr(self.script_config.Run, MAA_MODE_TIME_LIMIT_BOOK[self.phase]),
                self.script_config.Run.GameUpdateTimeLimit,
            )
            if self.if_game_hot_update
            else getattr(self.script_config.Run, MAA_MODE_TIME_LIMIT_BOOK[self.phase]),
        ):
            await self.cur_user_log.set_state(status="MAA 进程超时")
        else:
            await self.cur_user_log.set_state(status="MAA 正常运行中")

        logger.debug(f"MAA 日志分析结果: {self.cur_user_log.status}")
        if self.cur_user_log.status != "MAA 正常运行中":
            logger.info(f"MAA 任务结果: {self.cur_user_log.status}, 日志锁已释放")
            self.wait_event.set()

    async def _take_failure_shot(self) -> Path | None:
        """通过失败截图会话复用或生成本次失败画面，避免重复采集。"""
        return await self._failure_capture.run(self._capture_failure_shot)

    async def _capture_failure_shot(self) -> Path | None:
        """取一张失败现场画面：上游 debug/interface 图优先，adb 补截兜底。

        上游图是 MAA 在任务链失败/停止瞬间落的缓存帧；登录链失败、进程超时
        这些上游不落图的场景走 adb 补截当前画面（截到的可能是 MAA 结束动作
        退游戏后的桌面）。诊断旁路：任何失败只记日志并返回 ``None``。
        """

        assert self.maa_root_path is not None
        shot = await asyncio.to_thread(
            collect_maa_failure_image,
            self.maa_root_path,
            not_before=self.log_start_time,
        )
        if shot is not None:
            return shot
        # ModAVD 实例：截图走 ``modavd adb``（ModAVD 的私有 server，它的 adb 不能落到 5037）。
        host_adb = await resolve_host_adb(self)
        image = await capture_current_image(
            capture_adb=self.capture_adb,
            adb_path=self.emulator_manager.get_adb_path(),
            adb_address=self.emulator_info.adb_address
            if self.emulator_info is not None
            else "",
            png_reader=host_adb.screencap_png if host_adb is not None else None,
        )
        return await asyncio.to_thread(
            self._failure_capture.save, image, dir_name="maa-failure"
        )

    async def _business_final(self):
        """在运行前检查通过后汇总日志与账号结果，完成进程、模拟器、失败截图及通知相关收尾。"""
        if self.check_result != "Pass":
            logger.info(f"MAA 检查未通过，跳过任务收尾: {self.check_result}")
            return

        self.history.begin_user_history_capture(
            self.script_info,
            self.cur_user_item,
            failed=bool(self.cur_user_item.logs)
            and not (self.run_book["Annihilation"] and self.run_book["Routine"])
            and not self.stopped_manually,
        )

        started_at = time.monotonic()

        logger.info("MAA 收尾: 停止日志监控")
        await self.maa_log_monitor.stop()
        logger.info("MAA 收尾: 停止 MAA 进程")
        # 任务收尾时 MAA 多半还在跑任务, 发关闭消息会弹「确定要退出吗」把收尾卡住;
        # 需要等 MAA 自己退出去落盘的只有配置会话 (ScriptConfig)。
        await self.maa_process_manager.kill()
        await process.kill_process(self.maa_exe_path)
        self._remember_pending_update()
        logger.info(f"MAA 收尾: 结束残留 MAA 进程: {self.maa_exe_path}")

        # 中止可能绕过每轮结束后的刷新；正常已刷新时标记为空，不重复请求。
        current_log = self.current_log_at(self.log_start_time)
        if current_log is not None and self.cur_user_config.Info.IfQuickConfig:
            self._collect_cultivate_archive(
                "".join(current_log.content), finalizing=True
            )
        await self._finish_cultivate_round()

        logger.info("MAA 收尾: 回写 MAA 配置")
        await agree_bilibili(self.maa_tasks_path, False)

        # 是否成功提前判定：ExitEmulator 模式随后就关闭模拟器，失败画面的
        # 补截必须赶在关模拟器之前
        if_success = self.run_book["Annihilation"] and self.run_book["Routine"]

        # 失败画面：失败尝试路径已在关模拟器前留下的优先；否则现在取
        # （如总时限中止，模拟器此时仍开着）。成功轮不取，手动停止只保留已有图。
        failure_shot: Path | None = self._failure_shot
        if not if_success and failure_shot is None and not self.stopped_manually:
            failure_shot = await self._take_failure_shot()

        if self.script_config.Run.TaskTransitionMethod == "ExitEmulator":
            logger.info("账号任务结束, 关闭模拟器")
            await close_emulator(self)

        await self.run_user_scripts_after(self.cur_user_config)

        if self.maa_root_path is not None:
            await asyncio.to_thread(
                restore_depot_cache,
                self.maa_root_path,
                depot_cache_snapshot_dir(self.script_info.script_id),
            )

        history_records = []
        if_six_star = False
        for t, log_item in self.iter_logs():
            if log_item.status == "MAA 正常运行中" or (
                self.stopped_manually
                and log_item is self.cur_user_log
                and log_item.status == "未开始监看日志"
            ):
                await log_item.set_state(status="任务被用户手动中止")
            data: dict[str, HistoryStatistic] = {}
            try:
                parsed, six_star = log_statistics.parse_maa_statistics(log_item.content)
                if_six_star = if_six_star or six_star
                data = {
                    key: HistoryCounterStatistic(value=value)
                    if key in {"recruit_statistics", "drop_statistics"}
                    else HistorySnapshotStatistic(value=value)
                    for key, value in parsed.items()
                }
            except Exception as error:
                diagnostic = f"MAA 统计解析失败：{error}"
                logger.opt(exception=True).warning(diagnostic)
                await log_item.append_content(f"\n{diagnostic}\n")
            history_records.append(
                HistoryWrite(
                    time=t.astimezone(_utils_constants.UTC4),
                    username=self.cur_user_item.name,
                    script_name=self.script_info.name,
                    status="success"
                    if log_item.status == "Success!"
                    else "cancelled"
                    if self.stopped_manually
                    and log_item is self.cur_user_log
                    and log_item.status == "任务被用户手动中止"
                    else "error",
                    message=log_item.status,
                    logs="".join(log_item.content),
                    data=data,
                )
            )

        statistics: dict[str, object] = {
            key: value.value
            for key, value in aggregate_data(
                [
                    HistoryAggregationItem(time=record.time, data=record.data)
                    for record in history_records
                ]
            ).data.items()
        }
        statistics["user_info"] = self.cur_user_item.name
        statistics["start_time"] = self.user_start_time.strftime("%Y-%m-%d %H:%M:%S")
        statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        statistics["maa_result"] = (
            "代理任务全部完成"
            if (self.run_book["Annihilation"] and self.run_book["Routine"])
            else self.cur_user_item.result
        )
        # 培养步骤以 MAA 成功日志为准，练度刷新延迟也不漏掉本轮的阶段结果。
        cultivate_progress = log_statistics.parse_cultivate_progress(
            line for _, log_item in self.iter_logs() for line in log_item.content
        )
        progress_lines = list(cultivate_progress)
        if (
            self.cur_user_config.Info.IfQuickConfig
            and self.cur_user_config.Task.IfCultivate
        ):
            try:
                raw_targets = json.loads(self.cur_user_config.Task.CultivateTargets)
            except (TypeError, ValueError):
                raw_targets = None
            if isinstance(raw_targets, list):
                targets = parse_cultivate_targets(raw_targets)
                remaining = sum(len(target.goals) for target in targets)
                suffix = (
                    "（练度未同步）"
                    if targets and not self._cultivate_progress_synced
                    else ""
                )
                progress_lines.append(
                    f"剩余：{len(targets)} 名干员，{remaining} 个目标{suffix}"
                )
        if progress_lines:
            statistics["cultivate_progress"] = "；".join(progress_lines)
        # 本轮有干员达成养成目标时随统计报告告知账号（目标消失可查）
        if self._cultivate_achievement_summary:
            statistics["cultivate_achievement"] = "、".join(
                self._cultivate_achievement_summary
            )

        success_symbol = "√" if if_success else "X"

        # 任务被中止时，只要日志中已经完成过体力任务，也应发送掉落统计；
        # 失败轮取到现场画面时同样发送——登录失败这类开局即败的轮次，用户
        # 只能靠图看到卡在哪，不能因为没跑过体力就把现场吞掉。
        images: list[NotificationImage] = []
        if not if_success and failure_shot is not None:
            try:
                loaded = await prepare_screenshot_images(
                    [(self.cur_user_item.name, failure_shot)],
                    # ID 带用户序号：manager 汇总拼接各账号的图，前缀不唯一
                    # 会让邮件里同名 cid 互相覆盖
                    image_id_prefix=f"maa{self.script_info.current_index}",
                )
                images = [image for _, image in loaded]
                # 模板的「失败截图」块在这里组装；payload 走展平后的 images
                statistics["screenshots"] = screenshot_entries(loaded)
                # 供 manager 汇总「代理结果」收集（MaaFW 同款）
                self.report_image_pairs = list(loaded)
            except Exception as e:
                logger.warning(f"失败画面转码失败，通知不带图: {e}")
                images = []
        if self.run_book["Annihilation"] and self.run_book["Routine"]:
            if (
                self.cur_user_config.Data.ProxyTimes == 0
                and self.cur_user_config.Info.RemainedDay != -1
            ):
                self.cur_user_config.Info.RemainedDay = (
                    self.cur_user_config.Info.RemainedDay - 1
                )
                await self.cur_user_config.commit()
            self.cur_user_config.Data.ProxyTimes = (
                self.cur_user_config.Data.ProxyTimes + 1
            )
            await self.cur_user_config.commit()

            await self.cur_user_item.set_state(status="完成")
            logger.success(f"账号 {self.cur_user_uid} 的自动代理任务已完成")
        else:
            logger.warning(f"账号 {self.cur_user_uid} 的自动代理任务未完成")
            await self.cur_user_item.set_state(status="异常")

        if failure_shot is not None and history_records:
            # 原图还供上游诊断与问题包使用，归档只复制，不接管源文件。
            history_records[-1].attachments.append(
                HistoryAttachmentInput(
                    path=failure_shot,
                    kind="image",
                    role="failure_screenshot",
                    display_name="失败截图",
                    archive_mode="copy",
                )
            )
        await self.history.save_user_history(
            history_records,
            script=self.script_info,
            user=self.cur_user_item,
            log_warning=logger.opt(exception=True).warning,
        )

        if self.run_book["Annihilation"] and self.run_book["Routine"]:
            await Notify.send_notice(
                LocalNotice(
                    title="成功完成一个自动代理任务！",
                    message=f"已完成账号 {self.cur_user_item.name} 的自动代理任务",
                    ticker=f"已完成 {self.cur_user_item.name} 的自动代理任务",
                    duration_seconds=3,
                )
            )

        should_send_statistics = (
            if_success
            or bool(images)
            or bool(cultivate_progress)
            or _has_completed_sanity_task([item for _, item in self.iter_logs()])
        )
        if should_send_statistics:
            try:
                await Notify.push_statistics_report(
                    payload=_format_maa.build_statistics_payload(
                        title=f"{datetime.now().strftime('%m-%d')} |{success_symbol}|  {self.cur_user_item.name} 的自动代理统计报告",
                        message=statistics,
                        images=images,
                    ),
                    user_config=self.cur_user_config,
                    task_info=self.task_info,
                )
            except Exception as e:
                logger.opt(exception=True).warning(f"推送统计通知时出现异常: {e}")
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error", message=f"推送统计通知时出现异常: {e}"
                    ),
                )

        # 六星通知独立处理，避免单个通知异常阻断掉落统计。
        if if_six_star:
            try:
                logger.info(
                    f"开始推送通知, 模式: 公招六星, 标题: 喜报: 账号 {self.cur_user_item.name} 公招出六星啦！"
                )
                await Notify.dispatch_task_notification(
                    _format_maa.build_recruitment_payload(
                        title=f"喜报: 账号 {self.cur_user_item.name} 公招出六星啦！",
                        message={"user_name": self.cur_user_item.name},
                    ),
                    Notify.recruitment_targets(self.cur_user_config),
                    task_info=self.task_info,
                )
            except Exception as e:
                logger.opt(exception=True).warning(f"推送六星通知时出现异常: {e}")
                await Publisher.send(
                    id=self.task_info.task_id,
                    type=protocol.TASK_NOTICE,
                    data=WSTaskNoticeData(
                        level="error", message=f"推送六星通知时出现异常: {e}"
                    ),
                )

        logger.info(f"MAA 任务收尾完成 - 用时: {time.monotonic() - started_at:.3f}秒")

    async def on_crash(self, exc: BaseException):
        """将账号节点标记为异常，记录错误并向当前任务前端发布错误提示。"""
        await self.cur_user_item.set_state(status="异常")
        logger.opt(exception=True).warning(f"自动代理任务出现异常: {exc}")
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(
                level="error", message=f"自动代理任务出现异常: {exc}"
            ),
        )

    async def main_logic(self):
        """在账号硬时限内执行专项主流程，并在退出时提交账号、用户运行节点及日志记录。"""
        try:
            async with asyncio.timeout(self.script_config.Run.HardTimeLimit * 60):
                await self._business_main()
        finally:
            await self.cur_user_config.commit()
            await self.user_info.commit()
            for record in self.user_info.logs.values():
                await record.commit()

    async def finish(self):
        """已建立日志观察上下文时恢复本次运行临时调整的仓库识别配置。"""
        if hasattr(self, "maa_log_monitor"):
            await self._restore_depot_after_run()
