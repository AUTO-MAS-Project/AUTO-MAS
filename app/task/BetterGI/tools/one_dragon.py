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

「用户独立配置」模式下（``Info.IfUseMasConfig=True``）：
- 配置名固定为 MAS 专属槽位「MAS独立配置」，per-user 副本路径固定
  ``data/{script_id}/{user_id}/OneDragon/MAS独立配置.json``，BGI 同名实配全程零接触。
- 种子顺序为 per-user 副本 → 内置模板（不回退 BGI 实配，实配不是权威源）。
- 自定义配置组（per-user ScriptGroup 副本）在运行时以 ``MAS-{user短id}-{原名}`` 前缀名
  物化到 BGI ``User/ScriptGroup`` 并同步改写槽位 ``TaskDefinitions`` 引用；运行结束删除，
  BGI 本体目录平时保持干净（``remove_materialized_script_groups``）。
非独立模式（``IfUseMasConfig=False``）保持直控 BGI 所选实配，本模块的独立槽位逻辑不生效。
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


def _validate_script_id(script_id: str) -> str:
    """校验脚本 ID 可安全拼入 ``data/`` 相对路径：必须是合法 UUID。

    返回 strip 后的 ``script_id``；不合法抛 ``ValueError``（防目录穿越/越权读写）。
    """
    value = str(script_id or "").strip()
    try:
        uuid.UUID(value)
    except ValueError as e:
        raise ValueError(f"非法的脚本 ID: {script_id!r}") from e
    return value


def _validate_user_id(user_id: str) -> str:
    """校验用户 ID 可安全拼入 ``data/`` 相对路径：必须是合法 UUID。

    MAS 的 BetterGI 用户 id 恒为 UUID；不合法抛 ``ValueError``
    （防目录穿越/越权读写其他用户或脚本目录）。
    """
    value = str(user_id or "").strip()
    try:
        uuid.UUID(value)
    except ValueError as e:
        raise ValueError(f"非法的用户 ID: {user_id!r}") from e
    return value


def _validate_file_stem(name: str) -> str:
    """校验配置名可安全作为文件名主干：不含路径分隔符/盘符/``..``。

    返回 strip 后的名字；不合法抛 ``ValueError``（configName 来自前端请求，
    需防 ``../`` 等穿越出 per-user 目录）。
    """
    value = str(name or "").strip()
    if not value or any(ch in value for ch in ("/", "\\", ":")) or ".." in value:
        raise ValueError(f"非法的配置名: {name!r}")
    return value


def per_user_script_group_path(script_id: str, user_id: str, name: str) -> Path:
    """某用户的配置组 json 副本路径 ``data/{script_id}/{user_id}/ScriptGroup/{name}.json``。

    BetterGI 的配置组（``User/ScriptGroup/*.json``）是 BGI 全局共享文件；在「用户独立
    配置」语义下，MAS 把该用户对配置组的编辑（项目顺序 / 各项目 jsScriptSettingsObject）
    落在 per-user 副本，BGI 同名实配全程零接触（种子：per-user 副本 → BGI 实配）。
    """
    return (
        Path.cwd()
        / "data"
        / _validate_script_id(script_id)
        / _validate_user_id(user_id)
        / "ScriptGroup"
        / f"{_validate_file_stem(resolve_script_group_name(name))}.json"
    )


