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

MAS 用户配置目录的 owner 由 ``Info.Base`` 三态决定（shared=共享 Default、
independent=当前用户独立目录、native=不建 MAS 平行全量配置），统一经
:func:`~app.task.Okww.tools.backup_archive.owner_for_mode` 解析；上游默认
配置取自脚本共享目录内的 ok-ww 原生 working 配置。目录初始化原属
app/core/config.py，迁入本模块由 OK-WW 专项自己维护。
"""

import shutil
import uuid
from pathlib import Path
from typing import Optional

from app.core import Config
from app.models.config import OkwwConfig
from app.utils import get_logger
from app.utils.constants import BASE_INDEPENDENT, BASE_SHARED
from app.utils.io import force_rmtree, replace_dir

from ..AutoProxy import (
    _OKWW_REL_CONFIG_DIR,
    _okww_config_base,
    _okww_mas_config_dir,
)
from .backup_archive import (
    mas_config_dir,
    mas_rollback_point,
    read_overlay_values,
    restore_mas_backup,
)

logger = get_logger("OK-WW 配置目录")


async def ensure_user_config_dir(script_id: str, user_id: str, base: str) -> Path:
    """从 OK-WW 脚本当前配置初始化 MAS 用户配置目录。

    已存在配置文件时保留用户配置；仅当目标目录为空时复制脚本目录中的默认配置。
    shared 来源使用脚本共享目录，independent 来源使用当前用户独立目录。
    本函数只服务 shared/independent 来源的 MAS 目录初始化；native 来源不调用
    ——原生来源直接使用脚本原生配置，MAS 不建平行全量配置。

    Args:
        script_id: OK-WW 脚本 ID。
        user_id: OK-WW 用户 ID。
        base: base 来源（shared/independent/native 三态）；本函数只接受 shared /
            independent，旧字面量「简洁」/「详细」仅兼容存量数据，误传 native
            会抛 ValueError。

    Returns:
        MAS 用户配置目录路径。

    Raises:
        TypeError: 脚本不是 OK-WW 类型。
        ValueError: 配置来源非法或目标路径冲突。
        FileNotFoundError: OK-WW 默认配置目录不存在或为空。
    """

    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(script_config, OkwwConfig):
        raise TypeError(f"脚本配置类型错误: {script_id} 不是 OK-WW 类型")
    base = _okww_config_base(base)
    if base not in (BASE_SHARED, BASE_INDEPENDENT):
        raise ValueError(f"不支持的 OK-WW 配置来源: {base}")
    target_config_dir = _okww_mas_config_dir(script_id, user_id, base)
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


async def import_script_config_dir(script_id: str, user_id: Optional[str]) -> Path:
    """从 OK-WW 脚本目录导入当前配置，覆盖 MAS 用户配置目录。

    导入是显式覆盖：覆盖前先把现有 MAS 配置存底（进该用户的备份池，「配置
    恢复」里可手工找回），替换失败时按存底自动回滚并显式报错——导入失败
    不能只给用户留下一个空目录。

    Args:
        script_id: OK-WW 脚本 ID。
        user_id: 目标用户 ID；``None`` 表示共享来源（写入 Default 目录）。

    Returns:
        被覆盖写入的 MAS 用户配置目录。

    Raises:
        TypeError: 脚本不是 OK-WW 类型。
        FileNotFoundError: 脚本目录下没有可用的 OK-WW 配置。
        RuntimeError: 导入失败（已尝试回滚到导入前的配置）。
    """

    script_config = Config.ScriptConfig[uuid.UUID(script_id)]
    if not isinstance(script_config, OkwwConfig):
        raise TypeError(f"脚本配置类型错误: {script_id} 不是 OK-WW 类型")

    source_config_dir = (
        Path(script_config.get("Info", "RootPath")).expanduser() / _OKWW_REL_CONFIG_DIR
    )
    if not source_config_dir.is_dir() or not any(
        item.is_file() for item in source_config_dir.rglob("*")
    ):
        raise FileNotFoundError("未找到 OK-WW 默认设置，请先运行一次 OK-WW 并保存设置")

    owner = user_id or "Default"
    target_config_dir = mas_config_dir(script_id, owner)
    target_config_dir.parent.mkdir(parents=True, exist_ok=True)

    # 存底归桶：独立来源用户的存底进自己的池（「配置恢复」里能看到「导入前」
    # 这份）；共享来源没有请求用户，存底落在 Default 桶里，只作本次回滚点。
    overlay: Optional[dict] = None
    if user_id:
        uid = uuid.UUID(user_id)
        if uid in script_config.UserData:
            overlay = read_overlay_values(script_config.UserData[uid])
    rollback_ts = mas_rollback_point(script_id, owner, target_config_dir, overlay)

    try:
        replace_dir(source_config_dir, target_config_dir)
    except Exception as exc:
        if rollback_ts is None:
            raise RuntimeError(
                f"导入配置失败，且导入前没有可回滚的配置：{exc}"
            ) from exc
        try:
            restore_mas_backup(
                script_id, owner, rollback_ts, target_config_dir, overlay=overlay
            )
        except Exception as rollback_exc:
            logger.opt(exception=True).error(
                f"{script_id} - {owner} 导入失败后回滚失败: {rollback_exc}"
            )
            raise RuntimeError(
                f"导入配置失败，回滚也失败：{rollback_exc}（导入错误：{exc}）"
            ) from exc
        logger.opt(exception=True).error(
            f"{script_id} - {owner} 导入配置失败，已回滚到备份 {rollback_ts}"
        )
        raise RuntimeError(
            f"导入配置失败，已恢复到导入前的配置（备份 {rollback_ts}）：{exc}"
        ) from exc

    logger.info(f"{script_id} - {owner} 已从 OK-WW 目录导入配置文件")
    return target_config_dir
