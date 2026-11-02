#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License
#   as published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""ZZZ-OD 自动代理：按配置来源与账号切换方式拉起一条龙并监控日志。

MAS 用户与 zzz-od 实例槽**固定绑定**：每个用户绑定一个槽（绑定下标存于
用户配置 Info.SlotIdx，首次运行/配置时按全局查重分配），槽目录持久保留
（用户经「在一条龙内配置」维护配队等复杂配置）；注册表不持久写入——
运行/会话窗口内以**合成注册表视图**临时替换 one_dragon.yml（仅本脚本
用户槽），窗口结束恢复原生内容，zzz-od 原生世界零 MAS 痕迹。

新槽一律落在 ``MAS_SLOT_BASE``（1001）起的高位段：一条龙的「新增实例」只在
自己的注册表里找最小空号、**不扫盘**，而 MAS 槽刻意不进注册表，低号段随时会
被它抢走并覆盖。绑定号已经被原生实例占走时走**撞号兜底**——残留内容先存底
进回收池、该槽的 MAS 备份池跟着改绑到新号，目录本身不动（已归原生实例）。
自动回收另受**槽分配台账**约束（只收归属用户已不存在的号），手动清理不受限；
同安装另有 ZzzOd 脚本在跑时整体跳过（它在用槽的绑定号要到 ``final_task`` 才
回写，此时回收会拆掉它的现场）。

- independent 来源 + 「多实例切换」（脚本级下拉，不推荐）：把全部启用用户的配置
  注入各自绑定槽（备份 → 注入 → 清非保留类应用的运行记录），随后
  ``--onedragon --instance {slot1,slot2,...}`` 一次性运行多账号一条龙——
  zzz-od 内部依次执行各实例并自行切换游戏账号；结果按各实例槽运行记录
  diff 归属到对应用户。
- 注入模式 + 「单实例切换」（脚本级下拉，默认，推荐）：逐用户独立会话——注入
  该用户配置到其绑定槽 → 单实例运行（仅运行当前，无槽间切换）→ 跑完关闭
  → 下一个用户。失败域隔离，某用户失败只重启该用户。
- 注入模式 + 「MAS切换」（暂未开放）：MAS 侧 OCR 操控游戏完成账号切换后交
  一条龙运行。
- 原生来源：不注入不建视图，直接 ``--onedragon`` 裸跑，完全尊重 zzz-od 自己
  的 instance_run / 活跃实例 / 多账号运行设置；结果按全部实例运行记录聚合
  diff 判定。

