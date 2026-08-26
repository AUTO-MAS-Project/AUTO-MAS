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

import json
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
# MAS 运行时专属槽位配置名：开启「用户独立配置」时，把 per-user 配置落地到这个独立文件并据此启动，
# 绝不覆盖 BGI 同名的用户实配（{RootPath}/User/OneDragon/{用户所选名}.json 全程零接触）。
# 该槽位由 MAS 独占、运行后删除；名称避免与常见用户配置名冲突。
_MAS_ONE_DRAGON_SLOT_NAME = "MAS独立配置"

# BetterGI 内置自动战斗策略名（跨版本始终存在；AutoBossParam.BuildCombatStrategyPath 将其映射到 User\AutoFight\ 目录）
_AUTO_BOSS_BUILTIN_STRATEGY = "根据队伍自动选择"
# 自定义策略文件所在目录（{RootPath}/User/AutoFight/*.txt）
_AUTO_FIGHT_REL_DIR = Path("User") / "AutoFight"

# BetterGI 全局主配置（config.json）使用 camelCase 键。一条龙配置自带战斗字段的只有
# 秘境（PartyName）与首领讨伐（AutoBossTeamName/AutoBossStrategyName）；地脉花/幽境危战
# 则由 BetterGI 在 OneDragonTaskItem 里直接从全局 AutoLeyLineOutcropConfig /
# AutoStygianOnslaughtConfig 段读取队伍与策略（无一条龙专用字段），秘境策略走全局
# AutoFightConfig。故通用战斗队伍/策略需另补写以下 camelCase 叶子路径（tuple 表示嵌套）：
#   队伍:   autoLeyLineOutcropConfig.Team（地脉花）,
#           autoStygianOnslaughtConfig.fightTeamName（幽境危战）
#   策略:   autoFightConfig.strategyName（秘境）,
#           autoLeyLineOutcropConfig.fightConfig.strategyName（地脉花）,
#           autoStygianOnslaughtConfig.strategyName（幽境危战）
_BGI_CONFIG_REL_PATH = Path("User") / "config.json"

# 通用战斗队伍落到的叶子路径
_GLOBAL_TEAM_LEAVES = (
    ("autoLeyLineOutcropConfig", "Team"),
    ("autoStygianOnslaughtConfig", "fightTeamName"),
)

# 通用战斗策略落到的叶子路径
_GLOBAL_STRATEGY_LEAVES = (
    ("autoFightConfig", "strategyName"),
    ("autoLeyLineOutcropConfig", "fightConfig", "strategyName"),
    ("autoStygianOnslaughtConfig", "strategyName"),
)

# 全部待补写叶子路径：apply 用分组，快照/还原用全集
_ALL_GLOBAL_LEAVES = _GLOBAL_TEAM_LEAVES + _GLOBAL_STRATEGY_LEAVES


def list_auto_boss_strategies(root: Path) -> list[str]:
    """列出可选自动战斗策略：内置默认 + {RootPath}/User/AutoFight/*.txt 文件名。

    玩家可自行往该目录放置 .txt 战斗脚本，故每次调用实时扫描以反映最新选项。
    """
    options = [_AUTO_BOSS_BUILTIN_STRATEGY]
    autofight_dir = root / _AUTO_FIGHT_REL_DIR
    if autofight_dir.is_dir():
        for p in sorted(autofight_dir.glob("*.txt"), key=lambda p: p.stem):
            name = p.stem.strip()
            if name and name not in options:
                options.append(name)
    return options


def resolve_config_name(name: str) -> str:
    """解析一条龙配置名，空值显式兜底为「默认配置」。"""
    return (name or "").strip() or _DEFAULT_CONFIG_NAME


def launch_slot_name() -> str:
    """MAS 运行时专属槽位配置名（开启「用户独立配置」时据此启动一条龙）。"""
    return _MAS_ONE_DRAGON_SLOT_NAME


def one_dragon_slot_path(root: Path) -> Path:
    """MAS 运行时槽位配置文件的绝对路径（``{RootPath}/User/OneDragon/MAS独立配置.json``）。"""
    return one_dragon_path(root, _MAS_ONE_DRAGON_SLOT_NAME)


def remove_one_dragon_slot(root: Path) -> bool:
    """删除 MAS 运行时槽位配置（幂等）。返回是否确实存在并删除了。"""
    path = one_dragon_slot_path(root)
    existed = path.exists()
    path.unlink(missing_ok=True)
    return existed


