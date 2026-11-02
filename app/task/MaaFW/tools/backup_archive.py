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

"""MaaFW 配置备份归档：MAS 用户字段侧车 / MaaFW 项目 config/。

备份时机（MAS「动手前」）：

- 任务启动（manager ``prepare``）：``native`` 归档 MaaFW 项目 ``config/``
  目录当前状态，归档必须在任何写入前；
- 编辑界面进入（前端 ensure）：``native`` 捕捉「MAS 操作前原始态」；
- 编辑界面退出（前端 ensure）：``mas`` 归档 MAS 编辑页核心字段终态。

MaaFW 与 M9A 同属 MaaFramework 线：没有 per-user ConfigFile 目录，MAS
用户配置是字段（Info / Task.SelectedPreset / Task.TaskSnapshot / Device 段，
存共享 ScriptConfig.json），运行时物化进项目配置。因此 ``mas`` 池是**纯
字段侧车**（无目录部分），恢复即字段回填 MaaFWUserConfig。``native`` 池 =
项目 ``config/`` 目录（maa_option.json 等 Toolkit 配置），按视图路径指纹分桶。

``interface.json`` 不进 native 池：载荷 + 视图之后它随项目版本走（换版本、重新导入
另一个项目时整份换掉），MAS 运行期不写它；视图路径永不变，桶里会同时有旧版本、甚至
另一个项目的备份，恢复它会让视图里的 interface 与资源、pipeline 版本对不上。早先的
备份里还带着它，恢复时跳过、预览时只作参考。

时间戳快照、指纹去重、保留清理与目录恢复由公共模块
``app.utils.common.config.archive`` 提供（默认每池保留 10 份），本模块只保留
MaaFW 特有的侧车、恢复语义（恢复前强制归档当前）与预览摘要。
"""

import json
from collections.abc import Callable, Mapping
from pathlib import Path

from app.task.MaaFW.tools.core.interface.loader import parse_json_text
from app.task.MaaFW.tools.core.interface.models import (
    DUPLICATE_TASK_SUFFIX_SEPARATOR,
    PRETASK_TASK_PREFIX,
)
from app.utils import BASE_SOURCE_LABELS, get_logger
from app.utils.common.config import archive as _utils_config_archive

OVERLAY_SIDECAR_NAME = _utils_config_archive.OVERLAY_SIDECAR_NAME
read_overlay_sidecar = _utils_config_archive.read_overlay_sidecar

logger = get_logger("MaaFW 配置备份")

# ══════════════════ MAS 用户字段侧车（纯侧车，无目录） ══════════════════

_OVERLAY_INFO_KEYS = ("Base", "IfQuickConfig", "Account", "Controller", "Resource")
"""MAS 编辑页核心字段（UserData.Info，运行时物化进项目配置）"""

_OVERLAY_TASK_KEYS = ("SelectedPreset", "TaskSnapshot")
"""任务快照（UserData.Task：当前 preset 名 + taskOrder/taskChecked/taskOptions JSON）"""

_OVERLAY_DEVICE_KEYS = (
    "AdbAddress",
    "HWnd",
    "PlayCoverAddress",
    "PlayCoverUuid",
)
"""设备覆盖字段（UserData.Device，运行时下发 controller）"""

_OVERLAY_KEY_GROUPS = {
    "Info": _OVERLAY_INFO_KEYS,
    "Task": _OVERLAY_TASK_KEYS,
    "Device": _OVERLAY_DEVICE_KEYS,
}
"""侧车字段的配置段归属（键名无交集，侧车内平铺存储）"""

_OVERLAY_KEY_GROUP = {
    key: group for group, keys in _OVERLAY_KEY_GROUPS.items() for key in keys
}

_OVERLAY_PREVIEW_ONLY_KEYS = {"Base"}
"""仅预览不回填的字段：配置来源决定运行下发方式，恢复时以当前值为准"""

_OVERLAY_FIELD_LABELS = {
    "Base": "配置来源",
    "IfQuickConfig": "启用快速配置",
    "Account": "账号",
    "Controller": "Controller",
    "Resource": "Resource",
    "SelectedPreset": "当前方案",
    "TaskSnapshot": "任务快照",
    "AdbAddress": "ADB 地址",
    "HWnd": "窗口句柄",
    "PlayCoverAddress": "PlayCover 地址",
    "PlayCoverUuid": "PlayCover UUID",
}
"""侧车字段中文标签（对齐 MaaFW 编辑页词表）"""


