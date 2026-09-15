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

"""SRC 配置备份归档：MAS 用户配置（ConfigFile + 页面字段侧车）/ SRC 原生配置。

备份时机（MAS「动手前」，此时 SRC 配置尚未被触碰）：

- 任务 / 配置会话启动（manager ``prepare``）：``native`` 归档 SRC 安装
  目录 ``config/`` 当前状态（整目录）——安装配置物理上跨用户共享，只在
  任务级归档一次；下发处按用户归档会把上一轮下发的 MAS 配置误当原生
  内容挤进保留池；
- 运行 / 配置会话下发前（AutoProxy / ScriptConfig 的 ``set_src``）：
  ``mas`` 归档本轮下发源（脚本态共享 Default 目录、用户态当前用户目录，
  按 owner 各归各的；运行回写与会话保存会覆盖它）；
- 编辑界面进入 / 退出（前端 ensure）：进入时归档 ``native``（MAS 触碰前
  原始态）、退出时归档 ``mas``（编辑会话包络的 MAS 侧终态）。

``mas`` 池的内容 = ConfigFile 整目录 + **页面核心字段侧车**（Stage 段 +
Info 的 Server/Mode）：Stage 字段与 Server（注入 PackageName）运行时才写进
src.json、不落盘在 ConfigFile——侧车让「MAS 用户配置备份」与页面认知一致，
恢复时随文件一起回滚并按段分组回填表单。Mode（配置文件来源）决定恢复目标
目录，只进侧车与预览、不回填；Id/Password/前后置脚本/通知由 MAS 自己消费
（登录与执行域），不属于 SRC 配置内容，不进备份。池恒按用户分桶
（``mas/{user_id}``），脚本态多用户共享同一份 Default 目录时各自持有快照、
互不混淆。

``native`` 池 = SRC 安装目录 ``config/`` 整目录（src.json + deploy.yaml +
模板），按物理配置根指纹分桶、跨脚本共享、不随脚本删除。**恢复守卫（SRC
特有）**：manager 的任务级 Temp 快照（``Temp.ready`` 提交标记）在下次任务
开始时会把旧快照回滚覆盖 config/——残留待恢复快照时拒绝恢复，提示先完成
一次任务。

时间戳快照、指纹去重、保留清理与整目录恢复由公共模块
``app.utils.config_archive`` 提供（默认每池保留 10 份），本模块只保留
SRC 特有的目录布局、侧车、恢复语义（恢复前强制归档当前）、Temp 快照
守卫与预览摘要。
"""

import json
from pathlib import Path

from app.task.SRC.tools.config import is_src_config_available
from app.utils import get_logger
from app.utils.config_archive import (
    OVERLAY_SIDECAR_NAME,
    archive_files,
    config_root_key,
    dir_files,
    get_backup_dir,
    list_times,
    read_overlay_sidecar,
    restore_dir,
)
from app.utils.constants import STARRAIL_STAGE_BOOK

logger = get_logger("SRC 配置备份")

# ══════════════════ MAS 用户配置（池按用户，目标路径按 owner） ══════════════════

_OVERLAY_STAGE_KEYS = (
    "Channel",
    "Relic",
    "Materials",
    "Ornament",
    "ExtractReservedTrailblazePower",
    "UseFuel",
    "FuelReserve",
    "EchoOfWar",
    "SimulatedUniverseWorld",
)
"""MAS 页面关卡与开拓力字段（UserData.Stage，运行时注入 src.json）"""

_OVERLAY_INFO_KEYS = ("Server", "Mode")
"""MAS 页面基础字段（UserData.Info）：Server 注入 PackageName；Mode 仅预览"""

_OVERLAY_KEY_GROUPS = {"Info": _OVERLAY_INFO_KEYS, "Stage": _OVERLAY_STAGE_KEYS}
"""侧车字段的配置段归属（两组键名无交集，侧车内平铺存储）"""

_OVERLAY_KEY_GROUP = {
    key: group for group, keys in _OVERLAY_KEY_GROUPS.items() for key in keys
}

_OVERLAY_PREVIEW_ONLY_KEYS = {"Mode"}
"""仅预览不回填的字段：配置文件来源决定恢复目标目录，恢复时以当前值为准"""

