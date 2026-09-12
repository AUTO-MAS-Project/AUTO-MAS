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
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""BetterGI 一条龙：路径 B「MAS 自编排执行层」配置组与脚本资产渲染。

复用切号通道（``account_switch``）的成熟做法：把 Plan 写进配置组 ``MAS一条龙``
的 ``projects[0].jsScriptSettingsObject``，脚本本体（``MASOneDragon``）经
``User/JsScript/MASOneDragon`` 运行，由 ``BetterGI.exe --startGroups MAS一条龙``
单独执行。战斗 4 项在此直连执行层；日常 4 项由随后的一条龙（已过滤掉战斗 4 项）
承接，避免重复执行。
"""

from __future__ import annotations

import json
from contextlib import suppress
from pathlib import Path
from shutil import copy2
from typing import Any

from app.utils import get_logger, resource_path
from app.utils.io import read_file, write_file

from .one_dragon import _mas_user_short_id, resolve_custom_group
from .one_dragon_plan import resolve_base_name

logger = get_logger("BetterGI 一条龙执行层")

GROUP_NAME = "MAS一条龙"
SCRIPT_FOLDER_NAME = "MASOneDragon"

_GROUP_REL_DIR = Path("User") / "ScriptGroup"
_JS_SCRIPT_REL_DIR = Path("User") / "JsScript"
_RES_TEMPLATE_DIR = resource_path("templates", "BetterGI")
_SCRIPT_ASSET_DIR = _RES_TEMPLATE_DIR / "MASOneDragon"

# 执行层「段」配置组在 BGI 列表里的 index 基准（固定高位，避免与用户配置组插队）。
_SEGMENT_INDEX_BASE = 890

# 内置战斗 4 项（路径 B 下由本配置组直连执行层；其余由随后一条龙承接）
BUILTIN_COMBAT_STEPS: frozenset[str] = frozenset(
    {"自动秘境", "自动地脉花", "自动幽境危战", "自动首领讨伐"}
)


def ensure_script_assets(root_path: Path) -> None:
    """把 MASOneDragon 脚本资产（main.js / manifest.json）复制到 BGI 的
    ``User/JsScript/MASOneDragon``。

    验证1 已坐实：本地脚本经配置组 ``folderName`` 引用即可运行，无需订阅；
    这里负责把自建脚本本体落到该目录。内容不变则不重写，避免无谓 IO。
    settings.json 必须部署：manifest 声明 ``settings_ui`` 后 BGI 才会把配置组的
    ``jsScriptSettingsObject``（Plan）注入为脚本 settings 全局，缺失则 main.js
    读到空 Plan 秒退（2026-09 实机排障结论）。
    """
    dst_dir = root_path / _JS_SCRIPT_REL_DIR / SCRIPT_FOLDER_NAME
    dst_dir.mkdir(parents=True, exist_ok=True)
    for fname in ("main.js", "manifest.json", "settings.json"):
        src = _SCRIPT_ASSET_DIR / fname
        if not src.is_file():
            logger.warning(f"一条龙执行层脚本资产缺失，跳过复制: {src}")
            continue
        dst = dst_dir / fname
        if not dst.exists() or dst.read_bytes() != src.read_bytes():
            copy2(src, dst)
            logger.info(f"已部署一条龙执行层脚本资产: {dst}")


# 执行层「段」组名前缀（形如 MAS-{短id}-执行层段1）：每段一个配置组文件，
# 由 build_execution_segments 按左栏队列顺序切分，交给同一次 --startGroups 顺序执行。
_EXEC_SEGMENT_PREFIX = "MAS-{short}-执行层段"


def _load_group_template() -> dict[str, Any]:
    """读取执行层配置组模板（提供组级 ``config`` 与 MASOneDragon 项目骨架）。"""
    template_path = _RES_TEMPLATE_DIR / f"{GROUP_NAME}.json"
    template = read_file(template_path)
    if not isinstance(template, dict) or not isinstance(template.get("projects"), list):
        raise RuntimeError(f"一条龙执行层配置组模板无效: {template_path}")
    if not isinstance(template["projects"][0], dict):
        raise RuntimeError(f"一条龙执行层配置组模板缺 projects[0]: {template_path}")
    return template


def build_combat_project(plan_steps: list[dict[str, Any]]) -> dict[str, Any]:
    """构造承载战斗 4 项的 MASOneDragon JS 项目（注入 Plan）。"""
    project = dict(_load_group_template()["projects"][0])
    project["folderName"] = SCRIPT_FOLDER_NAME
    # plan 必须以 JSON 字符串注入：BGI 的 settings 注入是 .NET 对象包装（实测
    # MAS_SETTINGS_KEYS 打出 GetType/ToString 等），JS 侧对嵌套值（steps/weeklyLeyLine）
    # 做属性访问会拿到 undefined，序列化成字符串后由 main.js safeParsePlan 解析。
    project["jsScriptSettingsObject"] = {
        "plan": json.dumps({"version": 1, "steps": plan_steps}, ensure_ascii=False)
    }
    return project


def custom_exec_names(queue: list[dict[str, Any]], custom_kinds: frozenset[str]) -> list[str]:
    """按队列顺序取出「交由执行层接管的自定义项」名。

    与 ``one_dragon.apply_groups`` 写入 ``TaskDefinitions`` 的取值一致：
    非内置项写的是 ``step or name``（实例名优先，用于多实例各自独立）。
    """
    names: list[str] = []
    for entry in queue or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("kind") or "") not in custom_kinds:
            continue
        name = str(entry.get("name") or "").strip()
        if not name:
            continue
        names.append(str(entry.get("step") or name).strip() or name)
    return names


def build_execution_segments(
    root_path: Path,
    script_id: str,
    user_id: str,
    queue: list[dict[str, Any]],
    plan_steps: list[dict[str, Any]],
    custom_kinds: frozenset[str],
) -> list[dict[str, Any]]:
    """按左栏队列顺序把执行层切成「段」，每段对应一个配置组文件。

    切分规则（对应「路线 C：保真 + 完整顺序」）：
    - **战斗 4 项**：由 MASOneDragon 一个 JS 项目整体承载（内部按 Plan 顺序编排），
      插在队列中「第一个被接管的战斗项」的位置；队列里其余战斗项一并归入该段。
    - **js / pathing / keymouse 类自定义项**：并入相邻的「合成段」。它们的组级
      ``config`` 由 MAS 合成、没有用户语义，合并无损失；相邻多个连续项合并成一段，
      从而减少 ``RunMulti``/``TaskRunner`` 边界与随之而来的月卡检测等固定开销。
    - **scriptgroup 类自定义项**：它是用户自己的完整配置组（自带组级 ``pathingConfig``：
      队伍/自动拾取/防卡死等，而 BGI 的 Pathing/Shell 项目只读**组级**配置，项目上
      无处可放），因此**独立成段**，不与其邻居合并，保证其配置原样生效。

    Returns:
        ``[{"config": <组级config|None>, "projects": [项目...]}, ...]``；
        ``config`` 为 ``None`` 表示合成段（用模板默认 config）。
    """
    if not plan_steps and not any(
        str((e or {}).get("kind") or "") in custom_kinds
        for e in (queue or [])
        if isinstance(e, dict)
    ):
        return []

    # 多实例：实例名（组名-{行uid}）→ 基名。与 write_user_one_dragon / materialize 同规则，
    # 供 resolve_custom_group 回退到基名副本 / 按基名在 BGI 目录解析资产。
    instance_base: dict[str, str] = {}
    for entry in queue or []:
        if not isinstance(entry, dict):
            continue
        entry_name = str(entry.get("name") or "").strip()
        entry_step = str(entry.get("step") or "").strip()
        if entry_name and entry_step and entry_step != entry_name:
            instance_base[entry_step] = entry_name

    segments: list[dict[str, Any]] = []
    combat_placed = False

    def _append_synthetic(projects: list[Any]) -> None:
        """把项目并入末尾的合成段；末尾不是合成段则新开一段。"""
        if segments and segments[-1]["config"] is None:
            segments[-1]["projects"].extend(projects)
        else:
            segments.append({"config": None, "projects": list(projects)})

    for entry in queue or []:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name") or "").strip()
        if not name or not entry.get("enabled", True):
            continue
        base = resolve_base_name(name)
        if base in BUILTIN_COMBAT_STEPS:
            # 战斗 4 项整体一项，只在第一个被接管的战斗项处插入一次
            if plan_steps and not combat_placed:
                _append_synthetic([build_combat_project(plan_steps)])
                combat_placed = True
            continue
        kind = str(entry.get("kind") or "")
        if kind not in custom_kinds:
            continue
        group = resolve_custom_group(
            root_path, script_id, user_id, name, instance_base.get(name) or name
        )
        projects = group.get("projects") if isinstance(group, dict) else None
        if not isinstance(projects, list) or not projects:
            continue
        if kind == "scriptgroup":
            segments.append({"config": group.get("config"), "projects": projects})
        else:
            _append_synthetic(projects)

    # 兜底：队列里没有战斗项（如空队列 / 战斗项全被禁用）但仍有 Plan 时，
    # 仍要跑战斗段——与旧行为（战斗先跑）一致，插到最前面。
    if plan_steps and not combat_placed:
        segments.insert(0, {"config": None, "projects": [build_combat_project(plan_steps)]})
    return segments


def write_execution_groups(
    root_path: Path,
    user_id: str,
    segments: list[dict[str, Any]],
) -> list[Path]:
    """把「段」逐个写成 BetterGI 配置组文件（``User/ScriptGroup/MAS-{短id}-执行层段N.json``）。

    这些组由 MAS 每次运行前重新生成，不属于用户资产，运行结束由
    ``remove_execution_groups`` 删除；脚本本体（``User/JsScript/MASOneDragon``）保留。
    ``index`` 取固定高位区间，避免与用户配置组在 BGI 列表里插队。
    """
    if not segments:
        return []
    ensure_script_assets(root_path)
    template = _load_group_template()
    short = _mas_user_short_id(user_id)
    prefix = _EXEC_SEGMENT_PREFIX.format(short=short)
    created: list[Path] = []
    out_dir = root_path / _GROUP_REL_DIR
    for i, seg in enumerate(segments, start=1):
        name = f"{prefix}{i}"
        group = dict(template)
        group["name"] = name
        group["index"] = _SEGMENT_INDEX_BASE + i
        if isinstance(seg.get("config"), dict):
            group["config"] = seg["config"]
        group["projects"] = list(seg.get("projects") or [])
        out_path = out_dir / f"{name}.json"
        write_file(out_path, group)
        created.append(out_path)
    logger.info(
        f"已生成一条龙执行层配置组 {len(created)} 段: {[p.stem for p in created]}"
    )
    return created


def remove_execution_groups(root_path: Path, created: list[Path]) -> None:
    """删除本次运行物化到 BGI 的执行层「段」配置组文件（幂等）。"""
    for path in created or []:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass


def cleanup_leftover_execution_groups(root_path: Path, user_id: str) -> int:
    """清理该用户历史残留的执行层「段」配置组文件（进程被强杀等异常场景）。"""
    short = _mas_user_short_id(user_id)
    removed = 0
    sg_dir = root_path / _GROUP_REL_DIR
    if sg_dir.is_dir():
        for path in sg_dir.glob(f"MAS-{short}-执行层段*.json"):
            try:
                path.unlink(missing_ok=True)
                removed += 1
            except OSError:
                pass
    return removed
