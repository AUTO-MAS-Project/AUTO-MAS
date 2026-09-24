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
from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta, timezone
from typing import Any

from app.services import Matomo
from app.utils import get_logger
from app.utils.constants import UTC8
from app.utils.platform import IS_WINDOWS

from .community_scheduler import (
    TASK_COMMUNITY_SOURCES,
    CommunityTriggerSource,
    all_community_accounts_signed,
    should_run_community_for_source,
)
from .config import Config
from .task_manager import TaskManager

logger = get_logger("主业务定时器")

# 定时错过后的补跑宽限：计划时刻过去不超过这么久（按真实流逝时间）才补跑一次。
# 只兜住短暂的睡眠 / 卡顿与春季跳表，不补长时间关机或整夜睡眠错过的定时。
TIMED_START_GRACE = timedelta(minutes=10)


def _local_now() -> datetime:
    """当前时刻（带本地偏移），单独抽出便于测试注入。"""

    return datetime.now().astimezone()


def _timed_slots_in_window(
    prev_wall: datetime, now_wall: datetime, time_str: str
) -> list[datetime]:
    """列出本地墙钟区间 ``(prev_wall, now_wall]`` 内的 ``HH:MM`` 计划时刻。

    计划时刻按本地墙钟日期逐日展开；墙钟回拨（``now_wall <= prev_wall``）时区间为空。
    """

    try:
        slot_time = datetime.strptime(time_str, "%H:%M").time()
    except (TypeError, ValueError):
        return []

    slots: list[datetime] = []
    day: date = prev_wall.date()
    while day <= now_wall.date():
        planned = datetime.combine(day, slot_time)
        if prev_wall < planned <= now_wall:
            slots.append(planned)
        day += timedelta(days=1)
    return slots


