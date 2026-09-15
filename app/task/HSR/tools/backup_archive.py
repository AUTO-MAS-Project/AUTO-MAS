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

"""HSR 配置备份归档：MAS 用户字段侧车 / M7A+SRA 两引擎原生配置。

HSR 是唯一一对多专项（一个 ScriptType 编排 M7A 与 SRA 两个上游程序）。
备份时机（MAS「动手前」）：

- 任务启动（manager ``prepare``）：``native`` 归档 M7A ``config.yaml`` +
  SRA ``settings.json``/``cache.json``/``configs/``——运行会把托管字段写进
  这些文件、任务结束按运行期备份清单还原，崩溃残留会污染原生配置，持久
  归档提供跨会话找回；
- 编辑界面进入 / 退出（前端 ensure）：进入时归档 ``native``、退出时归档
  ``mas``（编辑会话包络的 MAS 侧终态）。

``mas`` 池是**纯字段侧车**（HSR 无 per-user 目录，用户配置即字段），
收录 **MAS 用户配置全量**（对齐 MAA「MAS 独有配置全量进侧车」口径）：
Info（名称/状态/服务器/剩余天数/前后脚本/备注）、TaskSwitch 任务开关、
Stage 副本配置（含原生关卡 JSON）、TaskOpt、Notify 通知、Control 引擎
开关、Managed.TaskMapping/Options（托管覆盖值，运行时物化进原生）、
Direct.*ImportedAt/Source（直控快照元数据）。侧车内平铺键为
``组.键``（如 ``TaskSwitch.Daily``）。**不收录**：Info.Id/Password（加密
凭据）、Direct.SRAConfig/M7AConfig（加密快照内容，API 不外泄）、
IfQuickConfig（HSR 不支持快速配置，死开关）、Info.Tag（虚拟字段）、
Data.*（运行统计与完成态，恢复配置不恢复统计）、Notify.CustomWebhooks
（子表结构）。Info.Mode 仅预览不回填（回填旧来源会翻转脚本态/用户态/
直控）。恢复即字段回填。

``native`` 池 = M7A ``config.yaml`` + SRA ``settings.json``/``cache.json``/
``configs/``，按 **SRA appdata 根的指纹分桶**（SRA appdata 是多脚本共享
目录，必须 config_root_key 分桶跨脚本共享、不随脚本删除——M7A config.yaml
随 SRA 池一并归档，HSR 脚本通常成对配两引擎）。

时间戳快照、指纹去重、保留清理与文件/目录恢复由公共模块
``app.utils.config_archive`` 提供（默认每池保留 10 份），本模块只保留
HSR 特有的两引擎目标解析、侧车、恢复语义（恢复前强制归档当前）与预览。
"""

import json
from pathlib import Path

import yaml

from app.utils import get_logger
from app.utils.config_archive import (
    archive_files,
    config_root_key,
    dir_files,
    get_backup_dir,
    list_times,
)

from .managed_config import SRA_REWARD_LABELS
from .sra_runtime import build_sra_tasklist_description

logger = get_logger("HSR 配置备份")

# ══════════════════ MAS 用户字段侧车（纯侧车，无目录） ══════════════════

_OVERLAY_SIDECAR_NAME = "_mas_overlay.json"
"""页面核心字段侧车文件名（归档内唯一文件；恢复时读出回填，不落任何目录）"""

_OVERLAY_KEY_GROUPS: dict[str, tuple[str, ...]] = {
    "Info": (
        "Mode",
        "Name",
        "Status",
        "Server",
        "RemainedDay",
        "IfScriptBeforeTask",
        "ScriptBeforeTask",
        "IfScriptAfterTask",
        "ScriptAfterTask",
        "Notes",
    ),
    "TaskSwitch": ("Daily", "ReceiveRewards", "DivergentUniverse", "CurrencyWars"),
    "Stage": ("Channel", "ScriptStage", "ScriptEchoOfWar"),
    "TaskOpt": ("EchoOfWarWeekday",),
    "Notify": (
        "Enabled",
        "IfSendStatistic",
        "IfSendMail",
        "ToAddress",
        "IfServerChan",
        "ServerChanKey",
    ),
    "Control": ("SRA", "M7A"),
    "Managed": ("TaskMapping", "Options"),
    "Direct": ("SRAImportedAt", "M7AImportedAt", "SRASource", "M7ASource"),
}
"""侧车收录的配置段与键（MAS 用户配置全量，见模块 docstring 的排除清单）。

侧车内平铺键为 ``组.键``——Info.Mode 与 Control.Mode 历史同名，裸键平铺
会互相覆盖；前缀形式也便于 group_overlay 按段解析。
"""

