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

"""OK-WW 用户配置目录初始化：上游脚本默认配置 → MAS 用户配置目录。

MAS 用户配置目录的 owner 由 ``Info.Mode`` 三态决定（脚本=共享 Default、
用户=当前用户独立目录、直控=不建 MAS 平行全量配置），统一经
:func:`~app.task.Okww.tools.backup_archive.owner_for_mode` 解析；上游默认
配置取自脚本共享目录内的 ok-ww 原生 working 配置。目录初始化原属
app/core/config.py，迁入本模块由 OK-WW 专项自己维护。
"""

import shutil
import uuid
from pathlib import Path

from app.core import Config
from app.models.config import OkwwConfig
from app.utils import get_logger
from app.utils.io import force_rmtree

from ..AutoProxy import (
    _OKWW_REL_CONFIG_DIR,
    _okww_config_mode,
    _okww_mas_config_dir,
)

logger = get_logger("OK-WW 配置目录")


async def ensure_user_config_dir(script_id: str, user_id: str, mode: str) -> Path:
    """从 OK-WW 脚本当前配置初始化 MAS 用户配置目录。

    已存在配置文件时保留用户配置；仅当目标目录为空时复制脚本目录中的默认配置。
    脚本来源使用脚本共享目录，用户来源使用当前用户独立目录。
    本函数只服务「脚本/用户」来源的 MAS 目录初始化；直控来源不调用——
    直控直接使用脚本原生配置，MAS 不建平行全量配置。

    Args:
        script_id: OK-WW 脚本 ID。
        user_id: OK-WW 用户 ID。
        mode: 配置来源（脚本/用户/直控三态）；本函数只接受“脚本”/“用户”，
            “简洁”/“详细”仅兼容旧配置，误传“直控”会抛 ValueError。

    Returns:
        MAS 用户配置目录路径。

    Raises:
        TypeError: 脚本不是 OK-WW 类型。
        ValueError: 配置模式非法或目标路径冲突。
        FileNotFoundError: OK-WW 默认配置目录不存在或为空。
    """

    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(script_config, OkwwConfig):
        raise TypeError(f"脚本配置类型错误: {script_id} 不是 OK-WW 类型")
    mode = _okww_config_mode(mode)
    if mode not in ("脚本", "用户"):
        raise ValueError(f"不支持的 OK-WW 配置模式: {mode}")
    target_config_dir = _okww_mas_config_dir(script_id, user_id, mode)
    if target_config_dir.exists() and not target_config_dir.is_dir():
        raise ValueError(f"OK-WW 用户配置路径不是目录: {target_config_dir}")
    if target_config_dir.is_dir() and any(
        item.is_file() for item in target_config_dir.rglob("*")
    ):
        return target_config_dir

    script_root = Path(script_config.get("Info", "RootPath")).expanduser()
    source_config_dir = script_root / _OKWW_REL_CONFIG_DIR
    if not source_config_dir.is_dir() or not any(
        item.is_file() for item in source_config_dir.rglob("*")
    ):
        raise FileNotFoundError("未找到 OK-WW 默认设置，请先运行一次 OK-WW 并保存设置")

    temporary_path = target_config_dir.with_name(
        f".{target_config_dir.name}.{uuid.uuid4().hex}.tmp"
    )
    try:
        shutil.copytree(source_config_dir, temporary_path)
        target_config_dir.parent.mkdir(parents=True, exist_ok=True)
        force_rmtree(target_config_dir)
        temporary_path.rename(target_config_dir)
    finally:
        force_rmtree(temporary_path)

    logger.info(
        f"已从 OK-WW 脚本默认配置初始化用户配置: {script_id} - {target_config_dir.parent.name}"
    )
    return target_config_dir