def read_overlay_values(config) -> dict:
    """读取配置对象的 MAS 页面核心字段（鸭子类型，仅需 ``get(group, key)``）。

    值为 ``None``（配置项不存在）的键不纳入侧车。
    """

    values: dict = {}
    for group, keys in _OVERLAY_KEY_GROUPS.items():
        for key in keys:
            if (value := getattr(getattr(config, group), key)) is not None:
                values[key] = value
    return values


def group_overlay(overlay: dict) -> dict[str, dict]:
    """把平铺的侧车字段按配置段分组（恢复回填 MaaFWUserConfig 用）。

    仅预览字段（配置来源）不回填：回填旧来源会静默翻转 shared/independent/native。
    """

    grouped: dict[str, dict] = {}
    for key, value in overlay.items():
        if key in _OVERLAY_PREVIEW_ONLY_KEYS:
            continue
        grouped.setdefault(_OVERLAY_KEY_GROUP.get(key, "Task"), {})[key] = value
    return grouped


def mas_backup_root(script_id: str, user_id: str) -> Path:
    """MAS 池归档根：``data/{script_id}/MaaFWBackups/mas/{user_id}``（恒按用户）。"""

    return Path.cwd() / "data" / script_id / "MaaFWBackups" / "mas" / user_id


def archive_mas_backup(
    script_id: str, user_id: str, overlay: dict | None, force: bool = False
) -> Path | None:
    """归档页面核心字段侧车到用户池（指纹去重，无变化跳过）。

    纯侧车：归档内唯一文件是 ``_mas_overlay.json``（无目录部分）；以内存
    JSON 直接入档（:func:`archive_files` 支持内存内容），免临时文件。
    """

    if not overlay:
        return None
    dest = _utils_config_archive.archive_files(
        {OVERLAY_SIDECAR_NAME: json.dumps(overlay, ensure_ascii=False, indent=2)},
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

    return _utils_config_archive.list_times(mas_backup_root(script_id, user_id))


def get_mas_backup_dir(script_id: str, user_id: str, ts: str) -> Path | None:
    """取用户池指定时间戳的归档目录；不存在返回 None。"""

    return _utils_config_archive.get_backup_dir(mas_backup_root(script_id, user_id), ts)


def restore_mas_backup(script_id: str, user_id: str, ts: str) -> dict | None:
    """读取用户池归档的侧车（供调用方回填 MaaFWUserConfig）；无目录目标。"""

    backup_dir = get_mas_backup_dir(script_id, user_id, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    return read_overlay_sidecar(backup_dir)


def archive_mas_runtime_backup(script_id: str, user_id: str, overlay: dict) -> None:
    """运行物化前归档本用户字段侧车（物化会覆盖项目配置，字段本身先存底）。"""

    archive_mas_backup(script_id, user_id, overlay)


# ══════════════════ MaaFW 项目配置（config/） ══════════════════

_INTERFACE_FILE = "interface.json"
"""早先的 native 备份里带着的 interface 定义：只用于预览，恢复时跳过"""

_CONFIG_PREFIX = "config/"


def native_backup_root(script_id: str, project_path: str | Path) -> Path:
    """MaaFW 项目配置的**脚本级**归档根：``data/{script_id}/MaaFWBackups/native/{key}``。

    MaaFW 是通用性专项（接入任意 MaaFW 项目，项目属于单个脚本实例）：
    归档生命周期随脚本。``key`` 取视图路径指纹，而视图路径由脚本 ID 推出、永不变，
    所以换版本、重新导入另一个项目后仍是同一个桶——这正是 interface.json 不进这个池的原因。
    """

    return (
        Path.cwd()
        / "data"
        / script_id
        / "MaaFWBackups"
        / "native"
        / _utils_config_archive.config_root_key(project_path)
    )


def collect_native_files(project_path: str | Path) -> dict[str, Path]:
    """收集 MaaFW 项目配置文件集（相对键 → 当前路径；缺失项跳过）。

    只收 ``config/**``（项目配置目录，排除 resource/ 资产）；``interface.json`` 随项目
    版本走，不归档（见模块说明）。
    """

    project_path = Path(project_path)
    files: dict[str, Path] = {}
    config_dir = project_path / "config"
    if config_dir.is_dir():
        for rel, path in _utils_config_archive.dir_files(config_dir).items():
            files[f"config/{rel}"] = path
    return files


def archive_native_backup(
    script_id: str, project_path: str | Path, force: bool = False
) -> Path | None:
    """归档 MaaFW 项目 ``config/`` 目录（指纹去重）。

    归档落到**脚本级池**（``data/{script_id}/``，生命周期随脚本实例）。
    项目缺 ``config/`` 时无可归档内容，返回 ``None``。
    """

    files = collect_native_files(project_path)
    if not files:
        return None
    dest = _utils_config_archive.archive_files(
        files, native_backup_root(script_id, project_path), force=force
    )
    if dest is None:
        logger.info("MaaFW 项目配置无变化，跳过归档")
        return None
    logger.info(f"MaaFW 项目配置已归档: {dest.name}")
    return dest


def list_native_backups(script_id: str, project_path: str | Path) -> list[str]:
    """MaaFW 项目配置全部归档时间戳（倒序，最新在前）。"""

    return _utils_config_archive.list_times(native_backup_root(script_id, project_path))


def get_native_backup_dir(
    script_id: str, project_path: str | Path, ts: str
) -> Path | None:
    """取指定时间戳的项目配置归档目录；不存在返回 None。"""

    return _utils_config_archive.get_backup_dir(
        native_backup_root(script_id, project_path), ts
    )


_NO_CONFIG_REASON_INTERFACE_ONLY = (
    "这份备份里没有项目配置（config/），只有备份时的 interface.json，仅供参考、不能恢复"
)
_NO_CONFIG_REASON = "这份备份里没有项目配置（config/），不能恢复"


def native_restore_scope(files: Mapping[str, Path]) -> tuple[list[str], str]:
    """一份 native 备份恢复时会写回哪些文件（``config/*``），以及不能恢复的原因（能恢复为空串）。

    预览与恢复共用这一份判断：预览据此返回 ``restoreAllowed`` / ``warnings``，界面禁用「一键
    恢复」并说明原因，与真点下去时的拒绝一致。早先只收了 interface.json 的备份就是不能恢复的。
    """

    managed = sorted(rel for rel in files if rel.startswith(_CONFIG_PREFIX))
    if managed:
        return managed, ""
    if _INTERFACE_FILE in files:
        return managed, _NO_CONFIG_REASON_INTERFACE_ONLY
    return managed, _NO_CONFIG_REASON


def restore_native_backup(script_id: str, project_path: str | Path, ts: str) -> None:
    """把归档恢复到 MaaFW 项目（恢复前自动归档当前，误恢复可找回）。

    只写回 ``config/*`` → 项目 ``config/``；replace 语义：``config/`` 子树整棵按备份
    替换，残留的同前缀文件一并清除，不动 ``resource/`` 等备份外资产。早先备份里的
    ``interface.json`` 跳过：它属于备份时的项目版本，写回会与视图里的资源对不上。
    """

    backup_dir = get_native_backup_dir(script_id, project_path, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    managed, reason = native_restore_scope(_utils_config_archive.dir_files(backup_dir))
    if reason:
        raise ValueError(reason)
    project_path = Path(project_path)
    archive_native_backup(script_id, project_path, force=True)
    _utils_config_archive.restore_files(backup_dir, project_path, managed)
    logger.info(f"MaaFW 项目配置已恢复备份 {ts}")


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
    """解析 JSON 对象字符串字段（TaskSnapshot），非法返回空 dict。"""

    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            loaded = json.loads(raw)
        except Exception:
            return {}
        return loaded if isinstance(loaded, dict) else {}
    return {}


def _instance_label(instance_id: str, task_label: Callable[[str], str] | None) -> str:
    if task_label is not None:
        label = task_label(instance_id)
        if label:
            return label
    head, separator, _ = instance_id.rpartition(DUPLICATE_TASK_SUFFIX_SEPARATOR)
    return (head if separator and head else instance_id).removeprefix(
        PRETASK_TASK_PREFIX
    )


def build_overlay_preview(
    overlay: dict, task_label: Callable[[str], str] | None = None
) -> dict:
    """mas 池预览：分区行（MAS 独有 / MaaFW 对应 / 设备覆盖）。

    ``task_label`` 把快照里的任务实例 ID（重复任务带 ``__MAS_DUP__`` 后缀）换成界面上
    看到的显示名；不给（读不到 interface）就只去掉重复后缀、显示任务 name。
    """

    sections: list[dict] = []

    mas_rows: list[dict] = []
    for key in ("Base", "IfQuickConfig"):
        if key in overlay:
            raw = overlay[key]
            value = (
                _format_bool(raw)
                if isinstance(raw, bool)
                else BASE_SOURCE_LABELS.get(str(raw), _summary_text(raw))
            )
            mas_rows.append({"key": _OVERLAY_FIELD_LABELS[key], "value": value})
    if mas_rows:
        sections.append({"name": "mas-only", "label": "MAS 独有配置", "rows": mas_rows})

    task_rows: list[dict] = []
    if "SelectedPreset" in overlay:
        task_rows.append(
            {"key": "当前方案", "value": _summary_text(overlay["SelectedPreset"])}
        )
    if "TaskSnapshot" in overlay:
        snapshot = _parse_json_dict(overlay["TaskSnapshot"])
        order = snapshot.get("taskOrder") or []
        checked = snapshot.get("taskChecked") or {}
        names = [
            _instance_label(name, task_label)
            for name in order
            if isinstance(name, str) and name and bool(checked.get(name, True))
        ]
        task_rows.append(
            {"key": "已启用任务", "value": "、".join(names) if names else "无"}
        )
    if "Account" in overlay:
        task_rows.append(
            {
                "key": "账号",
                "value": _utils_config_archive.mask_account(overlay["Account"]),
            }
        )
    for key in ("Controller", "Resource"):
        if key in overlay:
            task_rows.append(
                {
                    "key": _OVERLAY_FIELD_LABELS[key],
                    "value": _summary_text(overlay[key]),
                }
            )
    if task_rows:
        sections.append({"name": "maafw", "label": "MaaFW 配置", "rows": task_rows})

    device_rows: list[dict] = []
    for key in _OVERLAY_DEVICE_KEYS:
        if key in overlay and str(overlay[key]).strip():
            device_rows.append(
                {
                    "key": _OVERLAY_FIELD_LABELS[key],
                    "value": _summary_text(overlay[key]),
                }
            )
    if device_rows:
        sections.append({"name": "device", "label": "设备覆盖", "rows": device_rows})

    return {"sections": sections}


def build_native_preview(script_id: str, project_path: str | Path, ts: str) -> dict:
    """native 池预览：恢复会写回的 ``config/`` 文件，外加早先备份里 interface 的版本。

    只列恢复真正会写回的东西：``config/`` 下的文件名（不深入内容，经「查看详细配置」看
    原生）。早先的备份带着 interface.json，读出它的 ``version`` 作「备份时项目版本」参考；
    它按加载器同一口径解析（先 JSON、再 JSON5，带注释的 JSONC 也读得出）。
    """

    backup_dir = get_native_backup_dir(script_id, project_path, ts)
    if backup_dir is None:
        raise ValueError(f"备份不存在: {ts}")
    files = _utils_config_archive.dir_files(backup_dir)
    if not files:
        raise ValueError(f"备份内容为空: {ts}")

    rows: list[dict] = []
    if _INTERFACE_FILE in files:
        try:
            interface = parse_json_text(
                files[_INTERFACE_FILE].read_text(encoding="utf-8-sig")
            )
        except Exception:  # noqa: BLE001 - 坏 JSON 不阻断预览
            interface = None
        if not isinstance(interface, dict):
            version = "interface.json 无法解析"
        elif interface.get("version") is not None:
            version = _summary_text(interface["version"])
        else:
            version = "未声明"
        rows.append({"key": "备份时项目版本", "value": version})
    config_files = sorted(
        rel.removeprefix(_CONFIG_PREFIX)
        for rel in files
        if rel.startswith(_CONFIG_PREFIX)
    )
    rows.append(
        {
            "key": "项目配置文件",
            "value": _summary_text("、".join(config_files)) if config_files else "无",
        }
    )
    _, reason = native_restore_scope(files)
    return {
        "sections": [{"name": "maafw", "label": "MaaFW 项目配置", "rows": rows}],
        # 通用恢复组件认这两个键：不能恢复时禁用「一键恢复」并显示原因
        "restoreAllowed": not reason,
        "warnings": [reason] if reason else [],
    }
