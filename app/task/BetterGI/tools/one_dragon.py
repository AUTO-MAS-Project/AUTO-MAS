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

"""BetterGI 一条龙配置读写与配置组切换。

BetterGI 一条龙配置以独立 JSON 文件保存于 ``{RootPath}/User/OneDragon/{配置名}.json``
（``Name`` 字段 == 文件名）。每个配置组以「组名」标识（``TaskDefinitions`` 的 value），
UUID 是每实例随机生成的临时标识，因此本模块按组名识别与切换，新组用 ``uuid.uuid4()`` 生成。

MAS 只管理 8 个内置配置组（按组名对其 enabled 置 true/false，组定义保留、可逆），
其余自定义组（用户自建 ScriptGroup）本轮不管理、原样保留，其启用与否由 BetterGI 内部
配置决定；除三个组列表外的所有设置字段（队伍/秘境/地脉花/首领讨伐等）一律原样保留。
"""

import uuid
from pathlib import Path
from typing import Any

from app.utils.io import read_file, write_file

# 8 个内置一条龙配置组（与 app/models/config.py 的 _BGI_BUILTIN_ONE_DRAGON_GROUPS 同步）
_BUILTIN_ONE_DRAGON_GROUPS = [
    "领取邮件",
    "合成树脂",
    "自动地脉花",
    "自动秘境",
    "自动首领讨伐",
    "自动幽境危战",
    "领取每日奖励",
    "领取尘歌壶奖励",
]

# 一条龙配置目录（从 RootPath 派生）
_ONE_DRAGON_REL_DIR = Path("User") / "OneDragon"

# 内置种子模板（随 MAS 版本同步）
_RES_TEMPLATE_DIR = Path.cwd() / "res" / "templates" / "BetterGI"
_SEED_TEMPLATE = _RES_TEMPLATE_DIR / "OneDragon" / "默认配置.json"

# 空配置名的显式兜底配置名
_DEFAULT_CONFIG_NAME = "默认配置"


def resolve_config_name(name: str) -> str:
    """解析一条龙配置名，空值显式兜底为「默认配置」。"""
    return (name or "").strip() or _DEFAULT_CONFIG_NAME


def one_dragon_path(root: Path, name: str) -> Path:
    """一条龙配置文件的绝对路径。"""
    return root / _ONE_DRAGON_REL_DIR / f"{resolve_config_name(name)}.json"


def load_one_dragon(root: Path, name: str) -> dict[str, Any]:
    """读取一条龙配置；文件不存在返回空 ``{}``。"""
    data = read_file(one_dragon_path(root, name))
    return data if isinstance(data, dict) else {}


def write_one_dragon(root: Path, name: str, config: dict[str, Any]) -> Path:
    """写入一条龙配置（同步 ``Name`` 字段与文件名）。"""
    name = resolve_config_name(name)
    config = dict(config)
    config["Name"] = name
    out_path = one_dragon_path(root, name)
    write_file(out_path, config)
    return out_path


def load_seed_template() -> dict[str, Any]:
    """读取内置种子模板；模板缺失时返回仅含 8 个内置组的最小合法配置。"""
    data = read_file(_SEED_TEMPLATE)
    if isinstance(data, dict) and data:
        return data
    return _minimal_config()


def _minimal_config() -> dict[str, Any]:
    """构造最小合法的一条龙配置（仅 8 个内置组全部开启，无其它设置）。"""
    defs: dict[str, str] = {}
    order: list[str] = []
    for name in _BUILTIN_ONE_DRAGON_GROUPS:
        uid = str(uuid.uuid4())
        defs[uid] = name
        order.append(uid)
    return {
        "TaskEnabledList": {uid: True for uid in order},
        "TaskOrder": order,
        "TaskDefinitions": defs,
        "Name": _DEFAULT_CONFIG_NAME,
        "NextTaskId": "",
    }


def per_user_one_dragon_path(script_id: str, user_id: str, config_name: str) -> Path:
    """某用户的一条龙配置副本路径 ``data/{script_id}/{user_id}/OneDragon/{name}.json``。"""
    return (
        Path.cwd()
        / "data"
        / script_id
        / user_id
        / "OneDragon"
        / f"{resolve_config_name(config_name)}.json"
    )


