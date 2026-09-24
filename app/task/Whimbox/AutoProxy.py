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
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""奇想盒自动代理：无头 CLI ``startOneDragon`` + loguru 日志面判定。

执行链（对齐 BetterGI 线）：
1. ``check()``：安装哨兵三件 + 上游进程占用 + 今日次数/剩余天数；
2. 运行前：强制归档 ``configs/config.json`` → 若接管配置，把用户覆盖集按当前
   模板键集过滤后原子合并写入 → spawn 嵌入式 Python 无头一条龙；
3. 运行中：``IRunEventFeed`` 盯当日日志，实时把步骤/账号进展推调度台，
   判定交给 ``IRunResultParser``（管理员致命 / 收尾行 + 完成行结果块头 /
   中止 / 早退 / 停滞超时）；
4. 结束（final_task / on_crash 全覆盖）：停监控、清进程、还原运行前归档、
   写历史、落用户状态、推通知（结果块原文透传 + 未完成原因原文）。

成败判定全部取自上游结果面（日志收尾行与结果块），不自造判定信号；
多账号循环归上游 ``change_account``，MAS 不做账号定向。重试也只救「没有上游结论」
的异常（提前退出/卡死），上游连着给出同一个失败结论时收口，不重跑整条一条龙。
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import suppress
from datetime import datetime
from pathlib import Path

from app.core import Config
from app.core.ws import Publisher, protocol
from app.models.config import WhimboxConfig, WhimboxUserConfig
from app.models.ConfigBase import MultipleConfig
from app.models.schema import WSTaskNoticeData
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase, UserItem
from app.services import Notify
from app.task.general.tools import execute_script_task
from app.task.proxy_helpers import (
    CONFIG_SOURCE_DIRECT,
    push_dispatch_log,
    read_config_source,
)
from app.utils import get_logger
from app.utils.constants import UTC4

from .contracts import (
    IProcessLauncher,
    IRunEventFeed,
    IRunResultParser,
    IUpstreamConfigSurface,
    WhimboxRunEvent,
)
from .tools.feed import LoguruFileFeed, build_log_path_resolver
from .tools.launcher import EmbeddedPythonLauncher, find_upstream_pids
from .tools.marker import WhimboxMarkerParser, is_benign_marker
from .tools.notify import push_notification
from .tools.upstream import WheelAssetsConfigSurface, parse_override_map

logger = get_logger("奇想盒 自动代理")

# 实时进展推送：值得转述到调度台的行前缀（步骤进入/异常/账号切换）
_DISPATCH_LINE_PREFIXES = (
    "✅",
    "❌",
    "🛑",
    "账号列表:",
    "当前账号:",
    "已完成账号列表：",
)

# 失败提示行前缀：结果块里默认步骤只有 ✅/⏭️/❌ 三态、不带原因，原因只在上游这些
# 行里，收集后进报告「未完成原因」段（原文透传，不改写成步骤级归属）
_FAILURE_LINE_PREFIXES = ("❌", "🛑")

# 不做自动重试的判定状态：成功（调用方在此之前已收口）与环境性致命（缺管理员权限等，
# 重试必然同一结果）
_NO_RETRY_STATUSES = frozenset({"success", "fatal"})


def _should_retry(
    verdict_status: str | None, *, same_reason_as_last: bool = False
) -> bool:
    """是否值得再跑一轮（``Run.RunTimesLimit`` 的重试策略）。

    - **没有上游结论**的形态（``exited_early`` 提前退出 / ``stalled`` 卡死 / 未判定）：
      重试——这才是重试机制的原本用途；
    - **上游自己判负**（``failed``）：只在**原因与上一轮不同**时重试（情形在变，说明
      还有救）；连着给出同一个结论时收口，因为重试等于把整条一条龙再跑一遍（含重新
      启动游戏），而原因不会在几分钟内自己变；
    - **环境性致命**（``fatal``，如缺管理员权限）：不重试，权限不会因重试而出现；
    - ``success``：不重试（调用方在此之前已收口）。
    """

    if verdict_status in _NO_RETRY_STATUSES:
        return False
    if verdict_status == "failed":
        return not same_reason_as_last
    return True