_SERVER_LABELS = {
    "CN-Official": "官服",
    "CN-Bilibili": "B服",
    "VN-Official": "越南服",
    "OVERSEA-America": "美服",
    "OVERSEA-Asia": "亚服",
    "OVERSEA-Europe": "欧服",
    "OVERSEA-TWHKMO": "港澳台服",
}
"""服务器枚举 → 中文（对齐编辑页 serverOptions）"""

_PACKAGE_LABELS = {
    "com.miHoYo.hkrpg": "官服",
    "com.miHoYo.hkrpg.bilibili": "B服",
    "com.HoYoverse.hkrpgvn": "越南服",
    "com.HoYoverse.hkrpgoversea": "国际服",
}
"""SRC 原生配置 PackageName → 服名（国际服多服区共用包名，合并展示）"""

_CHANNEL_LABELS = {"Relic": "遗器", "Materials": "材料", "Ornament": "饰品"}
"""刷取类型枚举 → 中文（对齐编辑页选项）"""


def read_overlay_values(config) -> dict:
    """读取配置对象的 MAS 页面核心字段（鸭子类型，仅需 ``get(group, key)``）。

    覆盖 Stage 段全部字段与 Info 的 Server/Mode；值为 ``None``（配置项
    不存在）的键不纳入侧车。
    """

    values: dict = {}
    for group, keys in _OVERLAY_KEY_GROUPS.items():
        for key in keys:
            if (value := config.get(group, key)) is not None:
                values[key] = value
    return values


def group_overlay(overlay: dict) -> dict[str, dict]:
    """把平铺的侧车字段按配置段分组（恢复回填 UserData 用）。

    仅预览字段（配置文件来源）不回填：恢复目标目录由当前模式决定，
    回填旧值会静默改变脚本态/用户态。
    """

    grouped: dict[str, dict] = {}
    for key, value in overlay.items():
        if key in _OVERLAY_PREVIEW_ONLY_KEYS:
            continue
        grouped.setdefault(_OVERLAY_KEY_GROUP.get(key, "Stage"), {})[key] = value
    return grouped


def backup_root(script_id: str) -> Path:
    """某脚本的备份归档根目录（MAS 用户池用）：``data/{script_id}/SrcBackups``。"""

    return Path.cwd() / "data" / script_id / "SrcBackups"


def mas_backup_root(script_id: str, user_id: str) -> Path:
    """MAS 池归档根：``data/{script_id}/SrcBackups/mas/{user_id}``。

    **恒按用户分桶**——脚本态多用户共享 Default 下发源，但每个用户要
    看到、恢复自己的备份；池与恢复目标解耦（目标路径见
    :func:`mas_config_dir`，由 Info.Mode 决定 Default 或用户目录）。
    """

    return backup_root(script_id) / "mas" / user_id


def mas_config_dir(script_id: str, owner: str) -> Path:
    """MAS 配置目录：``data/{script_id}/{owner}/ConfigFile``。"""

    return Path.cwd() / "data" / script_id / owner / "ConfigFile"


def collect_mas_files(mas_dir: Path) -> dict[str, Path]:
    """收集 MAS 配置目录文件集（目录缺失或为空返回空 dict）。

    供声明式池声明归档内容（``files`` 回调）；:func:`archive_mas_backup`
    亦复用本函数收集目录部分。
    """

    mas_dir = Path(mas_dir)
    if not mas_dir.is_dir() or not any(mas_dir.iterdir()):
        return {}
    return dir_files(mas_dir)


