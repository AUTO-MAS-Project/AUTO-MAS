#   AUTO-MAS: A Multi-Script, Multi-Config Management and Automation Software
#   Copyright © 2025-2026 AUTO-MAS Team
#
#   This file is part of AUTO-MAS.
#
#   AUTO-MAS is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as
#   published by the Free Software Foundation, version 3 or (at your option)
#   any later version.
#
#   AUTO-MAS is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

#   Contact: DLmaster_361@163.com

"""BetterGI 配置备份归档：MAS 用户配置（per-user 副本 + 字段侧车）/ BetterGI 原生配置。

备份时机（MAS「动手前」，此时 BetterGI 配置尚未被触碰）：

- 任务启动（manager ``main_task``）：``native`` 归档 BetterGI 全局主配置
  ``{RootPath}/User/config.json``（AutoProxy 每次运行都会临时补写队伍/
  策略叶子、结束还原，崩溃/还原失败会把全局配置污染）与 **BGI 一条龙
  实配** ``{RootPath}/User/OneDragon/*.json``——用户在 BGI GUI 里直接
  编辑的配置，改坏无 MAS 侧找回点（用户实测场景）；
- 运行物化前（AutoProxy ``_write_one_dragon_config`` 前）：``mas`` 归档
  本用户 per-user 副本（运行会把字段物化进副本与 BGI 槽位）；
- 编辑界面进入 / 退出（前端 ensure）：进入时归档 ``native``、退出时归档
  ``mas``（编辑会话包络的 MAS 侧终态）。

``mas`` 池的内容 = per-user 副本目录 + **页面字段侧车**：

- per-user 副本：``data/{script_id}/{user_id}/`` 下的 ``OneDragon/``
  （一条龙配置副本）、``ScriptGroup/``（配置组副本）、``GlobalDomain/``
  （秘境刷取配置副本）——前端端点直接读写、就是页面编辑对象（对齐
  OkNte「ConfigFile 即页面编辑对象」）；脚本态/用户态/直控都走 per-user
  副本（副本与来源无关，直控下前端编辑同样落盘），池**恒按用户分桶**，
  无 owner 解耦（对齐 General）。
- 字段侧车：OneDragon 段全部字段 + Task.OneDragonConfigName + Switch.
  Resource（运行时物化进副本/原生或注入切号脚本）+ Info.Mode（仅预览：
  决定是否物化）。Id/Password/前后置脚本/通知/Data 由 MAS 自己消费（登录
  与执行域），不属于 BetterGI 配置内容，不进备份。恢复 = 副本目录回滚 +
  字段回填 UserData。

``native`` 池 = BetterGI 全局主配置 ``{RootPath}/User/config.json`` +
**BGI 一条龙实配**（``{RootPath}/User/OneDragon/*.json``，排除 MAS 运行时
临时槽位「MAS独立配置.json」——运行物化、结束删除，不是用户实配），按
物理安装根指纹分桶、跨脚本共享、不随脚本删除。一条龙实配在用户独立配置
模式下 MAS 零接触，但它是用户在 BGI GUI 里的直接编辑对象（直控/手工编辑
场景），纳入备份提供改坏找回点。

时间戳快照、指纹去重、保留清理与文件/目录恢复由公共模块
``app.utils.config_archive`` 提供（默认每池保留 10 份），本模块只保留
BetterGI 特有的副本布局、字段侧车、恢复语义（恢复前强制归档当前）与
预览摘要。
"""

import json
from pathlib import Path

from app.utils import get_logger
from app.utils.config_archive import (
    OVERLAY_SIDECAR_NAME,
    archive_files,
    config_root_key,
    dir_files,
    get_backup_dir,
    list_times,
    read_overlay_sidecar,
    restore_files,
)

logger = get_logger("BetterGI 配置备份")

# ══════════════════ MAS 用户配置（per-user 副本 + 字段侧车） ══════════════════

_OVERLAY_KEY_GROUPS = {
    "Info": ("Mode",),
    "Task": ("OneDragonConfigName",),
    "OneDragon": (
        "Groups",
        "DailyRewardPartyName",
        "PartyName",
        "AutoBossStrategyName",
        "IfUseTeams",
        "Teams",
        "IfUseCustomGroups",
        "CustomGroups",
        "Queue",
        "Plan",
        "UseExecutionLayer",
    ),
    "Switch": ("Resource",),
}
"""侧车字段的配置段归属（运行时物化进副本/原生或注入切号脚本的字段）"""

