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

"""BetterGI 启动前的原神客户端更新。

原神客户端由 BetterGI 自己启停，MAS 这边只知道用户选的「原神游戏程序」：所以更新
插在切号与启动 BetterGI 之前（切号也会拉起游戏），且不去读 BetterGI 自己的配置文件。

本文件只做「读配置 -> 判定区服与目录 -> 推调度台」这一段；查版本、下载、校验与落盘
都在 :mod:`app.services.genshin_updater`。**更新过程的所有叙述都由门面写进 app.log**，
这里只把影响本轮任务命运的少数几行推到调度台，免得刷掉专项自己的任务日志。
"""

from __future__ import annotations

from pathlib import Path

from app.models.config import BetterGIConfig
from app.services.genshin_updater import detect_genshin_region, update_genshin_client
from app.task.proxy_helpers import push_dispatch_log
from app.utils import get_logger

logger = get_logger("原神更新 BetterGI")


async def handle_genshin_game_update(
    script_config: BetterGIConfig,
    script_info: object,
) -> bool:
    """按配置接管原神客户端更新。

    Args:
        script_config: 当前脚本配置。
        script_info: 调度台条目，进度靠给它追加日志推送。

    Returns:
        是否可以继续本次任务；``False`` 表示更新失败，需要用户先看一眼。
    """
    if not script_config.get("Game", "IfAutoUpdate"):
        # 开关没开是常态，什么都不写：否则每次无关任务都要刷一行
        return True

    game_exe = str(script_config.get("Game", "UpdateExe") or "").strip()
    region = detect_genshin_region(game_exe)
    if not region:
        # 只影响这个功能本身、不改变任务命运：留 app.log 一行可诊断即可
        logger.warning(
            "原神更新已开启，但「原神游戏程序」不是 YuanShen.exe / GenshinImpact.exe"
            "（{}），本轮跳过",
            game_exe or "未选",
        )
        return True

    async def report(line: str) -> None:
        """只进调度台：更新过程的日志由门面统一写 app.log，这里不再复述。"""
        await push_dispatch_log(script_info, line)

    result = await update_genshin_client(
        str(Path(game_exe).parent),
        resource="官服" if region == "cn" else "国际服",
        time_limit_min=int(script_config.get("Game", "UpdateTimeLimit")),
        on_progress=report,
    )

    if result.success:
        if not result.noop:
            # 真的更新了才值得占用任务日志；「已是最新」只留在 app.log
            await report(
                f"原神客户端更新完成 {result.local_version or '?'} -> "
                f"{result.remote_version or '?'}"
            )
        return True

    await report(f"原神客户端更新未完成：{result.message}")
    return False
