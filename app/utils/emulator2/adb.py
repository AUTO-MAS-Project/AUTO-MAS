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

"""雷电实例的 ADB 序列号解析：先按公式猜，再拿 ``adb devices`` 核。

**为什么不能只靠公式。** 雷电的序列号约定是 ``emulator-{5554 + 2 × 原生索引}``，
这条规律实测成立（连故意占住 5562/5563 再启动都没有位移），``ldconsole`` 自己
执行 adb 命令时用的也是它。但它是**按索引推出来的，不是问出来的**：

- 同一条 Emulator 2.0 配置纳管**两条雷电安装**时，两边的 0 号都推出 ``emulator-5554``，
  现实里不可能两个都占住，必然有一个是错的
- 端口真被别的程序占走时，我们无从知道

**为什么旧的查询没用。** 旧实现是 ``get_adb_ports(vbox_pid)``，用 psutil 看 vbox 进程
监听了哪个端口。实测雷电 14 的 ``Ld9BoxHeadless.exe`` **一个端口都不监听**（端口由所有
实例共用的 ``VBoxNetNAT`` 持有），所以它永远返回 0、永远回落公式——那段查询在雷电 14 上
是死代码。

所以这里改成拿 ``adb devices`` 的真实结果去核对：**能核上就用核过的，核不上也不硬猜**。
"""

import re
from dataclasses import dataclass
from typing import Literal

#: 解析结果的来历。界面和日志要能区分「核过的」和「只是按公式推的」。
SerialSource = Literal["verified", "recovered", "formula"]

#: ``adb devices`` 的行：``emulator-5562\tdevice``。
#: 只收 ``device`` 状态——``offline`` / ``unauthorized`` 的连不上，认了也没用。
_DEVICE_LINE = re.compile(r"^(\S+)\s+device\s*$")


def candidate_serial(native_index: str | int) -> str:
    """按雷电的约定推一个候选序列号。"""
    return f"emulator-{5554 + int(native_index) * 2}"


def parse_adb_devices(output: str) -> list[str]:
    """从 ``adb devices`` 的输出里取出在线设备的序列号。"""
    serials: list[str] = []
    for line in (output or "").splitlines():
        line = line.strip()
        if not line or line.lower().startswith("list of devices"):
            continue
        match = _DEVICE_LINE.match(line)
        if match:
            serials.append(match.group(1))
    return serials


@dataclass(frozen=True)
class SerialResolution:
    serial: str
    source: SerialSource


def resolve_serial(
    native_index: str | int,
    serials: list[str],
    other_indexes: list[str] | None = None,
) -> SerialResolution:
    """解析某个原生索引对应的 ADB 序列号。

    三条路，优先级从高到低：

    1. **核对通过**：公式推出来的那个就在 ``adb devices`` 里 —— 绝大多数情况走这条
    2. **认领回来**：公式那个不在，但排掉其他实例各自的候选之后，正好只剩一个没人认领的
       设备 —— 那它只能是我们要找的。这条是为「两条安装撞号」和「端口被占走」准备的
    3. **只能按公式**：设备列表是空的（adb 没起来 / 实例没开完），或者剩下不止一个、
       无法确定是哪个 —— 这时**照样返回公式值，但标明没核过**，不去猜

    第 3 条里两种情况有意合并：调用方只需要知道「这个值没核过」，
    至于是没设备还是分不清，日志里说得清就够了。
    """
    candidate = candidate_serial(native_index)

    if candidate in serials:
        return SerialResolution(candidate, "verified")

    if not serials:
        return SerialResolution(candidate, "formula")

    # 其他实例各自的候选先排掉，剩下的才是可能属于我们的
    claimed = {candidate_serial(other) for other in (other_indexes or [])}
    unclaimed = [serial for serial in serials if serial not in claimed]

    if len(unclaimed) == 1:
        return SerialResolution(unclaimed[0], "recovered")

    return SerialResolution(candidate, "formula")
