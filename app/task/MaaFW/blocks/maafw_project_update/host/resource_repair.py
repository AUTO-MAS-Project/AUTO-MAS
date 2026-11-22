#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""运行中资源包加载失败后的发行包核对与修复（宿主侧，项目更新这一块）。

MaaFramework 拒收资源包（``load_failed``）多半是旧版本残留（新版已删的 pipeline 跟着导入进了载荷、
节点重名）：这里与官方发行包核对一次（``view_release_check.check_view_release``），视图换上了清理过的
载荷就告诉调用方立刻再跑一次（不重启游戏 / 模拟器、不占重试次数），否则写一行停止原因。

一个账号一份 :class:`MaaFWResourceRepair`，状态跨尝试保留：每次运行只核对一次（``checked``）；正在跑的
核对任务（``task``）留给调用方释放项目预约前等它（``project_path.release_run_reservation`` 的
``pending``）。入参只有普通数据（:class:`MaaFWRepairRequest`，调用方只在要修资源的那条分支里从配置
组装），账号日志经调用方给的 ``log(message, *, warning=False)`` 写出。
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# 资源包加载失败（节点重名、JSON 写错、资源目录不在）：资源文件一次尝试到下一次不会自己变，
# 重试只会原样再失败、还要白白重启游戏 / 模拟器。与环境级失败（run_verdict）分开说：不是运行环境的事。
RESOURCE_FAILURE_STOP_MESSAGE = (
    "资源包加载失败，重试也不会有别的结果，已停止本轮（不再重启游戏/模拟器）"
)
# 资源包加载失败后换了载荷、立刻再跑的那一次：（开头那行，之后「上一次（…）」里的称呼）。
# 不计入尝试次数，所以不编号。
RERUN_AFTER_CLEANUP = (
    "已清理残留，立即重新运行（不计入尝试次数）",
    "清理残留后的重新运行",
)
RERUN_AFTER_SWITCH = (
    "已换上同项目其他托管在用的版本，立即重新运行（不计入尝试次数）",
    "换版本后的重新运行",
)


@dataclass(frozen=True)
class MaaFWRepairRequest:
    """核对要用的普通数据，调用方从脚本配置取好。

    ``follow_source``：开发者模式（跟随来源目录，``embedded_project.follow_source_enabled``）；
    ``channel``：更新渠道（``resolve_update_credentials(...).channel``）；``proxy_url``：托管级解析出的
    代理（``resolve_update_proxy_url``，没有为 None）；``shell_hint``：导入报告里的外壳家族
    （``shell_hint_from_report``）。
    """

    script_id: str
    script_name: str
    follow_source: bool
    channel: Any
    proxy_url: str | None = field(repr=False)
    shell_hint: str


class MaaFWResourceRepair:
    """一个账号这次运行的资源包修复：每次运行只核对一次，正在跑的核对任务留给释放预约时等。"""

    def __init__(self, log: Callable[..., None]) -> None:
        self._log = log
        self.checked = False
        self.task: asyncio.Task[Any] | None = None

    async def run(
        self, kind: str, request: MaaFWRepairRequest
    ) -> tuple[str, str] | None:
        """资源包加载失败之后：视图刚换了载荷（清掉了旧版本残留，或经组同步换上了同组兄弟已
        清理过的那份）就返回下一次的（开头那行, 称呼），该立刻再跑一次；其余情况写一行停止
        原因、返回 None（不重试）。

        只有 MaaFramework 拒收资源包（``load_failed``）才核对：资源目录不在（``missing``）不是
        多了文件。每次运行只核对一次；开发者模式（跟随来源目录）以来源为准、不更新，不核对。
        核对期间被取消（用户停止）时置停止令牌再上抛，核对任务本身经 ``asyncio.shield`` 跑完。
        """

        if kind != "load_failed" or self.checked:
            self._log(RESOURCE_FAILURE_STOP_MESSAGE, warning=True)
            return None
        self.checked = True

        if request.follow_source:
            self._log(
                "开发者模式（跟随来源目录）以来源目录为准，不与官方发行包核对；"
                + RESOURCE_FAILURE_STOP_MESSAGE,
                warning=True,
            )
            return None

        import httpx

        from .view_release_check import (
            check_view_release,
            describe_outcome,
            release_group_members,
        )

        script_id = request.script_id
        proxy_url = request.proxy_url
        try:
            proxy = httpx.Proxy(proxy_url) if proxy_url else None
        except Exception:  # noqa: BLE001 - 代理填错按直连，地址不进日志
            proxy = None
        stop = threading.Event()
        task = asyncio.create_task(
            check_view_release(
                script_id,
                channel=request.channel,
                members=lambda: release_group_members(script_id),
                send_log=self._log,
                proxy=proxy,
                shell_hint=request.shell_hint,
                script_name=request.script_name,
                cancel_event=stop,
            )
        )
        # 核对 / 清理 / 切视图都在工作线程里改载荷与视图：用户这时点停止，得等它收尾再放预约
        # （release_run_reservation 会等这个任务），否则编辑页的导入、手动更新能同时动同一棵视图。
        self.task = task
        try:
            outcome = await asyncio.shield(task)
        except asyncio.CancelledError:
            stop.set()
            raise
        self._log(describe_outcome(outcome), warning=not outcome.switched)
        cleaned = outcome.status in {"cleaned", "repointed"}
        if outcome.switched and outcome.version_changed:
            # 等锁那几秒里组被推到了新版本、视图跟着换了：本次的 interface 与运行计划是按旧
            # 版本建的，不能拿来跑新版本。停下，下次运行前按新版本重做检查。
            self._log(
                f"本托管已换到 {outcome.version or '新版本'}，这一轮不再重新运行，"
                "下次运行会按新版本重新准备",
                warning=True,
            )
            return None
        if outcome.switched:
            # 视图换了载荷就重跑，不看 status：同组兄弟已清理过、本托管经组同步换过来时，
            # 核对的是换来的那份（status 是 verified / clean），旧视图里的残留照样没了。
            self._log(
                "已换上清理后的版本，立即重新运行（不重启游戏/模拟器）"
                if cleaned
                else "立即用换上的版本重新运行（不重启游戏/模拟器）"
            )
            return RERUN_AFTER_CLEANUP if cleaned else RERUN_AFTER_SWITCH
        if cleaned:
            self._log(
                "清理后的版本已准备好，但本托管这次没能切换过去，下次运行前自动切换",
                warning=True,
            )
        self._log(RESOURCE_FAILURE_STOP_MESSAGE, warning=True)
        return None


__all__ = [
    "RERUN_AFTER_CLEANUP",
    "RERUN_AFTER_SWITCH",
    "RESOURCE_FAILURE_STOP_MESSAGE",
    "MaaFWRepairRequest",
    "MaaFWResourceRepair",
]
