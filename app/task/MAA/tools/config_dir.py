#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, either version 3 of the
#   License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""MAA 用户配置目录导入：MAA 安装目录的原生配置 → MAS 用户配置目录。

导入目标与备份模块共用 :func:`~app.task.MAA.tools.backup_archive.mas_config_dir`
布局（``data/{script_id}/{owner}/ConfigFile``），owner 由 ``Info.Base`` 三态决定
（shared = 共享 Default 目录、independent = 当前用户目录、native 不建 MAS 平行
全量配置，由调用方拦截）；上游来源是 MAA 安装目录 ``Info.Path`` 下的 ``config``。

导入会**整体替换**目标目录：先拷到同父目录的临时目录，再删旧目录并改名落地，
拷贝失败时用户的 MAS 配置保持原样（与 OK-WW 同目录的 ``ensure_user_config_dir``
同一手法）。替换前必须走 ``force_rmtree``——目录里可能有只读文件（如脚本自带
的 .git 对象），静默残留会让随后的改名落地抛 PermissionError。
"""

import shutil
import uuid
from pathlib import Path
from typing import Optional

from app.core import Config
from app.models.config import MaaConfig
from app.utils import get_logger
from app.utils.io import force_rmtree

from .backup_archive import mas_config_dir

logger = get_logger("MAA 配置目录")

_MAA_REL_CONFIG_DIR = "config"
"""MAA 安装目录下的原生配置目录（与 ``Info.Path`` 拼成原生配置根）。"""

_MAA_CONFIG_FILES = ("gui.json", "gui.new.json")
"""MAA 原生配置核心文件（与备份模块同一组，用于判断脚本目录是否已有可用配置）。"""


async def import_script_config_dir(script_id: str, user_id: Optional[str]) -> Path:
    """从 MAA 脚本目录导入当前配置，覆盖 MAS 用户配置目录。

    Args:
        script_id: MAA 脚本 ID。
        user_id: 目标用户 ID；``None`` 表示共享来源（写入 Default 目录）。

    Returns:
        被覆盖写入的 MAS 用户配置目录。

    Raises:
        TypeError: 脚本不是 MAA 类型。
        FileNotFoundError: MAA 安装目录下没有可用配置。
    """

    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(script_config, MaaConfig):
        raise TypeError(f"脚本配置类型错误: {script_id} 不是 MAA 类型")

    source_config_dir = Path(script_config.get("Info", "Path")) / _MAA_REL_CONFIG_DIR
    if not any((source_config_dir / name).exists() for name in _MAA_CONFIG_FILES):
        raise FileNotFoundError(
            "MAA 配置文件不存在, 请检查 MAA 路径设置或先启动 MAA 完成配置文件生成"
        )

    target_config_dir = mas_config_dir(script_id, user_id or "Default")
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

    logger.info(f"{script_id} - {user_id or 'Default'} 已从 MAA 目录导入配置文件")
    return target_config_dir
