"""脚本单账号自动运行的总时限保护。"""

import asyncio
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime

from app.models.config import (
    BAAHConfig,
    BetterGIConfig,
    GeneralConfig,
    MaaConfig,
    MaaEndConfig,
    OkNteConfig,
    OkwwConfig,
    SrcConfig,
    UserConfigType,
    WhimboxConfig,
    ZzzOdConfig,
)
from app.models.task import LogRecord, ScriptItem, TaskExecuteBase, UserItem
from app.services import execute_script_task
from app.task.failure_capture_core import FailureCapture
from app.task.proxy_helpers import push_dispatch_log
from app.utils import get_logger

logger = get_logger("脚本运行")

# 进程级在途维护检测句柄：``asyncio.to_thread`` 的底层调用无法被取消，句柄
# 必须由跨 AutoProxy 实例（跨用户、跨重新运行）有效的 owner 持有——调度会
# 逐用户新建 AutoProxy，实例级句柄随实例失效，卡住的截图/OCR 便会在同一个
# 默认执行器里继续累积。按脚本条目（script_id）分槽：ok-nte 与 ok-ww 是不同的
# 检测资源，互不阻塞。只有底层真正结束才释放。
_INFLIGHT_DETECTIONS: dict[str, asyncio.Task] = {}


def _running_inflight_detection(script_id: str) -> asyncio.Task | None:
    """回收已结束的在途检测句柄；返回仍在执行的句柄（无则 None）。"""

    task = _INFLIGHT_DETECTIONS.get(script_id)
    if task is None:
        return None
    if task.get_loop() is not asyncio.get_running_loop():
        # 旧事件循环遗留的句柄：不适用于当前循环
        _INFLIGHT_DETECTIONS.pop(script_id, None)
        return None
    if not task.done():
        return task
    _INFLIGHT_DETECTIONS.pop(script_id, None)
    # 取回异常，避免「Task exception was never retrieved」告警
    with suppress(Exception):
        task.exception()
    return None


type ProxyScriptConfigType = (
    MaaConfig
    | MaaEndConfig
    | SrcConfig
    | OkwwConfig
    | OkNteConfig
    | GeneralConfig
    | BetterGIConfig
    | ZzzOdConfig
    | BAAHConfig
    | WhimboxConfig
)


