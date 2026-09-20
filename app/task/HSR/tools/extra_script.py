#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See
#   the GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.
#
#   Contact: DLmaster_361@163.com


from pathlib import Path

from app.models.config import HSRUserConfig
from app.task.general.tools import execute_script_task


async def run_script_before_task(user_config: HSRUserConfig) -> None:
    """执行用户配置的任务前脚本，未开启时直接返回。

    HSR 的托管与直控两条路径都要用，所以抽成函数；其余专项在 AutoProxy 里
    内联同样的两行。

    Args:
        user_config (HSRUserConfig): 当前用户配置。
    """

    if not user_config.get("Info", "IfScriptBeforeTask"):
        return

    await execute_script_task(
        Path(user_config.get("Info", "ScriptBeforeTask")),
        "脚本前任务",
    )


async def run_script_after_task(user_config: HSRUserConfig) -> None:
    """执行用户配置的任务后脚本，未开启时直接返回。

    Args:
        user_config (HSRUserConfig): 当前用户配置。
    """

    if not user_config.get("Info", "IfScriptAfterTask"):
        return

    await execute_script_task(
        Path(user_config.get("Info", "ScriptAfterTask")),
        "脚本后任务",
    )
