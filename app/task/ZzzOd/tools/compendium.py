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

"""一条龙副本字典与动态选项静态读取。

MAS 侧的动态选项（任务计划里的副本级联、配队方案、迷失之地图层与挑战配置）
全部可在不运行一条龙的情况下从安装目录静态获取，保证与一条龙原生 GUI 选项
动态一致（上游升级后无需改 MAS）：

- ``assets/game_data/compendium_data.yml`` — 副本字典（上游
  ``CompendiumService`` 的数据源）：「训练」tab 提供体力刷本 / 恶名狩猎的
  分类→类型→关卡级联，「作战→零号空洞→迷失之地」提供迷失之地图层
- ``config/auto_battle/`` — 配队方案模板（上游 ``get_auto_battle_op_config_list``
  同规则：剥离 .sample/.merged/.yml 后缀去重排序）
- ``config/lost_void_challenge/`` — 迷失之地挑战配置模板（上游
  ``get_all_lost_void_challenge_config`` 同规则，sample 也计入）
"""

import re
from pathlib import Path
from typing import Any

from app.utils.io import read_file

_COMPENDIUM_REL = Path("assets") / "game_data" / "compendium_data.yml"

# 解析结果缓存：每次选项请求都要读整份副本字典和整目录 yml，按文件签名
# （名称/mtime/大小）命中即复用上次解析结果；调用方只读不改
_SCAN_CACHE: dict[Path, tuple[tuple, Any]] = {}


def _file_signature(path: Path) -> tuple:
    try:
        stat = path.stat()
    except OSError:
        return (path.name, 0, 0)
    return (path.name, stat.st_mtime_ns, stat.st_size)


def _read_compendium(root: Path) -> list:
    """读取副本字典（签名未变时复用上次解析结果）。"""

    path = root / _COMPENDIUM_REL
    signature = (_file_signature(path),)
    cached = _SCAN_CACHE.get(path)
    if cached is not None and cached[0] == signature:
        return cached[1]
    data = read_file(path) or []
    _SCAN_CACHE[path] = (signature, data)
    return data


def _read_yml_dir(dir_path: Path) -> list[tuple[Path, Any]]:
    """读取目录下全部 *.yml（按名排序），目录签名未变时复用上次解析结果。"""

    if not dir_path.is_dir():
        return []
    paths = sorted(dir_path.glob("*.yml"))
    signature = tuple(_file_signature(path) for path in paths)
    cached = _SCAN_CACHE.get(dir_path)
    if cached is not None and cached[0] == signature:
        return cached[1]
    entries = [(path, read_file(path)) for path in paths]
    _SCAN_CACHE[dir_path] = (signature, entries)
    return entries


def _display(item: dict, name_key: str, display_key: str) -> str:
    """display 缺省时与上游一致回退到 name。"""

    return str(item.get(display_key) or item.get(name_key) or "")


def train_categories(root: Path) -> list[dict]:
    """「训练」tab 的副本级联树（体力刷本 / 恶名狩猎计划共用）。

    返回 ``[{name, label, mission_types: [{name, display, missions:
    [{name, display}]}]}]``；恶名狩猎分类与上游 CompendiumService 一致展示为
    「恶名狩猎 深度追猎」。
    """

    for tab in _read_compendium(root):
        if not isinstance(tab, dict) or tab.get("tab_name") != "训练":
            continue
        categories: list[dict] = []
        for cat in tab.get("category_list") or []:
            if not isinstance(cat, dict):
                continue
            mission_types = []
            for mt in cat.get("mission_type_list") or []:
                if not isinstance(mt, dict):
                    continue
                mission_types.append(
                    {
                        "name": str(mt.get("mission_type_name") or ""),
                        "display": _display(
                            mt, "mission_type_name", "mission_type_name_display"
                        ),
                        "missions": [
                            {
                                "name": str(m.get("mission_name") or ""),
                                "display": _display(
                                    m, "mission_name", "mission_name_display"
                                ),
                            }
                            for m in (mt.get("mission_list") or [])
                            if isinstance(m, dict)
                        ],
                    }
                )
            name = str(cat.get("category_name") or "")
            categories.append(
                {
                    "name": name,
                    "label": f"{name} 深度追猎" if name == "恶名狩猎" else name,
                    "mission_types": mission_types,
                }
            )
        return categories
    return []


def lost_void_missions(root: Path) -> list[str]:
    """迷失之地（作战→零号空洞→迷失之地）关卡展示名列表。"""

    for tab in _read_compendium(root):
        if not isinstance(tab, dict) or tab.get("tab_name") != "作战":
            continue
        for cat in tab.get("category_list") or []:
            if not isinstance(cat, dict) or cat.get("category_name") != "零号空洞":
                continue
            for mt in cat.get("mission_type_list") or []:
                if (
                    not isinstance(mt, dict)
                    or mt.get("mission_type_name") != "迷失之地"
                ):
                    continue
                return [
                    _display(m, "mission_name", "mission_name_display")
                    for m in (mt.get("mission_list") or [])
                    if isinstance(m, dict)
                ]
    return []


def hollow_zero_missions(root: Path) -> list[str]:
    """枯萎之都选图（作战→零号空洞，排除迷失之地；与上游
    ``get_hollow_zero_mission_name_list`` 同规则，取 mission_name）。"""

    names: list[str] = []
    for tab in _read_compendium(root):
        if not isinstance(tab, dict) or tab.get("tab_name") != "作战":
            continue
        for cat in tab.get("category_list") or []:
            if not isinstance(cat, dict) or cat.get("category_name") != "零号空洞":
                continue
            for mt in cat.get("mission_type_list") or []:
                if (
                    not isinstance(mt, dict)
                    or mt.get("mission_type_name") == "迷失之地"
                ):
                    continue
                names.extend(
                    str(m.get("mission_name") or "")
                    for m in (mt.get("mission_list") or [])
                    if isinstance(m, dict)
                )
    return [n for n in names if n]


