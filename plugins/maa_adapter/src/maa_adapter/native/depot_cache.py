#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
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


import shutil
from pathlib import Path

from auto_mas_core.host.core_notify_task_content import (
    prepare_screenshot_images as prepare_screenshot_images,
)
from auto_mas_core.host.core_notify_task_content import (
    screenshot_entries as screenshot_entries,
)
from auto_mas_core.host.utils import get_logger

from maa_adapter.native.runtime_config import _MAA_DEPOT_ARCHIVE_NAME

logger = get_logger("MAA")


def depot_cache_snapshot_dir(script_id: str) -> Path:
    """库存缓存存底目录（键级存底，覆盖 overlay 对该文件的覆写）。

    安装目录的 data/DepotData.json 不在原生配置整目录快照（config）范围内，
    overlay 覆写它是不可还原写入；不在整目录快照范围内的目标必须自带键级快照。
    目录存在即为「已存底」；目录里没有 DepotData.json 表示覆写前安装目录本来
    就没有该文件。

    Args:
        script_id: 脚本标识，决定 data/<script_id>/TempDepot 的归属。

    Returns:
        存底目录路径。
    """

    return Path.cwd() / f"data/{script_id}/TempDepot"


def snapshot_depot_cache(maa_root_path: Path, snapshot_dir: Path) -> bool:
    """覆写安装目录库存缓存前存底；已存底时保持第一次的现场。

    Args:
        maa_root_path: MAA 安装根目录，工作缓存在其 data/DepotData.json。
        snapshot_dir: 存底目录；已存在即视为已存底并直接放行。

    Returns:
        可以覆写时为 True；存底失败为 False（调用方不得覆写）。
    """

    if snapshot_dir.is_dir():
        return True
    live = maa_root_path / "data" / _MAA_DEPOT_ARCHIVE_NAME
    try:
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        if live.is_file():
            shutil.copy2(live, snapshot_dir / _MAA_DEPOT_ARCHIVE_NAME)
    except OSError:
        shutil.rmtree(snapshot_dir, ignore_errors=True)
        logger.opt(exception=True).warning(
            "MAA 库存缓存存底失败, 本轮不覆写安装目录缓存"
        )
        return False
    return True


def restore_depot_cache(maa_root_path: Path, snapshot_dir: Path) -> None:
    """按存底还原安装目录库存缓存（结束还原与崩溃恢复共用）。

    存底目录存在才算覆写过；还原失败保留存底，交给下一次 prepare 重试。

    Args:
        maa_root_path: MAA 安装根目录，工作缓存在其 data/DepotData.json。
        snapshot_dir: 存底目录；不存在表示没覆写过，直接放行。
    """

    if not snapshot_dir.is_dir():
        return
    live = maa_root_path / "data" / _MAA_DEPOT_ARCHIVE_NAME
    saved = snapshot_dir / _MAA_DEPOT_ARCHIVE_NAME
    try:
        if saved.is_file():
            live.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(saved, live)
        else:
            live.unlink(missing_ok=True)
    except OSError:
        logger.opt(exception=True).warning(
            f"MAA 库存缓存还原失败, 保留存底: {snapshot_dir}"
        )
        return
    shutil.rmtree(snapshot_dir, ignore_errors=True)