_OVERLAY_PREVIEW_ONLY_KEYS = {"Info.Mode"}
"""仅预览不回填的字段：配置来源决定运行方式，恢复时以当前值为准"""

_OVERLAY_FIELD_LABELS: dict[tuple[str, str], str] = {
    ("Info", "Mode"): "配置来源",
    ("Info", "Name"): "用户名",
    ("Info", "Status"): "启用状态",
    ("Info", "Server"): "服务器",
    ("Info", "RemainedDay"): "剩余天数",
    ("Info", "IfScriptBeforeTask"): "任务前脚本",
    ("Info", "ScriptBeforeTask"): "任务前脚本路径",
    ("Info", "IfScriptAfterTask"): "任务后脚本",
    ("Info", "ScriptAfterTask"): "任务后脚本路径",
    ("Info", "Notes"): "备注",
    ("TaskSwitch", "Daily"): "每日",
    ("TaskSwitch", "ReceiveRewards"): "领取奖励",
    ("TaskSwitch", "DivergentUniverse"): "差分宇宙",
    ("TaskSwitch", "CurrencyWars"): "货币战争",
    ("Stage", "Channel"): "体力类型",
    ("Stage", "ScriptStage"): "主副本",
    ("Stage", "ScriptEchoOfWar"): "历战余响副本",
    ("TaskOpt", "EchoOfWarWeekday"): "历战余响开始星期",
    ("Notify", "Enabled"): "通知",
    ("Notify", "IfSendStatistic"): "发送统计",
    ("Notify", "IfSendMail"): "邮件通知",
    ("Notify", "ToAddress"): "收件地址",
    ("Notify", "IfServerChan"): "Server 酱",
    ("Notify", "ServerChanKey"): "Server 酱密钥",
    ("Control", "SRA"): "SRA 引擎开关",
    ("Control", "M7A"): "M7A 引擎开关",
    ("Managed", "TaskMapping"): "任务映射",
    ("Managed", "Options"): "托管覆盖",
    ("Direct", "SRAImportedAt"): "SRA 快照导入时间",
    ("Direct", "M7AImportedAt"): "M7A 快照导入时间",
    ("Direct", "SRASource"): "SRA 快照来源",
    ("Direct", "M7ASource"): "M7A 快照来源",
}
"""侧车字段中文标签（对齐 HSR 编辑页词表）"""

# 侧车预览脱敏的键（回填完整值，预览不外泄）
_OVERLAY_SECRET_FLAT_KEYS = {"Notify.ToAddress", "Notify.ServerChanKey"}

_STAGE_CHANNEL_LABELS = {
    "CalyxGolden": "拟造花萼（金）",
    "CalyxCrimson": "拟造花萼（赤）",
    "Relic": "侵蚀隧洞",
    "Ornament": "饰品提取",
}
"""Stage.Channel 取值（HSRUserConfig OptionsValidator 值域）"""

_STAGE_WEEKDAY_LABELS = {
    "Monday": "周一",
    "Tuesday": "周二",
    "Wednesday": "周三",
    "Thursday": "周四",
    "Friday": "周五",
    "Saturday": "周六",
    "Sunday": "周日",
}
"""TaskOpt.EchoOfWarWeekday 取值（HSRUserConfig OptionsValidator 值域）"""

_STAGE_SERVER_LABELS = {"CN-Official": "官服"}
"""Info.Server 取值（HSRUserConfig 值域，与 getTags 同款映射）"""

_TASKSWITCH_MODULE_LABELS = {
    "Daily": "每日",
    "ReceiveRewards": "领取奖励",
    "DivergentUniverse": "差分宇宙",
    "CurrencyWars": "货币战争",
}
"""TaskSwitch 模块键 → 中文（task_mapping 的模块中文名）"""


def read_overlay_values(config) -> dict:
    """读取配置对象的 MAS 用户配置字段（鸭子类型，仅需 ``get(group, key)``）。

    值为 ``None``（配置项不存在）的键不纳入侧车；平铺键为 ``组.键``。
    """

    values: dict = {}
    for group, keys in _OVERLAY_KEY_GROUPS.items():
        for key in keys:
            if (value := config.get(group, key)) is not None:
                values[f"{group}.{key}"] = value
    return values