def list_user_script_group_names(script_id: str, user_id: str) -> list[str]:
    """列出某用户 per-user ScriptGroup 副本的文件名（不含 ``.json``）。

    副本是 MAS 在「用户独立配置」语义下保存的用户编辑内容，与 BGI 实配目录
    （``User/ScriptGroup/*.json``）相对独立；前端把两者并集视为「该用户可编辑的
    配置组」，据此把复制自 JS/路径等来源的自建副本识别为 scriptgroup 行。
    """
    names: list[str] = []
    sg_dir = per_user_script_group_path(script_id, user_id, "_").parent
    if sg_dir.is_dir():
        for p in sorted(sg_dir.glob("*.json"), key=lambda p: p.stem):
            name = p.stem.strip()
            if name and name not in names:
                names.append(name)
    return names


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
    当前由 MAS 写入（运行时槽位），而非用户自己的同名配置。

    ⚠️ 前提：同一脚本同一时刻至多一个 BetterGI 任务在运行（调度与使用方式保证），
    owner/backup 因此只按脚本维度记录；若未来允许同脚本并发任务，槽位/备份/
    前缀物化/全局叶子快照会产生竞态，需按任务维度隔离。
    """
    return Path.cwd() / "data" / _validate_script_id(script_id) / ".mas_slot_owner"


def _slot_backup_path(script_id: str) -> Path:
    """写槽位前若该位置本是用户自己的同名配置，备份到此处；结束时恢复而非删除。"""
    return Path.cwd() / "data" / _validate_script_id(script_id) / ".mas_slot_backup.json"


def remove_one_dragon_slot(root: Path, script_id: str) -> bool:
    """删除 MAS 运行时槽位配置（幂等）。返回是否确实存在并删除了。

    仅当槽位确为 MAS 本轮写入时删除（owner 标记或写前备份存在）；若两标记都不存在，
    说明该位置是用户自己的同名配置（本轮未物化），一律保留不触碰，避免误删用户文件。
    若写槽位前该位置本是用户自己的同名配置（已备份到 ``_slot_backup_path``），
    则恢复原内容而非删除（#498 二.2 附带窄路径）。
    """
    slot_path = one_dragon_slot_path(root)
    owner_path = _slot_owner_path(script_id)
    backup_path = _slot_backup_path(script_id)
    if not owner_path.exists() and not backup_path.exists():
        # 本轮未物化过：该文件属于用户自己（或本不存在），不删除
        return False
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


def parse_one_dragon_queue(raw: Any) -> list[dict[str, str]]:
    """解析前端保存的一条龙队列 JSON（字符串或已是列表），非法时返回空列表。

    元素归一为 ``{"kind", "name"}``：``name`` 命中内置 8 组时 ``kind`` 强制为
    ``builtin``，否则保留前端给的 kind（js/pathing/scriptgroup/custom，仅供展示，
    运行时统一按自定义组名处理）。空名与非字典项丢弃；**允许同名条目重复**
    （对应可视化队列的重复实例，每个实例是独立 uid）。
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
    out: list[dict[str, str]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        if not name:
            continue
        if name in _BUILTIN_ONE_DRAGON_GROUPS:
            kind = "builtin"
        else:
            kind = str(item.get("kind", "")).strip()
            if kind not in ("js", "pathing", "scriptgroup", "custom"):
                kind = "custom"
        out.append({"kind": kind, "name": name})
    return out


def _custom_groups_from_config(config: dict[str, Any]) -> list[dict[str, Any]]:
    """从一条龙配置 dict 抽取自定义配置组（非内置 8 组），按 ``TaskOrder`` 相对顺序。"""
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


def list_custom_groups(root: Path, config_name: str) -> list[dict[str, Any]]:
    """列出某一条龙配置（BGI 实配）里的自定义配置组。

    供「非独立模式」/直控场景读取 BGI 现有配置返回
    ``[{"name": ..., "enabled": ...}, ...]``。
    """
    return _custom_groups_from_config(load_one_dragon(root, config_name))


def list_user_custom_groups(
    root: Path, script_id: str, user_id: str, config_name: str
) -> list[dict[str, Any]]:
    """列出某用户 per-user 一条龙副本里的自定义配置组（独立模式权威源）。

    读取源与 ``read_user_one_dragon_settings`` 一致（副本 → 内置模板），
    保证表格展示的是将写入槽位的组（含自定义组开关状态）。
    """
    return _custom_groups_from_config(
        _seed_user_one_dragon_config(root, script_id, user_id, config_name)
    )


def one_dragon_path(root: Path, name: str) -> Path:
    """一条龙配置文件的绝对路径。"""
    return root / _ONE_DRAGON_REL_DIR / f"{_validate_file_stem(resolve_config_name(name))}.json"


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
        / _validate_script_id(script_id)
        / _validate_user_id(user_id)
        / "OneDragon"
        / f"{_validate_file_stem(resolve_config_name(config_name))}.json"
    )


def _mas_user_short_id(user_id: str) -> str:
    """用户短标识：取 UUID 十六进制前 8 位，供物化文件名前缀避让使用。"""
    short = (user_id or "").replace("-", "")[:8]
    return short or "user"