def hollow_zero_challenge_options(root: Path) -> list[dict]:
    """枯萎之都挑战配置模板选项（config/hollow_zero_challenge，sample 计入，
    与上游 ``get_all_hollow_zero_challenge_config`` 同规则）。"""

    return _template_options(
        root / "config" / "hollow_zero_challenge",
        include_sample=True,
        include_merged=False,
    )


_COFFEE_REL = Path("assets") / "game_data" / "coffee_data.yml"


def _coffee_display(item: dict) -> str:
    """咖啡展示名（与上游 Coffee.display_name 同规则：类型 - 关卡回退名称）。"""

    type_name = str(item.get("mission_type_name") or "")
    mission_name = str(item.get("mission_name") or "")
    if not type_name:
        return str(item.get("coffee_name") or "")
    if not mission_name:
        return type_name
    return f"{type_name} - {mission_name}"


def coffee_options(root: Path, day: int) -> list[dict]:
    """指定星期几（1~7）可选的咖啡选项（assets/game_data/coffee_data.yml，
    与上游 ``get_coffee_config_list_by_day`` 同源同规则）。"""

    data = read_file(root / _COFFEE_REL) or {}
    if not isinstance(data, dict):
        return []
    all_coffee = {
        str(i.get("coffee_name")): _coffee_display(i)
        for i in data.get("coffee_list") or []
        if isinstance(i, dict) and i.get("coffee_name")
    }
    for schedule in data.get("schedule") or []:
        if not isinstance(schedule, dict):
            continue
        try:
            days = [int(d) for d in schedule.get("days") or []]
        except (TypeError, ValueError):
            continue
        if int(day) not in days:
            continue
        options = []
        for name in schedule.get("coffee_list") or []:
            name = str(name)
            if name in all_coffee:
                options.append({"label": all_coffee[name], "value": name})
        return options
    # 当日无排程：回退为全部咖啡
    return [{"label": display, "value": name} for name, display in all_coffee.items()]


def world_patrol_route_lists(root: Path) -> list[dict]:
    """锄大地路线名单选项（config/world_patrol_route_list/*.yml 的 name 字段，
    与上游 ``get_world_patrol_route_lists`` 同源；「全部」由静态选项前置）。"""

    names: list[str] = []
    for _path, data in _read_yml_dir(root / "config" / "world_patrol_route_list"):
        if isinstance(data, dict) and data.get("name"):
            names.append(str(data["name"]))
    return [{"label": n, "value": n} for n in names]


def agent_names(root: Path) -> list[dict]:
    """代理人名列表（assets/game_data/agent/*.yml 的 agent_name 字段，
    「随机」由字段静态选项前置）。"""

    names: list[str] = []
    for _path, data in _read_yml_dir(root / "assets" / "game_data" / "agent"):
        if isinstance(data, dict) and data.get("agent_name"):
            names.append(str(data["agent_name"]))
    return [{"label": n, "value": n} for n in names]


# 兼容单引号同行与双引号多行两种写法（老角色单行、新角色多行双引号）
_AGENT_ENUM_RE = re.compile(r"Agent\(\s*['\"]([\w]+)['\"],\s*['\"]([^'\"]+)['\"]")


def agent_id_options(root: Path) -> list[dict]:
    """预备编队成员选项（label=代理人名，value=agent_id，与上游 AgentEnum 对应）。

    全量名单来自上游源码 ``AgentEnum``（assets/game_data/agent 数据文件只覆盖
    部分角色，新角色缺失会让下拉显示原始 id）；源码缺失时回退数据文件扫描。
    「代理人」空位由调用方前置。
    """

    enum_path = root / "src" / "zzz_od" / "game_data" / "agent.py"
    if enum_path.is_file():
        options = [
            {"label": name, "value": agent_id}
            for agent_id, name in _AGENT_ENUM_RE.findall(
                enum_path.read_text(encoding="utf-8")
            )
        ]
        if options:
            return options

    options: list[dict] = []
    for path, data in _read_yml_dir(root / "assets" / "game_data" / "agent"):
        if isinstance(data, dict) and data.get("agent_name"):
            options.append({"label": str(data["agent_name"]), "value": path.stem})
    return options


def _template_options(
    dir_path: Path, include_sample: bool, include_merged: bool
) -> list[dict]:
    """扫描配置目录出模板名选项（label=value=模板名，规则与上游一致）。"""

    names: set[str] = set()
    if dir_path.is_dir():
        for file_name in dir_path.iterdir():
            name = file_name.name
            if name.endswith(".sample.yml"):
                if include_sample:
                    names.add(name[:-11])
            elif name.endswith(".merged.yml"):
                if include_merged:
                    names.add(name[:-11])
            elif name.endswith(".yml"):
                names.add(name[:-4])
    return [{"label": n, "value": n} for n in sorted(names, key=str.lower)]


def auto_battle_options(root: Path) -> list[dict]:
    """配队方案模板选项（config/auto_battle，sample/merged 模板均计入）。"""

    return _template_options(
        root / "config" / "auto_battle", include_sample=True, include_merged=True
    )


def lost_void_challenge_options(root: Path) -> list[dict]:
    """迷失之地挑战配置模板选项（config/lost_void_challenge，sample 计入）。"""

    return _template_options(
        root / "config" / "lost_void_challenge",
        include_sample=True,
        include_merged=False,
    )
