#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License
#   as published by the Free Software Foundation, either version 3 of
#   the License, or (at your option) any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""一条龙应用目录静态解析。

zzz-od 的应用注册信息在 ``src/zzz_od/application/**/*_const.py`` 中以模块级常量
声明（``APP_ID`` / ``APP_NAME`` / ``DEFAULT_GROUP`` / ``PRIORITY``），无需运行
zzz-od 即可解析出完整目录，供前端「一条龙任务配置」展示可选任务。
"""

import re
from pathlib import Path

# 一条龙入口应用自身不能嵌套进任务列表，排除
_EXCLUDED_APP_IDS = frozenset({"one_dragon"})

_CONST_ASSIGN_RE = re.compile(
    r"^(APP_ID|APP_NAME|DEFAULT_GROUP|PRIORITY|NEED_NOTIFY)\s*=\s*['\"]([^'\"]*)['\"]",
    re.MULTILINE,
)
_BOOL_ASSIGN_RE = re.compile(
    r"^(DEFAULT_GROUP|NEED_NOTIFY)\s*=\s*(True|False)\b", re.MULTILINE
)
_INT_ASSIGN_RE = re.compile(r"^(PRIORITY)\s*=\s*(\d+)\b", re.MULTILINE)


def _parse_const_file(path: Path) -> dict | None:
    """解析单个 ``*_const.py``，返回应用信息；非应用 const（无 APP_ID）返回 None。"""

    text = path.read_text(encoding="utf-8")
    strings = dict(_CONST_ASSIGN_RE.findall(text))
    app_id = strings.get("APP_ID")
    if not app_id:
        return None
    bools = dict(_BOOL_ASSIGN_RE.findall(text))
    ints = dict(_INT_ASSIGN_RE.findall(text))
    return {
        "app_id": app_id,
        "app_name": strings.get("APP_NAME") or app_id,
        "default_group": bools.get("DEFAULT_GROUP") == "True",
        "priority": int(ints.get("PRIORITY", "9999")),
    }


def list_app_catalog(root: Path) -> list[dict]:
    """扫描应用 const 文件，返回按 PRIORITY 升序的应用目录。

    元素含 app_id / app_name（中文名）/ default_group（是否默认进一条龙）/
    priority（zzz-od 原生排序，缺省 9999 置底）。
    """

    app_dir = root / "src" / "zzz_od" / "application"
    if not app_dir.is_dir():
        raise ValueError(f"{root} 下未找到 src/zzz_od/application, 请确认安装目录")

    apps: list[dict] = []
    for path in sorted(app_dir.rglob("*_const.py")):
        info = _parse_const_file(path)
        if info is None or info["app_id"] in _EXCLUDED_APP_IDS:
            continue
        apps.append(info)
    apps.sort(key=lambda item: (item["priority"], item["app_id"]))
    return apps
