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

"""ok-script 项目 provider 集合。"""

from pathlib import Path

from app.task.Ok.common.provider import (
    OkScriptProvider,
    normalize_ok_script_resource_name,
    read_app_json_resource_name,
    read_pyappify_resource_name,
)

from .okef import OKEF_PROVIDER
from .oknte import OKNTE_PROVIDER
from .okww import OKWW_PROVIDER


OK_SCRIPT_PROVIDERS: dict[str, OkScriptProvider] = {
    OKEF_PROVIDER.resource_name: OKEF_PROVIDER,
    OKWW_PROVIDER.resource_name: OKWW_PROVIDER,
    OKNTE_PROVIDER.resource_name: OKNTE_PROVIDER,
}


def get_ok_script_provider(resource_name: object) -> OkScriptProvider | None:
    """按 ok-script 资源名获取当前宿主内置 provider。"""

    normalized = normalize_ok_script_resource_name(resource_name)
    if not normalized:
        return None
    return OK_SCRIPT_PROVIDERS.get(normalized)


def detect_ok_script_provider(
    root_path: str | Path,
    resource_name: object = "",
) -> OkScriptProvider | None:
    """按已保存资源名或项目根目录识别 ok-script provider。"""

    root = Path(root_path)
    if not root.is_dir():
        return None

    # 根目录是当前运行的事实来源，避免切换项目目录后仍使用旧 ResourceName。
    pyappify_resource_name = read_pyappify_resource_name(root)
    if pyappify_resource_name:
        return get_ok_script_provider(pyappify_resource_name)

    for candidate in OK_SCRIPT_PROVIDERS.values():
        app_json_resource_name = read_app_json_resource_name(
            candidate.app_json_path(root)
        )
        if app_json_resource_name:
            return get_ok_script_provider(app_json_resource_name)

    for candidate in OK_SCRIPT_PROVIDERS.values():
        if candidate.exe_path(root).is_file() and candidate.config_path(root).is_dir():
            return candidate

    return get_ok_script_provider(resource_name)
