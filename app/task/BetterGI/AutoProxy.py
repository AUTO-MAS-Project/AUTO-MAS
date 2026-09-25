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
from collections.abc import Callable
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
from app.task.proxy_helpers import (
    CONFIG_SOURCE_DIRECT,
    find_pids_by_name,
    push_dispatch_log,
    read_config_source,
)
from app.utils import (
    ProcessInfo,
    ProcessManager,
    ProcessRunner,
    get_logger,
)
from app.utils.constants import UTC4
from app.utils.LogMonitor import LogMonitor
from app.utils.platform import IS_ELEVATED

from .tools import (
    account_switch,
    account_switch_native,
    archive_mas_runtime_backup,
    game_info,
    one_dragon,
    one_dragon_bridge,
    push_notification,
    read_overlay_values,
    team_resolver,
)
from .tools.drop_statistics import parse_drop_lines
from .tools.one_dragon_plan import (
    build_combat_steps,
    parse_one_dragon_plan,
    plan_combat_bases,
    plan_steps_to_native_settings,
    resolve_base_name,
)
from .tools.one_dragon_report import (
    count_failed_custom_items,
    parse_execution_layer_report,
    parse_one_dragon_report,
)

logger = get_logger("BetterGI 自动代理")

# 掉落统计（数据源 = BGI 的「奖励识别」）可覆盖的战斗步骤基名：BGI 只在自动秘境与
# 自动首领讨伐暴露了 RewardRecognitionEnabled（幽境危战无此能力，故不列入）。
# ⚠️ 该常量与下面的强制开启逻辑、parse_drop_lines 调用、statistics["drop_statistics"]
#    写入，曾在合并 9 个 PR 时整段丢失（解析模块与通知模板都在、调用点没了，表现为
#    「开了掉落统计但通知里没有掉落表」）。补回时四处必须一起补，只补解析仍是空表。
_REWARD_RECOGNITION_STEP_BASES = frozenset({"自动秘境", "自动首领讨伐"})
# 一条龙队列中「走路径 B 执行层（--startGroups）」的自定义类型：配置组 / 脚本 / 路径 / 录制。
# 与 BUILTIN_COMBAT_STEP_NAMES 的内置战斗 4 项并列——战斗 4 项由 MASOneDragon 自编排执行层接管，
# 本集合由 --startGroups 逐个配置组直连执行（均物化为 MAS-{短id}-自定义配置组{N} 配置组后运行）。
CUSTOM_EXEC_KINDS = frozenset({"js", "pathing", "scriptgroup", "keymouse"})

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

# 执行层「必填配置缺失」标记（由 MASOneDragon/main.js 打出）：右栏必填项（如自动首领
# 讨伐的首领）未填时，main.js 不进 BGI 直接跳过该步并打本标记。字段布局与
# MAS_STEP_FAIL 一致：``MAS_STEP_MISSING_CONFIG: <步骤 uid> <步骤名> <原因>``。
#
# ⚠️ 与 MAS_STEP_FAIL 的分工：后者是运行期异常（识别失败等），按既有决策「单步失败跳过
# 继续、仅统计数量不判负」；本标记是前置配置错误、重试无用，必须判负并让用户看见——否则
# 该步被静默跳过、整轮仍报成功，用户表现为「一条龙直接完成」而任务其实没跑。
_BGI_MISSING_CONFIG_RE = re.compile(
    r"MAS_STEP_MISSING_CONFIG:\s*(\S+)\s+(\S+)\s+([^\r\n]+)"
)

# 执行层「部分失败」汇总标记（main.js 收尾打出）：捕获组 = 失败并已被跳过的步数。
# 按 2026-09-09 决策单步失败仍不判负（跳过继续、计入成功），但必须据此把状态改成
# 「部分失败」并让通知带上分步表，否则会出现「地脉花没打却显示成功」（2026-09-15 实机）。
_MAS_PLAN_DONE_WITH_FAILURES_RE = re.compile(r"MAS_PLAN_DONE_WITH_FAILURES\s+(\d+)")

# 切换账号单独执行的超时（秒），超时视为失败并继续一条龙
_BGI_SWITCH_TIMEOUT_SECONDS = 600

# 路径 B 执行层（战斗 4 项 --startGroups MAS一条龙）单独执行的超时（秒）
# 执行层空闲超时：on_log 每次收到日志即续期；仅当日志静默超过该时长才判定卡死。
# （旧实现为固定 900s 墙钟，多实例执行层总耗时可超 20 分钟会被误杀——2026-09-08 实机排障。）
_BGI_PLAN_COMBAT_IDLE_TIMEOUT_SECONDS = 300

# BetterGI 是单实例：带参启动（startOneDragon / --startGroups）会被已在运行的实例吞掉，
# 而对侧不会执行任何任务——表现为「一直卡住、游戏不启动」（2026-09-15 实机：MAS 未提权 +
# Run/UseAdmin=true 时 BGI 被 runas 提权启动，MAS 反而无权终止自己拉起的这个进程）。
# 故旧实例杀不掉时必须立即中止并给出可操作原因，不能继续启动后干等。
_BGI_UNKILLABLE_HINT = (
    "BetterGI 旧进程无法终止（它可能由 MAS 以管理员权限启动，而 MAS 自身未提权）："
    "请先手动关闭 BetterGI，或以管理员身份运行 MAS 后重试"
)

# 「杀进程后按进程名复核」的轮询参数：taskkill 报成功 ≠ 进程已消失（2026-09-15 实机：
# 报成功 3ms 后仍能扫到残留，导致误判「杀不掉」并白中止一次），必须留出真正退出的时间。
_BGI_EXIT_VERIFY_ATTEMPTS = 6
_BGI_EXIT_VERIFY_INTERVAL = 0.5


async def _wait_bgi_exit(
    attempts: int = _BGI_EXIT_VERIFY_ATTEMPTS,
    interval: float = _BGI_EXIT_VERIFY_INTERVAL,
) -> list[int]:
    """按进程名轮询等待 BetterGI 完全退出，返回仍未退出的 PID 列表（空列表=已退干净）。

    两条都必须按进程名复核：``taskkill`` 返回成功不代表进程已经消失；
    ``System.kill_process`` 还会把「读不到 exe 路径」的提权实例归入 uncertain_pids 而漏判成功。
    """
    remaining: list[int] = []
    for _ in range(attempts):
        remaining = await asyncio.to_thread(find_pids_by_name, _BGI_TRACK_PROCESS_NAME)
        if not remaining:
            return []
        await asyncio.sleep(interval)
    return remaining


# BetterGI 管理的原神游戏进程名，取自 BetterGI 源码
# TaskContext.GetGenshinGameProcessNameList()；任务结束后按此顺序逐一尝试关闭。
# 上游给出的是不含后缀的主名，此处补成完整映像名——psutil 的 name 与 taskkill /IM
# 要的都是完整映像名，只带主名会让 find_pids_by_name 的精确比较恒不命中
# （ZzzOd / OkNte 同类常量同此口径）
_BGI_GAME_PROCESS_NAMES: tuple[str, ...] = (
    "YuanShen.exe",  # 官服 / B服（国服）
    "GenshinImpact.exe",  # 国际服
    "Genshin Impact Cloud Game.exe",  # 云原神（国际）
    "Genshin Impact Cloud.exe",  # 云原神（备用进程名）
)
# 本地客户端进程名（官服/B服/国际服共用）：混服路径校验只针对本地客户端，
# 云原神无本地安装路径概念，不参与存活客户端与用户路径的一致性比较
_BGI_LOCAL_GAME_PROCESS_NAMES: tuple[str, ...] = ("YuanShen.exe", "GenshinImpact.exe")

# 用户服务器（Switch.Resource）→ 应使用的客户端渠道；客户端渠道由
# game_info.detect_channel 识别（config.ini channel/cps + 主程序名）
_RESOURCE_EXPECTED_CHANNEL: dict[str, str] = {
    "官服": "官服",
    "B服": "B服",
    "亚服": "国际服",
    "欧服": "国际服",
    "美服": "国际服",
    "港澳台服": "国际服",
}


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


# ── 进副本后「打不了 / 卡在副本里」的提示 ─────────────────
# 战斗队伍在游戏内存在、但 BGI 拿它匹配不到自动战斗脚本时（AutoDomainTask →
# CombatScriptBag.FindCombatScript 打「未匹配到任何战斗脚本」），BGI 会把自动秘境直接结束掉：
# 副本进了、仗没打，人还留在副本里；紧接着领奖的切队也会因「未能返回主界面」失败。
# 两种情况 BGI 都照打「任务结束」继续后面的任务，只看收尾标记会整条判成功——这里给用户
# 可操作的原因（分步表判失败由 one_dragon_report._BGI_STEP_FATAL_HINTS 负责）。
_BGI_PARTY_ROLES_RE = re.compile(r'识别到的队伍角色[:：]\s*"([^"]+)"')


