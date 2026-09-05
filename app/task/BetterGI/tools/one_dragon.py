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
import threading
import uuid
from pathlib import Path
from typing import Any

from app.models.config import _BGI_BUILTIN_ONE_DRAGON_GROUPS
from app.utils import resource_path
from app.utils.io import read_file, write_file

# 8 个内置一条龙配置组：单一来源为 app/models/config.py 的 _BGI_BUILTIN_ONE_DRAGON_GROUPS，
# 此处仅别名引用，避免双份硬编码随版本漂移。
_BUILTIN_ONE_DRAGON_GROUPS = _BGI_BUILTIN_ONE_DRAGON_GROUPS

# 全局主配置 config.json 的读-改-写串行化锁。atomic_write 只保证单次写原子，
# 读-改-写整体仍可能交错丢失更新（切号的 _ensure_auto_update_on_cli 与一条龙的
# apply_global_battle_* / snapshot / restore 都读写同一文件），故加锁串行化。
GLOBAL_CONFIG_LOCK = threading.Lock()

# 一条龙配置目录（从 RootPath 派生）
_ONE_DRAGON_REL_DIR = Path("User") / "OneDragon"

# 内置种子模板（随 MAS 版本同步）
_RES_TEMPLATE_DIR = resource_path("templates", "BetterGI")
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

# BetterGI 自定义 JS 脚本目录（{RootPath}/User/JsScript/*/manifest.json 即一个可执行脚本）
_JS_SCRIPT_REL_DIR = Path("User") / "JsScript"

# BetterGI 地图追踪（AutoPathing）路径文件目录：{RootPath}/User/AutoPathing/**/*.json
_AUTO_PATHING_REL_DIR = Path("User") / "AutoPathing"

# BetterGI 脚本仓库（订阅/下载的自定义脚本源仓库）：{RootPath}/Repos/bettergi-scripts-list
_REPO_REL_DIR = Path("Repos") / "bettergi-scripts-list"

# BetterGI 配置组目录（{RootPath}/User/ScriptGroup/*.json，BGI 一条龙自定义组定义）
_SCRIPT_GROUP_REL_DIR = Path("User") / "ScriptGroup"

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


def list_js_scripts(root: Path) -> list[tuple[str, str]]:
    """列出 BetterGI 可执行的自定义 JS 脚本。

    返回 ``[(目录名, manifest 显示名)]``：BetterGI 一条龙按**目录名**定位并执行任务
    （TaskDefinitions 的 value = 目录名），而目录名常为英文（如 ``AAA-Artifacts-Bulk-Supply``），
    ``manifest.json`` 的 ``name`` 才是玩家可读的中文显示名（如「AAA狗粮批发」）。
    候选列表应展示显示名、落库用目录名，故两者都返回。

    每个脚本目录须含 ``manifest.json`` 才视为可执行脚本（BetterGI 脚本目录语义），
    每次调用实时扫描以反映玩家手工放置/订阅更新的脚本。
    """
    items: list[tuple[str, str]] = []
    js_dir = root / _JS_SCRIPT_REL_DIR
    if js_dir.is_dir():
        for p in sorted(js_dir.iterdir()):
            if not p.is_dir():
                continue
            manifest = p / "manifest.json"
            if not manifest.is_file():
                continue
            folder = p.name.strip()
            display = folder
            data = read_file(manifest)
            if isinstance(data, dict) and isinstance(data.get("name"), str):
                display = data["name"].strip() or folder
            if folder and not any(f == folder for f, _ in items):
                items.append((folder, display))
    return items


def list_script_groups(root: Path) -> list[str]:
    """列出 BetterGI 配置组候选：{RootPath}/User/ScriptGroup/*.json 的文件名。

    配置组是 BetterGI 一条龙可引用的自定义任务组定义（BetterGI GUI 的「配置组」，
    文件名即组名，与一条龙 TaskDefinitions 的引用名一致，如「锄地一条龙」、
    「每日秘境DHXYHO」）。每次调用实时扫描，以反映 BGI 侧手工新增/删除的配置组。
    """
    names: list[str] = []
    sg_dir = root / _SCRIPT_GROUP_REL_DIR
    if sg_dir.is_dir():
        for p in sorted(sg_dir.glob("*.json"), key=lambda p: p.stem):
            name = p.stem.strip()
            if name and name not in names:
                names.append(name)
    return names