def parse_custom_groups(raw: Any) -> list[dict[str, Any]]:
    """解析前端保存的自定义配置组 JSON 列表（字符串或已是列表），非法时返回空列表。

    元素过滤为 ``{"name", "enabled"}`` 结构。
    """
    if isinstance(raw, list):
        data = raw
    elif isinstance(raw, str):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return []
        if not isinstance(data, list):
            return []
    else:
        return []
    return [
        {"name": str(item.get("name", "")).strip(), "enabled": bool(item.get("enabled", True))}
        for item in data
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    ]


def list_custom_groups(root: Path, config_name: str) -> list[dict[str, Any]]:
    """列出某一条龙配置里的自定义配置组（非内置 8 组），按 ``TaskOrder`` 相对顺序。

    供前端「自定义配置组」表格自动加载：读取 BetterGI 现有配置，返回
    ``[{"name": ..., "enabled": ...}, ...]``。
    """
    config = load_one_dragon(root, config_name)
    defs: dict[str, str] = config.get("TaskDefinitions") or {}
    enabled_map: dict[str, bool] = config.get("TaskEnabledList") or {}
    order: list[str] = list(config.get("TaskOrder") or [])
    name_by_uid = {uid: n for uid, n in defs.items() if n}
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for uid in order:
        name = name_by_uid.get(uid)
        if not name or name in _BUILTIN_ONE_DRAGON_GROUPS or name in seen:
            continue
        seen.add(name)
        items.append({"name": name, "enabled": bool(enabled_map.get(uid, True))})
    # 兜底：不在 TaskOrder 里但存在定义的自定义组
    for uid, name in defs.items():
        if (
            name
            and name not in _BUILTIN_ONE_DRAGON_GROUPS
            and name not in seen
        ):
            seen.add(name)
            items.append({"name": name, "enabled": bool(enabled_map.get(uid, True))})
    return items


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
    daily_reward_party_name: str = "",
    party_name: str = "",
    auto_boss_strategy_name: str = "",
    custom_groups: list[dict[str, Any]] | None = None,
    manage_custom_groups: bool = False,
) -> None:
    """把组开关与队伍/策略设置应用到一条龙配置，写入 BGI 运行时槽位并缓存 per-user 副本。

    种子优先级：per-user 副本 → BetterGI 现有配置 → 内置模板。
    关键：物化结果写入 MAS 专属槽位 ``{RootPath}/User/OneDragon/MAS独立配置.json``（据此启动，
    运行后由 ``remove_one_dragon_slot`` 删除），而 **不写入用户所选名的 BGI 实配**——BGI 同名
    配置全程零接触，不会被覆盖成用户独立配置的样子。per-user 缓存仍以用户所选名 key。

    非组字段（领取奖励队伍/战斗队伍/战斗策略）仅在非空时覆盖配置（留空不覆盖）；
    其中「战斗队伍/战斗策略」会落到秘境 ``PartyName`` 与首领讨伐的
    ``AutoBossTeamName`` / ``AutoBossStrategyName``（秘境策略仍走全局
    ``autoFightConfig``）；地脉花/幽境危战/以及秘境策略另外经
    ``apply_global_battle_team`` / ``apply_global_battle_strategy`` 补写全局 config.json。
    ``manage_custom_groups`` 开启时按 ``custom_groups``（name→enabled）管理自定义组，
    否则自定义组原样保留（由 BetterGI 内部决定）。
    """
    config_name = resolve_config_name(config_name)
    user_path = per_user_one_dragon_path(script_id, user_id, config_name)

    config = read_file(user_path)
    if not isinstance(config, dict):
        config = load_one_dragon(root, config_name)
    if not config:
        config = load_seed_template()

    config = apply_groups(
        config, groups, custom_groups=custom_groups, manage_customs=manage_custom_groups
    )
    if daily_reward_party_name:
        config["DailyRewardPartyName"] = daily_reward_party_name
    if party_name:
        config["PartyName"] = party_name
        # 一条龙自动首领讨伐从 AutoBossTeamName 取队伍（OneDragonTaskItem.cs）
        config["AutoBossTeamName"] = party_name
    if auto_boss_strategy_name:
        config["AutoBossStrategyName"] = auto_boss_strategy_name
    write_one_dragon(root, _MAS_ONE_DRAGON_SLOT_NAME, config)
    write_file(user_path, config)


def _global_config_path(root: Path) -> Path:
    """BetterGI 全局主配置 config.json 的绝对路径。"""
    return root / _BGI_CONFIG_REL_PATH


