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
#   You should have received a copy of the GNU Affero General Public
#   License along with AUTO-MAS. If not, see <https://www.gnu.org/licenses/>.

"""OK-WW 配置备份归档：MAS 用户配置 / 脚本原生配置，两类独立快照。

备份时机（MAS「动手前」，此时 ok-ww 尚未被触碰）：

- 任务 / 配置会话启动（manager ``prepare``）：``native`` 归档脚本原生
  working 配置当前状态（整目录）——原生配置物理上跨用户共享，只在任务级
  归档一次；下发/覆盖类操作按用户归档会把上一轮下发的 MAS 配置误当原生
  内容挤进保留池；
- 运行 / 配置会话下发前（AutoProxy / ScriptConfig 下发处）：``mas`` 归档
  本轮下发源（脚本态共享 Default 目录、用户态当前用户目录，按 owner 各归
  各的；运行回写与会话保存会覆盖它）；
- 编辑界面进入 / 退出（前端 ensure）：进入时归档 ``native``（MAS 触碰前
  原始态）、退出时归档 ``mas``（编辑会话包络的 MAS 侧终态）。

``mas`` 池的内容 = ConfigFile 整目录 + **侧车字段**：Info.Id（账号，运行
时被 AutoProxy 消费）+ 快速配置覆盖层字段（页面任务配置卡片，运行时才覆盖
进 DailyTask.json，不在 ConfigFile 中）——侧车让「MAS 用户配置备份」真正
覆盖用户在 MAS 页面配的东西，恢复时随文件一起回滚并回填表单（对齐
ZzzOd / MAA 字段回填模式）。
MAS 配置目录 owner 由用户当前的 ``Info.Mode`` 三态决定（脚本=Default 共
享、用户=独立目录、直控=无 MAS 配置），解析逻辑见 ``restore_service``。
时间戳快照、指纹去重、保留清理与整目录恢复的通用逻辑由公共模块
``app.utils.config_archive`` 提供（默认每池保留 10 份），本模块只保留
ok-ww 特有的 owner 目录布局、覆盖层侧车、恢复语义（恢复前强制归档当前）
与归档目录布局。
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
    mask_account,
    read_overlay_sidecar,
    restore_dir,
)

logger = get_logger("OK-WW 配置备份")


def backup_root(script_id: str) -> Path:
    """某脚本的备份归档根目录（MAS 用户池用）：``data/{script_id}/OkwwBackups``。"""

    return Path.cwd() / "data" / script_id / "OkwwBackups"


def project_backup_root() -> Path:
    """ok-ww 备份的项目级根目录：``data/OkwwBackups``。

    native（脚本原生配置）池挂在这里而不是脚本目录下——同一份物理安装
    可被多个脚本实例引用，原生备份按物理配置根指纹分桶、跨脚本共享、
    不随脚本删除（mas 用户池仍按脚本，见 :func:`mas_backup_root`）。
    """

    return Path.cwd() / "data" / "OkwwBackups"


def mas_backup_root(script_id: str, user_id: str) -> Path:
    """MAS 池归档根：``data/{script_id}/OkwwBackups/mas/{user_id}``。

    **恒按用户分桶**——备份内容（ConfigFile 快照 + 覆盖层字段侧车）的
    侧车是用户级的，按用户分桶才能保证每个用户只看到、只恢复自己的备份。
    注意池与恢复目标解耦：脚本态用户的下发源是共享 Default 目录，但其
    池仍是 ``mas/{user_id}``（多用户各自持有该共享目录的快照，侧车互不
    混淆）。
    """

    return backup_root(script_id) / "mas" / user_id


def native_backup_root(config_path: str | Path) -> Path:
    """ok-ww 原生配置的项目级归档目录：``data/OkwwBackups/native/{key}``。

    ``key`` 是物理配置根的指纹（:func:`config_root_key`）——同一份物理
    配置无论被哪个脚本引用都归同一个池；跨脚本共享、不随脚本删除。
    """

    return project_backup_root() / "native" / config_root_key(config_path)


def mas_config_dir(script_id: str, owner: str) -> Path:
    """MAS 配置目录：``data/{script_id}/{owner}/ConfigFile``。"""

    return Path.cwd() / "data" / script_id / owner / "ConfigFile"


# ══════════════════ MAS 配置（池按用户，目标路径按 owner） ══════════════════

_OVERLAY_INFO_KEYS = ("Id", "Mode")
"""侧车收录的 MAS 用户 Info 段字段：账号 Id（运行时被 AutoProxy 消费，
页面认知的一部分，进侧车随备份走、恢复回填；对齐 MAA 收账号先例）
与 Mode（配置文件来源，仅预览不回填）"""

_OVERLAY_PREVIEW_ONLY_KEYS = {"Mode"}
"""仅预览不回填的字段：配置来源决定运行下发方式（脚本/用户/直控），
恢复时以当前值为准，回填旧值会静默翻转用户态/脚本态。"""

_OVERLAY_TASK_KEYS = (
    "TaskIndex",
    "WhichToFarm",
    "WhichTacetSuppressionToFarm",
    "WhichForgeryChallengeToFarm",
    "MaterialSelection",
    "FarmNightmareNestForDailyEcho",
    "AdditionalTasks",
)
"""快速配置覆盖层字段（MAS 用户配置 Task 段，运行时覆盖进 DailyTask.json）"""

_OVERLAY_KEY_GROUPS = {"Info": _OVERLAY_INFO_KEYS, "Task": _OVERLAY_TASK_KEYS}
"""侧车字段的配置段归属（两组键名无交集，侧车内平铺存储）"""

_OVERLAY_KEY_GROUP = {
    key: group for group, keys in _OVERLAY_KEY_GROUPS.items() for key in keys
}
"""平铺侧车键 → 配置段（恢复回填分组用）"""


def read_overlay_values(config) -> dict:
    """读取配置对象的侧车字段：Info.Id/Mode（账号 + 配置文件来源）+ Task
    快速配置覆盖层字段。

    鸭子类型，仅需 ``get(group, key)``；值为 ``None``（配置项不存在）的键
    不纳入侧车。
    """

    values: dict = {}
    for group, keys in _OVERLAY_KEY_GROUPS.items():
        for key in keys:
            if (value := config.get(group, key)) is not None:
                values[key] = value
    return values


def group_overlay(overlay: dict) -> dict[str, dict]:
    """把平铺的侧车字段按配置段分组（恢复回填 UserData 用）。

    旧版备份无组归属的键回退到 Task 段（历史行为）；侧车键名与 Task
    覆盖层字段键名一致，无冲突。仅预览字段（配置文件来源）不回填：
    恢复目标目录由当前模式决定，回填旧值会静默改变用户态/脚本态。
    """

    grouped: dict[str, dict] = {}
    for key, value in overlay.items():
        if key in _OVERLAY_PREVIEW_ONLY_KEYS:
            continue
        grouped.setdefault(_OVERLAY_KEY_GROUP.get(key, "Task"), {})[key] = value
    return grouped


def collect_mas_files(
    mas_dir: str | Path, overlay: dict | None = None
) -> dict[str, "Path | str"]:
    """收集 MAS 配置目录文件集 + 覆盖层字段侧车（相对键 → 路径/内存内容）。

    侧车为内存 JSON（:func:`archive_files` 支持内存内容），免临时文件；
    目录缺失或为空时仅归档侧车——用户级目录要等首次运行物化，页面字段
    （Info/Task 侧车）不能因目录未建而一起丢（否则从未运行的用户切来源、
    改配置后退出，mas 池永远为空）。
    """

    mas_dir = Path(mas_dir)
    files: dict[str, "Path | str"] = {}
    if mas_dir.is_dir():
        files.update(dir_files(mas_dir))
    if overlay:
        files[OVERLAY_SIDECAR_NAME] = json.dumps(overlay, ensure_ascii=False, indent=2)
    return files


def archive_mas_backup(
    script_id: str,
    user_id: str,
    mas_dir: Path,
    overlay: dict | None = None,
    force: bool = False,
) -> Path | None:
    """归档 MAS 配置整份 + 覆盖层字段侧车到用户池（指纹去重，无变化跳过）。

    ``user_id`` 是池归属（恒按用户分桶，见 :func:`mas_backup_root`）；
    ``mas_dir`` 是归档/恢复目标路径，由调用方按三态 owner 解析（脚本态
    共享 Default 目录、用户态独立目录）——池与目标解耦。
    侧车参与指纹：只改表单覆盖层字段、未动 ConfigFile 时同样新建归档
    （内存 JSON 直接入档，免临时文件）。
    目录与侧车皆空时无可归档内容返回 ``None``；``force=True`` 恢复前
    存底（不清理历史条目；内容与最新份一致时同样跳过——当前配置已存放在
    该份备份中，误恢复可从它找回）。
    """

    files = collect_mas_files(mas_dir, overlay)
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
    script_id: str,
    user_id: str,
    ts: str,
    mas_dir: Path,
    overlay: dict | None = None,
) -> dict | None:
    """把用户池归档恢复到 MAS 配置目录（恢复前自动归档当前，误恢复可找回）。

    ``user_id`` 是池归属（与归档一致按用户分桶）；``mas_dir`` 是恢复目标
    路径，由调用方按三态 owner 解析（脚本态共享 Default 目录、用户态独立
    目录）。``overlay`` 为当前用户的覆盖层字段，随恢复前存底一起归档。
    返回该备份的覆盖层字段（供调用方回填 MAS 用户配置；旧版备份无侧车
    返回 ``None``），侧车文件随即从目录中分离删除，不留在 ConfigFile 里。
    """

    backup_dir = get_mas_backup_dir(script_id, user_id, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    mas_dir = Path(mas_dir)
    # 恢复前存底不设目录条件：目标目录缺失/为空时页面字段（overlay）仍需
    # 存底——恢复会清空目标，不存底就丢；无可归档内容由 archive 自判
    archive_mas_backup(script_id, user_id, mas_dir, overlay=overlay, force=True)
    restore_dir(mas_backup_root(script_id, user_id), ts, mas_dir)
    restored_overlay = read_overlay_sidecar(mas_dir)
    if restored_overlay is not None:
        (mas_dir / OVERLAY_SIDECAR_NAME).unlink(missing_ok=True)
    logger.info(f"用户 {user_id} 的 MAS 配置已恢复备份 {ts}")
    return restored_overlay


def archive_mas_runtime_backup(
    script_id: str,
    user_id: str,
    mas_dir: Path,
    overlay: dict | None = None,
) -> None:
    """运行 / 配置会话下发前归档 MAS 配置（下发源）到用户池。

    运行回写与会话保存会覆盖它，下发前存底；指纹去重，失败只记日志，
    绝不中止随后的运行或会话（归档是现场保护，不是前置条件）。
    ``user_id`` 是池归属；``mas_dir`` 是下发源目录，由调用方按当前用户
    三态解析（脚本态=Default 共享目录、用户态=独立目录；直控用户无 MAS
    配置，调用方不调用本函数）。native 池与此处无关：原生配置跨用户
    共享，由 manager ``prepare`` 在任务级一次性归档
    （见 :func:`archive_native_backup`）。
    """

    archive_mas_backup(script_id, user_id, mas_dir, overlay=overlay)


# ══════════════════ 脚本原生配置（working/configs 整目录） ══════════════════


def collect_native_files(config_path: str | Path) -> dict[str, Path]:
    """收集 ok-ww 原生 working 配置文件集（相对键 → 当前路径）。

    目录不存在或为空时无可归档内容，返回空 dict。
    """

    config_path = Path(config_path)
    if not config_path.is_dir() or not any(config_path.iterdir()):
        return {}
    return dir_files(config_path)


def archive_native_backup(config_path: Path, force: bool = False) -> Path | None:
    """归档 ok-ww 原生 working 配置当前状态（整目录）。

    归档落到该项目级池（按物理配置根指纹分桶），与脚本实例解耦。
    目录不存在或为空时无可归档内容，返回 ``None``。
    """

    files = collect_native_files(config_path)
    if not files:
        return None
    dest = archive_files(files, native_backup_root(config_path), force=force)
    if dest is None:
        logger.info("ok-ww 原生配置无变化，跳过归档")
        return None
    logger.info(f"ok-ww 原生配置已归档: {dest.name}")
    return dest


def list_native_backups(config_path: str | Path) -> list[str]:
    """ok-ww 原生配置全部归档时间戳（倒序，最新在前）。"""

    return list_times(native_backup_root(config_path))


def get_native_backup_dir(config_path: str | Path, ts: str) -> Path | None:
    """取指定时间戳的原生配置归档目录；不存在返回 None。"""

    return get_backup_dir(native_backup_root(config_path), ts)


def restore_native_backup(config_path: Path, ts: str) -> None:
    """把归档恢复到 ok-ww 原生配置位置（恢复前自动归档当前，误恢复可找回）。

    整目录替换（ok-ww 原生配置恒为目录，无 Folder/File 双模式）。
    """

    backup_dir = get_native_backup_dir(config_path, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    config_path = Path(config_path)
    # 恢复前强制归档当前——「恢复前的配置」在列表里有明确的时间戳条目
    archive_native_backup(config_path, force=True)
    restore_dir(native_backup_root(config_path), ts, config_path)
    logger.info(f"ok-ww 原生配置已恢复备份 {ts}")


# ══════════════════ 备份预览摘要 ══════════════════

_SUMMARY_ROW_LIMIT = 8
"""单文件摘要展示的最大字段行数"""

_SUMMARY_VALUE_LIMIT = 50
"""摘要字段值的最大字符数（超出截断）"""

CONFIG_DISPLAY_NAMES = {
    "DailyTask.json": "日常任务",
}
"""ok-ww 已知配置文件的展示名（未知文件回退文件名）"""

_FIELD_LABELS = {
    "Which to Farm": "消耗体力刷取",
    "Which Tacet Suppression to Farm": "F2 列表中的无音区序号",
    "Which Forgery Challenge to Farm": "F2 列表中的凝素领域序号",
    "Material Selection": "模拟领域材料",
    "Farm Nightmare Nest for Daily Echo": "需要时使用梦魇巢穴完成日常声骸",
    "Additional Tasks to Run After Daily Task": "每日任务后运行的附加任务",
}
"""MAS 快速配置覆盖层管理的字段中文标签（对齐编辑页词表）"""

_ENUM_VALUE_LABELS = {
    "Which to Farm": {
        "Tacet Suppression": "无音区",
        "Forgery Challenge": "凝素领域",
        "Simulation Challenge": "模拟领域",
    },
    "Material Selection": {
        "Resonator EXP": "共鸣者经验",
        "Weapon EXP": "武器经验",
        "Shell Credit": "贝币",
    },
    "Additional Tasks to Run After Daily Task": {
        "Check Weekly Garden": "检查每周乐园",
        "Auto Farm all Nightmare Nest": "自动刷所有梦魇巢穴",
        "Merge Echo If discarded > 1000": "已弃置声骸超过 1000 时融合",
        "Teleport and Farm 4C Echo": "传送并刷取 4C 声骸",
    },
}
"""枚举字段的取值中文词表（对齐编辑页选项；未知取值显示原文）"""

_PREVIEW_KEEP_FILES = ("DailyTask.json",)
"""native 池预览只保留 MAS 任务配置文件（ok-ww 直接消费的文件，文件值即
生效值），其余文件经「查看详细配置」恢复后在 ok-ww GUI 查看"""

_FILE_TO_OVERLAY_KEY = {
    "Which to Farm": "WhichToFarm",
    "Which Tacet Suppression to Farm": "WhichTacetSuppressionToFarm",
    "Which Forgery Challenge to Farm": "WhichForgeryChallengeToFarm",
    "Material Selection": "MaterialSelection",
    "Farm Nightmare Nest for Daily Echo": "FarmNightmareNestForDailyEcho",
    "Additional Tasks to Run After Daily Task": "AdditionalTasks",
}
"""DailyTask.json 文件字段名 → MAS 用户配置 Task 键名（同一概念的两种 owner）"""

_OVERLAY_FIELD_LABELS = {
    "Id": "账号",
    "Mode": "配置文件来源",
    **{overlay: _FIELD_LABELS[file] for file, overlay in _FILE_TO_OVERLAY_KEY.items()},
    "TaskIndex": "启动任务（-t N）",
}
"""覆盖层字段（侧车键名）中文标签，文件字段词表派生 + 页面专属键补充"""

_OVERLAY_ENUM_VALUE_LABELS = {
    overlay: _ENUM_VALUE_LABELS[file]
    for file, overlay in _FILE_TO_OVERLAY_KEY.items()
    if file in _ENUM_VALUE_LABELS
}
"""覆盖层枚举字段的取值中文词表，从文件字段词表派生"""


def _summary_value(key: str, value) -> str:
    """摘要标量值转展示文本（枚举词表翻译、布尔转是否、超长截断）。"""

    if isinstance(value, bool):
        return "是" if value else "否"
    enum = _ENUM_VALUE_LABELS.get(key)
    if enum is not None:
        text = enum.get(str(value), str(value))
    else:
        text = str(value)
    if len(text) > _SUMMARY_VALUE_LIMIT:
        return text[: _SUMMARY_VALUE_LIMIT - 1] + "…"
    return text


def _file_summary_rows(name: str, data: dict) -> list[dict]:
    """单个 JSON 配置文件的摘要行（仅 MAS 管理的字段，附加任务列表特殊展开）。

    预览的语义是「这个备份里 MAS 任务配置是什么样」，只展示 MAS 快速配置
    覆盖层管理的字段：ok-ww GUI 自有的其他字段（无中文词表）不进预览，
    经「查看详细配置」恢复后在 ok-ww GUI 里查看。
    """

    rows: list[dict] = []
    for key, value in data.items():
        if key not in _FIELD_LABELS:
            continue
        if isinstance(value, list):
            # 附加任务列表展开为顿号串（空列表明确显示「无」）
            joined = "、".join(
                _summary_value(key, item) if not isinstance(item, (dict, list)) else ""
                for item in value
            )
            rows.append({"key": _FIELD_LABELS[key], "value": joined or "无"})
            continue
        if isinstance(value, dict):
            continue
        rows.append({"key": _FIELD_LABELS[key], "value": _summary_value(key, value)})
        if len(rows) >= _SUMMARY_ROW_LIMIT:
            break
    return rows


def build_backup_file_summary(backup_dir: Path) -> list[dict]:
    """备份目录内 JSON 配置文件的摘要列表（预览用，纯读）。

    每个文件一条 ``{name, label, summary}``：label 用 ok-ww 配置展示名
    （未知文件回退文件名），summary 只取 MAS 管理的字段。只保留预览
    白名单内的文件，非 JSON / 坏 JSON / 无可展示字段的文件跳过（恢复时
    仍会随备份完整写回）。
    """

    files: list[dict] = []
    for rel in sorted(dir_files(backup_dir)):
        if "/" in rel or rel not in _PREVIEW_KEEP_FILES:
            continue
        try:
            data = json.loads((backup_dir / rel).read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        rows = _file_summary_rows(rel, data)
        if not rows:  # 无可展示字段的文件不进预览
            continue
        files.append(
            {
                "name": rel,
                "label": CONFIG_DISPLAY_NAMES.get(rel, rel),
                "summary": rows,
            }
        )
    return files


def _overlay_value(key: str, value) -> str:
    """覆盖层字段值转展示文本（账号脱敏、枚举词表翻译、布尔转是否、超长截断）。"""

    if key == "Id":
        return mask_account(value)  # 账号脱敏展示；侧车原值仍完整保存（恢复需要）
    if isinstance(value, bool):
        return "是" if value else "否"
    enum = _OVERLAY_ENUM_VALUE_LABELS.get(key)
    text = enum.get(str(value), str(value)) if enum is not None else str(value)
    if len(text) > _SUMMARY_VALUE_LIMIT:
        return text[: _SUMMARY_VALUE_LIMIT - 1] + "…"
    return text


def build_overlay_summary(overlay: dict) -> list[dict]:
    """侧车字段的摘要行（mas 池预览用，纯读）。

    展示的是备份时点的 MAS 页面表单值（账号 + 快速配置覆盖层字段），与
    用户在任务配置卡片所见同源，运行时才会覆盖进 DailyTask.json。
    """

    rows: list[dict] = []
    if "Mode" in overlay:
        rows.append(
            {
                "key": _OVERLAY_FIELD_LABELS["Mode"],
                "value": _overlay_value("Mode", overlay["Mode"]),
            }
        )
    if "Id" in overlay:
        rows.append({"key": "账号", "value": _overlay_value("Id", overlay["Id"])})
    for key in _OVERLAY_TASK_KEYS:
        if key not in overlay or key not in _OVERLAY_FIELD_LABELS:
            continue
        value = overlay[key]
        if isinstance(value, list):
            joined = "、".join(
                _overlay_value(key, item)
                for item in value
                if isinstance(item, (str, int, float, bool))
            )
            rows.append({"key": _OVERLAY_FIELD_LABELS[key], "value": joined or "无"})
            continue
        rows.append(
            {"key": _OVERLAY_FIELD_LABELS[key], "value": _overlay_value(key, value)}
        )
    return rows