_OVERLAY_KEY_GROUP = {
    key: group for group, keys in _OVERLAY_KEY_GROUPS.items() for key in keys
}

_OVERLAY_PREVIEW_ONLY_KEYS = {"Mode"}
"""仅预览不回填的字段：配置来源决定 MAS 是否物化，恢复以当前值为准"""

# 预览分区一：与 BetterGI 概念对应的字段（可在 BetterGI GUI 对照）
_OVERLAY_BGI_ORDER = (
    "OneDragonConfigName",
    "Groups",
    "DailyRewardPartyName",
    "PartyName",
    "AutoBossStrategyName",
    "IfUseTeams",
    "Teams",
    "IfUseCustomGroups",
    "CustomGroups",
    "Queue",
    "Plan",
    "UseExecutionLayer",
    "Resource",
)
# 预览分区二：MAS 独有字段（BetterGI GUI 无对应概念）
_OVERLAY_MAS_ONLY_ORDER = ("Mode",)

_OVERLAY_FIELD_LABELS = {
    "Mode": "配置来源",
    "OneDragonConfigName": "一条龙配置名",
    "Groups": "已启用任务",
    "DailyRewardPartyName": "领取奖励队伍",
    "PartyName": "战斗队伍",
    "AutoBossStrategyName": "战斗策略",
    "IfUseTeams": "使用队伍配置",
    "Teams": "队伍配置",
    "IfUseCustomGroups": "管理自定义配置组",
    "CustomGroups": "自定义配置组",
    "Queue": "一条龙队列",
    "Plan": "一条龙执行计划",
    "UseExecutionLayer": "直连执行层",
    "Resource": "游戏服务器",
}
"""侧车字段中文标签（对齐 BetterGI 编辑页词表）"""

_PER_USER_SUB_DIRS = ("OneDragon", "ScriptGroup", "GlobalDomain")
"""per-user 副本子目录（前端端点直接读写、页面编辑对象）"""


def read_overlay_values(config) -> dict:
    """读取配置对象的 BetterGI 页面字段（鸭子类型，仅需 ``get(group, key)``）。

    覆盖 Info.Mode / Task.OneDragonConfigName / OneDragon 段全部字段 /
    Switch.Resource；值为 ``None``（配置项不存在）的键不纳入侧车。
    """

    values: dict = {}
    for group, keys in _OVERLAY_KEY_GROUPS.items():
        for key in keys:
            if (value := config.get(group, key)) is not None:
                values[key] = value
    return values


def group_overlay(overlay: dict) -> dict[str, dict]:
    """把平铺的侧车字段按配置段分组（恢复回填 UserData 用）。

    仅预览字段（配置来源）不回填：物化与否由当前模式决定，回填旧值会
    静默改变运行行为。
    """

    grouped: dict[str, dict] = {}
    for key, value in overlay.items():
        if key in _OVERLAY_PREVIEW_ONLY_KEYS:
            continue
        grouped.setdefault(_OVERLAY_KEY_GROUP.get(key, "OneDragon"), {})[key] = value
    return grouped


def overlay_sidecar_content(overlay: dict) -> str:
    """页面字段侧车的内存 JSON（:func:`archive_files` 内存内容，免临时文件）。"""

    return json.dumps(overlay, ensure_ascii=False, indent=2)


def mas_user_dir(script_id: str, user_id: str) -> Path:
    """per-user 根目录：``data/{script_id}/{user_id}``（OneDragon/ScriptGroup/GlobalDomain 的父级）。"""

    return Path.cwd() / "data" / script_id / user_id


def mas_backup_root(script_id: str, user_id: str) -> Path:
    """MAS 池归档根：``data/{script_id}/BetterGIBackups/mas/{user_id}``（恒按用户）。"""

    return Path.cwd() / "data" / script_id / "BetterGIBackups" / "mas" / user_id


def _collect_mas_files(script_id: str, user_id: str) -> dict[str, Path]:
    """收集 per-user 副本文件集（相对键保留子目录名，如 ``OneDragon/xxx.json``）。

    仅收 per-user 副本三个子目录；UserData 字段与其它数据（切号脚本残留等）
    不属于副本内容，不进备份。
    """

    files: dict[str, Path] = {}
    user_root = mas_user_dir(script_id, user_id)
    for sub in _PER_USER_SUB_DIRS:
        sub_dir = user_root / sub
        if not sub_dir.is_dir():
            continue
        for rel, path in dir_files(sub_dir).items():
            files[f"{sub}/{rel}"] = path
    return files