def materialize_user_script_groups(
    root: Path,
    script_id: str,
    user_id: str,
    config: dict[str, Any],
) -> list[Path]:
    """把用户独立配置的自定义配置组物化到 BGI User/ScriptGroup（前缀避让）。

    仅物化**存在 per-user ScriptGroup 副本**（``data/{script}/{user}/ScriptGroup/{原名}.json``）
    的组：以 ``MAS-{user短id}-{原名}.json`` 写入 BGI，并把 ``config`` 的
    ``TaskDefinitions`` 中该组引用同步改写为前缀名。BGI 原有同名文件零接触
    （前缀不同绝不覆盖）。无副本的组（引用 BGI 已有配置组 / JS 脚本 / 路径等）
    原样保留名字，交由 BGI 自身解析。

    Returns:
        本次物化写入的文件路径列表（供运行结束删除）。
    """
    created: list[Path] = []
    defs = config.get("TaskDefinitions")
    if not isinstance(defs, dict):
        return created
    rename: dict[str, str] = {}
    seen: set[str] = set()
    for name in defs.values():
        if not isinstance(name, str) or not name:
            continue
        if name in _BUILTIN_ONE_DRAGON_GROUPS or name in seen:
            continue
        seen.add(name)
        copy = read_file(per_user_script_group_path(script_id, user_id, name))
        if not (isinstance(copy, dict) and copy):
            continue  # 无 MAS 副本：引用 BGI 已有组/JS/路径，原样保留
        prefixed = f"MAS-{_mas_user_short_id(user_id)}-{name}"
        copy["name"] = prefixed
        out_path = root / _SCRIPT_GROUP_REL_DIR / f"{prefixed}.json"
        write_file(out_path, copy)
        created.append(out_path)
        rename[name] = prefixed
    if rename:
        for uid, name in defs.items():
            if isinstance(name, str) and name in rename:
                defs[uid] = rename[name]
    return created


def remove_materialized_script_groups(root: Path, created: list[Path]) -> None:
    """删除本次运行物化到 BGI User/ScriptGroup 的前缀组文件（幂等）。"""
    for p in created or []:
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


def cleanup_leftover_mas_groups(root: Path, script_id: str, user_id: str) -> int:
    """清理该用户历史残留的 MAS 物化配置组文件（``User/ScriptGroup/MAS-{短id}-*.json``）。

    进程被强杀等异常场景会留下前缀物化文件（无 owner 标记可循），此函数按用户短 id
    前缀扫描删除，只命中 MAS 专属前缀，绝不触碰 BGI 本体文件。返回删除数量。

    ⚠️ 前提：同一脚本同一时刻至多一个 BetterGI 任务在运行；并发任务下此清理会删掉
    其他运行实例正在使用的物化文件（见 ``_slot_owner_path`` 的说明）。
    """
    short = _mas_user_short_id(user_id)
    removed = 0
    sg_dir = root / _SCRIPT_GROUP_REL_DIR
    if sg_dir.is_dir():
        for p in sg_dir.glob(f"MAS-{short}-*.json"):
            try:
                p.unlink(missing_ok=True)
                removed += 1
            except OSError:
                pass
    return removed