def group_overlay(overlay: dict) -> dict[str, dict]:
    """把 ``组.键`` 平铺侧车按配置段分组（恢复回填 HSRUserConfig 用）。

    仅预览字段（配置来源）不回填：回填旧来源会静默翻转脚本态/用户态/直控。
    无组前缀的键（旧格式侧车）无法定位段，跳过不回填。
    """

    grouped: dict[str, dict] = {}
    for key, value in overlay.items():
        if key in _OVERLAY_PREVIEW_ONLY_KEYS:
            continue
        group, _, name = key.partition(".")
        if not name:
            continue
        grouped.setdefault(group, {})[name] = value
    return grouped


def read_overlay_sidecar(backup_dir: Path) -> dict | None:
    """读取归档内的页面核心字段侧车；不存在（旧版备份）或损坏返回 ``None``。"""

    sidecar = Path(backup_dir) / _OVERLAY_SIDECAR_NAME
    if not sidecar.is_file():
        return None
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def mas_backup_root(script_id: str, user_id: str) -> Path:
    """MAS 池归档根：``data/{script_id}/HSRBackups/mas/{user_id}``（恒按用户）。"""

    return Path.cwd() / "data" / script_id / "HSRBackups" / "mas" / user_id


def archive_mas_backup(
    script_id: str, user_id: str, overlay: dict | None, force: bool = False
) -> Path | None:
    """归档页面核心字段侧车到用户池（指纹去重，无变化跳过）。

    侧车以内存 JSON 直接入档（:func:`archive_files` 支持内存内容），免临时
    文件。
    """

    if not overlay:
        return None
    dest = archive_files(
        {_OVERLAY_SIDECAR_NAME: json.dumps(overlay, ensure_ascii=False, indent=2)},
        mas_backup_root(script_id, user_id),
        force=force,
    )
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


