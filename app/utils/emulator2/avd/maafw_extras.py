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

"""MaaFramework 在魔改 AVD 上的截图通道：AVDExtras（读 ``SHM_videmulator<控制台端口>``）。

AVDExtras 首次出现在 MaaFramework v5.7.0（#1126）。它连上时跑 ``{ADB} -s {ADB_SERIAL} emu screenrecord
webrtc start`` 拿共享内存名，断开时跑 ``... webrtc stop``。``adb emu`` 只认 ``emulator-<控制台端口>``
序列号，而交给脚本的地址是 ``127.0.0.1:<adb 端口>``（脚本自己的 adb server 上），所以：

- ``command.EmuWebrtcStart`` 改走我们的私有 server：``<SDK adb> -P <私有端口> -s emulator-<控制台端口>
  emu screenrecord webrtc start``；
- ``command.EmuWebrtcStop`` 换成无害的 ``<SDK adb> -P <私有端口> version``：真停掉推流，共享内存就没了，
  同一台实例上的下一次连接拿到的是黑帧。开机调优已经开了
  推流，它本来就该一直开着。

截图方式只给 EmulatorExtras，不留普通 adb 回落（用户 09-26 定：魔改 AVD 上普通 adb 截图约 250 ms，
「不如不做」）；做不到就让连接失败、明确报错。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

#: AVDExtras 进 MaaFramework 的版本。
AVD_EXTRAS_MIN_MAAFW_VERSION = (5, 7, 0)


def build_maafw_avd_config(
    adb_path: str | Path, server_port: int, console_port: int
) -> dict[str, Any]:
    """AdbController 的 ``config``：开 AVDExtras，推流开关改走私有 adb server。"""
    adb = str(adb_path)
    return {
        "extras": {"avd": {"enable": True}},
        "command": {
            "EmuWebrtcStart": [
                adb,
                "-P",
                str(int(server_port)),
                "-s",
                f"emulator-{int(console_port)}",
                "emu",
                "screenrecord webrtc start",
            ],
            "EmuWebrtcStop": [adb, "-P", str(int(server_port)), "version"],
        },
    }


def parse_version(text: str | None) -> tuple[int, ...] | None:
    """``"v5.12.3"`` / ``"5.7.0-beta.1"`` → ``(5, 12, 3)``；认不出返回 ``None``。"""
    if not text:
        return None
    head = str(text).strip().lstrip("vV").split("-", 1)[0].split("+", 1)[0]
    parts = head.split(".")
    try:
        numbers = tuple(int(part) for part in parts[:3])
    except ValueError:
        return None
    return numbers + (0,) * (3 - len(numbers)) if numbers else None


def avd_extras_supported(version: str | None) -> bool | None:
    """运行环境的 MaaFramework 带不带 AVDExtras；版本认不出返回 ``None``。"""
    parsed = parse_version(version)
    if parsed is None:
        return None
    return parsed >= AVD_EXTRAS_MIN_MAAFW_VERSION


__all__ = [
    "AVD_EXTRAS_MIN_MAAFW_VERSION",
    "avd_extras_supported",
    "build_maafw_avd_config",
    "parse_version",
]