def write_user_one_dragon(
    root: Path,
    script_id: str,
    user_id: str,
    groups: list[str],
    daily_reward_party_name: str = "",
    party_name: str = "",
    auto_boss_strategy_name: str = "",
    custom_groups: list[dict[str, Any]] | None = None,
    manage_custom_groups: bool = False,
    queue: list[dict[str, Any]] | None = None,
) -> list[Path]:
    """把组开关与队伍/策略设置应用到一条龙配置，写入 BGI 运行时槽位并缓存 per-user 副本。

    ⚠️ 前提：同一脚本同一时刻至多一个 BetterGI 任务在运行（调度与使用方式保证）；
    槽位/owner/backup/前缀物化组/全局 config.json 叶子快照均按脚本维度共享，
    若未来允许同脚本并发任务，需先按任务维度隔离（见 ``_slot_owner_path``）。

    仅「用户独立配置」模式（``IfUseMasConfig=True``）调用；配置名固定为
    「MAS独立配置」：
    - per-user 副本固定 ``data/{script}/{user}/OneDragon/MAS独立配置.json``；
    - 种子优先级：per-user 副本 → 内置模板（**不回退 BGI 实配**，BGI 同名实配零接触，
      首次启用按纯内置模板开始，历史副本不再生效但保留在磁盘）；
    - 物化结果写入 MAS 专属槽位 ``{RootPath}/User/OneDragon/MAS独立配置.json``（据此启动，
      运行后由 ``remove_one_dragon_slot`` 删除）；
    - 入列的自定义配置组（含禁用，凡在 per-user ScriptGroup 副本中有定义的组）一并
      以 ``MAS-{短id}-{原名}`` 前缀物化到 BGI ``User/ScriptGroup``，并同步改写槽位
      ``TaskDefinitions`` 引用；BGI 本体原有同名文件绝不覆盖。

    非组字段（领取奖励队伍/战斗队伍/战斗策略）作为**运行时覆盖层**：仅在非空时写入
    BGI 槽位（留空则保持 BetterGI 现有设置），**只物化到槽位、不回写 per-user 副本**
    ——否则曾填写过的值会沉淀在副本中，之后清空（留空）仍被当作旧值继续执行，无法
    回退到 BetterGI 现有设置。其中「战斗队伍/战斗策略」会落到秘境 ``PartyName`` 与
    首领讨伐的 ``AutoBossTeamName`` / ``AutoBossStrategyName``（秘境策略仍走全局
    ``autoFightConfig``）；地脉花/幽境危战/以及秘境策略另外经
    ``apply_global_battle_team`` / ``apply_global_battle_strategy`` 补写全局 config.json
    （同样只在非空时写，留空保留 BGI 现有值）。
    ``manage_custom_groups`` 开启时按 ``custom_groups``（name→enabled）管理自定义组，
    否则自定义组原样保留（由 BetterGI 内部决定）。

    Returns:
        本次物化到 BGI 的配置组文件路径列表（供调用方在运行结束后
        ``remove_materialized_script_groups`` + ``remove_one_dragon_slot`` 清理）。
    """
    config_name = _MAS_ONE_DRAGON_SLOT_NAME
    user_path = per_user_one_dragon_path(script_id, user_id, config_name)

    config = read_file(user_path)
    if not config or not isinstance(config, dict):
        # 缓存缺失/为空：以纯内置模板开始（不回退 BGI 实配，实配不是权威源）
        config = load_seed_template()

    config = apply_groups(
        config,
        groups,
        custom_groups=custom_groups,
        manage_customs=manage_custom_groups,
        queue=queue,
    )
    # 副本只保存一条龙结构与组开关（不含顶部快捷覆盖，避免清空后残留旧值）
    write_file(user_path, config)
    slot_config = dict(config)
    # 顶部快捷覆盖只作用于运行时槽位：非空才写，留空则槽位维持副本（BetterGI 现有）值
    if daily_reward_party_name:
        slot_config["DailyRewardPartyName"] = daily_reward_party_name
    if party_name:
        slot_config["PartyName"] = party_name
        # 一条龙自动首领讨伐从 AutoBossTeamName 取队伍（OneDragonTaskItem.cs）
        slot_config["AutoBossTeamName"] = party_name
    if auto_boss_strategy_name:
        slot_config["AutoBossStrategyName"] = auto_boss_strategy_name

    materialized = materialize_user_script_groups(root, script_id, user_id, slot_config)

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
    write_one_dragon(root, _MAS_ONE_DRAGON_SLOT_NAME, slot_config)
    owner_path.parent.mkdir(parents=True, exist_ok=True)
    owner_path.write_text(script_id, encoding="utf-8")
    return materialized


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
        for leaf in _ALL_RUNTIME_GLOBAL_LEAVES:
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
        for leaf in _ALL_RUNTIME_GLOBAL_LEAVES:
            existed, value = snapshot.get(leaf, (False, None))
            if _restore_leaf(config, leaf, existed, value):
                changed = True
        if changed:
            for leaf in _ALL_RUNTIME_GLOBAL_LEAVES:
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
# domain 白名单叶子（段名, 键）二元组：运行时按用户物化后需随队伍/策略一起快照还原
_GLOBAL_DOMAIN_LEAVES: tuple[tuple[str, str], ...] = tuple(
    (segment, key)
    for segment, keys in _GLOBAL_DOMAIN_SETTING_LEAVES.items()
    for key in keys
)
# ---- 自动幽境危战「刷取策略 / 次数与树脂」：BetterGI 全局 config.json 段白名单 ----
# BGI 中 autoStygianOnslaughtConfig 段（camelCase 键）承载幽境危战的刷取战场（bossNum）、
# 战斗队伍（fightTeamName）、战斗策略（strategyName）与树脂消耗策略。与「自动秘境」
# 的 globalDomain 机制一致：右栏幽境面板的键存于 per-user 副本，运行时物化到 BGI 全局
# config.json 的 autoStygianOnslaughtConfig 段（运行结束快照还原）。
# 其中 fightTeamName/strategyName 的叶子已由 _GLOBAL_TEAM_LEAVES / _GLOBAL_STRATEGY_LEAVES
# 纳入快照（顶部「通用战斗队伍/策略」在非空时覆盖这两个键；留空则保留面板/BGI 现有值），
# 故本段补充快照的叶子只需其余独有键；白名单（副本读写）则含全部面板键。
_GLOBAL_STYGIAN_SEGMENT = "autoStygianOnslaughtConfig"
# 幽境面板「次数与树脂」可编辑的树脂次数（与 domain 段同键，但分属不同段）
_GLOBAL_STYGIAN_RESIN_COUNT_KEYS = (
    "originalResinUseCount",
    "condensedResinUseCount",
    "transientResinUseCount",
    "fragileResinUseCount",
)
# 幽境面板暴露的白名单键（扁平，与副本存储一致）
_GLOBAL_STYGIAN_SETTING_KEYS: frozenset[str] = frozenset(
    (
        "bossNum",  # 刷取战场：1/2/3
        "fightTeamName",  # 战斗队伍
        "strategyName",  # 战斗策略
        "specifyResinUse",  # false=刷取至树脂耗尽 / true=按下方指定次数
        "autoArtifactSalvage",  # 任务结束后自动分解圣遗物
        *_GLOBAL_STYGIAN_RESIN_COUNT_KEYS,
    )
)
# 幽境段需随运行快照还原的叶子（fightTeamName/strategyName 已含在 _ALL_GLOBAL_LEAVES）
_GLOBAL_STYGIAN_EXTRA_LEAVES: tuple[tuple[str, str], ...] = tuple(
    (_GLOBAL_STYGIAN_SEGMENT, key)
    for key in sorted(_GLOBAL_STYGIAN_SETTING_KEYS)
    if key not in ("fightTeamName", "strategyName")
)
# 运行时临时补写并需快照/还原的 config.json 叶子全集 = 队伍/策略 + 秘境刷取 + 幽境
_ALL_RUNTIME_GLOBAL_LEAVES = (
    _ALL_GLOBAL_LEAVES + _GLOBAL_DOMAIN_LEAVES + _GLOBAL_STYGIAN_EXTRA_LEAVES
)


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


