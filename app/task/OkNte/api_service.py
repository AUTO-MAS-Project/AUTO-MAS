#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2024-2025 DLmaster361
#   Copyright © 2025 MoeSnowyFox
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
"""OK-NTE 快速配置目录、字段枚举与文件保存业务。"""

import uuid
from pathlib import Path
from typing import Any

from app.core import Config
from app.models.config import OkNteConfig as RuntimeOkNteConfig
from app.utils import get_logger

logger = get_logger("脚本管理 API")


def _oknte_script_config(script_id: str) -> tuple[uuid.UUID, RuntimeOkNteConfig]:
    script_uid = uuid.UUID(script_id)
    script_config = Config.ScriptConfig[script_uid]
    if not isinstance(script_config, RuntimeOkNteConfig):
        raise ValueError("脚本配置类型错误, 不是 OK-NTE 类型")
    return script_uid, script_config


def _oknte_mas_config_dir(script_id: str, user_id: str) -> Path:
    from app.task.OkNte.tools.backup_archive import ensure_quick_config_dir

    script_uid, script_config = _oknte_script_config(script_id)
    user_uid = uuid.UUID(user_id)
    if user_uid not in script_config.UserData:
        raise ValueError("OK-NTE 用户不存在，请刷新后重试")
    if script_config.is_locked:
        raise ValueError("OK-NTE 正在运行，请结束任务后编辑")
    return ensure_quick_config_dir(str(script_uid), str(user_uid), script_config)


def _oknte_config_file_path(config_dir: Path, filename: str) -> Path:
    file_path = Path(filename)
    if file_path.name != filename or file_path.is_absolute() or ".." in file_path.parts:
        raise ValueError("配置文件名非法")
    return config_dir / filename


def list_configs(
    script_id: str, user_id: str
) -> tuple[list[dict[str, Any]], dict[str, Any], Path]:
    import json

    from app.task.OkNte.config_schema import (
        build_fields_for_config,
        get_all_config_info,
        load_oknte_option_labels,
    )

    _, script_config = _oknte_script_config(script_id)

    # 从 ok-nte 安装目录加载翻译 → option_labels
    root_path = script_config.Info.RootPath
    option_labels = load_oknte_option_labels(root_path) if root_path else {}

    # 面板与来源分别保存；切换来源不重置面板。
    mas_config_dir = _oknte_mas_config_dir(script_id, user_id)

    configs_info = get_all_config_info()
    if script_config.Script.ConfigPathMode == "File":
        config_path = script_config.Script.ConfigPath
        if config_path is None:
            raise ValueError("ConfigPath未配置，请检查路径设置")
        filename = config_path.name
        configs_info = [info for info in configs_info if info["filename"] == filename]

    # 读取 per-user JSON 配置，通过 build_fields_for_config 构建字段列表
    result = []
    for info in configs_info:
        filename = info["filename"]
        filepath = _oknte_config_file_path(mas_config_dir, filename)
        current_data: dict[str, Any] = {}
        parse_error = False
        if filepath.exists():
            try:
                current_data = json.loads(filepath.read_text(encoding="utf-8"))
            except Exception as e:
                # 解析失败按空数据构建字段, 但要让前端知道这份配置没读出来
                parse_error = True
                logger.warning(
                    f"OkNte 配置解析失败: {filepath}: {type(e).__name__}: {e}"
                )

        fields = build_fields_for_config(filename, current_data, option_labels)

        result.append(
            {
                **info,
                "fields": fields,
                "currentData": current_data,
                "parseError": parse_error,
            }
        )

    return result, option_labels, mas_config_dir


def save_configs(script_id: str, user_id: str, *, configs: dict) -> list[str]:
    from app.task.OkNte.config_schema import update_oknte_config_data

    # 写入用户配置目录
    mas_config_dir = _oknte_mas_config_dir(script_id, user_id)
    mas_config_dir.mkdir(parents=True, exist_ok=True)
    _, script_config = _oknte_script_config(script_id)
    if script_config.Script.ConfigPathMode == "File":
        config_path = script_config.Script.ConfigPath
        if config_path is None:
            raise ValueError("ConfigPath未配置，请检查路径设置")
        filename = config_path.name
        if set(configs) - {filename}:
            raise ValueError("单文件模式只能编辑所选配置文件")

    updated_files = []
    for filename, data in configs.items():
        filepath = _oknte_config_file_path(mas_config_dir, filename)
        update_oknte_config_data(filepath, data)
        updated_files.append(filename)

    return updated_files
