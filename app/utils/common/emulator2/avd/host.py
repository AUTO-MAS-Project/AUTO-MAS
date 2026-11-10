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

"""ModAVD 的宿主侧小工具：脚本用的 adb server、端口冲突、读模拟器进程的 CPU 时间。

adb server 由 ModAVD 命令行起（``modavd servers``，脱离进程树启动，不继承我们的输出管道），端口也由它
报：MAS 不自己起 adb server、不读 ``mas-avd.json``、不按端口段算端口。
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import psutil

from app.utils import get_logger

from . import cli as modavd_cli
from . import updater
from .components import root_key
from .constants import ADB_NO_LOCAL_SCAN_ENV

logger = get_logger("ModAVD 宿主")


class AdbPortConflict(RuntimeError):
    """ModAVD 要用的 adb server 端口被别的程序（不是 adb）占着（modavd 的 ``port_conflict``）。"""


class ScriptAdbPortConflict(AdbPortConflict):
    """``modavd servers`` 报端口被别的程序占着：脚本的 adb 连上去只会一直失败。"""


@dataclass(frozen=True)
class AdbServers:
    """``modavd servers`` 的结果：私有 server 与脚本用的 server 的端口、现在在不在听。"""

    adb_server_port: int
    adb_server_up: bool
    script_adb_server_port: int
    script_adb_server_up: bool

    def script_env(self) -> dict[str, str]:
        """脚本进程要叠加的环境变量：把它的 adb 指到脚本用的 server；脚本的 adb 万一自己拉起这个
        server，也不让它去扫 5555–5585 连上同机的雷电（:data:`~.constants.ADB_NO_LOCAL_SCAN_ENV`）。"""
        return {
            "ANDROID_ADB_SERVER_PORT": str(self.script_adb_server_port),
            **ADB_NO_LOCAL_SCAN_ENV,
        }


#: ``{根目录键: 最近一次 modavd servers 的结果}``，给 :func:`script_adb_env` 用。
_SERVERS: dict[str, AdbServers] = {}


def _port(data: dict, key: str) -> int:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise RuntimeError(f"modavd servers 没有给出 {key}")
    return value


async def adb_servers(root: str | Path) -> AdbServers:
    """``modavd servers``：两个 adb server 没在跑就由 modavd 以脱离方式起来，返回端口和在不在听。

    脚本进程（MaaFW 的 worker、agent、MAA …）里的 adb 客户端顺手拉起的 server 会继承那个进程的输出
    管道，读它输出的一方就等不到结束；先由 modavd 起好就没有这个问题。端口被别的程序占着时 modavd 报
    ``port_conflict``，这里抛 :class:`ScriptAdbPortConflict`（说明原样带上，里面写了改哪个端口）。
    MAS 自己的换上正在跑（:func:`.updater.update_in_progress`）时不起 modavd，直接报错。
    """
    if updater.update_in_progress(root):
        raise RuntimeError("ModAVD 正在更新，更新完再用")
    cli = await modavd_cli.resolve_cli(root)
    if cli is None:
        raise RuntimeError(f"找不到 ModAVD 命令行 {modavd_cli.ModAvdCli(root).exe}")
    try:
        data = await cli.servers()
    except modavd_cli.CLIError as error:
        message = (
            f"{error.message}（建议：{error.advice}）"
            if error.advice
            else error.message
        )
        if error.code == "port_conflict":
            raise ScriptAdbPortConflict(message) from error
        raise RuntimeError(f"modavd servers 失败：{message}") from error
    if not isinstance(data, dict):
        raise RuntimeError("modavd servers 返回的数据不是对象")
    servers = AdbServers(
        adb_server_port=_port(data, "adb_server_port"),
        adb_server_up=data.get("adb_server_up") is True,
        script_adb_server_port=_port(data, "script_adb_server_port"),
        script_adb_server_up=data.get("script_adb_server_up") is True,
    )
    _SERVERS[root_key(root)] = servers
    return servers


async def ensure_script_adb_server(root: str | Path) -> bool:
    """脚本专用 adb server 没在跑就（经 ``modavd servers``）起来，返回之后它是否在听。

    端口被别的程序占着时抛 :class:`ScriptAdbPortConflict`。之后用 :func:`script_adb_env` 取脚本的环境。
    """
    return (await adb_servers(root)).script_adb_server_up


def script_adb_port_known(root: str | Path) -> bool:
    """之前从 ``modavd servers`` 问到过这个根目录的脚本 adb 端口。"""
    return root_key(root) in _SERVERS


def script_adb_env(root: str | Path) -> dict[str, str]:
    """脚本进程要叠加的环境变量（端口取最近一次 ``modavd servers`` 报的，见 :meth:`AdbServers.script_env`）。

    还没问过（或没问成）modavd 时抛 ``RuntimeError``：不知道端口就不能让脚本的 adb 落到 5037 上。"""
    servers = _SERVERS.get(root_key(root))
    if servers is None:
        raise RuntimeError("还没从 modavd servers 拿到脚本用的 adb 端口")
    return servers.script_env()


def process_cpu_seconds(process: psutil.Process) -> float | None:
    """模拟器进程累计的 CPU 时间（冻结看门狗的判据之一）；进程没了、读不到返回 ``None``。"""
    try:
        times = process.cpu_times()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return None
    return float(times.user + times.system)


__all__ = [
    "AdbPortConflict",
    "AdbServers",
    "ScriptAdbPortConflict",
    "adb_servers",
    "ensure_script_adb_server",
    "process_cpu_seconds",
    "script_adb_env",
    "script_adb_port_known",
]