class ScriptAutoProxyBase[S: ProxyScriptConfigType, U: UserConfigType](TaskExecuteBase):
    _failure_capture: FailureCapture | None = None

    def _on_finalize_cancel_requested(self) -> None:
        if self._failure_capture is not None:
            self.stopped_manually = True
            self._failure_capture.cancel()

    # 总时限涵盖等待和全部重试，不随日志推进重置；收尾必须完成后再切换账号。
    wait_for_finalizer_on_cancel = True

    script_info: ScriptItem
    script_config: S
    cur_user_item: UserItem
    cur_user_config: U
    # 当前尝试的日志记录用于维护跳过等运行期记账。
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
    # 单次维护检测的超时：窗口捕获/OCR 卡住时按未命中放行，不拖住主流程
    _MAINTENANCE_DETECT_TIMEOUT_SECONDS = 15.0

    @property
    def run_timeout_seconds(self) -> float:
        return self.script_config.Run.HardTimeLimit * 60

    async def run_user_scripts_before(self) -> None:
        """执行用户级任务前脚本；每用户一次，先于全部重试。"""

        self._user_scripts_started = True
        if getattr(self.cur_user_config.Info, "IfScriptBeforeTask", False):
            await execute_script_task(
                getattr(self.cur_user_config.Info, "ScriptBeforeTask", None),
                "脚本前任务",
            )

    async def run_user_scripts_after(self) -> None:
        """执行用户级任务后脚本；前置未执行过时跳过，保证成对且只一次。"""

        if not self._user_scripts_started:
            return
        self._user_scripts_started = False
        if getattr(self.cur_user_config.Info, "IfScriptAfterTask", False):
            try:
                await execute_script_task(
                    getattr(self.cur_user_config.Info, "ScriptAfterTask", None),
                    "脚本后任务",
                )
            except Exception as error:
                message = f"用户任务后脚本执行失败：{error}"
                logger.opt(exception=True).warning(message)
                logs = self.cur_user_item.iter_history_logs()
                if logs:
                    logs[-1][1].content.append(message + "\n")

    async def skip_on_game_maintenance(self, detect: Callable[[], str | None]) -> bool:
        """游戏画面维护检测：命中维护弹窗文本则把当前用户记为维护跳过。

        公告通道（ScriptManagerBase.skip_maintenance_user）在启动前完成跳过；
        这里兜底「公告未覆盖但弹窗已出现」的场景，只覆盖游戏窗口已存在的
        情况（MAS 拉起、客户端已在运行）。检测失败或窗口不存在一律放行，
        不阻断正常流程。``detect`` 由专项提供（自持窗口截图与 OCR，命中
        维护弹窗文本返回原文、否则 None）；须在 main_task 尝试循环内、
        cur_user_log 赋值之后调用。
        """

        maintenance_text = await self._detect_game_maintenance(detect)
        if maintenance_text is None:
            return False

        reason = f"游戏维护中，本次跳过（画面检测到：{maintenance_text}）"
        self.cur_user_item.status = "跳过"
        self.cur_user_item.maintenance_skipped = True
        self.cur_user_log.status = reason
        self.cur_user_log.content = [reason]
        logger.info(f"用户 {self.cur_user_item.name} - {reason}")
        await self.notify_maintenance_skip(reason)
        return True

    async def _detect_game_maintenance(
        self, detect: Callable[[], str | None]
    ) -> str | None:
        """执行一次维护检测，返回命中原文；未命中、失败或超时返回 None。

        ``asyncio.to_thread`` 已开始的调用无法被取消（Python 3.12 语义），
        故超时只放弃异步等待、不取消实际检测任务。在途句柄由进程级 registry
        按 script_id 持有，跨用户与重新运行都有效；其真正结束前不再投递新的
        检测，避免卡住的截图/OCR 在执行器里叠加。
        """

        script_id = self.script_info.script_id
        if _running_inflight_detection(script_id) is not None:
            # 上一轮底层检测仍未结束：跳过本轮采样（按未命中处理）
            return None
        task = asyncio.ensure_future(asyncio.to_thread(detect))
        _INFLIGHT_DETECTIONS[script_id] = task
        try:
            text = await asyncio.wait_for(
                asyncio.shield(task),
                timeout=self._MAINTENANCE_DETECT_TIMEOUT_SECONDS,
            )
        except Exception as e:
            logger.warning(f"游戏画面维护检测失败（忽略，继续正常流程）: {e}")
            return None
        _running_inflight_detection(script_id)
        return text

    async def notify_maintenance_skip(self, reason: str) -> None:
        """推送维护跳过通知；失败仅记警告，不改变跳过结论。"""

        try:
            await push_dispatch_log(self.script_info, reason)
            await self.task_info.send_notice(level="info", message=reason)
        except Exception:
            logger.opt(exception=True).warning("维护跳过通知推送失败（忽略）")

    async def watch_game_maintenance(
        self, detect: Callable[[], str | None], stop: asyncio.Event
    ) -> None:
        """脚本运行期间的维护弹窗后台监视（与等待脚本结果并行）。

        每 ``_MAINTENANCE_WATCH_INTERVAL_SECONDS`` 秒用专项的 detect 读一次
        游戏画面，连续命中 ``_MAINTENANCE_WATCH_CONFIRMATIONS`` 次才判维护
        （游戏内瞬时文本不算）；判定后只写 ``_maintenance_reason`` 与状态标记
        并置 stop，由 main_task 出等待循环后统一落笔结论与通知——通知放在
        最终判定处，避免与随后的成功结论互相矛盾。检测失败、窗口不存在或
        上一次次检测仍未结束时均按未命中处理。

        临时补位：上游 ok-nte / ok-ww 没有运行期维护退出信号入口（脚本把
        维护当普通重试空转），MAS 在此按画面补位，待上游提供可消费的结果面
        后改为复用。
        """

        hits = 0
        while not stop.is_set():
            await asyncio.sleep(self._MAINTENANCE_WATCH_INTERVAL_SECONDS)
            if stop.is_set():
                return
            maintenance_text = await self._detect_game_maintenance(detect)
            if maintenance_text is None:
                hits = 0
                continue
            hits += 1
            if hits < self._MAINTENANCE_WATCH_CONFIRMATIONS:
                continue
            # 成功结论先落时不再覆盖（成功与弹窗同时出现的竞态）
            if self.cur_user_log.status == "Success!":
                return
            try:
                self._maintenance_reason = (
                    f"游戏维护中，本次跳过（运行期间画面检测到：{maintenance_text}）"
                )
                self.cur_user_item.status = "跳过"
                self.cur_user_item.maintenance_skipped = True
                logger.info(
                    f"用户 {self.cur_user_item.name} - {self._maintenance_reason}"
                )
            finally:
                # 通知由 main_task 在最终判定处推送；这里必须让等待循环退出
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
            # 收尾不等待卡住的检测：只留一条可查的说明。句柄由进程级 registry
            # 持有并在底层结束后自动回收，既不堆积线程、也不拖住收尾。
            if _running_inflight_detection(self.script_info.script_id) is not None:
                logger.warning("上一轮游戏画面维护检测仍未结束，本轮不再投递新检测")

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
                user.add_log_record(datetime.now().astimezone(), record)
            record.status = message
            record.content.append(message)
            self.script_info.log = f"{message}\n正在中止相关程序"
            logger.warning(f"{self.script_info.name} - {user.name}: {message}")
