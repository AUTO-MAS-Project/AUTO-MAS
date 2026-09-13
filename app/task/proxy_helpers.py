#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, version 3 or (at your option)
#   any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com


"""各专项自动代理共用的日志推送与进程查询小工具。

BAAH / Okww / OkNte / BetterGI / ZzzOd 在调度台日志与 log_box 采集上做的是同一
件事（向调度台追加一行、把采集节点写进当前用户推送日志），此前每家各存一份逐字
相同的实现；Okww / OkNte / ZzzOd 还各自复制了启动参数拆分与按进程名查 PID。这里
按统一语义各留一份。

``push_dispatch_log`` / ``append_push_log`` 只要求传入持有对应属性的对象，不引入
基类继承——``script_info`` 与 ``cur_user_item`` 由各专项自己持有（见各 AutoProxy 的
``self.script_info = ...``），放进 TaskExecuteBase 会把专项语义上提到共享模型层。
"""

from __future__ import annotations

import asyncio
import shlex

import psutil

__all__ = [
    "append_push_log",
    "find_pids_by_name",
    "push_dispatch_log",
    "split_args",
]


def split_args(raw: object) -> list[str]:
    """按 shell 规则拆分启动参数（保留 Windows 风格引号，空串返回空列表）。"""

    value = str(raw or "").strip()
    return shlex.split(value, posix=False) if value else []


def find_pids_by_name(process_name: str) -> list[int]:
    """按进程名收集 PID（同步全进程扫描，调用方放到线程里跑）。"""

    pids: list[int] = []
    for process in psutil.process_iter(["name"]):
        try:
            if process.info["name"] == process_name:
                pids.append(process.pid)
        except psutil.Error:
            continue
    return pids


async def push_dispatch_log(script_info: object, line: str) -> None:
    """向调度台追加流程日志（赋值 script_info.log 会触发 WebSocket 推送）。"""

    prev = script_info.log
    script_info.log = f"{prev}\n{line}" if prev else line
    # 让出事件循环：WebSocket 推送由赋值触发，不等待可能把多行攒成一次推送
    await asyncio.sleep(0)


def append_push_log(
    cur_user_item: object, log_type: str, text: str, ts: float
) -> None:
    """sink：把 log_box 采集结果写入当前用户的推送日志（供调度器聚合到报告）"""

    cur_user_item.push_log.append((log_type, text, ts))
