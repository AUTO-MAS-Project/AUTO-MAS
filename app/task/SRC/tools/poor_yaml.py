#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team

#   This file incorporates work covered by the following copyright and
#   permission notice:
#
#       StarRailCopilot Copyright © 2023-2026 LmeSzinc
#       https://github.com/LmeSzinc/StarRailCopilot

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


from pathlib import Path
from typing import Any, cast

from ruamel.yaml import YAML


_YAML = YAML(typ="safe")
_YAML.default_flow_style = False


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    loaded: Any = cast(Any, _YAML).load(path.read_text(encoding="utf-8"))
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"YAML 根节点必须是字典: {path}")
    mapping = cast(dict[object, Any], loaded)
    return {str(key): value for key, value in mapping.items()}


def poor_yaml_read(file: Path) -> dict[str, Any]:
    """读取 YAML 文件并返回字典对象。"""

    return _load_yaml_mapping(file)


def poor_yaml_write(
    data: dict[str, Any], file: Path, template_file: Path | None = None
) -> None:
    """写入 YAML 文件；若提供模板则先加载模板并合并。"""

    merged: dict[str, Any] = {}
    if template_file is not None and template_file.exists():
        merged = _load_yaml_mapping(template_file)

    merged.update(data)

    file.parent.mkdir(parents=True, exist_ok=True)
    with file.open("w", encoding="utf-8") as output:
        cast(Any, _YAML).dump(merged, output)