class AutoProxyTask(TaskExecuteBase):
    """奇想盒自动代理任务（每用户一轮）。

    四边界经构造注入，默认实现就地兜底构造（L1 组合，零容器）；单测经构造
    参数注入假实现，不经过 manager。
    """

    def __init__(
        self,
        script_info: ScriptItem,
        script_config: WhimboxConfig,
        user_config: MultipleConfig[WhimboxUserConfig],
        *,
        config_surface: IUpstreamConfigSurface | None = None,
        launcher: IProcessLauncher | None = None,
        parser: IRunResultParser | None = None,
        feed_factory=None,
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
        self.cur_user_config: WhimboxUserConfig = self.user_config[self.cur_user_uid]
        # 两态来源：脚本=把面板值写入上游 config.json；直控=用上游原生配置、MAS 零写入
        self.config_mode = read_config_source(self.cur_user_config)
        self.use_mas_config = self.config_mode != CONFIG_SOURCE_DIRECT

        self.root_path = Path(str(self.script_config.get("Info", "RootPath") or ""))
        self.config_surface = config_surface or WheelAssetsConfigSurface(self.root_path)
        self.launcher = launcher or EmbeddedPythonLauncher(
            self.root_path, bool(self.script_config.get("Run", "UseAdmin"))
        )
        self.parser = parser or WhimboxMarkerParser()
        self._feed_factory = feed_factory or (
            lambda on_event: LoguruFileFeed(
                on_event, build_log_path_resolver(self.root_path)
            )
        )
        self.feed: IRunEventFeed | None = None

        self.cur_user_log: LogRecord | None = None
        self.wait_event: asyncio.Event | None = None
        self.run_book = False
        self.result_block: str | None = None
        # 上游 ❌/🛑 提示行原文（结果块只有状态、没有原因），进报告「未完成原因」段
        self.failure_notes: list[str] = []
        # 本轮判定器的状态（_should_retry 输入）；每轮尝试开头清空
        self.last_verdict_status: str | None = None
        # 上一轮失败的判定文案（含上游原因），用于「同一原因不重复重试」
        self._last_failure_reason: str | None = None
        # 运行前归档锚点（None=运行前无 config.json，还原时删除会话期新建）
        self._pre_run_archive_ts: str | None = None
        # 本轮是否接管了上游配置（直控+关闭时不物化也不还原，上游自行迁移）
        self._config_took_over = False
        # 实时进展已推送的行数（避免重复转述）
        self._dispatch_pushed_lines = 0
        # 进程静默退出看门狗（无日志行时事件流不会回调，靠轮询兜底）
        self._exit_watchdog_task: asyncio.Task | None = None

    async def check(self) -> str:
        # 安装哨兵三件（分场景报错，覆盖首启未完成/弱网下载失败场景）
        install_error = self.config_surface.check_install()
        if install_error:
            return install_error

        # 上游正在运行：拒绝启动（不静默互踩 config.json，MAA issue-591 教训）
        running_pids = await asyncio.get_running_loop().run_in_executor(
            None, find_upstream_pids, self.root_path
        )
        if running_pids:
            return "奇想盒正在运行，请先关闭奇想盒 app 再执行任务"

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
        self.wait_event = asyncio.Event()
        self.user_start_time = datetime.now()

    def _takeover_config(self) -> None:
        """快照 → 物化：接管配置时把用户覆盖集写入上游 config.json。

        归档无条件执行（运行前安全网）；物化与还原只在接管时——直控模式
        MAS 零写入，上游运行期的自我迁移（合并默认键等）属其内部行为，
        不予还原。
        """

        # 运行前强制归档（覆盖性物化前；失败即任务失败，不留无快照的覆写）
        self._pre_run_archive_ts = self.config_surface.snapshot_pre_run()
        self._config_took_over = self.use_mas_config
        if not self.use_mas_config:
            return
        tasks = parse_override_map(self.cur_user_config.get("Task", "Tasks"))
        options = parse_override_map(self.cur_user_config.get("Task", "Options"))
        self.config_surface.materialize_overrides(
            {str(k): bool(v) for k, v in tasks.items()},
            options,
            run_all_accounts=bool(
                self.cur_user_config.get("OneDragon", "IfRunAllAccounts")
            ),
        )

    def _restore_config(self) -> None:
        """还原运行前归档条目（final_task / on_crash 共用，幂等）。"""

        if self._config_took_over:
            try:
                self.config_surface.restore_pre_run(self._pre_run_archive_ts)
            except Exception as e:
                logger.opt(exception=True).warning(f"还原奇想盒 config.json 失败: {e}")
        self._pre_run_archive_ts = None
        self._config_took_over = False

    async def main_task(self):
        await self.prepare()
        self.curdate = datetime.now(tz=UTC4).strftime("%Y-%m-%d")
        if self.cur_user_config.get("Data", "LastProxyDate") != self.curdate:
            await self.cur_user_config.set("Data", "LastProxyDate", self.curdate)
            await self.cur_user_config.set("Data", "ProxyTimes", 0)

        self.cur_user_item.status = "运行"

        self._takeover_config()

        run_limit = int(self.script_config.get("Run", "RunTimesLimit"))
        for i in range(run_limit):
            if self.run_book:
                break
            logger.info(
                f"用户 {self.cur_user_item.name} - 尝试次数: {i + 1}/{run_limit}"
            )
            self.cur_user_item.status = "运行"
            self.last_verdict_status = None
            log_start_time = datetime.now()
            self.cur_user_item.log_record[log_start_time] = LogRecord()
            self.cur_user_log = self.cur_user_item.log_record[log_start_time]
            self.script_info.log = ""
            self._dispatch_pushed_lines = 0

            if self.cur_user_config.get("Info", "IfScriptBeforeTask"):
                await execute_script_task(
                    Path(self.cur_user_config.get("Info", "ScriptBeforeTask")),
                    "脚本前任务",
                )

            await push_dispatch_log(
                self.script_info, "启动奇想盒无头一条龙: startOneDragon"
            )
            self.feed = self._feed_factory(self._on_run_event)
            await self.launcher.spawn()
            # 启动稍作等待再盯日志：文件 sink 在进程初始化后才创建
            await asyncio.sleep(1)
            await self.feed.start(log_start_time)
            self._exit_watchdog_task = asyncio.create_task(self._exit_watchdog())

            self.wait_event.clear()
            await self.wait_event.wait()
            # 本轮收口：停看门狗与日志监控，再进入结果处理
            await self._stop_monitoring()

            if self.cur_user_log.status == "Success!":
                self.run_book = True
                self.script_info.log = (
                    "检测到奇想盒已完成一条龙序列\n正在等待奇想盒自行退出"
                )
                if self.cur_user_config.get("Info", "IfScriptAfterTask"):
                    await execute_script_task(
                        Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
                        "脚本后任务",
                    )
                await asyncio.sleep(3)
                break

            logger.warning(
                f"用户 {self.cur_user_item.name} - 奇想盒代理异常: {self.cur_user_log.status}"
            )
            self.script_info.log = f"{self.cur_user_log.status}\n正在中止相关程序"
            await self.launcher.terminate()
            try:
                await Notify.push_plyer(
                    "奇想盒自动代理出现异常！",
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

            # 重试策略见 _should_retry：上游连着给出同一个结论时收口，不把整条
            # 一条龙再跑一遍（含重启游戏）；用户按提示处理后可手动重新运行
            reason = self.cur_user_log.status
            same_reason = reason != "" and reason == self._last_failure_reason
            self._last_failure_reason = reason
            if not _should_retry(
                self.last_verdict_status, same_reason_as_last=same_reason
            ):
                self.script_info.log += (
                    f"\n{reason}\n不再自动重试（同一失败原因已连续出现）"
                    "\n请按提示处理后重新运行"
                )
                logger.warning(
                    f"用户 {self.cur_user_item.name} - 判定 {self.last_verdict_status}"
                    f"（{reason}），跳过自动重试"
                )
                break

            if i + 1 < run_limit:
                self.script_info.log += f"\n将在稍后重试 ({i + 1}/{run_limit})"
                await asyncio.sleep(10)

    async def _exit_watchdog(self) -> None:
        """无日志行时的兜底收口：进程退出与停滞超时都由轮询推进。

        feed 只在有新行时才派发事件，因此两件事必须在这里做：① 进程已退出时
        再等数秒让 push 队列里最后的日志行（含收尾行）先进回调，再判定；
        ② 进程仍在运行但日志静默时照常判定一次——停滞（``Run.RunTimeLimit``）
        只有这条路径可达，否则卡死的任务会永久挂起。
        """

        with suppress(asyncio.CancelledError):
            while self.wait_event is not None and not self.wait_event.is_set():
                await asyncio.sleep(2)
                if not await self.launcher.is_running():
                    # enqueue 落盘为毫秒级，此处等收尾行进回调后再收口
                    await asyncio.sleep(5)
                    await self._evaluate_and_release()
                    return
                await self._evaluate_and_release()

    def _run_event_context_ready(self) -> bool:
        """本轮判定上下文是否就绪（feed/日志记录/等待事件均存在）。"""

        return (
            self.feed is not None
            and self.cur_user_log is not None
            and self.wait_event is not None
            and not self.wait_event.is_set()
        )

    async def _on_run_event(self, event: WhimboxRunEvent) -> None:
        """事件流回调：维护累计日志与实时进展推送，并按判定器收口。"""

        if not self._run_event_context_ready():
            return

        assert self.feed is not None and self.cur_user_log is not None

        log = self.feed.log_text
        self.cur_user_log.content = log.splitlines(keepends=True)
        self.script_info.log = log[-4000:] if len(log) > 4000 else log

        # 实时进展：步骤进入/异常/账号切换行的消息段转述到调度台（只推一次）。
        # loguru 行 = 「时间 | 级别 | 模块 - 消息」，emoji 前缀在消息段而非行首；
        # 结果块续行没有前缀结构，整行即消息。
        lines = self.cur_user_log.content
        for line in lines[self._dispatch_pushed_lines :]:
            message = (
                line.split(" - ", 1)[-1].strip() if " - " in line else line.strip()
            )
            if message.startswith(_DISPATCH_LINE_PREFIXES):
                await push_dispatch_log(self.script_info, message)
        self._dispatch_pushed_lines = len(lines)

        # 失败提示：上游结果块里默认步骤只有 ✅/⏭️/❌ 三态、不带原因，原因只在它自己的
        # ❌/🛑 行里——原样收集进报告（不把行映射回步骤：那是上游私有语义）。
        # 判据是「本行带时间列」（event.timestamp 非空即独立记录）：结果块的续行没有
        # 时间列，否则那几行 `❌…未完成` 会被当成失败提示重复收进来。
        # 「非失败提示」表（如「正在挖掘，无法收获」= 今日没得收）不进原因段，见
        # marker.py 的表注释；上游结果块原文本身不改写。
        if event.timestamp is not None:
            note = (
                event.text.split(" - ", 1)[-1].strip()
                if " - " in event.text
                else event.text.strip()
            )
            if (
                note.startswith(_FAILURE_LINE_PREFIXES)
                and not is_benign_marker(note)
                and note not in self.failure_notes
            ):
                self.failure_notes.append(note)

        await self._evaluate_and_release()

    async def _evaluate_and_release(self) -> None:
        """按判定器收口本轮：致命/完成/中止/早退/停滞任一命中即释放等待。

        收尾判定由 ``WhimboxMarkerParser`` 纯函数给出（成败取自上游结果面）；
        停滞用单调时钟（``is_log_stalled``）判定后作为输入传入。
        """

        if not self._run_event_context_ready():
            return

        assert self.feed is not None and self.cur_user_log is not None

        time_limit = self.script_config.get("Run", "RunTimeLimit")
        stalled = self.is_log_stalled(self.feed.latest_time, minutes=time_limit)
        verdict = self.parser.evaluate(
            self.feed.log_text,
            process_running=await self.launcher.is_running(),
            stalled_minutes=time_limit,
            stalled=stalled,
        )

        if verdict.status == "running":
            self.cur_user_log.status = "奇想盒正常运行中"
            return

        self.last_verdict_status = verdict.status
        if verdict.status == "success":
            self.cur_user_log.status = "Success!"
            self.cur_user_item.status = "完成"
            self.result_block = verdict.result_block
        else:
            self.cur_user_log.status = verdict.message
            self.cur_user_item.status = "异常"

        logger.info(f"奇想盒任务结果: {self.cur_user_log.status}, 释放日志等待")
        self.wait_event.set()

    async def _stop_monitoring(self) -> None:
        """停看门狗与日志监控（final_task / on_crash 共用，每步独立容错）。"""

        if self._exit_watchdog_task is not None:
            self._exit_watchdog_task.cancel()
            self._exit_watchdog_task = None
        if self.feed is not None:
            with suppress(Exception):
                await self.feed.stop()

    async def final_task(self):
        # 结束时先清理监控、看门狗与进程
        await self._stop_monitoring()
        await self.launcher.terminate()

        # 写入历史记录（对齐 General/BetterGI 行为）
        statistic_paths: list[Path] = []
        for t, log_item in self.cur_user_item.log_record.items():
            dt = t.replace(tzinfo=datetime.now().astimezone().tzinfo).astimezone(UTC4)
            log_path = Config.build_history_log_path(
                script_name=self.script_info.name,
                user_name=self.cur_user_item.name,
                log_time=dt,
            )

            if log_item.status == "奇想盒正常运行中":
                log_item.status = "任务被用户手动中止"

            if len(log_item.content) == 0:
                log_item.content = ["未捕获到任何日志内容"]
                log_item.status = "未捕获到日志"

            await Config.save_general_log(log_path, log_item.content, log_item.status)
            statistic_paths.append(log_path.with_suffix(".json"))

        if statistic_paths:
            try:
                statistics = await Config.merge_statistic_info(statistic_paths)
                if self.result_block:
                    # 上游「任务结果如下」块原样透传（多账号天然按「账号N：」分组）
                    statistics["result_block"] = self.result_block
                if self.failure_notes:
                    # 结果块默认步骤只有三态、不带原因：附上上游的 ❌/🛑 提示行原文
                    statistics["failure_notes"] = self.failure_notes
                statistics["user_info"] = self.cur_user_item.name
                start_time = getattr(self, "user_start_time", datetime.now())
                statistics["start_time"] = start_time.strftime("%Y-%m-%d %H:%M:%S")
                statistics["end_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                statistics["user_result"] = (
                    "一条龙任务已完成" if self.run_book else self.cur_user_item.result
                )
                success_symbol = "√" if self.run_book else "X"
                await push_notification(
                    "统计信息",
                    f"{datetime.now().strftime('%m-%d')} |{success_symbol}|  "
                    f"{self.cur_user_item.name} 的奇想盒自动代理统计报告",
                    statistics,
                    self.cur_user_config,
                )
            except Exception as e:
                # 失败不再静默：既记 ERROR 日志，也推到调度台实时日志
                await push_dispatch_log(self.script_info, f"推送用户统计通知失败: {e}")
                logger.opt(exception=True).error(
                    f"推送奇想盒用户统计通知时出现异常: {e}"
                )

        await self._persist_user_run_result()

        # 还原运行前配置（异常路径同样覆盖，见 on_crash）
        self._restore_config()

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
            logger.success(f"用户 {self.cur_user_uid} 的奇想盒自动代理任务已完成")
        else:
            await self.cur_user_config.set("Data", "LastProxyStatus", "失败")
            if self.cur_user_item.status != "完成":
                self.cur_user_item.status = "异常"

    async def on_crash(self, e: Exception):
        self.cur_user_item.status = "异常"
        if self.cur_user_log is not None:
            self.cur_user_log.status = f"奇想盒运行异常: {e}"
        logger.opt(exception=True).warning(f"奇想盒自动代理任务出现异常: {e}")
        if self.wait_event is not None:
            self.wait_event.set()
        with suppress(Exception):
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(
                    level="error", message=f"奇想盒自动代理任务出现异常: {e}"
                ),
            )
        with suppress(Exception):
            await self._stop_monitoring()
        with suppress(Exception):
            await self.launcher.terminate()
        with suppress(Exception):
            await self._persist_user_run_result()

        # 异常退出也要还原运行前配置（崩溃不得污染上游现场）
        try:
            self._restore_config()
        except Exception as e2:
            logger.opt(exception=True).warning(f"异常退出后还原奇想盒配置失败: {e2}")

        # 推送通知（复用 Notify）
        try:
            if (
                self.cur_user_log is not None
                and self.cur_user_log.status
                and self.cur_user_log.status != "Success!"
            ):
                await Notify.push_plyer(
                    "奇想盒运行异常",
                    f"用户 {self.cur_user_item.name}：{self.cur_user_log.status}",
                    "异常",
                    3,
                )
        except Exception:
            pass