启动器（OneDragon-RuntimeLauncher / OneDragon-Launcher）CLI 一条龙为进程内
同步运行、结束即退出；一条龙按任务粒度失败不中断（GroupApplication 继续跑
下一个），日志监控负责实时展示、终态标志行识别（成功/失败即结束等待）与
致命错误 / 超时兜底。
"""

import asyncio
import json
import re
import time
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from app.config import ConfigCollection
from app.core import Config, Notify, Publisher
from app.core.history import aggregate_data
from app.core.notify.task_content import (
    build_user_statistics_payload as build_user_statistics_payload,
)
from app.core.ws import protocol
from app.models.config import ZzzOdConfig, ZzzOdUserConfig
from app.models.notification import LocalNotice
from app.models.schema import HistoryAggregationItem, HistoryWrite, WSTaskNoticeData
from app.models.task import LogRecord, ScriptItem, UserItem
from app.services import System
from app.task.base import ScriptAutoProxyBase
from app.task.proxy_helpers import (
    CONFIG_BASE_INDEPENDENT,
    CONFIG_BASE_NATIVE,
    CONFIG_BASE_SHARED,
    kill_pids_by_name,
    push_dispatch_log,
    read_config_base,
    split_args,
    user_uses_native_base,
)
from app.utils import (
    BASE_SOURCE_LABELS,
    UTC4,
    LogMonitor,
    ProcessInfo,
    ProcessManager,
    get_logger,
    is_process_running,
    log_box,
)
from app.utils.common.log import sources as log_source

from . import push_log as _push_log
from .launchers import (
    _ZZZOD_LAUNCHER_BOOK,
    _other_launcher_label,
    find_launcher_exe,
    resolve_launcher,
)
from .slots import collect_used_slot_idxs, ensure_user_slot, recycle_unbound_slots
from .tools import (
    INSTANCE_RUN_ALL,
    INSTANCE_RUN_CURRENT,
    PERSISTENT_RUN_RECORD_APPS,
    RUN_STATUS_FAILED,
    RUN_STATUS_NOT_RUN,
    RUN_STATUS_RUNNING,
    RUN_STATUS_SUCCESS,
    archive_mas_config_backup,
    archive_onedragon_backup,
    backup_instance,
    clear_run_records,
    collect_mas_user_info,
    diff_run_records,
    find_active_instance,
    instance_dir,
    instance_run_is_all,
    launch_args_patch,
    list_app_catalog,
    list_instances,
    read_game_account,
    read_native_after_done,
    restore_instance,
    restore_instance_view,
    restore_plan_run_times,
    restore_run_record_files,
    snapshot_plan_run_times,
    snapshot_run_record_files,
    snapshot_run_records,
    user_field_patch,
    write_app_group,
    write_game,
    write_game_account,
    write_instance_view,
)

logger = get_logger("ZZZ-OD 自动代理")

# 游戏本体进程名：MAS 侧关闭游戏按进程名结束（游戏由启动器拉起，可能不在
# 启动器进程树内，进程管理器跟踪不到）
_ZZZ_GAME_PROCESS = "ZenlessZoneZero.exe"


# 启动器成功启动的证据：出现 zzz-od 应用层运行上下文即视为已启动（两种启动器的
# 一条龙运行日志都汇聚 .log/log.txt；启动器自身未起来时该文件无任何应用层条目）
_ZZZOD_LAUNCH_STARTED_MARKERS = (
    "[application_launcher.py",
    "[one_dragon_context.py",
    "[application_factory_manager.py",
)

# zzz-od 统一日志（log_utils，按日期滚动，当天固定为 log.txt）
_ZZZOD_REL_LOG = Path(".log") / "log.txt"

# 日志行格式：[HH:mm:ss.SSS] [file.py NN] [LEVEL]: message
_ZZZOD_LOG_TIME_START = 1
_ZZZOD_LOG_TIME_END = 13
_ZZZOD_LOG_TIME_FORMAT = "%H:%M:%S.%f"

# ── 内置失败关键词（zzz-od 原生日志，不向用户暴露配置）──────────────
#   「未找到有效的实例」—— --instance 无效后 ApplicationLauncher 直接退出；
#   「请先结束其他运行中的功能 再启动」—— 上一次运行未完全退出（残影进程）；
#   「运行应用 one_dragon 失败」—— 一条龙 app 执行抛异常（application_run_context）；
#   「指令[ 一条龙 ] 执行失败」—— 一条龙应用终态失败（如游戏窗口未就绪，此时可能
#     尚未写任何运行记录，不拦截会把空 diff 误判为「今日任务均已完成」）。
_ZZZOD_BUILTIN_FATAL: tuple[tuple[str, str], ...] = (
    ("未找到有效的实例", "ZZZ-OD 未找到有效的实例, 请检查账号配置"),
    ("请先结束其他运行中的功能 再启动", "ZZZ-OD 有运行中的功能未结束, 请稍后重试"),
    ("运行应用 one_dragon 失败", "ZZZ-OD 一条龙运行出现异常"),
    ("指令[ 一条龙 ] 执行失败", "ZZZ-OD 一条龙运行失败"),
)

# 应用最终失败触发有界重跑，内部操作的失败不直接判负；重试保留运行记录，
# 已完成任务的跳过与周期进度均交给 zzz-od 自己维护。白名单应用
# （_RETRY_FUTILE_APPS）的失败不触发重试，详见其注释。

# 一条龙应用终态成功标志（每次运行恰好出现一次）：出现即代表全部实例执行
# 完毕（对齐 ok-ww 的成功标志行行为）。出现后立即结束日志等待，不等启动器
# 进程退出（LogMonitor 静默期回调节流最长延迟 60s）；终态成败仍由 main_task
# 的运行记录 diff 统一判定——组内个别任务失败不影响该标志出现。
_ZZZOD_ONE_DRAGON_SUCCESS = "指令[ 一条龙 ] 执行成功"


# 汇总信号应用：上游「通知」应用在本轮存在失败任务时会把自己标失败
# （通知消息本身已发出，fire-and-forget），从失败名单剔除避免误导
_SUMMARY_APP_IDS = frozenset({"notify"})

# 「重试无意义」应用白名单（2026-10 维护者决策，条目为应用中文名，prepare
# 时经应用目录解析为 app_id、失配在启动时告警）：这些应用的最终失败重试也不
# 会改变结果（如限时活动关闭后入口消失，上游 app 内部已重试多次），失败不再
# 因它们消耗重试轮次，也不拦其余应用的重试——仅当本轮失败的应用全部在白名单
# 内（没有可恢复对象）时才跳过剩余重试。上游尚无「活动已结束」等专门状态前
# 的调度域临时补位，上游补齐后移除。
_RETRY_FUTILE_APPS: frozenset[str] = frozenset({"丽都城募", "情报板"})


def _match_fatal(log: str) -> str | None:
    """扫描内置致命关键词，命中返回状态文案，否则 None（三处判定共用）。"""

    return next((msg for needle, msg in _ZZZOD_BUILTIN_FATAL if needle in log), None)


def _failed_apps(
    diffs: list,
    log: str,
    app_name_book: dict[str, str],
    *,
    slot_idx: int | None = None,
) -> list[str]:
    """按实例取应用最后一次结果；缺少应用日志时沿用运行记录差分。

    只识别目录中的应用终态及上游「应用已完成」，不把内部指令失败当成应用
    失败。日志可覆盖连续两轮同为失败、运行记录差分为空的情形。
    """

    failed = {
        app_id
        for app_id, _, new in diffs
        if new == RUN_STATUS_FAILED and app_id not in _SUMMARY_APP_IDS
    }
    app_ids = {
        name: app_id
        for app_id, name in app_name_book.items()
        if app_id not in _SUMMARY_APP_IDS
    }
    results: dict[tuple[int | None, str], bool] = {}
    current_slot = None
    for line in log.splitlines():
        segment = re.search(r"开始加载实例配置 (\d+)", line)
        if segment is not None:
            current_slot = int(segment.group(1))
        if slot_idx is not None and current_slot != slot_idx:
            continue
        terminal = re.search(r"指令\[ (.+?) \] 执行(成功|失败)", line)
        skipped = re.search(r"应用已完成 (.+?)\s*$", line)
        if terminal is not None:
            name = terminal.group(1)
            is_failed = terminal.group(2) == "失败"
        elif skipped is not None:
            name = skipped.group(1)
            is_failed = False
        else:
            continue
        app_id = app_ids.get(name)
        if app_id is not None:
            results[current_slot, app_id] = is_failed

    observed = {app_id for _, app_id in results}
    failed.difference_update(observed)
    failed.update(app_id for (_, app_id), is_failed in results.items() if is_failed)
    return sorted(failed)


def _failures_all_futile(
    failed_app_ids: list[str], futile_app_ids: frozenset[str]
) -> bool:
    """失败的应用是否全部命中「重试无意义」白名单（没有可恢复对象）。

    白名单应用的失败不触发重试，也不拦其余应用的重试；空失败名单（致命
    错误 / 超时等运行级失败，未做应用级判定）按可重试处理。
    """

    return bool(failed_app_ids) and all(
        app_id in futile_app_ids for app_id in failed_app_ids
    )


def parse_user_apps(user_config: ZzzOdUserConfig) -> list[dict]:
    """解析用户配置的一条龙任务编排（JSON），返回 enabled 项列表。

    Raises:
        ValueError: AppList 不是合法 JSON 或结构异常。
    """

    try:
        raw = json.loads(str(user_config.OneDragon.AppList or "[]"))
    except json.JSONDecodeError as e:
        raise ValueError("一条龙任务编排数据异常, 请重新编辑任务配置") from e
    if not isinstance(raw, list):
        raise ValueError("一条龙任务编排数据异常, 请重新编辑任务配置")
    return [item for item in raw if isinstance(item, dict) and item.get("enabled")]


def inject_user_fields(
    root: Path, slot_idx: int, user_config: ZzzOdUserConfig, apps: list[dict]
) -> None:
    """把 MAS 用户字段写入绑定槽（game_account patch + game.yml 启动参数 + 任务编排整表）。

    不清运行记录、不备份——配置会话（以本页配置为基线打开 GUI）与运行时
    注入（配合 clear_run_records）共用。
    """

    slot_dir = instance_dir(root, slot_idx)
    write_game_account(slot_dir, user_field_patch(user_config))
    write_game(slot_dir, launch_args_patch(user_config))
    write_app_group(slot_dir, apps)


def _snapshot_all_run_records(root: Path) -> dict[str, int]:
    """聚合全部实例的运行记录（原生态基准）：失败 > 运行中 > 成功 > 未跑。"""

    aggregated: dict[str, int] = {}
    for item in list_instances(root):
        for app_id, status in snapshot_run_records(
            root, int(item.get("idx", -1))
        ).items():
            prev = aggregated.get(app_id)
            if status == RUN_STATUS_RUNNING or prev == RUN_STATUS_RUNNING:
                aggregated[app_id] = RUN_STATUS_RUNNING
            elif status == RUN_STATUS_FAILED or prev == RUN_STATUS_FAILED:
                aggregated[app_id] = RUN_STATUS_FAILED
            elif status == RUN_STATUS_SUCCESS or prev == RUN_STATUS_SUCCESS:
                aggregated[app_id] = RUN_STATUS_SUCCESS
    return aggregated


def _judge_baseline(root: Path, idx: int) -> dict[str, int]:
    """本轮终判基准：注入后的运行记录快照，保留类应用一律按未跑计。

    保留类应用（:data:`PERSISTENT_RUN_RECORD_APPS`）的记录不在注入时清空，
    其上一轮终态会让「本轮有没有变化」的差分失真——连续两轮失败会因前后同为
    失败被判成没变化，失败明细与重试提示一起丢掉。基准里把这些应用归零，
    与 :func:`_judge_after` 的 after 侧归一配对使用。
    """

    records = snapshot_run_records(root, idx)
    for app_id in PERSISTENT_RUN_RECORD_APPS:
        if app_id in records:
            records[app_id] = RUN_STATUS_NOT_RUN
    return records


def _judge_after(
    root: Path, idx: int, pre_files: dict[str, bytes | None]
) -> dict[str, int]:
    """终判 after 侧：保留类应用仅当记录文件在本轮被上游写过才采信其状态。

    记录保留后，槽内残留上一周期的终态会产出幻影 diff——启动器未启动也会
    被判成功、启动器自动切换被禁用。以注入时的文件字节为基准：字节未变的
    记录本轮没被写过（上游每轮 update_status 都会改写 dt/run_time），按未跑
    计；注入时读取失败（值为 ``None``、状态未知）同样按未跑计——绝不采信
    可能是上一周期残留的终态。``pre_files`` 为空（注入时不存在任何保留类
    记录）时无需归一，直接返回真实快照。
    """

    records = snapshot_run_records(root, idx)
    if not pre_files:
        return records
    current = snapshot_run_record_files(root, idx)
    for app_id in PERSISTENT_RUN_RECORD_APPS:
        name = f"{app_id}.yml"
        if app_id not in records or name not in pre_files:
            continue
        pre = pre_files[name]
        if pre is None or pre == current.get(name):
            records[app_id] = RUN_STATUS_NOT_RUN
    return records


def _judge_all_skipped(log: str, diffs: list) -> bool:
    """本轮该槽无任何运行记录变化时，是否属「任务已全部完成、被上游整轮跳过」。

    判据是「整轮跑完」标志：一条龙走完所有实例才会落
    ``指令[ 一条龙 ] 执行成功``（见 :data:`_ZZZOD_ONE_DRAGON_SUCCESS`）。
    记录保留后，本周期已完成的槽会全程无记录变化，需要这条回落避免重试耗尽；
    但只有它成立时空 diff 才等价于「该实例的应用组把每个启用任务都按已完成
    跳过」——启动器起过、实例被加载过都发生在应用组之前，单独用它们判断会把
    「实例还没跑到就退出」误判成完成。
    """

    return not diffs and _ZZZOD_ONE_DRAGON_SUCCESS in log


class AutoProxyTask(ScriptAutoProxyBase[ZzzOdConfig, ZzzOdUserConfig]):
    """ZZZ-OD 自动代理：逐用户按三态来源拉起启动器 CLI 一条龙并监控"""

    # 取消时等 final_task 完整收尾（SRC/MaaFW 同款）：不设此 flag 时外层取消会
    # 立刻打断 shield 的 final_task，导致 kill_managed_process 没跑——取消任务后
    # zzz-od 启动器/一行龙本体仍继续运行
    wait_for_finalizer_on_cancel = True

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: ZzzOdConfig,
        user_config: ConfigCollection[ZzzOdUserConfig],
        users: list[UserItem] | None = None,
    ):
        super().__init__()
        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config
        # 本任务实际执行的用户子集（manager 按配置来源分派人）：None=全部用户。
        # 注入轮只含注入模式用户，原生裸跑轮只含原生来源用户——report 聚合仍用
        # script_info.user_list（同一批 UserItem 对象，状态互通）
        self._task_users = users if users is not None else self.script_info.user_list

        self.cur_user_item: UserItem = self._task_users[self.script_info.current_index]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config: ZzzOdUserConfig = self.user_config[self.cur_user_uid]
        # base 来源三态（shared/independent=本配置字段注入运行 / native=zzz-od 原生配置）
        self.base = read_config_base(self.cur_user_config)
        # 账号切换方式（脚本级下拉，仅注入模式生效）：
        # 多实例切换=多用户注入多实例槽一轮跑；单实例切换=逐用户独立会话
        self.account_switch = str(self.script_config.Game.AccountSwitch or "单实例切换")
        self.cur_user_log: LogRecord | None = None
        self.launcher_process_manager: ProcessManager | None = None
        # 「启用游戏配置 + 任务前启动游戏」时由 MAS 拉起游戏本体的进程管理器
        self.game_process_manager: ProcessManager | None = None
        self.game_exe_path: Path | None = None
        self.wait_event: asyncio.Event | None = None
        self.script_root_path: Path | None = None
        self.launcher_exe_path: Path | None = None
        # 当前使用的启动器标签（原始/集成）、本任务启动时的模式快照（运行中途
        # 改配置不影响本轮判定）与是否已切换过
        self._launcher_label: str | None = None
        self._launcher_mode = "自动"
        self._launcher_switched = False
        self.script_log_path: Path | None = None
        self.log_monitor: LogMonitor | None = None
        # log_box 采集会话（用户级「节点详情推送模式」关闭时不创建，prepare 按配置启停）
        self._log_source: log_source.LogSource | None = None
        self._log_pipeline: log_box.LogPipeline | None = None
        self._log_user: UserItem | None = None
        self._log_failed = False
        self._log_close_task: asyncio.Task[None] | None = None
        # 实例 idx → 账号名映射（原生来源=原生注册表快照；注入=绑定槽用户名），供后置
        # 处理器把「开始加载实例配置 N」段边界映射为账号归属
        self._idx_names: dict[int, str] = {}
        # 用户名 → UserItem（注入多实例切换的 sink 路由用；原生来源等无归属场景为空）
        self._push_user_book: dict[str, UserItem] = {}
        # 注入前账密守卫的告警（多账号一轮时剔除账密不全的用户），main_task 推调度台
        self._guard_warnings: list[str] = []
        # 注入现场（注入模式共用）：绑定槽 → 备份目录（None=槽目录为本运行新建）
        self._injected_slots: list[tuple[int, Path | None]] = []
        # 槽位归属与注入基准（多实例切换按槽归属用户；单注入模式只有一个槽）
        self._slot_users: dict[int, tuple[UserItem, ZzzOdUserConfig]] = {}
        self._slot_records_before: dict[int, dict[str, int]] = {}
        # 注入时保留类应用运行记录的字节快照（供 _judge_after 识别本轮写过的文件；
        # 读取失败的条目值为 None，表示状态未知）
        self._slot_record_files: dict[int, dict[str, bytes | None]] = {}
        self._multi_uids: set[str] = set()
        self._multi_succeeded: set[int] = set()
        self._multi_ran = False
        self._multi_run_status = ""
        self._history_users: dict[str, UserItem] = {}
        self._shutdown_after_success: bool = False
        self.run_book = False
        # app_id → 中文名（用于结果与推送日志展示）
        self._app_name_book: dict[str, str] = {}
        # 本轮应用级失败名单（_judge_final 写入；重试前判「重试无意义」用）
        self._failed_app_ids: list[str] = []
        # 白名单解析结果（app_id 集，prepare 经应用目录解析）
        self._futile_app_ids: frozenset[str] = frozenset()

    def _enabled_app_list(self) -> list[dict]:
        """当前用户的一条龙任务编排 enabled 项列表。"""

        return parse_user_apps(self.cur_user_config)

    def _is_multi_account(self) -> bool:
        """注入模式且账号切换方式为「多实例切换」时走多账号一轮合并运行。"""

        return (
            self.base == CONFIG_BASE_INDEPENDENT and self.account_switch == "多实例切换"
        )

    def _is_bare_run(self) -> bool:
        """原生来源裸跑（不注入，按全部原生实例运行记录聚合判定）。"""

        return self.base == CONFIG_BASE_NATIVE

    def _direct_run_targets(self, root: Path) -> list[dict]:
        """原生来源运行的目标实例列表（与上游 ``handle_init`` 判定同口径）。

        随原生 ``instance_run`` 而定：全部实例=所有参与运行（``active_in_od``）
        的实例，其余（含 null / 空串等非法值）=活跃实例——只有**键缺失**才按
        上游默认取「全部实例」（判定见 :func:`instance_run_is_all`）；目标为空
        时回落活跃实例（对齐上游 ``handle_init`` 对空参与列表的回落）。上游对
        「有参与实例但无活跃」会自行切到首个参与实例运行，因此目标非空即
        放行，不以有无活跃实例拦截。
        """

        if instance_run_is_all(root):
            targets = [
                item for item in list_instances(root) if item.get("active_in_od")
            ]
        else:
            targets = []
        if not targets:
            active = find_active_instance(root)
            targets = [active] if active is not None else []
        return targets

    def _direct_missing_game_paths(self, root: Path) -> list[str]:
        """原生来源运行目标实例中未配置游戏路径的实例名（空=全部可运行）。

        原生来源=原生裸跑、MAS 零注入，游戏路径只可能来自目标实例的
        ``game_account.yml``；缺失时一条龙会以「未配置游戏路径」整体失败，
        这里提前拦截并指明是哪个实例。读不动或条目结构异常的实例不误判
        为未配置，交由一条龙自身报错。
        """

        missing: list[str] = []
        for item in self._direct_run_targets(root):
            try:
                idx = int(item.get("idx", -1))
                if idx <= 0:
                    continue
                game_path = str(
                    read_game_account(instance_dir(root, idx)).get("game_path") or ""
                ).strip()
            except Exception:
                continue
            if not game_path:
                missing.append(str(item.get("name") or f"{idx:02d}"))
        return missing

    def _push_log_enabled(self) -> bool:
        """节点详情采集开关：触发用户或（多实例切换时）任一启用用户未关闭即采集。"""

        if self.cur_user_item.push_log_mode != "关闭":
            return True
        if not self._is_multi_account():
            return False
        return any(
            (
                str(
                    self.user_config[uuid.UUID(item.user_id)].Notify.PushLogMode
                    or "汇总"
                )
                != "关闭"
                for item in self._task_users
                if self.user_config[uuid.UUID(item.user_id)].Info.Status
            )
        )

    def _collect_inject_users(
        self,
    ) -> list[tuple[UserItem, ZzzOdUserConfig, list[dict]]]:
        """多实例切换的注入名单：启用且有任务编排的用户（按调度顺序）。

        逐用户施加跳过条件（剩余天数 / 今日代理次数上限 / 任务编排为空），
        命中的用户标记「跳过」不入列。原生来源用户绝不入列（原生来源=零注入，
        manager 本就不应分派，此处兜底防御）。多账号一轮时额外做账密守卫：
        任一用户缺账号或密码都会在槽间切换时失败并拖死整轮，缺失者标记
        「异常」剔除，告警写入调度台。
        """

        limit = int(self.script_config.Run.ProxyTimesLimit)
        candidates: list[tuple[UserItem, ZzzOdUserConfig, list[dict]]] = []
        for user_item in self._task_users:
            uid = uuid.UUID(user_item.user_id)
            cfg = self.user_config[uid]
            if not cfg.Info.Status:
                continue
            if user_uses_native_base(cfg):
                logger.warning(
                    f"用户 {user_item.name} 为原生来源配置, 不参与注入运行（原生裸跑由调度单独分派）"
                )
                continue
            if cfg.Info.RemainedDay == 0:
                user_item.status = "跳过"
                continue
            if limit != 0 and cfg.Data.ProxyTimes >= limit:
                user_item.status = "跳过"
                continue
            try:
                apps = parse_user_apps(cfg)
            except ValueError:
                user_item.status = "异常"
                continue
            if not apps:
                user_item.status = "跳过"
                continue
            candidates.append((user_item, cfg, apps))

        if len(candidates) > 1:
            # 多账号一轮需要槽间切换，账密不全的用户必然拖死整轮，先行剔除
            guarded: list[tuple[UserItem, ZzzOdUserConfig, list[dict]]] = []
            for user_item, cfg, apps in candidates:
                if (
                    str(cfg.Game.Account or "").strip()
                    and str(cfg.Game.Password or "").strip()
                ):
                    guarded.append((user_item, cfg, apps))
                    continue
                user_item.status = "异常"
                message = (
                    f"用户 {user_item.name} 缺少账号或密码, 多账号运行时无法完成"
                    f"账号切换, 已从本轮注入名单剔除"
                )
                logger.warning(message)
                self._guard_warnings.append(message)
            return guarded
        return candidates

    def _inject_user_config(
        self, slot_idx: int, user_config: ZzzOdUserConfig, apps: list[dict]
    ) -> None:
        """把用户配置字段生成 zzz-od YAML 写入实例槽（MaaEnd 式字段下发）。

        账号字段只覆盖 MAS 侧非空字段，槽内 game_account.yml 的其余字段
        （platform、自定义窗口标题等）原样保留；启动参数整组覆盖 game.yml；
        随后清空非保留类应用的运行记录让本次任务全部重跑（保留类应用承载
        上游周期进度，见 PERSISTENT_RUN_RECORD_APPS）。
        """

        inject_user_fields(self.script_root_path, slot_idx, user_config, apps)
        clear_run_records(self.script_root_path, slot_idx)

    async def _prepare_injection(
        self, users: list[tuple[UserItem, ZzzOdUserConfig, list[dict]]]
    ) -> None:
        """注入模式：合成注册表视图 + 各用户字段写入绑定槽。

        多实例切换=全部启用用户各注入各槽（多账号一次跑）；单实例切换=仅当前
        用户（逐用户循环）。槽目录持久保留（配队等复杂配置），运行内容由
        备份/恢复保证零痕迹；注册表以合成视图呈现（仅本脚本用户槽）。
        """

        backup_base = (
            Path.cwd() / "data" / self.script_info.script_id / "Temp" / "InstanceBackup"
        )
        # 闪退自愈：上次运行/会话若残留合成视图，先还原原生注册表
        restore_instance_view(self.script_root_path)
        # 归档点：一条龙原生配置快照（one_dragon.yml + 原生实例目录）——
        # 必须在 ensure_user_slot（可能注册新槽）与合成视图写入之前，
        # 捕获的是未被本次 MAS 操作触碰的原生状态；MAS 槽快照在下方循环内逐槽归档
        try:
            archive_onedragon_backup(self.script_root_path)
        except Exception as e:
            logger.opt(exception=True).warning(f"归档 ZZZ-OD 原生配置快照失败: {e}")
        # 孤儿槽回收：一条龙注册表里没有、也没有任何 ZzzOd 用户绑定的
        # config/NN 是「分配过、用户/脚本已删」的残留——GUI 看不见也删不掉，
        # 不收就永久占号。放在 ensure_user_slot 之前：腾出的号本轮即可复用；
        # 原生配置快照已归档在前，回收后仍可找回（整目录拷贝+删除，线程里跑）
        await asyncio.to_thread(
            recycle_unbound_slots,
            self.script_root_path,
            scripts=Config.ScriptConfig,
            exclude_script_id=self.script_info.script_id,
        )
        used_idxs = collect_used_slot_idxs(
            self.script_root_path,
            scripts=Config.ScriptConfig,
            exclude_uids={uuid.UUID(u.user_id) for u, _, _ in users},
        )

        for user_item, cfg, apps in users:
            slot = await ensure_user_slot(
                self.script_root_path,
                cfg,
                used_idxs,
                script_id=self.script_info.script_id,
                owner_uid=user_item.user_id,
            )
            backup_dir = backup_base / f"{slot:02d}"
            if instance_dir(self.script_root_path, slot).is_dir():
                backup_instance(self.script_root_path, slot, backup_dir)
                # 时间戳归档：MAS 用户槽快照（含配队等全部内容），供配置恢复
                # ——统一入口会先物化本页账号+编排进槽（账号/编排只存在
                # UserData，槽要注入才带上；直接快照会漏、恢复会清空本页字段）
                archive_mas_config_backup(
                    self.script_info.script_id,
                    slot,
                    instance_dir(self.script_root_path, slot),
                    cfg,
                    meta=collect_mas_user_info(cfg),
                )
                self._injected_slots.append((slot, backup_dir))
            else:
                self._injected_slots.append((slot, None))
            self._inject_user_config(slot, cfg, apps)
            self._slot_users[slot] = (user_item, cfg)
            self._slot_records_before[slot] = _judge_baseline(
                self.script_root_path, slot
            )
            self._slot_record_files[slot] = snapshot_run_record_files(
                self.script_root_path, slot
            )
            self._multi_uids.add(user_item.user_id)
            # 多实例切换共用一个 log_box：各用户的节点详情推送模式与归属
            # （sink 按「【用户名】」前缀路由，idx→用户名供后置处理器归属）
            user_item.push_log_mode = str(cfg.Notify.PushLogMode or "汇总")
            self._idx_names[slot] = str(cfg.Info.Name or "")
        self._push_user_book = {user_item.name: user_item for user_item, _, _ in users}

    def _write_view(self) -> None:
        """（重）写合成注册表视图：仅本脚本注入槽，活跃=首槽。

        每轮尝试前调用：一条龙切换会把活跃实例写回视图（one_dragon.yml 即
        合成视图本体），不重写的话重试会从上次停留的槽开始；单槽注入用
        「仅运行当前」，规避上游 wrap-around 对自己的无意义登出/登录切换。

        单槽（单实例切换）且该用户配置了账号时置 ``force_login_before_run``：
        进入游戏前强制按账密登录该用户的账号，避免沿用游戏里上一个用户
        （或原生）的登录态串号；未配置账号不置位（沿用登录态语义）。
        多槽（多实例切换）不置位——槽间切换由上游 switch_account 处理
        （switch=True 时进入游戏自动强制登录）。
        """

        slots = self._injected_slots
        force_login = False
        if len(slots) == 1:
            first_user = next(iter(self._slot_users.values()))[1]
            force_login = bool(str(first_user.Game.Account or "").strip())

        write_instance_view(
            self.script_root_path,
            [(slot, f"MAS-{self._slot_users[slot][1].Info.Name}") for slot, _ in slots],
            active_idx=slots[0][0],
            instance_run=INSTANCE_RUN_ALL if len(slots) > 1 else INSTANCE_RUN_CURRENT,
            force_login=force_login,
        )

    async def _reset_daily_proxy_count(self) -> None:
        """跨日重置：仅重置日期变化的用户（多实例切换下每个用户都判一次）。

        单独放在 check 入口而非 main_task 是为避免 main_task 的「仅重置触发用户」
        漏洞——非触发用户的 ProxyTimes/LastProxyDate 从不重置就会从第二天起
        永久触发 ProxyTimesLimit 上限被跳过。
        """

        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        for cfg in self.user_config.values():
            if cfg.Data.LastProxyDate.strftime("%Y-%m-%d") != self.curdate:
                cfg.Data.LastProxyDate = datetime.now(tz=UTC4)
                await cfg.commit()
                cfg.Data.ProxyTimes = 0
                await cfg.commit()

    async def check(self) -> str:
        # 跨日重置：必须在 ProxyTimesLimit 上限比较之前完成（对齐 ok-nte，
        # 避免 check 入口拿过期 ProxyTimes 误判为超限、永久跳过）
        await self._reset_daily_proxy_count()
        root = self.script_config.Info.RootPath
        if root is None or not root.is_dir():
            return "请设置绝区零一条龙安装目录"
        try:
            find_launcher_exe(root)
        except ValueError as e:
            return str(e)

        # base 来源三态：shared/independent=按该用户的 MAS 配置注入运行（shared=
        # 脚本级共享配置载体，仍落到该用户绑定槽）；native=原生裸跑零注入。
        if self.base not in (
            CONFIG_BASE_SHARED,
            CONFIG_BASE_INDEPENDENT,
            CONFIG_BASE_NATIVE,
        ):
            return f"不支持的配置来源: {self.base}"

        if self.base in (CONFIG_BASE_SHARED, CONFIG_BASE_INDEPENDENT):
            # 同脚本用户名唯一（绑定槽名与统计都依赖名字区分）
            names = [
                str(cfg.Info.Name or "").strip()
                for cfg in self.user_config.values()
                if cfg.Info.Status
            ]
            duplicates = sorted({n for n in names if names.count(n) > 1})
            if duplicates:
                return (
                    f"存在同名用户: {'、'.join(duplicates)}, 请为每个用户设置不同的名称"
                )
            if self._is_multi_account():
                # 多实例切换：cur_user 只是触发者，逐用户跳过条件在注入名单中施加
                if not self._collect_inject_users():
                    return "没有可注入的用户, 请确认用户已启用且任务配置非空"
            else:
                try:
                    if not self._enabled_app_list():
                        return "未启用任何一条龙任务, 请在用户配置中开启至少一个任务"
                except ValueError as e:
                    return str(e)
                if (
                    self.script_config.Run.ProxyTimesLimit != 0
                    and self.cur_user_config.Data.ProxyTimes
                    >= self.script_config.Run.ProxyTimesLimit
                ):
                    self.cur_user_item.status = "跳过"
                    return "今日代理次数已达上限, 跳过该用户"
                if self.cur_user_config.Info.RemainedDay == 0:
                    self.cur_user_item.status = "跳过"
                    return "用户剩余天数为 0, 跳过该用户"
        else:
            # 原生来源=原生裸跑零注入，运行前先自愈上次注入模式残留的合成视图
            # （只含 MAS 槽）：否则下面读到的是视图，会把 MAS 槽当运行目标、
            # 误报「未配置游戏路径」；无 sidecar 时为 no-op
            restore_instance_view(root)
            if not self._direct_run_targets(root):
                return "zzz-od 中没有可运行的实例, 请先在一条龙中创建账号"
            # 原生来源裸跑读原生实例配置，路径缺失时一条龙只会以「未配置游戏路径」
            # 失败，这里提前给出可读提示并指明实例
            missing = self._direct_missing_game_paths(root)
            if missing:
                return (
                    f"实例 {'、'.join(missing)} 未配置游戏路径, "
                    "请在一条龙「账户管理」中设置"
                )

        return "Pass"

    async def prepare(self):
        # 启动器是引导式进程（自更新/接力时会更换进程实例）：跟踪的旧进程退出
        # 时按目标信息改绑后继实例，避免把接力误判成一条龙运行结束、提前收尾
        self.launcher_process_manager = ProcessManager(reseek_target=True)
        # 「启用游戏配置 + 任务前启动游戏」时由 MAS 拉起游戏本体（对齐 ok-nte）
        self.game_process_manager = (
            ProcessManager()
            if self.script_config.Game.Enabled
            and self.script_config.Game.LaunchBeforeTask
            else None
        )
        game_path = str(self.script_config.Game.Path or "").strip()
        self.game_exe_path = Path(game_path) if game_path else None
        self.wait_event = asyncio.Event()

        self.user_start_time = datetime.now()
        script_root_path = self.script_config.Info.RootPath
        if script_root_path is None:
            raise ValueError("RootPath未配置，请检查路径设置")
        self.script_root_path = script_root_path
        self.launcher_exe_path = find_launcher_exe(self.script_root_path)
        self.script_log_path = self.script_root_path / _ZZZOD_REL_LOG
        self.log_monitor = LogMonitor(
            (_ZZZOD_LOG_TIME_START, _ZZZOD_LOG_TIME_END),
            _ZZZOD_LOG_TIME_FORMAT,
            self.check_log,
        )

        self._app_name_book = {
            item["app_id"]: item["app_name"]
            for item in list_app_catalog(self.script_root_path)
        }
        if not self._app_name_book:
            raise ValueError("未能加载一条龙任务目录，请检查安装文件是否完整")

        # 白名单条目按应用目录解析为 app_id：上游更名后条目失配在启动时告警，
        # 而不是在重试判定里静默失配（失配条目按可重试处理）
        self._futile_app_ids = frozenset(
            app_id
            for app_id, name in self._app_name_book.items()
            if name in _RETRY_FUTILE_APPS
        )
        missing = _RETRY_FUTILE_APPS - set(self._app_name_book.values())
        if missing:
            logger.warning(
                f"「重试无意义」白名单条目 {'、'.join(sorted(missing))} "
                f"不在应用目录中, 可能已更名, 失配条目按可重试处理"
            )

        # 用户级节点详情推送模式（build_user_result_text 按此渲染）
        self.cur_user_item.push_log_mode = str(
            self.cur_user_config.Notify.PushLogMode or "汇总"
        )
        # 目录和账号映射会在运行期变化：收尾时再固定快照，不能在 prepare 提前捕获。
        # 触发用户关闭但其他启用用户需要详情时仍采集，保留原有多账号开关语义。
        self._prepare_log_details(
            self.script_log_path,
            mode=self.cur_user_item.push_log_mode,
            enabled=self._push_log_enabled(),
            rotated_name=f"{self.script_log_path.name}.%Y-%m-%d",
        )
        self.run_book = False

    def _resolve_log_file_path(self) -> Path:
        """一条龙统一日志路径（zzz-od 按日期滚动，当天固定为 log.txt）。

        LogMonitor 每轮循环重新解析，跨日后自动跟随当日文件。
        """

        return self.script_root_path / _ZZZOD_REL_LOG

    async def main_task(self):
        await self.prepare()
        # 跨日重置：check 入口已对全部用户完成日期+ProxyTimes 同步，main_task
        # 无需再就地重置触发用户
        self.cur_user_item.status = "运行"
        # 任务前脚本每用户一次，先于全部重试；后置脚本由收尾阶段成对执行
        await self.run_user_scripts_before()

        run_limit = int(self.script_config.Run.RunTimesLimit)
        try:
            # 注入现场（注入模式）：绑定槽备份 → 由用户配置字段生成 YAML 写入槽 →
            # 临时切 instance_run。注入只做一次——重试不清运行记录，
            # 让 zzz-od 按记录跳过已完成任务。
            if self.base == CONFIG_BASE_NATIVE:
                records_before = _snapshot_all_run_records(self.script_root_path)
                # 账号归属映射：原生注册表快照（idx → 实例名），供 log_box
                # 后置处理器把「开始加载实例配置 N」段边界映射为账号名
                self._idx_names = {
                    int(item.get("idx", -1)): str(item.get("name") or "")
                    for item in list_instances(self.script_root_path)
                    if isinstance(item, dict)
                }
                # 原生来源=MAS 零注入零干涉（快速配置已封锁，见 ZzzOdUserConfig.load），
                # 完全尊重 zzz-od 自己的 instance_run / 活跃实例 / 多账号运行设置
                launcher_args = ["--onedragon"]
            else:
                if self._is_multi_account():
                    # 多实例切换：全部启用用户 → 各自绑定槽，一条龙多账号一次跑
                    inject_users = self._collect_inject_users()
                    if not inject_users:
                        raise RuntimeError(
                            "没有可注入的用户, 请确认用户已启用且任务配置非空"
                        )
                    for warning in self._guard_warnings:
                        await self._push_dispatch_log(warning)
                        await Publisher.send(
                            id=self.task_info.task_id,
                            type=protocol.TASK_NOTICE,
                            data=WSTaskNoticeData(level="error", message=warning),
                        )
                else:
                    # 单实例切换：仅当前用户（逐用户循环）
                    inject_users = [
                        (
                            self.cur_user_item,
                            self.cur_user_config,
                            self._enabled_app_list(),
                        )
                    ]
                await self._prepare_injection(inject_users)
                # 多槽一轮靠一条龙内部切换（--instance 列表）；单槽用
                # 「仅运行当前」，规避上游 wrap-around 的无意义登出/登录
                launcher_args = ["--onedragon"]
                if len(self._injected_slots) > 1:
                    launcher_args += [
                        "--instance",
                        ",".join(str(slot) for slot, _ in self._injected_slots),
                    ]
            # 上游 CLI 不读原生 after_done 配置，关闭游戏通过参数下发；关机
            # 延后到 MAS 确认最终成功并完成收尾，避免首轮部分失败就启动倒计时，
            # 导致补跑中途关机。延时固定 60 秒，与一条龙 GUI 一致。取值随来源：
            # native=原生 after_done（与原生配置/GUI 显示一致），shared/independent
            # =该用户的 MAS 字段（经配置会话双向联动与 GUI 保持一致）。多实例
            # 切换整轮共用触发者的值。与 MAS 收尾的 CloseOnFinish
            # （kill_managed_process）相互独立，同时配置会各执行一次，无害。
            if self.base == CONFIG_BASE_NATIVE:
                after_done = read_native_after_done(self.script_root_path)
            else:
                after_done = str(self.cur_user_config.OneDragon.AfterDone or "关闭游戏")
            if after_done == "关闭游戏":
                launcher_args.append("--close-game")
            self._shutdown_after_success = after_done == "关机"

            # 任务结束后关闭游戏由 MAS 侧兜底执行（见 kill_managed_process），
            # 不依赖一条龙 --close-game：手动停止调度时 MAS 也能一并关游戏

            # 启动器选择：原生来源/用户统一按配置——自动=优先上次成功项，原始/集成=固定
            # 对应项（未安装回退可用项）；原生来源默认「自动」时行为等同原强绑定默认顺序
            self._launcher_mode = str(self.cur_user_config.Info.LauncherMode or "自动")
            self.launcher_exe_path, self._launcher_label = resolve_launcher(
                self.script_root_path,
                self._launcher_mode,
                str(self.cur_user_config.Data.LauncherLastGood or ""),
            )

            for i in range(run_limit):
                if self.run_book:
                    break
                logger.info(
                    f"用户 {self.cur_user_item.name} - 尝试次数: {i + 1}/{run_limit}"
                )
                # 多实例切换时触发者可能不在注入名单（如无任务被跳过），
                # 不能把它的「跳过」状态覆盖为「运行」
                if (
                    not self._is_multi_account()
                    or self.cur_user_item.user_id in self._multi_uids
                ):
                    self.cur_user_item.status = "运行"
                self.log_start_time = datetime.now().astimezone()
                self.cur_user_item.add_log_record(self.log_start_time, LogRecord())
                self.cur_user_log = self.cur_user_item.log_record[self.log_start_time]
                self._failed_app_ids = []
                self.script_info.log = ""

                # 启用游戏配置 + 任务前启动游戏：由 MAS 拉起游戏本体后再跑一条龙
                # （对齐 ok-ww/ok-nte；游戏已在运行时跳过，避免重复启动）
                if self.game_process_manager is not None:
                    try:
                        await self._mas_launch_game_before_task()
                    except Exception as e:
                        await self._push_dispatch_log(f"游戏启动失败: {e}")
                        self.cur_user_log.status = f"游戏启动失败: {e}"
                        self.cur_user_log.content = [f"游戏启动失败: {e}"]
                        self.script_info.log = self.cur_user_log.status
                        logger.opt(exception=True).warning(
                            f"用户 {self.cur_user_item.name} - MAS 启动游戏失败: {e}"
                        )
                        await self.kill_managed_process(
                            kill_game=self._mas_should_close_game()
                        )
                        try:
                            await Notify.send_notice(
                                LocalNotice(
                                    title="ZZZ-OD 自动代理出现异常！",
                                    message=f"用户 {self.cur_user_item.name} 游戏启动失败",
                                    ticker=f"{self.cur_user_item.name}的自动代理出现异常",
                                    duration_seconds=3,
                                )
                            )
                        except Exception:
                            pass
                        if i + 1 < run_limit:
                            self.script_info.log += (
                                f"\n将在稍后重试 ({i + 1}/{run_limit})"
                            )
                            await asyncio.sleep(10)
                        else:
                            self.cur_user_item.status = "异常"
                        continue

                base_label = BASE_SOURCE_LABELS.get(self.base, self.base)
                run_desc = (
                    f"{base_label}配置·多实例切换·{len(self._injected_slots)}个用户"
                    if self._is_multi_account()
                    else f"{base_label}配置"
                )
                if self._injected_slots:
                    # 一条龙切换会把活跃实例写回合成视图，每轮重写保证重试
                    # 从首槽开始、instance_run 语义正确（原生来源裸跑无视图）
                    self._write_view()
                await self._push_dispatch_log(f"启动 ZZZ-OD 一条龙（{run_desc}）")
                logger.info(
                    f"启动 ZZZ-OD 启动器: {self.launcher_exe_path} "
                    f"{' '.join(launcher_args)}"
                )

                await self.launcher_process_manager.open_process(
                    self.launcher_exe_path,
                    *launcher_args,
                    target_process=ProcessInfo(
                        name=self.launcher_exe_path.name,
                        exe=str(self.launcher_exe_path),
                        cmdline=None,
                    ),
                    elevated=True,
                )

                await asyncio.sleep(1)
                await self.log_monitor.start_monitor_file(
                    self._resolve_log_file_path, self.log_start_time
                )

                self.wait_event.clear()
                await self.wait_event.wait()
                await self.log_monitor.stop()

                # 进程退出后按运行记录 diff 判定终态
                log = "".join(self.cur_user_log.content)
                if self._is_multi_account():
                    await self._judge_multi(log)
                elif self._is_bare_run():
                    records_after = _snapshot_all_run_records(self.script_root_path)
                    self._judge_final(records_before, records_after, log)
                else:
                    slot0 = self._injected_slots[0][0]
                    records_before = self._slot_records_before[slot0]
                    records_after = _judge_after(
                        self.script_root_path,
                        slot0,
                        self._slot_record_files.get(slot0, {}),
                    )
                    self._judge_final(records_before, records_after, log)

                if self.run_book:
                    # 终态成功（判定器设置）：统一为框架成功契约「Success!」
                    # （原生来源跳过场景的可读说明已由判定器写入 script_info.log）
                    if (
                        self._launcher_label is not None
                        and self._launcher_mode == "自动"
                    ):
                        # 自动模式：把本次成功使用的启动器记忆为下次优先项
                        self.cur_user_config.Data.LauncherLastGood = (
                            type(self.cur_user_config.Data)
                            .model_validate({"LauncherLastGood": self._launcher_label})
                            .LauncherLastGood
                        )
                        await self.cur_user_config.commit()
                    self.script_info.log = (
                        self.script_info.log or "检测到 ZZZ-OD 已完成任务"
                    )
                    break

                # 自动模式：启动器未能启动（无应用层日志且运行记录无变化）时，
                # 自动切换到另一启动器并占用下一轮重试。切换会先改写
                # launcher_exe_path，中止残留进程必须用切换前的旧路径显式传入
                # （如卡在「按回车键退出」的错误提示），否则下一轮 open_process
                # 会因进程管理器仍被占用而抛「无法同时管理多个进程」，切换永远
                # 不会真正发生
                stale_launcher_path = self.launcher_exe_path
                if await self._maybe_switch_launcher(log):
                    await self.kill_managed_process(exe_path=stale_launcher_path)
                    continue

                failure_reason = (
                    self._multi_run_status
                    if self._multi_ran
                    else self.cur_user_log.status
                )
                logger.warning(
                    f"用户 {self.cur_user_item.name} - ZZZ-OD 代理异常: "
                    f"{failure_reason}"
                )
                self.script_info.log = f"{failure_reason}\n正在中止相关程序"
                await self.kill_managed_process(kill_game=self._mas_should_close_game())
                try:
                    await Notify.send_notice(
                        LocalNotice(
                            title="ZZZ-OD 自动代理出现异常！",
                            message=f"用户 {self.cur_user_item.name} 的自动代理出现一次异常",
                            ticker=f"{self.cur_user_item.name}的自动代理出现异常",
                            duration_seconds=3,
                        )
                    )
                except Exception:
                    pass
                if i + 1 < run_limit:
                    if self._all_failures_futile(log):
                        futile_names = "、".join(
                            self._app_display_name(app_id)
                            for app_id in self._failed_app_ids
                        )
                        self.script_info.log += f"\n失败的应用均无重试价值（{futile_names}），已跳过剩余重试"
                        logger.info(
                            f"用户 {self.cur_user_item.name} - "
                            f"失败应用均无重试价值({futile_names}), 跳过剩余重试"
                        )
                        await self._push_dispatch_log(
                            f"失败的应用均无重试价值（{futile_names}），跳过剩余重试"
                        )
                        break
                    self.script_info.log += f"\n将在稍后重试 ({i + 1}/{run_limit})"
                    await asyncio.sleep(10)
        finally:
            # 无论成败/异常，注入现场立即恢复（MAS 不留痕迹，zzz-od 原生配置零接触）
            await self._restore_injection()

    def _app_display_name(self, app_id: str) -> str:
        """app_id 的中文展示名；目录未收录时回退 app_id。"""

        return self._app_name_book.get(app_id, app_id)

    def _judge_final(self, records_before: dict, records_after: dict, log: str) -> None:
        """进程退出后的终态判定（优先级：check_log 已标记的终态 > 致命日志 >
        失败任务 > 成功任务 > 无变化）。"""

        # check_log 已把超时/异常/致命态写入 cur_user_log.status 并 need_stop；
        # 该值对 main_task 的最终结果判定具有最高优先级（避免被无 diff 的
        # 「今日任务均已完成」覆盖成 run_book=True 而绕过重试）。
        # 「Success!」（check_log 成功标志）和「ZZZ-OD 正常运行中/空」继续走
        # 后续 diff 路径，由运行记录与致命日志统一判定。
        if self.cur_user_log.status not in (
            "ZZZ-OD 正常运行中",
            "",
            "Success!",
        ):
            self.run_book = False
            if self.cur_user_item.status not in ("异常", "跳过"):
                self.cur_user_item.status = "异常"
            return

        log_status = "ZZZ-OD 正常运行中"
        user_status: str | None = None

        fatal = _match_fatal(log)
        if fatal is not None:
            log_status = fatal
            user_status = "异常"
        else:
            diffs = diff_run_records(records_before, records_after)
            failed_apps = _failed_apps(diffs, log, self._app_name_book)
            self._failed_app_ids = failed_apps
            if failed_apps:
                failed_names = [
                    self._app_display_name(app_id) for app_id in failed_apps
                ]
                log_status = "ZZZ-OD 部分任务执行失败: " + "、".join(failed_names)
                user_status = "异常"
                self.script_info.log = log_status
            elif any(new == RUN_STATUS_SUCCESS for _, _, new in diffs):
                log_status = "Success!"
                user_status = "完成"
                self.script_info.log = "检测到 ZZZ-OD 已完成任务"
            elif _ZZZOD_ONE_DRAGON_SUCCESS in log:
                # 记录无变化但出现「整轮跑完」标志：原生态=今日任务均已完成
                # （zzz-od 启动后按记录跳过全部任务，应用组执行完仍打标志）。
                # 与 _judge_all_skipped 同判据：启动证据（框架初始化日志）发生
                # 在应用组之前，不算完成证据——启动器进程被提前误判结束时日志
                # 里只有它们，当成完成会整轮空跑。结果向框架成功契约 Success!
                # 归一，可读说明放到 script_info.log
                log_status = "Success!"
                user_status = "完成"
                self.script_info.log = "今日任务均已完成"
            elif self._launch_evidence(log, False):
                # 有启动证据（框架初始化日志）但无记录变化、无整轮完成标志：
                # 一条龙启动了却没跑完就退出（启动器接力换进程间隙被误判结束、
                # 框架早退等），判失败走重试
                log_status = "ZZZ-OD 一条龙未完成即退出"
                user_status = "异常"
            else:
                # 记录无变化且无任何启动证据：启动器未能真正拉起一条龙
                # （缺依赖早退等），判失败走重试/启动器切换，不得报成功
                log_status = "启动器未能启动一条龙"
                user_status = "异常"

        self.cur_user_log.status = log_status
        # 仅成功或上游确认已完成的任务走成功分支，应用失败交给 main_task 重试。
        self.run_book = user_status == "完成"
        if user_status is not None:
            self.cur_user_item.status = user_status

    def _all_failures_futile(self, log: str) -> bool:
        """本轮失败是否已无重试价值：整轮正常走完且失败应用全部命中白名单。

        白名单应用的失败不触发重试，也不拦其余应用的重试；仅注入模式单实例
        会话启用——独立基座的多实例切换与原生裸跑一轮覆盖多个用户或实例
        （共享基座本就走既有单槽路径），个别应用的确定性失败不应剥夺其余
        目标的补跑机会。以「指令[ 一条龙 ] 执行成功」确认整轮走完：启动器
        提前退出时未跑到的应用不在失败名单里，缺这条证据按可重试处理，
        守住未尝试应用的补跑机会。
        """

        if self._is_multi_account() or self._is_bare_run():
            return False
        if _ZZZOD_ONE_DRAGON_SUCCESS not in log:
            return False
        return _failures_all_futile(self._failed_app_ids, self._futile_app_ids)

    def _launch_evidence(self, log: str, records_changed: bool) -> bool:
        """启动器是否已成功启动：出现应用层运行上下文日志或运行记录有变化即视为已启动。

        两种启动器的一条龙运行日志都汇聚 .log/log.txt；启动器自身未能启动
        （exe 缺失环境、同步失败早退等）时该文件没有任何应用层条目。
        """

        return records_changed or any(
            marker in log for marker in _ZZZOD_LAUNCH_STARTED_MARKERS
        )

    async def _maybe_switch_launcher(self, log: str) -> bool:
        """自动模式：判定启动器未能启动且另一启动器可用时，切换后占用下一轮重试。

        返回 True 表示已切换（调用方 continue，切换本身消耗一轮重试额度）；
        非自动 / 已切换过 / 无另一启动器 / 已有启动证据时不切换。
        """

        if self._launcher_mode != "自动":
            return False
        if self._launcher_switched or self._launcher_label is None:
            return False

        records_changed = False
        if self._injected_slots:
            slot0 = self._injected_slots[0][0]
            records_changed = bool(
                diff_run_records(
                    self._slot_records_before.get(slot0, {}),
                    _judge_after(
                        self.script_root_path,
                        slot0,
                        self._slot_record_files.get(slot0, {}),
                    ),
                )
            )
        if self._launch_evidence(log, records_changed):
            return False

        other = _other_launcher_label(self.script_root_path, self._launcher_label)
        if other is None:
            return False

        self._launcher_label = other
        self.launcher_exe_path = self.script_root_path / _ZZZOD_LAUNCHER_BOOK[other]
        self._launcher_switched = True
        logger.warning(f"检测到 {other}启动器未能启动，已切换为另一启动器重试")
        return True

    async def _judge_multi(self, log: str) -> None:
        """多实例切换：按各实例槽运行记录 diff 归属每个用户的结果。

        check_log 已标记的运行级终态（超时等）优先于运行记录 diff——收尾
        阶段卡死超时即使各槽已写出成功记录也不能判成功。致命日志次之：
        整轮异常时未完成的用户一律标记异常。整轮结果独立控制重试，
        用户日志保留各自结论；任一用户未完成则进入
        重试（zzz-od 按运行记录跳过已完成任务）。
        """

        # check_log 已把超时/异常态写入 cur_user_log.status：本轮按运行失败
        # 处理，各参与用户一并标记异常（与 _judge_final 的早退守卫同源）
        runtime_failed = self.cur_user_log.status not in (
            "ZZZ-OD 正常运行中",
            "",
            "Success!",
        )
        runtime_status = "" if not runtime_failed else self.cur_user_log.status
        fatal = None if runtime_failed else _match_fatal(log)
        all_ok = True

        for slot, (user_item, cfg) in self._slot_users.items():
            self._history_users[user_item.user_id] = user_item
            before = self._slot_records_before.get(slot, {})
            after = _judge_after(
                self.script_root_path, slot, self._slot_record_files.get(slot, {})
            )
            diffs = diff_run_records(before, after)
            failed_apps = _failed_apps(diffs, log, self._app_name_book, slot_idx=slot)
            success = any(new == RUN_STATUS_SUCCESS for _, _, new in diffs)
            # 记录保留后，本周期已全部完成的用户整轮被跳过、diff 为空，需要
            # 回落判完成（详见 _judge_all_skipped：以「整轮跑完」为判据，
            # 不用启动器/实例加载证据，那两者都发生在应用组之前）
            all_skipped = _judge_all_skipped(log, diffs)
            ok = (
                fatal is None
                and not runtime_failed
                and not failed_apps
                and (success or all_skipped)
            )
            all_ok = all_ok and ok

            user_item.status = "完成" if ok else "异常"
            # 每个参与用户写一行终态 log_record：result 行不再显示「未开始
            # 运行」而节点有内容的矛盾。get-or-create：cur_user 的条目由
            # main_task 创建且 check_log 正在向其写 content，不能替换对象
            record = (
                self.cur_user_log if user_item is self.cur_user_item else LogRecord()
            )
            if record is not self.cur_user_log:
                user_item.add_log_record(self.log_start_time, record)
            if ok:
                record_status = "Success!"
            elif runtime_failed:
                record_status = runtime_status
            elif fatal is not None:
                record_status = fatal
            else:
                failed_names = "、".join(
                    self._app_display_name(app_id) for app_id in failed_apps
                )
                record_status = "ZZZ-OD 部分任务执行失败" + (
                    f": {failed_names}" if failed_names else ""
                )
            record.status = record_status
            if record is not self.cur_user_log:
                record.content = list(self.cur_user_log.content)
            # 节点详情由 log_box 统一采集（final_task 收尾时按账号路由）；
            # 每轮同步最终状态，成功计数在整个补跑期间每个用户只增加一次。
            await self._persist_multi_user_result(
                cfg, ok, slot in self._multi_succeeded
            )
            if ok:
                self._multi_succeeded.add(slot)

        if runtime_failed:
            self._multi_run_status = runtime_status
            if self.cur_user_item.user_id in self._multi_uids:
                self.cur_user_item.status = "异常"
        elif fatal is not None:
            self._multi_run_status = fatal
            if self.cur_user_item.user_id in self._multi_uids:
                self.cur_user_item.status = "异常"
        elif all_ok:
            self._multi_run_status = "Success!"
            self.script_info.log = "检测到 ZZZ-OD 已完成任务"
        else:
            failed_users = "、".join(
                user_item.name
                for user_item, _ in self._slot_users.values()
                if user_item.status != "完成"
            )
            self._multi_run_status = f"ZZZ-OD 部分用户执行失败: {failed_users}"
            self.script_info.log = self._multi_run_status

        if self.cur_user_item.user_id not in self._multi_uids:
            # 非参与用户只承担本次启动与进度展示，其日志不作为用户历史保存。
            self.cur_user_log.status = self._multi_run_status

        self.run_book = all_ok
        self._multi_ran = True

    async def _apply_proxy_success(self, cfg: ZzzOdUserConfig) -> None:
        """代理成功的数据写回三步（单实例与多实例路径共用）：
        首次代理扣剩余天数 → 累计次数 → 落「成功」状态。"""

        if cfg.Data.ProxyTimes == 0 and cfg.Info.RemainedDay != -1:
            cfg.Info.RemainedDay = cfg.Info.RemainedDay - 1
            await cfg.commit()
        cfg.Data.ProxyTimes = cfg.Data.ProxyTimes + 1
        await cfg.commit()
        cfg.Data.LastProxyStatus = "成功"
        await cfg.commit()

    async def _persist_multi_user_result(
        self, cfg: ZzzOdUserConfig, ok: bool, succeeded_before: bool
    ) -> None:
        """多实例切换：逐用户写回代理数据（对齐 _persist_user_run_result 语义）。

        每轮同步成败状态，首次成功才累计次数，避免其他账号失败导致的重跑
        重复计次；后续失败仍需如实落盘。
        """

        if ok:
            if succeeded_before:
                cfg.Data.LastProxyStatus = "成功"
                await cfg.commit()
            else:
                await self._apply_proxy_success(cfg)
        else:
            cfg.Data.LastProxyStatus = "失败"
            await cfg.commit()

    async def _push_dispatch_log(self, line: str) -> None:
        """向调度台追加流程日志（赋值 script_info.log 会触发 WebSocket 推送）。"""

        await push_dispatch_log(self.script_info, line)

    async def _restore_injection(self) -> None:
        """恢复注入现场（注入模式接管过时生效；幂等，恢复一次后置空）。

        先还原合成视图（原生注册表回来，含原生 instance_run），再逐槽恢复
        备份；槽目录一律保留（配队等复杂配置持久供配置会话维护）。
        运行产物不随注入现场回滚——计划进度（体力计划/恶名狩猎计划的
        「已运行次数」）与保留类应用的运行记录（周挑战剩余次数、每日/每周
        计划次数等周期进度）都是恢复前取快照、恢复后原样写回。
        """

        restore_instance_view(self.script_root_path)
        slots, self._injected_slots = self._injected_slots, []
        slot_owner_items = {
            slot: user_item for slot, (user_item, _) in self._slot_users.items()
        }
        self._slot_users = {}
        self._slot_records_before = {}
        self._slot_record_files = {}
        self._multi_uids = set()
        self._multi_succeeded = set()
        if not slots:
            return
        failed: list[tuple[int, str]] = []
        for slot, backup_dir in slots:
            if backup_dir is None or not backup_dir.is_dir():
                continue
            # 逐槽隔离：单槽失败不阻断其它槽恢复，避免一个坏槽让全部槽留着
            # MAS 注入内容。快照读取本身已容错（失败按无快照处理）
            try:
                # 一条龙运行中会把计划进度写回槽内 per-app YAML、把周期进度写进
                # 运行记录，整目录恢复会连它们一起回滚；先快照再恢复，随后回写
                plan_run_times = snapshot_plan_run_times(self.script_root_path, slot)
                record_files = snapshot_run_record_files(self.script_root_path, slot)
                restore_instance(self.script_root_path, slot, backup_dir)
                restore_plan_run_times(self.script_root_path, slot, plan_run_times)
                restore_run_record_files(self.script_root_path, slot, record_files)
            except Exception as e:  # noqa: BLE001 - 单槽失败隔离，继续恢复其余槽
                logger.opt(exception=True).warning(
                    f"恢复 ZZZ-OD 槽 {slot} 注入现场失败: {e}"
                )
                failed.append((slot, str(e)))
        if failed:
            # 配置未完整恢复时保留现场，不能因实际运行用户已完成就自动关机。
            self._shutdown_after_success = False
            # 失败槽里留着 MAS 注入内容：只标该槽对应的用户，不牵连已恢复成功的槽
            for slot, _ in failed:
                user_item = slot_owner_items.get(slot) or self.cur_user_item
                user_item.status = "异常"
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="error",
                    message=(
                        "恢复 ZZZ-OD 注入现场失败，原生配置可能残留 MAS 内容: "
                        + "；".join(f"槽 {slot}: {reason}" for slot, reason in failed)
                    ),
                ),
            )

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """按内置日志监控运行；致命错误与超时立即终止，进程退出触发统一终判。"""

        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log_first_line = log[:-4000].count("\n") + 1
        self.script_info.log = log[-4000:]

        log_status = "ZZZ-OD 正常运行中"
        user_item_status: str | None = None
        need_stop = False

        fatal = _match_fatal(log)
        if fatal is not None:
            log_status = fatal
            user_item_status = "异常"
            need_stop = True
        else:
            if _ZZZOD_ONE_DRAGON_SUCCESS in log:
                # 一条龙应用执行完毕即结束等待（成功标志行，对齐 ok-ww）；
                # 终态成败由 main_task 的运行记录 diff 统一判定
                log_status = "Success!"
                need_stop = True
            elif not await self.launcher_process_manager.is_running():
                # 启动器进程退出 = 一条龙运行结束（正常路径也如此），
                # 终态成败由 main_task 的运行记录 diff 统一判定
                need_stop = True
            elif self.is_log_stalled(
                latest_time, minutes=self.script_config.Run.RunTimeLimit
            ):
                log_status = "ZZZ-OD 运行超时"
                user_item_status = "异常"
                need_stop = True

        self.cur_user_log.status = log_status
        if user_item_status is not None and (
            not self._is_multi_account()
            or self.cur_user_item.user_id in self._multi_uids
        ):
            self.cur_user_item.status = user_item_status

        logger.debug(f"ZZZ-OD 日志分析结果: {self.cur_user_log.status}")
        if need_stop:
            logger.info(f"ZZZ-OD 任务结果: {self.cur_user_log.status}, 日志锁已释放")
            self.wait_event.set()

    async def final_task(self):
        if self._multi_ran:
            for user in self._history_users.values():
                self.task_info.begin_user_history_capture(
                    self.script_info,
                    user,
                    failed=user.status == "异常" and not self.stopped_manually,
                )
        else:
            self.task_info.begin_user_history_capture(
                self.script_info,
                self.cur_user_item,
                failed=bool(self.cur_user_item.log_record)
                and not self.run_book
                and not self.stopped_manually,
            )

        # 结束时先清理进程与监控（正常结束/失败/超时/手动中止都走这里——
        # wait_for_finalizer_on_cancel 保证手动停止也会完整收尾）
        if self.log_monitor is not None:
            with suppress(Exception):
                await self.log_monitor.stop()
        await self.kill_managed_process(kill_game=self._mas_should_close_game())
        await self._restore_injection()

        # box 在宿主固定动态映射，后台归并后回到宿主按账号交付；
        # 返回前节点已就位，manager 与调度台继续使用同一份用户结果。
        await self._close_log_details()

        # 写入历史记录（对齐 General/SRC/MaaEnd/Okww/BetterGI 行为）
        await self._persist_user_run_result()

        await self.run_user_scripts_after()

        history_records = []
        for t, log_item in self.cur_user_item.iter_history_logs():
            if log_item.status == "ZZZ-OD 正常运行中" or (
                self.stopped_manually
                and log_item is self.cur_user_log
                and log_item.status == "未开始监看日志"
            ):
                log_item.status = "任务被用户手动中止"

            was_cancelled = (
                self.stopped_manually
                and log_item is self.cur_user_log
                and log_item.status == "任务被用户手动中止"
            )
            if len(log_item.content) == 0:
                log_item.content = ["未捕获到任何日志内容"]
                # 未判定（进程异常退出/被中止）才标未捕获；已有终态判定时
                # 保留判定状态（判定依据是运行记录 diff，不依赖日志内容）
                if log_item.status in ("未开始监看日志", "ZZZ-OD 正常运行中"):
                    log_item.status = "未捕获到日志"

            history_records.append(
                HistoryWrite(
                    time=t.astimezone(UTC4),
                    username=self.cur_user_item.name,
                    script_name=self.script_info.name,
                    status=(
                        "success"
                        if log_item.status == "Success!"
                        else "cancelled"
                        if was_cancelled
                        else "error"
                    ),
                    message=log_item.status,
                    logs="".join(log_item.content),
                )
            )

        if not self._multi_ran or self.cur_user_item.user_id in self._history_users:
            if history_records:
                await self.task_info.save_user_history(
                    history_records,
                    script=self.script_info,
                    user=self.cur_user_item,
                    log_warning=logger.opt(exception=True).warning,
                )
        # 一次上游运行可同时执行多个实例，各用户沿用自己已确认的每轮结论。
        for user in self._history_users.values():
            if user is self.cur_user_item:
                continue
            records = [
                HistoryWrite(
                    time=started_at.astimezone(UTC4),
                    username=user.name,
                    script_name=self.script_info.name,
                    status="success" if item.status == "Success!" else "error",
                    message=item.status,
                    logs="".join(item.content),
                )
                for started_at, item in user.iter_history_logs()
            ]
            if records:
                await self.task_info.save_user_history(
                    records,
                    script=self.script_info,
                    user=user,
                    log_warning=logger.opt(exception=True).warning,
                )

        if history_records:
            try:
                statistics = {
                    key: value.value
                    for key, value in aggregate_data(
                        [
                            HistoryAggregationItem(time=record.time, data=record.data)
                            for record in history_records
                        ]
                    ).data.items()
                }
                statistics["user_info"] = self.cur_user_item.name
                start_time = getattr(self, "user_start_time", datetime.now())
                statistics["start_time"] = start_time.strftime("%Y-%m-%d %H:%M:%S")
                statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if not self.run_book:
                    user_result = self.cur_user_item.result
                else:
                    user_result = "代理任务全部完成"
                statistics["user_result"] = user_result
                success_symbol = "√" if self.run_book else "X"
                await Notify.push_statistics_report(
                    payload=build_user_statistics_payload(
                        title=f"{datetime.now().strftime('%m-%d')} |{success_symbol}|  {self.cur_user_item.name} 的 ZZZ-OD 自动代理统计报告",
                        message=statistics,
                    ),
                    user_config=self.cur_user_config,
                    task_info=self.task_info,
                )
            except Exception as e:
                # 失败不再静默：既记 ERROR 日志，也推到调度台实时日志
                await self._push_dispatch_log(f"推送用户统计通知失败: {e}")
                logger.opt(exception=True).error(
                    f"推送 ZZZ-OD 用户统计通知时出现异常: {e}"
                )

        # 多实例触发者可能被正常跳过，整轮是否成功以实际参与用户的结果为准。
        if self._shutdown_after_success and self.run_book:
            shutdown_error = ""
            try:
                process = await asyncio.create_subprocess_exec(
                    "shutdown", "/s", "/t", "60"
                )
                if await process.wait() != 0:
                    shutdown_error = "任务已完成，但未能安排自动关机，请检查系统权限"
            except OSError as e:
                shutdown_error = f"任务已完成，但未能安排自动关机: {e}"
            if shutdown_error:
                logger.error(shutdown_error)
                await self._push_dispatch_log(shutdown_error)
            else:
                await self._push_dispatch_log("一条龙任务已完成，60 秒后关机")

    async def _persist_user_run_result(self) -> None:
        # 多实例切换：各用户的数据已在 _judge_multi 逐用户写回，避免重复计数
        if self._multi_ran:
            return

        if self.run_book:
            await self._apply_proxy_success(self.cur_user_config)
            self.cur_user_item.status = "完成"
            logger.success(f"用户 {self.cur_user_uid} 的 ZZZ-OD 自动代理任务已完成")
        else:
            self.cur_user_config.Data.LastProxyStatus = "失败"
            await self.cur_user_config.commit()
            if self.cur_user_item.status != "完成":
                self.cur_user_item.status = "异常"

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        if self.cur_user_log is not None:
            self.cur_user_log.status = f"ZZZ-OD 运行异常: {e}"
        logger.opt(exception=True).warning(f"ZZZ-OD 自动代理任务出现异常: {e}")
        if self.wait_event is not None:
            self.wait_event.set()
        with suppress(Exception):
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="error", message=f"ZZZ-OD 自动代理任务出现异常: {e}"
                ),
            )
        with suppress(Exception):
            await self.kill_managed_process(kill_game=self._mas_should_close_game())
        with suppress(Exception):
            await self._restore_injection()
        with suppress(Exception):
            await self._persist_user_run_result()

        # 推送通知（复用 Notify）
        try:
            if (
                self.cur_user_log is not None
                and self.cur_user_log.status
                and self.cur_user_log.status != "Success!"
            ):
                await Notify.send_notice(
                    LocalNotice(
                        title="ZZZ-OD 运行异常",
                        message=f"用户 {self.cur_user_item.name}：{self.cur_user_log.status}",
                        ticker="异常",
                        duration_seconds=3,
                    )
                )
        except Exception:
            pass

    async def kill_managed_process(
        self, kill_game: bool = False, exe_path: Path | None = None
    ) -> None:
        """中止 ZZZ-OD 启动器进程；kill_game 为真时由 MAS 结束游戏进程。

        游戏由启动器拉起、可能不在启动器进程树内（进程管理器跟踪不到），
        按进程名结束——手动停止调度时同样收尾游戏，不依赖一条龙 --close-game。
        exe_path 显式指定按路径兜底结束的目标，默认当前 launcher_exe_path；
        切换启动器后旧进程仍在时，必须传切换前的旧路径。
        """

        if self.launcher_process_manager is not None:
            try:
                await self.launcher_process_manager.kill()
            except Exception as e:
                logger.opt(exception=True).warning(
                    f"通过进程管理器中止 ZZZ-OD 进程失败: {e}"
                )
        fallback_path = exe_path if exe_path is not None else self.launcher_exe_path
        if fallback_path is not None:
            try:
                await System.kill_process(fallback_path)
            except Exception as e:
                logger.opt(exception=True).warning(f"中止 ZZZ-OD 主进程失败: {e}")
        if kill_game:
            await self._kill_game_process()

    def _mas_should_close_game(self) -> bool:
        """收尾/中止时由 MAS 结束游戏（任务结束后关闭游戏=是）。"""

        return bool(self.script_config.Game.CloseOnFinish)

    async def _mas_launch_game_before_task(self) -> None:
        """MAS 接管启动游戏本体（启用游戏配置 + 任务前启动游戏时调用）。

        一条龙自身也会拉起游戏，但 MAS 先把游戏开好可跳过一条龙内的启动
        等待；检测到游戏进程已在运行时直接复用，不重复启动。
        """

        if not isinstance(self.game_process_manager, ProcessManager):
            return
        await self._push_dispatch_log(f"正在检查游戏进程 ({_ZZZ_GAME_PROCESS})...")
        if is_process_running(_ZZZ_GAME_PROCESS):
            logger.info("检测到游戏本体进程已在运行，跳过由 MAS 重复启动游戏")
            await self._push_dispatch_log("检测到游戏已在运行，跳过启动")
            await self._note_launch_arguments_skipped()
            return
        if self.game_exe_path is None:
            raise RuntimeError(
                "未配置游戏路径，请在脚本配置的游戏配置中选择游戏本体（ZenlessZoneZero.exe）"
            )
        await self._push_dispatch_log("正在由 MAS 启动游戏...")
        await self.game_process_manager.open_process(
            self.game_exe_path, *split_args(self.script_config.Game.Arguments)
        )
        wait_time = max(int(self.script_config.Game.WaitTime or 0), 0)
        if wait_time:
            await self._push_dispatch_log(f"等待游戏启动（{wait_time} 秒）...")
            await asyncio.sleep(wait_time)
        await self._push_dispatch_log("游戏启动完成")

    async def _note_launch_arguments_skipped(self) -> None:
        """游戏已在运行时不会重复启动，配了启动参数的用户要知道这轮没生效。"""

        arguments = str(self.script_config.Game.Arguments or "").strip()
        if arguments:
            message = f"检测到游戏已在运行，本轮不会应用启动参数（{arguments}）"
            logger.info(message)
            await self._push_dispatch_log(message)

    async def _kill_game_process(self) -> None:
        """按进程名结束游戏本体（对齐 ok-nte 的 MAS 侧关闭）。"""

        try:
            # 全进程扫描放到线程里，不阻塞事件循环
            failed = await kill_pids_by_name(_ZZZ_GAME_PROCESS)
            if failed:
                message = f"有 {failed} 个绝区零游戏进程未能结束，请人工确认关闭"
                logger.warning(message)
                await self._push_dispatch_log(message)
        except Exception as e:
            logger.opt(exception=True).warning(f"关闭游戏进程失败: {e}")

    def _prepare_log_details(
        self, path: Path, *, mode: str, enabled: bool, rotated_name: str | None
    ) -> None:
        """本专项固定来源与用户；读取和交付时机由自身生命周期控制。"""
        self._log_user = self.cur_user_item
        self._log_user.push_log_mode = mode
        self._log_source = None
        self._log_pipeline = None
        self._log_close_task = None
        self._log_failed = False
        if not enabled:
            return
        try:
            pipeline = log_box.LogPipeline()

            for rule in _push_log.ZZZOD_PUSH_RULES:
                pipeline.add_rule(*rule)

            source = log_source.LogSource(
                path, start_from_end=True, rotated_name=rotated_name
            )
            source.open()
            self._log_source = source
            self._log_pipeline = pipeline
        except Exception:
            self._log_failed = True
            logger.opt(exception=True).warning("ZzzOd 节点采集初始化失败")

    async def _close_log_details(self) -> None:
        """本专项只交付一次；取消先等待交付完成再继续传播。"""
        if self._log_user is None:
            return
        if self._log_close_task is None:
            self._log_close_task = asyncio.create_task(self._collect_log_details())
        cancelled = None
        while not self._log_close_task.done():
            try:
                await asyncio.shield(self._log_close_task)
            except asyncio.CancelledError as error:
                cancelled = error
        self._log_close_task.result()
        if cancelled is not None:
            raise cancelled

    async def _collect_log_details(self) -> None:
        user = self._log_user
        source = self._log_source
        pipeline = self._log_pipeline
        if user is None or (source is None and not self._log_failed):
            return
        if not self._log_failed:
            try:
                assert source is not None and pipeline is not None
                users = dict(self._push_user_book)
                pipeline.postprocessors.append(
                    _push_log.make_zzzod_resolve(
                        set(self._app_name_book.values()), dict(self._idx_names)
                    )
                )

                def read():
                    for line in source.read_new():
                        pipeline.feed(line, timestamp=time.time())
                    return pipeline.finish()

                entries = await asyncio.to_thread(read)
                for entry in entries:
                    match = _push_log.ACCOUNT_PREFIX_RE.match(entry.text)
                    if match is not None and match.group(1) in users:
                        target = users[match.group(1)]
                        if target.push_log_mode != "关闭":
                            target.push_log.append(
                                (entry.log_type, match.group(2), entry.timestamp)
                            )
                    else:
                        user.push_log.append(
                            (entry.log_type, entry.text, entry.timestamp)
                        )
            except Exception:
                self._log_failed = True
                logger.opt(exception=True).warning("节点采集或交付失败")
