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

"""一次「对触发脚本所在组做一次更新类操作」的公共参数与入口（宿主侧）。

``view_update.run_view_update`` 有四个调用方：运行前 / 运行后自动更新（``embedded_manager``）、
手动 ``/maafw/update``（``api_service/update.py``）、旧投影规则载荷的补齐（``view_heal``）、
运行时发行包核对（``view_release_check``）。它们各自要组装的东西——触发脚本、组（渠道）与
同组候选、谁持视图预约、等谱系锁的上限、日志出口、停止令牌、代理、进度出口、预检——都收在
:class:`UpdateSession` 里；核心那一步（下载 / 构建 / 补齐 / 核对）仍由调用方写成
``core_call`` 交给 :meth:`UpdateSession.run`，因为四条路各不相同。

放在 ``tools/embedded``：要碰视图预约、宿主的运行环境准备与 httpx 代理对象，属于宿主接缝；
核心包不认识它。
"""

from __future__ import annotations

import functools
import threading
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.task.MaaFW.tools.core.project_update.progress import UpdateProgressEvent
from app.task.MaaFW.tools.embedded import env_confirm, view_update
from app.task.MaaFW.tools.embedded.embedded_project import GroupMember

ProgressSink = Callable[[UpdateProgressEvent], None]
Members = Sequence[GroupMember] | Callable[[], Sequence[GroupMember]]


@dataclass(frozen=True)
class UpdateProxy:
    """一次更新用的代理，两种形态各给一份。

    - ``url``：给子进程（运行池的 uv / pip、agent venv 的安装、预检）。``None`` = 没解析过，
      准备环境时沿用全局；``""`` = 直连；其余是带协议、可能带 ``user:pw@`` 的地址。
    - ``client``：给核心包下载用的 ``httpx.Proxy``；``None`` = 直连。

    地址里可能有账号密码，**一个字符都不进日志**。
    """

    url: str | None = None
    client: httpx.Proxy | None = None

    @classmethod
    def parse(cls, url: str | None, *, warn: Callable[[str], None]) -> UpdateProxy:
        """地址 → 两种形态。留空（``None`` / ``""``）原样保留 ``url``、``client`` 为 None；
        填错的（``httpx.Proxy`` 不认）用 ``warn`` 说一句（只说类型）并整条直连：``url``
        变成 ``""``——下载已按直连，预检的 uv / pip 也别再拿一个 httpx 都不认的串。"""

        if not url:
            return cls(url, None)
        try:
            return cls(url, httpx.Proxy(url))
        except Exception as exc:  # noqa: BLE001 - 代理填错不该让整次更新失败
            warn(f"MFW 项目更新代理地址无效（{type(exc).__name__}），本次直连")
            return cls("", None)


