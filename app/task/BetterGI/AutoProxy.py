#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

import asyncio
import re
import time
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from app.core import Config
from app.core.ws import Publisher, protocol
from app.models.config import BetterGIConfig, BetterGIUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.schema import WSTaskNoticeData
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase, UserItem
from app.services import Notify, System
from app.task.general.tools import execute_script_task
from app.task.proxy_helpers import push_dispatch_log
from app.utils import ProcessInfo, ProcessManager, ProcessRunner, get_logger
from app.utils.constants import UTC4
from app.utils.LogMonitor import LogMonitor
from app.utils.platform import IS_ELEVATED

from .tools import (
    account_switch,
    one_dragon,
    one_dragon_bridge,
    push_notification,
)
from .tools.one_dragon_plan import (
    BUILTIN_COMBAT_STEP_NAMES,
    build_combat_steps,
    parse_one_dragon_plan,
    resolve_base_name,
)
from .tools.one_dragon_report import parse_one_dragon_report

logger = get_logger("BetterGI 自动代理")

# BetterGI 项目结构固定相对路径（从 RootPath 派生，不依赖用户存储值）
# ⚠️ 与前端 BetterGIScriptEdit.vue 的 BGI_EXE_NAME 保持同步，改这里时需同步改前端
_BGI_REL_EXE = "BetterGI.exe"
_BGI_TRACK_PROCESS_NAME = "BetterGI.exe"
# BetterGI 的 Serilog 日志按天滚动，实际文件名为 better-genshin-impact{yyyyMMdd}.log
# （不存在无日期后缀的 better-genshin-impact.log）
_BGI_REL_LOG_DIR = "log"
_BGI_LOG_FILE_PREFIX = "better-genshin-impact"

# ── BetterGI 专项硬编码（不存 ConfigItem，随 MAS 版本同步）──────────────
# BetterGI 使用 Serilog 文件日志，行格式：
#   [{HH:mm:ss.fff}] [{Level:u3}] [{BgiInstance}] {SourceContext}\n{Message}
# 成功/失败判定取自 BetterGI 的统一日志片段，BetterGI 不向用户暴露关键词配置。
#
# 进程级致命只有下面两种，会直接判异常：
#   [FTL]          —— BetterGI 自己的 Fatal 级别，出现即进程级崩溃；
#   「任务启动失败」—— 任务锁被占用（多半残留进程占锁），单条被跳过但整条可信度存疑。
# ⚠️ 不得把 [ERR] 放进此表：它是 TaskRunner.Run 在每个【子任务】的 catch(Exception) 里打印的
# 「任务级」异常（TaskRunner.cs 的 Run 包裹每条任务/配置组，捕获后不 rethrow，一条龙继续跑
# 下一条）。直接 BGI 中这是可恢复的“跳过该步继续跑”，一条龙仍会正常走完收尾行；若 MAS 按
# [ERR] 判 fatal，会把本可直接跑完的一条龙中途强杀（本次已实际复现）。真正跑不动由「收尾行
# 缺失 + 进程提前退出 / 卡死 / 超时」兜底（见 check_log）。
_BGI_BUILTIN_FATAL: tuple[tuple[str, str], ...] = (
    ("[FTL]", "BetterGI 出现致命错误"),
    ("任务启动失败", "BetterGI 任务启动失败"),
)
# 唯一权威收尾是 OneDragonFlowViewModel.RunThreadAsync 在全部任务 + 配置组任务 +
# CheckRewardsTask 完成后打印的固定行「一条龙和配置组任务结束」（仅正常完成路径，取消/异常
# 分支会在其前 return，不打印该行）。run 中即使有杂散 [ERR]，只要最终走到收尾行，即证明各步
# 异常均可恢复，按成功处理。命中条件见 _one_dragon_sequence_done。
_BGI_SEQUENCE_DONE_MARKER = "一条龙和配置组任务结束"
# 出现过 [ERR] 后、若连续这么久没有任何新日志行（BGI 既未完成也未退出），判定卡死提前失败。
# 仅在出错后静默触发，正常推进时 latest_time 会被新行持续刷新、不会误触。
_BGI_ERR_STALL_MINUTES = 5
_BGI_LOG_TIME_START = 1
_BGI_LOG_TIME_END = 13
_BGI_LOG_TIME_FORMAT = "%H:%M:%S.%f"

# 切换账号单独执行的超时（秒），超时视为失败并继续一条龙
_BGI_SWITCH_TIMEOUT_SECONDS = 600

# 路径 B 执行层（战斗 4 项 --startGroups MAS一条龙）单独执行的超时（秒）
# 执行层空闲超时：on_log 每次收到日志即续期；仅当日志静默超过该时长才判定卡死。
# （旧实现为固定 900s 墙钟，多实例执行层总耗时可超 20 分钟会被误杀——2026-09-08 实机排障。）
_BGI_PLAN_COMBAT_IDLE_TIMEOUT_SECONDS = 300

# BetterGI 管理的原神游戏进程名（不含 .exe），与 BetterGI 源码
# TaskContext.GetGenshinGameProcessNameList() 保持一致；任务结束后按此顺序逐一尝试关闭。
_BGI_GAME_PROCESS_NAMES: tuple[str, ...] = (
    "YuanShen",  # 官服 / B服（国服）
    "GenshinImpact",  # 国际服
    "Genshin Impact Cloud Game",  # 云原神（国际）
    "Genshin Impact Cloud",  # 云原神（备用进程名）
)


def _one_dragon_sequence_done(log: str) -> bool:
    """判定整条一条龙序列是否完成。

    以 BetterGI 唯一权威收尾行为准：``一条龙和配置组任务结束``。它只在全部任务 +
    配置组任务 + CheckRewardsTask 都完成后打印；任何子任务（含切换账号配置组）边界的
    「→ 任务结束」或「配置组任务执行: X/Y」都不代表整条完成，不得据此判成功。

    Args:
        log: 本次运行的累计日志文本。

    Returns:
        True 表示整条一条龙已完成。
    """
    return _BGI_SEQUENCE_DONE_MARKER in log