def _combat_script_miss_hint(log: str) -> str | None:
    """「队伍匹配不到自动战斗脚本」（进副本后无法开打）的用户可读提示；无则 None。"""
    if "未匹配到任何战斗脚本" not in log:
        return None
    roles = _BGI_PARTY_ROLES_RE.findall(log)
    party = roles[-1].strip() if roles else ""
    who = f"队伍「{party}」" if party else "当前队伍"
    return (
        f"{who}在 BGI 的自动战斗里没有匹配的脚本，进副本后无法开打（该任务被跳过）；"
        "请在 BGI「自动战斗」里为该队伍配置脚本，或改用已有脚本的队伍"
    )


def _back_to_main_failed_hint(log: str) -> str | None:
    """「切队回不到主界面」（游戏被留在副本/子界面）的用户可读提示；无则 None。"""
    if "未能返回主界面" not in log:
        return None
    return (
        "切换队伍失败：游戏被留在副本/子界面（未能返回主界面），"
        "本次领奖等后续步骤未干成；请手动回到主界面后重试"
    )


def _missing_config_reasons(log: str) -> list[str]:
    """从执行层累计日志提取「必填配置缺失」的用户可读原因（``步骤名：原因``）。

    标记行含步骤 uid，对用户无意义；这里只保留步骤名与原因，直接用于调度台/日志
    提示（如「自动首领讨伐：未选择首领」）。同一原因重复出现由调用方去重。
    """
    return [
        f"{m.group(2)}：{m.group(3).strip()}"
        for m in _BGI_MISSING_CONFIG_RE.finditer(log)
    ]