def archive_mas_backup(
    script_id: str,
    user_id: str,
    overlay: dict | None = None,
    force: bool = False,
) -> Path | None:
    """归档 per-user 副本 + 页面字段侧车到用户池（指纹去重，无变化跳过）。

    副本与侧车都参与指纹：只改页面字段、未动副本时同样新建归档。副本
    全部缺失（用户从未保存过配置组/秘境刷取且未运行过任务）时无可恢复
    内容，返回 ``None``。
    """

    files = _collect_mas_files(script_id, user_id)
    if overlay:
        files[OVERLAY_SIDECAR_NAME] = overlay_sidecar_content(overlay)
    if not files:
        return None
    dest = archive_files(files, mas_backup_root(script_id, user_id), force=force)
    if dest is None:
        logger.info("MAS 配置无变化，跳过归档")
        return None
    logger.info(f"用户 {user_id} 的 MAS 配置已归档: {dest.name}")
    return dest


def list_mas_backups(script_id: str, user_id: str) -> list[str]:
    """用户池的全部归档时间戳（倒序，最新在前）。"""

    return list_times(mas_backup_root(script_id, user_id))


def get_mas_backup_dir(script_id: str, user_id: str, ts: str) -> Path | None:
    """取用户池指定时间戳的归档目录；不存在返回 None。"""

    return get_backup_dir(mas_backup_root(script_id, user_id), ts)


