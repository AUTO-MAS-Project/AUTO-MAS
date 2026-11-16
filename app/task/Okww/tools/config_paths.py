"""OK-WW 配置来源与目录；配置操作不依赖任务执行器。"""

from pathlib import Path

from app.utils import constants as _utils_constants

from .backup_archive import mas_config_dir, owner_for_mode

_OKWW_REL_CONFIG_DIR = "data/apps/ok-ww/working/configs"


def _okww_config_base(raw: object) -> str:
    """读取 OK-WW 配置来源（base 三态），并兼容旧版字面量。"""
    return _utils_constants.normalize_base_source(raw) or _utils_constants.BASE_SHARED


def _okww_mas_config_dir(script_id: str, user_id: str, base: str) -> Path:
    base = _okww_config_base(base)
    owner = owner_for_mode(base, user_id)
    if owner is None:
        raise ValueError("原生来源不使用 MAS 全量配置目录")
    return mas_config_dir(script_id, owner)
