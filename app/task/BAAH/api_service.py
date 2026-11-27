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
"""BAAH 原生配置查询与推荐模板生成。"""

import json
import uuid
from collections.abc import Callable
from pathlib import Path

from app.config import ConfigEntry
from app.models.config import BAAHConfig
from app.utils.common.update_files import directory_lock

from .tools import CONFIG_DIR_NAME, list_config_names, read_json


class BAAHConfigService:
    """持有 BAAH 安装布局与配置名称查询策略。"""

    def __init__(
        self,
        *,
        get_script: Callable[[uuid.UUID], ConfigEntry],
        template_path: Path,
    ) -> None:
        self._get_script = get_script
        self._template_path = template_path

    def get_config_names(self, script_id: str) -> list[str]:
        """读取安装目录下已有的配置文件名，不含 .json 后缀。"""
        script_config = self._get_script(uuid.UUID(script_id))
        if not isinstance(script_config, BAAHConfig):
            raise TypeError("托管配置类型错误, 不是 BAAH 类型")

        baah_path = script_config.Script.BAAHPath
        if baah_path is None:
            return []
        return list_config_names(baah_path.parent / CONFIG_DIR_NAME)

    async def create_recommended_config(self, script_id: str) -> str:
        """从随包原生模板新建配置，独占创建以保留所有已有文件。"""
        script_config = self._get_script(uuid.UUID(script_id))
        if not isinstance(script_config, BAAHConfig):
            raise TypeError("托管配置类型错误, 不是 BAAH 类型")
        if script_config.is_locked:
            raise RuntimeError("托管正在运行，请停止后再生成配置")
        baah_path = script_config.Script.BAAHPath
        if baah_path is None or not baah_path.is_file():
            raise ValueError("请先设置有效的 BAAH 主程序路径")

        lock = directory_lock(baah_path.parent.resolve())
        if lock.locked():
            raise RuntimeError("BAAH 目录正在使用，请等待任务结束后重试")
        async with lock:
            template = read_json(self._template_path)
            if not template:
                raise RuntimeError("推荐配置模板缺失或为空，请修复 MAS 安装")
            payload = json.dumps(template, ensure_ascii=False, indent=4) + "\n"
            config_dir = baah_path.parent / CONFIG_DIR_NAME
            config_dir.mkdir(exist_ok=True)
            index = 1
            while True:
                name = "推荐配置" if index == 1 else f"推荐配置_{index}"
                path = config_dir / f"{name}.json"
                try:
                    handle = path.open("x", encoding="utf-8", newline="\n")
                except FileExistsError:
                    index += 1
                    continue
                try:
                    with handle:
                        handle.write(payload)
                except BaseException:
                    path.unlink(missing_ok=True)
                    raise
                return name