def _set_leaf(config: dict, leaf: tuple[str, ...], value: str) -> bool:
    """沿叶子路径向下补建字典并赋 ``value``；值未变返回 False（避免无谓触写）。"""
    cur = config
    for key in leaf[:-1]:
        nxt = cur.get(key)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[key] = nxt
        cur = nxt
    key = leaf[-1]
    if cur.get(key) == value:
        return False
    cur[key] = value
    return True


def _apply_leaves(root: Path, leaves, value: str) -> None:
    """把 ``value`` 补写到 config.json 的若干叶子路径，保留同段其余字段；空值不写。"""
    value = (value or "").strip()
    if not value:
        return
    config = read_file(_global_config_path(root))
    if not isinstance(config, dict):
        config = {}
    changed = False
    for leaf in leaves:
        changed |= _set_leaf(config, leaf, value)
    if changed:
        write_file(_global_config_path(root), config)


def apply_global_battle_team(root: Path, party_name: str) -> None:
    """把通用战斗队伍补写进 BetterGI 全局配置，供一条龙的地脉花/幽境危战读取。

    首领讨伐走一条龙 ``AutoBossTeamName``（见 ``write_user_one_dragon``）；地脉花/幽境危战
    由 BGI 直读全局段，故在此补写。保留同段其余字段；空值不覆盖。
    """
    _apply_leaves(root, _GLOBAL_TEAM_LEAVES, party_name)


def apply_global_battle_strategy(root: Path, strategy_name: str) -> None:
    """把通用战斗策略补写进 BetterGI 全局配置，供一条龙的秘境/地脉花/幽境危战读取。

    首领讨伐走一条龙 ``AutoBossStrategyName``（见 ``write_user_one_dragon``）；其余三项
    由 BGI 直读全局段。保留同段其余字段；空值不覆盖。
    """
    _apply_leaves(root, _GLOBAL_STRATEGY_LEAVES, strategy_name)


def _restore_leaf(config: dict, leaf: tuple[str, ...], existed: bool, value) -> bool:
    """还原单个叶子：原存在则回写原值，原缺失则删除；返回是否实际改写。"""
    parent = config
    for key in leaf[:-1]:
        nxt = parent.get(key) if isinstance(parent, dict) else None
        if not isinstance(nxt, dict):
            return False  # 父链已不存在（本次并未补写该叶子），无需还原
        parent = nxt
    if not isinstance(parent, dict):
        return False
    key = leaf[-1]
    if existed:
        if parent.get(key) != value:
            parent[key] = value
            return True
        return False
    if key in parent:
        del parent[key]
        return True
    return False


def _prune_empty_ancestors(config: dict, leaf: tuple[str, ...]) -> None:
    """沿 leaf 前缀（不含叶子本身）从深到浅删除沿途变空的字典。"""
    prefix = list(leaf[:-1])
    while prefix:
        cur = config
        broken = False
        for key in prefix[:-1]:
            nxt = cur.get(key) if isinstance(cur, dict) else None
            if not isinstance(nxt, dict):
                broken = True
                break
            cur = nxt
        if broken:
            return
        last = prefix[-1]
        grand = cur.get(last) if isinstance(cur, dict) else None
        if isinstance(grand, dict) and not grand:
            del cur[last]
            prefix.pop()
        else:
            return


def snapshot_global_battle_config(root: Path) -> dict[tuple[str, ...], tuple[bool, Any]]:
    """快照 config.json 本次可能改写的队伍/策略叶子路径，供结束还原。

    键为叶子路径元组，值为 ``(该叶子原本是否存在, 原值)``。
    """
    config = read_file(_global_config_path(root))
    if not isinstance(config, dict):
        config = {}
    snap: dict[tuple[str, ...], tuple[bool, Any]] = {}
    for leaf in _ALL_GLOBAL_LEAVES:
        cur: Any = config
        present = True
        for key in leaf:
            if not isinstance(cur, dict) or key not in cur:
                present = False
                break
            cur = cur[key]
        snap[leaf] = (present, cur if present else None)
    return snap


