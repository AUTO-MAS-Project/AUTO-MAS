"""脚本单账号自动运行的总时限保护。"""

import asyncio
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from app.core.ws import Publisher, protocol
from app.models.ConfigBase import ConfigBase
from app.models.schema import WSTaskNoticeData
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase, UserItem
from app.task.proxy_helpers import push_dispatch_log
from app.utils.logger import get_logger

logger = get_logger("脚本运行")


class ScriptAutoProxyBase(TaskExecuteBase):
    # 总时限涵盖等待和全部重试，不随日志推进重置；收尾必须完成后再切换账号。
    wait_for_finalizer_on_cancel = True

    script_info: ScriptItem
    script_config: ConfigBase
    cur_user_item: UserItem
    cur_user_config: ConfigBase
    # main_task 尝试循环内赋值的当前日志记录，维护跳过等运行期记账会写入。
    cur_user_log: LogRecord
    # 用户级前/后脚本成对标记：前置跑过才收尾后置，且每用户只收尾一次。
    _user_scripts_started: bool = False
    # 运行期维护弹窗监视的命中结论（含原文），未命中为 None；由
    # watch_game_maintenance 写入、main_task 出等待循环后消费。
    _maintenance_reason: str | None = None
    # 运行期监视参数：轮询间隔与确认次数（连续命中才算，防止游戏内
    # 短暂出现的公告文本被误判为维护弹窗）。
    _MAINTENANCE_WATCH_INTERVAL_SECONDS = 30.0
    _MAINTENANCE_WATCH_CONFIRMATIONS = 2

    @property
    def run_timeout_seconds(self) -> float:
        return self.script_config.get("Run", "HardTimeLimit") * 60

    async def run_user_scripts_before(self) -> None:
        """执行用户级任务前脚本；每用户一次，先于全部重试。"""

        # 就地导入：专项包会反向导入本模块，模块级导入会成环。
        from app.task.general.tools import execute_script_task

        self._user_scripts_started = True
        if self.cur_user_config.get("Info", "IfScriptBeforeTask"):
            await execute_script_task(
                Path(self.cur_user_config.get("Info", "ScriptBeforeTask")),
                "脚本前任务",
            )

    async def run_user_scripts_after(self) -> None:
        """执行用户级任务后脚本；前置未执行过时跳过，保证成对且只一次。"""

        from app.task.general.tools import execute_script_task

        if not self._user_scripts_started:
            return
        self._user_scripts_started = False
        if self.cur_user_config.get("Info", "IfScriptAfterTask"):
            await execute_script_task(
                Path(self.cur_user_config.get("Info", "ScriptAfterTask")),
                "脚本后任务",
            )

    async def skip_on_game_maintenance(self, detect: Callable[[], str | None]) -> bool:
        """游戏画面维护检测：命中维护弹窗文本则把当前用户记为维护跳过。

        公告通道（ScriptManagerBase.skip_maintenance_user）在启动前完成跳过；
        这里兜底「公告未覆盖但弹窗已出现」的场景，只覆盖游戏窗口已存在的
        情况（MAS 拉起、客户端已在运行）。检测失败或窗口不存在一律放行，
        不阻断正常流程。``detect`` 由专项提供（自持窗口截图与 OCR，命中
        维护弹窗文本返回原文、否则 None）；须在 main_task 尝试循环内、
        cur_user_log 赋值之后调用。
        """

        try:
            maintenance_text = await asyncio.to_thread(detect)
        except Exception as e:
            logger.opt(exception=True).warning(
                f"游戏画面维护检测失败（忽略，继续正常流程）: {e}"
            )
            return False
        if maintenance_text is None:
            return False

        reason = f"游戏维护中，本次跳过（画面检测到：{maintenance_text}）"
        self.cur_user_item.status = "跳过"
        self.cur_user_item.maintenance_skipped = True
        self.cur_user_log.status = reason
        self.cur_user_log.content = [reason]
        logger.info(f"用户 {self.cur_user_item.name} - {reason}")
        await push_dispatch_log(self.script_info, reason)
        await Publisher.send(
            id=self.task_info.task_id,
            type=protocol.TASK_NOTICE,
            data=WSTaskNoticeData(level="info", message=reason),
        )
        return True

    async def watch_game_maintenance(
        self, detect: Callable[[], str | None], stop: asyncio.Event
    ) -> None:
        """脚本运行期间的维护弹窗后台监视（与等待脚本结果并行）。

        每 ``_MAINTENANCE_WATCH_INTERVAL_SECONDS`` 秒用专项的 detect 读一次
        游戏画面，连续命中 ``_MAINTENANCE_WATCH_CONFIRMATIONS`` 次才判维护
        （游戏内瞬时文本不算）；判定后写入 ``_maintenance_reason``、置 stop
        事件，由 main_task 出等待循环后统一收尾。仅写状态标记与通知，不改
        cur_user_log——日志监控停止后由 main_task 落笔，避免与末次轮询互相
        覆盖。脚本已有成功结论或窗口不存在/识别失败时不作处理。
        """
        hits = 0
        while not stop.is_set():
            await asyncio.sleep(self._MAINTENANCE_WATCH_INTERVAL_SECONDS)
            if stop.is_set():
                return
            try:
                maintenance_text = await asyncio.to_thread(detect)
            except Exception:
                hits = 0
                continue
            if maintenance_text is None:
                hits = 0
                continue
            hits += 1
            if hits < self._MAINTENANCE_WATCH_CONFIRMATIONS:
                continue
            # 成功结论先落时不再覆盖（成功与弹窗同时出现的竞态）
            if self.cur_user_log.status == "Success!":
                return
            self._maintenance_reason = (
                f"游戏维护中，本次跳过（运行期间画面检测到：{maintenance_text}）"
            )
            self.cur_user_item.status = "跳过"
            self.cur_user_item.maintenance_skipped = True
            logger.info(f"用户 {self.cur_user_item.name} - {self._maintenance_reason}")
            await push_dispatch_log(self.script_info, self._maintenance_reason)
            await Publisher.send(
                id=self.task_info.task_id,
                type=protocol.TASK_NOTICE,
                data=WSTaskNoticeData(level="info", message=self._maintenance_reason),
            )
            stop.set()
            return

    def clear_maintenance_hit(self) -> None:
        """成功结论优先：清除运行期晚到的维护命中标记，避免被误报成维护跳过。"""
        self.cur_user_item.maintenance_skipped = False
        self._maintenance_reason = None

    async def _finalize_task(self) -> None:
        """收尾时成对执行后置脚本；收尾被取消或异常中断也仍会尝试执行。"""

        try:
            await super()._finalize_task()
        finally:
            await self.run_user_scripts_after()

    async def _run_main_task(self) -> None:
        timeout = asyncio.timeout(self.run_timeout_seconds)
        try:
            async with timeout:
                await self.main_task()
        except TimeoutError:
            # 脚本内部的 TimeoutError 仍交给原异常流程处理。
            if not timeout.expired():
                raise

            message = f"运行超过 {self.run_timeout_seconds / 60:g} 分钟，已终止"
            user = self.cur_user_item
            user.status = "异常"
            if user.log_record:
                record = user.log_record[max(user.log_record)]
            else:
                record = LogRecord()
                user.log_record[datetime.now()] = record
            record.status = message
            record.content.append(message)
            self.script_info.log = f"{message}\n正在中止相关程序"
            logger.warning(f"{self.script_info.name} - {user.name}: {message}")
