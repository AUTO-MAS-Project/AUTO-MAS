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

"""游戏客户端更新共用的结果类型与版本比较。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.utils import get_logger

logger = get_logger("游戏更新")


@dataclass
class GameUpdateResult:
    """游戏更新检查与接管的结果"""

    status: Literal["Skipped", "UpToDate", "Updated", "NeedManualUpdate"]
    """``Skipped`` 未执行检查；``UpToDate`` 无需更新；``Updated`` 已由 MAS 完成更新；
    ``NeedManualUpdate`` 需要用户手动更新，本次不应继续代理"""
    message: str
    """面向用户的说明文本"""
    resource_version: str = ""
    """可选的服务端资源版本号；仅部分游戏提供（如明日方舟用于识别待下载的资源热更新），
    未提供时为空字符串"""


def _parse_version(version: str) -> tuple[int, ...]:
    """把形如 ``2.7.61`` 的版本号解析为可比较的整数元组，无法解析的段落按 0 处理。

    只比较主版本号：开头的 ``v`` / ``V`` 去掉，第一个 ``-`` / ``+`` 之后的构建后缀
    不参与比较（``3.9.0-112.0.1361`` 按 ``3.9.0`` 算）。否则后缀里的数字会被当成
    更低位的版本段，同一主版本、一边带构建号一边不带时就会误判成落后，触发一次
    白下的安装包。
    """

    core = re.split(r"[-+]", version.strip().lstrip("vV"), maxsplit=1)[0]
    parts: list[int] = []
    for segment in core.split("."):
        digits = re.match(r"\d+", segment.strip())
        parts.append(int(digits.group()) if digits else 0)
    return tuple(parts)


def is_client_outdated(installed: str, remote: str) -> bool:
    """判断已安装客户端是否落后于服务端版本。"""

    installed_parts = _parse_version(installed)
    remote_parts = _parse_version(remote)
    if not any(installed_parts) or not any(remote_parts):
        # 任一侧完全解析不出数字时不敢下判断，按未落后处理，交给上游原有流程
        logger.warning(f"版本号无法比较: 已安装 {installed}, 服务端 {remote}")
        return False
    length = max(len(installed_parts), len(remote_parts))
    installed_parts += (0,) * (length - len(installed_parts))
    remote_parts += (0,) * (length - len(remote_parts))
    return installed_parts < remote_parts
