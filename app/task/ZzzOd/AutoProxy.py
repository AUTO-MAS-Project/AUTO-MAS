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

- 用户态 + 「多实例切换」（脚本级下拉，不推荐）：把全部启用用户的配置
  注入各自绑定槽（备份 → 注入并清运行记录），随后
  ``--onedragon --instance {slot1,slot2,...}`` 一次性运行多账号一条龙——
  zzz-od 内部依次执行各实例并自行切换游戏账号；结果按各实例槽运行记录
  diff 归属到对应用户。
- 用户态 + 「单实例切换」（脚本级下拉，默认，推荐）：逐用户独立会话——注入
  该用户配置到其绑定槽 → 单实例运行（仅运行当前，无槽间切换）→ 跑完关闭
  → 下一个用户。失败域隔离，某用户失败只重启该用户。
- 用户态 + 「MAS切换」（暂未开放）：MAS 侧 OCR 操控游戏完成账号切换后交
  一条龙运行。
- 直控态：不注入不建视图，直接 ``--onedragon`` 裸跑，完全尊重 zzz-od 自己
  的 instance_run / 活跃实例 / 多账号运行设置；结果按全部实例运行记录聚合
  diff 判定。

启动器（OneDragon-RuntimeLauncher / OneDragon-Launcher）CLI 一条龙为进程内
同步运行、结束即退出；一条龙按任务粒度失败不中断（GroupApplication 继续跑
下一个），日志监控负责实时展示、终态标志行识别（成功/失败即结束等待）与
致命错误 / 超时兜底。
"""

import asyncio
import json
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from app.core import Config
from app.core.ws import Publisher, protocol
from app.log_box import LogCollect, log_box
from app.models.config import ZzzOdConfig, ZzzOdUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.schema import WSTaskNoticeData
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase, UserItem
from app.services import Notify, System
from app.task.general.tools import execute_script_task
from app.task.proxy_helpers import (
    find_pids_by_name,
    push_dispatch_log,
    split_args,
)
from app.utils import ProcessInfo, ProcessManager, get_logger, is_process_running
from app.utils.constants import UTC4
from app.utils.LogMonitor import LogMonitor

from .push_log import ACCOUNT_PREFIX_RE, ZZZOD_PUSH_RULES, make_zzzod_resolve
from .tools import (
    INSTANCE_RUN_ALL,
    INSTANCE_RUN_CURRENT,
    RUN_STATUS_FAILED,
    RUN_STATUS_RUNNING,
    RUN_STATUS_SUCCESS,
    archive_mas_config_backup,
    archive_onedragon_backup,
    backup_instance,
    clear_run_records,
    collect_mas_user_info,
    diff_run_records,
    find_active_instance,
    find_free_instance_idx,
    instance_dir,
    list_app_catalog,
    list_instances,
    push_notification,
    restore_instance,
    restore_instance_view,
    snapshot_run_records,
    user_field_patch,
    write_app_group,
    write_game_account,
    write_instance_view,
)

logger = get_logger("ZZZ-OD 自动代理")

# 启动器标签 → exe 文件名（集成=WithRuntime 打包的 RuntimeLauncher；原始=旧安装器
# Launcher；.bak 为启动器自更新残留，不参与发现）。元组顺序即默认发现顺序（集成优先）
_ZZZOD_LAUNCHER_BOOK = {
    "集成": "OneDragon-RuntimeLauncher.exe",
    "原始": "OneDragon-Launcher.exe",
}

_ZZZOD_LAUNCHERS = tuple(_ZZZOD_LAUNCHER_BOOK.values())

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

# 节点失败不触发重跑：运行记录 diff 里的应用失败只记录进任务报告（次日运行
# 时 zzz-od 会按运行记录自行重试失败节点）。运行级失败（启动器/登录/配置）
# 由致命日志关键词 + check_log 超时态走 main_task 的「用户运行失败 → 重试」分支。

# 一条龙应用终态成功标志（每次运行恰好出现一次）：出现即代表全部实例执行
# 完毕（对齐 ok-ww 的成功标志行行为）。出现后立即结束日志等待，不等启动器
# 进程退出（LogMonitor 静默期回调节流最长延迟 60s）；终态成败仍由 main_task
# 的运行记录 diff 统一判定——组内个别任务失败不影响该标志出现。
_ZZZOD_ONE_DRAGON_SUCCESS = "指令[ 一条龙 ] 执行成功"


# 汇总信号应用：上游「通知」应用在本轮存在失败任务时会把自己标失败
# （通知消息本身已发出，fire-and-forget），从失败名单剔除避免误导
_SUMMARY_APP_IDS = frozenset({"notify"})


def _match_fatal(log: str) -> str | None:
    """扫描内置致命关键词，命中返回状态文案，否则 None（三处判定共用）。"""

    return next(
        (msg for needle, msg in _ZZZOD_BUILTIN_FATAL if needle in log), None
    )


def _failed_apps(diffs: list) -> list[str]:
    """从运行记录 diff 中提取本轮失败的应用 id（剔除汇总信号应用）。"""

    return [
        app_id
        for app_id, _, new in diffs
        if new == RUN_STATUS_FAILED and app_id not in _SUMMARY_APP_IDS
    ]


def find_launcher_exe(root: Path) -> Path:
    """在安装根目录下发现 OneDragon 启动器。

    Raises:
        ValueError: 未找到任何启动器。
    """

    for name in _ZZZOD_LAUNCHERS:
        path = root / name
        if path.is_file():
            return path
    raise ValueError(f"{root} 下未找到 OneDragon 启动器, 请确认绝区零一条龙安装目录")


def find_launchers(root: Path) -> dict[str, Path]:
    """返回安装根目录下实际安装的启动器（标签 → exe 路径，未安装的不在结果中）。"""

    return {
        label: root / name
        for label, name in _ZZZOD_LAUNCHER_BOOK.items()
        if (root / name).is_file()
    }


def resolve_launcher(
    root: Path, mode: str, last_good: str = ""
) -> tuple[Path, str]:
    """按用户选择返回 (启动器 exe, 标签)。

    - 自动：优先「上次成功」的启动器（``last_good``），否则按默认顺序（集成优先）；
    - 原始/集成：固定用对应 exe，所选项未安装时回退默认顺序可用项并告警。

    Raises:
        ValueError: 安装根目录下没有任何启动器。
    """

    available = find_launchers(root)
    if available.get(mode):
        return available[mode], mode
    if mode == "自动" and last_good in available:
        return available[last_good], last_good
    # 固定模式所选未安装或无记忆：按默认顺序取首个可用（集成优先）
    for name in _ZZZOD_LAUNCHERS:
        path = root / name
        if path.is_file():
            label = next(
                (tag for tag, exe in _ZZZOD_LAUNCHER_BOOK.items() if exe == name),
                name,
            )
            if mode in ("原始", "集成"):
                logger.warning(
                    f"所选{mode}启动器未安装，已回退使用{label}启动器"
                )
            return path, label
    raise ValueError(f"{root} 下未找到 OneDragon 启动器, 请确认绝区零一条龙安装目录")


def _other_launcher_label(root: Path, label: str) -> str | None:
    """返回另一启动器的标签；未安装返回 None。"""

    other = "原始" if label == "集成" else "集成"
    return other if (root / _ZZZOD_LAUNCHER_BOOK[other]).is_file() else None


async def ensure_user_slot(
    root: Path, user_config: ZzzOdUserConfig, used_idxs: set[int]
) -> int:
    """解析/分配用户的绑定实例槽（纯分配，不触碰注册表——注册表由合成视图提供）。

    绑定下标存于用户配置 ``Info.SlotIdx``：有效 = 不与原生实例、其他 MAS
    用户已绑定槽冲突；无效则分配最小空闲 idx（全局查重）并把绑定落回用户
    配置。槽目录持久保留（配队等复杂配置），注册表只在运行/会话窗口内以
    合成视图出现。
    """

    bound = int(user_config.get("Info", "SlotIdx") or -1)
    native_idxs = {
        int(item.get("idx", -1))
        for item in list_instances(root)
        if isinstance(item, dict)
    }
    if bound > 0 and bound not in native_idxs and bound not in used_idxs:
        slot = bound
    else:
        slot = find_free_instance_idx(root, used_idxs)
    used_idxs.add(slot)
    if slot != bound:
        await user_config.set("Info", "SlotIdx", slot)
    return slot


def collect_used_slot_idxs(
    exclude_uids: set[uuid.UUID] | None = None,
) -> set[int]:
    """收集所有 ZzzOd 脚本用户已绑定的实例槽 idx（跨脚本全局查重用）。

    槽目录 config/{idx:02d} 跨脚本共享文件系统，idx 分配必须全局唯一，
    否则不同脚本的用户会写入同一目录互相覆盖配置。本次要注入/会话的用户
    经 ``exclude_uids`` 排除——它们通过自身 SlotIdx 重认领绑定。
    """

    used: set[int] = set()
    excluded = exclude_uids or set()
    for script_config in Config.ScriptConfig.values():
        if not isinstance(script_config, ZzzOdConfig):
            continue
        for uid, cfg in script_config.UserData.items():
            if uid in excluded:
                continue
            bound = int(cfg.get("Info", "SlotIdx") or -1)
            if bound > 0:
                used.add(bound)
    return used


def parse_user_apps(user_config: ZzzOdUserConfig) -> list[dict]:
    """解析用户配置的一条龙任务编排（JSON），返回 enabled 项列表。

    Raises:
        ValueError: AppList 不是合法 JSON 或结构异常。
    """

    try:
        raw = json.loads(str(user_config.get("OneDragon", "AppList") or "[]"))
    except json.JSONDecodeError as e:
        raise ValueError("一条龙任务编排数据异常, 请重新编辑任务配置") from e
    if not isinstance(raw, list):
        raise ValueError("一条龙任务编排数据异常, 请重新编辑任务配置")
    return [item for item in raw if isinstance(item, dict) and item.get("enabled")]


def inject_user_fields(
    root: Path, slot_idx: int, user_config: ZzzOdUserConfig, apps: list[dict]
) -> None:
    """把 MAS 用户字段写入绑定槽（game_account patch + 任务编排整表）。

    不清运行记录、不备份——配置会话（以本页配置为基线打开 GUI）与运行时
    注入（配合 clear_run_records）共用。
    """

    slot_dir = instance_dir(root, slot_idx)
    write_game_account(slot_dir, user_field_patch(user_config))
    write_app_group(slot_dir, apps)


def _snapshot_all_run_records(root: Path) -> dict[str, int]:
    """聚合全部实例的运行记录（直控态基准）：失败 > 运行中 > 成功 > 未跑。"""

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


class AutoProxyTask(TaskExecuteBase):
    """ZZZ-OD 自动代理：逐用户按三态来源拉起启动器 CLI 一条龙并监控"""

    # 取消时等 final_task 完整收尾（SRC/MaaFW 同款）：不设此 flag 时外层取消会
    # 立刻打断 shield 的 final_task，导致 kill_managed_process 没跑——取消任务后
    # zzz-od 启动器/一行龙本体仍继续运行
    wait_for_finalizer_on_cancel = True

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: ZzzOdConfig,
        user_config: MultipleConfig[ZzzOdUserConfig],
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
        # 注入轮只含用户模式用户，直控裸跑轮只含直控用户——report 聚合仍用
        # script_info.user_list（同一批 UserItem 对象，状态互通）
        self._task_users = users if users is not None else self.script_info.user_list

        self.cur_user_item: UserItem = self._task_users[
            self.script_info.current_index
        ]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config: ZzzOdUserConfig = self.user_config[self.cur_user_uid]
        # 两态配置来源（用户=本配置字段 / 直控=zzz-od 原生配置）
        self.mode = str(self.cur_user_config.get("Info", "Mode") or "用户")
        # 账号切换方式（脚本级下拉，仅用户态生效）：
        # 多实例切换=多用户注入多实例槽一轮跑；单实例切换=逐用户独立会话
        self.account_switch = str(
            self.script_config.get("Game", "AccountSwitch") or "单实例切换"
        )
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
        self.log_collect: LogCollect | None = None
        # 实例 idx → 账号名映射（直控=原生注册表快照；注入=绑定槽用户名），供后置
        # 处理器把「开始加载实例配置 N」段边界映射为账号归属
        self._idx_names: dict[int, str] = {}
        # 用户名 → UserItem（注入多实例切换的 sink 路由用；直控等无归属场景为空）
        self._push_user_book: dict[str, UserItem] = {}
        # 注入前账密守卫的告警（多账号一轮时剔除账密不全的用户），main_task 推调度台
        self._guard_warnings: list[str] = []
        # 注入现场（用户态共用）：绑定槽 → 备份目录（None=槽目录为本运行新建）
        self._injected_slots: list[tuple[int, Path | None]] = []
        # 槽位归属与注入基准（多实例切换按槽归属用户；单用户模式只有一个槽）
        self._slot_users: dict[int, tuple[UserItem, ZzzOdUserConfig]] = {}
        self._slot_records_before: dict[int, dict[str, int]] = {}
        self._multi_uids: set[str] = set()
        self._multi_judged: set[int] = set()
        self._multi_ran = False
        # 本轮判定为完成但部分任务执行失败的节点展示名（写入 script_info.log/通知）
        self._partial_failed_apps: list[str] = []
        self.run_book = False
        # app_id → 中文名（用于结果与推送日志展示）
        self._app_name_book: dict[str, str] = {}

    def _enabled_app_list(self) -> list[dict]:
        """当前用户的一条龙任务编排 enabled 项列表。"""

        return parse_user_apps(self.cur_user_config)

    def _is_multi_account(self) -> bool:
        """用户态且账号切换方式为「多实例切换」时走多账号一轮合并运行。"""

        return self.mode == "用户" and self.account_switch == "多实例切换"

    def _is_bare_run(self) -> bool:
        """直控态裸跑（不注入，按全部原生实例运行记录聚合判定）。"""

        return self.mode == "直控"

    def _push_log_enabled(self) -> bool:
        """节点详情采集开关：触发用户或（多实例切换时）任一启用用户未关闭即采集。"""

        if self.cur_user_item.push_log_mode != "关闭":
            return True
        if not self._is_multi_account():
            return False
        return any(
            str(
                self.user_config[uuid.UUID(item.user_id)].get(
                    "Notify", "PushLogMode"
                )
                or "汇总"
            )
            != "关闭"
            for item in self._task_users
            if self.user_config[uuid.UUID(item.user_id)].get("Info", "Status")
        )

    def _route_push_log(self, log_type: str, text: str, ts: float) -> None:
        """sink：把 log_box 采集结果按账号路由进各用户的推送日志。

        多实例切换的节点行带「【用户名】」前缀：剥掉前缀路由到对应 MAS 用户
        （其结果行已带用户名）；直控等无用户归属的场景统一落入当前用户
        （多账号时前缀保留，由报告渲染区分账号归属）。
        """

        m = ACCOUNT_PREFIX_RE.match(text)
        if m is not None and m.group(1) in self._push_user_book:
            target = self._push_user_book[m.group(1)]
            if target.push_log_mode != "关闭":
                target.push_log.append((log_type, m.group(2), ts))
        else:
            self.cur_user_item.push_log.append((log_type, text, ts))

    def _collect_inject_users(
        self,
    ) -> list[tuple[UserItem, ZzzOdUserConfig, list[dict]]]:
        """多实例切换的注入名单：启用且有任务编排的用户（按调度顺序）。

        逐用户施加跳过条件（剩余天数 / 今日代理次数上限 / 任务编排为空），
        命中的用户标记「跳过」不入列。直控用户绝不入列（直控=零注入，
        manager 本就不应分派，此处兜底防御）。多账号一轮时额外做账密守卫：
        任一用户缺账号或密码都会在槽间切换时失败并拖死整轮，缺失者标记
        「异常」剔除，告警写入调度台。
        """

        limit = int(self.script_config.get("Run", "ProxyTimesLimit"))
        candidates: list[tuple[UserItem, ZzzOdUserConfig, list[dict]]] = []
        for user_item in self._task_users:
            uid = uuid.UUID(user_item.user_id)
            cfg = self.user_config[uid]
            if not cfg.get("Info", "Status"):
                continue
            if str(cfg.get("Info", "Mode") or "用户") == "直控":
                logger.warning(
                    f"用户 {user_item.name} 为直控配置, 不参与注入运行（原生裸跑由调度单独分派）"
                )
                continue
            if cfg.get("Info", "RemainedDay") == 0:
                user_item.status = "跳过"
                continue
            if limit != 0 and cfg.get("Data", "ProxyTimes") >= limit:
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
                if str(cfg.get("Game", "Account") or "").strip() and str(
                    cfg.get("Game", "Password") or ""
                ).strip():
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

        只覆盖 MAS 侧非空字段，槽内 game_account.yml 的其余字段（platform、
        自定义窗口标题等）原样保留；随后清空运行记录让本次任务全部重跑。
        """

        inject_user_fields(self.script_root_path, slot_idx, user_config, apps)
        clear_run_records(self.script_root_path, slot_idx)

    async def _prepare_injection(
        self, users: list[tuple[UserItem, ZzzOdUserConfig, list[dict]]]
    ) -> None:
        """用户态注入：合成注册表视图 + 各用户字段写入绑定槽。

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
        used_idxs = collect_used_slot_idxs(
            exclude_uids={uuid.UUID(u.user_id) for u, _, _ in users}
        )

        for user_item, cfg, apps in users:
            slot = await ensure_user_slot(self.script_root_path, cfg, used_idxs)
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
            self._slot_records_before[slot] = snapshot_run_records(
                self.script_root_path, slot
            )
            self._multi_uids.add(user_item.user_id)
            # 多实例切换共用一个 log_box：各用户的节点详情推送模式与归属
            # （sink 按「【用户名】」前缀路由，idx→用户名供后置处理器归属）
            user_item.push_log_mode = str(
                cfg.get("Notify", "PushLogMode") or "汇总"
            )
            self._idx_names[slot] = str(cfg.get("Info", "Name") or "")
        self._push_user_book = {
            user_item.name: user_item for user_item, _, _ in users
        }

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
            force_login = bool(str(first_user.get("Game", "Account") or "").strip())

        write_instance_view(
            self.script_root_path,
            [
                (slot, f"MAS-{self._slot_users[slot][1].get('Info', 'Name')}")
                for slot, _ in slots
            ],
            active_idx=slots[0][0],
            instance_run=(
                INSTANCE_RUN_ALL if len(slots) > 1 else INSTANCE_RUN_CURRENT
            ),
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
            if cfg.get("Data", "LastProxyDate") != self.curdate:
                await cfg.set("Data", "LastProxyDate", self.curdate)
                await cfg.set("Data", "ProxyTimes", 0)

    async def check(self) -> str:
        # 跨日重置：必须在 ProxyTimesLimit 上限比较之前完成（对齐 ok-nte，
        # 避免 check 入口拿过期 ProxyTimes 误判为超限、永久跳过）
        await self._reset_daily_proxy_count()
        root = Path(self.script_config.get("Info", "RootPath"))
        if not root.is_dir():
            return "请设置绝区零一条龙安装目录"
        try:
            find_launcher_exe(root)
        except ValueError as e:
            return str(e)

        if self.mode not in ("用户", "直控"):
            return f"不支持的配置来源: {self.mode}"

        if self.mode == "用户":
            # 同脚本用户名唯一（绑定槽名与统计都依赖名字区分）
            names = [
                str(cfg.get("Info", "Name") or "").strip()
                for cfg in self.user_config.values()
                if cfg.get("Info", "Status")
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
                if self.script_config.get(
                    "Run", "ProxyTimesLimit"
                ) != 0 and self.cur_user_config.get(
                    "Data", "ProxyTimes"
                ) >= self.script_config.get("Run", "ProxyTimesLimit"):
                    self.cur_user_item.status = "跳过"
                    return "今日代理次数已达上限, 跳过该用户"
                if self.cur_user_config.get("Info", "RemainedDay") == 0:
                    self.cur_user_item.status = "跳过"
                    return "用户剩余天数为 0, 跳过该用户"
        elif find_active_instance(root) is None:
            return "zzz-od 中没有可运行的实例, 请先在一条龙中创建账号"

        return "Pass"

    async def prepare(self):
        self.launcher_process_manager = ProcessManager()
        # 「启用游戏配置 + 任务前启动游戏」时由 MAS 拉起游戏本体（对齐 ok-nte）
        self.game_process_manager = (
            ProcessManager()
            if self.script_config.get("Game", "Enabled")
            and self.script_config.get("Game", "LaunchBeforeTask")
            else None
        )
        game_path = str(self.script_config.get("Game", "Path") or "").strip()
        self.game_exe_path = Path(game_path) if game_path else None
        self.wait_event = asyncio.Event()

        self.user_start_time = datetime.now()
        self.script_root_path = Path(self.script_config.get("Info", "RootPath"))
        self.launcher_exe_path = find_launcher_exe(self.script_root_path)
        self.script_log_path = self.script_root_path / _ZZZOD_REL_LOG
        self.log_monitor = LogMonitor(
            (_ZZZOD_LOG_TIME_START, _ZZZOD_LOG_TIME_END),
            _ZZZOD_LOG_TIME_FORMAT,
            self.check_log,
        )

        with suppress(Exception):
            self._app_name_book = {
                item["app_id"]: item["app_name"]
                for item in list_app_catalog(self.script_root_path)
            }

        # 用户级节点详情推送模式（build_user_result_text 按此渲染）
        self.cur_user_item.push_log_mode = str(
            self.cur_user_config.get("Notify", "PushLogMode") or "汇总"
        )
        # ── log_box：节点详情采集（MAS 进程宿主，sink 按账号路由）──
        # 触发用户关闭且（多实例切换时）全部启用用户也关闭时不创建：不读日志、
        # 不匹配、不处理，省采集开销；关闭用户的 push_log 保持为空
        if self._push_log_enabled():
            self.log_collect = log_box.get_collect(
                paths=[self.script_log_path],
                sink=self._route_push_log,
                start_from_end=True,
                # zzz-od 跨零点把 log.txt 滚动为 log.txt.YYYY-MM-DD（内容日期
                # 式命名）：声明模板让轮转补偿在 inode 不可用的文件系统上也命中
                rotated_name=f"{self.script_log_path.name}.%Y-%m-%d",
            )
            self.log_collect.open()
            for rule in ZZZOD_PUSH_RULES:
                self.log_collect.collect(*rule)
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

        run_limit = int(self.script_config.get("Run", "RunTimesLimit"))
        try:
            # 注入现场（用户态）：绑定槽备份 → 由用户配置字段生成 YAML 写入槽 →
            # 临时切 instance_run。注入只做一次——重试不清运行记录，
            # 让 zzz-od 按记录跳过已完成任务。
            if self.mode == "直控":
                records_before = _snapshot_all_run_records(self.script_root_path)
                # 账号归属映射：原生注册表快照（idx → 实例名），供 log_box
                # 后置处理器把「开始加载实例配置 N」段边界映射为账号名
                self._idx_names = {
                    int(item.get("idx", -1)): str(item.get("name") or "")
                    for item in list_instances(self.script_root_path)
                    if isinstance(item, dict)
                }
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

            # 任务结束后关闭游戏由 MAS 侧执行（见 kill_managed_process），
            # 不再委托一条龙 --close-game：手动停止调度时 MAS 也能一并关游戏

            # 启动器选择：直控/用户统一按配置——自动=优先上次成功项，原始/集成=固定
            # 对应项（未安装回退可用项）；直控默认「自动」时行为等同原强绑定默认顺序
            self._launcher_mode = str(
                self.cur_user_config.get("Info", "LauncherMode") or "自动"
            )
            self.launcher_exe_path, self._launcher_label = resolve_launcher(
                self.script_root_path,
                self._launcher_mode,
                str(self.cur_user_config.get("Data", "LauncherLastGood") or ""),
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
                self.log_start_time = datetime.now()
                self.cur_user_item.log_record[self.log_start_time] = LogRecord()
                self.cur_user_log = self.cur_user_item.log_record[self.log_start_time]
                self.script_info.log = ""

                if self.cur_user_config.get("Info", "IfScriptBeforeTask"):
                    await execute_script_task(
                        Path(self.cur_user_config.get("Info", "ScriptBeforeTask")),
                        "脚本前任务",
                    )

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
                            await Notify.push_plyer(
                                "ZZZ-OD 自动代理出现异常！",
                                f"用户 {self.cur_user_item.name} 游戏启动失败",
                                f"{self.cur_user_item.name}的自动代理出现异常",
                                3,
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

                run_desc = (
                    f"{self.mode}配置·多实例切换·{len(self._injected_slots)}个用户"
                    if self._is_multi_account()
                    else f"{self.mode}配置"
                )
                if self._injected_slots:
                    # 一条龙切换会把活跃实例写回合成视图，每轮重写保证重试
                    # 从首槽开始、instance_run 语义正确（直控裸跑无视图）
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
                    records_after = snapshot_run_records(self.script_root_path, slot0)
                    self._judge_final(records_before, records_after, log)

                if self.run_book:
                    # 终态成功（判定器设置）：统一为框架成功契约「Success!」
                    # （直控跳过场景的可读说明已由判定器写入 script_info.log）
                    if (
                        self._launcher_label is not None
                        and self._launcher_mode == "自动"
                    ):
                        # 自动模式：把本次成功使用的启动器记忆为下次优先项
                        await self.cur_user_config.set(
                            "Data", "LauncherLastGood", self._launcher_label
                        )
                    self.script_info.log = self.script_info.log or "检测到 ZZZ-OD 已完成任务"
                    if self.cur_user_config.get("Info", "IfScriptAfterTask"):
                        await execute_script_task(
                            Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
                            "脚本后任务",
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

                logger.warning(
                    f"用户 {self.cur_user_item.name} - ZZZ-OD 代理异常: "
                    f"{self.cur_user_log.status}"
                )
                self.script_info.log = f"{self.cur_user_log.status}\n正在中止相关程序"
                await self.kill_managed_process(
                    kill_game=self._mas_should_close_game()
                )
                try:
                    await Notify.push_plyer(
                        "ZZZ-OD 自动代理出现异常！",
                        f"用户 {self.cur_user_item.name} 的自动代理出现一次异常",
                        f"{self.cur_user_item.name}的自动代理出现异常",
                        3,
                    )
                except Exception:
                    pass
                if self.cur_user_config.get("Info", "IfScriptAfterTask"):
                    await execute_script_task(
                        Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
                        "脚本后任务",
                    )
                if i + 1 < run_limit:
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
            failed_apps = _failed_apps(diffs)
            # 节点失败只记录不重跑（次日 zzz-od 按运行记录自行重试），本轮仍判
            # 完成；结果向框架成功契约 Success! 归一，失败节点进 script_info.log
            # 供任务详情与通知展示（历史层保持只认 Success! 的干净契约）
            if failed_apps:
                self._partial_failed_apps = [
                    self._app_display_name(app_id) for app_id in failed_apps
                ]
                log_status = "Success!"
                user_status = "完成"
                self.script_info.log = (
                    "部分任务执行失败: " + "、".join(self._partial_failed_apps)
                )
            elif any(new == RUN_STATUS_SUCCESS for _, _, new in diffs):
                log_status = "Success!"
                user_status = "完成"
                self.script_info.log = "检测到 ZZZ-OD 已完成任务"
            elif self._launch_evidence(log, False) or _ZZZOD_ONE_DRAGON_SUCCESS in log:
                # 记录无变化但有一条龙运行证据（应用层日志/成功标志）：
                # 直控态=今日任务均已完成（zzz-od 启动后按记录跳过全部任务）。
                # 结果向框架成功契约 Success! 归一，可读说明放到 script_info.log
                log_status = "Success!"
                user_status = "完成"
                self.script_info.log = "今日任务均已完成"
            else:
                # 记录无变化且无任何启动证据：启动器未能真正拉起一条龙
                # （缺依赖早退等），判失败走重试/启动器切换，不得报成功
                log_status = "启动器未能启动一条龙"
                user_status = "异常"

        self.cur_user_log.status = log_status
        # 以 run_book 向 main_task 通信终态：判定为完成的路径统一归一为
        # Success!（部分节点失败/直控跳过也视为成功，否则会空跑满重试次数
        # 并以失败落库）；具体说明已写入 script_info.log 供详情展示
        self.run_book = user_status == "完成"
        if user_status is not None:
            self.cur_user_item.status = user_status

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
                    snapshot_run_records(self.script_root_path, slot0),
                )
            )
        if self._launch_evidence(log, records_changed):
            return False

        other = _other_launcher_label(self.script_root_path, self._launcher_label)
        if other is None:
            return False

        self._launcher_label = other
        self.launcher_exe_path = (
            self.script_root_path / _ZZZOD_LAUNCHER_BOOK[other]
        )
        self._launcher_switched = True
        logger.warning(
            f"检测到 {other}启动器未能启动，已切换为另一启动器重试"
        )
        return True

    async def _judge_multi(self, log: str) -> None:
        """多实例切换：按各实例槽运行记录 diff 归属每个用户的结果。

        check_log 已标记的运行级终态（超时等）优先于运行记录 diff——收尾
        阶段卡死超时即使各槽已写出成功记录也不能判成功。致命日志次之：
        整轮异常时未完成的用户一律标记异常。全部用户完成时
        cur_user_log.status 置 ``Success!`` 以复用主流程的成功分支；任一用户
        未完成则进入重试（zzz-od 按运行记录跳过已完成任务）。
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
            before = self._slot_records_before.get(slot, {})
            after = snapshot_run_records(self.script_root_path, slot)
            diffs = diff_run_records(before, after)
            # 节点失败只记录不判异常（次日 zzz-od 按运行记录自行重试）
            failed_apps = _failed_apps(diffs)
            success = any(new == RUN_STATUS_SUCCESS for _, _, new in diffs)
            ok = fatal is None and not runtime_failed and success
            all_ok = all_ok and ok

            user_item.status = "完成" if ok else "异常"
            # 每个参与用户写一行终态 log_record：result 行不再显示「未开始
            # 运行」而节点有内容的矛盾。get-or-create：cur_user 的条目由
            # main_task 创建且 check_log 正在向其写 content，不能替换对象
            record = user_item.log_record.get(self.log_start_time)
            if record is None:
                record = LogRecord()
                user_item.log_record[self.log_start_time] = record
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
            # 节点详情由 log_box 统一采集（final_task 收尾时按账号路由）；
            # 数据落库只在状态变化时写，防止重试期间 ProxyTimes 多次自增
            if slot not in self._multi_judged or ok:
                await self._persist_multi_user_result(
                    cfg, ok, slot in self._multi_judged
                )
            self._multi_judged.add(slot)

        if runtime_failed:
            self.cur_user_log.status = runtime_status
            if self.cur_user_item.user_id in self._multi_uids:
                self.cur_user_item.status = "异常"
        elif fatal is not None:
            self.cur_user_log.status = fatal
            if self.cur_user_item.user_id in self._multi_uids:
                self.cur_user_item.status = "异常"
        elif all_ok:
            self.cur_user_log.status = "Success!"
            self.script_info.log = "检测到 ZZZ-OD 已完成任务"
        else:
            failed_users = "、".join(
                user_item.name
                for user_item, _ in self._slot_users.values()
                if user_item.status != "完成"
            )
            self.cur_user_log.status = f"ZZZ-OD 部分用户执行失败: {failed_users}"

        self.run_book = all_ok
        self._multi_ran = True

    async def _apply_proxy_success(self, cfg: ZzzOdUserConfig) -> None:
        """代理成功的数据写回三步（单实例与多实例路径共用）：
        首次代理扣剩余天数 → 累计次数 → 落「成功」状态。"""

        if cfg.get("Data", "ProxyTimes") == 0 and cfg.get("Info", "RemainedDay") != -1:
            await cfg.set("Info", "RemainedDay", cfg.get("Info", "RemainedDay") - 1)
        await cfg.set("Data", "ProxyTimes", cfg.get("Data", "ProxyTimes") + 1)
        await cfg.set("Data", "LastProxyStatus", "成功")

    async def _persist_multi_user_result(
        self, cfg: ZzzOdUserConfig, ok: bool, judged_before: bool
    ) -> None:
        """多实例切换：逐用户写回代理数据（对齐 _persist_user_run_result 语义）。

        ok → 成功（幂等：重试时已写过的用户跳过自增）；ok=False → 仅当本次
        运行尚未写过该用户时落「失败」，重试成功后仍可翻转为成功。
        """

        if ok:
            if cfg.get("Data", "LastProxyStatus") == "成功" and judged_before:
                return
            await self._apply_proxy_success(cfg)
        else:
            if judged_before:
                return
            await cfg.set("Data", "LastProxyStatus", "失败")

    async def _push_dispatch_log(self, line: str) -> None:
        """向调度台追加流程日志（赋值 script_info.log 会触发 WebSocket 推送）。"""

        await push_dispatch_log(self.script_info, line)

    async def _restore_injection(self) -> None:
        """恢复注入现场（用户态接管过时生效；幂等，恢复一次后置空）。

        先还原合成视图（原生注册表回来，含原生 instance_run），再逐槽恢复
        备份；槽目录一律保留（配队等复杂配置持久供配置会话维护）。
        """

        restore_instance_view(self.script_root_path)
        slots, self._injected_slots = self._injected_slots, []
        slot_user_items = [user_item for user_item, _ in self._slot_users.values()]
        self._slot_users = {}
        self._slot_records_before = {}
        self._multi_uids = set()
        self._multi_judged = set()
        if not slots:
            return
        try:
            for slot, backup_dir in slots:
                if backup_dir is not None and backup_dir.is_dir():
                    restore_instance(self.script_root_path, slot, backup_dir)
        except Exception as e:
            logger.opt(exception=True).warning(f"恢复 ZZZ-OD 注入现场失败: {e}")
            # 槽里留着 MAS 注入内容：本轮不能按成功收尾，参与用户一律置异常
            for user_item in slot_user_items or [self.cur_user_item]:
                user_item.status = "异常"
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="error",
                    message=f"恢复 ZZZ-OD 注入现场失败，原生配置可能残留 MAS 内容: {e}",
                ),
            )

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """按内置日志监控运行；致命错误与超时立即终止，进程退出触发统一终判。"""

        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log[-4000:] if len(log) > 4000 else log

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
                latest_time, minutes=self.script_config.get("Run", "RunTimeLimit")
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
        # 结束时先清理进程与监控（正常结束/失败/超时/手动中止都走这里——
        # wait_for_finalizer_on_cancel 保证手动停止也会完整收尾）
        if self.log_monitor is not None:
            with suppress(Exception):
                await self.log_monitor.stop()
        await self.kill_managed_process(kill_game=self._mas_should_close_game())
        await self._restore_injection()

        # log_box 收尾：冲刷残留并完成后置聚合（账号归属 → sink 路由进各用户
        # push_log）。manager.final_task 的报告聚合在子任务收尾之后执行，
        # 此处先 close 保证节点详情已就位
        if self.log_collect is not None:
            with suppress(Exception):
                self.log_collect.close(
                    make_zzzod_resolve(
                        set(self._app_name_book.values()), self._idx_names
                    )
                )

        # 写入历史记录（对齐 General/SRC/MaaEnd/Okww/BetterGI 行为）
        statistic_paths: list[Path] = []
        for t, log_item in self.cur_user_item.log_record.items():
            dt = t.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone(UTC4)
            log_path = Config.build_history_log_path(
                script_name=self.script_info.name,
                user_name=self.cur_user_item.name,
                log_time=dt,
            )

            if log_item.status == "ZZZ-OD 正常运行中":
                log_item.status = "任务被用户手动中止"

            if len(log_item.content) == 0:
                log_item.content = ["未捕获到任何日志内容"]
                # 未判定（进程异常退出/被中止）才标未捕获；已有终态判定时
                # 保留判定状态（判定依据是运行记录 diff，不依赖日志内容）
                if log_item.status in ("未开始监看日志", "ZZZ-OD 正常运行中"):
                    log_item.status = "未捕获到日志"

            await Config.save_general_log(log_path, log_item.content, log_item.status)
            statistic_paths.append(log_path.with_suffix(".json"))

        if statistic_paths:
            try:
                statistics = await Config.merge_statistic_info(statistic_paths)
                statistics["user_info"] = self.cur_user_item.name
                start_time = getattr(self, "user_start_time", datetime.now())
                statistics["start_time"] = start_time.strftime("%Y-%m-%d %H:%M:%S")
                statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                if not self.run_book:
                    user_result = self.cur_user_item.result
                elif self._partial_failed_apps:
                    # 判定完成但部分节点失败：结果保持成功，明细告知用户
                    user_result = (
                        "部分任务未完成，将于次日重试: "
                        + "、".join(self._partial_failed_apps)
                    )
                else:
                    user_result = "代理任务全部完成"
                statistics["user_result"] = user_result
                success_symbol = "√" if self.run_book else "X"
                await push_notification(
                    "统计信息",
                    f"{datetime.now().strftime('%m-%d')} |{success_symbol}|  "
                    f"{self.cur_user_item.name} 的 ZZZ-OD 自动代理统计报告",
                    statistics,
                    self.cur_user_config,
                )
            except Exception as e:
                # 失败不再静默：既记 ERROR 日志，也推到调度台实时日志
                await self._push_dispatch_log(f"推送用户统计通知失败: {e}")
                logger.opt(exception=True).error(
                    f"推送 ZZZ-OD 用户统计通知时出现异常: {e}"
                )

        await self._persist_user_run_result()

    async def _persist_user_run_result(self) -> None:
        # 多实例切换：各用户的数据已在 _judge_multi 逐用户写回，避免重复计数
        if self._multi_ran:
            return

        if self.run_book:
            await self._apply_proxy_success(self.cur_user_config)
            self.cur_user_item.status = "完成"
            logger.success(f"用户 {self.cur_user_uid} 的 ZZZ-OD 自动代理任务已完成")
        else:
            await self.cur_user_config.set("Data", "LastProxyStatus", "失败")
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
                data=WSTaskNoticeData(level="error", message=f"ZZZ-OD 自动代理任务出现异常: {e}"),
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
                await Notify.push_plyer(
                    "ZZZ-OD 运行异常",
                    f"用户 {self.cur_user_item.name}：{self.cur_user_log.status}",
                    "异常",
                    3,
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

        return bool(self.script_config.get("Game", "CloseOnFinish"))

    async def _mas_launch_game_before_task(self) -> None:
        """MAS 接管启动游戏本体（启用游戏配置 + 任务前启动游戏时调用）。

        一条龙自身也会拉起游戏，但 MAS 先把游戏开好可跳过一条龙内的启动
        等待；检测到游戏进程已在运行时直接复用，不重复启动。
        """

        if not isinstance(self.game_process_manager, ProcessManager):
            return
        await self._push_dispatch_log(
            f"正在检查游戏进程 ({_ZZZ_GAME_PROCESS})..."
        )
        if is_process_running(_ZZZ_GAME_PROCESS):
            logger.info("检测到游戏本体进程已在运行，跳过由 MAS 重复启动游戏")
            await self._push_dispatch_log("检测到游戏已在运行，跳过启动")
            return
        if self.game_exe_path is None:
            raise RuntimeError(
                "未配置游戏路径，请在脚本配置的游戏配置中选择游戏本体（ZenlessZoneZero.exe）"
            )
        await self._push_dispatch_log("正在由 MAS 启动游戏...")
        await self.game_process_manager.open_process(
            self.game_exe_path,
            *split_args(self.script_config.get("Game", "Arguments")),
        )
        wait_time = max(int(self.script_config.get("Game", "WaitTime") or 0), 0)
        if wait_time:
            await self._push_dispatch_log(f"等待游戏启动（{wait_time} 秒）...")
            await asyncio.sleep(wait_time)
        await self._push_dispatch_log("游戏启动完成")

    async def _kill_game_process(self) -> None:
        """按进程名结束游戏本体（对齐 ok-nte 的 MAS 侧关闭）。"""

        try:
            # 全进程扫描放到线程里，不阻塞事件循环
            for pid in await asyncio.to_thread(find_pids_by_name, _ZZZ_GAME_PROCESS):
                try:
                    await System.kill_process_by_pid(pid)
                except Exception as e:
                    logger.opt(exception=True).warning(
                        f"结束游戏进程失败 PID: {pid}, {e}"
                    )
        except Exception as e:
            logger.opt(exception=True).warning(f"关闭游戏进程失败: {e}")