def write_user_one_dragon(
    root: Path,
    script_id: str,
    user_id: str,
    config_name: str,
    groups: list[str],
) -> None:
    """把组开关应用到一条龙配置，写入 BetterGI 并缓存 per-user 副本。

    种子优先级：per-user 副本 → BetterGI 现有配置 → 内置模板。
    """
    config_name = resolve_config_name(config_name)
    user_path = per_user_one_dragon_path(script_id, user_id, config_name)

    config = read_file(user_path)
    if not isinstance(config, dict):
        config = load_one_dragon(root, config_name)
    if not config:
        config = load_seed_template()

    config = apply_groups(config, groups)
    write_one_dragon(root, config_name, config)
    write_file(user_path, config)


def snapshot_user_one_dragon(
    root: Path,
    script_id: str,
    user_id: str,
    config_name: str,
) -> None:
    """回读 BetterGI 现有一条龙配置为 per-user 副本（捕获 GUI 中改的设置）。"""
    config_name = resolve_config_name(config_name)
    config = load_one_dragon(root, config_name)
    if config:
        write_file(per_user_one_dragon_path(script_id, user_id, config_name), config)


def apply_groups(config: dict[str, Any], enabled: list[str]) -> dict[str, Any]:
    """按组名切换一条龙配置的组开关，保留其余设置与自定义组。

    按钮是「开关」而非删减：对每个内置组在 ``TaskEnabledList`` 里置 ``true/false``，
    组定义保留（便于日后重新打开）；仅在按钮 ON 而配置里缺失时才补建新组。
    非内置组（自定义 ScriptGroup）无按钮，一律原样保留其 UUID、启用状态与相对顺序；
    其启用与否由 BetterGI 内部配置决定（内部开着就跑）。

    应用到当前运行的配置（``Name`` 指向哪个就写哪个），不局限于某一份命名。

    Args:
        config: 一条龙配置 dict（可为空 ``{}``）。
        enabled: 按钮打开的 8 个内置组名列表。

    Returns:
        修改后的配置 dict（浅拷贝，原 ``config`` 不变）。
    """
    config = dict(config or {})
    selected = [n for n in enabled if n in _BUILTIN_ONE_DRAGON_GROUPS]
    selected_set = set(selected)

    old_defs: dict[str, str] = config.get("TaskDefinitions") or {}
    old_enabled: dict[str, bool] = config.get("TaskEnabledList") or {}
    old_order: list[str] = list(config.get("TaskOrder") or [])
    name_by_uid = {uid: n for uid, n in old_defs.items() if n}

    new_defs: dict[str, str] = {}
    new_order: list[str] = []
    new_enabled: dict[str, bool] = {}
    present_builtin: set[str] = set()

    # 单遍扫描旧顺序：自定义组原样保留，内置组按按钮开关置 enabled，保持相对顺序
    for uid in old_order:
        name = name_by_uid.get(uid)
        if not name or uid in new_defs:
            continue
        if name in _BUILTIN_ONE_DRAGON_GROUPS:
            present_builtin.add(name)
            new_defs[uid] = name
            new_order.append(uid)
            new_enabled[uid] = name in selected_set
        else:  # 自定义组：启用状态不干预（保留 BetterGI 内部设定）
            new_defs[uid] = name
            new_order.append(uid)
            new_enabled[uid] = bool(old_enabled.get(uid, True))

    # 兜底：未出现在 TaskOrder 的自定义组不丢失
    for uid, name in old_defs.items():
        if (
            name
            and name not in _BUILTIN_ONE_DRAGON_GROUPS
            and uid not in new_defs
        ):
            new_defs[uid] = name
            new_order.append(uid)
            new_enabled[uid] = bool(old_enabled.get(uid, True))

    # 按钮 ON 但配置缺失的内置组：补建并启用
    for name in selected:
        if name not in present_builtin:
            uid = str(uuid.uuid4())
            new_defs[uid] = name
            new_order.append(uid)
            new_enabled[uid] = True

    config["TaskDefinitions"] = new_defs
    config["TaskOrder"] = new_order
    config["TaskEnabledList"] = new_enabled
    return config
