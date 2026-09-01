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
import uuid
from contextlib import suppress
from datetime import datetime, timedelta
from pathlib import Path

from app.core import Config
from app.models.task import TaskExecuteBase, ScriptItem, UserItem, LogRecord
from app.models.ConfigBase import MultipleConfig
from app.models.config import BetterGIConfig, BetterGIUserConfig
from app.services import Notify, System
from app.utils import get_logger, ProcessManager, ProcessInfo, ProcessRunner
from app.utils.LogMonitor import LogMonitor
from app.utils.constants import UTC4
from app.task.general.tools import execute_script_task

from .tools import push_notification
from .tools import account_switch
from .tools import one_dragon
from .tools.one_dragon_report import _parse_one_dragon_report

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

# BetterGI 管理的原神游戏进程名（不含 .exe），与 BetterGI 源码
# TaskContext.GetGenshinGameProcessNameList() 保持一致；任务结束后按此顺序逐一尝试关闭。
_BGI_GAME_PROCESS_NAMES: tuple[str, ...] = (
    "YuanShen",                     # 官服 / B服（国服）
    "GenshinImpact",                # 国际服
    "Genshin Impact Cloud Game",    # 云原神（国际）
    "Genshin Impact Cloud",         # 云原神（备用进程名）
)
# 优雅关闭游戏后等待退出时间（秒），超时未退出则强制结束
_BGI_GAME_CLOSE_WAIT_SECONDS = 5


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


# 脚本仓库更新/下载进展消息（去重展示用）。BGI 把它打在不带方括号前缀的消息行。
# 这些行若能转述给用户，切号/一条龙启动时「正在下载脚本」就不会被误认为卡死。
_REPO_PROGRESS_CATEGORY = (
    "浅克隆仓库",
    "拉取对象",
    "开始静默更新脚本仓库",
    "自动更新订阅脚本完成",
    "本地仓库已是最新",
)