class _MainTimer:
    def __init__(self):
        self.started = False
        self.second_timer: asyncio.Task[None] | None = None
        self.hour_timer: asyncio.Task[None] | None = None
        self.community_sign_task: asyncio.Task | None = None
        # 定时启动的上次检查时刻（带本地偏移），None 表示尚未检查过
        self._last_timed_check: datetime | None = None
        # 已触发过的 (队列, 时间槽, 计划时刻)，防止秋季回拨重复的钟点再触发一次
        self._timed_fired: set[tuple[str, str, datetime]] = set()
        # 定时循环里各步骤最近一次的异常摘要，用于同一错误只记一次日志
        self._loop_errors: dict[str, str] = {}

    async def start(self):
        """启动定时器"""

        if self.started:
            logger.warning("主业务定时器仅能启动一次，无法重复启动")
            return

        self.second_timer = asyncio.create_task(self.second_task())
        self.hour_timer = asyncio.create_task(self.hour_task())
        self.started = True

        if Config.ToolsConfig.get("GameSign", "Enabled") and (
            Config.ToolsConfig.get("GameSign", "RunOnStartup")
        ):
            self.schedule_community_for_startup()

        logger.info("主业务定时器启动")

    async def stop(self):
        """停止定时器"""

        if not self.started:
            return

        tasks = [
            task
            for task in (
                self.second_timer,
                self.hour_timer,
                self.community_sign_task,
            )
            if task is not None and not task.done()
        ]
        for task in tasks:
            task.cancel()
        try:
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
                logger.info("主业务定时器已关闭")
        finally:
            self.started = False

    async def second_task(self):
        """每秒定期任务"""
        logger.info("每秒定期任务启动")

        async def arknights_pc_tick() -> None:
            if IS_WINDOWS and Config.ToolsConfig.get("ArknightsPC", "Enabled"):
                # 懒导入：启动期导入失败（如更新后端撞上 app/ 重拷窗口）时这里会再抛，
                # 不能让它把整个每秒循环带走，否则定时队列跟着停摆（#738）
                from app.MaaFW.ArknightWin32 import ArknightWin32Toolkit

                await ArknightWin32Toolkit.scheduled_task()

        while True:
            await self._run_loop_step("定时启动检查", self.timed_start)
            await self._run_loop_step("明日方舟 PC 工具巡检", arknights_pc_tick)
            await asyncio.sleep(1)

    async def hour_task(self):
        """每小时定期任务"""

        logger.info("每小时定期任务启动")

        async def upload_statistics() -> None:
            if (
                datetime.strptime(
                    Config.get("Data", "LastStatisticsUpload"), "%Y-%m-%d %H:%M:%S"
                ).date()
                != datetime.now().date()
            ):
                await Matomo.send_event(
                    "App",
                    "Version",
                    Config.VERSION,
                    1 if "beta" in Config.VERSION else 0,
                )
                await Config.set(
                    "Data",
                    "LastStatisticsUpload",
                    datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                )

        while True:
            await self._run_loop_step("统计上报", upload_statistics)
            await asyncio.sleep(3600)

    async def _run_loop_step(
        self, name: str, step: Callable[[], Awaitable[Any]]
    ) -> None:
        """执行定时循环里的一步，异常只记日志、不让整个循环退出。

        每秒循环里同一个错误会反复出现：同一步骤连续抛出相同的异常摘要时只记第一次，
        恢复正常后记一条恢复日志，之后再出错重新记录。
        """

        try:
            await step()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            signature = f"{type(error).__name__}: {error}"
            if self._loop_errors.get(name) != signature:
                self._loop_errors[name] = signature
                logger.opt(exception=error).error(
                    f"{name}异常，定时循环继续运行: {signature}"
                )
        else:
            if self._loop_errors.pop(name, None) is not None:
                logger.info(f"{name}已恢复正常")

    @logger.catch()
    async def timed_start(self):
        """定时启动代理任务

        以「上次检查 → 本次检查」的本地墙钟区间判定到点：计划时刻落在
        ``(上次检查, 本次检查]`` 内即视为到点，因此春季跳表跳过的钟点、短暂睡眠 /
        卡顿错过的定时都会在下一次检查时补上。区间左端始终不晚于当前分钟的零秒，
        与逐分钟精确匹配一致：这一分钟中途才设好的定时仍在本分钟内触发，同一分钟
        的重复命中由已触发记录挡住。补跑只在迟到不超过 ``TIMED_START_GRACE``
        时进行，超出的记日志放弃。星期按计划时刻所在的本地日期判定。
        """

        now = _local_now()
        now_wall = now.replace(tzinfo=None)
        minute_floor = now_wall.replace(second=0, microsecond=0) - timedelta(
            microseconds=1
        )
        prev = self._last_timed_check
        if prev is None:
            prev_wall = minute_floor
            real_elapsed = now_wall - minute_floor
        else:
            prev_wall = min(prev.replace(tzinfo=None), minute_floor)
            real_elapsed = now.astimezone(timezone.utc) - prev.astimezone(timezone.utc)
        self._last_timed_check = now

        # 已触发记录只需覆盖秋季回拨的重复钟点，保留前一天即可
        self._timed_fired = {
            key
            for key in self._timed_fired
            if key[2].date() >= now_wall.date() - timedelta(days=1)
        }

        for uid, queue in Config.QueueConfig.items():
            # 检查区间已前移，一个队列的配置读不出来不能连带丢掉其余队列的到点
            try:
                due = self._due_timed_slots(
                    uid, queue, prev_wall, now_wall, real_elapsed
                )
            except Exception as e:
                logger.opt(exception=e).error(f"读取队列定时设置失败：{uid}")
                continue

            if not due:
                continue

            # 同一队列一次检查内只唤起一次，多个到点的时间槽一并记为已触发
            for time_set_id, planned in due:
                self._timed_fired.add((str(uid), time_set_id, planned))
            planned = max(planned for _, planned in due)

            if now_wall - planned >= timedelta(minutes=1):
                logger.info(f"补跑错过的定时 {planned:%Y-%m-%d %H:%M}：{uid}")
            logger.info(f"定时唤起任务：{uid}")
            # 检查区间已前移，一个队列唤起失败不能连带跳过其余队列
            try:
                await TaskManager.add_task(
                    "AutoProxy",
                    str(uid),
                    new_task_info={
                        "queueId": str(uid),
                        "taskName": f"队列 - {queue.get('Info', 'Name')}",
                        "taskType": "定时代理",
                    },
                    trigger_source="scheduled_task",
                )
                await queue.set(
                    "Data", "LastTimedStart", planned.strftime("%Y-%m-%d %H:%M")
                )
            except Exception as e:
                logger.opt(exception=e).error(f"定时唤起任务失败：{uid}")

    def _due_timed_slots(
        self,
        uid,
        queue,
        prev_wall: datetime,
        now_wall: datetime,
        real_elapsed: timedelta,
    ) -> list[tuple[str, datetime]]:
        """列出队列在本次检查区间内到点、且仍在补跑窗口内的 (时间槽, 计划时刻)。"""

        # 循环队列由队列项各自的周期驱动，定时设置对它不生效
        if queue.get("Info", "CycleEnabled"):
            return []

        if not queue.get("Info", "TimeEnabled"):
            return []

        last_timed_start = queue.get("Data", "LastTimedStart")
        due: list[tuple[str, datetime]] = []

        for time_set_id, time_set in queue.TimeSet.items():
            if not time_set.get("Info", "Enabled"):
                continue

            for planned in _timed_slots_in_window(
                prev_wall, now_wall, time_set.get("Info", "Time")
            ):
                if planned.strftime("%A") not in time_set.get("Info", "Days"):
                    continue

                key = (str(uid), str(time_set_id), planned)
                # 避免重复调起任务：本次运行内按时间槽与计划时刻去重（当天改了时间的
                # 槽按新时刻照常触发），重启后靠持久化的 LastTimedStart 兜住同一分钟
                if key in self._timed_fired or (
                    planned.strftime("%Y-%m-%d %H:%M") == last_timed_start
                ):
                    continue

                # 迟到时长按真实流逝时间封顶：春季跳表时墙钟跨过一小时，真实只过了一瞬
                lateness = min(now_wall - planned, real_elapsed)
                if lateness > TIMED_START_GRACE:
                    self._timed_fired.add(key)
                    logger.info(
                        f"定时 {planned:%Y-%m-%d %H:%M} 已错过 {lateness}，"
                        f"超出补跑窗口，不再唤起队列：{uid}"
                    )
                    continue

                due.append((str(time_set_id), planned))

        return due

    def schedule_community_for_startup(self) -> None:
        """Schedule one background community sign-in after application startup."""

        if not (
            Config.ToolsConfig.get("GameSign", "Enabled")
            and (Config.ToolsConfig.get("GameSign", "RunOnStartup"))
        ):
            return

        if self.community_sign_task is not None and not self.community_sign_task.done():
            logger.debug("游戏社区签到后台任务正在执行，跳过重复派发")
            return

        task = asyncio.create_task(self.try_community_for_task(source="startup"))
        self.community_sign_task = task
        task.add_done_callback(self._on_community_sign_done)

    def _on_community_sign_done(self, task: asyncio.Task) -> None:
        """清理社区签到任务并记录未处理异常。"""

        if self.community_sign_task is task:
            self.community_sign_task = None
        if task.cancelled():
            return

        try:
            task.result()
        except Exception as e:
            logger.opt(exception=e).error("游戏社区签到后台任务异常")

    async def _execute_community_sign(
        self, *, source: CommunityTriggerSource = "scheduled"
    ) -> list[dict[str, object]]:
        """执行游戏社区签到并按触发来源决定通知方式。"""
        from app.core.community_sign import (
            CommunitySignInProgressError,
            community_sign_flow,
            run_community_sign_in,
        )
        from app.tools.community import format_community_sign_results

        today = datetime.now(tz=UTC8).strftime("%Y-%m-%d")

        try:
            # 流程锁覆盖签到和结果落盘，通知在锁外发送。
            async with community_sign_flow():
                logger.info("开始执行游戏社区签到")
                results = await run_community_sign_in(force=False)

                # 如果所有用户都已签到（无新结果），保留已有结果
                if not results:
                    logger.info("所有用户今日已签到，跳过")
                    if all_community_accounts_signed(
                        Config.ToolsConfig.GameSign_Accounts, today
                    ):
                        await Config.ToolsConfig.set("GameSign", "LastSignDate", today)
                    return []

                # 格式化并合并结果
                formatted = format_community_sign_results(results)
                await Config.update_community_results(formatted)

                # 检查是否所有用户都已签到，更新全局 LastSignDate
                if all_community_accounts_signed(
                    Config.ToolsConfig.GameSign_Accounts, today
                ):
                    await Config.ToolsConfig.set("GameSign", "LastSignDate", today)

            logger.success("游戏社区签到执行完成")

            # 任务触发的结果由任务完成通知消费；其它自动来源单独发送。
            if source not in TASK_COMMUNITY_SOURCES and Config.ToolsConfig.get(
                "GameSign", "NotifyEnabled"
            ):
                from app.tools.community_notify import push_community_notification

                try:
                    failed_channels = await push_community_notification(results)
                except Exception as exc:
                    logger.warning(f"游戏社区签到完成，但通知服务异常: {exc}")
                else:
                    if failed_channels:
                        logger.warning(
                            f"游戏社区结果通知部分失败: {'、'.join(failed_channels)}"
                        )
            return results

        except CommunitySignInProgressError:
            logger.info("游戏社区签到正在执行，跳过本次触发")
        except Exception as e:
            logger.error(f"游戏社区签到执行失败: {e}")
            # 保留已有结果，不覆盖为错误信息
            logger.exception("游戏社区签到执行异常堆栈")
        return []

    async def try_community_for_task(
        self, *, source: CommunityTriggerSource | None = None
    ) -> list[dict[str, object]]:
        """执行 MAS 自动签到并返回结果。

        ``task`` 结果由任务完成通知汇总，``startup`` 结果独立通知。
        """
        if source is None:
            source = "task_manual"

        if not should_run_community_for_source(
            enabled=Config.ToolsConfig.get("GameSign", "Enabled"),
            run_on_startup=Config.ToolsConfig.get("GameSign", "RunOnStartup"),
            source=source,
        ):
            return []

        today = datetime.now(tz=UTC8).strftime("%Y-%m-%d")

        # 快速检查：是否没有待处理账号
        if all_community_accounts_signed(Config.ToolsConfig.GameSign_Accounts, today):
            return []

        return await self._execute_community_sign(source=source)


MainTimer = _MainTimer()