@dataclass
class UpdateSession:
    """触发脚本 S 的一次更新类操作。字段与 :func:`view_update.run_view_update` 同义：

    - ``script_id`` / ``script_name``：触发脚本（名字只给「同项目的脚本「X」正在更新」用）；
    - ``channel``：S 所在的组（谱系 + 渠道；开发者模式是私有渠道）；
    - ``members``：同组候选，或返回候选的函数（登记之后、持谱系锁时才调，拿到的是切换
      那一刻的运行状态）；
    - ``send_log``：日志出口，会从工作线程回调，调用方保证线程安全；
    - ``reservation_held``：调用方是否整段持有 S 视图的项目预约（手动更新、补齐、核对持有；
      自动更新不持有，切 S 时现拿，拿不到本轮不切）；
    - ``lock_timeout``：等谱系锁的上限，None 不限时（自动更新）；拿不到抛
      ``project_lock_busy``；
    - ``cancel_event``：用户停止时置位的令牌。等锁时、拿到锁后、调 ``core_call`` 之前各看一次；
      ``core_call`` 里面怎么停由调用方把同一个令牌交给核心包。手动更新现在不传（一次同步
      请求做完）；把手动更新挪到后台作业时由作业给一个，停止按钮置位它即可；
    - ``proxy``：见 :class:`UpdateProxy`；
    - ``progress``：核心包进度事件的出口（类型化后的 :class:`UpdateProgressEvent`），None
      表示不要进度。交给核心包的回调用 :meth:`core_progress` 取；
    - ``base``：``data/`` 的根，测试用。

    用法::

        session = UpdateSession(script_id, channel=..., members=..., send_log=...,
                                reservation_held=True, proxy=UpdateProxy.parse(url, warn=...))

        async def core_call(view_path, target, after_register):
            post_validate = session.precheck(pool_root=..., failure=..., ...)
            return await update_maafw_project_if_needed(
                view_path, ..., progress=session.core_progress(),
                post_validate=post_validate, payload=target, after_register=after_register)

        outcome = await session.run(core_call)   # view_update.ViewUpdateOutcome

    session 本身不持任何锁或预约，可以随用随建；``run`` 可以调多次（每次都是一次完整的
    谱系锁 → 组同步 → ``core_call`` → 切换 → 传播）。
    """

    script_id: str
    channel: str
    members: Members
    send_log: Callable[[str], None]
    reservation_held: bool
    script_name: str = ""
    lock_timeout: float | None = None
    cancel_event: threading.Event | None = None
    proxy: UpdateProxy = field(default_factory=UpdateProxy)
    progress: ProgressSink | None = None
    base: Path | None = None

    def core_progress(self) -> Callable[[Mapping[str, Any]], None] | None:
        """给核心包 ``progress=`` 的回调：dict 事件转成 :class:`UpdateProgressEvent` 再交给
        ``progress``。没有 ``progress`` 时为 None（核心包不发）。回调会从事件循环与工作线程
        两边来，出口自己保证线程安全；它抛的异常由核心包记一行告警吞掉，不影响更新。"""

        sink = self.progress
        if sink is None:
            return None

        def report(event: Mapping[str, Any]) -> None:
            sink(UpdateProgressEvent.of(event))

        return report

    def precheck(
        self,
        *,
        pool_root: str | Path,
        failure: MutableMapping[str, Any],
        previous_version: str | None,
        project_name: str | None,
        memo_path_for: Callable[[str], Path] | None,
        cancel_event: threading.Event,
    ) -> Callable[[Path], bool]:
        """登记前的运行环境预检（``post_validate``），见 :func:`env_confirm.build_update_precheck`。

        代理与日志出口取自 session；``cancel_event`` 由调用方显式给：自动更新给用户停止的
        令牌，手动更新与投影补齐给一个新令牌（预检一旦开始就做完）。

        **在事件循环上调**（manager 与 ``precheck`` 的导入在这里解析）。要在工作线程里组装的
        （投影补齐到真预检时才解析运行池路由）先在事件循环上取 :meth:`precheck_builder`。
        """

        return env_confirm.build_update_precheck(
            proxy_url=self.proxy.url,
            cancel_event=cancel_event,
            send_log=self.send_log,
            pool_root=pool_root,
            failure=failure,
            previous_version=previous_version,
            project_name=project_name,
            memo_path_for=memo_path_for,
        )

    def precheck_builder(self) -> Callable[..., Callable[[Path], bool]]:
        """:meth:`precheck` 的组装函数，导入在这里（事件循环上）解析好。

        返回的函数收 :meth:`precheck` 的同名关键字参数（``pool_root`` / ``failure`` /
        ``previous_version`` / ``project_name`` / ``memo_path_for`` / ``cancel_event``），
        不再导入任何东西，可以在工作线程里调。
        """

        return functools.partial(
            env_confirm.resolve_update_precheck(),
            proxy_url=self.proxy.url,
            send_log=self.send_log,
        )

    async def run(
        self, core_call: view_update.CoreCall, *, switch_label: str = "新版本"
    ) -> view_update.ViewUpdateOutcome:
        """谱系锁 → 组同步 → ``core_call(视图, 目标载荷, 登记钩子)`` → 切 S → 同组空闲脚本立即切
        并在后台确认运行环境。返回 ``ViewUpdateOutcome``（``result`` 是 ``core_call`` 的结果，
        dataclass 结果按「S 的视图换没换版本」改写过）。

        ``switch_label``：登记 / 切换日志里怎么称呼登记出来的载荷（补齐是「补齐后的版本」，
        核对是「清理后的版本」）。异常原样抛出：S 还没采纳是 ``EmbeddedProjectError``，
        锁超时 / 停止是带 ``project_lock_busy`` / ``cancelled`` 的 ``MaaFWProjectUpdateError``。
        """

        return await view_update.run_view_update(
            self.script_id,
            channel=self.channel,
            members=self.members,
            reservation_held=self.reservation_held,
            send_log=self.send_log,
            core_call=core_call,
            script_name=self.script_name,
            lock_timeout=self.lock_timeout,
            base=self.base,
            switch_label=switch_label,
            cancel_event=self.cancel_event,
        )


__all__ = ["Members", "ProgressSink", "UpdateProxy", "UpdateSession"]