def restore_mas_backup(
    script_id: str, user_id: str, ts: str, overlay: dict | None = None
) -> dict | None:
    """把用户池归档恢复到 per-user 副本（恢复前自动归档当前，误恢复可找回）。

    返回该备份的侧车（供调用方回填 UserData；旧版备份无侧车返回
    ``None``），侧车文件随即从副本目录中分离删除，不留在 per-user 里。
    """

    backup_dir = get_mas_backup_dir(script_id, user_id, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    archive_mas_backup(script_id, user_id, overlay=overlay, force=True)
    # 把归档内副本文件（按 OneDragon/… 相对键）逐一写回 per-user 根目录
    user_root = mas_user_dir(script_id, user_id)
    files = dir_files(backup_dir)
    for rel, path in files.items():
        if rel == OVERLAY_SIDECAR_NAME:
            continue
        target = user_root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    restored_overlay = read_overlay_sidecar(backup_dir)
    logger.info(f"用户 {user_id} 的 MAS 配置已恢复备份 {ts}")
    return restored_overlay


def archive_mas_runtime_backup(script_id: str, user_id: str, overlay: dict) -> None:
    """运行物化前归档 per-user 副本 + 页面字段到用户池。

    运行会把字段物化进副本与 BGI 槽位、覆盖副本内容，物化前存底；指纹
    去重，失败不阻断运行（调用方以 ``suppress`` 包裹）。
    """

    archive_mas_backup(script_id, user_id, overlay=overlay)


# ══════════════════ BetterGI 原生配置（全局 config.json + 一条龙实配） ══════════════════

_BGI_GLOBAL_CONFIG_REL = Path("User") / "config.json"
"""BetterGI 全局主配置相对路径（从 RootPath 派生）"""

_BGI_ONE_DRAGON_REL_DIR = Path("User") / "OneDragon"
"""BGI 一条龙实配目录相对路径（与 tools.one_dragon._ONE_DRAGON_REL_DIR 同源）"""

_BGI_ONE_DRAGON_SLOT_NAME = "MAS独立配置"
"""MAS 运行时临时槽位名（与 tools.one_dragon._MAS_ONE_DRAGON_SLOT_NAME 同源；不属用户实配，归档排除）"""


def native_backup_root(root_path: str | Path) -> Path:
    """BetterGI 原生配置的项目级归档目录：``data/BetterGIBackups/native/{key}``。

    ``key`` 是物理安装根的指纹（:func:`config_root_key`）——同一份安装无论
    被哪个脚本引用都归同一个池；跨脚本共享、不随脚本删除。
    """

    return (
        Path.cwd() / "data" / "BetterGIBackups" / "native" / config_root_key(root_path)
    )


def global_config_path(root_path: str | Path) -> Path:
    """BetterGI 全局主配置文件路径（``{RootPath}/User/config.json``）。"""

    return Path(root_path) / _BGI_GLOBAL_CONFIG_REL


def collect_native_files(root_path: Path) -> dict[str, Path]:
    """收集 native 归档目标文件集（相对键 → 文件路径）。

    - ``config.json``：全局主配置（MAS 运行触碰）；
    - ``OneDragon/{名}.json``：BGI 一条龙实配（用户在 BGI GUI 里直接编辑的
      配置，改坏无 MAS 侧找回点——用户实测场景）。排除 MAS 运行时临时
      槽位「MAS独立配置.json」（运行时物化、结束删除，不是用户实配）。
    """

    files: dict[str, Path] = {}
    config_path = global_config_path(root_path)
    if config_path.is_file():
        files[config_path.name] = config_path
    dragon_dir = root_path / _BGI_ONE_DRAGON_REL_DIR
    if dragon_dir.is_dir():
        for rel, path in dir_files(dragon_dir).items():
            if Path(rel).name == f"{_BGI_ONE_DRAGON_SLOT_NAME}.json":
                continue
            files[f"OneDragon/{rel}"] = path
    return files


def archive_native_backup(root_path: str | Path, force: bool = False) -> Path | None:
    """归档 BetterGI 原生配置（全局 config.json + 一条龙实配，指纹去重）。

    两类都为空（目录不存在且无 config.json）时无可归档内容，返回 ``None``。
    """

    root_path = Path(root_path)
    files = collect_native_files(root_path)
    if not files:
        return None
    dest = archive_files(files, native_backup_root(root_path), force=force)
    if dest is None:
        logger.info("BetterGI 原生配置无变化，跳过归档")
        return None
    logger.info(f"BetterGI 原生配置已归档: {dest.name}")
    return dest


def list_native_backups(root_path: str | Path) -> list[str]:
    """BetterGI 原生配置全部归档时间戳（倒序，最新在前）。"""

    return list_times(native_backup_root(root_path))


def get_native_backup_dir(root_path: str | Path, ts: str) -> Path | None:
    """取指定时间戳的原生配置归档目录；不存在返回 None。"""

    return get_backup_dir(native_backup_root(root_path), ts)


def restore_native_backup(root_path: str | Path, ts: str) -> None:
    """把归档恢复到 BetterGI 安装目录（恢复前自动归档当前，误恢复可找回）。

    按归档内相对键写回（``config.json`` → ``{RootPath}/User/config.json``、
    ``OneDragon/{名}.json`` → ``{RootPath}/User/OneDragon/{名}.json``）。
    replace 语义：OneDragon 子树整棵按备份替换，跨恢复残留的同前缀文件
    一并清除（:func:`restore_files` 管理）。
    """

    backup_dir = get_native_backup_dir(root_path, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    root_path = Path(root_path)
    archive_native_backup(root_path, force=True)
    restore_files(backup_dir, root_path / _BGI_GLOBAL_CONFIG_REL.parent)
    logger.info(f"BetterGI 原生配置已恢复备份 {ts}")


# ══════════════════ 备份预览摘要 ══════════════════

_SUMMARY_VALUE_LIMIT = 50
"""摘要字段值的最大字符数（超出截断）"""


def _summary_text(value) -> str:
    text = str(value)
    if len(text) > _SUMMARY_VALUE_LIMIT:
        return text[: _SUMMARY_VALUE_LIMIT - 1] + "…"
    return text


def _format_bool(value) -> str:
    return "开启" if bool(value) else "关闭"


def _parse_json_list(raw) -> list:
    """解析 JSON 数组字符串字段（CustomGroups/Queue/Plan 等），非法返回空列表。"""

    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, str) and raw.strip():
        try:
            loaded = json.loads(raw)
        except Exception:
            return []
        return (
            [item for item in loaded if isinstance(item, dict)]
            if isinstance(loaded, list)
            else []
        )
    return []


def _overlay_value_text(key: str, value) -> str:
    """侧车字段值转展示文本（对齐 §3.3「任务启用罗列 + 配置内容表单行」结构）。

    - ``Groups``：内置组开关列表 → 「已启用任务」罗列行（与 native 池一条龙
      实配反读同标签同口径，两池重叠部分逐字一致）；
    - ``CustomGroups``：管理表 [{"name","enabled"}] → 启用自定义组罗列；
    - ``Queue``：编排 [{"kind","name"}] → 任务队列顺序罗列；
    - 其余标量：布尔转开关、原样截断。
    """

    if key == "Groups":
        names = [str(name) for name in value or [] if str(name)]
        return "、".join(names) if names else "无"
    if key == "Teams":
        # 队伍配置表 JSON 数组（不含序号 0 通用队伍），预览只给数量
        items = _parse_json_list(value)
        return f"已配置 {len(items)} 支队伍" if items else "无"
    if key == "CustomGroups":
        items = _parse_json_list(value)
        names = [
            str(item.get("name") or "")
            for item in items
            if bool(item.get("enabled", True))
        ]
        names = [name for name in names if name]
        return "、".join(names) if names else "无"
    if key == "Queue":
        items = _parse_json_list(value)
        names = [str(item.get("name") or "") for item in items]
        names = [name for name in names if name]
        return "、".join(names) if names else "无"
    if key == "Plan":
        # 执行计划 [{uid,kind,name,enabled,settings}] → 启用步骤罗列（JSON
        # 原文截断用户读不懂；settings 参数细节经「查看详细配置」看）
        items = _parse_json_list(value)
        names = [
            str(item.get("name") or "")
            for item in items
            if bool(item.get("enabled", True))
        ]
        names = [name for name in names if name]
        return "、".join(names) if names else "无"
    if isinstance(value, bool):
        return _format_bool(value)
    return _summary_text(value)


def build_overlay_preview(overlay: dict) -> dict:
    """mas 池预览：分区行（MAS 独有 = 配置来源；BetterGI 对应 = 页面字段）。

    任务开关用「已启用任务」罗列行（与 native 池一条龙实配反读同口径）；
    副本文件另列摘要（文件名 + 大小），让用户确认「副本里有什么」。
    """

    sections: list[dict] = []

    mas_rows: list[dict] = []
    for key in _OVERLAY_MAS_ONLY_ORDER:
        if key in overlay:
            mas_rows.append(
                {
                    "key": _OVERLAY_FIELD_LABELS.get(key, key),
                    "value": _summary_text(overlay[key]),
                }
            )
    if mas_rows:
        sections.append({"name": "mas-only", "label": "MAS 独有配置", "rows": mas_rows})

    bgi_rows: list[dict] = []
    for key in _OVERLAY_BGI_ORDER:
        if key not in overlay:
            continue
        bgi_rows.append(
            {
                "key": _OVERLAY_FIELD_LABELS.get(key, key),
                "value": _overlay_value_text(key, overlay[key]),
            }
        )
    if bgi_rows:
        sections.append({"name": "bgi", "label": "BetterGI 配置", "rows": bgi_rows})

    return {"sections": sections}


def build_mas_preview(backup_dir: Path, overlay: dict | None) -> dict:
    """mas 池预览载荷：字段分区 + 副本文件摘要（相对键 + 大小）。"""

    sections = build_overlay_preview(overlay or {})["sections"]
    files = {
        rel: path.stat().st_size
        for rel, path in dir_files(backup_dir).items()
        if rel != OVERLAY_SIDECAR_NAME
    }
    if files:
        file_rows = [
            {"key": rel, "value": f"{size} B"} for rel, size in sorted(files.items())
        ]
        sections.append({"name": "copies", "label": "用户配置副本", "rows": file_rows})
    return {"sections": sections}


def _enabled_task_rows(config: dict) -> list[dict]:
    """从一条龙实配 dict 合成「已启用任务」行（对齐 MAA/BAAH 任务罗列口径）。

    BGI 实配结构（实测）：``TaskOrder``（uid 序，同名可重复）+
    ``TaskEnabledList``（uid→bool）+ ``TaskDefinitions``（uid→任务名）。
    按 TaskOrder 顺序经 TaskDefinitions 映射为任务名、过滤启用项；任一
    键缺失/为空则降级不反读（不臆造）。
    """

    order = config.get("TaskOrder")
    enabled = config.get("TaskEnabledList")
    defs = config.get("TaskDefinitions")
    if (
        not isinstance(order, list)
        or not order
        or not isinstance(enabled, dict)
        or not isinstance(defs, dict)
    ):
        return []
    names = [
        str(defs.get(uid) or "")
        for uid in order
        if isinstance(uid, str) and enabled.get(uid)
    ]
    names = [name for name in names if name]
    if not names:
        return [{"key": "已启用任务", "value": "无"}]
    return [{"key": "已启用任务", "value": "、".join(names)}]


def build_native_preview(root_path: str | Path, ts: str) -> dict:
    """native 池预览：反读备份内 config.json 关键字段（与 mas 池同口径）。

    只收 **mas 侧有对应配置概念** 的字段（§3.3「两池同字段同口径」）：

    - **任务列表**（一条龙实配反读，``TaskOrder``+``TaskEnabledList``+
      ``TaskDefinitions`` 合成「已启用任务」行，对齐 MAA/BAAH 口径）——
      实配文件取 ``config.json`` 顶层 ``selectedOneDragonFlowConfigName``
      指向的那份（BGI 界面「配置」下拉所选，截图里的「默认配置」），
      归档内缺失时取首个实配、无实配则跳过该行；
    - **战斗配置叶子**（全局 config.json，MAS 运行触碰/物化的目标）：
      战斗策略（``autoFightConfig.strategyName``，= 侧车 OneDragon.
      AutoBossStrategyName 物化目标）、自动秘境队伍（``autoDomainConfig.
      partyName``）与分解圣遗物开关、自动首领（``autoBossConfig``）/
      地脉花（``autoLeyLineOutcropConfig``）/ 幽境危战
      （``autoStygianOnslaughtConfig``）的队伍与策略。

    MAS 侧无对应概念的段（自动拾取/剧情/钓鱼/快速传送/吃料理等一键开关、
    游戏路径、捕获模式、遮罩外观、热键、通知凭据）**不进预览**——不属于
    用户日常通过 MAS 管理的配置；敏感字段（通知凭据、米游社 cookie）一律
    不读不展示。
    """

    backup_dir = get_native_backup_dir(root_path, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    files = dir_files(backup_dir)
    if not files:
        raise ValueError(f"备份内容为空: {ts}")

    rows: list[dict] = []

    # ── 任务列表（一条龙实配反读，置顶——用户最常改的就是任务开关）──
    global_data: dict | None = None
    global_rel = "config.json"
    if global_rel in files:
        try:
            loaded = json.loads(files[global_rel].read_text(encoding="utf-8-sig"))
            global_data = loaded if isinstance(loaded, dict) else None
        except Exception:  # noqa: BLE001 - 坏 JSON 不阻断预览
            global_data = None
    dragon_rels = sorted(rel for rel in files if rel.startswith("OneDragon/"))
    dragon_config: dict | None = None
    selected_name = (
        str(global_data.get("selectedOneDragonFlowConfigName") or "").strip()
        if global_data
        else ""
    )
    for rel in (
        [f"OneDragon/{selected_name}.json"] if selected_name else []
    ) + dragon_rels:
        if rel not in files:
            continue
        try:
            loaded = json.loads(files[rel].read_text(encoding="utf-8-sig"))
        except Exception:  # noqa: BLE001
            continue
        if isinstance(loaded, dict):
            dragon_config = loaded
            break

    if dragon_config is not None:
        rows.extend(_enabled_task_rows(dragon_config))

    if global_data is None:
        if "config.json" in files:
            rows.append(
                {
                    "key": "config.json",
                    "value": "无法解析（"
                    + f"{files['config.json'].stat().st_size} B）",
                }
            )
        if not rows:
            rows.append({"key": "文件", "value": f"{len(files)} 个（无 config.json）"})
        return {
            "sections": [{"name": "bgi", "label": "BetterGI 全局配置", "rows": rows}]
        }

    data = global_data

    def _seg(key: str) -> dict:
        seg = data.get(key)
        return seg if isinstance(seg, dict) else {}

    def _text(value, empty: str = "未设置") -> str:
        text = str(value or "").strip()
        return _summary_text(text) if text else empty

    fight = _seg("autoFightConfig")
    rows.append({"key": "战斗策略", "value": _text(fight.get("strategyName"))})

    domain = _seg("autoDomainConfig")
    rows.append({"key": "自动秘境队伍", "value": _text(domain.get("partyName"))})
    if domain:
        rows.append(
            {
                "key": "秘境·分解圣遗物",
                "value": _format_bool(domain.get("autoArtifactSalvage")),
            }
        )

    boss = _seg("autoBossConfig")
    if boss:
        rows.append({"key": "自动首领队伍", "value": _text(boss.get("teamName"))})
        rows.append({"key": "自动首领策略", "value": _text(boss.get("strategyName"))})

    ley = _seg("autoLeyLineOutcropConfig")
    if ley:
        rows.append(
            {
                "key": "地脉花类型",
                "value": _text(ley.get("leyLineOutcropType")),
            }
        )
        rows.append({"key": "地脉花队伍", "value": _text(ley.get("team"))})

    stygian = _seg("autoStygianOnslaughtConfig")
    if stygian:
        rows.append(
            {"key": "幽境危战队伍", "value": _text(stygian.get("fightTeamName"))}
        )
        rows.append(
            {"key": "幽境危战策略", "value": _text(stygian.get("strategyName"))}
        )

    return {"sections": [{"name": "bgi", "label": "BetterGI 全局配置", "rows": rows}]}
