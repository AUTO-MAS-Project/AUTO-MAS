#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file is part of AUTO-MAS.

#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.

#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
#   Affero General Public License for more details.

#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""原神客户端更新的原神门面。

编排在 :mod:`app.services.gi_updater.pipeline`——挪出事件循环、把进度转成调度台日志、
混装目录 / 只应用增量包 / 磁盘余量三道门禁都在那里，与具体游戏无关。本模块只做一件事：
把原神的短名钉进入口，并沿用宿主既有的函数名与结论类型。
"""

from __future__ import annotations

from pathlib import Path

from app.services.gi_updater.common import AbortHook
from app.services.gi_updater.install import UpdateKind
from app.services.gi_updater.pipeline import ProgressHook, UpdateResult, update_client
from app.services.gi_updater.presets import GameKey

__all__ = [
    "GenshinUpdateResult",
    "UpdateKind",
    "update_genshin_client",
]

#: 一轮原神客户端更新的结论——类型与名字沿用宿主既有调用方
GenshinUpdateResult = UpdateResult


async def update_genshin_client(
    game_path: str | Path,
    *,
    resource: str = "自动",
    on_progress: ProgressHook | None = None,
    should_abort: AbortHook | None = None,
) -> GenshinUpdateResult:
    """检查并按需更新原神客户端，直到落盘完成。

    Args:
        should_abort: 中止判定，在文件批次边界轮询；``None`` 表示不可中止。

    Returns:
        :class:`GenshinUpdateResult`。任何异常都转成 ``success=False`` 的结论，
        不把 traceback 抛给调度侧。
    """
    return await update_client(
        GameKey.Genshin,
        game_path,
        resource=resource,
        on_progress=on_progress,
        should_abort=should_abort,
    )
