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
import random
from datetime import datetime, timedelta

from app.services import Matomo
from app.utils import get_logger
from app.utils.constants import UTC8
from app.models.task import TaskMode, TaskTriggerSource
from .config import Config
from .task_dispatcher import TaskDispatcher


logger = get_logger("主业务定时器")


class _MainTimer:

    def __init__(self):
        self.started = False
        self.second_timer: asyncio.Task[None] | None = None
        self.hour_timer: asyncio.Task[None] | None = None
        self.game_sign_task: asyncio.Task[None] | None = None

    async def start(self):
        """启动定时器"""

        if self.started:
            logger.warning("主业务定时器仅能启动一次，无法重复启动")
            return

        self.second_timer = asyncio.create_task(MainTimer.second_task())
        self.hour_timer = asyncio.create_task(MainTimer.hour_task())
        self.started = True
        logger.info("主业务定时器启动")

    async def stop(self):
        """停止定时器"""

        if not self.started:
            return

        try:
            tasks = [
                task
                for task in (
                    self.second_timer,
                    self.hour_timer,
                    self.game_sign_task,
                )
                if task is not None and not task.done()
            ]
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            logger.info("主业务定时器已关闭")
        finally:
            self.started = False

    async def second_task(self):
        """每秒定期任务"""
        logger.info("每秒定期任务启动")

        while True:

            await self.timed_start()

            if Config.tools.arknights_pc.enabled:
                from app.MaaFW import ArknightWin32Toolkit

                await ArknightWin32Toolkit.scheduled_task()

            self._schedule_game_sign_check()

            await asyncio.sleep(1)

    async def hour_task(self):
        """每小时定期任务"""

        logger.info("每小时定期任务启动")

        while True:

            if Config.setting.data.last_statistics_upload.date() != datetime.now(
                tz=UTC8
            ).date():
                await Matomo.send_event(
                    "App",
                    "Version",
                    Config.VERSION,
                    1 if "beta" in Config.VERSION else 0,
                )
                Config.setting.data.last_statistics_upload = datetime.now(tz=UTC8)
                await Config.setting.commit()

            await asyncio.sleep(3600)

    @logger.catch()
    async def timed_start(self):
        """定时启动代理任务（读 ``Config.queues`` + ``TaskDispatcher``）。"""

        now = datetime.now()
        curtime = now.strftime("%Y-%m-%d %H:%M")
        curday = now.strftime("%A")

        for uid, queue in Config.queues.items():
            if not queue.info.time_enabled:
                continue

            # 避免同一分钟内重复调起
            last = queue.data.last_timed_start.strftime("%Y-%m-%d %H:%M")
            if curtime == last:
                continue

            for time_set in queue.time_sets.values():
                if (
                    time_set.info.enabled
                    and curday in time_set.info.days
                    and curtime[11:16] == time_set.info.time.strftime("%H:%M")
                ):
                    logger.info(f"定时唤起任务：{uid}")
                    try:
                        await TaskDispatcher.start(
                            mode=TaskMode.AUTO_PROXY,
                            queue_id=str(uid),
                            script_id=None,
                            user_id=None,
                            trigger_source=TaskTriggerSource.SCHEDULED_TASK,
                        )
                    except Exception as error:
                        logger.error(f"定时队列 {uid} 无法创建任务：{error}")
                        continue
                    queue.data.last_timed_start = now
                    await queue.commit()

                    # 定时任务触发游戏签到
                    self.schedule_game_sign_for_task()

    def _schedule_game_sign_check(self) -> None:
        """派发签到检查，不阻塞每秒调度循环。"""

        if not Config.tools.game_sign.enabled:
            return

        check_time = datetime.now(tz=UTC8)
        if check_time.second != 0:
            return

        if self.game_sign_task is not None and not self.game_sign_task.done():
            return

        task = asyncio.create_task(self.check_game_sign(check_time=check_time))
        self.game_sign_task = task
        task.add_done_callback(self._on_game_sign_check_done)

    def schedule_game_sign_for_task(self) -> None:
        """派发任务生命周期签到，并与定时签到共享任务守卫。"""

        if self.game_sign_task is not None and not self.game_sign_task.done():
            logger.debug("游戏社区签到后台任务正在执行，跳过重复派发")
            return

        task = asyncio.create_task(self.try_game_sign_for_task())
        self.game_sign_task = task
        task.add_done_callback(self._on_game_sign_check_done)

    def _on_game_sign_check_done(self, task: asyncio.Task[None]) -> None:
        """清理签到任务并记录未处理异常。"""

        if self.game_sign_task is task:
            self.game_sign_task = None
        if task.cancelled():
            return

        try:
            task.result()
        except Exception as e:
            logger.error("游戏社区签到后台任务异常", exc_info=e)

    async def check_game_sign(
        self, *, check_time: datetime | None = None
    ) -> None:
        """检查并执行游戏社区签到

        启用签到 + 时间窗口内随机时刻执行，窗口外补签。
        仅在整分钟时执行（秒数 != 0 时跳过），因为调度精度为分钟级。
        """

        gs = Config.tools.game_sign
        if not gs.enabled:
            return

        now = check_time or datetime.now(tz=UTC8)
        if now.second != 0:
            return

        today = now.date()

        # 检查是否所有启用的用户今日都已签到
        all_users_signed = True
        for account in Config.tools.accounts.values():
            if account.info.enabled and account.info.last_sign_date != today:
                all_users_signed = False
                break

        if all_users_signed:
            return

        # 窗口时间为 ui format hm：用 HH:MM 与当前时刻比较
        now_hm = now.strftime("%H:%M")
        window_start_hm = gs.window_start.strftime("%H:%M")
        window_end_hm = gs.window_end.strftime("%H:%M")

        if now_hm < window_start_hm:
            return

        if now_hm > window_end_hm:
            await self._execute_game_sign()
            return

        scheduled_time_str = gs.scheduled_time

        if not scheduled_time_str:
            # 首次进入窗口：按剩余秒数随机计划今日签到时刻
            window_end = now.replace(
                hour=gs.window_end.hour,
                minute=gs.window_end.minute,
                second=0,
                microsecond=0,
            )
            remaining_seconds = int((window_end - now).total_seconds())
            if remaining_seconds <= 0:
                await self._execute_game_sign()
                return
            random_offset = random.randint(0, remaining_seconds)
            scheduled_time = now + timedelta(seconds=random_offset)
            gs.scheduled_time = scheduled_time.strftime("%H:%M")
            await Config.tools.commit()
            return

        # 检查是否到达计划时间（分钟精度）
        if now_hm == scheduled_time_str:
            await self._execute_game_sign()
            # 同分钟内避免重复触发
            gs.scheduled_time = ""
            await Config.tools.commit()

    async def _execute_game_sign(self) -> None:
        """执行游戏签到并处理结果"""
        from app.tools.game_sign import (
            GameSignInProgressError,
            format_sign_results,
            run_all_sign_in,
        )

        today = datetime.now(tz=UTC8).date()
        gs = Config.tools.game_sign

        try:
            logger.info("开始执行游戏社区签到")
            results = await run_all_sign_in(force=False)

            # 如果所有用户都已签到（无新结果），保留已有结果
            if not results:
                logger.info("所有用户今日已签到，跳过")
                gs.last_sign_date = today
                gs.scheduled_time = ""
                await Config.tools.commit()
                return

            # 格式化并合并结果
            formatted = format_sign_results(results)
            await Config.update_game_sign_results(formatted)

            # 清除计划时间
            gs.scheduled_time = ""

            # 检查是否所有用户都已签到，更新全局 last_sign_date
            all_signed_after = True
            for account in Config.tools.accounts.values():
                if account.info.enabled and account.info.last_sign_date != today:
                    all_signed_after = False
                    break
            if all_signed_after:
                gs.last_sign_date = today

            await Config.tools.commit()

            logger.success("游戏社区签到执行完成")

            # 如果启用通知，发送签到结果
            if gs.notify_enabled:
                from app.tools.game_sign_notify import push_game_sign_notification

                failed_channels = await push_game_sign_notification(results)
                if failed_channels:
                    logger.warning(
                        f"游戏签到结果通知部分失败: {'、'.join(failed_channels)}"
                    )

        except GameSignInProgressError:
            logger.info("游戏社区签到正在执行，跳过本次触发")
        except Exception as e:
            logger.error(f"游戏社区签到执行失败: {e}")
            # 保留已有结果，不覆盖为错误信息
            logger.exception("游戏社区签到执行异常堆栈")

    async def try_game_sign_for_task(self) -> None:
        """任务生命周期触发的游戏签到（跳过已签到用户）

        由定时任务启动、任务结束等事件触发。
        不受全局 last_sign_date 限制，仅按用户 last_sign_date 过滤。
        """
        gs = Config.tools.game_sign
        if not gs.enabled:
            return

        today = datetime.now(tz=UTC8).date()

        # 快速检查：是否所有用户都已签到
        all_signed = True
        for account in Config.tools.accounts.values():
            if account.info.enabled and account.info.last_sign_date != today:
                all_signed = False
                break
        if all_signed:
            return

        from app.tools.game_sign import (
            GameSignInProgressError,
            format_sign_results,
            run_all_sign_in,
        )

        try:
            results = await run_all_sign_in(force=False)
            if not results:
                return

            formatted = format_sign_results(results)
            await Config.update_game_sign_results(formatted)

            # 签到后检查是否所有用户都已完成
            all_signed_after = True
            for account in Config.tools.accounts.values():
                if account.info.enabled and account.info.last_sign_date != today:
                    all_signed_after = False
                    break
            if all_signed_after:
                gs.last_sign_date = today
                gs.scheduled_time = ""
                await Config.tools.commit()

            logger.info("任务触发的游戏签到已完成")

            if gs.notify_enabled:
                from app.tools.game_sign_notify import push_game_sign_notification

                failed_channels = await push_game_sign_notification(results)
                if failed_channels:
                    logger.warning(
                        f"游戏签到结果通知部分失败: {'、'.join(failed_channels)}"
                    )

        except GameSignInProgressError:
            logger.info("游戏社区签到正在执行，跳过本次触发")
        except Exception as e:
            logger.error(f"任务触发的游戏签到失败: {e}")


MainTimer = _MainTimer()