def restore_global_battle_config(root: Path, snapshot: dict[tuple[str, ...], tuple[bool, Any]]) -> None:
    """把 config.json 的队伍/策略叶子路径还原为快照状态，消除单次运行残留。

    原本缺失则删除（沿路径清理变空字典），原本存在则回写原值；只改写本次动过的键。
    """
    if not snapshot:
        return
    config = read_file(_global_config_path(root))
    if not isinstance(config, dict):
        return
    changed = False
    for leaf in _ALL_GLOBAL_LEAVES:
        existed, value = snapshot.get(leaf, (False, None))
        if _restore_leaf(config, leaf, existed, value):
            changed = True
    if changed:
        for leaf in _ALL_GLOBAL_LEAVES:
            _prune_empty_ancestors(config, leaf)
        write_file(_global_config_path(root), config)


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


def apply_groups(
    config: dict[str, Any],
    enabled: list[str],
    custom_groups: list[dict[str, Any]] | None = None,
    manage_customs: bool = False,
) -> dict[str, Any]:
    """按组名切换一条龙配置的组开关，保留其余设置。

    按钮是「开关」而非删减：对每个内置组在 ``TaskEnabledList`` 里置 ``true/false``，
    组定义保留（便于日后重新打开）；仅在按钮 ON 而配置里缺失时才补建新组。

    自定义组处理分两种情况：
    - ``manage_customs=False``（总开关关）：自定义组一律原样保留其 UUID、启用状态与
      相对顺序，启用与否由 BetterGI 内部配置决定。
    - ``manage_customs=True``（总开关开）：按 ``custom_groups``（[{"name","enabled"}]）
      覆盖自定义组启用状态：入表组按表状态、未入表（但 BetterGI 文件里存在）组默认开、
      入表且启用但配置缺失时补建。

    应用到当前运行的配置（``Name`` 指向哪个就写哪个），不局限于某一份命名。

    Args:
        config: 一条龙配置 dict（可为空 ``{}``）。
        enabled: 按钮打开的 8 个内置组名列表。
        custom_groups: 自定义配置组管理列表（name→enabled），仅 ``manage_customs`` 时使用。
        manage_customs: 是否管理自定义组开关。

    Returns:
        修改后的配置 dict（浅拷贝，原 ``config`` 不变）。
    """
    config = dict(config or {})
    selected = [n for n in enabled if n in _BUILTIN_ONE_DRAGON_GROUPS]
    selected_set = set(selected)

    # 自定义组管理表：name -> enabled
    custom_enabled: dict[str, bool] = {}
    for cg in custom_groups or []:
        name = (cg.get("name") if isinstance(cg, dict) else None) or ""
        name = str(name).strip()
        if name and name not in _BUILTIN_ONE_DRAGON_GROUPS:
            custom_enabled[name] = bool(cg.get("enabled", True))

    old_defs: dict[str, str] = config.get("TaskDefinitions") or {}
    old_enabled: dict[str, bool] = config.get("TaskEnabledList") or {}
    old_order: list[str] = list(config.get("TaskOrder") or [])
    name_by_uid = {uid: n for uid, n in old_defs.items() if n}

    new_defs: dict[str, str] = {}
    new_order: list[str] = []
    new_enabled: dict[str, bool] = {}
    present_builtin: set[str] = set()

    # 单遍扫描旧顺序：内置组按按钮开关置 enabled，自定义组按管理表/原样保留，保持相对顺序
    for uid in old_order:
        name = name_by_uid.get(uid)
        if not name or uid in new_defs:
            continue
        if name in _BUILTIN_ONE_DRAGON_GROUPS:
            present_builtin.add(name)
            new_defs[uid] = name
            new_order.append(uid)
            new_enabled[uid] = name in selected_set
        else:  # 自定义组
            new_defs[uid] = name
            new_order.append(uid)
            if manage_customs:
                # 入表按表状态；未入表默认开
                new_enabled[uid] = bool(custom_enabled.get(name, True))
            else:
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
            if manage_customs:
                new_enabled[uid] = bool(custom_enabled.get(name, True))
            else:
                new_enabled[uid] = bool(old_enabled.get(uid, True))

    # 按钮 ON 但配置缺失的内置组：补建并启用
    for name in selected:
        if name not in present_builtin:
            uid = str(uuid.uuid4())
            new_defs[uid] = name
            new_order.append(uid)
            new_enabled[uid] = True

    # 管理开启时：入表且启用但配置里缺失的自定义组：补建并启用
    if manage_customs:
        for name, on in custom_enabled.items():
            if on and name not in new_defs.values():
                uid = str(uuid.uuid4())
                new_defs[uid] = name
                new_order.append(uid)
                new_enabled[uid] = True

    config["TaskDefinitions"] = new_defs
    config["TaskOrder"] = new_order
    config["TaskEnabledList"] = new_enabled
    return config