def _latest_repo_progress(log: str) -> str | None:
    """从累计日志中提取最近一条值得转述的脚本仓库下载/更新进展行。

    BGI 把仓库更新/下载进展打在不带方括号前缀的消息行；转述给用户后，切号/一条龙
    启动时「正在下载脚本」就不会被误认为卡死。
    Serilog 每行消息在带 ``[HH:mm:ss]`` 前缀的头行之后另起一行，这里只匹配消息行。
    按时间从后往前找，命中即返回相干文案；无进展（或不在下载/更新阶段）返回 None。
    """
    for ln in reversed(log.splitlines()):
        ln = ln.strip()
        if not ln or ln.startswith("["):
            continue
        if "浅克隆仓库" in ln:
            return "正在从脚本仓库下载脚本（首次克隆/仓库冷启动，可能耗时较长，请耐心等待）..."
        if "拉取对象" in ln:
            return "正在向脚本仓库拉取 git 对象..."
        if "开始静默更新脚本仓库" in ln:
            return "正在静默更新脚本仓库..."
        if "自动更新订阅脚本完成" in ln:
            return f"脚本仓库更新完成: {ln}"
        if "本地仓库已是最新" in ln:
            return "脚本仓库已是最新，无需下载"
    return None


def _is_switch_script_updated(log: str) -> bool:
    """切号脚本是否已在本次日志中被检出。"""
    return '更新脚本成功: "js/SwitchAccountMultipleMode"' in log


# ── 切队配置错误识别 ─────────────────────────────────
# 一条龙里的战斗队伍（PartyName）若在游戏内置找不到，BGI 切队会把整条一龙任务打崩：
#   - OCR 扫描不到名单：SwitchPartyTask 打「未找到队伍: <名>，返回主界面」；
#   - 直接抛异常：SwitchPartyTask.Start 第202行 Enumerable.Last() 取不到匹配项 →
#     InvalidOperationException "Sequence contains no elements" → 自动地脉花等任务打 [ERR]。
# 两者都说明配置的战斗队伍名不合法。命中时给明确报错（指明队伍名），而非笼统的
# 「任务执行异常」/「完成任务前退出」。
_BGI_PARTY_SWITCH_RE = re.compile(r'尝试切换至队伍:\s*["“]?([^"”\n]+)["”]?\s*$', re.M)
_BGI_PARTY_ERROR_HINTS = ("未找到队伍", "Sequence contains no elements")


def _party_config_error(log: str) -> str | None:
    """检测切队配置错误（战斗队伍名在游戏内置找不到），返回出错队伍名；无则 None。"""
    if not ("尝试切换至队伍" in log and any(h in log for h in _BGI_PARTY_ERROR_HINTS)):
        return None
    m = _BGI_PARTY_SWITCH_RE.search(log)
    if not m:
        return None
    name = m.group(1).strip()
    return name or None