def _merge_one_dragon_reports(*phases: list[dict] | None) -> list[dict] | None:
    """把各相的分步表按执行顺序拼成一张表，并重编号 ``1/N…N/N``。

    一次任务最多两相：执行层（``--startGroups`` 直连战斗 4 项）先跑、原生一条龙（日常）
    后跑，拼起来就是真实执行顺序。两相各自都从 1 开始编号，直接拼会出现两个 ``1/4``、
    ``1/3``，故按合并后的长度重编号；相内顺序与各步的 ``start``/``end`` 原样保留。
    全部相都没有步骤时返回 None，调用方据此省略通知里的整块。
    """
    merged: list[dict] = []
    for steps in phases:
        for step in steps or []:
            merged.append({**step, "index": len(merged) + 1})
    if not merged:
        return None
    for step in merged:
        step["total"] = len(merged)
    return merged


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
        # 配置来源决定「谁拥有本次运行的配置」：直控 = 用 BGI 所选原生配置，MAS 不接管
        # （一条龙配置名回到 Task.OneDragonConfigName，前端也据此显示原生控件）；
        # 脚本/用户 = MAS 侧配置（脚本级共享 / per-user 独立）。
        # 注：快速配置不参与这里的判定——它在直控下的语义是「要不要把面板值写入
        # 原生配置」，与「用哪份配置启动」是两件事，混在一起会让直控被锁回 MAS 槽位。
        # （合并 dev #781「全专项快速配置开关语义」时保留本分支这一语义：见下 writes_native_config。）
        self.config_mode = read_config_source(self.cur_user_config)
        # 配置来源决定「谁拥有本次运行的配置」：直控 = 用 BGI 所选原生配置，MAS 不接管；
        # 脚本/用户 = MAS 侧配置。**快速配置不参与这个判定**（维护者决策：放弃把快速配置
        # 当作配置来源开关）——它在直控下只表示「要不要把面板值写进那份原生配置」，
        # 见下方 writes_native_config。
        # 注：此处与 dev #781 的 use_mas_config = IfQuickConfig 相左，PR 内已同步调整 dev 的
        # test_quick_config_sources 相应断言，评审时请一并确认。
        self.use_mas_config = self.config_mode != CONFIG_SOURCE_DIRECT
        # 直控 + 快速配置开启：把面板值写入 BGI **那份原生配置**（运行前快照、结束还原）。
        # 与 use_mas_config 分开：后者只决定「用哪份配置启动」，这里决定「要不要接管写入」。
        # ⚠️ 该开关已从 BetterGI 用户页隐藏，改由配置来源派生（BetterGIUserConfig.load：
        # 直控 = 关，脚本 / 用户 = 开），故此处对直控恒为假 —— 整条 _write_native_one_dragon
        # 路径当前不可达（含一条龙平面周表键那部分写入）。按维护者决策保留实现，
        # 将来若恢复开关可直接复用。
        self.writes_native_config = self.config_mode == CONFIG_SOURCE_DIRECT and bool(
            self.cur_user_config.get("Info", "IfQuickConfig")
        )
        # 原生配置的运行前快照与本次写入内容（还原前比对，保护运行期间的外部修改）
        self._native_one_dragon_snapshot: dict | None = None
        self._native_one_dragon_written: dict | None = None
        self.cur_user_log: LogRecord | None = None
        self.bettergi_process_manager: ProcessManager | None = None
        # MAS 方式切号的托管游戏启动器（游戏不随后端退出，见
        # _mas_launch_game_for_switch 的 breakaway 说明）
        self.switch_game_manager: ProcessManager | None = None
        self.wait_event: asyncio.Event | None = None
        self.script_root_path: Path | None = None
        self.script_exe_path: Path | None = None
        self.script_target_process_info: ProcessInfo | None = None
        self.log_monitor: LogMonitor | None = None
        # 切队配置错误报错只推送一次，避免每个日志回调重复刷屏
        self._party_err_pushed = False
        # 运行时提示（找不到自动战斗脚本、切队回不到主界面）同样只推一次
        self._bgi_hints_pushed: set[str] = set()

    async def check(self) -> str:
        # 跨日重置：必须在 ProxyTimesLimit 上限比较之前完成，否则昨日达上限的用户
        # LastProxyDate/ProxyTimes 永不被重置，从次日起被永久跳过（对齐 ZzzOd）。
        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        if self.cur_user_config.get("Data", "LastProxyDate") != self.curdate:
            await self.cur_user_config.set("Data", "LastProxyDate", self.curdate)
            await self.cur_user_config.set("Data", "ProxyTimes", 0)

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

        # MAS 方式切号的前置校验（对齐 MaaEnd：不满足直接报错而非运行期失败）。
        # MAS 侧实现覆盖官服（miHoYo 登录界面）与B服（bilibili 登录记录面板）；
        # 国际服请沿用 BetterGI 脚本方式（Run.AccountSwitchMethod = BGI）。
        # 只校验「填了账号、要执行切号」的用户：未配账号 = 不切号，对任何服务器都是
        # 合法配置（国际服未配账号不应被拦，2026-09-24 复核）。
        method = self._account_switch_method()
        resource = str(self.cur_user_config.get("Switch", "Resource") or "官服").strip()
        account = str(self.cur_user_config.get("Info", "Id") or "").strip()
        if method == "MAS" and account:
            if resource == "官服":
                if not str(self.cur_user_config.get("Info", "Password") or ""):
                    # 无密码走下拉列表匹配，要求账号能生成掩码锚点（手机号/邮箱）；
                    # 第三方登录账号没有打码锚点，无法在登录记录中定位
                    if "*" not in account_switch.mask_account(account):
                        self.cur_user_item.status = "异常"
                        return (
                            "MAS 方式下拉列表切换需要手机号或邮箱账号，"
                            "第三方登录账号请填写密码走账号+密码方式"
                        )
            elif resource != "B服":
                self.cur_user_item.status = "异常"
                return (
                    "MAS 方式账号切换暂仅支持官服/B服用户，"
                    "请改回 BetterGI 脚本切换方式或调整该用户的服务器"
                )
            # B服的「账户」字段即B站用户名：未填时由外层 account 条件放行、运行期
            # 跳过切换（同 OK-WW 未配置账号语义），填了即按昵称匹配选号

        # 渠道一致性校验（仅对填了账号、要执行切号的用户）：官服/B服/国际服是三个
        # 互相隔离的客户端（B站账号无法登录官服客户端），客户端渠道与用户服务器
        # 不符时整条任务链都不成立，提前给出可操作错误而非运行期莫名失败。
        # 不切号的用户不校验——其 Switch.Resource 可能只是未改动的默认值。
        if account:
            expected = _RESOURCE_EXPECTED_CHANNEL.get(resource)
            if expected:
                info = game_info.read_game_info(
                    root, str(self.cur_user_config.get("Switch", "GamePath") or "")
                )
                if info["channel"] and info["channel"] != expected:
                    self.cur_user_item.status = "异常"
                    return (
                        f"该用户服务器为 {resource}，但游戏客户端是"
                        f"{info['channel']}客户端（{info['installPath']}）；"
                        "请在用户配置中为该用户指定对应的游戏客户端路径，"
                        "或调整 BetterGI 的游戏路径"
                    )

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
        self.one_dragon_groups = (
            list(self.cur_user_config.get("OneDragon", "Groups") or [])
            if self.use_mas_config
            else []
        )
        self.use_custom_groups = self.use_mas_config and bool(
            self.cur_user_config.get("OneDragon", "IfUseCustomGroups")
        )
        self.one_dragon_custom_groups = (
            one_dragon.parse_custom_groups(
                self.cur_user_config.get("OneDragon", "CustomGroups") or ""
            )
            if self.use_mas_config
            else []
        )
        # 「队伍配置」总开关与队伍表：开启时按「战斗场景」选队（第 1 层优先级）；
        # 关闭时数据保留但除通用队伍外一律不参与匹配（通用队伍照旧生效）。
        self.use_teams = self.use_mas_config and bool(
            self.cur_user_config.get("OneDragon", "IfUseTeams")
        )
        self.one_dragon_teams = (
            team_resolver.parse_teams(
                self.cur_user_config.get("OneDragon", "Teams") or ""
            )
            if self.use_mas_config
            else []
        )
        # 可视化队列（有序条目，含重复实例）：决定运行时 TaskOrder 重建顺序；
        # 为空/非法时 write_user_one_dragon 回退旧行为（沿用副本 TaskOrder 相对顺序）
        self.one_dragon_queue = (
            one_dragon.parse_one_dragon_queue(
                self.cur_user_config.get("OneDragon", "Queue") or ""
            )
            if self.use_mas_config
            else []
        )
        # 直控模式（非用户独立配置）下 MAS 不干预一条龙：禁用执行层与自定义项执行层，
        # 仅按所选实配名裸跑 BGI 一条龙（启动参数已固定 startOneDragon <configName>）。
        # 否则残留的 UseExecutionLayer/Plan/Queue 会触发路径 B 执行层，违背直控设计初衷。
        self.use_execution_layer = bool(self.use_mas_config) and bool(
            self.cur_user_config.get("OneDragon", "UseExecutionLayer")
        )
        # 路径 B（自定义项执行层）：队列中 kind ∈ CUSTOM_EXEC_KINDS 的条目与战斗 4 项一起，
        # 由 one_dragon_bridge 按左栏队列顺序切成「段」（MAS-{短id}-执行层段{N}），在**同一次**
        # ``--startGroups <段名...>`` 里顺序执行。本类只负责计算「是否有自定义项需由执行层
        # 接管」与门控；具体段名在 _write_one_dragon_config 切段时确定（见 main_task）。
        self.custom_exec_items = [
            q
            for q in (self.one_dragon_queue or [])
            if str(q.get("kind", "")) in CUSTOM_EXEC_KINDS
            and str(q.get("name", "")).strip()
        ]
        self.custom_exec_enabled = self.use_execution_layer and bool(
            self.custom_exec_items
        )
        # 路径 B 执行层开关与 Plan：UseExecutionLayer 开且 Plan 含启用的战斗 4 项时进入 plan 模式。
        # 只有「Plan 中配过该组」且「队列中该条目启用」的战斗组才由执行层接管，其余战斗组
        # 留在一条龙副本（_write_one_dragon_config 只剔除实际接管的组，避免重复执行）。
        # 条件比 dev #781 宽一档：直控 + 快速配置时**要**算 Plan——那一路由
        # _write_native_one_dragon 把 Plan 写成原生设置，不算出来就没内容可写。
        _plan_steps = (
            parse_one_dragon_plan(self.cur_user_config.get("OneDragon", "Plan") or "")
            if (self.use_mas_config or getattr(self, "writes_native_config", False))
            else []
        )
        # 这次实际跑谁：Plan 中启用、且队列行启用、且组开关允许的战斗 4 项（各带自身 settings）。
        self.plan_combat_steps = build_combat_steps(
            _plan_steps, self.one_dragon_queue, self.one_dragon_groups
        )
        # 谁归执行层负责（不看启停）：只要 Plan 里配过该战斗组的实例，就不再交回原生一条龙
        # 执行——开则由战斗段跑，关则本次不跑。_write_one_dragon_config 用它决定原生副本
        # 剔除谁；不能用 plan_mode 代替：全部行都关掉时 plan_mode 为假，战斗项会整体落回
        # 原生副本照跑，与界面「已关」不符（2026-09-12 实机排障）。
        self.plan_combat_bases = plan_combat_bases(_plan_steps)
        # 路径 B 回退：顶层「通用战斗队伍」(OneDragon.PartyName) 默认填入各战斗步骤的
        # 队伍字段，与路径 A（write_user_one_dragon 把 PartyName 写入秘境/首领，并经
        # apply_global_battle_team 写入地脉花/幽境全局配置）保持一致。仅在对应的 per-group
        # 队伍字段为空时注入，已显式设置的队伍不覆盖。
        _default_party = (
            str(self.cur_user_config.get("OneDragon", "PartyName") or "").strip()
            if (self.use_mas_config or getattr(self, "writes_native_config", False))
            else ""
        )
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
        # 掉落统计（用户级开关，默认开）：数据源是 BGI 的「奖励识别」，因此开启时强制把
        # 本次会跑的战斗步骤打开识别（执行层走 Plan.settings），并在运行前把 BGI 全局
        # autoDomainConfig.rewardRecognitionEnabled 置 true（覆盖原生一条龙路径）。
        self.drop_statistics_enabled = bool(
            self.cur_user_config.get("Notify", "IfSendDropStatistics")
        )
        if self.drop_statistics_enabled:
            for _step in self.plan_combat_steps:
                if (
                    resolve_base_name(str(_step.get("name", "")))
                    not in _REWARD_RECOGNITION_STEP_BASES
                ):
                    continue
                _settings = _step.get("settings")
                if not isinstance(_settings, dict):
                    _settings = {}
                    _step["settings"] = _settings
                _settings["rewardRecognitionEnabled"] = True

        # 第 1 层（最高优先级）：队伍配置表按「战斗场景」匹配选队，写入独立的
        # masTeamOverride / masStrategyOverride，由执行层 main.js 以最高优先级读取，
        # 从而压过每周行与步骤级字段（「按任务决定队伍」优先于「按日期决定」）。
        # 只在总开关开启且表非空时介入；随机在一次运行内固定（此处一次性解析）。
        if self.use_teams and self.one_dragon_teams:
            _hit = team_resolver.apply_teams_to_steps(
                self.plan_combat_steps, self.one_dragon_teams
            )
            logger.info(
                f"队伍配置：总开关开启，{len(self.one_dragon_teams)} 个队伍参与匹配，"
                f"{_hit} 个战斗步骤按场景命中队伍"
            )
        self.plan_mode = self.use_execution_layer and bool(self.plan_combat_steps)
        self.launch_config_name = self.one_dragon_config
        self.bettergi_args = ["startOneDragon", self.launch_config_name]

        self.run_book = False

        # 通用战斗队伍/策略落到全局 config.json 前的叶子快照，None 表示尚未接管
        self._reseed_global_config: dict | None = None
        # 本次物化到 BGI User/ScriptGroup 的前缀配置组文件（运行结束删除）
        self._materialized_script_groups: list[Path] = []
        # 执行层「段」组文件与组名（按左栏队列顺序切分，运行结束删除）
        self._materialized_exec_groups: list[Path] = []
        self.exec_group_names: list[str] = []
        # 执行层「部分失败」的步数：单步失败已跳过继续、不判负，但状态/通知要标出来
        self.partial_failed_steps = 0

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
            # 直控来源：快速配置开启才接管写入，且写的是 BGI 那份原生配置（非 MAS 槽位）
            self._write_native_one_dragon(exclude_task_names=exclude_task_names)
            return
        party_name = str(self.cur_user_config.get("OneDragon", "PartyName") or "")
        # 路径 B：战斗 4 项由执行层直连，原生一条龙只跑日常 + 自定义组。
        # 把归执行层负责的战斗组一律从原生副本剔除，使前端开关成为唯一真理源：开 → 执行层
        # 跑（战斗段）；关（Plan.step.enabled=false）→ 原生也不跑，避免「关了还漏跑」。
        # **不能按 plan_mode 门控**：全部行都关掉时 plan_mode 为假，那样战斗项会整体落回
        # 原生副本照跑（2026-09-12 实机排障）。
        # 归属口径与 build_combat_steps 对齐：队列非空时队列是编排真相源，只剔除「入队且在
        # Plan 中配过」的战斗组（未入队的孤儿实例执行层也不跑，故留原生副本按 Groups 兜底）；
        # 队列为空（用户从未维护过可视化队列，Plan/Groups 由开关直接改写）时它不做队列过滤，
        # 直接接管 Plan 中启用的战斗实例，此时必须整批剔除 Plan 里的战斗组——否则界面已关
        # 的行仍留在 Groups 里，原生一条龙会照跑（2026-09-23 实机：只开「领取邮件」的用户
        # 被跑出 5 个任务）。
        # Plan 里没有实例的战斗组（异常存量/尚未配过）仍留在原生副本：宁可多跑一次，
        # 也不静默丢掉界面上开着的任务。
        # 日常 4 项不在战斗集合内，仍按 OneDragon.Groups 在原生一条龙启停（单开关已对齐）。
        _exclude: set[str] = set(exclude_task_names or ())
        if self.use_execution_layer:
            if self.one_dragon_queue:
                _queue_bases = {
                    base
                    for q in self.one_dragon_queue
                    if (base := resolve_base_name(str(q.get("name", ""))))
                }
                _exclude |= self.plan_combat_bases & _queue_bases
            else:
                _exclude |= set(self.plan_combat_bases)
        # 执行层接管的自定义项同样从原生副本剔除：它们改由执行层「段」承载
        # （见下方 build_execution_segments），不剔除会与原生一条龙重复执行。
        if self.custom_exec_enabled:
            _exclude |= set(
                one_dragon_bridge.custom_exec_names(
                    self.one_dragon_queue, CUSTOM_EXEC_KINDS
                )
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
            exclude_task_names=sorted(_exclude) or None,
            # 掉落统计：开启时强制打开首领讨伐的奖励识别（原生路径读槽位顶层字段）
            boss_reward_recognition=True if self.drop_statistics_enabled else None,
            # 执行层接管时不再逐项物化自定义配置组（避免与「段」重复）
            materialize_custom_groups=not self.custom_exec_enabled,
        )
        # 执行层「段」：按左栏队列顺序切段并写入 BGI 配置组（战斗段 + 自定义项同批），
        # 随后由 ``_run_execution_layer`` 用**一次** ``--startGroups <段名...>`` 顺序跑完。
        self._materialized_exec_groups = []
        self.exec_group_names = []
        if self.plan_mode or self.custom_exec_enabled:
            self._materialized_exec_groups = one_dragon_bridge.write_execution_groups(
                self.script_root_path,
                self.cur_user_item.user_id,
                one_dragon_bridge.build_execution_segments(
                    self.script_root_path,
                    self.script_info.script_id,
                    self.cur_user_item.user_id,
                    self.one_dragon_queue or [],
                    self.plan_combat_steps,
                    CUSTOM_EXEC_KINDS,
                ),
            )
            self.exec_group_names = [
                str(p.stem) for p in self._materialized_exec_groups
            ]
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
        # 掉落统计：把「启用奖励识别」写进全局 autoDomainConfig 段。必须排在用户副本
        # 物化**之后**（副本里的值可能是关，先写会被覆盖回 false）；该叶子已含在运行时
        # 快照集合内，运行结束随队伍/策略一起还原，不留残留。
        if self.drop_statistics_enabled:
            one_dragon.apply_global_reward_recognition(self.script_root_path)
        logger.info(
            f"已写入用户 {self.cur_user_item.name} 的独立一条龙配置（槽位 "
            f"{one_dragon.launch_slot_name()}），物化配置组 {len(self._materialized_script_groups)} 个"
        )

    def _write_native_one_dragon(
        self, exclude_task_names: list[str] | None = None
    ) -> None:
        """直控 + 快速配置开启：把面板值写入 BGI **那份原生一条龙配置**。

        不建 MAS 槽位、不物化 ``MAS-`` 前缀配置组（原生配置引用的是用户自己的组）。
        写入内容留档给 ``_restore_one_dragon_config`` 比对，用于保护运行期间的外部修改。
        直控下执行层被禁用（见 ``use_execution_layer``），故不需要路径 B 的剔除参数。
        """
        if self._native_one_dragon_snapshot is None:
            # 快照阶段没读到原生配置（文件缺失/非法）：本次不接管，避免写出一份空配置
            return
        party_name = str(self.cur_user_config.get("OneDragon", "PartyName") or "")
        written = one_dragon.write_native_one_dragon(
            self.script_root_path,
            self.one_dragon_config,
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
            exclude_task_names=exclude_task_names,
            # 四项战斗组的 per-任务设置（树脂/奖励识别/秘境界/首领名…）：
            # 直控下执行层不跑，Plan 只有这里会落到原生配置
            native_step_settings=plan_steps_to_native_settings(self.plan_combat_steps),
        )
        if written is None:
            return
        self._native_one_dragon_written = written
        # 通用战斗队伍/策略与幽境/秘境的全局叶子：与 MAS 槽位路径同口径补写
        # （原生路径同样读 config.json 这些段），结束由 _restore_one_dragon_config 还原
        one_dragon.apply_global_battle_team(self.script_root_path, party_name)
        one_dragon.apply_global_battle_strategy(
            self.script_root_path,
            str(self.cur_user_config.get("OneDragon", "AutoBossStrategyName") or ""),
        )
        one_dragon.apply_user_global_stygian_settings(
            self.script_root_path,
            self.script_info.script_id,
            self.cur_user_item.user_id,
        )
        one_dragon.apply_user_global_domain_settings(
            self.script_root_path,
            self.script_info.script_id,
            self.cur_user_item.user_id,
        )
        logger.info(
            f"已把用户 {self.cur_user_item.name} 的面板值写入一条龙配置"
            f"「{self.one_dragon_config}」（直控 + 快速配置）"
        )

    def _backup_one_dragon_config(self) -> None:
        """运行前快照乐观覆盖的全局 config.json 队伍/策略叶子，供结束后还原。

        独立配置模式下 per-user 配置落到 MAS 专属槽位，不写 BGI 同名实配；BGI 那套
        一条龙文件无需备份。全局 config.json 的队伍/策略叶子（地脉花/幽境危战/秘境读段）
        仍需运行时临时补写、结束还原，故这里先快照。同时清理上一轮强杀可能残留的
        前缀物化组（只命中 MAS-{短id}-自定义配置组*，不碰 BGI 本体）。

        直控来源且快速配置开启时改为接管 **BGI 那份原生一条龙配置**：先整份快照，
        再连同全局叶子一起补写，运行/异常结束由 ``_restore_one_dragon_config`` 还原。
        """
        if not self.use_mas_config:
            if not self.writes_native_config:
                return
            self._native_one_dragon_snapshot = one_dragon.read_native_one_dragon(
                self.script_root_path, self.one_dragon_config
            )
            if self._native_one_dragon_snapshot is None:
                logger.warning(
                    f"用户 {self.cur_user_item.name} 直控快速配置：未找到一条龙配置"
                    f"「{self.one_dragon_config}」，本次不写入面板值"
                )
            self._reseed_global_config = one_dragon.snapshot_global_battle_config(
                self.script_root_path
            )
            return
        one_dragon.cleanup_leftover_mas_groups(
            self.script_root_path,
            self.script_info.script_id,
            self.cur_user_item.user_id,
        )
        # 上一轮被强杀时残留的执行层「段」组一并清理，避免常驻 BGI 配置组列表
        one_dragon_bridge.cleanup_leftover_execution_groups(
            self.script_root_path, self.cur_user_item.user_id
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
            # 直控 + 快速配置：只还原本次真正写过的那份原生配置；先在写前比对——运行期间
            # 被外部改过的配置保留外部改动（与各专项「发现外侧新修改时保护该修改」同口径）
            if self.writes_native_config:
                if self._native_one_dragon_written is not None:
                    native_path = one_dragon.one_dragon_path(
                        self.script_root_path, self.one_dragon_config
                    )
                    current = one_dragon.read_file(native_path)
                    if current == self._native_one_dragon_written:
                        if self._native_one_dragon_snapshot is not None:
                            one_dragon.write_file(
                                native_path, self._native_one_dragon_snapshot
                            )
                    else:
                        logger.warning(
                            f"用户 {self.cur_user_item.name} 的一条龙配置在运行期间被外部"
                            "修改，保留该修改、不做还原"
                        )
                if self._reseed_global_config is not None:
                    one_dragon.restore_global_battle_config(
                        self.script_root_path, self._reseed_global_config
                    )
                self._native_one_dragon_written = None
                self._native_one_dragon_snapshot = None
                self._reseed_global_config = None
            return
        try:
            one_dragon.remove_materialized_script_groups(
                self.script_root_path, self._materialized_script_groups
            )
            self._materialized_script_groups = []
            one_dragon_bridge.remove_execution_groups(
                self.script_root_path, self._materialized_exec_groups
            )
            self._materialized_exec_groups = []
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

    def _native_one_dragon_task_names(self) -> list[str]:
        """本次启动的一条龙配置里「启用的一条龙内置任务」名（按 ``TaskOrder`` 顺序）。

        原生进度行 ``一条龙任务执行: X/N`` 只有序号没有任务名，统计通知的分步表要靠这份
        顺序表才能把序号还原成任务名（见 ``tools.one_dragon_report``）。读配置失败时返回
        空表——解析器会退回日志行内推断，不能让一条辅助信息拖垮整次通知。
        """
        try:
            cfg = one_dragon.load_one_dragon(
                self.script_root_path, self.launch_config_name
            )
        except (OSError, ValueError, KeyError, TypeError) as e:
            logger.warning(f"用户 {self.cur_user_item.name} 一条龙任务名读取失败: {e}")
            return []
        names = one_dragon.enabled_one_dragon_task_names(cfg)
        # 留痕：分步表任务名对不上时，先看这行就知道是配置读不到还是顺序表与本次运行不符
        logger.info(
            f"用户 {self.cur_user_item.name} 原生一条龙任务名（按配置顺序）: {names}"
        )
        return names

    async def main_task(self):
        await self.prepare()

        self.cur_user_item.status = "运行"

        # 切换账号（单独执行 --startGroups，先于一条龙）
        if not await self._switch_account():
            self.cur_user_item.status = "异常"
            self.script_info.log = "切换账号失败，已中止任务"
            logger.error(f"用户 {self.cur_user_item.name} 切换账号失败，中止任务")
            return

        # 用户独立配置：先备份现场再写入，结束后 (final_task/on_crash) 还原
        self._backup_one_dragon_config()
        # 物化前归档本用户 per-user 副本 + 页面字段（运行会把字段物化进副本
        # 与 BGI 槽位、覆盖副本内容；指纹去重，失败不阻断运行）。native 池
        # 由 manager.prepare 在任务级一次性归档
        with suppress(Exception):
            archive_mas_runtime_backup(
                self.script_info.script_id,
                str(self.cur_user_uid),
                read_overlay_values(self.cur_user_config),
            )
        self._write_one_dragon_config()

        # 路径 B：执行层（战斗段 + 自定义项）在**一次** BGI 进程里按左栏队列顺序跑完，
        # 组名由 _write_one_dragon_config 切段时确定。失败不再中止任务：日常 4 项（领奖类）
        # 与执行层无依赖，仍由随后的一条龙承接，避免执行层异常连坐吞掉日常收益
        # （2026-09-08 用户决策：记录警告但继续）。
        exec_ok = True
        if self.exec_group_names:
            exec_ok = await self._run_execution_layer()
            if not exec_ok:
                self.script_info.log = "执行层失败，继续执行一条龙日常"
                logger.warning(
                    f"用户 {self.cur_user_item.name} 执行层失败，记录警告并继续一条龙日常"
                )

        # 原生一条龙（阶段2）无启用任务：不再启动 BetterGI，避免空一条龙进程不退出导致任务挂死。
        # 路径 B 下战斗/自定义组已被剔除，若日常也都关，启用任务数即为 0。
        if not self._native_one_dragon_has_tasks():
            if exec_ok:
                # 执行层已完成，原生一条龙无活可干：整体视为成功，直接收尾
                self.run_book = True
                self.script_info.log = "执行层已完成；原生一条龙无启用任务，跳过阶段2"
            else:
                self.script_info.log = "一条龙无启用任务，跳过"
            logger.info(
                f"用户 {self.cur_user_item.name} 原生一条龙无启用任务，跳过 BetterGI 启动"
            )
            return

        # 启动原生一条龙前先确认没有杀不掉的旧实例：BGI 单实例下带参启动会被已有实例吞掉，
        # 表现为「一直卡住、游戏不启动」；而 wait_event 只在收到日志时才会被唤醒，一行日志
        # 都没有时会无限等下去（2026-09-15 实机排障）。
        if not await self.kill_managed_process():
            self.cur_user_item.status = "异常"
            self.script_info.log = _BGI_UNKILLABLE_HINT
            logger.error(
                f"用户 {self.cur_user_item.name} 无法启动 BetterGI：{_BGI_UNKILLABLE_HINT}"
            )
            await self._push_dispatch_log(f"无法启动 BetterGI：{_BGI_UNKILLABLE_HINT}")
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

            # 重试前同样确认没有杀不掉的旧实例：BGI 单实例下带参启动会被它吞掉，重试毫无意义
            # （2026-09-15 实机：3 次重试全打在同一个无法终止的实例上）
            if not await self.kill_managed_process():
                self.cur_user_item.status = "异常"
                self.cur_user_log.status = _BGI_UNKILLABLE_HINT
                self.script_info.log = _BGI_UNKILLABLE_HINT
                logger.error(
                    f"用户 {self.cur_user_item.name} 无法启动 BetterGI：{_BGI_UNKILLABLE_HINT}"
                )
                await self._push_dispatch_log(
                    f"无法启动 BetterGI：{_BGI_UNKILLABLE_HINT}"
                )
                return

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

            # 启动后若一个 BetterGI 都不剩（参数被旧单实例吞掉 / 进程秒退），直接置失败并唤醒
            # 等待，避免 wait_event 永远等不到日志行而无限卡住（2026-09-15 实机排障）。
            if not await asyncio.to_thread(find_pids_by_name, _BGI_TRACK_PROCESS_NAME):
                self.cur_user_log.status = (
                    "BetterGI 启动后立即退出（可能有旧实例在运行）"
                )
                self.wait_event.set()

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

    async def _run_execution_layer(self) -> bool:
        """路径 B：用**一次** ``--startGroups <段名...>`` 按队列顺序跑完执行层，返回是否成功。

        各「段」由 ``one_dragon_bridge.build_execution_segments`` 按左栏队列顺序切分，并在
        ``_write_one_dragon_config`` 里物化（战斗 4 项整体一段；js/pathing/keymouse 相邻合并；
        scriptgroup 独立成段），全部在**同一个 BGI 进程**里顺序执行——既省掉一次冷启动，
        也让执行顺序真正听队列。

        成功 = **所有段**都打印「配置组 "<名>" 执行结束」；失败 = 执行配置组任务时失败 /
        任务启动失败 / [FTL] / MAS_PLAN_FAIL；进程提前退出亦判失败。

        另有两条与「步骤跳过」相关的口径：
        - ``MAS_STEP_FAIL``（运行期异常）：只统计数量，不判负（单步跳过继续，见下方注释）；
        - ``MAS_STEP_MISSING_CONFIG``（右栏必填项未填）：判负并提示具体原因——该步根本没
          进 BGI，若仍判成功，用户会看到「一条龙直接完成」而任务实际没跑。
        """
        group_names = list(self.exec_group_names)
        if not group_names:
            # 没有需要接管的段 = 本次没有执行层任务要跑，不建记录
            return True

        # 执行层是一次真实运行，必须留下 log_record：否则本用户这次运行在 MAS 侧没有
        # 任何记录（结果列落到「未开始运行」、不写历史日志、不发统计通知、分步报告与
        # 掉落统计无数据可解析）。原生一条龙随后会另开一条记录，结果形如「执行层 | 一条龙」。
        exec_log = LogRecord()
        self.log_start_time = datetime.now()
        self.cur_user_item.log_record[self.log_start_time] = exec_log
        # 同步为「当前记录」：on_crash 与收尾的「运行异常」通知都读 self.cur_user_log
        self.cur_user_log = exec_log

        await self._push_dispatch_log(
            f"开始执行层: --startGroups {' '.join(group_names)}"
        )
        logger.info(
            f"用户 {self.cur_user_item.name} 启动 BetterGI 执行层: "
            f"{self.script_exe_path} --startGroups {' '.join(group_names)}"
        )

        # 杀旧进程，保证单实例下 --startGroups 由新进程执行。杀不掉必须中止：否则新进程的
        # 参数会被那个旧实例吞掉，执行层永远等不到结束标记，只能干等到空闲超时（2026-09-15 实机）
        if not await self.kill_managed_process():
            failure_reason = _BGI_UNKILLABLE_HINT
            exec_log.status = failure_reason
            logger.error(
                f"用户 {self.cur_user_item.name} 执行层未启动：{failure_reason}"
            )
            await self._push_dispatch_log(f"执行层未启动：{failure_reason}")
            return False

        result: dict[str, bool] = {"success": False, "started": False}
        done_event = asyncio.Event()
        done_groups: set[str] = set()
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
        # 失败并已被跳过的步数（取 main.js 收尾的汇总标记，比逐行计数更可靠）
        partial_failed = 0
        # 必填配置缺失的步骤（用户可读原因）：与 step_failed 不同，它会让本次执行层判负
        missing_config: list[str] = []
        # 失败原因，收尾时写入 exec_log.status；成功统一为项目契约 "Success!"
        failure_reason = "执行层未正常结束"

        last_activity = time.monotonic()

        async def on_log(log_content: list[str], latest_time: datetime) -> None:
            nonlocal last_activity, step_failed, partial_failed, done_groups
            nonlocal failure_reason
            last_activity = time.monotonic()
            log = "".join(log_content)
            # 与原生一条龙的 check_log 同构：把执行层日志写进本次运行记录，
            # 历史日志、统计通知与掉落统计都从这条记录取数据
            exec_log.content = log_content
            # 单步失败只统计（执行层会跳过继续），不据此判负；另外取 main.js 收尾的
            # 汇总标记（失败且已跳过的步数），用于把状态改成「部分失败」
            step_failed = log.count("MAS_STEP_FAIL")
            if (pm := _MAS_PLAN_DONE_WITH_FAILURES_RE.search(log)) is not None:
                partial_failed = int(pm.group(1))
            for reason in _missing_config_reasons(log):
                if reason not in missing_config:
                    missing_config.append(reason)
            for name in group_names:
                if f'配置组 "{name}" 执行结束' in log:
                    done_groups.add(name)
            if done_groups >= set(group_names):
                # 必填配置缺失 → 判负：该步被跳过、任务没跑，若还判成功用户无从得知
                result["success"] = not missing_config
                if missing_config:
                    failure_reason = "执行层失败：有任务因必填配置缺失未执行"
                done_event.set()
            elif any(m in log for m in fail_markers):
                result["success"] = False
                failure_reason = "执行层失败（命中致命日志）"
                done_event.set()
            elif result["started"] and not await self._bgi_alive():
                # 按进程名判定：BGI 自提权重启换 PID 不代表执行层已死
                failure_reason = "执行层进程在结束标记前退出"
                done_event.set()

        monitor = LogMonitor(self.log_time_range, self.log_time_format, on_log)

        try:
            await self.bettergi_process_manager.open_process(
                self.script_exe_path,
                "--startGroups",
                *group_names,
                target_process=self.script_target_process_info,
                elevated=self.script_config.get("Run", "UseAdmin") and not IS_ELEVATED,
            )
            result["started"] = True
            await asyncio.sleep(1)
            await monitor.start_monitor_file(
                self._resolve_log_file_path, datetime.now()
            )
            # 空闲超时循环：日志每次输出即续期，仅当日志静默超过 idle 阈值
            # （BGI 卡死）才终止，不设总时长上限。旧实现为固定 900s 墙钟，
            # 多实例执行层总耗时 20+ 分钟会被误杀（2026-09-08 实机排障：
            # 7 步在 14 分钟处被砍，末位步骤未执行）。
            while not done_event.is_set():
                try:
                    await asyncio.wait_for(done_event.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass
                # 已启动却查不到被跟踪的进程：可能是参数被旧单实例吞掉（新进程秒退），
                # 也可能是 BGI 自行提权重启导致 PID 变了——按进程名复核，确实一个都不剩
                # 才判失败，避免把「自重启」误判成退出。
                if result["started"] and not await self._bgi_alive():
                    failure_reason = "执行层进程在结束标记前退出"
                    done_event.set()
                    break
                # 仅按空闲阈值判定卡死（日志持续输出即一直等，不设总时长上限）
                if (
                    time.monotonic() - last_activity
                    >= _BGI_PLAN_COMBAT_IDLE_TIMEOUT_SECONDS
                ):
                    result["success"] = False
                    failure_reason = (
                        "执行层空闲超时"
                        f"（{_BGI_PLAN_COMBAT_IDLE_TIMEOUT_SECONDS}s 无日志输出）"
                    )
                    logger.warning(
                        f"用户 {self.cur_user_item.name} 执行层空闲超时"
                        f"（{_BGI_PLAN_COMBAT_IDLE_TIMEOUT_SECONDS}s 无日志输出）"
                    )
                    break
        except Exception as e:
            logger.opt(exception=True).warning(f"执行层执行异常: {e}")
            result["success"] = False
            failure_reason = f"执行层执行异常: {e}"
        finally:
            await monitor.stop()
            await self.kill_managed_process()
            # 「段」组文件由 _restore_one_dragon_config 统一删除（含异常路径）

        if missing_config:
            # 具体到「哪一项缺什么」，避免只留一句笼统的「执行层失败」
            reason = "；".join(missing_config)
            failure_reason = f"执行层有任务未执行（配置缺失）: {reason}"
            await self._push_dispatch_log(f"执行层有任务未执行：{reason}")
            logger.warning(
                f"用户 {self.cur_user_item.name} 执行层有任务未执行（配置缺失）: {reason}"
            )

        # 自定义项（配置组 / 脚本 / 路径 / 录制）不走 main.js，BGI 也不会因为其中某个项目
        # 失败而判本次执行层失败（配置组照样走到「执行结束」），所以只能按 BGI 项目行自己补计；
        # 否则这类失败会静默消失（2026-09-19 实机：脚本项失败仍报「成功」）。
        custom_failed = count_failed_custom_items("".join(exec_log.content))
        # 失败步数：main.js 的收尾汇总最可靠，缺失时退回逐行计数；自定义项另行累加
        failed_steps = max(partial_failed, step_failed) + custom_failed
        if custom_failed:
            logger.warning(
                f"用户 {self.cur_user_item.name} 执行层有 {custom_failed} 个自定义项失败"
                f"（配置组/脚本/路径/录制，已跳过并继续后续项目）"
            )

        # 收尾状态：成功必须用 "Success!"（final_task 的成功轮筛选与 on_crash 的
        # 「非 Success! 即弹运行异常通知」都依赖这个契约串）
        exec_log.status = "Success!" if result["success"] else failure_reason
        if result["success"] and failed_steps:
            # 有步骤失败并已跳过：按 2026-09-09 决策不判负（不重试、计入成功），但状态不能再
            # 报「成功」——否则出现「任务没跑完却显示成功」（2026-09-15 实机：地脉花未打）。
            self.partial_failed_steps = failed_steps
            exec_log.status = f"部分失败：{failed_steps} 个步骤未完成（已跳过继续）"

        if result["success"]:
            if failed_steps:
                logger.warning(
                    f"用户 {self.cur_user_item.name} 执行层完成，"
                    f"但 {failed_steps} 个步骤失败（已跳过并继续后续步骤）"
                )
                await self._push_dispatch_log(
                    f"执行层完成，{failed_steps} 个步骤失败已跳过（结果记为部分失败）"
                )
            else:
                await self._push_dispatch_log("执行层完成")
        else:
            await self._push_dispatch_log("执行层失败")
        return result["success"]

    def _account_switch_method(self) -> str:
        """读取脚本级账号切换方式；缺失或非法值回落默认 MAS。"""
        method = str(self.script_config.get("Run", "AccountSwitchMethod") or "MAS")
        return method if method in {"BGI", "MAS"} else "MAS"

    async def _switch_account(self) -> bool:
        """单独执行一次切号，返回是否切换成功。

        按脚本级 ``Run.AccountSwitchMethod`` 分流：

        - ``MAS``：MAS 托管游戏启动后，由 MAS 前台 OCR 直接操控游戏切号
          （官服按手机号/邮箱掩码或账密，B服按B站用户名，见
          ``_switch_account_mas``）；
        - ``BGI``（默认）：走 BetterGI「切换账号多模式」脚本（--startGroups）。

        未配置账号时直接返回 True（无需切换）；失败/超时返回 False，
        由调用方决定是否继续执行一条龙。
        """
        # 用户级游戏客户端路径（临时覆盖）：不写 BetterGI 全局配置——installPath
        # 是全局单值，写入会污染其他「跟随全局」的用户（2026-09-23 实机）。
        # 生效方式：MAS 方式自行按用户路径拉起游戏；BGI 脚本方式由 MAS 预拉起
        # 后 BGI attach 运行中的客户端。
        user_game_path = str(
            self.cur_user_config.get("Switch", "GamePath") or ""
        ).strip()

        if self._account_switch_method() == "MAS":
            return await self._switch_account_mas(user_game_path)

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
        #    首次使用/误删导致脚本本地缺失时，临时开启「运行前同步更新」，
        #    让 BGI 在跑切号组前先把脚本同步拉下，避免「第一次启动切号必失败」。
        script_missing = not account_switch.switch_script_dir(
            self.script_root_path
        ).is_dir()
        try:
            script_present = account_switch.ensure_switch_subscription(
                self.script_root_path, sync_update=script_missing
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

        # 2. 杀旧进程，保证单实例下 --startGroups 由新进程执行；杀不掉必须中止（同执行层）
        if not await self.kill_managed_process():
            logger.error(
                f"用户 {self.cur_user_item.name} 切换账号未启动：{_BGI_UNKILLABLE_HINT}"
            )
            await self._push_dispatch_log(f"切换账号未启动：{_BGI_UNKILLABLE_HINT}")
            return False

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

        # 4. 用户级游戏客户端路径（临时覆盖）：MAS 先按生效路径拉起该用户的
        # 客户端，BGI 启动后 attach 运行中的游戏——不写 BGI 全局配置
        # （installPath 是全局单值，写入会污染其他跟随全局的用户）
        if user_game_path:
            try:
                await self._ensure_user_game_running(user_game_path)
            except Exception as e:
                logger.opt(exception=True).warning(
                    f"用户 {self.cur_user_item.name} 游戏客户端启动失败: {e}"
                )
                await self._push_dispatch_log(f"游戏客户端启动失败: {e}")
                return False

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
            elif switch_result["started"] and not await self._bgi_alive():
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

    async def _switch_account_mas(self, user_game_path: str = "") -> bool:
        """MAS 侧强制切换账号（官服/B服）：托管启动游戏 + 前台 OCR 操控登录界面。

        官服：有密码走「登录其他账号 + 剪贴板输入账密」，无密码走下拉列表按
        掩码选号；B服：按B站用户名在登录记录面板选号（暂不支持账密登录）。
        成功后游戏保持运行，与 BGI 脚本路径的收尾一致，由随后的一条龙接管。
        失败返回 False，由调用方中止任务。
        """
        account = str(self.cur_user_config.get("Info", "Id") or "").strip()
        if not account:
            return True
        password = str(self.cur_user_config.get("Info", "Password") or "")
        resource = str(self.cur_user_config.get("Switch", "Resource") or "官服").strip()

        # MAS 托管游戏启动（同 OK-NTE 语义）：已运行跳过，未运行按用户级路径
        # （留空跟随 BGI 全局）拉起；游戏起不来切号无从执行，直接失败中止
        try:
            await self._ensure_user_game_running(user_game_path)
        except Exception as e:
            logger.opt(exception=True).warning(
                f"用户 {self.cur_user_item.name} 游戏启动失败: {e}"
            )
            await self._push_dispatch_log(f"游戏启动失败: {e}")
            return False

        await self._push_dispatch_log("正在由 MAS 前台切换账号...")
        # 切号在后台线程内同步执行，on_log 契约是同步回调；_push_dispatch_log 是
        # async 方法，须经 run_coroutine_threadsafe 调度回事件循环（对齐 OK-WW/OK-NTE）
        switch_loop = asyncio.get_running_loop()

        def _push_switch_log(line: str) -> None:
            asyncio.run_coroutine_threadsafe(self._push_dispatch_log(line), switch_loop)

        try:
            success = await account_switch_native.async_switch_account(
                account, password, resource=resource, on_log=_push_switch_log
            )
        except Exception as e:
            success = False
            await self._push_dispatch_log(f"MAS 账号切换失败: {e}")
            logger.opt(exception=True).warning(
                f"用户 {self.cur_user_item.name} MAS 账号切换失败: {e}"
            )
        if success:
            await self._push_dispatch_log("MAS 账号切换完成")
            logger.success(f"用户 {self.cur_user_item.name} MAS 账号切换完成")
        else:
            await self._push_dispatch_log("MAS 账号切换失败，已中止任务")
            logger.warning(
                f"用户 {self.cur_user_item.name} MAS 账号切换失败，已中止任务"
            )
        return success

    async def _ensure_user_game_running(self, user_game_path: str = "") -> Path:
        """确保该用户的游戏客户端在运行（用户级路径临时生效，不写 BGI 配置）。

        生效路径 = 用户级 ``Switch.GamePath``（优先）或 BGI 全局配置。已运行的
        本地客户端与生效路径一致时跳过启动；不一致时（CloseOnFinish 关闭时的
        上一用户残留 / BGI 全局被外部改动）终止残留后拉起正确客户端——切号与
        一条龙必须跑在该用户服务器对应的客户端上。

        Returns:
            Path: 生效的游戏主程序路径。

        Raises:
            RuntimeError: 路径未配置/不存在。
        """
        game_exe = game_info.resolve_game_exe(self.script_root_path, user_game_path)
        running = await asyncio.to_thread(
            game_info.find_running_game_exe, _BGI_LOCAL_GAME_PROCESS_NAMES
        )
        if running is not None:
            if game_info.same_path(running, game_exe):
                logger.info(
                    f"检测到原神已在运行且与该用户客户端一致，跳过启动: {running}"
                )
                await self._push_dispatch_log("检测到原神已在运行，跳过游戏启动")
                return game_exe
            await self._push_dispatch_log(
                f"检测到运行中的客户端 ({running}) 与该用户的游戏客户端不一致，正在关闭..."
            )
            await self._kill_game_processes(_BGI_LOCAL_GAME_PROCESS_NAMES)
        await self._push_dispatch_log(f"正在由 MAS 启动原神: {game_exe.name}")
        # 持有为实例属性：局部 ProcessManager 出栈后 asyncio 子进程 transport
        # 被 GC 会产生 unclosed 告警噪音；保留句柄不影响 CloseOnFinish 收尾语义
        self.switch_game_manager = ProcessManager()
        # breakaway=True：游戏不该随后端退出（Runtime 用 KILL_ON_JOB_CLOSE 的
        # Job 监督后端，子进程默认留在 Job 里被连带回收；对齐模拟器/游戏客户端
        # 直拉调用点的既有惯例，见 windows/process.py 顶部契约说明）
        await self.switch_game_manager.open_process(game_exe, breakaway=True)
        await self._push_dispatch_log("原神已拉起，等待窗口就绪...")
        return game_exe

    async def check_log(self, log_content: list[str], latest_time: datetime) -> None:
        """按内置日志判定结果，未见成功日志便退出则视为异常。"""
        log = "".join(log_content)
        self.cur_user_log.content = log_content
        self.script_info.log = log[-4000:] if len(log) > 4000 else log

        log_status = "BetterGI 正常运行中"
        user_item_status: str | None = None

        # 进副本后打不了 / 游戏被留在副本里的提示：BGI 两种情况都照打「任务结束」继续后面的
        # 任务（不判负），但要给一次可操作的原因；分步表与「部分失败」由 final_task 收尾处理
        for hint in (_combat_script_miss_hint(log), _back_to_main_failed_hint(log)):
            if hint and hint not in self._bgi_hints_pushed:
                self._bgi_hints_pushed.add(hint)
                logger.warning(f"用户 {self.cur_user_item.name} {hint}")
                await self._push_dispatch_log(f"BetterGI 运行提示：{hint}")

        # 切队配置错误（战斗队伍名在游戏内置找不到）优先于笼统的 [ERR] 判定，
        # 并给一次指明队伍名的明确报错
        if party_err := _party_config_error(log):
            # 队伍名命中「队伍配置」表时额外标注来源：场景选队是运行时随机抽取的，
            # 不指明来源用户很难定位到底是哪一行配置引起的
            from_teams = any(t["name"] == party_err for t in self.one_dragon_teams)
            source = "「队伍配置」表" if from_teams else "「战斗队伍」配置"
            log_status = (
                f"切队失败/配置错误: 战斗队伍「{party_err}」在游戏内队伍列表中未找到"
                f"（来源：{source}）"
            )
            user_item_status = "异常"
            if not self._party_err_pushed:
                self._party_err_pushed = True
                await self._push_dispatch_log(
                    f"BetterGI 运行异常：战斗队伍「{party_err}」在游戏内未找到，"
                    f"请核对 MAS 里该用户的{source}"
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
                elif not await self._bgi_alive():
                    # 按进程名判定：BGI 自提权重启会换 PID，跟踪 PID 失效 ≠ 任务已死
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
            dt = t.astimezone(UTC4)
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
        # 一次任务最多两相（执行层 → 原生一条龙），两相**都要进表**：只取一相会让后跑的
        # 日常相把战斗 4 项顶掉（2026-09-19 实机：通知只见「领取邮件/领取尘歌壶奖励/
        # 领取每日奖励」，执行层的幽境危战/地脉花/首领讨伐/秘境全看不见）。
        # 同一相的多轮日志只可能是重试，故每相只取一轮：成功轮优先，无成功轮时取最后一轮
        # 能解析出步骤的（末轮可能在打出标记前就失败）。全部相都无步骤时整块省略。
        runs = list(self.cur_user_item.log_record.values())
        # 原生一条龙的进度行只有序号、日志里没有任务名：按本次启动的那份配置给出名字表，
        # 供解析器按序号还原（长度对不上时解析器自行退回日志推断，见 one_dragon_report）。
        native_task_names = self._native_one_dragon_task_names()

        def _phase_steps(
            parser: Callable[[str], list[dict] | None],
        ) -> list[dict] | None:
            """取某一相的步骤：成功轮优先，否则最近一轮能解析出步骤的轮次。"""
            fallback: list[dict] | None = None
            for item in reversed(runs):
                steps = parser("".join(item.content))
                if not steps:
                    continue
                if item.status == "Success!":
                    return steps
                if fallback is None:
                    fallback = steps
            return fallback

        # 注意：执行层以「部分失败」收尾的那些轮同样要取——单步失败被判负、状态不是
        # Success!，只认成功轮会把它整相丢掉。
        # 这一相不止 main.js 的战斗步：队列里的自定义项（配置组 / 脚本 / 路径 / 录制）由
        # 同一次 --startGroups 直连 BGI 配置组执行，解析器按 BGI 项目行一并还原
        # （2026-09-19 实机：只有自定义项的运行整块分步表缺失）。
        exec_steps = _phase_steps(parse_execution_layer_report)
        native_steps = _phase_steps(
            lambda content: parse_one_dragon_report(content, native_task_names)
        )
        one_dragon_report = _merge_one_dragon_reports(exec_steps, native_steps)
        # 原生一条龙的任务级异常（匹配不到自动战斗脚本、切队回不到主界面…）会让该任务被跳过，
        # BGI 却照打「任务结束」并继续后面的任务，只看「一条龙和配置组任务结束」会整条判成功
        # （2026-09-19 实机：秘境一仗没打、领奖也没领，通知却是「成功」）。分步表里判失败的步
        # 计入「部分失败」——与执行层同口径：不判负、照常计次，但状态与通知要说清。
        native_failed = sum(1 for s in native_steps or [] if not s["ok"])
        if native_failed:
            self.partial_failed_steps += native_failed
            logger.warning(
                f"用户 {self.cur_user_item.name} 一条龙有 {native_failed} 个任务未干成"
                f"（已跳过并继续后续任务）"
            )
        if one_dragon_report:
            # 必须留痕：分步表少了一相时，先看这行就知道是「那相没跑/没解析出步骤」还是「拼接漏了」
            logger.info(
                f"用户 {self.cur_user_item.name} 分步表：执行层 {len(exec_steps or [])} 步 + "
                f"一条龙 {len(native_steps or [])} 步 = {len(one_dragon_report)} 行"
            )

        # 掉落统计：解析各轮日志里的「本轮奖励识别结果」（BGI 奖励识别打印的行），
        # 按物品跨轮跨来源累加。与分步报告不同——掉落是逐轮产出，必须合并全部轮次，
        # 因此不挑轮次；识别未开启或日志里没有该行时结果为空表，通知里整块省略。
        drop_statistics: dict[str, int] = {}
        if self.drop_statistics_enabled:
            drop_lines: list[str] = []
            for item in runs:
                drop_lines.extend(item.content)
            drop_statistics = parse_drop_lines(drop_lines)
            # 必须留痕：这一块此前完全静默，出问题时无从判断是「开关没读到」「日志里没有
            # 识别行」还是「解析为空」，只能靠翻历史日志手工复现（2026-09-16 实机排障）
            logger.info(
                f"用户 {self.cur_user_item.name} 掉落统计：合并 {len(runs)} 轮日志 "
                f"{len(drop_lines)} 行，解析到 {len(drop_statistics)} 项物品"
            )
        else:
            logger.info(
                f"用户 {self.cur_user_item.name} 未开启「统计掉落物品」，跳过掉落解析"
            )

        if statistic_paths:
            try:
                statistics = await Config.merge_statistic_info(statistic_paths)
                if one_dragon_report:
                    statistics["one_dragon_steps"] = one_dragon_report
                if drop_statistics:
                    statistics["drop_statistics"] = drop_statistics
                statistics["user_info"] = self.cur_user_item.name
                start_time = getattr(self, "user_start_time", datetime.now())
                statistics["start_time"] = start_time.strftime("%Y-%m-%d %H:%M:%S")
                statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                statistics["user_result"] = (
                    "代理任务全部完成" if self.run_book else self.cur_user_item.result
                )
                if self.run_book and self.partial_failed_steps:
                    # 不判负，但执行结果要说清有几个步骤没做完，不能写「全部完成」
                    statistics["user_result"] = (
                        f"代理任务完成（{self.partial_failed_steps} 个步骤失败已跳过）"
                    )
                success_symbol = "√" if self.run_book else "X"
                # 统计通知的字段清单：用于确认分步表/掉落表这类可选区块到底有没有下发
                logger.info(
                    f"用户 {self.cur_user_item.name} 统计通知字段: "
                    f"{sorted(statistics.keys())}"
                )
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
            # 部分失败仍算成功（不判负、照常计次），但状态要能看到，不能显示成「完成」
            self.cur_user_item.status = (
                "部分失败" if self.partial_failed_steps else "完成"
            )
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

    async def _kill_game_processes(self, names: tuple[str, ...] | list[str]) -> None:
        """按完整映像名（含 .exe）逐一强制结束游戏进程（含子进程），失败必须落日志。

        游戏对 WM_CLOSE 无响应：taskkill 不带 /F 的「优雅关闭」会一直等待进程
        退出直至 60s 超时抛异常，反而跳过后续的强制关闭（旧实现的游戏残留根因），
        故这里直接 /F 结束。
        """
        for image in names:
            try:
                result = await ProcessRunner.run_process(
                    "taskkill", "/IM", image, "/F", "/T"
                )
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

    async def _close_game(self) -> None:
        """任务结束后关闭原神游戏进程。

        按进程名逐一强制结束，覆盖官服/B服/国际服/云原神等客户端。
        taskkill 非零返回（拒绝访问/进程不存在）必须落日志，否则关闭失败
        在收尾里完全无痕、无法排查。
        """
        if not self.script_config.get("Game", "CloseOnFinish"):
            return

        await self._push_dispatch_log("任务结束，正在关闭游戏进程")
        await self._kill_game_processes(_BGI_GAME_PROCESS_NAMES)
        await self._push_dispatch_log("游戏进程已关闭")

    async def _bgi_alive(self) -> bool:
        """是否还有任意 BetterGI 存活。

        BGI 自己会重启并提权（它的设置里要求管理员、或启动游戏需要管理员时会这样），重启后
        **MAS 启动时跟踪的那个 PID 已经退出**，而真正的任务在**新进程**里继续跑、日志也仍写在
        同一个文件里。所以「进程是否还在」必须按进程名判断：只看跟踪 PID 会把这种自重启误判成
        「在完成任务前退出」，白跑满 3 次重试（2026-09-15 实机：MAS 报 3 次失败，而 BGI 其实
        已把游戏启动并跑完了一条龙）。
        """
        if await self.bettergi_process_manager.is_running():
            return True
        return bool(await asyncio.to_thread(find_pids_by_name, _BGI_TRACK_PROCESS_NAME))

    async def kill_managed_process(self) -> bool:
        """中止 BetterGI 进程（游戏进程由 BetterGI 自身管理）。

        Returns:
            bool: 已确认无 BetterGI 残留时返回 True；仍有实例存活（MAS 无权终止它）时返回
                False——BGI 单实例，带参启动会被已有实例吞掉（任务卡住、游戏不启动），
                调用方必须据此中止而不是继续启动。
                注意 ``System.kill_process`` 对「读不到 exe 路径」的提权进程会归入
                uncertain_pids 而漏判为成功，故末尾必须按进程名复核一遍。
        """
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

        remaining = await _wait_bgi_exit()
        if remaining:
            logger.warning(
                f"BetterGI 进程仍存活（PID: {remaining}）：{_BGI_UNKILLABLE_HINT}"
            )
            return False
        return True
