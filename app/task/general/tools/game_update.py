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

"""通用脚本启动游戏前的原神客户端更新。

本文件只做「读配置 -> 判定区服与目录 -> 推调度台」这一段；查版本、下载、校验
与落盘都在 :mod:`app.services.genshin_updater`。**更新过程的所有叙述都由门面写进
app.log**，这里只把影响本轮任务命运的少数几行推到调度台。

通用脚本要服务很多没有专项适配的游戏，所以只在「游戏路径」填的确实是原神客户端
可执行文件时才接管更新，其余一律放行不处理。B服与官服共用 ``YuanShen.exe``
无法从文件名区分，不做技术识别，仅靠配置页提示 + 用户自觉。
"""

from __future__ import annotations

from pathlib import Path

from app.models.config import GeneralConfig
from app.services.genshin_updater import detect_genshin_region, update_genshin_client
from app.task.proxy_helpers import push_dispatch_log
from app.utils import get_logger

logger = get_logger("原神更新 通用脚本")


async def handle_genshin_game_update(
    script_config: GeneralConfig,
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
        # 开关没开是常态，什么都不写：否则每个无关脚本每次任务都要刷一行
        return True

    async def report(line: str) -> None:
        """只进调度台：更新过程的日志由门面统一写 app.log，这里不再复述。"""
        await push_dispatch_log(script_info, line)

    if str(script_config.get("Game", "Type") or "") != "Client":
        # 只有 PC 客户端模式才谈得上更新客户端；模拟器/URL 模式下不接管。
        # 这里可能是用户开着开关又切了启动方式，属于常态，不写日志
        return True

    game_path = str(script_config.get("Game", "Path") or "").strip()
    region = detect_genshin_region(game_path)
    if not region:
        # 开关开着但路径不是原神客户端：留 app.log 一行说明为什么没动，
        # 不刷调度台——它不改变本轮任务的命运
        logger.warning(
            "原神更新已开启，但「游戏路径」不是 YuanShen.exe / GenshinImpact.exe"
            "（{}），本轮跳过",
            game_path or "未填",
        )
        return True

    # 「游戏路径」在客户端模式下就是游戏可执行文件，原神把 ``config.ini``
    # 放在同一级，所以安装目录取它的上级
    game_dir = str(Path(game_path).parent)
    result = await update_genshin_client(
        game_dir,
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
