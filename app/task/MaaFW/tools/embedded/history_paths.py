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

"""MaaFW 每次尝试的 history 日志路径。

history 文件名带脚本名前缀（``history/<日期>/<用户>/<脚本名>-<HH-MM-SS>.log``），与走
``Config.build_history_log_path`` 的专项同一口径：历史侧栏只从文件名解析托管名，没有前缀就
只能归到「未标注托管」。``script_name`` 省略时退回无前缀的旧写法，老记录照常可读。
``runner_task`` 落盘和调度层按日志记录反推历史文件（失败回放的历史关联）都从这里取，
两边不能各拼一份。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from app.utils.constants import UTC4


def maafw_history_log_path(
    user_name: str, started_at: datetime, script_name: str = ""
) -> Path:
    """返回一次尝试的 ``.log`` 路径；同名 ``.json`` 是它的统计文件。

    ``script_name`` 非空时按 ``Config.build_history_log_path`` 的同一口径（非法字符换成
    ``_``、去掉首尾空格与点）加前缀，历史侧栏才能解析出托管名。
    """

    dt = started_at.astimezone(UTC4)
    time_stamp = dt.strftime("%H-%M-%S")
    safe_script_name = re.sub(r'[<>:"/\\|?*]', "_", str(script_name or "").strip())
    safe_script_name = safe_script_name.rstrip(" .")[: 255 - len(f"-{time_stamp}.log")]
    file_name = f"{safe_script_name}-{time_stamp}" if safe_script_name else time_stamp
    return Path.cwd() / f"history/{dt.strftime('%Y-%m-%d')}/{user_name}/{file_name}.log"
