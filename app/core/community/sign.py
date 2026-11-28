#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


"""游戏社区签到核心编排：流程锁与系统时间自检，平台执行在签到插件内。

宿主只负责"什么时候跑"，平台遍历、凭据回写与完成日期标记由附属插件
`signflow-sign` 通过 `signflow.sign` 服务承担。
"""

import asyncio
from contextlib import asynccontextmanager
from contextvars import ContextVar

from app.tools.common.community import contracts as _tool_community_contract
from app.tools.common.community import sign as _tool_community_sign_provider
from app.utils import get_logger

CommunitySignInProgressError = _tool_community_contract.CommunitySignInProgressError
CommunitySignPluginUnavailableError = (
    _tool_community_contract.CommunitySignPluginUnavailableError
)


logger = get_logger("游戏社区签到")


# 系统时钟偏差超过该阈值时，在签到失败原因里补一句校准提示。
_SYSTEM_TIME_HINT_SECONDS = 300.0
_SIGNED_STATUSES = ("成功", "已签到")


class CommunitySignOperations:
    def __init__(self) -> None:
        self._community_sign_lock = asyncio.Lock()
        self._community_sign_flow_lock = asyncio.Lock()
        self._community_sign_lock_owner: ContextVar[asyncio.Task | None] = ContextVar(
            "community_sign_lock_owner", default=None
        )

    @asynccontextmanager
    async def community_sign_flow(self):
        """保护签到请求及结果落盘，通知由调用方在锁外发送。"""

        if self._community_sign_flow_lock.locked():
            raise _tool_community_contract.CommunitySignInProgressError(
                "游戏社区签到正在执行，请稍后重试"
            )

        await self._community_sign_flow_lock.acquire()
        try:
            yield
        finally:
            self._community_sign_flow_lock.release()

    async def _enter_community_sign_lock(self) -> bool:
        """获取全局签到锁；同一任务嵌套调用时复用已持有的锁。"""

        current_task = asyncio.current_task()
        if (
            current_task is not None
            and self._community_sign_lock_owner.get() is current_task
        ):
            return False

        if self._community_sign_lock.locked():
            raise _tool_community_contract.CommunitySignInProgressError(
                "游戏社区签到正在执行，请稍后重试"
            )

        await self._community_sign_lock.acquire()
        self._community_sign_lock_owner.set(current_task)
        return True

    def _exit_community_sign_lock(self, acquired: bool) -> None:
        if not acquired:
            return
        self._community_sign_lock_owner.set(None)
        self._community_sign_lock.release()

    def _attach_system_time_hint(
        self,
        results: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        """系统时钟偏差过大时，在失败结果的原因里补一句校准提示。"""

        offset = _tool_community_sign_provider.last_system_time_offset()
        if offset is None or offset <= _SYSTEM_TIME_HINT_SECONDS:
            return results

        hint = f"疑似系统时钟偏差约 {offset:.0f} 秒，建议先校准系统时间"
        for item in results:
            # 占位失败与已签到的条目没有可展示的失败原因。
            if item.get("_notification_only") or item.get("status") in _SIGNED_STATUSES:
                continue
            reason = str(item.get("reason") or "").strip()
            item["reason"] = f"{reason}；{hint}" if reason else hint
        return results

    async def run_community_sign_in(
        self, force: bool = False
    ) -> list[dict[str, object]]:
        """协调执行游戏社区签到，避免重复签到和重复通知。

        平台遍历、凭据回写与完成日期标记都由 `signflow-sign` 附属插件承担；
        这里只保留流程锁与系统时间自检，触发时机仍由调度层决定。
        """

        # 时间检查只提供告警，不应阻塞真实签到或占用签到锁。
        time_check_task = asyncio.create_task(
            _tool_community_sign_provider.check_community_system_time()
        )
        acquired = False
        try:
            acquired = await self._enter_community_sign_lock()
            results = await self._run_plugin_sign_in(force=force)
        finally:
            self._exit_community_sign_lock(acquired)
            if not time_check_task.done():
                time_check_task.cancel()
            await asyncio.gather(time_check_task, return_exceptions=True)
        # 自检任务在 finally 收尾，此处才拿得到本轮时间偏差。
        return self._attach_system_time_hint(results)

    async def _run_plugin_sign_in(self, *, force: bool) -> list[dict[str, object]]:
        """调用签到插件跑完本轮签到。

        插件未启用时给出可读原因，而不是把插件层的"服务未注册"直接抛给调度与
        API 调用方；其余异常照旧上抛，由上层按任务来源决定记录还是重试。
        """

        from app.core.plugin import Plugin
        from app.plugin.errors import PluginError

        try:
            runner = Plugin.services.require("signflow.sign")
        except PluginError as error:
            # 用专用异常而不是 RuntimeError：API 与调度层要据此给出
            # 「去插件市场安装」的引导，而不是当成一次普通签到失败。
            raise _tool_community_contract.CommunitySignPluginUnavailableError(
                "签到插件未启用：请先在插件市场安装并启用 SignFlow 签到"
            ) from error

        return await runner(force=force)