def read_script_group(root: Path, name: str) -> dict[str, Any]:
    """读取某个配置组 json 全文（{RootPath}/User/ScriptGroup/{name}.json）。

    配置组 json 的结构：``{index, name, config, projects: [...]}``，其中
    ``projects`` 为组内脚本项目数组（每项含 name/folderName/index/type/status/
    schedule/runNum/allowJsNotification/allowJsHTTPHash/jsScriptSettingsObject）。
    文件不存在或非法时返回空 dict。
    """
    sg_dir = root / _SCRIPT_GROUP_REL_DIR
    path = sg_dir / f"{resolve_script_group_name(name)}.json"
    data = read_file(path)
    return data if isinstance(data, dict) else {}


def write_script_group(root: Path, name: str, data: dict[str, Any]) -> Path:
    """把配置组 json 全文写回 {RootPath}/User/ScriptGroup/{name}.json。

    同步顶层 ``name``（组名即文件名）与 ``index`` 之外的结构字段一律原样保留；
    ``data`` 传入的 projects 数组将整体替换（顺序即 BGI 执行顺序）。
    """
    name = resolve_script_group_name(name)
    data = dict(data or {})
    data["name"] = name
    sg_dir = root / _SCRIPT_GROUP_REL_DIR
    sg_dir.mkdir(parents=True, exist_ok=True)
    out_path = sg_dir / f"{name}.json"
    write_file(out_path, data)
    return out_path


def resolve_script_group_name(name: str) -> str:
    """解析配置组名：去首尾空白，拒绝路径穿越与空名。"""
    name = (name or "").strip()
    if not name:
        raise ValueError("配置组名不能为空")
    if any(c in name for c in ("/", "\\", "..")):
        raise ValueError(f"配置组名非法: {name!r}")
    return name


def list_script_settings_ui(root: Path, folder: str) -> list[dict[str, Any]]:
    """读取某个 JsScript 脚本目录的 settings.json UI 定义（用于双击弹窗渲染）。

    BetterGI 每个可执行 JS 脚本目录（{RootPath}/User/JsScript/{folder}/）下有
    ``settings.json``：以数组声明脚本设置项的表单（name/type/label/options/default，
    支持 select / input-text / checkbox / multi-checkbox / separator）。
    目录缺失或文件非法返回空列表。
    """
    folder = (folder or "").strip()
    if not folder or any(c in folder for c in ("/", "\\", "..")):
        return []
    js_dir = root / _JS_SCRIPT_REL_DIR / folder
    settings = js_dir / "settings.json"
    data = read_file(settings)
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def read_script_readme(root: Path, folder: str) -> str:
    """读取某个 JsScript 脚本目录的 README（脚本说明，用于双击弹窗「脚本说明」标签）。

    BetterGI 可执行脚本目录（{RootPath}/User/JsScript/{folder}/）通常带 ``README.md``
    说明脚本用法/注意事项。大小写不敏感匹配常见命名；返回纯文本，缺失返回空串。
    """
    folder = (folder or "").strip()
    if not folder or any(c in folder for c in ("/", "\\", "..")):
        return ""
    js_dir = root / _JS_SCRIPT_REL_DIR / folder
    if not js_dir.is_dir():
        return ""
    for name in ("README.md", "readme.md", "Readme.md", "README.txt", "readme.txt"):
        candidate = js_dir / name
        if candidate.is_file():
            try:
                text = candidate.read_text(encoding="utf-8", errors="replace")
            except OSError:
                text = ""
            return (text or "").strip()
    return ""


def per_user_script_group_path(script_id: str, user_id: str, name: str) -> Path:
    """某用户的配置组 json 副本路径 ``data/{script_id}/{user_id}/ScriptGroup/{name}.json``。

    BetterGI 的配置组（``User/ScriptGroup/*.json``）是 BGI 全局共享文件；在「用户独立
    配置」语义下，MAS 把该用户对配置组的编辑（项目顺序 / 各项目 jsScriptSettingsObject）
    落在 per-user 副本，BGI 同名实配全程零接触（种子：per-user 副本 → BGI 实配）。
    """
    return (
        Path.cwd()
        / "data"
        / script_id
        / user_id
        / "ScriptGroup"
        / f"{resolve_script_group_name(name)}.json"
    )