def restore_mas_backup(script_id: str, user_id: str, ts: str) -> dict | None:
    """读取用户池归档的侧车（供调用方回填 HSRUserConfig）；无目录目标。"""

    backup_dir = get_mas_backup_dir(script_id, user_id, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    return read_overlay_sidecar(backup_dir)


def archive_mas_runtime_backup(script_id: str, user_id: str, overlay: dict) -> None:
    """运行物化前归档本用户字段侧车（物化会写原生配置，字段本身先存底）。"""

    archive_mas_backup(script_id, user_id, overlay)


# ══════════════════ M7A + SRA 原生配置（两引擎） ══════════════════

_M7A_CONFIG_FILE = "M7A/config.yaml"
"""归档内 M7A 配置的相对键"""

_SRA_SETTINGS_FILE = "SRA/settings.json"
_SRA_CACHE_FILE = "SRA/cache.json"
_SRA_CONFIGS_DIR = "SRA/configs"
"""归档内 SRA 配置的相对键"""


def native_backup_root(sra_app_data: str | Path) -> Path:
    """HSR 原生配置的项目级归档根：``data/HSRBackups/native/{key}``。

    ``key`` 是 **SRA appdata 根**的指纹（:func:`config_root_key`）——SRA
    appdata 是多脚本共享目录，按物理根分桶、跨脚本共享、不随脚本删除；
    M7A config.yaml 随 SRA 池一并归档（HSR 脚本通常成对配两引擎）。
    """

    return Path.cwd() / "data" / "HSRBackups" / "native" / config_root_key(sra_app_data)


def collect_native_files(m7a_root: Path | None, sra_app_data: Path) -> dict[str, Path]:
    """收集两引擎原生配置文件集（相对键 → 文件路径；缺失项跳过）。

    - ``M7A/config.yaml``：M7A 安装根下的配置文件；
    - ``SRA/settings.json`` / ``SRA/cache.json`` / ``SRA/configs/``：SRA
      appdata 共享目录下的配置（configs 为目录，整目录归档）。
    """

    files: dict[str, Path] = {}
    if m7a_root is not None:
        m7a_config = Path(m7a_root) / "config.yaml"
        if m7a_config.is_file():
            files[_M7A_CONFIG_FILE] = m7a_config
    sra_settings = sra_app_data / "settings.json"
    if sra_settings.is_file():
        files[_SRA_SETTINGS_FILE] = sra_settings
    sra_cache = sra_app_data / "cache.json"
    if sra_cache.is_file():
        files[_SRA_CACHE_FILE] = sra_cache
    sra_configs = sra_app_data / "configs"
    if sra_configs.is_dir():
        for rel, path in dir_files(sra_configs).items():
            files[f"{_SRA_CONFIGS_DIR}/{rel}"] = path
    return files


def archive_native_backup(
    m7a_root: Path | None, sra_app_data: Path, force: bool = False
) -> Path | None:
    """归档两引擎原生配置（指纹去重，无变化跳过）。全缺失时返回 ``None``。"""

    files = collect_native_files(m7a_root, sra_app_data)
    if not files:
        return None
    dest = archive_files(files, native_backup_root(sra_app_data), force=force)
    if dest is None:
        logger.info("HSR 原生配置无变化，跳过归档")
        return None
    logger.info(f"HSR 原生配置已归档: {dest.name}")
    return dest


def list_native_backups(sra_app_data: str | Path) -> list[str]:
    """HSR 原生配置全部归档时间戳（倒序，最新在前）。"""

    return list_times(native_backup_root(sra_app_data))


def get_native_backup_dir(sra_app_data: str | Path, ts: str) -> Path | None:
    """取指定时间戳的原生配置归档目录；不存在返回 None。"""

    return get_backup_dir(native_backup_root(sra_app_data), ts)


def restore_native_backup(m7a_root: Path | None, sra_app_data: Path, ts: str) -> None:
    """把归档恢复到两引擎原生位置（恢复前自动归档当前，误恢复可找回）。

    按归档内相对键写回：``M7A/*`` → M7A 安装根、``SRA/*`` → SRA appdata；
    只覆盖归档内包含的文件。
    """

    backup_dir = get_native_backup_dir(sra_app_data, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    files = dir_files(backup_dir)
    if not files:
        raise ValueError(f"备份内容为空: {ts}")
    archive_native_backup(m7a_root, sra_app_data, force=True)
    for rel, path in files.items():
        if rel.startswith("M7A/"):
            if m7a_root is None:
                continue
            target = Path(m7a_root) / rel[len("M7A/") :]
        else:
            target = sra_app_data / rel[len("SRA/") :]
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
    logger.info(f"HSR 原生配置已恢复备份 {ts}")


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


def _parse_json_dict(raw) -> dict:
    """解析 JSON 对象字符串字段（TaskMapping/Options），非法返回空 dict。"""

    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            loaded = json.loads(raw)
        except Exception:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _stage_label(raw, channel: str | None = None) -> str:
    """从 Stage 原生关卡 JSON 提取关卡显示名（label）。

    ``ScriptStage`` 含 ``stages`` 按体力类型分槽，取 ``channel`` 槽；
    ``ScriptEchoOfWar`` 为单槽顶层。缺失/损坏返回空串。
    """

    data = _parse_json_dict(raw)
    if not data:
        return ""
    if channel is not None:
        stages = data.get("stages")
        data = (
            stages.get(channel)
            if isinstance(stages, dict) and isinstance(stages.get(channel), dict)
            else data
        )
    return str(data.get("label") or "").strip()


def _overlay_row(flat_key: str, value) -> dict:
    """侧车字段 → 预览行；敏感键脱敏（回填完整值，预览不外泄）。"""

    label = _OVERLAY_FIELD_LABELS[tuple(flat_key.split(".", 1))]
    if flat_key in _OVERLAY_SECRET_FLAT_KEYS:
        value = "已设置（不显示）" if str(value).strip() else "未设置"
    return {"key": label, "value": _summary_text(value)}


def build_overlay_preview(overlay: dict) -> dict:
    """mas 池预览：MAS 用户配置全量分区（侧车收录什么就展示什么）。

    分区：MAS 独有配置（来源/服务器/脚本/直控引擎/备注）→ 任务配置
    （任务开关/副本）→ 通知 → 托管配置（映射/覆盖）→ 直控快照。
    """

    sections: list[dict] = []

    def has(group: str, key: str) -> bool:
        return f"{group}.{key}" in overlay

    mas_rows: list[dict] = []
    if has("Info", "Mode"):
        mas_rows.append(_overlay_row("Info.Mode", overlay["Info.Mode"]))
    if has("Info", "Server"):
        server = str(overlay["Info.Server"])
        mas_rows.append(
            {
                "key": "服务器",
                "value": _STAGE_SERVER_LABELS.get(server, server),
            }
        )
    if has("Info", "RemainedDay"):
        days = overlay["Info.RemainedDay"]
        mas_rows.append(
            {
                "key": "剩余天数",
                "value": "未设置" if days is None or int(days) < 0 else str(days),
            }
        )
    for enabled_key, path_key, label in (
        ("IfScriptBeforeTask", "ScriptBeforeTask", "任务前脚本"),
        ("IfScriptAfterTask", "ScriptAfterTask", "任务后脚本"),
    ):
        if not has("Info", enabled_key):
            continue
        value = "关闭"
        if overlay[f"Info.{enabled_key}"]:
            path = str(overlay.get(f"Info.{path_key}") or "").strip()
            value = f"启用 · {path}" if path else "启用"
        mas_rows.append({"key": label, "value": value})
    engines = [
        engine
        for engine in ("SRA", "M7A")
        if has("Control", engine) and overlay[f"Control.{engine}"]
    ]
    if has("Control", "SRA") or has("Control", "M7A"):
        mas_rows.append(
            {"key": "直控引擎", "value": "、".join(engines) if engines else "无"}
        )
    if has("Info", "Notes"):
        mas_rows.append(_overlay_row("Info.Notes", overlay["Info.Notes"]))
    if mas_rows:
        sections.append({"name": "mas-only", "label": "MAS 独有配置", "rows": mas_rows})

    task_rows: list[dict] = []
    if any(has("TaskSwitch", key) for key in _TASKSWITCH_MODULE_LABELS):
        enabled = [
            label
            for key, label in _TASKSWITCH_MODULE_LABELS.items()
            if overlay.get(f"TaskSwitch.{key}") is True
        ]
        task_rows.append(
            {"key": "任务开关", "value": "、".join(enabled) if enabled else "无"}
        )
    if has("Stage", "Channel"):
        channel = str(overlay["Stage.Channel"])
        task_rows.append(
            {
                "key": "体力类型",
                "value": _STAGE_CHANNEL_LABELS.get(channel, channel),
            }
        )
    if has("Stage", "ScriptStage"):
        label = _stage_label(
            overlay["Stage.ScriptStage"],
            str(overlay.get("Stage.Channel") or "") or None,
        )
        task_rows.append({"key": "主副本", "value": label or "未选择"})
    if has("Stage", "ScriptEchoOfWar"):
        label = _stage_label(overlay["Stage.ScriptEchoOfWar"])
        task_rows.append({"key": "历战余响副本", "value": label or "未选择"})
    if has("TaskOpt", "EchoOfWarWeekday"):
        weekday = str(overlay["TaskOpt.EchoOfWarWeekday"])
        task_rows.append(
            {
                "key": "历战余响开始星期",
                "value": _STAGE_WEEKDAY_LABELS.get(weekday, weekday),
            }
        )
    if task_rows:
        sections.append({"name": "tasks", "label": "任务配置", "rows": task_rows})

    if has("Notify", "Enabled"):
        notify_value = "关闭"
        if overlay["Notify.Enabled"]:
            channels = [
                label
                for key, label in (
                    ("IfSendStatistic", "统计"),
                    ("IfSendMail", "邮件"),
                    ("IfServerChan", "Server 酱"),
                )
                if overlay.get(f"Notify.{key}") is True
            ]
            notify_value = "、".join(channels) if channels else "开启"
        notify_rows: list[dict] = [{"key": "通知", "value": notify_value}]
        for secret_key in ("Notify.ToAddress", "Notify.ServerChanKey"):
            if secret_key in overlay:
                notify_rows.append(_overlay_row(secret_key, overlay[secret_key]))
        sections.append({"name": "notify", "label": "通知", "rows": notify_rows})

    managed_rows: list[dict] = []
    if "Managed.TaskMapping" in overlay:
        mapping = _parse_json_dict(overlay["Managed.TaskMapping"])
        managed_rows.append(
            {
                "key": "任务映射",
                "value": "、".join(f"{k}→{v}" for k, v in mapping.items()) or "无",
            }
        )
    if "Managed.Options" in overlay:
        options = _parse_json_dict(overlay["Managed.Options"])
        managed_rows.append({"key": "托管覆盖", "value": "、".join(options) or "无"})
    if managed_rows:
        sections.append({"name": "managed", "label": "托管配置", "rows": managed_rows})

    direct_rows: list[dict] = []
    for key in _OVERLAY_KEY_GROUPS["Direct"]:
        flat_key = f"Direct.{key}"
        if flat_key in overlay and str(overlay[flat_key]).strip():
            direct_rows.append(_overlay_row(flat_key, overlay[flat_key]))
    if direct_rows:
        sections.append({"name": "direct", "label": "直控快照", "rows": direct_rows})

    return {"sections": sections}


def build_native_preview(sra_app_data: str | Path, ts: str) -> dict:
    """native 池预览：两引擎常用配置反读 + 文件清单。

    反读范围只限 **MAS 侧有对应概念的常用字段**（托管表单/patch 白名单覆盖的
    键，词表固化、零本体运行时依赖）：

    - M7A ``config.yaml``：清体力/副本/历战余响/体力补充/培养目标/每日实训/
      领取奖励/兑换码/差分宇宙/货币战争/云游戏（键名以 MAS 托管白名单为准）；
    - SRA ``configs/*.json``：每档案一节——游戏渠道/清体力/任务清单/补充
      开拓力/领取奖励/差分宇宙/货币战争/完成后动作（键形为顶层 camelCase 段
      + 段内平铺点号键，见 SRA ``SRACore/models/tasks_config.py``，与 MAS
      ``_build_sra_base_config`` 写出口径一致；奖励开关兼容索引式与命名键）；
    - ``settings.json``/``cache.json`` 结构未经现场核实（后者为运行缓存），
      **不反读内容**，只在文件清单节展示。
    """

    backup_dir = get_native_backup_dir(sra_app_data, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    files = dir_files(backup_dir)
    if not files:
        raise ValueError(f"备份内容为空: {ts}")

    sections: list[dict] = []

    m7a_payload = _load_yaml_dict(backup_dir / "M7A" / "config.yaml")
    m7a_rows = _m7a_preview_rows(m7a_payload) if m7a_payload else []
    if m7a_rows:
        sections.append({"name": "m7a", "label": "M7A（三月七助手）", "rows": m7a_rows})

    for rel in sorted(files):
        if not rel.startswith(f"{_SRA_CONFIGS_DIR}/") or not rel.endswith(".json"):
            continue
        profile = _load_json_dict(files[rel])
        rows = _sra_profile_rows(profile) if profile else []
        if rows:
            stem = rel[len(_SRA_CONFIGS_DIR) + 1 : -len(".json")]
            sections.append(
                {"name": f"sra:{stem}", "label": f"SRA 配置档案 · {stem}", "rows": rows}
            )

    # 归档文件清单由 service.preview 统一注入标准 ``files`` 字段
    # （基座兜底），专项预览载荷只负责摘要 sections
    return {"sections": sections}


# ── 反读词表（固化，零本体运行时依赖；出处见行内注释）──────────────────

_M7A_PREVIEW_KEYS: tuple[tuple[str, str], ...] = (
    ("power_enable", "清体力"),
    ("build_target_enable", "培养目标"),
    ("daily_enable", "每日实训"),
    ("cloud_game_enable", "云游戏"),
)
"""M7A 平铺布尔键 → 行标签（键均在 MAS 托管白名单内，含义取自
config.example.yaml 行内注释）"""

_M7A_REWARD_SUB_LABELS: tuple[tuple[str, str], ...] = (
    ("reward_dispatch_enable", "委托"),
    ("reward_mail_enable", "邮件"),
    ("reward_assist_enable", "支援"),
    ("reward_quest_enable", "每日实训"),
    ("reward_srpass_enable", "无名勋礼"),
    ("reward_redemption_code_enable", "兑换码"),
    ("reward_achievement_enable", "成就"),
    ("reward_message_enable", "短信"),
)
"""M7A 领取奖励子开关 → 短标签（config.example.yaml 行内注释原文去尾）"""

_M7A_DIVERGENT_TYPE_LABELS = {"normal": "常规演算", "cycle": "周期演算"}
"""M7A weekly_divergent_type 取值（config.example.yaml：normal/cycle）"""

_M7A_CURRENCY_WARS_TYPE_LABELS = {"normal": "标准博弈", "overclock": "超频博弈"}
"""M7A currencywars_type 取值（config.example.yaml：normal/overclock）"""

_SRA_CHANNEL_LABELS = {0: "国服", 1: "B服", 2: "国际服"}
"""SRA startGame.game.channel 取值（SRA tasks/StartGameTask._game_channel：
0=cn、1=bl、2=gb）"""

_SRA_REPLENISH_WAY_LABELS = {0: "后备开拓力", 1: "燃料", 2: "星琼"}
"""SRA trailblazePower.replenish.way 取值（与托管表单 _SRA_SELECTS 同口径，
SRA TrailblazePowerTask.replenish）"""

_SRA_DIVERGENT_MODE_LABELS = {0: "常规演算", 1: "周期演算"}
"""SRA cosmicStrife.divergentUniverse.mode 取值（与托管表单 _SRA_SELECTS 同口径）"""

_SRA_CURRENCY_WARS_MODE_LABELS = {0: "标准博弈", 1: "超频博弈", 2: "刷开局"}
"""SRA cosmicStrife.currencyWars.mode 取值（与托管表单 _SRA_SELECTS 同口径）"""

_SRA_REWARD_KEY_ORDER = (
    "trailblazeProfile",
    "assignments",
    "mail",
    "dailyTraining",
    "namelessHonor",
    "giftOfOdyssey",
    "redeemCode",
)
"""SRA 命名式奖励开关的顺序（SRA ReceiveRewardsConfig，与
SRA_REWARD_LABELS 一一对应；索引式 rewards 列表按同序兼容读取）"""

_SRA_FINISH_ACTION_LABELS: tuple[tuple[str, str], ...] = (
    ("exitGame", "退出游戏"),
    ("logout", "登出"),
    ("shutdown", "关机"),
    ("sleep", "睡眠"),
    ("exitApp", "退出 SRA"),
)
"""SRA missionAccomplished 完成后动作开关 → 短标签（TasksConfig 键名直译）"""


def _load_json_dict(path: Path) -> dict | None:
    """容错读取 JSON 对象文件；缺失/损坏/非对象返回 ``None``。"""

    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _load_yaml_dict(path: Path) -> dict | None:
    """容错读取 YAML 对象文件；缺失/损坏/非对象返回 ``None``。"""

    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _join_bool_labels(payload: dict, pairs: tuple[tuple[str, str], ...]) -> str:
    """把启用的布尔子开关连成短标签串；全关返回「无」。"""

    enabled = [label for key, label in pairs if payload.get(key) is True]
    return "、".join(enabled) if enabled else "无"


def _m7a_preview_rows(payload: dict) -> list[dict]:
    """M7A config.yaml 常用字段行（只收录 MAS 白名单概念内的键）。"""

    rows: list[dict] = []

    def present(key: str) -> bool:
        return payload.get(key) is not None

    for key, label in _M7A_PREVIEW_KEYS:
        if present(key):
            rows.append({"key": label, "value": _format_bool(payload[key])})

    instance_type = payload.get("instance_type")
    if instance_type is not None:
        instance_names = payload.get("instance_names")
        name = (
            instance_names.get(instance_type, "")
            if isinstance(instance_names, dict)
            else ""
        )
        value = _summary_text(instance_type)
        if name and name != "无":
            value = f"{instance_type} · {name}"
        rows.append({"key": "副本", "value": value})

    if present("echo_of_war_enable"):
        value = _format_bool(payload["echo_of_war_enable"])
        instance_names = payload.get("instance_names")
        eow_name = (
            instance_names.get("历战余响", "")
            if isinstance(instance_names, dict)
            else ""
        )
        if payload.get("echo_of_war_enable") and eow_name and eow_name != "无":
            value = f"开启 · {eow_name}"
        rows.append({"key": "历战余响", "value": value})

    if present("use_reserved_trailblaze_power") or present("use_fuel"):
        supplements = []
        if payload.get("use_reserved_trailblaze_power"):
            supplements.append("后备开拓力")
        if payload.get("use_fuel"):
            supplements.append("燃料")
        rows.append(
            {
                "key": "体力补充",
                "value": "、".join(supplements) if supplements else "无",
            }
        )

    if present("reward_enable"):
        value = _format_bool(payload["reward_enable"])
        if payload.get("reward_enable"):
            subs = {
                key: payload.get(key)
                for key, _label in _M7A_REWARD_SUB_LABELS
                if payload.get(key) is not None
            }
            if subs:
                value = _join_bool_labels(subs, _M7A_REWARD_SUB_LABELS)
        rows.append({"key": "领取奖励", "value": value})

    codes = payload.get("redemption_code")
    if isinstance(codes, list):
        rows.append({"key": "兑换码", "value": f"{len(codes)} 个" if codes else "无"})

    if present("weekly_divergent_enable"):
        value = _format_bool(payload["weekly_divergent_enable"])
        if payload.get("weekly_divergent_enable"):
            parts = [
                _M7A_DIVERGENT_TYPE_LABELS.get(
                    str(payload.get("weekly_divergent_type"))
                )
                or str(payload.get("weekly_divergent_type") or "")
            ]
            if payload.get("weekly_divergent_level") is not None:
                parts.append(f"难度{payload['weekly_divergent_level']}")
            value = " · ".join(part for part in parts if part) or "开启"
        rows.append({"key": "差分宇宙", "value": value})

    if present("currencywars_enable"):
        value = _format_bool(payload["currencywars_enable"])
        if payload.get("currencywars_enable"):
            value = (
                _M7A_CURRENCY_WARS_TYPE_LABELS.get(
                    str(payload.get("currencywars_type"))
                )
                or "开启"
            )
        rows.append({"key": "货币战争", "value": value})

    return rows


def _sra_profile_rows(payload: dict) -> list[dict]:
    """SRA 档案常用字段行（顶层 camelCase 段 + 平铺点号键）。"""

    rows: list[dict] = []

    start_game = payload.get("startGame")
    if isinstance(start_game, dict) and start_game.get("game.channel") is not None:
        channel = start_game.get("game.channel")
        rows.append(
            {
                "key": "游戏渠道",
                "value": _SRA_CHANNEL_LABELS.get(channel, str(channel)),
            }
        )

    trailblaze = payload.get("trailblazePower")
    if isinstance(trailblaze, dict):
        if trailblaze.get("enabled") is not None:
            rows.append({"key": "清体力", "value": _format_bool(trailblaze["enabled"])})
        tasklist = trailblaze.get("tasklist")
        if isinstance(tasklist, list):
            description = build_sra_tasklist_description(tasklist) if tasklist else "无"
            rows.append(
                {
                    "key": "清体力任务清单",
                    "value": _summary_text(description),
                }
            )
        if trailblaze.get("replenish.enabled") is not None:
            value = "关闭"
            if trailblaze.get("replenish.enabled"):
                way = trailblaze.get("replenish.way")
                way_label = _SRA_REPLENISH_WAY_LABELS.get(
                    way, str(way if way is not None else "")
                )
                value = way_label or "开启"
                times = trailblaze.get("replenish.times")
                if isinstance(times, int) and times > 0:
                    value = f"{value} ×{times}"
            rows.append({"key": "补充开拓力", "value": value})

    rewards_section = payload.get("receiveRewards")
    if isinstance(rewards_section, dict):
        reward_values = _sra_reward_values(rewards_section)
        if reward_values is not None:
            enabled = [
                SRA_REWARD_LABELS[index]
                for index, flag in enumerate(reward_values)
                if flag
            ]
            rows.append(
                {"key": "领取奖励", "value": "、".join(enabled) if enabled else "无"}
            )

    cosmic = payload.get("cosmicStrife")
    if isinstance(cosmic, dict):
        if cosmic.get("divergentUniverse.enabled") is not None:
            value = "关闭"
            if cosmic.get("divergentUniverse.enabled"):
                mode = cosmic.get("divergentUniverse.mode")
                mode_label = _SRA_DIVERGENT_MODE_LABELS.get(
                    mode, str(mode if mode is not None else "")
                )
                value = mode_label or "开启"
                runtimes = cosmic.get("divergentUniverse.runtimes")
                if isinstance(runtimes, int) and runtimes > 0:
                    value = f"{value} ×{runtimes}"
            rows.append({"key": "差分宇宙", "value": value})
        if cosmic.get("currencyWars.enabled") is not None:
            value = "关闭"
            if cosmic.get("currencyWars.enabled"):
                mode = cosmic.get("currencyWars.mode")
                mode_label = _SRA_CURRENCY_WARS_MODE_LABELS.get(
                    mode, str(mode if mode is not None else "")
                )
                value = mode_label or "开启"
                runtimes = cosmic.get("currencyWars.runtimes")
                if isinstance(runtimes, int) and runtimes > 0:
                    value = f"{value} ×{runtimes}"
            rows.append({"key": "货币战争", "value": value})

    finish = payload.get("missionAccomplished")
    if isinstance(finish, dict):
        rows.append(
            {
                "key": "完成后动作",
                "value": _join_bool_labels(finish, _SRA_FINISH_ACTION_LABELS),
            }
        )

    return rows


def _sra_reward_values(section: dict) -> list[bool] | None:
    """读 SRA 奖励开关为布尔列表（SRA_REWARD_LABELS 顺序）。

    命名键（``rewards.<name>``）优先，缺失项回退索引式 ``rewards`` 列表——
    与 SRA ``ReceiveRewardsConfig.from_dict`` 的兼容口径一致。两类键都
    不存在时返回 ``None``（不渲染该行）。
    """

    legacy = section.get("rewards")
    legacy_values = (
        [bool(item) for item in legacy] if isinstance(legacy, list) else None
    )
    if legacy_values is not None:
        # 索引式按 SRA 语义补齐到定长：被改短的尾部按默认关闭处理
        legacy_values += [False] * (len(_SRA_REWARD_KEY_ORDER) - len(legacy_values))
    values: list[bool] = []
    has_named = False
    for index, name in enumerate(_SRA_REWARD_KEY_ORDER):
        named = section.get(f"rewards.{name}")
        if named is not None:
            has_named = True
            values.append(bool(named))
            continue
        if legacy_values is not None and len(legacy_values) > index:
            values.append(legacy_values[index])
        else:
            values.append(False)
    if has_named:
        return values
    return legacy_values
