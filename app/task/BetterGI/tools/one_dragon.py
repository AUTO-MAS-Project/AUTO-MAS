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

MAS 只管理 8 个内置配置组，其余自定义组（用户自建 ScriptGroup）本轮不管理、原样保留；
除三个组列表外的所有设置字段（队伍/秘境/地脉花/首领讨伐等）一律原样保留。
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
    """按组名切换一条龙的配置组，保留其余设置与自定义组。

    只增删 8 个内置组：``enabled`` 里的内置组按顺序保留（已存在则复用原 UUID，否则生成新
    UUID），不在 ``enabled`` 的内置组移除；非内置组（自定义 ScriptGroup）原样保留其
    UUID、启用状态与相对顺序。除三个组列表外的字段均不动。

    Args:
        config: 一条龙配置 dict（可为空 ``{}``）。
        enabled: 要执行的内置组名列表（乱序会被过滤到内置组并按给定顺序排列）。

    Returns:
        修改后的配置 dict（浅拷贝，原 ``config`` 不变）。
    """
    config = dict(config or {})
    enabled = [n for n in enabled if n in _BUILTIN_ONE_DRAGON_GROUPS]

    old_defs: dict[str, str] = config.get("TaskDefinitions") or {}
    old_enabled: dict[str, bool] = config.get("TaskEnabledList") or {}
    old_order: list[str] = list(config.get("TaskOrder") or [])

    # 自定义组（非内置组）——按原顺序保留，其余情况兜底补上未排序的
    custom_entries: list[tuple[str, str]] = []
    seen_custom: set[str] = set()
    for uid in old_order:
        name = old_defs.get(uid)
        if name and name not in _BUILTIN_ONE_DRAGON_GROUPS:
            custom_entries.append((uid, name))
            seen_custom.add(name)
    for uid, name in old_defs.items():
        if name and name not in _BUILTIN_ONE_DRAGON_GROUPS and name not in seen_custom:
            custom_entries.append((uid, name))
            seen_custom.add(name)

    # 内置组：按组名复用已有 UUID
    builtin_uuid_by_name: dict[str, str] = {}
    for uid, name in old_defs.items():
        if name in _BUILTIN_ONE_DRAGON_GROUPS:
            builtin_uuid_by_name.setdefault(name, uid)

    new_defs: dict[str, str] = {}
    new_order: list[str] = []
    new_enabled: dict[str, bool] = {}

    for uid, name in custom_entries:
        new_defs[uid] = name
        new_order.append(uid)
        new_enabled[uid] = bool(old_enabled.get(uid, True))

    for name in enabled:
        uid = builtin_uuid_by_name.get(name) or str(uuid.uuid4())
        new_defs[uid] = name
        new_order.append(uid)
        new_enabled[uid] = True

    config["TaskDefinitions"] = new_defs
    config["TaskOrder"] = new_order
    config["TaskEnabledList"] = new_enabled
    return config