def read_user_script_group(
    root: Path, script_id: str, user_id: str, name: str
) -> dict[str, Any]:
    """读取某用户的配置组 json（per-user 副本 → BGI 实配的种子顺序）。

    供右栏「配置组项目编辑」渲染与编辑：副本缺失/未生成时回退 BGI 实配，
    保证展示的是用户当前可编辑的内容（首次编辑时即以实配为底稿）。
    """
    name = resolve_script_group_name(name)
    copy = read_file(per_user_script_group_path(script_id, user_id, name))
    if isinstance(copy, dict) and copy:
        return copy
    return read_script_group(root, name)


def write_user_script_group(
    root: Path, script_id: str, user_id: str, name: str, config: dict[str, Any]
) -> Path:
    """把用户编辑后的配置组 json 写回 per-user 副本（不触碰 BGI 同名实配）。

    ``config`` 传入的是完整配置组 json（含 projects 数组顺序与每项的
    jsScriptSettingsObject）；写前同步 ``name`` 字段。缺目录自动补建。
    """
    name = resolve_script_group_name(name)
    config = dict(config or {})
    config["name"] = name
    out_path = per_user_script_group_path(script_id, user_id, name)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_file(out_path, config)
    return out_path


# 官方传送点资源：tp.json 内可刷秘境（每周秘境/自动秘境）的类型名
# BlessDomain=圣遗物、ForgeryDomain=武器素材、MasteryDomain=天赋素材
_TP_DOMAIN_TYPES = ("BlessDomain", "ForgeryDomain", "MasteryDomain")


def scan_domain_catalog(root: Path) -> tuple[str, list[dict[str, Any]]]:
    """扫描每周秘境可选的秘境目录，返回 ``(来源说明, 秘境列表)``。

    **以官方传送点 ``GameTask/AutoTrackPath/Assets/tp.json`` 为唯一权威来源**：
    BetterGI 前端每周秘境下拉的秘境候选与其奖励物品列表，正来自 tp.json 中
    Bless/Forgery/Mastery 三类 Domain 点的 ``name/country/rewards`` 字段
    （BetterGI 运行时也按同名字典定位秘境传送点）。不依赖任何用户脚本资产
    （AutoDomainCustomizable 等删除后不受影响）。

    返回项结构：``{name, region, category, rewards}``；
    ``rewards`` 为该秘境奖励物品数组（顺序与 BGI 前端展示/领奖档位 1/2/3 一致，
    即 rewards[0]=领奖序号 1、rewards[1]=2、rewards[2]=3；圣遗物本为两件套装）。
    """

    tp_candidates = [
        root / "GameTask" / "AutoTrackPath" / "Assets" / "tp.json",
        root / "GameTask" / "AutoTrackPath" / "Assets" / "TP.json",
    ]
    for tp_path in tp_candidates:
        if not tp_path.is_file():
            continue
        items = _parse_tp_domain_names(tp_path)
        if items:
            return str(tp_path), items
    return "", []


