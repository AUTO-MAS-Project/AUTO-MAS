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


import re
from pathlib import Path

from app.utils import decode_bytes


def poor_yaml_read(file: Path) -> dict:
    """
    Poor implementation to load yaml without pyyaml dependency, but with re

    Args:
        file (Path): yaml file path

    Returns:
        dict:
    """
    content = decode_bytes(file.read_bytes())
    data = {}
    regex = re.compile(r"^(.*?):(.*?)$")
    for line in content.splitlines():
        line = line.strip("\n\r\t ").replace("\\", "/")
        if line.startswith("#"):
            continue
        result = re.match(regex, line)
        if result:
            k, v = result.group(1), result.group(2).strip("\n\r\t' ")
            if v:
                if v.lower() == "null":
                    v = None
                elif v.lower() == "false":
                    v = False
                elif v.lower() == "true":
                    v = True
                elif v.isdigit():
                    v = int(v)
                data[k] = v

    return data


def poor_yaml_write(data: dict, file: Path, template_file: Path | None = None):
    """
    Args:
        data (dict):
        file (Path): yaml file path
        template_file (Path | None): template file path
    """
    if template_file is None:
        template_file = file
    text = decode_bytes(template_file.read_bytes())
    text = text.replace("\\", "/")

    for key, value in data.items():
        if value is None:
            value = "null"
        elif value is True:
            value = "true"
        elif value is False:
            value = "false"
        text = re.sub(f"{key}:.*?\n", f"{key}: {value}\n", text)

    file.write_text(text, encoding="utf-8")
