#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#   SPDX-License-Identifier: AGPL-3.0-or-later

"""M9A 运行前登录的两种结局：登录失败（:class:`M9ALoginRequired`）与「登录交给首任务完成」
（:class:`M9AStartupTask`）。

``login.py`` 与 M9A 自己的账号流程（``account_run.py``）用这里的类：返回 :class:`M9AStartupTask` 时
流程给首任务标「启动游戏失败」并放进截止表；登录失败类继承 ``run_verdict.MaaFWClientStepFailed``，
运行判定按它认（文案直接给用户看，按普通失败重试）。
"""

from __future__ import annotations

from dataclasses import dataclass

from app.task.MaaFW.tools.embedded.run_verdict import MaaFWClientStepFailed


class M9ALoginRequired(MaaFWClientStepFailed):
    """M9A 的运行前登录判定本次无法继续运行（如 B 服登录失败）；文案直接给用户看。"""


@dataclass(frozen=True)
class M9AStartupTask:
    """选号后的公开启动任务：由同一 worker 执行，失败时结束本轮。

    ``deadline`` 是 ``time.monotonic()`` 口径的登录截止时刻，``entry`` 是首项任务应有的 entry。
    """

    deadline: float
    entry: str


__all__ = ["M9ALoginRequired", "M9AStartupTask"]
