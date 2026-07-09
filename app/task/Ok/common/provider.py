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

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_VERSION_SUFFIX_RE = re.compile(r"[-_ ]?v?\d+(?:\.\d+)+(?:[-_.a-z0-9]*)?$", re.I)
_PYAPPIFY_NAME_RE = re.compile(r"^\s*name\s*:\s*[\"']?([^\"'\r\n#]+)[\"']?", re.M)


@dataclass(frozen=True)
class OkScriptProvider:
    """ok-script 项目差异描述。

    这里只放可由具体项目决定的路径、进程和日志判态，不承载 MAS 的运行流程。
    """

    resource_name: str
    display_name: str
    exe_name: str
    config_dir: str
    log_file: str
    pythonw_path: str
    track_process_name: str
    game_process_name: str
    running_status: str
    fatal_patterns: tuple[tuple[str, str], ...]
    success_patterns: tuple[str, ...]
    max_task_index: int
    log_time_start: int = 1
    log_time_end: int = 23
    log_time_format: str = "%Y-%m-%d %H:%M:%S,%f"

    @property
    def log_time_range(self) -> tuple[int, int]:
        return (self.log_time_start - 1, self.log_time_end)

    @property
    def app_json_file(self) -> str:
        return f"data/apps/{self.resource_name}/app.json"

    def app_json_path(self, root_path: Path) -> Path:
        return root_path / self.app_json_file

    def exe_path(self, root_path: Path) -> Path:
        return root_path / self.exe_name

    def config_path(self, root_path: Path) -> Path:
        return root_path / self.config_dir

    def log_path(self, root_path: Path) -> Path:
        return root_path / self.log_file

    def track_process_path(self, root_path: Path) -> Path:
        return root_path / self.pythonw_path

    def build_task_args(self, task_index: int) -> list[str]:
        return ["-t", str(task_index), "-e"]


def normalize_ok_script_resource_name(value: Any) -> str:
    """把 pyappify/app.json 中的资源名规整为 provider 可匹配的 key。"""

    text = str(value or "").strip().strip("\"'")
    if not text:
        return ""
    normalized = _VERSION_SUFFIX_RE.sub("", text).strip()
    return normalized or text


def read_pyappify_resource_name(root_path: Path) -> str:
    pyappify_path = root_path / "pyappify.yml"
    if not pyappify_path.is_file():
        return ""

    match = _PYAPPIFY_NAME_RE.search(pyappify_path.read_text(encoding="utf-8"))
    return normalize_ok_script_resource_name(match.group(1) if match else "")


def read_app_json_resource_name(app_json_path: Path) -> str:
    if not app_json_path.is_file():
        return ""

    data = json.loads(app_json_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return ""
    return normalize_ok_script_resource_name(data.get("name"))


def ok_script_mas_config_dir(script_id: str, user_id: str) -> Path:
    """返回 MAS 侧保存的 ok-script 用户配置目录。"""

    return Path.cwd() / "data" / script_id / user_id / "ConfigFile"