def _parse_tp_domain_names(tp_path: Path) -> list[dict[str, Any]]:
    """从官方 tp.json 提取可刷的秘境（Bless/Forgery/Mastery 三类）及其奖励物品。

    tp.json 结构：``{data: [{points: [{type, name, country, rewards: [...], ...}]}]}``。
    仅收集目标类型且 name 非空、去重（同名多次出现时只列一次）；
    ``rewards`` 为纯物品名数组（顺序即 BGI 前端展示顺序，圣遗物为两件套装）。
    """

    raw = read_file(tp_path)
    if not isinstance(raw, dict):
        return []
    data = raw.get("data")
    if not isinstance(data, list):
        return []
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for scene in data:
        if not isinstance(scene, dict):
            continue
        points = scene.get("points")
        if not isinstance(points, list):
            continue
        for pt in points:
            if not isinstance(pt, dict):
                continue
            if pt.get("type") not in _TP_DOMAIN_TYPES:
                continue
            name = str(pt.get("name") or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            rewards_raw = pt.get("rewards")
            rewards: list[str] = []
            if isinstance(rewards_raw, list):
                rewards = [
                    str(r).strip()
                    for r in rewards_raw
                    if isinstance(r, str) and str(r).strip()
                ]
            out.append(
                {
                    "name": name,
                    "region": str(pt.get("country") or "").strip(),
                    "category": str(pt.get("type") or "").strip(),
                    "rewards": rewards,
                }
            )
    return out


def resolve_script_dirs(root: Path) -> dict[str, str]:
    """返回 BetterGI 常用目录与可执行文件绝对路径。

    - ``repo``：脚本仓库检出目录（{RootPath}/Repos/bettergi-scripts-list，BGI 的 ScriptRepoUpdater 管理）
    - ``jsScript``：脚本目录（{RootPath}/User/JsScript）
    - ``autoPathing``：地图追踪任务目录（{RootPath}/User/AutoPathing）
    - ``oneDragon``：一条龙配置目录（{RootPath}/User/OneDragon）
    - ``scriptGroup``：配置组目录（{RootPath}/User/ScriptGroup）
    - ``exe``：BetterGI 主程序（{RootPath}/BetterGI.exe，用于打开 BGI 调度/主界面）

    目录不存在时仅返回派生路径，由调用方决定是否提示缺失；返回绝对路径便于前端直接打开。
    """
    return {
        "repo": str((root / _REPO_REL_DIR).resolve()),
        "jsScript": str((root / _JS_SCRIPT_REL_DIR).resolve()),
        "autoPathing": str((root / _AUTO_PATHING_REL_DIR).resolve()),
        "oneDragon": str((root / _ONE_DRAGON_REL_DIR).resolve()),
        "scriptGroup": str((root / _SCRIPT_GROUP_REL_DIR).resolve()),
        "exe": str((root / "BetterGI.exe").resolve()),
    }


def build_auto_pathing_tree(root: Path) -> tuple[str, list[dict]]:
    """递归构建 BetterGI 地图追踪目录树（{RootPath}/User/AutoPathing）。

    返回 ``(AutoPathing 绝对目录, 目录树)``；目录树节点结构：
    ``{"name": 目录名, "dirs": [子节点...], "files": [路径文件名(不含 .json)]}``。
    路径文件名不含 ``.json`` 且带相对目录前缀，如 ``0_0_飞萤/A01-蒙德-…``；
    由于已确认存在跨目录同名文件，文件展示以「目录前缀 + 文件名」保证可读唯一。

    Args:
        root: BetterGI RootPath。

    Returns:
        (AutoPathing 绝对目录字符串, 顶层目录树列表)。目录不存在时返回空树。
    """
    base = root / _AUTO_PATHING_REL_DIR

    def build(dir_path: Path) -> dict:
        node: dict = {"name": dir_path.name, "dirs": [], "files": []}
        if not dir_path.is_dir():
            return node
        for child in sorted(dir_path.iterdir(), key=lambda p: p.name):
            if child.is_dir():
                node["dirs"].append(build(child))
            elif child.is_file() and child.suffix.lower() == ".json":
                rel = child.relative_to(base)
                rel_str = str(rel.with_suffix("")).replace("\\", "/")
                node["files"].append(rel_str)
        return node

    tree: list[dict] = []
    if base.is_dir():
        for child in sorted(base.iterdir(), key=lambda p: p.name):
            if child.is_dir():
                tree.append(build(child))
            # AutoPathing 根目录下均为分类目录；顶层散落的 json（极少数）直接并入虚拟节点展示
            elif child.is_file() and child.suffix.lower() == ".json":
                tree.append({"name": child.stem, "dirs": [], "files": [child.stem]})
    return str(base.resolve()), tree


def list_one_dragon_configs(root: Path) -> list[str]:
    """列出可选一条龙配置名：{RootPath}/User/OneDragon/*.json 的文件名。

    排除 MAS 运行时槽位「MAS独立配置」；始终把「默认配置」置顶（空名/首选的兜底）。
    实时扫描以反映 BGI 侧手工新增/删除的配置。
    """
    names: list[str] = []
    dragon_dir = root / _ONE_DRAGON_REL_DIR
    if dragon_dir.is_dir():
        for p in sorted(dragon_dir.glob("*.json"), key=lambda p: p.stem):
            name = p.stem.strip()
            if name and name != _MAS_ONE_DRAGON_SLOT_NAME and name not in names:
                names.append(name)
    names = [name for name in names if name != _DEFAULT_CONFIG_NAME]
    return [_DEFAULT_CONFIG_NAME] + names


def resolve_config_name(name: str) -> str:
    """解析一条龙配置名，空值显式兜底为「默认配置」。"""
    return (name or "").strip() or _DEFAULT_CONFIG_NAME


def launch_slot_name() -> str:
    """MAS 运行时专属槽位配置名（开启「用户独立配置」时据此启动一条龙）。"""
    return _MAS_ONE_DRAGON_SLOT_NAME


def one_dragon_slot_path(root: Path) -> Path:
    """MAS 运行时槽位配置文件的绝对路径（``{RootPath}/User/OneDragon/MAS独立配置.json``）。"""
    return one_dragon_path(root, _MAS_ONE_DRAGON_SLOT_NAME)


def _slot_owner_path(script_id: str) -> Path:
    """MAS 槽位占用标记：存在表示 ``{RootPath}/User/OneDragon/MAS独立配置.json``
    当前由 MAS 写入（运行时槽位），而非用户自己的同名配置。"""
    return Path.cwd() / "data" / script_id / ".mas_slot_owner"


def _slot_backup_path(script_id: str) -> Path:
    """写槽位前若该位置本是用户自己的同名配置，备份到此处；结束时恢复而非删除。"""
    return Path.cwd() / "data" / script_id / ".mas_slot_backup.json"


def remove_one_dragon_slot(root: Path, script_id: str) -> bool:
    """删除 MAS 运行时槽位配置（幂等）。返回是否确实存在并删除了。

    若写槽位前该位置本是用户自己的同名配置（已备份），则恢复原内容而非删除，
    避免 MAS 运行时槽位覆盖并删掉用户配置（#498 二.2 附带窄路径）。
    """
    slot_path = one_dragon_slot_path(root)
    owner_path = _slot_owner_path(script_id)
    backup_path = _slot_backup_path(script_id)
    if backup_path.exists():
        # 写槽位前这里是用户自己的配置：恢复原内容，不删除
        backup = read_file(backup_path)
        backup_path.unlink(missing_ok=True)
        if isinstance(backup, dict):
            write_one_dragon(root, _MAS_ONE_DRAGON_SLOT_NAME, backup)
        owner_path.unlink(missing_ok=True)
        return slot_path.exists()
    existed = slot_path.exists()
    slot_path.unlink(missing_ok=True)
    owner_path.unlink(missing_ok=True)
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
        {
            "name": str(item.get("name", "")).strip(),
            "enabled": bool(item.get("enabled", True)),
        }
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
        if name and name not in _BUILTIN_ONE_DRAGON_GROUPS and name not in seen:
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
    if not config or not isinstance(config, dict):
        # 缓存缺失/为空时（read_file 对不存在返回 {}）回退到 BGI 实配：否则种子退化为
        # 仅 8 个内置组的空模板，用户现有自定义配置组会整体丢失、重启后落到一条龙末尾。
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
    slot_path = one_dragon_slot_path(root)
    owner_path = _slot_owner_path(script_id)
    backup_path = _slot_backup_path(script_id)
    # 槽位原本存在且非 MAS 占用（用户自己的同名配置）：备份，结束时恢复而非删除
    if slot_path.exists() and not owner_path.exists():
        backup = read_file(slot_path)
        if isinstance(backup, dict):
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            write_file(backup_path, backup)
        else:
            backup_path.unlink(missing_ok=True)
    else:
        backup_path.unlink(missing_ok=True)
    write_one_dragon(root, _MAS_ONE_DRAGON_SLOT_NAME, config)
    owner_path.parent.mkdir(parents=True, exist_ok=True)
    owner_path.write_text(script_id, encoding="utf-8")
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
    with GLOBAL_CONFIG_LOCK:
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


def snapshot_global_battle_config(
    root: Path,
) -> dict[tuple[str, ...], tuple[bool, Any]]:
    """快照 config.json 本次可能改写的队伍/策略叶子路径，供结束还原。

    键为叶子路径元组，值为 ``(该叶子原本是否存在, 原值)``。
    """
    with GLOBAL_CONFIG_LOCK:
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


def restore_global_battle_config(
    root: Path, snapshot: dict[tuple[str, ...], tuple[bool, Any]]
) -> None:
    """把 config.json 的队伍/策略叶子路径还原为快照状态，消除单次运行残留。

    原本缺失则删除（沿路径清理变空字典），原本存在则回写原值；只改写本次动过的键。
    """
    if not snapshot:
        return
    with GLOBAL_CONFIG_LOCK:
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


# ---- 自动秘境「秘境刷取配置」：BetterGI 全局 config.json 段白名单 ----
# 领奖树脂设定 / 分解圣遗物 / 启用奖励识别 在 BGI 中存于全局 config.json
# （`autoDomainConfig` 段 + `autoArtifactSalvageConfig` 段，camelCase 键），
# 不属于 per-user 一条龙 JSON。此处只管理右栏「秘境刷取配置」标签暴露的白名单键，
# 其余同段字段（战斗延迟、移动方式等进阶项）不在右栏覆盖、原样保留。
# 结构: 段名(camelCase) -> 该段允许读写的叶子键 -> 类型转换函数(读/写用)。
_GLOBAL_DOMAIN_CONFIG_SEGMENT = "autoDomainConfig"
_GLOBAL_ARTIFACT_SALVAGE_SEGMENT = "autoArtifactSalvageConfig"

# 领奖树脂设定弹窗（SpecifyResinUse 模式开关）可编辑的 4 个次数
_GLOBAL_DOMAIN_RESIN_COUNT_KEYS = (
    "originalResinUseCount",
    "condensedResinUseCount",
    "transientResinUseCount",
    "fragileResinUseCount",
)
# 秘境刷取配置暴露的白名单（段名 -> 叶子键集合）
_GLOBAL_DOMAIN_SETTING_LEAVES: dict[str, frozenset[str]] = {
    _GLOBAL_DOMAIN_CONFIG_SEGMENT: frozenset(
        (
            "specifyResinUse",  # 模式切换：先用浓缩后原粹 / 按下方配置数量使用
            *_GLOBAL_DOMAIN_RESIN_COUNT_KEYS,
            "autoArtifactSalvage",  # 分解圣遗物开关
            "rewardRecognitionEnabled",  # 启用奖励识别
        )
    ),
    _GLOBAL_ARTIFACT_SALVAGE_SEGMENT: frozenset(("maxArtifactStar",)),  # 分解最高星级
}
# 扁平键（前端直接使用的小写键）→ 所属段
_GLOBAL_DOMAIN_LEAF_SEGMENT: dict[str, str] = {
    leaf: segment
    for segment, leaves in _GLOBAL_DOMAIN_SETTING_LEAVES.items()
    for leaf in leaves
}


def _coerce_domain_leaf(segment: str, key: str, value: Any) -> Any:
    """把 config.json 读出的值规整为前端可用类型（右栏渲染用）。"""
    if value is None:
        return None
    if segment == _GLOBAL_DOMAIN_CONFIG_SEGMENT and key == "specifyResinUse":
        return bool(value)
    if segment == _GLOBAL_DOMAIN_CONFIG_SEGMENT and key == "autoArtifactSalvage":
        return bool(value)
    if segment == _GLOBAL_DOMAIN_CONFIG_SEGMENT and key == "rewardRecognitionEnabled":
        return bool(value)
    if segment == _GLOBAL_DOMAIN_CONFIG_SEGMENT and key in _GLOBAL_DOMAIN_RESIN_COUNT_KEYS:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    return value


def read_global_domain_settings(root: Path) -> dict[str, Any]:
    """读取 BetterGI 全局 config.json 的秘境刷取配置白名单键（扁平键值对）。

    config.json 可能缺失整段（全新安装），此时返回默认值（false/0/"4"），
    避免前端对 undefined 渲染报错；缺失键也以默认值兜底。
    """
    default_values: dict[str, Any] = {
        "specifyResinUse": False,
        "originalResinUseCount": 0,
        "condensedResinUseCount": 0,
        "transientResinUseCount": 0,
        "fragileResinUseCount": 0,
        "autoArtifactSalvage": False,
        "rewardRecognitionEnabled": False,
        "maxArtifactStar": "4",
    }
    with GLOBAL_CONFIG_LOCK:
        config = read_file(_global_config_path(root))
    if not isinstance(config, dict):
        return dict(default_values)
    out = dict(default_values)
    for key in default_values:
        segment = _GLOBAL_DOMAIN_LEAF_SEGMENT[key]
        seg_data = config.get(segment)
        if isinstance(seg_data, dict) and key in seg_data:
            out[key] = _coerce_domain_leaf(segment, key, seg_data[key])
    return out


def write_global_domain_settings(root: Path, settings: dict[str, Any]) -> None:
    """把右栏秘境刷取配置写回 BetterGI 全局 config.json 的白名单键。

    只更新白名单叶子，保留同段其余字段（战斗延迟/移动等进阶项不受影响）；
    空 settings 不触写。写入值做类型规整（bool/int/str）以防前端字符串化误写。
    """
    if not settings:
        return
    with GLOBAL_CONFIG_LOCK:
        config = read_file(_global_config_path(root))
        if not isinstance(config, dict):
            config = {}
        changed = False
        for key, value in settings.items():
            segment = _GLOBAL_DOMAIN_LEAF_SEGMENT.get(key)
            if segment is None:
                continue  # 非白名单键直接忽略，避免污染 config.json
            seg_data = config.get(segment)
            if not isinstance(seg_data, dict):
                seg_data = {}
                config[segment] = seg_data
            if segment == _GLOBAL_ARTIFACT_SALVAGE_SEGMENT:
                norm = str(value) if value is not None else "4"
            elif segment == _GLOBAL_DOMAIN_CONFIG_SEGMENT and key in _GLOBAL_DOMAIN_RESIN_COUNT_KEYS:
                try:
                    norm = int(value)
                except (TypeError, ValueError):
                    norm = 0
            else:
                norm = bool(value)
            if seg_data.get(key) == norm:
                continue
            seg_data[key] = norm
            changed = True
        if changed:
            write_file(_global_config_path(root), config)


def snapshot_user_one_dragon(
    root: Path,
    script_id: str,
    user_id: str,
    config_name: str,
    read_name: str | None = None,
) -> None:
    """回读 BetterGI 现有一条龙配置为 per-user 副本（捕获 GUI 中改的设置）。

    ``read_name`` 指定实际读取的配置名：独立模式下用户编辑的是 MAS 槽位「MAS独立配置」，
    而 per-user 缓存 key 仍是用户所选名 ``config_name``，故读取源与缓存 key 解耦。
    缺省 ``read_name=None`` 时与 ``config_name`` 相同（直控/旧行为）。
    """
    config_name = resolve_config_name(config_name)
    source_name = resolve_config_name(read_name or config_name)
    config = load_one_dragon(root, source_name)
    if config:
        write_file(per_user_one_dragon_path(script_id, user_id, config_name), config)


# ---- 一条龙「设置项」白名单（右栏设置，可写回 per-user 副本；排除结构字段）----
# 结构与模板/BGI 一条龙 JSON 顶层键一致；新增 BGI 版本字段时在此追加即可。
_ONE_DRAGON_SETTING_KEYS: tuple[str, ...] = (
    "CraftingBenchCountry",
    "AdventurersGuildCountry",
    "MinResinToKeep",
    "PartyName",
    "DomainName",
    "WeeklyDomainEnabled",
    "AutoBossName",
    "AutoBossStrategyName",
    "AutoBossTeamName",
    "AutoBossSpecifyRunCount",
    "AutoBossRunCount",
    "AutoBossUseTransientResin",
    "AutoBossUseFragileResin",
    "AutoBossReviveRetryCount",
    "AutoBossReturnToStatueAfterEachRound",
    "AutoBossRewardRecognitionEnabled",
    "AutoBossTimeout",
    "DailyRewardPartyName",
    "SundayEverySelectedValue",
    "SundayWeeklySelectedValue",
    "SereniteaPotTpType",
    "SecretTreasureObjects",
    "LeyLineOneDragonMode",
    "LeyLineRunMonday",
    "LeyLineRunTuesday",
    "LeyLineRunWednesday",
    "LeyLineRunThursday",
    "LeyLineRunFriday",
    "LeyLineRunSaturday",
    "LeyLineRunSunday",
    "LeyLineMondayType",
    "LeyLineMondayCountry",
    "LeyLineTuesdayType",
    "LeyLineTuesdayCountry",
    "LeyLineWednesdayType",
    "LeyLineWednesdayCountry",
    "LeyLineThursdayType",
    "LeyLineThursdayCountry",
    "LeyLineFridayType",
    "LeyLineFridayCountry",
    "LeyLineSaturdayType",
    "LeyLineSaturdayCountry",
    "LeyLineSundayType",
    "LeyLineSundayCountry",
    "LeyLineRunCount",
    "LeyLineResinExhaustionMode",
    "LeyLineOpenModeCountMin",
    "MondayPartyName",
    "MondayDomainName",
    "MondaySelectedValue",
    "TuesdayPartyName",
    "TuesdayDomainName",
    "TuesdaySelectedValue",
    "WednesdayPartyName",
    "WednesdayDomainName",
    "WednesdaySelectedValue",
    "ThursdayPartyName",
    "ThursdayDomainName",
    "ThursdaySelectedValue",
    "FridayPartyName",
    "FridayDomainName",
    "FridaySelectedValue",
    "SaturdayPartyName",
    "SaturdayDomainName",
    "SaturdaySelectedValue",
    "SundayPartyName",
    "SundayDomainName",
    "SundaySelectedValue",
    "CompletionAction",
)
_ONE_DRAGON_SETTING_SET = frozenset(_ONE_DRAGON_SETTING_KEYS)


def _pick_settings(config: dict[str, Any]) -> dict[str, Any]:
    """从一条龙配置 dict 里抽取白名单设置项（含默认补全，前端渲染缺省值用）。"""
    base = _DEFAULT_SETTING_VALUES if _DEFAULT_SETTING_VALUES else {}
    out = dict(base)
    for key in _ONE_DRAGON_SETTING_KEYS:
        if key in config:
            out[key] = config[key]
    return out


# 设置项默认值（BGI 模板/合理缺省；运行时 per-user 副本缺失项用模板种子补齐）
_DEFAULT_SETTING_VALUES: dict[str, Any] = {}


def load_setting_defaults() -> dict[str, Any]:
    """按内置模板解析设置项默认值（模板缺失时不报错，仅返回白名单空键）。"""
    global _DEFAULT_SETTING_VALUES
    seed = load_seed_template()
    _DEFAULT_SETTING_VALUES = {
        key: seed.get(key)
        for key in _ONE_DRAGON_SETTING_KEYS
        if key in seed
    }
    return dict(_DEFAULT_SETTING_VALUES)


def read_user_one_dragon_settings(
    root: Path,
    script_id: str,
    user_id: str,
    config_name: str,
) -> dict[str, Any]:
    """读取某用户一条龙配置的设置项（右栏渲染）。

    种子顺序与 ``write_user_one_dragon`` 一致：per-user 副本 → BGI 实配 → 内置模板；
    副本未生成（用户尚未运行过）时以 BGI 实配/模板为准，保证右栏显示的是将生效的值。
    """
    config_name = resolve_config_name(config_name)
    config: dict[str, Any] = {}
    copy = read_file(per_user_one_dragon_path(script_id, user_id, config_name))
    if isinstance(copy, dict) and copy:
        config = copy
    else:
        config = load_one_dragon(root, config_name) or {}
    if not config:
        config = load_seed_template() or {}
    return _pick_settings(config)


def write_user_one_dragon_settings(
    root: Path,
    script_id: str,
    user_id: str,
    config_name: str,
    settings: dict[str, Any],
) -> None:
    """把右栏设置项写回 per-user 副本（不触碰 BGI 同名实配）。

    副本种子：per-user 副本 → BGI 实配 → 内置模板，仅覆盖白名单键并保留结构字段；
    运行时 ``write_user_one_dragon`` 以本副本为种子物化到 MAS 槽位，设置即生效。
    """
    config_name = resolve_config_name(config_name)
    config: dict[str, Any] = {}
    copy = read_file(per_user_one_dragon_path(script_id, user_id, config_name))
    if isinstance(copy, dict) and copy:
        config = copy
    else:
        config = load_one_dragon(root, config_name) or {}
    if not config:
        config = load_seed_template() or {}
    for key, value in (settings or {}).items():
        if key in _ONE_DRAGON_SETTING_SET:
            config[key] = value
    # 兜底：确保关键结构字段存在（minimal/空种子情况）
    if not config.get("TaskDefinitions") or not config.get("TaskOrder"):
        base = load_seed_template() or {}
        for struct_key in ("TaskEnabledList", "TaskOrder", "TaskDefinitions"):
            if struct_key not in config and struct_key in base:
                config[struct_key] = base[struct_key]
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
      覆盖自定义组启用状态：入表组按表状态、未入表（但 BetterGI 文件里存在）组保持原
      启用状态、入表且启用但配置缺失时补建。

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
                # 入表按表状态；未入表保持 BetterGI 原启用状态，避免误开用户已关闭的组
                new_enabled[uid] = (
                    custom_enabled[name]
                    if name in custom_enabled
                    else bool(old_enabled.get(uid, True))
                )
            else:
                new_enabled[uid] = bool(old_enabled.get(uid, True))

    # 兜底：未出现在 TaskOrder 的自定义组不丢失
    for uid, name in old_defs.items():
        if name and name not in _BUILTIN_ONE_DRAGON_GROUPS and uid not in new_defs:
            new_defs[uid] = name
            new_order.append(uid)
            if manage_customs:
                new_enabled[uid] = (
                    custom_enabled[name]
                    if name in custom_enabled
                    else bool(old_enabled.get(uid, True))
                )
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


# 模块加载时预解析设置项默认值（供右栏渲染缺省值）
load_setting_defaults()