def per_user_global_domain_path(script_id: str, user_id: str) -> Path:
    """某用户的秘境刷取配置副本路径 ``data/{script_id}/{user_id}/GlobalDomain/settings.json``。

    BGI 的秘境刷取段（``autoDomainConfig`` / ``autoArtifactSalvageConfig``）存在于全局
    ``config.json``，本身是脚本级共享；在「用户独立配置」语义下，MAS 把该用户编辑的
    白名单值落在 per-user 副本，运行时才物化到 BGI 全局 config.json（运行结束还原），
    使不同用户的秘境刷取设置互不覆盖。
    """
    return (
        Path.cwd()
        / "data"
        / _validate_script_id(script_id)
        / _validate_user_id(user_id)
        / "GlobalDomain"
        / "settings.json"
    )


def read_user_global_domain_settings(
    root: Path, script_id: str, user_id: str
) -> dict[str, Any]:
    """读取某用户的秘境刷取配置（per-user 副本为权威源，缺失键兜底 BGI 全局/默认）。

    以 BGI 全局实配（含默认值兜底）为底稿，再用该用户副本覆盖其上：副本缺失/为空时
    结果即 BGI 现状（首次展示反映实配）；副本键值优先（用户保存后的隔离值），新增白名单
    键在未保存前仍回退全局，避免旧副本缺键导致前端 undefined。
    """
    base = read_global_domain_settings(root)
    copy = read_file(per_user_global_domain_path(script_id, user_id))
    if isinstance(copy, dict) and copy:
        base.update({k: v for k, v in copy.items() if k in _GLOBAL_DOMAIN_LEAF_SEGMENT})
    return base


