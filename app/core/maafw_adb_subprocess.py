#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
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

"""宿主侧：起 :mod:`app.core.maafw_adb_job` 子进程跑一次 MaaFramework 任务，转回日志、取回结果。

官方模拟器实例用（MaaFramework 在 MAS 进程里起的 adb 只能落到 5037，见子进程模块说明）。
解释器与 MAS 同一个（``sys.executable``），maa binding 也就是同一份。任务描述经 **stdin** 传入，
不进命令行；子进程每行日志在这里再按 ``secrets`` 打一次码才交给 ``on_log``。
调用方被取消时结束子进程。
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

JOB_SCRIPT = Path(__file__).with_name("maafw_adb_job.py")
#: 一次任务（登录要等游戏加载、选账号）的上限。
DEFAULT_TIMEOUT_SECONDS = 600.0


@dataclass
class AdbJobResult:
    returncode: int
    result: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and bool(self.result.get("ok"))


def mask(text: str, secrets: list[str]) -> str:
    for secret in sorted((s for s in secrets if s), key=len, reverse=True):
        text = text.replace(secret, "***")
    return text


def build_command() -> list[str]:
    """子进程命令行：只有解释器和脚本路径，任务内容（含账号密码）一律走 stdin。"""
    return [sys.executable, str(JOB_SCRIPT)]


async def run_adb_job(
    job: dict[str, Any],
    *,
    env: dict[str, str],
    on_log: Callable[[str], None],
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> AdbJobResult:
    """跑一次任务。``job["secrets"]`` 里的值在转回的日志与结果里都会换成 ``***``。"""
    secrets = [str(s) for s in job.get("secrets") or [] if s]
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    process = await asyncio.create_subprocess_exec(
        *build_command(),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        # 子进程的输出按 UTF-8 读回（管道下 Windows 默认是本地代码页）
        env={**env, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"},
        creationflags=creationflags,
    )
    result: dict[str, Any] = {}

    async def pump() -> None:
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(json.dumps(job, ensure_ascii=False).encode("utf-8"))
        await process.stdin.drain()
        process.stdin.close()
        while True:
            raw = await process.stdout.readline()
            if not raw:
                break
            line = mask(raw.decode("utf-8", errors="replace").rstrip("\r\n"), secrets)
            if line.startswith("RESULT "):
                with suppress(ValueError):
                    result.update(json.loads(line[len("RESULT ") :]))
                # 拿到结果就不再等 EOF：子进程里 adb 顺手拉起的 server 可能继承了这根管道，
                # 它不退出，EOF 就永远不来
                break
            if line.startswith("LOG "):
                on_log(line[len("LOG ") :])
            elif line.strip():
                on_log(line)
        await process.wait()

    try:
        await asyncio.wait_for(pump(), timeout=timeout)
    except BaseException:
        # 取消、超时、任何异常：子进程不留
        if process.returncode is None:
            with suppress(ProcessLookupError):
                process.kill()
            with suppress(Exception):
                await process.wait()
        raise
    return AdbJobResult(process.returncode or 0, result)


__all__ = ["AdbJobResult", "build_command", "mask", "run_adb_job"]
