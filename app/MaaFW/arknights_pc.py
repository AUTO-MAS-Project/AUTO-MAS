#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2026 AUTO-MAS Team

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


"""明日方舟 PC 工具的按需加载。

导入 ``app.MaaFW.ArknightWin32`` 会顺带构造 ``MaaFWManager``（同步加载 MaaFW 资源包）
和一个 ``Tasker``，把 MaaFramework 原生库整套载入；新装环境首次导入可达数十秒。
工具默认不启用，所以只在启用时才导入：启动期没启用就不碰，之后用户打开开关再加载。
本模块自身不依赖 Win32 / maa，可以随处导入。
"""

import asyncio
import importlib
import time
from typing import TYPE_CHECKING

from app.core import Config
from app.core.ws import Publisher, protocol
from app.models.schema import WSTaskNoticeData
from app.utils import get_logger

if TYPE_CHECKING:
    from app.MaaFW.ArknightWin32 import _ArknightWin32Toolkit

logger = get_logger("明日方舟PC工具")

# 加载失败后，定时巡检至少隔这么久才再试：失败多半是环境问题，每秒重试只会每秒刷一遍堆栈。
# 启动和用户打开开关不受这个间隔限制。
LOAD_RETRY_SECONDS = 60.0

_toolkit: "_ArknightWin32Toolkit | None" = None
_loading: asyncio.Task[None] | None = None
_bound = False
_retry_at = 0.0


def loaded_toolkit() -> "_ArknightWin32Toolkit | None":
    """已加载的工具实例，未加载时返回 None（不触发加载）"""

    return _toolkit


async def _load(notify: bool) -> None:
    global _toolkit, _retry_at

    try:
        # 导入很重且是同步的，放到线程里，不卡事件循环
        module = await asyncio.to_thread(
            importlib.import_module, "app.MaaFW.ArknightWin32"
        )
        toolkit = module.ArknightWin32Toolkit
        await toolkit.init()
    except Exception as e:
        _retry_at = time.monotonic() + LOAD_RETRY_SECONDS
        logger.exception(f"明日方舟 PC 工具加载失败: {e}")
        # 启动期不再等加载，失败进不了后台初始化告警；启动和打开开关时各提示一次，
        # 定时巡检的重试只记日志
        if notify:
            await Publisher.send(
                id=protocol.ID_ARKNIGHTS_PC_TOOLKIT,
                type=protocol.TOOLKIT_NOTICE,
                data=WSTaskNoticeData(
                    level="error", message=f"明日方舟 PC 工具加载失败: {e}"
                ),
            )
        return
    _toolkit = toolkit


def ensure_loading(force: bool = False) -> asyncio.Task[None] | None:
    """未加载时在后台发起加载，返回加载任务（正在加载则复用同一个）。

    已加载，或上次失败后仍在重试间隔内（``force`` 为假时）返回 None。
    ``force`` 同时表示失败时要向前端提示。
    """

    global _loading

    if _toolkit is not None:
        return None
    if _loading is not None and not _loading.done():
        return _loading
    if not force and time.monotonic() < _retry_at:
        return None
    _loading = asyncio.create_task(_load(notify=force))
    return _loading


async def _on_enabled_change(enabled: bool) -> None:
    if _toolkit is not None:
        await _toolkit.on_enabled_change(enabled)
    elif enabled:
        # 首次启用：init 会按当前开关值走一遍 on_enabled_change
        ensure_loading(force=True)


async def start() -> None:
    """启动期调用：接管启用开关，已启用时在后台发起加载，不等它完成"""

    global _bound

    if not _bound:
        Config.ToolsConfig.bind("ArknightsPC", "Enabled", _on_enabled_change)
        _bound = True
    if Config.ToolsConfig.get("ArknightsPC", "Enabled"):
        # 不等：后台初始化要等所有步骤走完才报 ready，已启用的用户换了新环境，
        # 首次导入一样会拖过监督器的健康预算
        ensure_loading(force=True)