def _latest_repo_progress(log: str) -> str | None:
    """从累计日志中提取最近一条值得转述的脚本仓库下载/更新进展行。

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
_BGI_PARTY_SWITCH_RE = re.compile(
    r'尝试切换至队伍:\s*["“]?([^"”\n]+)["”]?\s*$', re.M
)
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
        self.script_log_path: Path | None = None
        self.log_monitor: LogMonitor | None = None
        # 切队配置错误报错只推送一次，避免每个日志回调重复刷屏
        self._party_err_pushed = False

    async def check(self) -> str:
        root = Path(self.script_config.get("Info", "RootPath"))
        if not root.is_dir():
            return "请设置 BetterGI 脚本路径"
        if not (root / _BGI_REL_EXE).is_file():
            return "请设置 BetterGI 脚本路径"

        if (
            self.script_config.get("Run", "ProxyTimesLimit") != 0
            and self.cur_user_config.get("Data", "ProxyTimes")
            >= self.script_config.get("Run", "ProxyTimesLimit")
        ):
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

        self.script_log_path = self._resolve_log_file_path()

        self.log_time_range = (_BGI_LOG_TIME_START, _BGI_LOG_TIME_END)
        self.log_time_format = _BGI_LOG_TIME_FORMAT
        self.log_monitor = LogMonitor(
            self.log_time_range,
            self.log_time_format,
            self.check_log,
        )

        self.one_dragon_config = one_dragon.resolve_config_name(
            str(self.cur_user_config.get("Task", "OneDragonConfigName") or "")
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
        # 「用户独立配置」开启时，per-user 配置落到 MAS 专属槽位并据此启动，BGI 同名的
        # 用户实配全程零接触。若用户恰好把配置命名为槽位名，退化为直连（防自伤）。
        self.use_mas_launch_slot = (
            self.use_mas_config
            and one_dragon.launch_slot_name() != self.one_dragon_config
        )
        self.launch_config_name = (
            one_dragon.launch_slot_name()
            if self.use_mas_launch_slot
            else self.one_dragon_config
        )
        self.bettergi_args = ["startOneDragon", self.launch_config_name]

        self.run_book = False

        # 通用战斗队伍/策略落到全局 config.json 前的叶子快照，None 表示尚未接管
        self._reseed_global_config: dict | None = None

    def _resolve_log_file_path(self) -> Path:
        """构造 BetterGI 当日滚动日志路径（better-genshin-impact{yyyyMMdd}.log）。"""
        return (
            self.script_root_path
            / _BGI_REL_LOG_DIR
            / f"{_BGI_LOG_FILE_PREFIX}{datetime.now():%Y%m%d}.log"
        )

    async def _push_dispatch_log(self, line: str) -> None:
        """向调度台追加流程日志（赋值 script_info.log 会触发 WebSocket 推送）。"""

        prev = self.script_info.log
        self.script_info.log = f"{prev}\n{line}" if prev else line
        await asyncio.sleep(0)

    def _write_one_dragon_config(self) -> None:
        """用户独立配置模式下，把组开关应用到一条龙配置并写回 BetterGI。"""
        if not self.use_mas_config:
            return
        party_name = str(
            self.cur_user_config.get("OneDragon", "PartyName") or ""
        )
        one_dragon.write_user_one_dragon(
            self.script_root_path,
            self.script_info.script_id,
            self.cur_user_item.user_id,
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
        )
        # 通用战斗队伍/策略补写进全局 config.json（秘境/地脉花/幽境危战读取段）
        one_dragon.apply_global_battle_team(self.script_root_path, party_name)
        one_dragon.apply_global_battle_strategy(
            self.script_root_path,
            str(self.cur_user_config.get("OneDragon", "AutoBossStrategyName") or ""),
        )
        logger.info(
            f"已写入用户 {self.cur_user_item.name} 的一条龙配置: {self.one_dragon_config}"
        )

    def _snapshot_one_dragon_config(self) -> None:
        """把 BetterGI 现有的一条龙配置回读为 per-user 副本（捕获 GUI 中改的设置）。

        独立模式下读取源是 MAS 槽位 ``launch_config_name``（用户在 BGI GUI 里编辑的就是这份），
        缓存 key 仍是用户所选名 ``one_dragon_config``，供下一轮 ``write_user_one_dragon`` 种子。
        """
        if not self.use_mas_config:
            return
        one_dragon.snapshot_user_one_dragon(
            self.script_root_path,
            self.script_info.script_id,
            self.cur_user_item.user_id,
            self.one_dragon_config,
            read_name=self.launch_config_name,
        )

    def _backup_one_dragon_config(self) -> None:
        """运行前快照乐观覆盖的全局 config.json 队伍/策略叶子，供结束后还原。

        独立配置模式下 per-user 配置落到 MAS 专属槽位，不写 BGI 同名实配；BGI 那套
        一条龙文件无需备份。全局 config.json 的队伍/策略叶子（地脉花/幽境危战/秘境读段）
        仍需运行时临时补写、结束还原，故这里先快照。
        """
        if not self.use_mas_config:
            return
        self._reseed_global_config = one_dragon.snapshot_global_battle_config(
            self.script_root_path
        )

    def _restore_one_dragon_config(self) -> None:
        """运行/异常结束后还原全局 config.json 队伍/策略叶子，并删除 MAS 运行时槽位。

        仅在本次确接管过（``_reseed_global_config`` 非 None）时生效；还原一次后置 None
        保证幂等，避免 final_task 与 on_crash 相继触发时重复覆盖。槽位文件在 ``finally``
        中无条件删除（幂等），使 BGI GUI 不残留 MAS 运行时配置。
        """
        if self._reseed_global_config is None:
            return
        try:
            # 还原全局 config.json 队伍/策略叶子字段（秘境/地脉花/幽境危战读取段）
            one_dragon.restore_global_battle_config(
                self.script_root_path, self._reseed_global_config
            )
        finally:
            one_dragon.remove_one_dragon_slot(self.script_root_path)
            self._reseed_global_config = None

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
                elevated=True,
            )

            # 启动日志监控（文件日志）
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
            self.script_info.log = (
                f"{self.cur_user_log.status}\n正在中止相关程序"
            )
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
                self.script_info.log += (
                    f"\n将在稍后重试 ({i + 1}/{run_limit})"
                )
                await asyncio.sleep(10)

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

        # 更新情况：BGI 启动时先更新仓库脚本、再执行配置组；本地已有脚本则本次是增量检查。
        # 缺失（用户误删/初次使用）时 ensure_switch_subscription 已强制重建仓库，BGI 启动即补位。
        if script_present:
            logger.info("切换账号脚本已存在于本地，BGI 启动时检查仓库更新")
            await self._push_dispatch_log("切换账号脚本已就绪，随 BGI 启动检查仓库更新")
        else:
            logger.info("切换账号脚本本地缺失，已强制 BGI 启动时从脚本仓库重新检出")
            await self._push_dispatch_log(
                "切换账号脚本缺失，已重新订阅并由 BGI 启动时重新下载（若网络较慢请耐心等待）"
            )

        await self._push_dispatch_log(
            f"开始切换账号: --startGroups {account_switch._GROUP_NAME}"
        )
        logger.info(
            f"用户 {self.cur_user_item.name} 启动 BetterGI 切换账号: "
            f"{self.script_exe_path} --startGroups {account_switch._GROUP_NAME}"
        )

        # 2. 杀旧进程，保证单实例下 --startGroups 由新进程执行
        await self.kill_managed_process()

        switch_success = asyncio.Event()
        switch_result = {"success": False, "started": False}
        # 已转述过到调度台的仓库进展（每个文案只推一次，避免刷屏）
        repo_progress_reported: set[str] = set()

        # 单组 --startGroups 的成功/失败判定取自 BetterGI 配置组日志：
        #   成功: 配置组 "MAS切换账号" 执行结束
        #   失败: 执行配置组任务时失败 / 任务启动失败 / 任务执行异常 / [FTL] / [ERR]
        switch_group_done = f'配置组 "{account_switch._GROUP_NAME}" 执行结束'
        # 单组 --startGroups 场景下 [ERR] 即该配置组执行失败（无后续组可续跑），与一条龙判定中
        # [ERR] 是「任务级可恢复、跳过继续跑」的语义不同，故此处按失败处理。
        switch_group_fail = (
            "执行配置组任务时失败",
            "任务启动失败",
            "任务执行异常",
            "[FTL]",
            "[ERR]",
        )

        async def on_switch_log(
            log_content: list[str], latest_time: datetime
        ) -> None:
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
                account_switch._GROUP_NAME,
                target_process=self.script_target_process_info,
                elevated=True,
            )
            # open_process 内部 search_process 已确认目标进程存在，之后退出才算失败
            switch_result["started"] = True
            await asyncio.sleep(1)
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

        if switch_result["success"]:
            await self._push_dispatch_log("切换账号完成")
            logger.success(f"用户 {self.cur_user_item.name} 切换账号完成")
        else:
            await self._push_dispatch_log("切换账号失败或超时，已中止任务")
            logger.warning(f"用户 {self.cur_user_item.name} 切换账号失败或超时，已中止任务")
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
                elif (
                    "[ERR]" in log
                    and datetime.now() - latest_time
                    > timedelta(minutes=_BGI_ERR_STALL_MINUTES)
                ):
                    # [ERR] 后长时间无任何新日志行：BGI 既没走完收尾、也没继续推进也没退出，
                    # 判定卡死提前失败（不等 RunTimeLimit）。仍在新行推进则不触发。
                    log_status = (
                        f"BetterGI 出现 [ERR] 后 {_BGI_ERR_STALL_MINUTES} "
                        "分钟无进展（疑似卡死）"
                    )
                    user_item_status = "异常"
                elif datetime.now() - latest_time > timedelta(
                    minutes=self.script_config.get("Run", "RunTimeLimit")
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
        # 无一条龙任务（仅配置组/未捕获到日志）时自动省略该区块。
        combined_log = "".join(
            ln for item in self.cur_user_item.log_record.values() for ln in item.content
        )
        one_dragon_report = _parse_one_dragon_report(combined_log)

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

        # 用户独立配置：回读 BetterGI 现有配置，捕获运行中/GUI 里改的设置，固化到 per-user 副本
        self._snapshot_one_dragon_config()

        # 快照已完成，再把现场还原为覆盖前的副本，避免污染其它用户
        self._restore_one_dragon_config()

    async def _persist_user_run_result(self) -> None:
        if self.cur_user_config is None:
            return

        await self.cur_user_config.set(
            "Data", "LastOneDragonConfig", getattr(self, "one_dragon_config", "")
        )
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
            await Config.send_websocket_message(
                id=self.task_info.task_id,
                type="Info",
                data={"Error": f"BetterGI 自动代理任务出现异常: {e}"},
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

        按进程名逐一尝试：先优雅关闭（发送 WM_CLOSE），等待短暂时间后
        再强制结束残留进程，覆盖官服/B服/国际服/云原神等客户端。
        """
        if not self.script_config.get("Game", "CloseOnFinish"):
            return

        await self._push_dispatch_log("任务结束，正在关闭游戏进程")
        for name in _BGI_GAME_PROCESS_NAMES:
            image = f"{name}.exe"
            try:
                # 先优雅关闭（taskkill 不带 /F 会向 GUI 窗口发送 WM_CLOSE）
                graceful = await ProcessRunner.run_process(
                    "taskkill", "/IM", image, "/T"
                )
                if graceful.returncode == 0:
                    await asyncio.sleep(_BGI_GAME_CLOSE_WAIT_SECONDS)
                # 再强制结束仍残留的进程（含子进程）
                await ProcessRunner.run_process("taskkill", "/IM", image, "/F", "/T")
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
                logger.opt(exception=True).warning(
                    f"中止 BetterGI 主进程失败: {e}"
                )