def write_user_global_domain_settings(
    script_id: str, user_id: str, settings: dict[str, Any]
) -> Path:
    """把右栏秘境刷取配置写回 per-user 副本（不触碰 BGI 全局 config.json）。

    只保留白名单扁平键；运行时 ``apply_user_global_domain_settings`` 负责物化到 BGI。
    """
    out: dict[str, Any] = {}
    for key, value in (settings or {}).items():
        if key in _GLOBAL_DOMAIN_LEAF_SEGMENT:
            out[key] = value
    out_path = per_user_global_domain_path(script_id, user_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_file(out_path, out)
    return out_path


def apply_user_global_domain_settings(
    root: Path, script_id: str, user_id: str
) -> bool:
    """把某用户 per-user 副本的秘境刷取配置物化到 BGI 全局 config.json。

    仅在副本存在且非空时写入；写入前调用方应已快照（``snapshot_global_battle_config``
    现在覆盖 domain 白名单叶子），运行结束后由 ``restore_global_battle_config`` 还原。
    返回是否实际触写了 BGI config.json。
    """
    copy = read_file(per_user_global_domain_path(script_id, user_id))
    if not (isinstance(copy, dict) and copy):
        return False
    write_global_domain_settings(root, copy)
    return True


# ---- 自动幽境危战（autoStygianOnslaughtConfig 段）读写 ----
# 段默认值（与 BGI AutoStygianOnslaughtConfig.cs 一致）：刷取战场默认 1、次数均为 0、
# 开关均为 false、队伍/策略留空（空值不覆盖 BGI 现有/顶部通用值）。
def _default_stygian_settings() -> dict[str, Any]:
    return {
        "bossNum": 1,
        "fightTeamName": "",
        "strategyName": "",
        "specifyResinUse": False,
        "autoArtifactSalvage": False,
        "originalResinUseCount": 0,
        "condensedResinUseCount": 0,
        "transientResinUseCount": 0,
        "fragileResinUseCount": 0,
    }


def _coerce_stygian_leaf(key: str, value: Any) -> Any:
    """把 config.json 读出的幽境段值规整为前端可用类型（右栏渲染用）。"""
    if value is None:
        return None
    if key == "bossNum":
        try:
            return int(value)
        except (TypeError, ValueError):
            return 1
    if key in _GLOBAL_STYGIAN_RESIN_COUNT_KEYS:
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0
    if key in ("specifyResinUse", "autoArtifactSalvage"):
        return bool(value)
    return value


def read_global_stygian_settings(root: Path) -> dict[str, Any]:
    """读取 BetterGI 全局 config.json 的幽境危战段白名单键（扁平键值对）。

    config.json 可能缺失整段（全新安装），此时返回默认值（bossNum=1/false/0），
    避免前端对 undefined 渲染报错；缺失键也以默认值兜底。
    """
    defaults = _default_stygian_settings()
    with GLOBAL_CONFIG_LOCK:
        config = read_file(_global_config_path(root))
    if not isinstance(config, dict):
        return defaults
    out = dict(defaults)
    seg_data = config.get(_GLOBAL_STYGIAN_SEGMENT)
    if isinstance(seg_data, dict):
        for key in defaults:
            if key in seg_data:
                out[key] = _coerce_stygian_leaf(key, seg_data[key])
    return out


def write_global_stygian_settings(root: Path, settings: dict[str, Any]) -> None:
    """把右栏幽境危战设置写回 BetterGI 全局 config.json 的 autoStygianOnslaughtConfig 段。

    只更新白名单叶子，保留同段其余字段；空 settings 不触写。
    - 队伍/策略留空（空串/纯空白）不写入：保留 BGI 现有值 / 由顶部通用字段接管；
    - 其余键做类型规整（int/bool），防止前端字符串化误写。
    """
    if not settings:
        return
    with GLOBAL_CONFIG_LOCK:
        config = read_file(_global_config_path(root))
        if not isinstance(config, dict):
            config = {}
        seg_data = config.get(_GLOBAL_STYGIAN_SEGMENT)
        if not isinstance(seg_data, dict):
            seg_data = {}
            config[_GLOBAL_STYGIAN_SEGMENT] = seg_data
        changed = False
        for key, value in settings.items():
            if key not in _GLOBAL_STYGIAN_SETTING_KEYS:
                continue  # 非白名单键直接忽略，避免污染 config.json
            if key in ("fightTeamName", "strategyName"):
                text = str(value or "").strip()
                if not text:
                    continue  # 留空不覆盖 BGI 现有/顶部通用值
                norm: Any = text
            elif key == "bossNum":
                try:
                    norm = int(value)
                except (TypeError, ValueError):
                    norm = 1
            elif key in _GLOBAL_STYGIAN_RESIN_COUNT_KEYS:
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


def per_user_global_stygian_path(script_id: str, user_id: str) -> Path:
    """某用户的幽境危战配置副本路径 ``data/{script_id}/{user_id}/GlobalStygian/settings.json``。

    语义同 ``per_user_global_domain_path``：BGI 的幽境段存于全局 config.json（脚本级共享），
    「用户独立配置」下 MAS 把该用户编辑的白名单值落在 per-user 副本，运行时才物化到 BGI
    （运行结束还原），使不同用户的幽境设置互不覆盖。
    """
    return (
        Path.cwd()
        / "data"
        / _validate_script_id(script_id)
        / _validate_user_id(user_id)
        / "GlobalStygian"
        / "settings.json"
    )


def read_user_global_stygian_settings(
    root: Path, script_id: str, user_id: str
) -> dict[str, Any]:
    """读取某用户的幽境危战设置（per-user 副本为权威源，缺失键兜底 BGI 全局/默认）。"""
    base = read_global_stygian_settings(root)
    copy = read_file(per_user_global_stygian_path(script_id, user_id))
    if isinstance(copy, dict) and copy:
        base.update(
            {k: v for k, v in copy.items() if k in _GLOBAL_STYGIAN_SETTING_KEYS}
        )
    return base


def write_user_global_stygian_settings(
    script_id: str, user_id: str, settings: dict[str, Any]
) -> Path:
    """把右栏幽境危战设置写回 per-user 副本（不触碰 BGI 全局 config.json）。

    只保留白名单扁平键；运行时 ``apply_user_global_stygian_settings`` 负责物化到 BGI。
    """
    out: dict[str, Any] = {}
    for key, value in (settings or {}).items():
        if key in _GLOBAL_STYGIAN_SETTING_KEYS:
            out[key] = value
    out_path = per_user_global_stygian_path(script_id, user_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    write_file(out_path, out)
    return out_path


def apply_user_global_stygian_settings(
    root: Path, script_id: str, user_id: str
) -> bool:
    """把某用户 per-user 副本的幽境危战设置物化到 BGI 全局 config.json。

    仅在副本存在且非空时写入；写入前调用方应已快照（``snapshot_global_battle_config``
    现在覆盖幽境白名单叶子），运行结束后由 ``restore_global_battle_config`` 还原。
    返回是否实际触写了 BGI config.json。
    """
    copy = read_file(per_user_global_stygian_path(script_id, user_id))
    if not (isinstance(copy, dict) and copy):
        return False
    write_global_stygian_settings(root, copy)
    return True


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


def _seed_user_one_dragon_config(
    root: Path,
    script_id: str,
    user_id: str,
    config_name: str,
) -> dict[str, Any]:
    """读取用户一条龙配置的种子：per-user 副本优先。

    - 固定槽位名（MAS独立配置，用户独立模式）：副本缺失时以纯内置模板开始，
      不回退 BGI 实配（实配不是权威源，避免把 BGI 同名用户配置当底稿）。
    - 其它配置名（非独立模式直控）：副本缺失时回退 BGI 实配 → 内置模板（旧行为）。
    """
    config_name = resolve_config_name(config_name)
    config: dict[str, Any] = {}
    copy = read_file(per_user_one_dragon_path(script_id, user_id, config_name))
    if isinstance(copy, dict) and copy:
        config = copy
    elif config_name == _MAS_ONE_DRAGON_SLOT_NAME:
        config = {}
    else:
        config = load_one_dragon(root, config_name) or {}
    if not config:
        config = load_seed_template() or {}
    return config


def read_user_one_dragon_settings(
    root: Path,
    script_id: str,
    user_id: str,
    config_name: str,
) -> dict[str, Any]:
    """读取某用户一条龙配置的设置项（右栏渲染）。

    种子顺序与 ``write_user_one_dragon`` 一致（见 ``_seed_user_one_dragon_config``）；
    独立模式固定名副本缺失时以内置模板为准，保证右栏显示的是将生效的值。
    """
    return _pick_settings(_seed_user_one_dragon_config(root, script_id, user_id, config_name))


def write_user_one_dragon_settings(
    root: Path,
    script_id: str,
    user_id: str,
    config_name: str,
    settings: dict[str, Any],
) -> None:
    """把右栏设置项写回 per-user 副本（不触碰 BGI 同名实配）。

    副本种子见 ``_seed_user_one_dragon_config``：独立模式固定名副本缺失时以纯内置模板
    为底稿，仅覆盖白名单键并保留结构字段；运行时 ``write_user_one_dragon`` 以本副本为
    种子物化到 MAS 槽位，设置即生效。
    """
    config = _seed_user_one_dragon_config(root, script_id, user_id, config_name)
    for key, value in (settings or {}).items():
        if key in _ONE_DRAGON_SETTING_SET:
            config[key] = value
    # 兜底：确保关键结构字段存在（minimal/空种子情况）
    if not config.get("TaskDefinitions") or not config.get("TaskOrder"):
        base = load_seed_template() or {}
        for struct_key in ("TaskEnabledList", "TaskOrder", "TaskDefinitions"):
            if struct_key not in config and struct_key in base:
                config[struct_key] = base[struct_key]
    config_name = resolve_config_name(config_name)
    write_file(per_user_one_dragon_path(script_id, user_id, config_name), config)


def apply_groups(
    config: dict[str, Any],
    enabled: list[str],
    custom_groups: list[dict[str, Any]] | None = None,
    manage_customs: bool = False,
    queue: list[dict[str, Any]] | None = None,
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

    队列顺序（可视化编排）：``queue`` 非空时（``parse_one_dragon_queue`` 的产物）按其
    顺序重建 ``TaskOrder``/``TaskDefinitions``——每个队列条目生成独立 uid（同名条目即
    重复实例），内置组 enabled 取按钮开关、自定义组 enabled 取管理表/旧状态；不在队列
    里的旧自定义组兜底追加到末尾，避免静默丢失。``queue`` 为空/非法时保持旧行为
    （沿用副本 ``TaskOrder`` 相对顺序，不重排）。

    应用到当前运行的配置（``Name`` 指向哪个就写哪个），不局限于某一份命名。

    Args:
        config: 一条龙配置 dict（可为空 ``{}``）。
        enabled: 按钮打开的 8 个内置组名列表。
        custom_groups: 自定义配置组管理列表（name→enabled），仅 ``manage_customs`` 时使用。
        manage_customs: 是否管理自定义组开关。
        queue: 可视化队列（有序条目），见 ``parse_one_dragon_queue``；空时回退旧行为。

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
    # name -> (首个旧 uid, 旧启用状态)：队列模式按名取旧启用状态
    old_by_name: dict[str, tuple[str, bool]] = {}
    for uid in old_order:
        name = name_by_uid.get(uid)
        if name and name not in old_by_name:
            old_by_name[name] = (uid, bool(old_enabled.get(uid, True)))

    def _custom_enabled_for(name: str) -> bool:
        old = old_by_name.get(name)
        old_on = bool(old[1]) if old else True
        if manage_customs:
            # 入表按表状态；未入表保持 BetterGI 原启用状态，避免误开用户已关闭的组
            return custom_enabled[name] if name in custom_enabled else old_on
        return old_on

    queue_entries = [e for e in (queue or []) if isinstance(e, dict)]
    new_defs: dict[str, str] = {}
    new_order: list[str] = []
    new_enabled: dict[str, bool] = {}
    present_builtin: set[str] = set()

    if queue_entries:
        # 队列模式：按可视化队列顺序重建（允许同名重复实例，各占独立 uid）
        for entry in queue_entries:
            name = str(entry.get("name") or "").strip()
            if not name:
                continue
            uid = str(uuid.uuid4())
            new_defs[uid] = name
            new_order.append(uid)
            if name in _BUILTIN_ONE_DRAGON_GROUPS:
                present_builtin.add(name)
                new_enabled[uid] = name in selected_set
            else:
                new_enabled[uid] = _custom_enabled_for(name)
    else:
        # 旧行为：单遍扫描旧顺序，内置组按按钮开关置 enabled，自定义组按管理表/原样保留
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
                new_enabled[uid] = _custom_enabled_for(name)

    # 兜底：不在队列/旧顺序里的自定义组不丢失（按名去重，追加到末尾）
    covered_names = set(new_defs.values())
    for uid, name in old_defs.items():
        if (
            name
            and name not in _BUILTIN_ONE_DRAGON_GROUPS
            and name not in covered_names
        ):
            covered_names.add(name)
            new_defs[uid] = name
            new_order.append(uid)
            new_enabled[uid] = _custom_enabled_for(name)

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
