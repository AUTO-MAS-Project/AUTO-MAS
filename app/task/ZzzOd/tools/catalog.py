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

内置应用和 ``plugins/*`` 的声明合并到同一目录。第三方声明单独容错，
只读取常量、不执行代码，供前端「一条龙任务配置」展示可选任务。
"""

import ast
import re
from pathlib import Path

from app.utils import get_logger

logger = get_logger("绝区零一条龙目录")
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


def list_app_catalog(root: Path, *, include_plugins: bool = True) -> list[dict]:
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
    # 插件是可选扩展：单个目录损坏、更新中或权限异常不能影响内置目录。
    known = {item["app_id"] for item in apps}
    for info in _list_plugin_catalog(root) if include_plugins else []:
        if info["app_id"] in known:
            logger.warning(f"插件应用 ID 重复，保留先注册的应用：{info['app_id']}")
            continue
        known.add(info["app_id"])
        apps.append(info)
    apps.sort(key=lambda item: (item["priority"], item["app_id"]))
    return apps


def _list_plugin_catalog(root: Path) -> list[dict]:
    """只读插件根第一层的声明，不导入或执行第三方代码。"""
    plugin_root = root / "plugins"
    try:
        if not plugin_root.exists():
            return []
        directories = sorted(plugin_root.iterdir())
    except OSError as exc:
        logger.warning(f"插件目录读取失败，继续使用内置任务：{plugin_root}: {exc}")
        return []
    apps: list[dict] = []
    for directory in directories:
        try:
            if directory.is_symlink() or not directory.is_dir():
                continue
            factories = list(directory.glob("*_factory.py"))
            constants = list(directory.glob("*_const.py"))
            if len(factories) != 1 or len(constants) != 1:
                raise ValueError("插件根必须各有一个 factory 和 const 文件")
            if factories[0].is_symlink() or constants[0].is_symlink():
                raise ValueError("插件声明文件不能是符号链接")
            declarations: dict = {}
            tree = ast.parse(constants[0].read_text(encoding="utf-8-sig"))
            for node in tree.body:
                if isinstance(node, ast.Assign) and len(node.targets) == 1:
                    target, value = node.targets[0], node.value
                elif isinstance(node, ast.AnnAssign) and node.value is not None:
                    target, value = node.target, node.value
                else:
                    continue
                if isinstance(target, ast.Name) and target.id in {
                    "APP_ID",
                    "APP_NAME",
                    "DEFAULT_GROUP",
                    "INTERNAL_APP",
                    "PRIORITY",
                }:
                    declarations[target.id] = ast.literal_eval(value)
            app_id = declarations.get("APP_ID")
            name = declarations.get("APP_NAME")
            default = declarations.get("DEFAULT_GROUP")
            internal = declarations.get("INTERNAL_APP", False)
            priority = declarations.get("PRIORITY")
            if priority is None:
                priority = 9999
            if (
                not isinstance(app_id, str)
                or not app_id.strip()
                or not isinstance(name, str)
                or not name.strip()
                or app_id != app_id.strip()
                or any(c in app_id for c in "/\\")
                or app_id in {".", ".."}
            ):
                raise ValueError("应用 ID 和名称必须是非空文本")
            if type(default) is not bool or type(internal) is not bool:
                raise ValueError("插件入口声明必须是布尔值")
            if type(priority) is not int or (default and internal):
                raise ValueError("插件排序或入口声明无效")
            if app_id in _EXCLUDED_APP_IDS:
                raise ValueError("插件不能覆盖一条龙入口")
            apps.append(
                {
                    "app_id": app_id,
                    "app_name": name,
                    "default_group": default,
                    "priority": priority,
                    "is_plugin": True,
                }
            )
        except Exception as exc:
            logger.warning(
                f"插件声明读取失败，跳过该插件并继续内置任务：{directory}: {exc}"
            )
    return apps