def archive_mas_backup(
    script_id: str,
    user_id: str,
    mas_dir: Path,
    overlay: dict | None = None,
    force: bool = False,
) -> Path | None:
    """归档 MAS 配置整份 + 页面核心字段侧车到用户池（指纹去重，无变化跳过）。

    ``user_id`` 是池归属（恒按用户分桶）；``mas_dir`` 是归档/恢复目标
    路径，由调用方按三态 owner 解析（脚本态共享 Default 目录、用户态
    独立目录）——池与目标解耦。侧车参与指纹：只改页面配置、未动
    ConfigFile 时同样新建归档（内存 JSON 写入，免临时文件）。目录不存在
    或为空时无可恢复内容，返回 ``None``；``force=True`` 恢复前存底
    （内容与最新份一致时同样跳过）。
    """

    files = dict(collect_mas_files(mas_dir))
    if overlay:
        files[OVERLAY_SIDECAR_NAME] = json.dumps(overlay, ensure_ascii=False, indent=2)
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
    路径，由调用方按三态 owner 解析。``overlay`` 为当前用户的页面核心
    字段，随恢复前存底一起归档。返回该备份的侧车（供调用方回填 MAS 用户
    配置；旧版备份无侧车返回 ``None``），侧车文件随即从目录中分离删除，
    不留在 ConfigFile 里。
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

    运行回写与会话保存会覆盖它，下发前存底；指纹去重，``mas_dir`` 由
    调用方按当前用户三态解析（脚本态=Default 共享目录、用户态=独立目录）。
    ``overlay`` 为当前用户的页面核心字段。native 池与此处无关：原生配置
    跨用户共享，由 manager ``prepare`` 在任务级一次性归档。
    """

    archive_mas_backup(script_id, user_id, mas_dir, overlay=overlay)


# ══════════════════ SRC 原生配置（安装目录 config/ 整目录） ══════════════════


def project_backup_root() -> Path:
    """SRC 备份的项目级根目录：``data/SrcBackups``。

    native（脚本原生配置）池挂在这里而不是脚本目录下——同一份物理安装
    可被多个脚本实例引用，原生备份按物理配置根指纹分桶、跨脚本共享、
    不随脚本删除（mas 用户池仍按脚本，见 :func:`mas_backup_root`）。
    """

    return Path.cwd() / "data" / "SrcBackups"


def native_backup_root(config_path: str | Path) -> Path:
    """SRC 原生配置的项目级归档目录：``data/SrcBackups/native/{key}``。

    ``key`` 是物理配置根的指纹（:func:`config_root_key`）——同一份物理
    配置无论被哪个脚本引用都归同一个池；跨脚本共享、不随脚本删除。
    """

    return project_backup_root() / "native" / config_root_key(config_path)


def collect_native_files(config_path: str | Path) -> dict[str, Path]:
    """收集 SRC 安装目录 config/ 文件集（目录缺失或配置入口不可解析返回空 dict）。

    供声明式池声明归档内容（``files`` 回调）；:func:`archive_native_backup`
    亦复用本函数。
    """

    config_path = Path(config_path)
    if not config_path.is_dir() or not is_src_config_available(config_path):
        return {}
    return dir_files(config_path)


def archive_native_backup(config_path: Path, force: bool = False) -> Path | None:
    """归档 SRC 安装目录 config/ 当前状态（整目录）。

    归档落到该项目级池（按物理配置根指纹分桶），与脚本实例解耦。
    目录不存在或配置入口不可解析（损坏）时无可归档内容，返回 ``None``。
    """

    config_path = Path(config_path)
    files = collect_native_files(config_path)
    if not files:
        return None
    dest = archive_files(files, native_backup_root(config_path), force=force)
    if dest is None:
        logger.info("SRC 原生配置无变化，跳过归档")
        return None
    logger.info(f"SRC 原生配置已归档: {dest.name}")
    return dest


def list_native_backups(config_path: str | Path) -> list[str]:
    """SRC 原生配置全部归档时间戳（倒序，最新在前）。"""

    return list_times(native_backup_root(config_path))


def get_native_backup_dir(config_path: str | Path, ts: str) -> Path | None:
    """取指定时间戳的原生配置归档目录；不存在返回 None。"""

    return get_backup_dir(native_backup_root(config_path), ts)


def restore_native_backup(config_path: Path, ts: str, script_id: str) -> None:
    """把归档恢复到 SRC 安装目录 config/（恢复前自动归档当前，误恢复可找回）。

    整目录替换。``script_id`` 用于 Temp 快照守卫：manager 的任务级快照
    残留（``data/{script_id}/Temp.ready``）意味着下次任务开始时会把旧
    快照回滚覆盖 config/——此时拒绝恢复，避免恢复结果被冲掉。
    """

    backup_dir = get_native_backup_dir(config_path, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    temp_ready_path = Path.cwd() / "data" / script_id / "Temp.ready"
    if temp_ready_path.exists():
        raise ValueError(
            "检测到 SRC 待恢复的配置快照，请先完成一次 SRC 任务后再恢复配置"
        )
    config_path = Path(config_path)
    # 恢复前强制归档当前——「恢复前的配置」在列表里有明确的时间戳条目
    archive_native_backup(config_path, force=True)
    restore_dir(native_backup_root(config_path), ts, config_path)
    logger.info(f"SRC 原生配置已恢复备份 {ts}")


# ══════════════════ 备份预览摘要 ══════════════════

_SUMMARY_VALUE_LIMIT = 50
"""摘要字段值的最大字符数（超出截断）"""


def _summary_text(value) -> str:
    text = str(value)
    if len(text) > _SUMMARY_VALUE_LIMIT:
        return text[: _SUMMARY_VALUE_LIMIT - 1] + "…"
    return text


def _stage_text(value) -> str:
    """关卡/枚举值转中文（MAS 自持词表 STARRAIL_STAGE_BOOK；未知值显示原文）。"""

    return STARRAIL_STAGE_BOOK.get(str(value), str(value))


def build_overlay_preview(overlay: dict) -> dict:
    """mas 池预览：分区行（MAS 独有 = 配置文件来源；SRC 配置 = 页面核心字段）。"""

    def _row(key: str, value) -> dict:
        return {"key": key, "value": _summary_text(value)}

    sections: list[dict] = []

    mas_rows: list[dict] = []
    if "Mode" in overlay:
        mas_rows.append(_row("配置文件来源", overlay["Mode"]))
    if mas_rows:
        sections.append({"name": "mas-only", "label": "MAS 独有配置", "rows": mas_rows})

    src_rows: list[dict] = []
    if "Server" in overlay:
        src_rows.append(
            _row(
                "服务器", _SERVER_LABELS.get(str(overlay["Server"]), overlay["Server"])
            )
        )
    if "Channel" in overlay:
        src_rows.append(
            _row(
                "刷取类型",
                _CHANNEL_LABELS.get(str(overlay["Channel"]), overlay["Channel"]),
            )
        )
    for key, label in (
        ("Relic", "遗器关卡"),
        ("Materials", "材料关卡"),
        ("Ornament", "饰品关卡"),
        ("EchoOfWar", "历战余响关卡"),
        ("SimulatedUniverseWorld", "模拟宇宙世界"),
    ):
        if key in overlay:
            src_rows.append(_row(label, _stage_text(overlay[key])))
    if "ExtractReservedTrailblazePower" in overlay:
        src_rows.append(
            _row(
                "使用储备开拓力",
                "开启" if bool(overlay["ExtractReservedTrailblazePower"]) else "关闭",
            )
        )
    if "UseFuel" in overlay:
        src_rows.append(
            _row("使用燃料", "开启" if bool(overlay["UseFuel"]) else "关闭")
        )
    if "FuelReserve" in overlay:
        src_rows.append(_row("保留燃料", overlay["FuelReserve"]))
    if src_rows:
        sections.append({"name": "src", "label": "SRC 配置", "rows": src_rows})

    return {"sections": sections}


def _read_backup_src_json(backup_dir: Path) -> dict | None:
    """读归档内的 SRC 主配置 JSON（优先 src.json，回退非模板 json、模板 json）。

    全新安装从未生成 src.json 时归档内只有 template.json（下次运行就按它
    生成主配置）——回退读它，预览显示模板默认值而非「无法解析」。
    """

    candidates = [backup_dir / "src.json", *sorted(backup_dir.glob("*.json"))]
    fallback: dict | None = None
    for path in candidates:
        if not path.is_file():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:  # noqa: BLE001 - 坏 JSON 不阻断预览
            continue
        if not isinstance(data, dict):
            continue
        if path.name != "template.json":
            return data
        if fallback is None:
            fallback = data
    return fallback


def build_native_preview(config_path: str | Path, ts: str) -> dict:
    """native 池预览：反读备份内 src.json 关键字段（与 mas 池同口径）。

    反读范围：目标设备 / 服务器（包名反查）、各副本调度开关与关卡
    （词表 STARRAIL_STAGE_BOOK，do_not_use=未启用）、后备开拓力三项；
    其余内部字段不进预览。
    """

    backup_dir = get_native_backup_dir(config_path, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")

    data = _read_backup_src_json(backup_dir)
    rows: list[dict] = []
    if not isinstance(data, dict):
        rows.append({"key": "配置内容", "value": "无法解析（非 JSON 对象）"})
        return {"sections": [{"name": "src", "label": "SRC 配置", "rows": rows}]}

    alas = data.get("Alas") or {}
    emulator = alas.get("Emulator") or {}
    if emulator.get("Serial"):
        rows.append({"key": "目标设备", "value": _summary_text(emulator["Serial"])})
    if emulator.get("PackageName"):
        rows.append(
            {
                "key": "服务器",
                "value": _PACKAGE_LABELS.get(
                    str(emulator["PackageName"]), _summary_text(emulator["PackageName"])
                ),
            }
        )

    dungeon = data.get("Dungeon") or {}
    dungeon_stage = dungeon.get("Dungeon") or {}
    rows.append(
        {
            "key": "每日副本",
            "value": "开启"
            if (dungeon.get("Scheduler") or {}).get("Enable")
            else "关闭",
        }
    )
    if dungeon_stage.get("NameAtDoubleRelic") not in (None, "do_not_use"):
        rows.append(
            {
                "key": "遗器关卡",
                "value": _stage_text(dungeon_stage["NameAtDoubleRelic"]),
            }
        )
    if dungeon_stage.get("NameAtDoubleCalyx") not in (None, "do_not_use"):
        rows.append(
            {
                "key": "材料关卡",
                "value": _stage_text(dungeon_stage["NameAtDoubleCalyx"]),
            }
        )
    if dungeon_stage.get("Name") not in (None,):
        rows.append({"key": "主副本关卡", "value": _stage_text(dungeon_stage["Name"])})

    trailblaze = dungeon.get("TrailblazePower") or {}
    if "ExtractReservedTrailblazePower" in trailblaze:
        rows.append(
            {
                "key": "使用储备开拓力",
                "value": "开启"
                if bool(trailblaze["ExtractReservedTrailblazePower"])
                else "关闭",
            }
        )
    if "UseFuel" in trailblaze:
        rows.append(
            {
                "key": "使用燃料",
                "value": "开启" if bool(trailblaze["UseFuel"]) else "关闭",
            }
        )
    if "FuelReserve" in trailblaze:
        rows.append(
            {"key": "保留燃料", "value": _summary_text(trailblaze["FuelReserve"])}
        )

    ornament = data.get("Ornament") or {}
    ornament_stage = ornament.get("Ornament") or {}
    rows.append(
        {
            "key": "饰品提取",
            "value": "开启"
            if (ornament.get("Scheduler") or {}).get("Enable")
            else "关闭",
        }
    )
    if ornament_stage.get("Dungeon") not in (None, "do_not_use"):
        rows.append(
            {"key": "饰品关卡", "value": _stage_text(ornament_stage["Dungeon"])}
        )

    weekly = data.get("Weekly") or {}
    weekly_stage = weekly.get("Weekly") or {}
    rows.append(
        {
            "key": "历战余响",
            "value": "开启"
            if (weekly.get("Scheduler") or {}).get("Enable")
            else "关闭",
        }
    )
    if weekly_stage.get("Name") not in (None, "do_not_use"):
        rows.append({"key": "历战余响关卡", "value": _stage_text(weekly_stage["Name"])})

    rogue = data.get("Rogue") or {}
    rogue_world = rogue.get("RogueWorld") or {}
    rows.append(
        {
            "key": "模拟宇宙",
            "value": "开启" if (rogue.get("Scheduler") or {}).get("Enable") else "关闭",
        }
    )
    if rogue_world.get("World") not in (None, "do_not_use"):
        rows.append({"key": "模拟宇宙世界", "value": _stage_text(rogue_world["World"])})

    return {"sections": [{"name": "src", "label": "SRC 配置", "rows": rows}]}