class AutoProxyTask(TaskExecuteBase):
    """BetterGI 自动代理：拼 `startOneDragon <configName>` 启动并监控日志"""

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: BetterGIConfig,
        user_config: MultipleConfig[BetterGIUserConfig],
    ):
        super().__init__()
        if script_info.task_info is None:
            raise RuntimeError("ScriptItem 未绑定到 TaskItem")

        self.task_info = script_info.task_info
        self.script_info = script_info
        self.script_config = script_config
        self.user_config = user_config

        self.cur_user_item: UserItem = self.script_info.user_list[
            self.script_info.current_index
        ]
        self.cur_user_uid = uuid.UUID(self.cur_user_item.user_id)
        self.cur_user_config: BetterGIUserConfig = self.user_config[self.cur_user_uid]
        self.use_mas_config = bool(self.cur_user_config.get("Info", "IfUseMasConfig"))
        self.cur_user_log: LogRecord | None = None
        self.bettergi_process_manager: ProcessManager | None = None
        self.wait_event: asyncio.Event | None = None
        self.script_root_path: Path | None = None
        self.script_exe_path: Path | None = None
        self.script_target_process_info: ProcessInfo | None = None
        self.log_monitor: LogMonitor | None = None
        # 切队配置错误报错只推送一次，避免每个日志回调重复刷屏
        self._party_err_pushed = False

    async def check(self) -> str:
        root = Path(self.script_config.get("Info", "RootPath"))
        if not root.is_dir():
            return "请设置 BetterGI 脚本路径"
        if not (root / _BGI_REL_EXE).is_file():
            return "请设置 BetterGI 脚本路径"

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

        return "Pass"

    async def prepare(self):
        self.bettergi_process_manager = ProcessManager()
        self.wait_event = asyncio.Event()

        self.user_start_time = datetime.now()
        self.log_start_time = datetime.now()

        # ── 所有 Script 路径从 RootPath 实时派生，不依赖 ConfigItem 存储值 ──
        self.script_root_path = Path(self.script_config.get("Info", "RootPath"))
        self.script_exe_path = self.script_root_path / _BGI_REL_EXE

        self.script_target_process_info = ProcessInfo(
            name=_BGI_TRACK_PROCESS_NAME,
            exe=str(self.script_exe_path),
            cmdline=None,
        )

        self.log_time_range = (_BGI_LOG_TIME_START, _BGI_LOG_TIME_END)
        self.log_time_format = _BGI_LOG_TIME_FORMAT
        self.log_monitor = LogMonitor(
            self.log_time_range,
            self.log_time_format,
            self.check_log,
        )

        # 「用户独立配置」开启时：一条龙配置名固定为 MAS 专属槽位「MAS独立配置」，
        # 忽略用户旧所选名（Task.OneDragonConfigName 冻结不用），BGI 同名实配全程零接触；
        # 关闭时维持现状：直控 BGI 所选实配、MAS 不干预。
        self.one_dragon_config = (
            one_dragon.launch_slot_name()
            if self.use_mas_config
            else one_dragon.resolve_config_name(
                str(self.cur_user_config.get("Task", "OneDragonConfigName") or "")
            )
        )
        self.one_dragon_groups = list(
            self.cur_user_config.get("OneDragon", "Groups") or []
        )
        self.use_custom_groups = bool(
            self.cur_user_config.get("OneDragon", "IfUseCustomGroups")
        )
        self.one_dragon_custom_groups = one_dragon.parse_custom_groups(
            self.cur_user_config.get("OneDragon", "CustomGroups") or ""
        )
        # 可视化队列（有序条目，含重复实例）：决定运行时 TaskOrder 重建顺序；
        # 为空/非法时 write_user_one_dragon 回退旧行为（沿用副本 TaskOrder 相对顺序）
        self.one_dragon_queue = one_dragon.parse_one_dragon_queue(
            self.cur_user_config.get("OneDragon", "Queue") or ""
        )
        # 路径 B 执行层开关与 Plan：UseExecutionLayer 开且 Plan 含启用的战斗 4 项时进入 plan 模式。
        # 只有「Plan 中配过该组」且「队列中该条目启用」的战斗组才由执行层接管，其余战斗组
        # 留在一条龙副本（_write_one_dragon_config 只剔除实际接管的组，避免重复执行）。
        self.use_execution_layer = bool(
            self.cur_user_config.get("OneDragon", "UseExecutionLayer")
        )
        _plan_steps = parse_one_dragon_plan(
            self.cur_user_config.get("OneDragon", "Plan") or ""
        )
        self.plan_combat_steps = build_combat_steps(
            _plan_steps, self.one_dragon_queue, self.one_dragon_groups
        )
        # 路径 B 回退：顶层「通用战斗队伍」(OneDragon.PartyName) 默认填入各战斗步骤的
        # 队伍字段，与路径 A（write_user_one_dragon 把 PartyName 写入秘境/首领，并经
        # apply_global_battle_team 写入地脉花/幽境全局配置）保持一致。仅在对应的 per-group
        # 队伍字段为空时注入，已显式设置的队伍不覆盖。
        _default_party = str(self.cur_user_config.get("OneDragon", "PartyName") or "").strip()
        if _default_party:
            _TEAM_FIELD_BY_BASE = {
                "自动秘境": "partyName",
                "自动地脉花": "team",
                "自动幽境危战": "fightTeamName",
                "自动首领讨伐": "teamName",
            }
            for _step in self.plan_combat_steps:
                _base = resolve_base_name(str(_step.get("name", "")))
                _field = _TEAM_FIELD_BY_BASE.get(_base)
                if not _field:
                    continue
                _settings = _step.get("settings")
                if not isinstance(_settings, dict):
                    _settings = {}
                    _step["settings"] = _settings
                if not _settings.get(_field):
                    _settings[_field] = _default_party
        self.plan_mode = self.use_execution_layer and bool(self.plan_combat_steps)
        self.launch_config_name = self.one_dragon_config
        self.bettergi_args = ["startOneDragon", self.launch_config_name]

        self.run_book = False

        # 通用战斗队伍/策略落到全局 config.json 前的叶子快照，None 表示尚未接管
        self._reseed_global_config: dict | None = None
        # 本次物化到 BGI User/ScriptGroup 的前缀配置组文件（运行结束删除）
        self._materialized_script_groups: list[Path] = []

    def _resolve_log_file_path(self) -> Path:
        """构造 BetterGI 当日滚动日志路径（better-genshin-impact{yyyyMMdd}.log）。"""
        return (
            self.script_root_path
            / _BGI_REL_LOG_DIR
            / f"{_BGI_LOG_FILE_PREFIX}{datetime.now():%Y%m%d}.log"
        )

    async def _push_dispatch_log(self, line: str) -> None:
        """向调度台追加流程日志（赋值 script_info.log 会触发 WebSocket 推送）。"""

        await push_dispatch_log(self.script_info, line)

    def _write_one_dragon_config(
        self, exclude_task_names: list[str] | None = None
    ) -> None:
        """用户独立配置模式下，把组开关应用到一条龙配置并物化到 BGI（槽位 + 前缀配置组）。

        物化的配置组文件路径记录在 ``self._materialized_script_groups``，
        由 ``_restore_one_dragon_config`` 在结束后删除。
        ``exclude_task_names`` 用于路径 B：把已改由执行层直连的战斗 4 项从一条龙副本过滤掉。
        """
        if not self.use_mas_config:
            return
        party_name = str(self.cur_user_config.get("OneDragon", "PartyName") or "")
        # 路径 B：战斗 4 项由执行层直连，原生一条龙只跑日常 + 自定义组。
        # 把「队列里出现的所有战斗组」一律从原生副本剔除，使前端队列开关成为唯一真理源：
        # 开 → 执行层跑；关（Plan.step.enabled=false）→ 原生也不跑，避免关了还漏跑/重复跑。
        # 日常 4 项不在战斗集合内，仍按 OneDragon.Groups 在原生一条龙启停（单开关已对齐）。
        _exclude = exclude_task_names or (
            sorted(
                {
                    b
                    for q in (self.one_dragon_queue or [])
                    for b in [resolve_base_name(str(q.get("name", "")))]
                    if b and b in BUILTIN_COMBAT_STEP_NAMES
                }
            )
            if self.plan_mode
            else None
        )
        self._materialized_script_groups = one_dragon.write_user_one_dragon(
            self.script_root_path,
            self.script_info.script_id,
            self.cur_user_item.user_id,
            self.one_dragon_groups,
            daily_reward_party_name=str(
                self.cur_user_config.get("OneDragon", "DailyRewardPartyName") or ""
            ),
            party_name=party_name,
            auto_boss_strategy_name=str(
                self.cur_user_config.get("OneDragon", "AutoBossStrategyName") or ""
            ),
            custom_groups=self.one_dragon_custom_groups,
            manage_custom_groups=self.use_custom_groups,
            queue=self.one_dragon_queue,
            exclude_task_names=_exclude,
        )
        # 通用战斗队伍/策略先补写进全局 config.json（秘境/地脉花/幽境危战读取段）；
        # 优先级：右栏配置 > 顶部通用（通用仅兜底）
        one_dragon.apply_global_battle_team(self.script_root_path, party_name)
        one_dragon.apply_global_battle_strategy(
            self.script_root_path,
            str(self.cur_user_config.get("OneDragon", "AutoBossStrategyName") or ""),
        )
        # 幽境危战面板设置（刷取战场/树脂策略等）随后物化到 config.json 的
        # autoStygianOnslaughtConfig 段：右栏 fightTeamName/strategyName 非空时覆盖
        # 通用值（右栏优先），留空则保留刚补写的通用值（通用兜底）。
        one_dragon.apply_user_global_stygian_settings(
            self.script_root_path,
            self.script_info.script_id,
            self.cur_user_item.user_id,
        )
        # 秘境刷取配置（领奖树脂/分解圣遗物/奖励识别）：有 per-user 副本则物化到
        # BGI config.json 的 autoDomainConfig/autoArtifactSalvageConfig 段（运行结束还原）
        if one_dragon.apply_user_global_domain_settings(
            self.script_root_path,
            self.script_info.script_id,
            self.cur_user_item.user_id,
        ):
            logger.info(
                f"已物化用户 {self.cur_user_item.name} 的秘境刷取配置到全局 config.json"
            )
        logger.info(
            f"已写入用户 {self.cur_user_item.name} 的独立一条龙配置（槽位 "
            f"{one_dragon.launch_slot_name()}），物化配置组 {len(self._materialized_script_groups)} 个"
        )

    def _backup_one_dragon_config(self) -> None:
        """运行前快照乐观覆盖的全局 config.json 队伍/策略叶子，供结束后还原。

        独立配置模式下 per-user 配置落到 MAS 专属槽位，不写 BGI 同名实配；BGI 那套
        一条龙文件无需备份。全局 config.json 的队伍/策略叶子（地脉花/幽境危战/秘境读段）
        仍需运行时临时补写、结束还原，故这里先快照。同时清理上一轮强杀可能残留的
        前缀物化组（只命中 MAS-{短id}-*，不碰 BGI 本体）。
        """
        if not self.use_mas_config:
            return
        one_dragon.cleanup_leftover_mas_groups(
            self.script_root_path, self.script_info.script_id, self.cur_user_item.user_id
        )
        self._reseed_global_config = one_dragon.snapshot_global_battle_config(
            self.script_root_path
        )

    def _restore_one_dragon_config(self) -> None:
        """运行/异常结束后还原现场：删除物化配置组文件、还原 config.json 叶子、删槽位。

        仅在「用户独立配置」模式下生效（非独立模式 MAS 不写槽位/物化文件，绝不触碰
        BGI 目录）：删除物化的前缀配置组文件与槽位是幂等执行；只有真正接管过全局
        config.json 队伍/策略叶子（``_reseed_global_config`` 非 None）才还原叶子。
        各步置空后再次调用即安全，避免 final_task 与 on_crash 相继触发时重复操作。
        """
        if not self.use_mas_config:
            return
        try:
            one_dragon.remove_materialized_script_groups(
                self.script_root_path, self._materialized_script_groups
            )
            self._materialized_script_groups = []
            one_dragon.remove_one_dragon_slot(
                self.script_root_path, self.script_info.script_id
            )
            if self._reseed_global_config is not None:
                # 还原全局 config.json 队伍/策略叶子字段（秘境/地脉花/幽境危战读取段）
                one_dragon.restore_global_battle_config(
                    self.script_root_path, self._reseed_global_config
                )
        finally:
            self._reseed_global_config = None

    def _native_one_dragon_has_tasks(self) -> bool | None:
        """原生一条龙（阶段2）是否还有任何启用任务。

        路径 B 下战斗组已被执行层接管并从原生副本剔除，若日常/自定义组也都关，
        启用任务数即为 0。此时再启动 ``startOneDragon`` 会让 BetterGI 空跑且不退出，
        导致任务挂死。读实际写好的原生配置，按 ``TaskEnabledList`` 判定是否有活可干。

        Returns:
            True/False 表示有无启用任务；配置读不出来时返回 None，由调用方按失败处理，
            不与「真的没有启用任务」混为一谈。
        """
        try:
            cfg = one_dragon.load_one_dragon(
                self.script_root_path, self.launch_config_name
            )
        except (OSError, ValueError, KeyError, TypeError) as e:
            logger.opt(exception=True).warning(
                f"用户 {self.cur_user_item.name} 一条龙配置读取失败: {e}"
            )
            return None
        enabled = cfg.get("TaskEnabledList") if isinstance(cfg, dict) else None
        if not isinstance(enabled, dict):
            return False
        return any(bool(v) for v in enabled.values())

    async def main_task(self):
        await self.prepare()
        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        if self.cur_user_config.get("Data", "LastProxyDate") != self.curdate:
            await self.cur_user_config.set("Data", "LastProxyDate", self.curdate)
            await self.cur_user_config.set("Data", "ProxyTimes", 0)

        self.cur_user_item.status = "运行"

        # 切换账号（单独执行 --startGroups，先于一条龙）
        if not await self._switch_account():
            self.cur_user_item.status = "异常"
            self.script_info.log = "切换账号失败，已中止任务"
            logger.error(f"用户 {self.cur_user_item.name} 切换账号失败，中止任务")
            return

        # 用户独立配置：先备份现场再写入，结束后 (final_task/on_crash) 还原
        self._backup_one_dragon_config()
        self._write_one_dragon_config()

        # 路径 B：先直连执行层跑战斗 4 项。失败不再中止任务：日常 4 项（领奖类）
        # 与战斗无依赖，仍由随后的一条龙承接，避免战斗异常连坐吞掉日常收益
        # （2026-09-08 用户决策：记录警告但继续）。
        plan_combat_ok = True
        if self.plan_mode:
            plan_combat_ok = await self._run_plan_combat()
            if not plan_combat_ok:
                self.script_info.log = "执行层（战斗4项）失败，继续执行一条龙日常"
                logger.warning(
                    f"用户 {self.cur_user_item.name} 执行层失败，记录警告并继续一条龙日常"
                )

        # 原生一条龙（阶段2）无启用任务：不再启动 BetterGI，避免空一条龙进程不退出导致任务挂死。
        # 路径 B 下战斗组已被剔除，若日常/自定义组也都关，启用任务数即为 0。
        has_tasks = self._native_one_dragon_has_tasks()
        if has_tasks is None:
            # 配置读取失败：不是「无活可干」，按失败收尾（run_book 保持 False）
            self.cur_user_item.status = "异常"
            self.script_info.log = "一条龙配置读取失败，已中止任务"
            return
        if not has_tasks:
            if self.plan_mode and plan_combat_ok:
                # 战斗已由执行层完成，日常一条龙无活可干：整体视为成功，直接收尾
                self.run_book = True
                self.script_info.log = (
                    "执行层战斗已完成；原生一条龙无启用任务，跳过阶段2"
                )
            else:
                self.script_info.log = "一条龙无启用任务，跳过"
            logger.info(
                f"用户 {self.cur_user_item.name} 原生一条龙无启用任务，跳过 BetterGI 启动"
            )
            return

        run_limit = int(self.script_config.get("Run", "RunTimesLimit"))
        for i in range(run_limit):
            if self.run_book:
                break
            logger.info(
                f"用户 {self.cur_user_item.name} - 尝试次数: {i + 1}/{run_limit}"
            )
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

            await self._push_dispatch_log(
                f"启动 BetterGI: startOneDragon {self.launch_config_name}"
            )
            logger.info(
                f"启动 BetterGI 进程: {self.script_exe_path} "
                f"{' '.join(self.bettergi_args)}"
            )

            await self.bettergi_process_manager.open_process(
                self.script_exe_path,
                *self.bettergi_args,
                target_process=self.script_target_process_info,
                # 仅当 MAS 自身未提权时才走 runas 触发 UAC；已提权时子进程自动继承
                elevated=self.script_config.get("Run", "UseAdmin") and not IS_ELEVATED,
            )

            # 启动日志监控（文件日志）
            # 传入可调用对象让监控器按日期滚动日志跨零点自动切换新文件，
            # 避免固定路径在午夜后读不到新日志行而误判超时
            await asyncio.sleep(1)
            await self.log_monitor.start_monitor_file(
                self._resolve_log_file_path, self.log_start_time
            )

            self.wait_event.clear()
            await self.wait_event.wait()
            await self.log_monitor.stop()

            if self.cur_user_log.status == "Success!":
                self.run_book = True
                self.script_info.log = (
                    "检测到 BetterGI 已完成任务\n正在等待 BetterGI 自行退出"
                )
                if self.cur_user_config.get("Info", "IfScriptAfterTask"):
                    await execute_script_task(
                        Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
                        "脚本后任务",
                    )
                await asyncio.sleep(3)
                break

            logger.warning(
                f"用户 {self.cur_user_item.name} - BetterGI 代理异常: "
                f"{self.cur_user_log.status}"
            )
            self.script_info.log = f"{self.cur_user_log.status}\n正在中止相关程序"
            await self.kill_managed_process()
            try:
                await Notify.push_plyer(
                    "BetterGI 自动代理出现异常！",
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

    async def _run_plan_combat(self) -> bool:
        """路径 B：用 ``--startGroups MAS一条龙`` 直连执行层跑战斗 4 项，返回是否成功。

        单组 --startGroups 成败判定与切号一致（见 ``_switch_account``）：
        成功 = 「配置组 "MAS一条龙" 执行结束」；失败 = 执行配置组任务时失败 / 任务启动失败 /
        任务执行异常 / [FTL] / [ERR]；进程提前退出亦判失败。
        """
        group_name = one_dragon_bridge.GROUP_NAME
        try:
            one_dragon_bridge.write_one_dragon_group(
                self.script_root_path, self.plan_combat_steps
            )
        except Exception as e:
            logger.opt(exception=True).warning(f"一条龙执行层配置组生成失败: {e}")
            await self._push_dispatch_log(f"执行层配置组生成失败: {e}")
            return False

        await self._push_dispatch_log(
            f"开始执行层（战斗4项）: --startGroups {group_name}"
        )
        logger.info(
            f"用户 {self.cur_user_item.name} 启动 BetterGI 执行层: "
            f"{self.script_exe_path} --startGroups {group_name}"
        )

        # 杀旧进程，保证单实例下 --startGroups 由新进程执行
        await self.kill_managed_process()

        result: dict[str, bool] = {"success": False, "started": False}
        done_event = asyncio.Event()
        done_marker = f'配置组 "{group_name}" 执行结束'
        # [ERR]/任务执行异常 是 TaskRunner 在每个子任务 catch 里打印的「任务级」可恢复异常，
        # BGI 捕获后不 rethrow、跳过该步继续跑后续项，配置组仍能到达"执行结束"。若把它们当 fatal，
        # 会在 BGI 还想继续时强杀（见 _BGI_BUILTIN_FATAL 注释）。仅保留真正致命的标记。
        fail_markers = (
            "执行配置组任务时失败",
            "任务启动失败",
            "[FTL]",
            # 执行层 JS 脚本整体失败标记（MAS_PLAN_FAIL 抛异常后 BGI 仍会打印
            # 「配置组 ... 执行结束」，仅靠 done_marker 会把失败误判为成功）
            "MAS_PLAN_FAIL",
            # 注：MAS_STEP_FAIL 不再作为致命标记——执行层已改为单步失败跳过并继续，
            # 仅统计数量，最终按整体是否完成判定成败（2026-09-09 用户决策）。
        )

        step_failed = 0

        last_activity = time.monotonic()

        async def on_log(log_content: list[str], latest_time: datetime) -> None:
            nonlocal last_activity, step_failed
            last_activity = time.monotonic()
            log = "".join(log_content)
            # 单步失败只统计（执行层会跳过继续），不据此判负
            step_failed = log.count("MAS_STEP_FAIL")
            if done_marker in log:
                result["success"] = True
                done_event.set()
            elif any(m in log for m in fail_markers):
                result["success"] = False
                done_event.set()
            elif (
                result["started"]
                and not await self.bettergi_process_manager.is_running()
            ):
                done_event.set()

        monitor = LogMonitor(self.log_time_range, self.log_time_format, on_log)

        try:
            await self.bettergi_process_manager.open_process(
                self.script_exe_path,
                "--startGroups",
                group_name,
                target_process=self.script_target_process_info,
                elevated=self.script_config.get("Run", "UseAdmin") and not IS_ELEVATED,
            )
            result["started"] = True
            await asyncio.sleep(1)
            await monitor.start_monitor_file(
                self._resolve_log_file_path, datetime.now()
            )
            # 空闲超时循环：日志每次输出即续期，仅当日志静默超过 idle 阈值
            #（BGI 卡死）才终止，不设总时长上限。旧实现为固定 900s 墙钟，
            # 多实例执行层总耗时 20+ 分钟会被误杀（2026-09-08 实机排障：
            # 7 步在 14 分钟处被砍，末位步骤未执行）。
            while not done_event.is_set():
                    try:
                        await asyncio.wait_for(done_event.wait(), timeout=1.0)
                    except asyncio.TimeoutError:
                        pass
                    # 仅按空闲阈值判定卡死（日志持续输出即一直等，不设总时长上限）
                    if time.monotonic() - last_activity >= _BGI_PLAN_COMBAT_IDLE_TIMEOUT_SECONDS:
                        result["success"] = False
                        logger.warning(
                            f"用户 {self.cur_user_item.name} 执行层空闲超时"
                            f"（{_BGI_PLAN_COMBAT_IDLE_TIMEOUT_SECONDS}s 无日志输出）"
                        )
                        break
        except Exception as e:
            logger.opt(exception=True).warning(f"执行层执行异常: {e}")
            result["success"] = False
        finally:
            await monitor.stop()
            await self.kill_managed_process()
            with suppress(Exception):
                one_dragon_bridge.remove_one_dragon_group(self.script_root_path)

        if result["success"]:
            if step_failed:
                logger.warning(
                    f"用户 {self.cur_user_item.name} 执行层完成，"
                    f"但 {step_failed} 个步骤失败（已跳过并继续后续步骤）"
                )
                await self._push_dispatch_log(
                    f"执行层（战斗4项）完成，{step_failed} 个步骤失败已跳过"
                )
            else:
                await self._push_dispatch_log("执行层（战斗4项）完成")
        else:
            await self._push_dispatch_log("执行层（战斗4项）失败")
        return result["success"]

    async def _switch_account(self) -> bool:
        """单独执行一次切号（--startGroups），返回是否切换成功。

        未配置账号时直接返回 True（无需切换）；失败/超时返回 False，
        由调用方决定是否继续执行一条龙。
        """
        account = str(self.cur_user_config.get("Info", "Id") or "").strip()
        if not account:
            return True

        resource = str(self.cur_user_config.get("Switch", "Resource") or "官服").strip()
        uid = str(self.cur_user_config.get("Switch", "Uid") or "").strip()
        password = str(self.cur_user_config.get("Info", "Password") or "")

        # 切换模式不再单独配置，按密码是否填写推断：
        # 填密码 → 「账号+密码+OCR」，未填 → 「下拉列表」。
        # B服 无下拉/OCR 方式，由 resolve_switch_settings 强制走「B服切换另一个账号匹配+键鼠」。
        mode = "账号+密码+OCR" if password else "下拉列表"
        global_account, servers, mode = account_switch.resolve_switch_settings(
            resource, mode
        )

        # 1. 订阅脚本仓库（BetterGI 自行拉取/更新切换账号脚本）+ 生成配置组
        try:
            script_present = account_switch.ensure_switch_subscription(
                self.script_root_path
            )
            account_switch.write_switch_group(
                self.script_root_path,
                account,
                password,
                mode,
                global_account,
                servers,
                uid,
            )
        except Exception as e:
            logger.opt(exception=True).warning(f"切换账号准备失败: {e}")
            await self._push_dispatch_log(f"切换账号准备失败: {e}")
            # write_switch_group 可能已写入明文凭据后抛异常，失败路径同样脱敏，避免明文残留磁盘
            with suppress(Exception):
                account_switch.scrub_switch_group(self.script_root_path)
            return False

        await self._push_dispatch_log(
            f"开始切换账号: --startGroups {account_switch.GROUP_NAME}"
        )
        logger.info(
            f"用户 {self.cur_user_item.name} 启动 BetterGI 切换账号: "
            f"{self.script_exe_path} --startGroups {account_switch.GROUP_NAME}"
        )

        # 2. 杀旧进程，保证单实例下 --startGroups 由新进程执行
        await self.kill_managed_process()

        # 3. 脚本缺失（用户误删/初次使用）：首轮只保证订阅就绪，交给 BGI 启动后的后台
        # 自动更新补位；仅当上一轮 BGI 运行结束后脚本仍缺失，才清理本地仓库强制重建。
        # 必须放在杀进程之后，避免删掉仍被上一轮 BGI 使用或正在克隆中的仓库。
        if script_present:
            logger.info("切换账号脚本已存在于本地，BGI 启动时检查仓库更新")
            await self._push_dispatch_log("切换账号脚本已就绪，随 BGI 启动检查仓库更新")
        elif account_switch.rebuild_script_repo_if_checkout_failed(
            self.script_root_path, self.script_info.script_id
        ):
            await self._push_dispatch_log(
                "切换账号脚本上一轮仍未检出，已清理本地脚本仓库，由 BGI 启动时完整重建"
                "（若网络较慢请耐心等待）"
            )
        else:
            await self._push_dispatch_log(
                "切换账号脚本缺失，已重新订阅，等待 BGI 启动后自动下载；"
                "本轮若因此失败，下次运行会强制重建脚本仓库"
            )

        switch_success = asyncio.Event()
        switch_result = {"success": False, "started": False}
        # 已转述过到调度台的仓库进展（每个文案只推一次，避免刷屏）
        repo_progress_reported: set[str] = set()

        # 单组 --startGroups 的成功/失败判定取自 BetterGI 配置组日志：
        #   成功: 配置组 "MAS切换账号" 执行结束
        #   失败: 执行配置组任务时失败 / 任务启动失败 / [FTL]
        switch_group_done = f'配置组 "{account_switch.GROUP_NAME}" 执行结束'
        # 配置组内部仍由多个任务项组成，单个项 [ERR]/任务执行异常 是 TaskRunner 捕获后可恢复的
        # 「任务级」异常，BGI 跳过该项继续跑、配置组仍能到达"执行结束"。与一条龙 check_log 一致，
        # 不把 [ERR] 当 fatal，避免 BGI 本可续跑时被强杀。仅保留真正致命的标记。
        switch_group_fail = (
            "执行配置组任务时失败",
            "任务启动失败",
            "[FTL]",
        )

        async def on_switch_log(log_content: list[str], latest_time: datetime) -> None:
            log = "".join(log_content)

            # 转述 BGI 脚本仓库的下载/更新进展，避免下载阶段长时间无动静被误认为卡死
            if prog := _latest_repo_progress(log):
                if prog not in repo_progress_reported:
                    repo_progress_reported.add(prog)
                    await self._push_dispatch_log(prog)
            if _is_switch_script_updated(log):
                if "切换脚本已检出" not in repo_progress_reported:
                    repo_progress_reported.add("切换脚本已检出")
                    await self._push_dispatch_log(
                        "切号脚本已从仓库检出: SwitchAccountMultipleMode"
                    )

            if switch_group_done in log:
                switch_result["success"] = True
                switch_success.set()
            elif any(n in log for n in switch_group_fail):
                switch_result["success"] = False
                switch_success.set()
            elif (
                switch_result["started"]
                and not await self.bettergi_process_manager.is_running()
            ):
                # 进程已启动（search_process 确认过）后又在任务完成前退出
                switch_success.set()

        switch_monitor = LogMonitor(
            self.log_time_range, self.log_time_format, on_switch_log
        )

        try:
            await self.bettergi_process_manager.open_process(
                self.script_exe_path,
                "--startGroups",
                account_switch.GROUP_NAME,
                target_process=self.script_target_process_info,
                # 仅当 MAS 自身未提权时才走 runas 触发 UAC；已提权时子进程自动继承
                elevated=self.script_config.get("Run", "UseAdmin") and not IS_ELEVATED,
            )
            # open_process 内部 search_process 已确认目标进程存在，之后退出才算失败
            switch_result["started"] = True
            await asyncio.sleep(1)
            # 传可调用对象：跨零点时自动切换到当日新日志，避免误判超时
            await switch_monitor.start_monitor_file(
                self._resolve_log_file_path, datetime.now()
            )

            try:
                await asyncio.wait_for(
                    switch_success.wait(), timeout=_BGI_SWITCH_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                switch_result["success"] = False
                logger.warning(f"用户 {self.cur_user_item.name} 切换账号超时")
        except Exception as e:
            logger.opt(exception=True).warning(f"切换账号执行异常: {e}")
            switch_result["success"] = False
        finally:
            await switch_monitor.stop()
            await self.kill_managed_process()
            # 切号结束即脱敏配置组，避免明文账号/密码残留磁盘
            with suppress(Exception):
                account_switch.scrub_switch_group(self.script_root_path)
            # BGI 确实启动并退出过：记录脚本是否已检出，仍缺失则留下标记供下一轮
            # 强制重建仓库；BGI 根本没起来时不记录，避免因启动失败误删用户仓库
            if switch_result["started"]:
                with suppress(Exception):
                    account_switch.record_switch_checkout_result(
                        self.script_root_path, self.script_info.script_id
                    )

        if switch_result["success"]:
            await self._push_dispatch_log("切换账号完成")
            logger.success(f"用户 {self.cur_user_item.name} 切换账号完成")
        else:
            await self._push_dispatch_log("切换账号失败或超时，已中止任务")
            logger.warning(
                f"用户 {self.cur_user_item.name} 切换账号失败或超时，已中止任务"
            )
        return switch_result["success"]

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """按内置日志判定结果，未见成功日志便退出则视为异常。"""
        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log[-4000:] if len(log) > 4000 else log

        log_status = "BetterGI 正常运行中"
        user_item_status: str | None = None

        # 切队配置错误（战斗队伍名在游戏内置找不到）优先于笼统的 [ERR] 判定，
        # 并给一次指明队伍名的明确报错
        if party_err := _party_config_error(log):
            log_status = (
                f"切队失败/配置错误: 战斗队伍「{party_err}」在游戏内队伍列表中未找到"
            )
            user_item_status = "异常"
            if not self._party_err_pushed:
                self._party_err_pushed = True
                await self._push_dispatch_log(
                    f"BetterGI 运行异常：战斗队伍「{party_err}」在游戏内未找到，"
                    "请核对 MAS 里该用户的「战斗队伍」配置"
                )
        else:
            for needle, msg in _BGI_BUILTIN_FATAL:
                if needle in log:
                    log_status = msg
                    user_item_status = "异常"
                    break
            # 仅在未命中进程级致命日志时判定成功/提前退出/卡死/超时（for…else）
            else:
                if _one_dragon_sequence_done(log):
                    log_status = "Success!"
                    user_item_status = "完成"
                elif not await self.bettergi_process_manager.is_running():
                    log_status = "BetterGI 在完成任务前退出"
                    user_item_status = "异常"
                elif "[ERR]" in log and self.is_log_stalled(
                    latest_time, minutes=_BGI_ERR_STALL_MINUTES, key="err"
                ):
                    # [ERR] 后长时间无任何新日志行：BGI 既没走完收尾、也没继续推进也没退出，
                    # 判定卡死提前失败（不等 RunTimeLimit）。仍在新行推进则不触发。
                    log_status = (
                        f"BetterGI 出现 [ERR] 后 {_BGI_ERR_STALL_MINUTES} "
                        "分钟无进展（疑似卡死）"
                    )
                    user_item_status = "异常"
                elif self.is_log_stalled(
                    latest_time, minutes=self.script_config.get("Run", "RunTimeLimit")
                ):
                    log_status = "BetterGI 运行超时"
                    user_item_status = "异常"

        self.cur_user_log.status = log_status
        if user_item_status is not None:
            self.cur_user_item.status = user_item_status

        logger.debug(f"BetterGI 日志分析结果: {self.cur_user_log.status}")
        if self.cur_user_log.status != "BetterGI 正常运行中":
            logger.info(f"BetterGI 任务结果: {self.cur_user_log.status}, 日志锁已释放")
            self.wait_event.set()

    async def final_task(self):
        # 结束时先清理进程与监控
        if self.log_monitor is not None:
            with suppress(Exception):
                await self.log_monitor.stop()
        await self.kill_managed_process()

        # 任务结束后关闭原神游戏进程（Game.CloseOnFinish）
        await self._close_game()

        # 写入历史记录（对齐 General/SRC/MaaEnd/Okww 行为）
        statistic_paths: list[Path] = []
        for t, log_item in self.cur_user_item.log_record.items():
            dt = t.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone(UTC4)
            log_path = Config.build_history_log_path(
                script_name=self.script_info.name,
                user_name=self.cur_user_item.name,
                log_time=dt,
            )

            if log_item.status == "BetterGI 正常运行中":
                log_item.status = "任务被用户手动中止"

            if len(log_item.content) == 0:
                log_item.content = ["未捕获到任何日志内容"]
                log_item.status = "未捕获到日志"

            await Config.save_general_log(log_path, log_item.content, log_item.status)
            statistic_paths.append(log_path.with_suffix(".json"))

        # 一条龙分步执行报告：按执行顺序列出每步做了什么、成败与经过（供统计通知/邮件模板）。
        # 多次重试会产生多轮 log_record，若拼成一条再解析会重复出现两轮 1/N…N/N，
        # 故按轮解析：成功即停止重试、成功轮最多一个，优先取它；无成功轮时取最后一个
        # 能解析出步骤的轮次，避免末轮在打出「一条龙任务执行」前就失败而整块省略。
        # 无一条龙任务（仅配置组/未捕获到日志）时自动省略该区块。
        one_dragon_report: list[dict] | None = None
        runs = list(self.cur_user_item.log_record.values())
        success_runs = [item for item in runs if item.status == "Success!"]
        for item in reversed(success_runs or runs):
            one_dragon_report = parse_one_dragon_report("".join(item.content))
            if one_dragon_report:
                break

        if statistic_paths:
            try:
                statistics = await Config.merge_statistic_info(statistic_paths)
                if one_dragon_report:
                    statistics["one_dragon_steps"] = one_dragon_report
                statistics["user_info"] = self.cur_user_item.name
                start_time = getattr(self, "user_start_time", datetime.now())
                statistics["start_time"] = start_time.strftime("%Y-%m-%d %H:%M:%S")
                statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                statistics["user_result"] = (
                    "代理任务全部完成" if self.run_book else self.cur_user_item.result
                )
                success_symbol = "√" if self.run_book else "X"
                await push_notification(
                    "统计信息",
                    f"{datetime.now().strftime('%m-%d')} |{success_symbol}|  "
                    f"{self.cur_user_item.name} 的 BetterGI 自动代理统计报告",
                    statistics,
                    self.cur_user_config,
                )
            except Exception as e:
                # 失败不再静默：既记 ERROR 日志，也推到调度台实时日志，让用户能看到推送为何失败
                await self._push_dispatch_log(f"推送用户统计通知失败: {e}")
                logger.opt(exception=True).error(
                    f"推送 BetterGI 用户统计通知时出现异常: {e}"
                )

        await self._persist_user_run_result()

        # 用户独立配置：任务配置以 MAS 前端为准，不回读 BGI；仅还原现场（删物化组/槽位）
        self._restore_one_dragon_config()

    async def _persist_user_run_result(self) -> None:
        if self.cur_user_config is None:
            return

        if self.run_book:
            if (
                self.cur_user_config.get("Data", "ProxyTimes") == 0
                and self.cur_user_config.get("Info", "RemainedDay") != -1
            ):
                await self.cur_user_config.set(
                    "Info",
                    "RemainedDay",
                    self.cur_user_config.get("Info", "RemainedDay") - 1,
                )
            await self.cur_user_config.set(
                "Data",
                "ProxyTimes",
                self.cur_user_config.get("Data", "ProxyTimes") + 1,
            )
            await self.cur_user_config.set("Data", "LastProxyStatus", "成功")
            self.cur_user_item.status = "完成"
            logger.success(f"用户 {self.cur_user_uid} 的 BetterGI 自动代理任务已完成")
        else:
            await self.cur_user_config.set("Data", "LastProxyStatus", "失败")
            if self.cur_user_item.status != "完成":
                self.cur_user_item.status = "异常"

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        if self.cur_user_log is not None:
            self.cur_user_log.status = f"BetterGI 运行异常: {e}"
        logger.opt(exception=True).warning(f"BetterGI 自动代理任务出现异常: {e}")
        if self.wait_event is not None:
            self.wait_event.set()
        with suppress(Exception):
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="error",
                    message=f"BetterGI 自动代理任务出现异常: {e}",
                ),
            )
        with suppress(Exception):
            await self.kill_managed_process()
        with suppress(Exception):
            await self._persist_user_run_result()

        # 异常退出也要还原 BetterGI 现场（切号失败/中途崩溃不得污染原配置）
        try:
            self._restore_one_dragon_config()
        except Exception as e:
            logger.opt(exception=True).warning(
                f"异常退出后恢复 BetterGI 一条龙配置失败: {e}"
            )

        # 推送通知（复用 Notify）
        try:
            if (
                self.cur_user_log is not None
                and self.cur_user_log.status
                and self.cur_user_log.status != "Success!"
            ):
                await Notify.push_plyer(
                    "BetterGI 运行异常",
                    f"用户 {self.cur_user_item.name}：{self.cur_user_log.status}",
                    "异常",
                    3,
                )
        except Exception:
            pass

    async def _close_game(self) -> None:
        """任务结束后关闭原神游戏进程。

        按进程名逐一强制结束（含子进程），覆盖官服/B服/国际服/云原神等客户端。
        游戏对 WM_CLOSE 无响应：taskkill 不带 /F 的「优雅关闭」会一直等待进程
        退出直至 60s 超时抛异常，反而跳过后续的强制关闭（旧实现的游戏残留根因），
        故这里直接 /F 结束。taskkill 非零返回（拒绝访问/进程不存在）必须落日志，
        否则关闭失败在收尾里完全无痕、无法排查。
        """
        if not self.script_config.get("Game", "CloseOnFinish"):
            return

        await self._push_dispatch_log("任务结束，正在关闭游戏进程")
        for name in _BGI_GAME_PROCESS_NAMES:
            image = f"{name}.exe"
            try:
                result = await ProcessRunner.run_process("taskkill", "/IM", image, "/F", "/T")
                if result.returncode != 0:
                    reason = (result.stderr or result.stdout or "").strip()
                    if "没有找到进程" in reason or "not found" in reason.lower():
                        continue  # 该名称的客户端本就未运行，属正常
                    logger.warning(f"关闭游戏进程 {image} 失败: {reason}")
                    if "拒绝访问" in reason or "access" in reason.lower():
                        await self._push_dispatch_log(
                            "关闭游戏失败：游戏以管理员权限运行，MAS 无权结束。"
                            "请以管理员身份运行 AUTO-MAS，或将游戏与 BetterGI 改为普通权限启动"
                        )
                    else:
                        await self._push_dispatch_log(
                            f"关闭游戏进程 {image} 失败: {reason}"
                        )
            except Exception as e:
                logger.warning(f"关闭游戏进程 {image} 失败: {e}")
        await self._push_dispatch_log("游戏进程已关闭")

    async def kill_managed_process(self) -> None:
        """中止 BetterGI 进程（游戏进程由 BetterGI 自身管理）。"""
        if self.bettergi_process_manager is not None:
            try:
                await self.bettergi_process_manager.kill()
            except Exception as e:
                logger.opt(exception=True).warning(
                    f"通过进程管理器中止 BetterGI 进程失败: {e}"
                )
        if self.script_exe_path is not None:
            try:
                await System.kill_process(self.script_exe_path)
            except Exception as e:
                logger.opt(exception=True).warning(f"中止 BetterGI 主进程失败: {e}")
