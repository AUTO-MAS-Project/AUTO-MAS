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

"""脚本复制、删除时的 MFW 视图与运行池策略。"""

import asyncio
from typing import cast

from app.config import ConfigEntry
from app.models.config import MaaFWConfig
from app.utils import get_logger
from app.utils import io as _utils_io

from .embedded_project import (
    FollowSourceCloneUnavailable,
    clone_embedded_copy,
    embedded_project_dir,
    is_source_form,
)
from .project_path import release_project_path, try_reserve_project_path

logger = get_logger("配置管理")


async def clone_script(source: ConfigEntry, target: ConfigEntry) -> None:
    """复制时物化源载荷；失败留待运行前重建，不影响已提交的脚本复制。

    开发者模式不随复制继承，目标挂源原渠道组的 latest。组里没有正式载荷，
    或源为源码形态时先不建视图，首次运行按来源目录导入；来源也不在时沿用
    缺视图的同来源兄弟 / 已登记版本重建路径。
    """
    source_config = cast(MaaFWConfig, source)
    target_config = cast(MaaFWConfig, target)
    await target_config.update(
        type(target_config).model_validate({"Embedded": {"FollowSource": False}}),
        check_visibility=False,
    )
    group_channel = str(source_config.Update.Channel or "stable")
    source_form = is_source_form(source_config)

    target_key = await try_reserve_project_path(embedded_project_dir(str(target.uid)))
    if target_key is None:
        return
    try:
        await asyncio.to_thread(
            lambda: clone_embedded_copy(
                source_script_id=str(source.uid),
                target_script_id=str(target.uid),
                group_channel=group_channel,
                source_form=source_form,
            )
        )
    except FollowSourceCloneUnavailable as exc:
        logger.info(f"复制脚本时先不建视图，第一次运行前按来源目录导入: {exc}")
    except Exception as exc:  # noqa: BLE001 - 失败下次运行会按来源 / 载荷重建
        logger.warning(f"复制脚本时建视图失败，将按需重建: {exc}")
    finally:
        await release_project_path(target_key)


def after_script_removal() -> None:
    """删除提交后启动运行池对账，不拖慢删除响应。"""
    from .pool_reconcile import reconcile_in_background

    reconcile_in_background("script-deleted")


async def cleanup_script_files(script_id: str) -> None:
    """通用数据目录清理后，再删除不在该目录下的 MFW 视图。"""
    # 视图不放在 data/<uid>/ 下，避免进入配置备份的整目录快照。
    embedded_copy = embedded_project_dir(script_id)
    if embedded_copy.exists():
        await asyncio.to_thread(_utils_io.force_rmtree, embedded_copy)
