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


import re
import time

from app.utils.platform.common.process_runner import (
    decode_bytes,  # noqa: F401  # 兼容 re-export：io.py/LogMonitor.py 经 .tools 导入
)


def busy_wait(ms: float) -> None:
    """
    高精度忙等待, 高 CPU 占用, 目标精度 ±0.1ms

    Args:
        ms(float): 毫秒数
    """

    end = time.perf_counter() + ms / 1000.0
    while time.perf_counter() < end:
        pass


_PRE_RELEASE_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc)\.(\d+))?$")
_PRE_RELEASE_ABBR = {"alpha": "a", "beta": "b", "rc": "rc"}


def to_pep440(version: str) -> str:
    """把 ``vX.Y.Z[-phase.N]`` 版本号转成 PEP 440 写法。

    ``v5.5.0-beta.3`` → ``5.5.0b3``；正式版 ``v5.4.0`` → ``5.4.0``。
    """
    matched = _PRE_RELEASE_RE.match(version)
    if matched is None:
        raise ValueError(f"版本号 {version} 无法转换成 PEP 440 写法")
    major, minor, patch, phase, ordinal = matched.groups()
    base = f"{major}.{minor}.{patch}"
    if phase is None:
        return base
    return f"{base}{_PRE_RELEASE_ABBR[phase]}{ordinal}"
